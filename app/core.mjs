export const VERSION = 1;
export const INTERVALS = [1, 3, 7, 14, 30, 60];
export const RATINGS = ['forgot', 'unsure', 'remembered', 'perfect'];
export const SECONDS = {true_false:20, choice:30, fill_blank:30, reveal:40, free_response:60};
export function japanDate(value = new Date()) {
  return new Date(new Date(value).getTime() + 9 * 3600000).toISOString().slice(0,10);
}
export function addDays(day, days) {
  const date = new Date(day + 'T00:00:00Z'); date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0,10);
}
export function schedule(stage, rating, day) {
  if (!RATINGS.includes(rating)) throw Error('不正な評価です');
  const next = stage == null ? [0,0,1,2][RATINGS.indexOf(rating)]
    : rating === 'forgot' ? 0 : rating === 'unsure' ? Math.max(0,stage-1)
    : Math.min(5,stage + (rating === 'perfect' ? 2 : 1));
  return {stage:next, next_review_at:addDays(day, INTERVALS[next])};
}
export function stateFrom(events, stars = {}) {
  const states = structuredClone(stars);
  for (const value of Object.values(states)) {
    for (const key of Object.keys(value)) if (!['question_id','is_starred','star_updated_at'].includes(key)) delete value[key];
    value.schema_version = 1;
  }
  for (const event of [...events].sort((a,b)=>a.reviewed_at.localeCompare(b.reviewed_at)||a.event_id.localeCompare(b.event_id))) {
    const prior = states[event.question_id] || {question_id:event.question_id, is_starred:false};
    const next = schedule(prior.stage, event.rating, event.study_date);
    const ratings = {...prior.ratings}; ratings[event.rating] = (ratings[event.rating]||0)+1;
    states[event.question_id] = {...prior, ...next, schema_version:1, last_reviewed_at:event.reviewed_at,
      review_count:(prior.review_count||0)+1, ratings, lapse_count:(prior.lapse_count||0)+(event.rating==='forgot'?1:0)};
  }
  return states;
}
export function weakness(id, state, events, today) {
  if (!state?.review_count) return null;
  const points = {forgot:4,unsure:2,remembered:-1,perfect:-2};
  const recent = events.filter(e=>e.question_id===id).sort((a,b)=>b.reviewed_at.localeCompare(a.reviewed_at)||b.event_id.localeCompare(a.event_id)).slice(0,10);
  return Math.max(0,recent.reduce((n,e)=>n+points[e.rating],0)+(state.next_review_at<today?1:0)+(state.is_starred?3:0));
}
export function queue(questions, states, events, mode, today = japanDate(), exclude = []) {
  const candidates = questions.filter(q=>q.status==='active'&&!exclude.includes(q.question_id));
  const due = q=>states[q.question_id]?.next_review_at <= today;
  const fresh = q=>!states[q.question_id]?.review_count;
  const score = q=>weakness(q.question_id,states[q.question_id],events,today)||0;
  const rank = q=> {
    const s = states[q.question_id];
    if (s?.next_review_at<today) return 0;
    if (due(q) && score(q)>=6) return 1;
    if (due(q)) return 2;
    if (fresh(q)) return 3;
    return score(q)>=6 ? 4 : s?.is_starred ? 5 : 6;
  };
  candidates.sort((a,b)=>rank(a)-rank(b)
    || (rank(a)===0 ? states[a.question_id].next_review_at.localeCompare(states[b.question_id].next_review_at):0)
    || score(b)-score(a)
    || (states[a.question_id]?.last_reviewed_at||'').localeCompare(states[b.question_id]?.last_reviewed_at||'')
    || a.question_id.localeCompare(b.question_id));
  const max = mode==='all' ? Infinity : mode==='10' ? 15 : 8;
  const budget = mode==='all' ? Infinity : mode==='10' ? 600 : 300;
  const countDue = candidates.filter(due).length;
  const ratio = countDue>=2*max ? 0 : countDue>=max/2 ? .2 : countDue>0 ? .4 : 1;
  let time=0,newCount=0;
  const selected=[];
  const remaining = candidates.filter(q=>mode!=='all'||due(q));
  while (remaining.length && selected.length<max) {
    let i = remaining.findIndex(q=>time+SECONDS[q.type]<=budget && (!fresh(q)||newCount<Math.floor(max*ratio)));
    if (i<0) break;
    if (selected.length>=2 && selected.at(-1).lesson_id===selected.at(-2).lesson_id && remaining[i].lesson_id===selected.at(-1).lesson_id) {
      const other = remaining.findIndex(q=>rank(q)===rank(remaining[i]) && q.lesson_id!==selected.at(-1).lesson_id
        && time+SECONDS[q.type]<=budget && (!fresh(q)||newCount<Math.floor(max*ratio)));
      if(other>=0) i=other;
    }
    const [q]=remaining.splice(i,1); selected.push(q); time+=SECONDS[q.type]; if(fresh(q)) newCount++;
  }
  // Re-evaluate after every removal: reducing the denominator can reduce the cap.
  while(mode!=='all' && newCount>Math.floor(selected.length*ratio)) {
    const index=selected.findLastIndex(fresh); if(index<0)break;
    selected.splice(index,1); newCount--;
  }
  return selected;
}
function validDate(s) {
  return typeof s==='string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s+'T00:00:00Z')) && new Date(s+'T00:00:00Z').toISOString().slice(0,10)===s;
}
function timestamp(s) { return typeof s==='string' && !Number.isNaN(Date.parse(s)) && new Date(s).toISOString()===s; }
function id(s) { return typeof s==='string' && s.length>0 && s.length<400 && !['__proto__','constructor','prototype'].includes(s); }
function canonical(v) {
  if(Array.isArray(v)) return '['+v.map(canonical).join(',')+']';
  if(v&&typeof v==='object')return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';
  return JSON.stringify(v);
}
export function validateBackup(data) {
  if(data.schema_version!==1 || data.timezone!=='Asia/Tokyo' || !timestamp(data.created_at)
    || typeof data.app_version!=='string' || !Array.isArray(data.review_events) || !Array.isArray(data.question_state)
    || !data.settings || typeof data.settings!=='object' || Array.isArray(data.settings)) throw Error('対応していないバックアップ形式です');
  if(data.review_events.length>200000 || data.question_state.length>100000)throw Error('バックアップが大きすぎます');
  const ids=new Set(),items=new Set(),stars={};
  for(const e of data.review_events) {
    if(e.schema_version!==1 || ![e.event_id,e.question_id,e.session_id,e.session_item_id].every(id)
      || ids.has(e.event_id) || items.has(e.session_item_id) || !timestamp(e.reviewed_at)
      || e.study_date!==japanDate(e.reviewed_at) || !validDate(e.next_review_at) || !RATINGS.includes(e.rating)
      || !(e.stage_before===null || Number.isInteger(e.stage_before)&&e.stage_before>=0&&e.stage_before<=5)) throw Error('不正または重複した学習履歴です');
    const expected=schedule(e.stage_before,e.rating,e.study_date);
    if(e.stage_after!==expected.stage || e.next_review_at!==expected.next_review_at)throw Error('復習予定の整合性がありません');
    ids.add(e.event_id);items.add(e.session_item_id);
  }
  for(const s of data.question_state) {
    if(s.schema_version!==1||!id(s.question_id)||Object.hasOwn(stars,s.question_id)||typeof s.is_starred!=='boolean'
      || (s.star_updated_at!=null&&!timestamp(s.star_updated_at)))throw Error('不正な重点設定です');
    stars[s.question_id]={question_id:s.question_id,is_starred:s.is_starred,star_updated_at:s.star_updated_at};
  }
  return {events:data.review_events,stars,settings:data.settings};
}
export function mergeBackup(existingEvents, existingStates, data) {
  const incoming=validateBackup(data), all=new Map(existingEvents.map(e=>[e.event_id,e]));
  const items=new Map(existingEvents.map(e=>[e.session_item_id,e.event_id]));
  let duplicates=0,starConflicts=0;
  for(const e of incoming.events) {
    if(all.has(e.event_id)) {
      if(canonical(all.get(e.event_id))!==canonical(e))throw Error('同じIDに異なる履歴があります。復元を中止しました');
      duplicates++;continue;
    }
    if(items.has(e.session_item_id))throw Error('同じ出題への重複評価があります');
    all.set(e.event_id,e);items.set(e.session_item_id,e.event_id);
  }
  const stars=structuredClone(existingStates);
  for(const [key,s] of Object.entries(incoming.stars)) {
    const old=stars[key];
    if(!old || (s.star_updated_at||'')>(old.star_updated_at||'')) stars[key]=s;
    else if(s.star_updated_at===old.star_updated_at && s.is_starred!==old.is_starred)starConflicts++;
  }
  const events=[...all.values()], states=stateFrom(events,stars);
  return {events,states,duplicates,starConflicts,added:events.length-existingEvents.length};
}
export function safeURL(path, base, anchor='') {
  if(typeof path!=='string'||!path||/^[a-z][a-z0-9+.-]*:/i.test(path)||path.startsWith('/')
    ||/[\\\x00-\x1f?#]/.test(path)||path.split('/').some(p=>p==='..'||p==='.'||!p))throw Error('安全でない教材パスです');
  const url=new URL(path.split('/').map(encodeURIComponent).join('/'),base);
  if(url.origin!==base.origin||!url.pathname.startsWith(base.pathname))throw Error('教材が公開範囲外です');
  if(anchor) {if(!anchor.startsWith('#'))throw Error('不正なアンカーです');url.hash=anchor.slice(1);}
  return url.href;
}
