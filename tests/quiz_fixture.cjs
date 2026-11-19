// Real PostgreSQL in an isolated directory; no network or production credentials.
const fs=require('node:fs'),path=require('node:path'),{execFileSync}=require('node:child_process');
const uid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
async function fixture({modulePath, disk, realtime=false}={}){
 const {PGlite}=require(path.resolve(modulePath||process.env.PGLITE_MODULE||'../photo-sql-check/package/dist/index.cjs'));
 const python=process.env.SCORING_PYTHON||'../Scripts/python.exe';
 const generated=JSON.parse(execFileSync(python,['-c',`import json; from core.scoring_v1 import new_rules; from core.quiz_duel import CONFIG; from data.quiz_questions import prepare_duel_deck; print(json.dumps(dict(rules=new_rules(),config=CONFIG,deck=prepare_duel_deck('test'))))`],{encoding:'utf8'}));
 let pg=new PGlite(disk),now='2026-11-19T20:00:00Z';
 const q=(sql,args=[])=>pg.query(sql,args),clock=async at=>{now=at;await q('update test_clock set at_time=$1',[at]);};
 const rpc=async(sql,args=[])=>{await q('set role service_role');try{return await q(sql,args);}finally{await q('reset role');}};
 await pg.exec(`create role anon;create role authenticated;create role service_role bypassrls;
 create table test_clock(at_time timestamptz);insert into test_clock values('${now}');
 grant select on test_clock to service_role;grant usage on schema public to anon,authenticated,service_role;`);
 await pg.exec(fs.readFileSync('schema.sql','utf8').replace('create extension if not exists pgcrypto;',''));
 for(const file of ['004_server_game_tables.sql','005_scoring_v1.sql','009_single_competition_lobbies.sql','010_team_lobbies.sql','011_chug_duel.sql','012_qa_minigames.sql','013_checkin_photo_privacy.sql','014_focus_challenge.sql','016_quiz_duel.sql']){
  let sql=fs.readFileSync('migrations/'+file,'utf8');if(!realtime)sql=sql.replaceAll('statement_timestamp()','(select at_time from test_clock)');
  await pg.exec(sql);if(file==='016_quiz_duel.sql')await pg.exec(sql);
 }
 for(let p=1;p<=8;p++)await q("insert into players(id,display_name,first_name,last_name,pin_hash) values($1,$2,'Test','Only','fixture')",[uid(p),'Player '+p]);
 await q("insert into territories values('quiz-fixture','Quiz fixture','{}')");
 async function lobby(n,{team=false,test=false}={}){
  const lid=uid(100+n);
  await q(`insert into lobbies(id,name,invite_code,game_mode,team_count,team_capacity,team_assignment)
  values($1,$2,$3,$4,$5,$6,$7)`,[lid,'Quiz test '+n,'QUIZ'+n,team?'team':'individual',team?2:null,team?4:null,team?'manual':null]);
  let teams=team?(await q('select id from lobby_teams where lobby_id=$1 order by number',[lid])).rows.map(t=>t.id):[];
  for(let p=1;p<=6;p++)await q('insert into lobby_memberships(id,player_id,lobby_id,team_id) values($1,$2,$3,$4)',[uid(1000+n*10+p),uid(p),lid,team?teams[(p-1)%2]:null]);
  const rules={...generated.rules,...(test?{test_mode:true}:{})};
  const sid=(await q('select * from start_scoring_season($1,$2,$3,$4,$5)',[uid(1),lid,'1_month','Europe/Lisbon',rules])).rows[0].id;
  const mid=p=>uid(1000+n*10+p);
  async function add(p,id,kind='mixed',size='large',territory=null){return (await rpc('select * from accept_scoring_checkin($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)',[uid(p),uid(id),mid(p),sid,kind,size,territory,territory?'matched':'outside',`${lid}/${uid(id)}.jpg`,now])).rows[0];}
  return {lid,sid,mid,teams,add};
 }
 return {q,rpc,exec:sql=>pg.exec(sql),clock,advance:async ms=>clock(new Date(Date.parse(now)+ms).toISOString()),lobby,deck:generated.deck,config:generated.config,
 status:async(p,sid)=>(await rpc('select quiz_status($1,$2) data',[uid(p),sid])).rows[0].data,
 invite:async(p,l,id,opponent=2,stake=3,deck=generated.deck)=>(await rpc('select invite_quiz_duel($1,$2,$3,$4,$5,$6) data',[uid(p),l.sid,uid(id),l.mid(opponent),stake,deck])).rows[0].data,
 act:async(p,id,action,round=null,choice=null)=>(await rpc('select quiz_action($1,$2,$3,$4,$5) data',[uid(p),typeof id==='number'?uid(id):id,action,round,choice])).rows[0].data,
 close:()=>pg.close(),reopen:async()=>{await pg.close();pg=new PGlite(disk);},now:()=>now};
}
module.exports={fixture,uid};
