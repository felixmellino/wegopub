// Two independent Streamlit sessions backed by disposable PostgreSQL.
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const {chromium}=require(path.resolve(process.argv[2]));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.TIME_DUEL_BROWSER_CHANNEL?{channel:process.env.TIME_DUEL_BROWSER_CHANNEL}:{})});
 try{
  const a=await browser.newPage({viewport:{width:390,height:844}}),b=await browser.newPage({viewport:{width:390,height:844}});
  const errors=[];a.on('pageerror',e=>errors.push(e.message));b.on('pageerror',e=>errors.push(e.message));
  const base='http://127.0.0.1:'+(process.env.TIME_DUEL_APP_PORT||'8782');
  await Promise.all([a.goto(base+'/?player=1'),b.goto(base+'/?player=2')]);
  await a.getByRole('button',{name:'Open Time Duel',exact:true}).click();
  await a.getByRole('button',{name:'Send Time Duel challenge',exact:true}).click();
  await a.getByText('Pending Challenge invite',{exact:true}).waitFor();
  assert.equal(await a.getByRole('button',{name:'Send Time Duel challenge',exact:true}).isDisabled(),true);
  const badge=b.getByRole('img',{name:'1 pending Time Duel invite',exact:true});
  await badge.waitFor({state:'visible'});
  assert.equal(await badge.textContent(),'1 invite');
  assert.equal(await b.getByRole('button',{name:'Accept Time Duel',exact:true}).count(),0);
  await b.waitForFunction(()=>getComputedStyle(document.querySelector('.st-key-wego_nav_minigames button'),'::after').content.startsWith('"1"'));
  await b.getByRole('button',{name:'Open Time Duel',exact:true}).click();
  await b.getByRole('button',{name:'Accept Time Duel',exact:true}).click();
  const board=p=>p.frameLocator('iframe[title="time_duel_component.time_duel"]');
  const ab=board(a),bb=board(b);
  async function ready(){
   await ab.getByRole('button',{name:"I'm ready",exact:true}).click();
   assert(await ab.locator('#target').isHidden(),'Target hidden until both ready');
   await bb.getByRole('button',{name:"I'm ready",exact:true}).click();
   await ab.getByRole('button',{name:'Start',exact:true}).waitFor();await bb.getByRole('button',{name:'Start',exact:true}).waitFor();
   assert.equal(await ab.locator('#target').textContent(),await bb.locator('#target').textContent());
  }
  async function round(){
   await ready();
   const targetSeconds=parseInt(await ab.locator('#target').textContent(),10);
   await ab.getByRole('button',{name:'Start',exact:true}).click();
   assert.equal(await ab.locator('#target').textContent(),'?');
   await sleep(targetSeconds*1000-100);await ab.getByRole('button',{name:'Stop',exact:true}).click();
   assert.match(await ab.locator('#ownTime').textContent(),/\d\.\d{3}s/);
   await sleep(1800);assert.equal(await bb.locator('#otherTime').textContent(),'—','Opponent result hidden before own start');
   await bb.getByRole('button',{name:'Start',exact:true}).click();
   await bb.locator('#otherTime').filter({hasText:/\d\.\d{3}s/}).waitFor();
   await sleep(250);await bb.getByRole('button',{name:'Stop',exact:true}).click();
  }
  for(let n=0;n<3;n++)await round();
  await ab.locator('#result').waitFor({state:'visible'});await bb.locator('#result').waitFor({state:'visible'});
  assert.equal(await ab.locator('#resultTitle').textContent(),'You won!');
  assert.match(await ab.locator('#reward').textContent(),/×1.25/);
  fs.mkdirSync('output/previews',{recursive:true});await a.screenshot({path:'output/previews/time-duel-result.png'});
  await ab.getByRole('button',{name:'Back to Time Duel',exact:true}).click();
  await bb.getByRole('button',{name:'Back to Time Duel',exact:true}).click();
  await a.getByRole('button',{name:'Send Time Duel challenge',exact:true}).click();await b.getByRole('button',{name:'Accept Time Duel',exact:true}).click();
  await ready();await ab.getByRole('button',{name:'Start',exact:true}).click();await sleep(1400);await a.reload();
  await a.getByRole('button',{name:'Open Time Duel',exact:true}).click();
  await ab.locator('#ownTime').filter({hasText:'Lost'}).waitFor();
  await bb.getByRole('button',{name:'Start',exact:true}).click();await sleep(100);await bb.getByRole('button',{name:'Stop',exact:true}).click();
  await ab.getByRole('button',{name:"I'm ready",exact:true}).waitFor();
  assert.equal(errors.length,0,errors.join('\n'));
  assert.equal(await a.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'No horizontal overflow on phone');
  console.log('PASS: two-phone Streamlit invitations, hidden targets/timer, local results, disclosure gate, three rounds, reward and reload forfeiture');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
