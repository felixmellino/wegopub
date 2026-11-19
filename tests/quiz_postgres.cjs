const assert=require('node:assert/strict'),path=require('node:path'),{fixture,uid}=require('./quiz_fixture.cjs');
(async()=>{
 const f=await fixture({modulePath:process.argv[2],disk:path.resolve('.venv','quiz-sql-'+Date.now())});
 const {q,rpc,clock,advance,lobby,invite,act,status,deck}=f;
 const l=await lobby(1);for(let p=1;p<=6;p++)await l.add(p,2000+p);
 assert.deepEqual((await q('select _quiz_rules() data')).rows[0].data,f.config,'Python/SQL rules agree');
 const balance=async p=>Number((await status(p,l.sid)).available_points);
 assert.equal(await balance(1),5);
 await assert.rejects(status(7,l.sid),/permission_denied/);
 for(const stake of [null,0,2,11])await assert.rejects(invite(1,l,3000,2,stake),/quiz_stake/);
 await assert.rejects(invite(1,l,3000,1),/permission_denied/);
 await assert.rejects(invite(1,l,3000,2,6),/quiz_funds/);
 for(const bad of [[],deck.slice(1),deck.map(x=>({...x,correct_index:8})),deck.map(x=>({...x,options:['x','x','y','z']}))])await assert.rejects(invite(1,l,3000,2,3,bad),/quiz_questions/);
 let d=await invite(1,l,3000);assert.equal(d.question,null);assert(!('questions' in d));
 assert.equal((await invite(1,l,3000)).id,d.id,'Invitation retry recovers original deck');
 await assert.rejects(invite(3,l,3000),/permission_denied/);
 await assert.rejects(act(3,d.id,'accept'),/permission_denied/);
 d=await act(2,d.id,'accept');assert.equal(await balance(1),2);assert.equal(await balance(2),2);
 assert.equal((await status(1,l.sid)).outgoing,false);
 await assert.rejects(invite(1,l,3001,3),/quiz_limit/);
 // Other games cannot start after a quiz reservation, and cancellation refunds.
 await rpc('select * from invite_chug_duel($1,$2,$3,$4,$5,$6)',[uid(1),l.sid,uid(3900),l.mid(3),'beer','small']);
 await assert.rejects(rpc('select * from chug_duel_action($1,$2,$3,$4)',[uid(3),uid(3900),'accept',null]),/quiz_busy/);
 d=await act(1,d.id,'cancel');assert.equal(d.status,'cancelled');assert.equal(await balance(1),5);
 assert.equal((await status(1,l.sid)).outgoing,true);
 await rpc('select * from chug_duel_action($1,$2,$3,$4)',[uid(1),uid(3900),'cancel',null]);
 // Reservation also prevents a correction from lowering available funds.
 d=await invite(1,l,3001,2,5);d=await act(2,d.id,'accept');
 await assert.rejects(rpc('select * from correct_scoring_checkin($1,$2,$3,$4,$5)',[uid(1),uid(2001),'beer','small',0]),/quiz_reserved_points/);
 assert.equal(Number((await q('select points_awarded from drink_entries where id=$1',[uid(2001)])).rows[0].points_awarded),5);
 d=await act(1,d.id,'ready');assert.equal(d.status,'accepted');
 d=await act(2,d.id,'ready');assert.equal(d.status,'playing');
 await assert.rejects(act(1,d.id,'answer',0,deck[0].correct_index),/quiz_early/);
 assert(!JSON.stringify(d.question).includes('correct_index'));assert(!JSON.stringify(d).includes(deck[1].question));
 const saved=JSON.stringify((await status(1,l.sid)).duels[0]);await f.reopen();
 assert.equal(JSON.stringify((await status(1,l.sid)).duels[0]),saved,'Restart preserves deck, stakes and timers');
 await clock(d.round_starts_at);await advance(100);
 d=await act(1,d.id,'answer',0,deck[0].correct_index);assert.equal(d.answered,true);assert.equal(d.round_results.length,0);
 await assert.rejects(act(1,d.id,'answer',0,(deck[0].correct_index+1)%4),/quiz_answer_locked/);
 await advance(100);d=await act(2,d.id,'answer',0,deck[0].correct_index);assert.equal(d.status,'between');assert.equal(d.challenger_score,1);
 d=(await status(1,l.sid)).duels[0];await clock(d.next_round_at);d=(await status(1,l.sid)).duels[0];
 assert.equal(d.round_no,1);assert.equal(d.question.question,deck[1].question);
 await act(1,d.id,'answer',0,deck[0].correct_index);assert.equal((await q('select count(*) n from quiz_answers where round_no=1')).rows[0].n,0,'Stale round answer ignored');
 await clock(d.round_starts_at);await advance(100);await act(2,d.id,'answer',1,(deck[1].correct_index+1)%4);
 await advance(50);d=await act(1,d.id,'answer',1,deck[1].correct_index);
 assert.equal(d.status,'completed');assert.equal(d.challenger_score,2);assert.equal(d.winner_id,l.mid(1));
 assert.equal(await balance(1),10);assert.equal(await balance(2),0);
 await act(2,d.id,'forfeit');await act(1,d.id,'answer',1,deck[1].correct_index);
 assert.equal((await q('select count(*) n from quiz_transfers')).rows[0].n,1,'Terminal retries transfer once');
 assert.equal((await status(1,l.sid)).outgoing,false);assert.equal((await status(2,l.sid)).incoming,false);
 await assert.rejects(rpc('select * from correct_scoring_checkin($1,$2,$3,$4,$5)',[uid(2),uid(2002),'beer','small',0]),/quiz_reserved_points/);
 // Each role has its own allowance; normal third-round higher score wins.
 d=await invite(3,l,3010,1,3);await act(1,d.id,'accept');await act(1,d.id,'ready');d=await act(3,d.id,'ready');
 for(let round=0;round<3;round++){
  await clock(d.round_starts_at);await advance(100);await act(3,d.id,'answer',round,round===0?deck[round].correct_index:(deck[round].correct_index+1)%4);
  await advance(100);d=await act(1,d.id,'answer',round,(deck[round].correct_index+1)%4);
  if(d.status==='between'){await clock(d.next_round_at);d=(await status(3,l.sid)).duels.find(x=>x.id===d.id);}
 }
 assert.equal(d.status,'completed');assert.equal(d.challenger_score,1);assert.equal(d.opponent_score,0);
 // No answers on either device => six timeouts => draw; clocks never restart.
 d=await invite(4,l,3020,5);await act(5,d.id,'accept');await act(4,d.id,'ready');d=await act(5,d.id,'ready');
 await advance(200000);d=(await status(4,l.sid)).duels.find(x=>x.id===d.id);
 assert.equal(d.status,'draw');assert.equal(d.round_results.length,6);assert.equal(Number((await status(4,l.sid)).available_points),5);
 // Decider: tie at 1:1, then faster correct wins the first additional question.
 await clock('2026-11-20T06:00:00Z');
 assert.equal((await status(1,l.sid)).outgoing,true);assert.equal((await status(2,l.sid)).incoming,true);
 d=await invite(4,l,3021,5);await act(5,d.id,'accept');await act(4,d.id,'ready');d=await act(5,d.id,'ready');
 for(let round=0;round<4;round++){
  await clock(d.round_starts_at);await advance(100);
  await act(4,d.id,'answer',round,round===0||round===3?deck[round].correct_index:(deck[round].correct_index+1)%4);
  await advance(100);d=await act(5,d.id,'answer',round,round===1||round===3?deck[round].correct_index:(deck[round].correct_index+1)%4);
  if(d.status==='between'){await clock(d.next_round_at);d=(await status(4,l.sid)).duels.find(x=>x.id===d.id);}
 }
 assert.equal(d.status,'completed');assert.equal(d.round_results.length,4);assert.equal(d.winner_id,l.mid(4));
 // Accepted but never started expires without consuming a role. Explicit quit does consume it.
 d=await invite(6,l,3030,3);await act(3,d.id,'accept');await advance(600001);
 assert.equal((await status(6,l.sid)).duels[0].status,'expired');assert.equal((await status(6,l.sid)).outgoing,true);
 d=await invite(6,l,3031,3);await act(3,d.id,'accept');await act(6,d.id,'ready');d=await act(3,d.id,'ready');
 d=await act(6,d.id,'forfeit');assert.equal(d.status,'forfeited');assert.equal(d.winner_id,l.mid(3));
 assert.equal((await status(6,l.sid)).outgoing,false);
 // Team purse: two teammates cannot reserve the same team's points twice.
 const t=await lobby(2,{team:true,test:true});await t.add(1,4001);await t.add(2,4002);
 await assert.rejects(invite(1,t,4100,3),/quiz_team/);
 let td=await invite(1,t,4100,2);await act(2,td.id,'accept');
 assert.equal(Number((await status(3,t.sid)).available_points),2);
 await assert.rejects(invite(3,t,4101,4),/quiz_funds/);
 await assert.rejects(q('update lobby_memberships set team_id=$1 where id=$2',[t.teams[1],t.mid(1)]),/team_locked/);
 await act(1,td.id,'ready');await act(2,td.id,'ready');td=await act(1,td.id,'forfeit');
 const transfer=(await q('select * from quiz_transfers where id=$1',[td.id])).rows[0];assert.equal(transfer.source_id,t.teams[0]);assert.equal(transfer.target_id,t.teams[1]);
 assert.equal(Number((await status(3,t.sid)).available_points),2);assert.equal(Number((await status(4,t.sid)).available_points),8);
 await advance(120000);await t.add(3,4003);
 td=await invite(1,t,4101,2);await act(2,td.id,'accept');await act(1,td.id,'cancel');
 td=await invite(1,t,4102,2);await act(2,td.id,'accept');await act(1,td.id,'ready');await act(2,td.id,'ready');await act(2,td.id,'forfeit');
 assert.equal((await status(1,t.sid)).outgoing,true,'QA can repeat used roles');
 // Exact timing ties score no round point; a hard reset does not shorten a question.
 await clock('2026-11-21T05:59:58Z');td=await invite(1,t,4103,2);await act(2,td.id,'accept');await act(1,td.id,'ready');td=await act(2,td.id,'ready');
 await clock('2026-11-21T06:00:00Z');td=(await status(1,t.sid)).duels.find(x=>x.id===td.id);
 assert.equal(td.status,'draw');assert.equal(td.round_results.length,0);
 const tied=await invite(3,t,4110,4);await act(4,tied.id,'accept');await act(3,tied.id,'ready');td=await act(4,tied.id,'ready');
 await clock(td.round_starts_at);await act(3,td.id,'answer',0,deck[0].correct_index);td=await act(4,td.id,'answer',0,deck[0].correct_index);
 assert.equal(td.challenger_score,0);assert.equal(td.opponent_score,0);await act(3,td.id,'forfeit');
 const fresh=await lobby(3,{team:true,test:true});await fresh.add(1,4501);await fresh.add(2,4502);
 const teamHold=await invite(3,fresh,4510,4);await act(4,teamHold.id,'accept');
 await assert.rejects(q('update lobby_memberships set team_id=$1 where id=$2',[fresh.teams[1],fresh.mid(3)]),/quiz_busy/);
 await act(3,teamHold.id,'cancel');
 // A correction may be the first request after a short, rollover-capped hold.
 await clock('2026-11-22T05:59:45Z');
 const boundary=await lobby(4,{test:true});await boundary.add(1,4601);await boundary.add(2,4602);
 const hold=await invite(1,boundary,4610,2,5);await act(2,hold.id,'accept');
 await clock('2026-11-22T06:00:00Z');
 const correction=(await rpc('select * from correct_scoring_checkin($1,$2,$3,$4,$5)',
  [uid(1),uid(4601),'beer','small',0])).rows[0];
 assert.equal(Number(correction.points_awarded),1);
 assert.equal((await status(1,boundary.sid)).duels[0].status,'expired');
 // The Python standings replay agrees with SQL balances for both account types.
 const {execFileSync}=require('node:child_process');
 for(const season of [l,t]){
  const entries=(await q('select * from drink_entries where season_id=$1',[season.sid])).rows;
  const transfers=(await q('select * from quiz_transfers where season_id=$1',[season.sid])).rows;
  const script="import json,sys; from types import SimpleNamespace; from data.db import _row_to_drink_entry; from core.scoring_v1 import replay_season; d=json.load(sys.stdin); print(json.dumps({k:float(v) for k,v in replay_season([_row_to_drink_entry(e) for e in d['entries']],[SimpleNamespace(**t) for t in d['transfers']]).season_rows()}))";
  const totals=JSON.parse(execFileSync(process.env.SCORING_PYTHON||'../Scripts/python.exe',['-c',script],{input:JSON.stringify({entries,transfers}),encoding:'utf8'}));
  for(const [account,points] of Object.entries(totals))assert.equal(Number((await q('select _quiz_balance($1,$2) n',[season.sid,account])).rows[0].n),points);
 }
 // All anonymous access and helper calls are denied.
 await q('set role anon');for(const sql of ['select * from quiz_duels','select * from quiz_answers','select * from quiz_transfers','select _quiz_rules()'])await assert.rejects(q(sql),/permission denied/);await q('reset role');
 console.log('Quiz PostgreSQL: permissions, timing, reservations, teams, retries, limits, deciders and restart passed');
 await f.close();
})().catch(e=>{console.error(e);process.exitCode=1;});
