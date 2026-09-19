import {schedule,japanDate,stateFrom,mergeBackup} from './core.mjs';
const STORES=['review_events','question_state','sessions','settings'];
let db;
const request=r=>new Promise((resolve,reject)=>{r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
export async function openDB() {
  db=await new Promise((resolve,reject)=>{
    const r=indexedDB.open('my-library-review',1);
    r.onupgradeneeded=()=>{
      const d=r.result;
      d.createObjectStore('review_events',{keyPath:'event_id'}).createIndex('session_item_id','session_item_id',{unique:true});
      d.createObjectStore('question_state',{keyPath:'question_id'});
      d.createObjectStore('sessions',{keyPath:'key'});
      d.createObjectStore('settings',{keyPath:'key'});
    };
    r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);
    r.onblocked=()=>reject(Error('別のタブを閉じてから再試行してください'));
  });
  db.onversionchange=()=>db.close();return db;
}
async function transaction(mode, action) {
  if(!db)throw Error('保存先を開けません。再読み込みしてください');
  const tx=db.transaction(STORES,mode);
  const done=new Promise((resolve,reject)=>{tx.oncomplete=resolve;tx.onabort=()=>reject(tx.error||Error('保存を中止しました'));tx.onerror=()=>{};});
  const stores=Object.fromEntries(STORES.map(n=>[n,tx.objectStore(n)]));
  try {const value=await action(stores);await done;return value;}
  catch(e){try{tx.abort();}catch{} await done.catch(()=>{});throw e;}
}
export async function snapshot() {
  return transaction('readonly',async s=>{
    const [events,states,session,settings]=await Promise.all([
      request(s.review_events.getAll()),request(s.question_state.getAll()),request(s.sessions.get('active')),request(s.settings.get('preferences'))]);
    return {events,states:Object.fromEntries(states.map(q=>[q.question_id,q])),session,settings:settings?.value||{}};
  });
}
export async function start(items,mode) {
  return transaction('readwrite',async s=>{
    const old=await request(s.sessions.get('active'));
    if(old&&!old.finished)return old;
    const session={key:'active',schema_version:1,session_id:crypto.randomUUID(),started_at:new Date().toISOString(),
      mode,items:items.map(q=>({...q,session_item_id:crypto.randomUUID()})),position:0,revealed:false,answer:'',finished:false};
    s.sessions.put(session);return session;
  });
}
export async function progress(session, changes) {
  return transaction('readwrite',async s=>{
    const current=await request(s.sessions.get('active'));
    if(!current||current.session_id!==session.session_id||current.position!==session.position||current.finished)throw Error('別のタブで進みました。ホームから再開してください');
    Object.assign(current,changes);s.sessions.put(current);return current;
  });
}
export async function rate(session,rating) {
  return transaction('readwrite',async s=>{
    const current=await request(s.sessions.get('active'));
    if(!current||current.session_id!==session.session_id||current.position!==session.position||current.finished||!current.revealed)throw Error('この問題は保存済みか、別のタブで変更されています');
    const q=current.items[current.position];
    const [events,states]=await Promise.all([request(s.review_events.getAll()),request(s.question_state.getAll())]);
    if(events.some(e=>e.session_item_id===q.session_item_id))throw Error('この評価は保存済みです');
    const allStates=Object.fromEntries(states.map(x=>[x.question_id,x]));
    const before=allStates[q.question_id]?.stage??null, now=new Date().toISOString(),day=japanDate(now);
    const next=schedule(before,rating,day);
    const event={schema_version:1,event_id:crypto.randomUUID(),question_id:q.question_id,reviewed_at:now,
      study_date:day,rating,stage_before:before,stage_after:next.stage,next_review_at:next.next_review_at,
      session_id:current.session_id,session_item_id:q.session_item_id};
    s.review_events.add(event);
    s.question_state.put(stateFrom([...events,event],allStates)[q.question_id]);
    current.position++;current.revealed=false;current.answer='';current.finished=current.position===current.items.length;
    s.sessions.put(current);return current;
  });
}
export async function star(id) {
  return transaction('readwrite',async s=>{
    const value=await request(s.question_state.get(id))||{schema_version:1,question_id:id,is_starred:false};
    value.is_starred=!value.is_starred;value.star_updated_at=new Date().toISOString();s.question_state.put(value);
  });
}
export async function backup() {
  const data=await snapshot();
  return {schema_version:1,app_version:'1.0.0',timezone:'Asia/Tokyo',created_at:new Date().toISOString(),
    review_events:data.events,question_state:Object.values(data.states),settings:data.settings};
}
export async function restore(data, apply=false) {
  return transaction(apply?'readwrite':'readonly',async s=>{
    const [events,states,settings]=await Promise.all([request(s.review_events.getAll()),request(s.question_state.getAll()),request(s.settings.get('preferences'))]);
    const merged=mergeBackup(events,Object.fromEntries(states.map(x=>[x.question_id,x])),data);
    if(apply) {
      for(const event of merged.events)s.review_events.put(event);
      for(const state of Object.values(merged.states))s.question_state.put(state);
      if(!settings)s.settings.put({key:'preferences',schema_version:1,value:data.settings});
    }
    return merged;
  });
}
