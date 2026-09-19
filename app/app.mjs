import {japanDate,queue,weakness,safeURL,RATINGS,SECONDS} from './core.mjs';
import * as db from './db.mjs';
const base=new URL('../',location.href), main=document.querySelector('#main'),notice=document.querySelector('#notice');
const labels={forgot:'忘れた',unsure:'微妙',remembered:'覚えていた',perfect:'完璧'};
const typeLabels={true_false:'○×',choice:'4択',fill_blank:'穴埋め',reveal:'答えを見る',free_response:'記述・自己採点'};
const levelLabels={basic:'基礎',understanding:'理解',application:'応用'};
const statusLabels={success:'準備完了',blocked:'問題の準備待ち',pending:'準備中',failed:'生成の再試行待ち',stale:'教材の更新待ち'};
let library=[],questions=[],data,view='home',loadError='',ready=false,busy=false;
function el(tag,text,attrs={}) {
  const node=document.createElement(tag);if(text!==undefined&&text!==null)node.textContent=String(text);
  for(const [key,value] of Object.entries(attrs)) node.setAttribute(key,value);
  return node;
}
function block(...children){const node=el('section',null,{class:'card'});node.append(...children);return node;}
function button(text,action,cls=''){
  const node=el('button',text,{class:cls});node.addEventListener('click',()=>guard(action));return node;
}
async function guard(action){
  if(busy)return;busy=true;notice.textContent='';
  document.querySelectorAll('button').forEach(b=>b.disabled=true);
  try{await action();}catch(e){notice.textContent='操作を完了できませんでした。'+e.message;}
  finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false);}
}
async function json(path){const response=await fetch(safeURL(path,base),{cache:'no-store'});if(!response.ok)throw Error('データを取得できません');return response.json();}
function checkQuestion(q,lesson){
  if(!q||typeof q.question_id!=='string'||!q.question_id.startsWith(lesson.lesson_id+':')||!Object.hasOwn(SECONDS,q.type)
    ||!['active','deprecated','inactive'].includes(q.status)||typeof q.question!=='string'||!q.question.trim()
    ||typeof q.explanation!=='string'||!q.source||q.source.path!==lesson.source_path||!q.source.anchor?.startsWith('#'))throw Error('問題データが不正です');
  safeURL(q.source.path,base,q.source.anchor);
  if(q.type==='true_false'?typeof q.answer!=='boolean':typeof q.answer!=='string')throw Error('解答データが不正です');
  if(q.type==='choice'&&(!Array.isArray(q.choices)||q.choices.length!==4||new Set(q.choices.map(c=>c.id)).size!==4
    ||q.choices.some(c=>typeof c.text!=='string'||typeof c.id!=='string')||!q.choices.some(c=>c.id===q.answer)))throw Error('選択肢が不正です');
}
function stable(value){if(Array.isArray(value))return '['+value.map(stable).join(',')+']';if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+stable(value[k])).join(',')+'}';return JSON.stringify(value);}
async function hash(value){const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(stable(value)));return [...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');}
async function load(){
  loadError='';library=[];questions=[];
  try{
    const result=await json('review/library.json');
    if(result.schema_version!==1||!Array.isArray(result.lessons))throw Error('教材一覧の形式が不正です');
    const ids=new Set(),qids=new Set();
    for(const l of result.lessons){
      if(!/^[a-z0-9][a-z0-9._-]{0,119}$/.test(l.lesson_id)||ids.has(l.lesson_id))throw Error('教材IDが重複しています');
      ids.add(l.lesson_id);safeURL(l.source_path,base);safeURL(l.review_path,base);
    }
    library=result.lessons;
    for(const lesson of library.filter(l=>l.status==='active'&&l.generation_status==='success')){
      try{
        const r=await json(lesson.review_path);
        if(r.schema_version!==1||r.lesson_id!==lesson.lesson_id||r.content_hash!==lesson.content_hash||!Array.isArray(r.questions)
          ||r.content_hash!==lesson.review_content_hash||await hash(r)!==lesson.review_hash)throw Error('教材と問題の版が一致しません');
        const active=r.questions.filter(q=>q.status==='active');
        if(active.length!==lesson.question_count)throw Error('問題件数が一致しません');
        const localIds=new Set();
        for(const q of active){checkQuestion(q,lesson);if(qids.has(q.question_id)||localIds.has(q.question_id))throw Error('問題IDが重複しています');localIds.add(q.question_id);}
        localIds.forEach(id=>qids.add(id));
        questions.push(...active.map(q=>({...q,lesson_id:lesson.lesson_id,lesson_title:lesson.title,content_hash:r.content_hash})));
      }catch(e){lesson.generation_status='stale';lesson.client_error=e.message;loadError='一部の問題を取得できません。再読み込みで再試行できます。';}
    }
  }catch(e){questions=[];library=[];loadError=e.message;}
}
async function render(next=view){
  view=next;
  if(ready)data=await db.snapshot();
  main.replaceChildren();
  document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-current',b.dataset.view===view?'page':'false'));
  if(!ready){main.append(el('h1','保存先を開けません'),el('p','履歴は初期化していません。他のタブを閉じ、ブラウザの保存設定を確認してください。'),button('再読み込み',()=>location.reload()));return;}
  if(view==='home')home();else if(view==='lessons')lessons();else if(view==='settings')settings();else if(view==='history')history();else if(view==='question')question();else finish();
  main.focus({preventScroll:true});
}
function home(){
  const today=japanDate(),due=questions.filter(q=>data.states[q.question_id]?.next_review_at<=today),over=due.filter(q=>data.states[q.question_id].next_review_at<today);
  const fresh=questions.filter(q=>!data.states[q.question_id]?.review_count);
  main.append(el('p',today,{class:'muted'}),el('h1','今日も、少しずつ。'),el('p','思い出す時間を、5分から。',{class:'muted'}));
  const stats=el('div',null,{class:'stats'});
  for(const [n,label] of [[due.length,'今日の復習'],[fresh.length,'新規']]){const d=el('div');d.append(el('strong',n),el('span',label));stats.append(d);}
  main.append(block(stats,el('p',`今日の復習のうち、期限を過ぎた問題 ${over.length} 件`,{class:'muted'})));
  if(data.session&&!data.session.finished)main.append(button('中断した復習を再開',()=>render('question'),'primary'));
  const modes=el('div',null,{class:'modes'});
  for(const [mode,title,note] of [['5','5分だけ復習','最大8問 · 気軽にひと区切り'],['10','10分じっくり','最大15問 · 少し広く思い出す'],['all','今日の復習全部','期限が来た問題だけ']]){
    const b=button(title,()=>begin(mode),mode==='5'?'primary':'');b.append(el('small',note));modes.append(b);
  }main.append(modes);
  if(!questions.length)main.append(block(el('h2','問題を準備しています'),el('p','学習履歴の保存先は準備できています。問題生成が完了すると、ここから復習を始められます。'),button('教材を確認',()=>render('lessons'))));
  const weak=questions.filter(q=>weakness(q.question_id,data.states[q.question_id],data.events,today)>=6);
  if(weak.length)main.append(block(el('h2','もう一度確認したい分野'),el('p',[...new Set(weak.map(q=>q.lesson_title))].join('・'))));
  const days=new Set(data.events.map(e=>e.study_date));
  if(days.size)main.append(el('p',`これまで ${days.size} 日、学習しました。`,{class:'muted'}));
  main.append(scopeList());
  if(loadError)main.append(block(el('p',loadError),button('データを再読み込み',async()=>{await load();await render();})));
}
async function begin(mode,exclude=[]){
  const latest=await db.snapshot();
  if(latest.session&&!latest.session.finished){await render('question');return;}
  const items=queue(questions,latest.states,latest.events,mode,japanDate(),exclude);
  if(!items.length){notice.textContent=mode==='all'?'今日の復習はありません。5分・10分モードから新しい問題を学べます。':'今、出題できる問題はありません。教材の準備状況をご確認ください。';return;}
  await db.start(items,mode);await render('question');
}
function scopeList(){
  const section=block(el('h2','教材の範囲'),el('p',`登録済み ${library.length} ファイル。問題の準備状況にかかわらず、元の教材を開けます。`,{class:'muted'}));
  const groups=new Map();
  for(const l of library){const category=l.categories?.[0]||'その他';if(!groups.has(category))groups.set(category,[]);groups.get(category).push(l);}
  for(const [category,items] of [...groups].sort(([a],[b])=>a.localeCompare(b))){
    section.append(el('h3',`${category.replace('_',' ')}（${items.length}ファイル）`));
    const list=el('ul',null,{class:'scope-list'});
    for(const l of items){
      const item=el('li');
      item.append(el('a',l.title,{href:safeURL(l.source_path,base)}),el('p',l.source_path,{class:'source-path muted'}),
        el('span',statusLabels[l.generation_status]||'対象外',{class:'tag'}),
        el('p',l.generation_status==='success'?`${l.question_count} 問`:l.client_error||l.reason||'問題が準備できるまで、元の教材を読むことができます。',{class:'muted'}));
      list.append(item);
    }
    section.append(list);
  }
  if(!library.length)section.append(el('p',loadError||'教材はまだ登録されていません。'));
  return section;
}
function lessons(){
  main.append(el('h1','教材'));
  main.append(scopeList());
  main.append(button('再読み込み',async()=>{await load();await render();}));
}
function question(){
  const session=data.session;
  if(!session){home();return;}if(session.finished){finish();return;}
  const q=session.items[session.position];
  checkQuestion(q,{lesson_id:q.lesson_id,source_path:q.source.path});
  main.append(el('p',q.lesson_title,{class:'muted'}),el('progress',null,{value:session.position,max:session.items.length,'aria-label':'復習の進み具合'}),
    el('p',`${session.position+1} / ${session.items.length} · ${typeLabels[q.type]} · ${levelLabels[q.level]||''}`,{class:'muted'}),el('h1',q.question));
  const star=button(data.states[q.question_id]?.is_starred?'★ 重点を解除':'☆ 重点にする',async()=>{await db.star(q.question_id);await render();});
  star.setAttribute('aria-pressed',String(!!data.states[q.question_id]?.is_starred));main.append(star);
  if(!session.revealed){
    if(q.type==='choice'||q.type==='true_false'){
      const choices=q.type==='choice'?q.choices:[{id:true,text:'○ 正しい'},{id:false,text:'× 誤り'}], area=el('div',null,{class:'choices card'});
      for(const c of choices)area.append(button(c.text,async()=>{await db.progress(session,{answer:c.id,revealed:true});await render();}));
      main.append(area);
    }else{
      let input;
      if(q.type!=='reveal'){
        input=el(q.type==='free_response'?'textarea':'input',null,{id:'answer','aria-label':'あなたの回答',maxlength:'10000'});input.value=session.answer||'';
        main.append(el('label','あなたの回答',{for:'answer'}),input);
        // Persist typing without taking the global busy lock. A blur transaction must not
        // swallow the click on the reveal button by taking the global busy lock.
        input.addEventListener('input',()=>{
          db.progress(session,{answer:input.value}).catch(e=>{notice.textContent='回答を保存できませんでした。'+e.message;});
        });
      }
      main.append(button('答えを見る',async()=>{await db.progress(session,{answer:input?.value||'',revealed:true});await render();},'primary'));
    }
  }else{
    const correct=q.type==='choice'?q.choices.find(c=>c.id===q.answer).text:q.type==='true_false'?(q.answer?'○ 正しい':'× 誤り'):q.answer;
    const answer=block(el('h2','答え'),el('p',correct,{class:'answer'}),el('p',q.explanation,{class:'answer'}));
    if(['choice','true_false'].includes(q.type))answer.prepend(el('p',session.answer===q.answer?'○ 正解':'× 答えを確認しましょう',{class:'tag'}));
    else if(session.answer)answer.append(el('h3','あなたの回答'),el('p',session.answer,{class:'answer'}));
    answer.append(button('教材で確認する',()=>openSource(q)));
    main.append(answer,el('p','どのくらい思い出せましたか？ 保存すると次へ進みます。'));
    const ratings=el('div',null,{class:'ratings'});
    RATINGS.forEach(r=>ratings.append(button(labels[r],async()=>{await db.rate(session,r);await render('question');})));
    main.append(ratings);
  }
  main.append(el('p','未評価の問題は学習実績に含まれません。',{class:'muted'}),button('中断してホームへ',async()=>{
    const input=document.querySelector('#answer');if(input)await db.progress(session,{answer:input.value});await render('home');
  }));
}
async function openSource(q){
  const url=safeURL(q.source.path,base,q.source.anchor);
  try{
    const response=await fetch(url,{cache:'no-store'});if(!response.ok)throw Error();
    const document=new DOMParser().parseFromString(await response.text(),'text/html');
    if(!document.getElementById(q.source.anchor.slice(1)))throw Error();
  }catch{notice.textContent='教材の該当箇所を開けません。この問題の復習は続けられます。';return;}
  // Session is already persisted before navigation; Back resumes this question.
  sessionStorage.setItem('review-return','question');location.assign(url);
}
function finish(){
  const session=data.session,events=data.events.filter(e=>e.session_id===session?.session_id);
  main.append(el('h1','おつかれさまでした。'),el('p',`${events.length} 問の復習を保存しました。`));
  const summary=block(el('h2','今回の復習'));
  RATINGS.forEach(r=>summary.append(el('p',`${labels[r]}：${events.filter(e=>e.rating===r).length} 問`)));
  const dates={};for(const e of events)dates[data.states[e.question_id]?.next_review_at]=(dates[data.states[e.question_id]?.next_review_at]||0)+1;
  summary.append(el('h3','今回復習した問題の次回予定'));
  Object.entries(dates).sort().forEach(([date,count])=>summary.append(el('p',`${date}：${count} 問`)));main.append(summary);
  main.append(button('もう5分',()=>begin('5',data.events.filter(e=>e.study_date===japanDate()&&e.session_id===session?.session_id).map(e=>e.question_id)),'primary'),button('ホームへ',()=>render('home')));
}
function history(){
  main.append(el('h1','学習履歴'),el('p','最新100件を表示します。全履歴はバックアップに含まれます。',{class:'muted'}));
  if(!data.events.length)main.append(el('p','復習を終えると、ここに記録が残ります。'));
  for(const e of [...data.events].sort((a,b)=>b.reviewed_at.localeCompare(a.reviewed_at)).slice(0,100)){
    const q=questions.find(q=>q.question_id===e.question_id),row=el('div',null,{class:'history-row'});
    row.append(el('small',`${e.study_date} · ${labels[e.rating]}`),el('p',q?.question||`過去の問題：${e.question_id}`));
    if(q)row.append(el('a',q.lesson_title,{href:safeURL(q.source.path,base,q.source.anchor)}));main.append(row);
  }
}
function settings(){
  main.append(el('h1','設定とバックアップ'),el('p','履歴はこの端末・ブラウザ専用です。ブラウザのデータ削除や端末交換に備え、定期的に保存してください。'));
  main.append(button('JSONバックアップを保存',async()=>{
    const blob=new Blob([JSON.stringify(await db.backup(),null,2)],{type:'application/json'}),url=URL.createObjectURL(blob);
    const a=el('a',null,{href:url,download:`my-library-review-${japanDate()}.json`});a.click();setTimeout(()=>URL.revokeObjectURL(url),3000);
  },'primary'));
  const label=el('label','バックアップを読み込む',{for:'import'}),input=el('input',null,{type:'file',accept:'.json,application/json',id:'import'}),result=el('div');
  input.addEventListener('change',()=>guard(async()=>{
    result.replaceChildren();const file=input.files[0];if(!file)return;if(file.size>50000000)throw Error('50MB以下のファイルを選んでください');
    const backup=JSON.parse(await file.text()),preview=await db.restore(backup);
    result.append(el('p',`追加 ${preview.added} 件、重複 ${preview.duplicates} 件、★の同時刻競合 ${preview.starConflicts} 件。既存履歴は残します。`),
      button('確認して復元する',async()=>{const merged=await db.restore(backup,true);await render('settings');notice.textContent=`復元しました。追加 ${merged.added} 件、重複 ${merged.duplicates} 件。`},'primary'));
  }));
  main.append(block(label,input,result));
  if(navigator.storage?.persist)main.append(button('ブラウザに保存領域の保持を依頼',async()=>{notice.textContent=await navigator.storage.persist()?'保存領域の保持が許可されました。バックアップも続けてください。':'保持は許可されませんでした。定期的にバックアップしてください。';}));
  main.append(el('p','復習日の切り替えは日本時間の午前0時です。色は端末の明暗設定に従います。ホーム画面への追加はブラウザのメニューから行えます。',{class:'muted'}));
}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>guard(()=>render(b.dataset.view))));
window.addEventListener('pageshow',event=>{if(event.persisted&&ready)guard(()=>render('question'));});
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&ready)guard(()=>render());});
try{await db.openDB();ready=true;}catch(e){notice.textContent=e.message;}
await load();
const returnView=sessionStorage.getItem('review-return');sessionStorage.removeItem('review-return');
await render(returnView==='question'?'question':'home');
