/* Optional browser QA. URL must be a synthetic local fixture, never production. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require(process.argv[2]?path.resolve(process.argv[2]):'playwright');
const root=path.resolve('.');
const artifactDir=path.join(root,'.venv','chug-preview');
fs.mkdirSync(artifactDir,{recursive:true});
let browser;
(async()=>{
 const launch={headless:true,args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']};
 if(!fs.existsSync(chromium.executablePath()))launch.channel='msedge';
 browser=await chromium.launch(launch);
 const context=await browser.newContext({viewport:{width:390,height:844}});
 const page=await context.newPage();
 // Exercise the real component with a controlled server clock and hostile names.
 const html=fs.readFileSync('components/chug_duel/index.html','utf8');
 await page.setContent(html);
 const css=fs.readFileSync('assets/theme.css','utf8');
 const tokens=css.slice(css.indexOf(':root {'),css.indexOf('/* Base */'));
 const args={duel_id:'browser-test',state:'started',challenger:'<img src=x onerror=alert(1)>',opponent:'Bob',tokens,
   server_now:'2026-11-19T20:00:00Z',play_at:null};
 await page.evaluate(args=>{
   window.results=[];
   window.addEventListener('message',e=>{if(e.data?.type==='streamlit:setComponentValue')window.results.push(e.data.value);});
   window.postMessage({type:'streamlit:render',args},'*');
 },args);
 await page.locator('#challenger').click();await page.locator('#challenger').click();
 assert.equal(await page.evaluate(()=>window.results.length),0);
 await page.locator('#opponent').click();
 await page.waitForFunction(()=>window.results.length===1);
 assert.equal((await page.evaluate(()=>window.results[0])).phase,'ready');
 assert.equal(await page.locator('img').count(),0);
 args.play_at='2026-11-19T20:00:03Z';
 await page.evaluate(args=>window.postMessage({type:'streamlit:render',args},'*'),args);
 await page.waitForFunction(()=>document.querySelector('#status').textContent==='3');
 await page.locator('#opponent').click();
 assert.equal(await page.evaluate(()=>window.results.length),1); // early tap ignored
 // Polling must not restart or move the local countdown.
 await page.waitForFunction(()=>document.querySelector('#status').textContent==='2');
 await page.evaluate(args=>window.postMessage({type:'streamlit:render',args},'*'),args);
 assert.equal(await page.locator('#status').textContent(),'2');
 await page.waitForFunction(()=>document.querySelector('#status').textContent==='1');
 await page.waitForFunction(()=>document.querySelector('#status').textContent==='GO');
 assert.deepEqual(await page.locator('main').boundingBox(),{x:0,y:0,width:390,height:844});
 await page.screenshot({path:path.join(artifactDir,'board-mobile.png')});
 await page.evaluate(()=>{
   for(const id of ['opponent','challenger'])document.getElementById(id).dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,cancelable:true}));
 });
 await page.waitForFunction(()=>window.results.length===2);
 assert.equal((await page.evaluate(()=>window.results[1])).winner,'opponent');
 assert.equal(await page.evaluate(()=>window.results.filter(r=>r.phase==='result').length),1);
 args.state='completed';args.winner='opponent';
 await page.evaluate(args=>window.postMessage({type:'streamlit:render',args},'*'),args);
 await page.waitForFunction(()=>document.querySelector('#hint').textContent==='Result saved');
 assert.equal(await page.locator('#status').textContent(),'Bob wins');
 assert.equal(await page.evaluate(()=>window.results.filter(r=>r.phase==='result').length),1);
 args.duel_id='aborted-browser-test';args.state='aborted';args.winner=null;args.play_at=null;
 await page.evaluate(args=>window.postMessage({type:'streamlit:render',args},'*'),args);
 await page.waitForFunction(()=>document.querySelector('#status').textContent==='Ended without winner');
 assert.equal(await page.locator('button.winner').count(),0);
 args.duel_id='resumed-browser-test';args.state='started';args.play_at='2026-11-19T19:59:00Z';
 await page.evaluate(args=>window.postMessage({type:'streamlit:render',args},'*'),args);
 await page.waitForFunction(()=>document.querySelector('#status').textContent==='GO');
 await page.locator('#challenger').press('Enter');
 await page.waitForFunction(()=>window.results.some(r=>r.duel_id==='resumed-browser-test'&&r.winner==='challenger'));
 console.log('PASS: real board: full viewport, 3/2/1/GO without countdown reset, early taps ignored, first-tap lock, saved winner, escaped names.');

 if(process.env.CHUG_QA_URL){
   const url=new URL(process.env.CHUG_QA_URL);
   assert(['127.0.0.1','localhost'].includes(url.hostname),'Only synthetic local QA is allowed');
   const host=await context.newPage();
   const guestContext=await browser.newContext({viewport:{width:390,height:844}});
   const guest=await guestContext.newPage();
   await host.goto(url.href);
   await host.getByRole('button',{name:'Send challenge',exact:true}).waitFor({timeout:30000});
   const nav=host.locator('.st-key-wego_bottom_nav');
   const buttons=await nav.getByRole('button').allTextContents();
   assert.equal(buttons.findIndex(x=>x.includes('Minigames')),buttons.findIndex(x=>x.includes('Check in'))+1);
   assert(await host.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await host.screenshot({path:path.join(artifactDir,'lobby-mobile.png'),fullPage:true});
   await host.getByRole('button',{name:'Send challenge',exact:true}).click();
   url.searchParams.set('role','guest');await guest.goto(url.href);
   await guest.getByRole('button',{name:'Accept duel',exact:true}).click();
   const camera=host.frameLocator('iframe[title="camera_capture.drink_camera"]');
   await camera.getByRole('button',{name:'Take photo',exact:true}).click({timeout:30000});
   await host.getByRole('button',{name:'Save shared check-in & open duel',exact:true}).waitFor({timeout:30000});
   await host.getByRole('button',{name:'Save shared check-in & open duel',exact:true}).click();
   const boardFrame=host.locator('iframe[title="chug_duel_component.chug_duel"]');
   const board=host.frameLocator('iframe[title="chug_duel_component.chug_duel"]');
   await boardFrame.waitFor();
   await host.evaluate(()=>{window.chugOriginalFrame=document.querySelector('iframe[title="chug_duel_component.chug_duel"]');});
   const assertFocused=async()=>{
     const box=await boardFrame.boundingBox();
     const viewport=host.viewportSize();
     assert.deepEqual(box,{x:0,y:0,width:viewport.width,height:viewport.height});
     assert.equal(await nav.isVisible(),false);
     assert(await host.evaluate(()=>window.chugOriginalFrame===document.querySelector('iframe[title="chug_duel_component.chug_duel"]')));
   };
   await assertFocused();
   await board.getByRole('button',{name:'Alice ready or finish',exact:true}).click();
   await board.getByRole('button',{name:'Bob ready or finish',exact:true}).click();
   for(const value of ['3','2','1']){
     await board.getByRole('status').filter({hasText:new RegExp('^'+value+'$')}).waitFor({timeout:15000});
     await assertFocused();
   }
   await board.getByRole('status').filter({hasText:/^GO$/}).waitFor({timeout:15000});
   await assertFocused();
   await host.mouse.move(100,400);await host.mouse.wheel(0,900);
   await assertFocused();
   assert.equal(await board.locator('body').evaluate(el=>el.scrollHeight<=innerHeight),true);
   await host.setViewportSize({width:844,height:390});
   await assertFocused();
   assert.equal(await board.getByRole('status').textContent(),'GO');
   await host.setViewportSize({width:390,height:844});
   await assertFocused();
   await host.screenshot({path:path.join(artifactDir,'duel-mobile.png'),fullPage:true});
   await board.getByRole('button',{name:'Alice ready or finish',exact:true}).click();
   await board.getByRole('status').filter({hasText:'Alice wins'}).waitFor({timeout:15000});
   await board.getByText('Result saved',{exact:true}).waitFor({timeout:15000});
   await assertFocused();
   await guest.getByText('Alice won',{exact:false}).waitFor({timeout:15000});
   await host.getByRole('button',{name:'Back to Minigames',exact:true}).click();
   await host.getByText('Alice won',{exact:false}).waitFor({timeout:15000});
   assert(await nav.isVisible());
   assert.equal(await host.locator('.st-key-chug_duel_stage').count(),0);
   await host.reload();await host.getByText('Alice won',{exact:false}).waitFor({timeout:15000});
   await host.setViewportSize({width:1440,height:1000});
   await host.screenshot({path:path.join(artifactDir,'result-desktop.png'),fullPage:true});
   if(process.env.CHUG_QA_REPLAYS==='1'){
     assert.deepEqual(await host.locator('[data-testid="stMetricValue"]').allTextContents(),['Unlimited','Unlimited']);
     await host.getByRole('button',{name:'Send challenge',exact:true}).click();
     await guest.getByRole('button',{name:'Accept duel',exact:true}).click({timeout:15000});
     await camera.getByRole('button',{name:'Take photo',exact:true}).click({timeout:15000});
     await host.getByRole('button',{name:'Save shared check-in & open duel',exact:true}).click();
     await host.getByRole('button',{name:'End without winner',exact:true}).click();
     await host.getByRole('button',{name:'Back to Minigames',exact:true}).click();
     await host.getByRole('button',{name:'Send challenge',exact:true}).waitFor({timeout:15000});
     assert.deepEqual(await host.locator('[data-testid="stMetricValue"]').allTextContents(),['Unlimited','Unlimited']);
     await host.getByRole('button',{name:'Send challenge',exact:true}).click();
     await guest.getByRole('button',{name:'Decline',exact:true}).click({timeout:15000});
     await host.getByRole('button',{name:'Send challenge',exact:true}).waitFor({timeout:15000});
     console.log('PASS: QA lobby: same players can challenge and accept again after a completed game; abort also permits another replay; both indicators remain Unlimited.');
   }
   console.log('PASS: synthetic Streamlit app: actual camera capture, stable fullscreen iframe through Ready/countdown/GO/winner, blocked scrolling, hidden/restored navigation, result on both phones, refresh recovery.');
   await guestContext.close();
 }
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();});
