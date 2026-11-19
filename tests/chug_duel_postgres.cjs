/* Isolated PostgreSQL integration checks; optional PGlite 0.3.14. Never Supabase. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const {PGlite}=require(process.argv[2]?path.resolve(process.argv[2]):'@electric-sql/pglite');
const python=process.env.SCORING_PYTHON||'python';
const rules=JSON.parse(execFileSync(python,['-c','import json; from core.scoring_v1 import new_rules; print(json.dumps(new_rules()))'],{encoding:'utf8'}));
const uid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const statePath=path.resolve('.venv',`chug-db-test-${Date.now()}`);
assert(statePath.startsWith(path.resolve('.venv')+path.sep));
let pg,now='2026-11-19T20:00:00Z';
const q=(sql,args=[])=>pg.query(sql,args);
const clock=async value=>{now=value;await q('update test_clock set at_time=$1',[value]);};
const action=async(p,id,a,w=null)=>(await q('select * from chug_duel_action($1,$2,$3,$4)',[uid(p),uid(id),a,w?uid(w):null])).rows[0];
const invite=async(p,id,op,season,drink='beer',size='large')=>(await q('select * from invite_chug_duel($1,$2,$3,$4,$5,$6)',[uid(p),season,uid(id),uid(op),drink,size])).rows[0];
const start=async(p,id,location='outside',territory=null,photo=now)=>(await q('select * from start_chug_duel($1,$2,$3,$4,$5)',[uid(p),uid(id),territory,location,photo])).rows[0];
async function replay(season){
 const rows=(await q('select * from drink_entries where season_id=$1 order by event_order',[season])).rows;
 return JSON.parse(execFileSync(python,['-c',"import json,sys; from data.db import _row_to_drink_entry; from core.scoring_v1 import replay_season; s=replay_season([_row_to_drink_entry(r) for r in json.load(sys.stdin)]); print(json.dumps({'quarters':s.season_quarters,'owners':s.owners,'totals':s.territory_totals,'awards':s.awards}))"],{input:JSON.stringify(rows),encoding:'utf8'}));
}
(async()=>{
 pg=new PGlite(statePath);
 await pg.exec(`create role anon;create role authenticated;create role service_role bypassrls;
 create table test_clock(at_time timestamptz);insert into test_clock values('${now}');
 grant select on test_clock to service_role;
 grant usage on schema public to anon,authenticated,service_role;`);
 await pg.exec(fs.readFileSync('schema.sql','utf8').replace('create extension if not exists pgcrypto;',''));
 for(const file of ['004_server_game_tables.sql','005_scoring_v1.sql','009_single_competition_lobbies.sql','010_team_lobbies.sql','011_chug_duel.sql']){
  const sql=fs.readFileSync('migrations/'+file,'utf8').replaceAll('statement_timestamp()','(select at_time from test_clock)');
  await pg.exec(sql);
  if(file==='011_chug_duel.sql')await pg.exec(sql); // repeatable migration
 }
 for(let p=1;p<=6;p++)await q("insert into players(id,display_name,first_name,last_name,pin_hash) values($1,$2,'Test','Only','fixture')",[uid(p),'Player'+p]);
 for(const lid of [100,101]){
  await q('insert into lobbies(id,name,invite_code) values($1,$2,$3)',[uid(lid),'Duel test '+lid,'DUEL'+lid]);
  for(let p=1;p<=6;p++)await q('insert into lobby_memberships(id,player_id,lobby_id) values($1,$2,$3)',[uid(lid===100?10+p:20+p),uid(p),uid(lid)]);
 }
 await q("insert into territories values('shortys','Shortys','{}')");
 const newSeason=async lid=>(await q('select * from start_scoring_season($1,$2,$3,$4,$5)',[uid(1),uid(lid),'1_month','Europe/Lisbon',rules])).rows[0].id;
 const season=await newSeason(100),other=await newSeason(101);
 let d=await invite(1,301,12,season);
 assert.equal((await invite(1,301,12,season)).id,d.id);
 await assert.rejects(invite(1,302,13,season),/duel_pending/);
 await assert.rejects(invite(1,303,11,season),/permission_denied/);
 await assert.rejects(invite(1,303,22,season),/permission_denied/);
 await assert.rejects(action(1,301,'accept'),/permission_denied/);
 await assert.rejects(action(3,301,'accept'),/permission_denied/);
 await assert.rejects(start(1,301),/duel_unavailable/);
 assert.equal((await action(2,301,'accept')).status,'accepted');
 await assert.rejects(start(2,301),/permission_denied/);
 await assert.rejects(start(1,301,'unavailable'),/location_unavailable/);
 await assert.rejects(start(1,301,'outside',null,'2026-11-19T19:00:00Z'),/invalid_photo/);
 assert.equal((await q('select count(*)::int n from drink_entries')).rows[0].n,0);
 d=await start(1,301);
 assert.equal(d.status,'started');
 assert.equal((await q('select count(*)::int n from drink_entries')).rows[0].n,2);
 await start(1,301); // reply recovery: same rows
 assert.equal((await q('select count(*)::int n from drink_entries')).rows[0].n,2);
 assert.deepEqual((await replay(season)).quarters,{[uid(11)]:12,[uid(12)]:12});
 await assert.rejects(action(2,301,'finish',12),/permission_denied/);
 await assert.rejects(action(1,301,'finish',11),/duel_early/);
 d=await action(1,301,'arm');
 await assert.rejects(action(1,301,'finish',11),/duel_early/);
 await clock('2026-11-19T20:00:03Z');
 const simultaneousResults=await Promise.all([action(1,301,'finish',11),action(1,301,'finish',12)]);
 assert(simultaneousResults.every(result=>result.winner_id===uid(11)));
 assert.equal((await action(1,301,'finish',12)).winner_id,uid(11)); // immutable result
 assert.deepEqual((await replay(season)).quarters,{[uid(11)]:24,[uid(12)]:0});
 assert.equal((await q('select count(*)::int n from drink_entries where duel_transfer_to is not null')).rows[0].n,1);
 await assert.rejects(q('select * from correct_scoring_checkin($1,$2,$3,$4,$5)',[uid(1),d.challenger_entry_id,'wine','large',0]),/duel_entry_locked/);
 await assert.rejects(invite(1,304,13,season),/duel_limit/);
 // Opposite roles are independent. Cooldown rejection rolls back BOTH entries.
 await invite(2,305,11,season);await action(1,305,'accept');
 await assert.rejects(start(2,305),/cooldown/);
 assert.equal((await q('select count(*)::int n from drink_entries')).rows[0].n,2);
 await clock('2026-11-19T20:02:00Z');
 await start(2,305);await action(2,305,'abort');
 await assert.rejects(invite(3,306,11,season),/duel_limit/);
 assert.deepEqual((await replay(season)).quarters,{[uid(11)]:36,[uid(12)]:12});
 // Another lobby gives independent allowances.
 await invite(1,307,22,other);await action(2,307,'decline');
 await invite(1,308,22,other);await action(1,308,'cancel');
 await invite(1,321,22,other);await action(2,321,'accept');await start(1,321,'matched','shortys');
 const ownershipBefore=await replay(other);await action(1,321,'arm');
 await clock('2026-11-19T20:02:03Z');await action(1,321,'finish',22);
 const ownershipAfter=await replay(other);
 for(const field of ['owners','totals','awards'])assert.deepEqual(ownershipAfter[field],ownershipBefore[field]);
 assert.equal(ownershipAfter.quarters[uid(21)],ownershipBefore.quarters[uid(21)]-12);
 assert.equal(ownershipAfter.quarters[uid(22)],ownershipBefore.quarters[uid(22)]+12);
 // Only the SECOND participant is in cooldown: the first insert must roll back.
 await invite(5,322,16,season);await action(6,322,'accept');
 await q('select * from accept_scoring_checkin($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)',
   [uid(6),uid(323),uid(16),season,'beer','large',null,'outside',`${uid(100)}/${uid(323)}.jpg`,now]);
 const countBefore=(await q('select count(*)::int n from drink_entries')).rows[0].n;
 await assert.rejects(start(5,322),/cooldown/);
 assert.equal((await q('select count(*)::int n from drink_entries')).rows[0].n,countBefore);
 assert.equal((await q('select count(*)::int n from drink_entries where membership_id=$1',[uid(15)])).rows[0].n,0);
 // Pending/accepted expiry releases slots, starts consume them on timeout.
 await invite(3,309,14,season);
 await clock('2026-11-19T20:12:03Z');
 let listing=(await q('select * from list_chug_duels($1,$2)',[uid(3),season])).rows;
 assert.equal(listing.find(x=>x.id===uid(309)).status,'expired');
 await invite(3,310,14,season);await action(4,310,'accept');
 await clock('2026-11-19T20:22:03Z');
 await q('select * from list_chug_duels($1,$2)',[uid(3),season]);
 assert.equal((await q('select status from chug_duels where id=$1',[uid(310)])).rows[0].status,'cancelled');
 await invite(3,311,14,season);await action(4,311,'accept');await start(3,311,'matched','shortys');
 const before=await replay(season);
 await clock('2026-11-19T20:32:03Z');
 await action(3,311,'finish',13); // expired: no transfer
 assert.equal((await q('select status from chug_duels where id=$1',[uid(311)])).rows[0].status,'aborted');
 assert.deepEqual(await replay(season),before);
 await assert.rejects(invite(3,312,15,season),/duel_limit/);
 await clock('2026-11-20T00:01:00Z');
 await assert.rejects(invite(1,313,15,season),/duel_limit/);
 await clock('2026-11-20T06:00:00Z');
 assert.equal((await invite(1,314,12,season)).game_night.toISOString().slice(0,10),'2026-11-20');
 // Team members cannot challenge their teammates; transfers use team identities.
 await q("insert into lobbies(id,name,invite_code,game_mode,team_count,team_capacity,team_assignment) values($1,'Teams','TEAMDUEL','team',2,3,'manual')",[uid(102)]);
 const teams=(await q('select id from lobby_teams where lobby_id=$1 order by number',[uid(102)])).rows;
 for(let p=1;p<=3;p++)await q('insert into lobby_memberships(id,player_id,lobby_id,team_id) values($1,$2,$3,$4)',[uid(30+p),uid(p),uid(102),teams[p===2?1:0].id]);
 const teamSeason=await newSeason(102);
 await assert.rejects(invite(1,315,33,teamSeason),/duel_team/);
 await invite(1,316,32,teamSeason);await action(2,316,'accept');await start(1,316);await action(1,316,'arm');
 await clock('2026-11-20T06:00:03Z');await action(1,316,'finish',32);
 assert.deepEqual((await replay(teamSeason)).quarters,{[teams[0].id]:0,[teams[1].id]:24});
 // Competing accepts cannot reserve the same incoming role twice.
 await action(1,314,'cancel');
 await invite(1,317,15,season);await invite(2,318,15,season);
 const race=await Promise.allSettled([action(5,317,'accept'),action(5,318,'accept')]);
 assert.equal(race.filter(r=>r.status==='fulfilled').length,1);
 assert.match(String(race.find(r=>r.status==='rejected').reason),/duel_limit/);
 // Existing QA games must gain unlimited repeats when migration 012 is applied.
 await q('insert into lobbies(id,name,invite_code) values($1,$2,$3)',[uid(103),'QA games','QAGAMES']);
 for(let p=1;p<=3;p++)await q('insert into lobby_memberships(id,player_id,lobby_id) values($1,$2,$3)',[uid(40+p),uid(p),uid(103)]);
 const qaRules={...rules,test_mode:true,start_weekday:2,start_hour:8};
 const qa=(await q('select * from start_scoring_season($1,$2,$3,$4,$5)',[uid(1),uid(103),'1_month','Europe/Lisbon',qaRules])).rows[0].id;
 await invite(1,400,42,qa);await action(2,400,'accept');await start(1,400);await action(1,400,'arm');
 await clock('2026-11-20T06:00:06Z');await action(1,400,'finish',41);
 await assert.rejects(invite(1,401,42,qa),/duel_limit/);
 const normalBeforeQA=await replay(season);
 const qaMigration=fs.readFileSync('migrations/012_qa_minigames.sql','utf8');
 await pg.exec(qaMigration);await pg.exec(qaMigration);
 assert.equal((await q('select test_mode from chug_duels where id=$1',[uid(400)])).rows[0].test_mode,true);
 await q('update chug_duels set test_mode=true where id=$1',[uid(301)]);
 assert.equal((await q('select test_mode from chug_duels where id=$1',[uid(301)])).rows[0].test_mode,false);
 await assert.rejects(invite(1,402,12,season),/duel_limit/); // normal rules still enforced
 await assert.rejects(q(`insert into chug_duels(id,season_id,challenger_id,opponent_id,game_night,drink_type,size,status,created_at,expires_at,test_mode)
   values($1,$2,$3,$4,'2026-11-20','beer','large','accepted',$5,$5::timestamptz+interval '10 minutes',true)`,
   [uid(403),season,uid(11),uid(12),now]),/duplicate key/);
 await invite(1,404,42,qa);await action(2,404,'accept');
 await assert.rejects(start(1,404),/cooldown/); // QA replays retain ordinary check-in rules
 await clock('2026-11-20T06:02:03Z');await start(1,404);await action(1,404,'arm');
 await clock('2026-11-20T06:02:06Z');await action(1,404,'finish',42);
 await action(1,404,'finish',41); // retries cannot transfer points twice
 await invite(1,405,42,qa);await action(2,405,'accept');
 await clock('2026-11-20T06:04:03Z');await start(1,405);await action(1,405,'abort');
 await invite(1,406,42,qa);await action(2,406,'accept');
 await assert.rejects(invite(3,407,42,qa),/duel_busy/); // unlimited is sequential
 await action(1,406,'cancel');
 assert.equal((await invite(1,408,42,qa)).test_mode,true);
 await action(2,408,'decline');
 assert.deepEqual((await replay(qa)).quarters,{[uid(41)]:36,[uid(42)]:36});
 assert.equal((await q('select count(*)::int n from drink_entries where season_id=$1 and duel_transfer_to is not null',[qa])).rows[0].n,2);
 assert.deepEqual(await replay(season),normalBeforeQA);
 // Authoritative closing window and public-role denial.
 await clock('2026-11-22T18:00:00Z');
 await assert.rejects(invite(6,319,13,season),/scoring_closed/);
 await pg.exec('set role anon');
 await assert.rejects(q('select * from chug_duels'),/permission denied/);
 await assert.rejects(invite(1,320,12,season),/permission denied/);
 await pg.exec('reset role');
 const saved=await replay(season);
 const savedQA=await replay(qa);
 await pg.close();pg=new PGlite(statePath);
 assert.deepEqual(await replay(season),saved);
 assert.deepEqual(await replay(qa),savedQA);
 assert.equal((await action(1,301,'finish',12)).winner_id,uid(11));
 assert.deepEqual(await replay(season),saved);
 console.log('PASS: migration repeat; authorization; atomic start; cooldown rollback; countdown; 6/0 transfer once; unchanged territories/income; normal role limits; expiry/abort; midnight/06:00; competing accepts; 012 QA backfill, unlimited sequential repeats, server-derived test flag, normal-limit spoof rejection, unchanged normal standings; restart persistence.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(pg)await pg.close();});
