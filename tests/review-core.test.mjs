import test from 'node:test';
import assert from 'node:assert/strict';
import {japanDate,addDays,schedule,queue,stateFrom,weakness,mergeBackup,safeURL} from '../app/core.mjs';
test('Japan midnight, month/year boundaries, stage transitions',()=>{
  assert.equal(japanDate('2026-09-19T14:59:59Z'),'2026-09-19');
  assert.equal(japanDate('2026-09-19T15:00:00Z'),'2026-09-20');
  assert.equal(addDays('2026-12-31',1),'2027-01-01');assert.equal(addDays('2028-02-28',1),'2028-02-29');
  for(const [rating,stage] of [['forgot',0],['unsure',2],['remembered',4],['perfect',5]]) assert.equal(schedule(3,rating,'2026-09-19').stage,stage);
  assert.equal(schedule(0,'unsure','2026-09-19').stage,0);assert.equal(schedule(5,'perfect','2026-09-19').stage,5);
  assert.deepEqual(['forgot','unsure','remembered','perfect'].map(r=>schedule(null,r,'2026-09-19').stage),[0,0,1,2]);
});
const day='2026-09-19';
const questions=Array.from({length:40},(_,i)=>({question_id:'q'+i,lesson_id:'l'+i%3,type:'free_response',status:'active'}));
test('queue limits, due-only all, no duplicate, new cap and lesson interleaving',()=>{
  const states=Object.fromEntries(questions.slice(0,20).map(q=>[q.question_id,{review_count:1,next_review_at:day}]));
  const five=queue(questions,states,[],'5',day);assert.ok(five.length<=5);assert.equal(new Set(five.map(q=>q.question_id)).size,five.length);
  assert.ok(five.every(q=>states[q.question_id]));
  assert.equal(queue(questions,states,[],'all',day).length,20);
  assert.equal(queue(questions,{},[],'all',day).length,0);
  assert.equal(queue(questions,{},[],'10',day).length,10);
  for(let i=2;i<five.length;i++)assert.ok(new Set(five.slice(i-2,i+1).map(q=>q.lesson_id)).size>1);
});
test('future weak/star never displaces due; 5-minute ratio is final-count based',()=>{
  const states=Object.fromEntries(questions.slice(0,3).map(q=>[q.question_id,{review_count:1,next_review_at:day}]));
  states.q3={review_count:1,next_review_at:'2027-01-01',is_starred:true};
  const result=queue(questions,states,[],'5',day);
  assert.deepEqual(new Set(result.slice(0,3).map(q=>q.question_id)),new Set(['q0','q1','q2']));
  assert.ok(result.filter(q=>!states[q.question_id]).length<=Math.floor(result.length*.4));
});
function event(i,rating='remembered'){
  const date=new Date(Date.UTC(2026,8,1+i)).toISOString(),study_date=japanDate(date),next=schedule(null,rating,study_date);
  return {schema_version:1,event_id:'e'+i,question_id:'q',reviewed_at:date,study_date,rating,stage_before:null,stage_after:next.stage,next_review_at:next.next_review_at,session_id:'s'+i,session_item_id:'si'+i};
}
function backup(events){return {schema_version:1,app_version:'1',timezone:'Asia/Tokyo',created_at:'2026-09-19T00:00:00.000Z',review_events:events,question_state:[],settings:{}};}
test('weakness only uses latest ten, improves, star and overdue are current bonuses',()=>{
  const events=Array.from({length:20},(_,i)=>event(i,i<10?'forgot':'perfect'));
  assert.equal(weakness('q',{review_count:20,next_review_at:'2026-09-01',is_starred:true},events,day),0);
  assert.equal(weakness('q',{review_count:1,next_review_at:'2026-09-01',is_starred:true},[event(0,'forgot')],day),8);
  assert.equal(weakness('q',{},events,day),null);
});
test('backup round trip, idempotence, collision and unknown IDs',()=>{
  const events=[event(0)],data=backup(events),first=mergeBackup([],{},data);
  assert.equal(first.added,1);assert.equal(first.states.q.stage,1);
  assert.equal(mergeBackup(first.events,first.states,data).added,0);
  const conflict=structuredClone(data);conflict.review_events[0].session_id='different';
  assert.throws(()=>mergeBackup(first.events,first.states,conflict));
  const bad=structuredClone(data);bad.schema_version=2;assert.throws(()=>mergeBackup([],{},bad));
  const wrong=structuredClone(data);wrong.review_events[0].next_review_at='2026-02-30';assert.throws(()=>mergeBackup([],{},wrong));
  const duplicate=structuredClone(data);duplicate.review_events.push({...events[0],event_id:'other'});assert.throws(()=>mergeBackup([],{},duplicate));
});
test('safe URLs support project base, Japanese and spaces; reject traversal/schemes',()=>{
  const base=new URL('https://example.com/my-library/');
  assert.equal(new URL(safeURL('教材/a b.html',base,'#one')).hash,'#one');
  for(const path of ['../secret','https://evil.test/','javascript:alert(1)','/root','a\\b','a?b'])assert.throws(()=>safeURL(path,base));
});
