// Real Streamlit board and PostgreSQL, isolated synthetic user, no live credentials.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {spawn}=require('node:child_process'),{fixture}=require('./quiz_fixture.cjs');
const {chromium}=require(path.resolve(process.argv[2]));
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 let f,server,app,browser,log='';
 try{
  f=await fixture();
  for(const file of ['015_focus_test_replays.sql','018_focus_reaction_only.sql','019_focus_false_start_three_tries.sql','020_focus_wait_time.sql','021_focus_three_stage_flow.sql'])
   await f.exec(fs.readFileSync('migrations/'+file,'utf8').replaceAll('statement_timestamp()','(select at_time from test_clock)'));
  const l=await f.lobby(1,{test:true}),base=Date.parse(f.now()),start=Date.now();let queue=Promise.resolve();
  server=http.createServer((req,res)=>{
   let body='';req.on('data',d=>body+=d);req.on('end',()=>{queue=queue.then(async()=>{
    let result;try{
     const {name,parameters:p}=JSON.parse(body);await f.clock(new Date(base+Date.now()-start).toISOString());
     if(name==='fixture')result={sid:l.sid,lid:l.lid};
     else if(name==='focus_status')result=(await f.rpc('select focus_status($1,$2) data',[p.actor_player,p.target_season])).rows[0].data;
     else if(name==='start_focus_attempt')result=(await f.rpc('select start_focus_attempt($1,$2,$3) data',[p.actor_player,p.target_season,p.request_id])).rows[0].data;
     else if(name==='focus_attempt_action')result=(await f.rpc('select focus_attempt_action($1,$2,$3,$4,$5) data',[p.actor_player,p.target_attempt,p.expected_revision,p.selected_action,p.evidence])).rows[0].data;
     else throw Error('Invalid fixture route');
    }catch(error){result={error:error.message};}
    res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(result));
   });});
  });await new Promise(r=>server.listen(8773,'127.0.0.1',r));
  app=spawn(process.env.SCORING_PYTHON||'../Scripts/python.exe',['-m','streamlit','run','tests/fixtures/focus_browser_app.py','--server.address','127.0.0.1','--server.port','8774','--server.headless','true','--browser.gatherUsageStats','false'],{windowsHide:true,stdio:['ignore','pipe','pipe']});
  app.stdout.on('data',d=>log+=d);app.stderr.on('data',d=>log+=d);
  for(let i=0;i<100;i++){try{if((await fetch('http://127.0.0.1:8774/_stcore/health')).ok)break;}catch{}await delay(200);}
  const launch={headless:true};if(!fs.existsSync(chromium.executablePath()))launch.channel='msedge';
  browser=await chromium.launch(launch);const page=await browser.newPage({viewport:{width:390,height:844}});
  await page.goto('http://127.0.0.1:8774');
  await page.getByRole('button',{name:'Start',exact:true}).click();
  const board=page.frameLocator('iframe[title="focus_challenge_component.focus_challenge"]');
  await board.getByRole('button',{name:'Start reaction',exact:true}).click();
  // Tap 80ms after the actual visible signal, not a pre-guessed server timestamp.
  await board.locator('#react').evaluate(button=>new Promise(resolve=>{
   const timer=setInterval(()=>{if(button.textContent==='TAP NOW'){
    clearInterval(timer);setTimeout(()=>{button.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));resolve();},80);
   }},5);
  }));
  await board.getByRole('button',{name:'Start memory',exact:true}).waitFor();
  await page.reload();
  await board.getByRole('button',{name:'Start memory',exact:true}).waitFor();
  assert.equal(await page.getByTestId('stException').count(),0);
  await board.getByRole('button',{name:'Start memory',exact:true}).click();
  const row=(await f.q('select challenge,reaction_ms from focus_attempts where season_id=$1 order by started_at desc limit 1',[l.sid])).rows[0];
  assert.equal(row.reaction_ms.length,1);
  await board.locator('#grid button').first().waitFor({state:'visible'});
  const frame=page.frames().find(x=>x.url().includes('focus_challenge'));
  await frame.waitForFunction(()=>!document.querySelector('#grid button').disabled);
  for(const cell of row.challenge.memory){
   await board.getByRole('button',{name:'Memory cell '+(cell+1),exact:true}).click();
   await frame.waitForFunction(()=>document.querySelector('#saving').textContent==='');
  }
  await board.getByRole('button',{name:'Start precision',exact:true}).click();
  for(let i=0;i<12;i++){await board.locator('#target').click();await delay(150);}
  await board.getByText('Focus boost earned!',{exact:true}).waitFor();
  assert.equal(await page.getByTestId('stException').count(),0);
  assert.equal((await f.q("select count(*) n from focus_attempts where status='passed'")).rows[0].n,1);
  fs.mkdirSync('.venv/focus-browser-qa',{recursive:true});
  await page.screenshot({path:'.venv/focus-browser-qa/passed-mobile.png'});
  console.log('Focus browser passed: single fast reaction → memory-ready reload → seven memory answers → twelve precision taps → saved boost.');
 }catch(error){console.error(log.slice(-3000));throw error;}
 finally{if(browser)await browser.close();if(app)app.kill();if(server)await new Promise(r=>server.close(r));if(f)await f.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
