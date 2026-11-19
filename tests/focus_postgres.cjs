const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {execFileSync}=require('node:child_process');
const {PGlite}=require(path.resolve(process.argv[2]||'.venv/photo-sql-check/package/dist/index.cjs'));
const rules=JSON.parse(execFileSync(process.env.SCORING_PYTHON||'.venv/Scripts/python.exe',['-c','import json; from core.scoring_v1 import new_rules; print(json.dumps(new_rules()))'],{encoding:'utf8'}));
const uid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const disk=path.resolve('.venv',`focus-db-test-${Date.now()}`);
let pg,now='2026-11-19T20:00:00Z';
const q=(sql,args=[])=>pg.query(sql,args);
const clock=async value=>{now=value;await q('update test_clock set at_time=$1',[value]);};
const rpc=async(sql,args=[])=>{await q('set role service_role');try{return await q(sql,args);}finally{await q('reset role');}};
const status=async(p,s)=>(await rpc('select focus_status($1,$2) data',[uid(p),s])).rows[0].data;
const start=async(p,s,id)=>(await rpc('select start_focus_attempt($1,$2,$3) data',[uid(p),s,uid(id)])).rows[0].data;
const act=async(p,a,action,evidence={})=>(await rpc('select focus_attempt_action($1,$2,$3,$4,$5) data',[uid(p),a.id,a.revision,action,evidence])).rows[0].data;
async function advance(ms){await clock(new Date(Date.parse(now)+ms).toISOString());}
async function add(p,mid,s,id,kind='beer',size='small',territory='shortys',lobby=100){
 return (await q('select * from accept_scoring_checkin($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)',
 [uid(p),uid(id),uid(mid),s,kind,size,territory,territory?'matched':'outside',`${uid(lobby)}/${uid(id)}.jpg`,now])).rows[0];
}
async function win(p,a){
 a=await act(p,a,'ready');
 for(let i=0;i<a.config.reaction_trials;i++){
  await clock(new Date(Date.parse(a.signal_at)+200).toISOString());
  a=await act(p,a,'reaction',{elapsed_ms:200});
 }
 assert.equal(a.phase,'memory_ready');
 a=await act(p,a,'ready');
 assert.equal(a.phase,'memory');
 const memory=[...a.memory];
 await clock(a.signal_at);
 for(const cell of memory){a=await act(p,a,'memory',{cell});}
 assert.equal(a.phase,'precision_ready');
 a=await act(p,a,'ready');await advance(4000);
 a=await act(p,a,'precision',{taps:Array.from({length:12},(_,i)=>(i+1)*300)});
 assert.equal(a.status,'passed');return a;
}
(async()=>{
 pg=new PGlite(disk);
 await pg.exec(`create role anon;create role authenticated;create role service_role bypassrls;
 create table test_clock(at_time timestamptz);insert into test_clock values('${now}');
 grant select on test_clock to service_role;grant usage on schema public to anon,authenticated,service_role;`);
 await pg.exec(fs.readFileSync('schema.sql','utf8').replace('create extension if not exists pgcrypto;',''));
 for(const file of ['004_server_game_tables.sql','005_scoring_v1.sql','009_single_competition_lobbies.sql','010_team_lobbies.sql','011_chug_duel.sql','012_qa_minigames.sql','013_checkin_photo_privacy.sql','014_focus_challenge.sql','015_focus_test_replays.sql','017_focus_reaction_flow.sql','018_focus_reaction_only.sql','019_focus_false_start_three_tries.sql','020_focus_wait_time.sql','021_focus_three_stage_flow.sql']){
  const sql=fs.readFileSync('migrations/'+file,'utf8').replaceAll('statement_timestamp()','(select at_time from test_clock)');
  await pg.exec(sql);if(file==='014_focus_challenge.sql'||file==='015_focus_test_replays.sql'||file==='017_focus_reaction_flow.sql')await pg.exec(sql);
 }
 // Deterministic entropy only in this isolated fixture; production uses UUID entropy.
 const source=(await q("select prosrc from pg_proc where proname='_focus_int'")).rows[0].prosrc;
 assert(source.includes('gen_random_uuid'));
 await pg.exec('create sequence focus_test_rng;grant usage on sequence focus_test_rng to service_role');
 await pg.exec(`create or replace function _focus_int(bound integer) returns integer language sql as $$
 select ((('x'||substr(md5(nextval('focus_test_rng')::text),1,8))::bit(32)::bigint)%bound)::integer $$;`);
 for(let p=1;p<=4;p++)await q("insert into players(id,display_name,first_name,last_name,pin_hash) values($1,$2,'Test','Only','fixture')",[uid(p),'Player'+p]);
 await q("insert into lobbies(id,name,invite_code) values($1,'Focus test','FOCUS')",[uid(100)]);
 for(let p=1;p<=3;p++)await q('insert into lobby_memberships(id,player_id,lobby_id) values($1,$2,$3)',[uid(10+p),uid(p),uid(100)]);
 await q("insert into territories values('shortys','Shortys','{}')");
 const sid=(await q('select * from start_scoring_season($1,$2,$3,$4,$5)',[uid(1),uid(100),'1_month','Europe/Lisbon',rules])).rows[0].id;
 await assert.rejects(start(4,sid,400),/permission_denied/);
 await assert.rejects(start(1,sid,400),/focus_locked/);
 // Owner is player 2 before player 1's later boosted drink.
 for(let i=0;i<4;i++){await advance(120000);await add(2,12,sid,200+i,'mixed','large');}
 for(let i=0;i<5;i++){await advance(120000);await add(1,11,sid,210+i);}
 assert.equal((await status(1,sid)).count,5);
 let a=await start(1,sid,400);
 assert.equal((await start(1,sid,401)).id,a.id,'Concurrent new IDs recover one running attempt');
 assert.equal(a.phase,'reaction_ready');assert.equal(a.memory,undefined);assert.equal(a.positions,undefined);
 await assert.rejects(act(2,a,'ready'),/permission_denied/);
 const first=(await q('select challenge from focus_attempts where id=$1',[a.id])).rows[0].challenge;
 a=await act(1,a,'fail');
 assert.equal((await status(1,sid)).threshold,7);
 await assert.rejects(start(1,sid,401),/focus_locked/);
 for(let i=0;i<2;i++){await advance(120000);await add(1,11,sid,220+i);}
 a=await start(1,sid,401);
 const next=(await q('select challenge from focus_attempts where id=$1',[a.id])).rows[0].challenge;
 assert.notDeepEqual(first,next,'Different persisted cryptographic challenges');
 // Stale and malformed actions never skip stages or reset their deadlines.
 await assert.rejects(act(1,a,'memory',{cell:0}),/focus_invalid_action/);
 const beforeRestart=JSON.stringify(a);
 const persisted=(await q('select challenge from focus_attempts where id=$1',[a.id])).rows[0].challenge;
 await pg.close();pg=new PGlite(disk);
 assert.equal(JSON.stringify((await status(1,sid)).attempt),beforeRestart);
 assert.deepEqual((await q('select challenge from focus_attempts where id=$1',[a.id])).rows[0].challenge,persisted);
 a=await win(1,a);
 const savedWin=JSON.stringify(a);
 assert.equal((await act(1,a,'fail')).status,'passed','A saved win cannot be replayed or replaced');
 await assert.rejects(start(1,sid,402),/focus_won/);
 await advance(120000);
 const boosted=await add(1,11,sid,230);
 assert.equal(Number(boosted.points_awarded),1.5);assert.equal(boosted.focus_attempt_id,a.id);
 assert.equal(Number(boosted.owner_bonus_quarters)/4,0.375,'Exact boosted owner income');
 const edited=(await q('select * from correct_scoring_checkin($1,$2,$3,$4,$5)',[uid(1),uid(230),'beer','large',0])).rows[0];
 assert.equal(Number(edited.points_awarded),4.5);assert.equal(Number(edited.owner_bonus_quarters)/4,1.125);
 // Same result after an app-side retry; no second correction or multiplier compounding.
 assert.equal(Number((await q('select * from correct_scoring_checkin($1,$2,$3,$4,$5)',[uid(1),uid(230),'beer','large',0])).rows[0].points_awarded),4.5);
 await advance(120000);
 await q('select * from invite_chug_duel($1,$2,$3,$4,$5,$6)',[uid(1),sid,uid(500),uid(13),'beer','small']);
 await q('select * from chug_duel_action($1,$2,$3,$4)',[uid(3),uid(500),'accept',null]);
 await q('select * from start_chug_duel($1,$2,$3,$4,$5)',[uid(1),uid(500),null,'outside',now]);
 const duelEntries=(await q('select * from drink_entries where duel_id=$1',[uid(500)])).rows;
 assert.equal(duelEntries.length,2);assert(duelEntries.every(x=>Number(x.points_awarded)===1&&x.focus_attempt_id===null));
 await q('select * from chug_duel_action($1,$2,$3,$4)',[uid(1),uid(500),'abort',null]);
 assert.equal((await status(1,sid)).count,9,'Shared duel entry counts once for its owner');

 // Historical replay retains the multiplier even long after its boost expires.
 await clock(a.boost_ends_at);
 const normal=await add(1,11,sid,231);
 assert.equal(Number(normal.points_awarded),1);assert.equal(normal.focus_attempt_id,null);
 assert.equal(Number((await q('select points_awarded from drink_entries where id=$1',[uid(230)])).rows[0].points_awarded),4.5);
 // A new evening clears counts/allowances, not a still-running one-hour effect.
 await clock('2026-11-20T05:30:00Z');
 for(let n=0;n<5;n++){await advance(120000);await add(3,13,sid,600+n);}
 let late=await start(3,sid,610);late=await win(3,late);
 const lateEnd=late.boost_ends_at;
 await clock('2026-11-20T06:00:00Z');
 assert.equal((await status(3,sid)).count,0);assert.equal((await status(3,sid)).won,false);
 assert.equal((await status(3,sid)).boost_ends_at,lateEnd);
 assert.equal(Number((await add(3,13,sid,611)).points_awarded),1.5);
 // Exact threshold/reset, timeout consumption, stale resume and failed false start.
 for(let n=0;n<5;n++){await advance(120000);await add(2,12,sid,620+n);}
 let timed=await start(2,sid,630);await clock(timed.deadline);await advance(2001);
 assert.equal((await status(2,sid)).attempt.status,'failed');
 assert.equal((await status(2,sid)).threshold,7);
 await assert.rejects(start(2,sid,631),/focus_locked/);
 for(let n=0;n<2;n++){await advance(120000);await add(2,12,sid,640+n);}
 timed=await start(2,sid,631);timed=await act(2,timed,'ready');
 await assert.rejects(act(2,timed,'reaction',{elapsed_ms:100}),/focus_invalid_action/);
 timed=await act(2,timed,'fail');assert.equal((await status(2,sid)).threshold,9);
 // Team-lobby data uses the same personal five-entry gate and personal boost.
 await q("insert into lobbies(id,name,invite_code,game_mode,team_count,team_capacity,team_assignment) values($1,'Focus teams','FOCUSTEAM','team',2,3,'manual')",[uid(102)]);
 const teams=(await q('select id from lobby_teams where lobby_id=$1 order by number',[uid(102)])).rows;
 for(let p=1;p<=3;p++)await q('insert into lobby_memberships(id,player_id,lobby_id,team_id) values($1,$2,$3,$4)',[uid(30+p),uid(p),uid(102),teams[p===2?1:0].id]);
 const teamSid=(await q('select * from start_scoring_season($1,$2,$3,$4,$5)',[uid(1),uid(102),'1_month','Europe/Lisbon',rules])).rows[0].id;
 async function teamAdd(p,id){return (await q('select * from accept_scoring_checkin($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)',
 [uid(p),uid(id),uid(30+p),teamSid,'beer','small','shortys','matched',`${uid(102)}/${uid(id)}.jpg`,now])).rows[0];}
 for(let n=0;n<5;n++){await advance(120000);await teamAdd(1,700+n);}
 assert.equal((await status(3,teamSid)).count,0,'A teammate cannot borrow another member’s entries');
 let ta=await win(1,await start(1,teamSid,710));await advance(120000);
 assert.equal(Number((await teamAdd(1,711)).points_awarded),1.5);
 assert.equal(Number((await teamAdd(3,712)).points_awarded),1,'Teammate ordinary award stays unboosted');
 assert.equal((await teamAdd(2,713)).owner_team_id,teams[0].id);
 // Frozen older snapshots remain disabled; neither migration nor enabling new rules changes them.
 const oldRules={...rules};delete oldRules.focus_challenge;
 await q("insert into lobbies(id,name,invite_code) values($1,'Old','OLD')",[uid(103)]);
 await q('insert into lobby_memberships(id,player_id,lobby_id) values($1,$2,$3)',[uid(41),uid(1),uid(103)]);
 const oldSid=(await q('select * from start_scoring_season($1,$2,$3,$4,$5)',[uid(1),uid(103),'1_month','Europe/Lisbon',oldRules])).rows[0].id;
 await assert.rejects(status(1,oldSid),/focus_disabled/);
 // Explicit QA bypasses unlocks even on a pre-Focus snapshot. Names/strings cannot enable it.
 await q("insert into lobbies(id,name,invite_code) values($1,'Existing QA','QAFOCUS')",[uid(104)]);
 await q('insert into lobby_memberships(id,player_id,lobby_id) values($1,$2,$3)',[uid(51),uid(1),uid(104)]);
 const qaRules={...oldRules,test_mode:true,start_weekday:2,start_hour:8};
 const qaSid=(await q('select * from start_scoring_season($1,$2,$3,$4,$5)',[uid(1),uid(104),'1_month','Europe/Lisbon',qaRules])).rows[0].id;
 assert.equal((await status(1,qaSid)).count,0);assert.equal((await status(1,qaSid)).threshold,0);
 assert.equal((await status(1,qaSid)).unlimited,true);
 await assert.rejects(start(4,qaSid,900),/permission_denied/);
 let qa=await start(1,qaSid,900);
 assert.equal(qa.test_mode,true,'The result screen receives authoritative QA mode');
 assert.deepEqual(qa.config,rules.focus_challenge);
 assert.equal((await start(1,qaSid,901)).id,qa.id,'QA still permits only one running attempt');
 qa=await act(1,qa,'fail');
 qa=await win(1,await start(1,qaSid,901));
 const firstQaWin=qa;
 qa=await win(1,await start(1,qaSid,902));
 assert(Date.parse(qa.boost_ends_at)>Date.parse(firstQaWin.boost_ends_at),'New QA wins refresh, rather than stack, the boost');
 assert.equal((await q("select count(*)::int n from focus_attempts where season_id=$1 and status='passed' and test_mode",[qaSid])).rows[0].n,2);
 const qaAward=await add(1,51,qaSid,903,'beer','small','shortys',104);
 assert.equal(Number(qaAward.points_awarded),1.5,'Multiple QA wins never compound the multiplier');
 assert.equal(qaAward.focus_attempt_id,qa.id,'Old QA snapshots also record the boost provenance');
 assert.deepEqual((await q('select scoring_rules from seasons where id=$1',[qaSid])).rows[0].scoring_rules,qaRules,'Frozen QA snapshot is unchanged');
 for(const ms of [221,220]){
  let edge=await start(1,qaSid,940+ms);edge=await act(1,edge,'ready');
  await clock(new Date(Date.parse(edge.signal_at)+ms).toISOString());
  edge=await act(1,edge,'reaction',{elapsed_ms:ms});
  assert.equal(edge.status,ms===221?'failed':'running');
  if(ms===220){
   assert.equal(edge.phase,'memory_ready');assert.equal(edge.memory,undefined);
   await assert.rejects(act(1,edge,'memory',{cell:0}),/focus_invalid_action/);
   edge=await act(1,edge,'ready');assert.equal(edge.phase,'memory');assert.equal(edge.memory.length,7);
   await act(1,edge,'fail');
  }
 }
 const latestQa=(await status(1,qaSid)).attempt.id;
 await pg.exec(fs.readFileSync('migrations/015_focus_test_replays.sql','utf8').replaceAll('statement_timestamp()','(select at_time from test_clock)'));
 await pg.exec(fs.readFileSync('migrations/017_focus_reaction_flow.sql','utf8').replaceAll('statement_timestamp()','(select at_time from test_clock)'));
 await pg.exec(fs.readFileSync('migrations/021_focus_three_stage_flow.sql','utf8').replaceAll('statement_timestamp()','(select at_time from test_clock)'));
 assert.equal((await status(1,qaSid)).unlimited,true,'Repeat migration preserves multiple QA wins');
 await pg.close();pg=new PGlite(disk);
 assert.equal((await status(1,qaSid)).attempt.id,latestQa,'QA replay state survives restart');
 for(const flag of [false,'true',1]){
  const n=flag===false?105:flag==='true'?106:107;
  await q("insert into lobbies(id,name,invite_code) values($1,'Test QA lobby',$2)",[uid(n),'FAKEQA'+n]);
  await q('insert into lobby_memberships(id,player_id,lobby_id) values($1,$2,$3)',[uid(n+1000),uid(1),uid(n)]);
  const s=(await q('select * from start_scoring_season($1,$2,$3,$4,$5)',[uid(1),uid(n),'1_month','Europe/Lisbon',{...rules,test_mode:flag}])).rows[0].id;
  assert.equal((await status(1,s)).unlimited,false);
  await assert.rejects(start(1,s,n+2000),/focus_locked/);
 }
 await clock('2026-11-22T18:00:00Z');await assert.rejects(start(2,sid,800),/scoring_closed/);
 let outsideQa=await win(1,await start(1,qaSid,904));
 assert(Date.parse(outsideQa.boost_ends_at)>Date.parse('2026-11-22T18:00:00Z'),'QA games run outside the weekly drink window');
 await assert.rejects(add(1,51,qaSid,905,'beer','small','shortys',104),/scoring_closed/,'Drink scoring still obeys its window');
 const qaEnd=(await q('select ends_at from seasons where id=$1',[qaSid])).rows[0].ends_at;
 await clock(qaEnd);await assert.rejects(start(1,qaSid,906),/scoring_closed/,'QA still requires an active season');
 // Existing installations may have already applied main's 018/019. Keep an
 // in-flight three-try game intact, then use the selected flow for its successor.
 await clock('2026-11-23T20:00:00Z');
 const install=async file=>pg.exec(fs.readFileSync('migrations/'+file,'utf8').replaceAll('statement_timestamp()','(select at_time from test_clock)'));
 await install('019_focus_false_start_three_tries.sql');
 await install('020_focus_wait_time.sql');
 let legacy=await act(1,await start(1,qaSid,1300),'ready');
 assert.equal(legacy.config.reaction_trials,3);
 assert.equal(legacy.config.reaction_wait_min_ms,3500);
 const legacyExpiry=legacy.expires_at;
 await install('021_focus_three_stage_flow.sql');
 legacy=(await status(1,qaSid)).attempt;
 assert.equal(legacy.config.reaction_only,true);
 assert.equal(legacy.expires_at,legacyExpiry,'Migration cannot extend a running deadline');
 legacy=await act(1,legacy,'false_start');assert.equal(legacy.step,0);
 for(let i=0;i<3;i++){
  await clock(new Date(Date.parse(legacy.signal_at)+200).toISOString());
  legacy=await act(1,legacy,'reaction',{elapsed_ms:200});
 }
 assert.equal(legacy.status,'passed','A previous reaction-only game keeps its old outcome');
 let successor=await act(1,await start(1,qaSid,1301),'ready');
 assert.equal(successor.config.reaction_trials,1);assert.equal(successor.config.reaction_median_ms,220);
 await clock(new Date(Date.parse(successor.signal_at)+200).toISOString());
 successor=await act(1,successor,'reaction',{elapsed_ms:200});
 assert.equal(successor.phase,'memory_ready');assert.equal(successor.status,'running');
 assert.equal(successor.boost_ends_at,null,'One fast reaction alone does not award the new boost');
 successor=await act(1,successor,'fail');
 await install('021_focus_three_stage_flow.sql');
 assert.equal((await status(1,qaSid)).attempt.id,successor.id,'Repeat installation preserves results');
 await q('set role anon');await assert.rejects(q('select * from focus_attempts'),/permission denied/);
 await assert.rejects(q('select focus_status($1,$2)',[uid(1),sid]),/permission denied/);await q('reset role');
 await pg.close();pg=new PGlite(disk);
 assert.equal((await q('select status from focus_attempts where id=$1',[uid(401)])).rows[0].status,'passed','Win and challenges survive database restart');
 assert.equal((await q('select challenge from focus_attempts where id=$1',[uid(401)])).rows[0].challenge.memory.length,7);
 console.log('Focus PostgreSQL checks passed: migration repeat, access, normal unlocks/one win, QA zero-upload replays on old snapshots, multiple wins without stacking, scoring windows, resume and database restart.');
 await pg.close();
})().catch(async e=>{console.error(e);if(pg)await pg.close();process.exitCode=1;});
