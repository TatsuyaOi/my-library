// Isolated browser tests. Fixture responses are never written to the public site.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdir} from 'node:fs/promises';
import {join} from 'node:path';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const url=process.env.REVIEW_TEST_URL||'http://127.0.0.1:8000/app/';
const browser=await chromium.launch({channel:'chrome',headless:true});
const context=await browser.newContext({viewport:{width:390,height:844}});
const page=await context.newPage();
const errors=[];page.on('pageerror',e=>errors.push(e.message));
function stable(v){if(Array.isArray(v))return '['+v.map(stable).join(',')+']';if(v&&typeof v==='object')return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+stable(v[k])).join(',')+'}';return JSON.stringify(v);}
const types=['true_false','choice','fill_blank','reveal','free_response'];
const questions=types.map((type,i)=>({question_id:`fixture:c${i}:${type}:1`,concept_key:`c${i}`,revision:1,type,
  level:'basic',difficulty:1,importance:'high',question:`テスト問題 ${i+1}`,answer:type==='true_false'?true:type==='choice'?'a':'短い',
  explanation:'テスト専用の説明です。公開教材ではありません。',source:{path:'fixture.html',anchor:'#one',evidence:'短い'},tags:[],status:'active',
  ...(type==='choice'?{choices:['a','b','c','d'].map(id=>({id,text:`選択肢 ${id}`}))}:{})}));
const review={schema_version:1,lesson_id:'fixture',content_hash:'a'.repeat(64),generated_at:'2026-09-19T00:00:00+00:00',questions};
const manifest={schema_version:1,lessons:[{lesson_id:'fixture',title:'テスト専用教材',source_path:'fixture.html',review_path:'review/fixture.json',
  status:'active',generation_status:'success',question_count:5,content_hash:review.content_hash,review_content_hash:review.content_hash,
  review_hash:createHash('sha256').update(stable(review)).digest('hex')}]};
try{
  // First test the real blocked state before applying test-only routes.
  await page.goto(url);await page.getByRole('heading',{name:'今日も、少しずつ。'}).waitFor();
  await page.getByRole('heading',{name:'問題を準備しています'}).waitFor();
  await page.getByRole('heading',{name:'教材の範囲',exact:true}).waitFor();
  const liveManifest=await (await page.request.get(new URL('../review/library.json',url).href)).json();
  assert.equal(liveManifest.lessons.length,14);
  assert.equal(await page.locator('.scope-list a').count(),14);
  for(const lesson of liveManifest.lessons){
    await page.getByText(lesson.source_path,{exact:true}).waitFor();
    assert.equal(await page.locator('.scope-list a').evaluateAll(links=>links.map(a=>decodeURI(new URL(a.href).pathname))).then(paths=>paths.includes('/'+lesson.source_path)),true);
  }
  for(const [category,count] of [['11 哲学',3],['21 基本情報',1],['22 簿記',2],['41 AI',2],['51 仕事',6]])
    await page.getByRole('heading',{name:`${category}（${count}ファイル）`,exact:true}).waitFor();
  for(const width of [360,390,412])for(const colorScheme of ['light','dark']){
    await page.setViewportSize({width,height:844});await page.emulateMedia({colorScheme});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    if(process.env.REVIEW_SCREENSHOT_DIR){
      await mkdir(process.env.REVIEW_SCREENSHOT_DIR,{recursive:true});
      await page.screenshot({path:join(process.env.REVIEW_SCREENSHOT_DIR,`home-${width}-${colorScheme}.png`),fullPage:true});
    }
  }
  await context.route('**/review/library.json',r=>r.fulfill({json:manifest}));
  await context.route('**/review/fixture.json',r=>r.fulfill({json:review}));
  await context.route('**/fixture.html*',r=>r.fulfill({contentType:'text/html; charset=utf-8',body:'<!doctype html><meta charset="utf-8"><h1 id="one">テスト教材：短い</h1>'}));
  await page.reload();await page.getByRole('button',{name:/5分だけ復習/}).click();
  await page.getByRole('heading',{name:'テスト問題 1'}).waitFor();
  await page.getByRole('button',{name:'☆ 重点にする'}).click();
  await page.getByRole('button',{name:'○ 正しい',exact:true}).click();
  await page.reload();await page.getByRole('button',{name:'中断した復習を再開'}).click();
  await page.getByRole('heading',{name:'答え',exact:true}).waitFor();
  await page.getByRole('button',{name:'教材で確認する'}).click();
  await page.getByRole('heading',{name:'テスト教材：短い'}).waitFor();
  await page.goBack();await page.getByRole('heading',{name:'テスト問題 1'}).waitFor();
  // Inject an IndexedDB write failure: no event or progression may be committed.
  await page.evaluate(()=>{window.savedAdd=IDBObjectStore.prototype.add;IDBObjectStore.prototype.add=function(){throw Error('injected storage failure');};});
  await page.getByRole('button',{name:'覚えていた',exact:true}).click();
  await page.getByRole('status').filter({hasText:'injected storage failure'}).waitFor();
  assert.equal(await page.evaluate(async()=>{const db=await import('./db.mjs');return(await db.snapshot()).events.length;}),0);
  await page.evaluate(()=>{IDBObjectStore.prototype.add=window.savedAdd;});
  await page.getByRole('button',{name:'覚えていた',exact:true}).click();
  await page.getByRole('heading',{name:'テスト問題 2'}).waitFor();
  await page.getByRole('button',{name:'選択肢 a',exact:true}).click();
  // Two tabs race on the same item. Only one transaction may succeed.
  const other=await context.newPage();await other.goto(url);
  const savedSession=await page.evaluate(async()=>{const db=await import('./db.mjs');return(await db.snapshot()).session;});
  const race=await Promise.all([page,other].map(p=>p.evaluate(async session=>{
    const db=await import('./db.mjs');try{await db.rate(session,'perfect');return true;}catch{return false;}
  },savedSession)));
  assert.equal(race.filter(Boolean).length,1);await other.close();
  await page.reload();await page.getByRole('button',{name:'中断した復習を再開'}).click();
  await page.getByRole('heading',{name:'テスト問題 3'}).waitFor();
  await page.getByRole('textbox',{name:'あなたの回答'}).fill('短い');
  await page.reload();await page.getByRole('button',{name:'中断した復習を再開'}).click();
  assert.equal(await page.getByRole('textbox',{name:'あなたの回答'}).inputValue(),'短い');
  if(process.env.REVIEW_SCREENSHOT_DIR)await page.screenshot({path:join(process.env.REVIEW_SCREENSHOT_DIR,'question.png'),fullPage:true});
  await page.getByRole('button',{name:'答えを見る',exact:true}).click();
  await page.getByRole('button',{name:'微妙',exact:true}).click();
  await page.getByRole('heading',{name:'テスト問題 4'}).waitFor();
  await page.getByRole('button',{name:'答えを見る',exact:true}).click();
  await page.getByRole('button',{name:'忘れた',exact:true}).click();
  await page.getByRole('heading',{name:'テスト問題 5'}).waitFor();
  await page.getByRole('textbox',{name:'あなたの回答'}).fill('自分の言葉による回答');
  await page.getByRole('button',{name:'答えを見る',exact:true}).click();
  await page.getByRole('button',{name:'完璧',exact:true}).click();
  await page.getByRole('heading',{name:'おつかれさまでした。'}).waitFor();
  const backup=await page.evaluate(async()=>{const db=await import('./db.mjs');return db.backup();});
  assert.equal(backup.review_events.length,5);assert.ok(backup.question_state.some(s=>s.is_starred));
  await page.getByRole('button',{name:'設定',exact:true}).click();
  await page.locator('#import').setInputFiles({name:'backup.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(backup))});
  await page.getByRole('button',{name:'確認して復元する'}).click();
  await page.getByRole('status').filter({hasText:'追加 0 件、重複 5 件'}).waitFor();
  const restored=await page.evaluate(async backup=>{const db=await import('./db.mjs');return(await db.backup()).review_events;},backup);
  assert.equal(restored.length,5);
  const conflict=structuredClone(backup);conflict.review_events[0].session_id='conflicting';
  await page.locator('#import').setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(conflict))});
  await page.getByRole('status').filter({hasText:'異なる履歴'}).waitFor();
  await page.reload();await page.getByRole('button',{name:'履歴',exact:true}).click();
  assert.equal(await page.locator('.history-row').count(),5);
  assert.deepEqual(errors,[]);
  console.log('PASS: 5 formats, six viewport/theme combinations, resume, source/back, failed save, two-tab race, backup/import, conflict preservation, reload');
}catch(error){console.error('Browser failure context:',await page.locator('body').innerText());throw error;}
finally{await context.close();await browser.close();}
