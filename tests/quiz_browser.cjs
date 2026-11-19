// Two real Streamlit sessions + real transactional SQL; no live users/points.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {spawn}=require('node:child_process'),{fixture,uid}=require('./quiz_fixture.cjs');
const {chromium}=require(path.resolve(process.argv[2]));
const output=path.resolve('.venv','quiz-browser-qa');fs.mkdirSync(output,{recursive:true});
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 let f,server,app,browser,appOutput='';
 try{
  f=await fixture();const l=await f.lobby(1,{test:true});for(let p=1;p<=6;p++)await l.add(p,2000+p);
  const base=Date.parse(f.now()),started=Date.now();let queue=Promise.resolve();
  server=http.createServer((req,res)=>{
   let body='';req.on('data',data=>body+=data);req.on('end',()=>{
    queue=queue.then(async()=>{let result;try{
     const {name,parameters:p}=JSON.parse(body||'{}');await f.clock(new Date(base+Date.now()-started).toISOString());
     if(name==='fixture')result={sid:l.sid,lid:l.lid};
     else if(name==='quiz_status')result=(await f.rpc('select quiz_status($1,$2) data',[p.actor_player,p.target_season])).rows[0].data;
     else if(name==='invite_quiz_duel')result=(await f.rpc('select invite_quiz_duel($1,$2,$3,$4,$5,$6) data',[p.actor_player,p.target_season,p.invitation_id,p.opponent_member,p.selected_stake,p.private_questions])).rows[0].data;
     else if(name==='quiz_action')result=(await f.rpc('select quiz_action($1,$2,$3,$4,$5) data',[p.actor_player,p.target_duel,p.selected_action,p.expected_round,p.selected_choice])).rows[0].data;
     else throw Error('Unknown fixture route');
    }catch(error){result={error:error.message};}
    res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(result));});
   });
  });await new Promise(resolve=>server.listen(8771,'127.0.0.1',resolve));
  app=spawn(process.env.SCORING_PYTHON||'../Scripts/python.exe',['-m','streamlit','run','tests/fixtures/quiz_browser_app.py','--server.address','127.0.0.1','--server.port','8772','--server.headless','true','--browser.gatherUsageStats','false'],{windowsHide:true,stdio:['ignore','pipe','pipe']});
  app.stdout.on('data',d=>appOutput+=d);app.stderr.on('data',d=>appOutput+=d);
  for(let n=0;n<100;n++){try{if((await fetch('http://127.0.0.1:8772/_stcore/health')).ok)break;}catch{}await delay(200);}
  const launch={headless:true};if(!fs.existsSync(chromium.executablePath()))launch.channel='msedge';browser=await chromium.launch(launch);
  const a=await browser.newPage({viewport:{width:390,height:844}}),b=await browser.newPage({viewport:{width:1280,height:900}});
  await Promise.all([a.goto('http://127.0.0.1:8772/?player=1'),b.goto('http://127.0.0.1:8772/?player=2')]);
  await a.getByRole('button',{name:'Send quiz challenge',exact:true}).click();
  await b.getByRole('button',{name:'Accept quiz',exact:true}).click();
  const board=p=>p.frameLocator('iframe[title="quiz_duel_component.quiz_duel"]');
  const ab=board(a),bb=board(b);
  await Promise.all([ab.getByRole('button',{name:"I'm ready",exact:true}).waitFor(),bb.getByRole('button',{name:"I'm ready",exact:true}).waitFor()]);
  await ab.getByRole('button',{name:"I'm ready",exact:true}).click();
  await bb.getByRole('button',{name:"I'm ready",exact:true}).click();
  await ab.locator('#countdown').waitFor({state:'visible'});
  assert(await ab.locator('#count').textContent());
  for(let round=0;round<2;round++){
   await ab.locator('#question').waitFor({state:'visible'});await bb.locator('#question').waitFor({state:'visible'});
   assert.equal(await ab.locator('#prompt').textContent(),await bb.locator('#prompt').textContent());
   assert.deepEqual(await ab.locator('#options button').allTextContents(),await bb.locator('#options button').allTextContents());
   const row=(await f.q('select id,questions from quiz_duels where season_id=$1 order by created_at desc limit 1',[l.sid])).rows[0];
   const correct=row.questions[round].correct_index;
   if(round===0){
    await a.screenshot({path:path.join(output,'question-mobile.png')});
    assert(await a.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    const y=await a.evaluate(()=>scrollY);await a.mouse.wheel(0,500);await delay(100);assert.equal(await a.evaluate(()=>scrollY),y);
   }
   await ab.locator('#options button').nth(correct).click();
   await ab.getByText('Answer locked · Waiting for the other player.',{exact:true}).waitFor();
   if(round===0){
    await a.reload();await ab.locator('#question').waitFor({state:'visible'});
    assert(await ab.locator('#options button').nth(correct).isDisabled(),'Reload keeps first answer locked');
   }
   await bb.locator('#options button').nth((correct+1)%4).click();
   if(round===0){
    await ab.getByText('You won the round',{exact:true}).waitFor();
    await ab.locator('#countdown').waitFor({state:'visible'});
   }
  }
  await ab.getByText('You won!',{exact:true}).waitFor();await bb.getByText('Opponent wins',{exact:true}).waitFor();
  await a.screenshot({path:path.join(output,'result-mobile.png')});await b.screenshot({path:path.join(output,'result-desktop.png')});
  assert.equal((await f.q('select count(*) n from quiz_transfers')).rows[0].n,1);
  await ab.getByRole('button',{name:'Back to quizzes',exact:true}).click();
  await a.getByRole('button',{name:'Send quiz challenge',exact:true}).waitFor();
  assert.equal(await a.getByTestId('stException').count(),0);assert.equal(await b.getByTestId('stException').count(),0);
  console.log('Quiz browser: two players, identical questions, countdown, locked answer after reload, 2:0, single transfer, fixed mobile screen passed');
 }catch(error){console.error(appOutput.slice(-3500));throw error;}
 finally{if(browser)await browser.close();if(app)app.kill();if(server)await new Promise(r=>server.close(r));if(f)await f.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
