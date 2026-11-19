/* Optional PostgreSQL integration suite. See docs/SCORING_IMPLEMENTATION.md.
 * Uses an isolated PGlite database, never the team's Supabase credentials.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {PGlite} = require(process.argv[2] ? path.resolve(process.argv[2]) : '@electric-sql/pglite');
const python = process.env.SCORING_PYTHON || 'python';
const rules = JSON.parse(execFileSync(python, ['-c', 'import json; from core.scoring_v1 import new_rules; print(json.dumps(new_rules()))'], {encoding:'utf8'}));
const uid = n => `00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const statePath = path.resolve('.venv', `scoring-db-test-${Date.now()}`);
assert(statePath.startsWith(path.resolve('.venv') + path.sep));
let pg;
let currentTime = '2026-11-19T18:00:00Z';
const q = (sql,args=[]) => pg.query(sql,args);
async function clock(value) {
  currentTime = value;
  await q('update public.test_clock set at_time=$1',[value]);
}
async function accept(player, member, capture, drink, size, season, outside=false, lobby=100) {
  return (await q('select * from public.accept_scoring_checkin($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)',
    [uid(player),uid(capture),uid(member),season,drink,size,outside?null:'shortys',outside?'outside':'matched',
     `${uid(lobby)}/${uid(capture)}.jpg`,currentTime])).rows[0];
}
async function correct(player,capture,drink,size,revision=0) {
  return (await q('select * from public.correct_scoring_checkin($1,$2,$3,$4,$5)',
    [uid(player),uid(capture),drink,size,revision])).rows[0];
}
async function checkPythonReplay(season) {
  const rows=(await q('select * from public.drink_entries where season_id=$1 order by event_order',[season])).rows;
  const result=JSON.parse(execFileSync(python,['-c',
    "import json,sys; from data.db import _row_to_drink_entry; from core.scoring_v1 import replay_season; s=replay_season([_row_to_drink_entry(r) for r in json.load(sys.stdin)]); print(json.dumps({'awards':s.awards,'owners':s.owners,'quarters':s.season_quarters}))"],
    {input:JSON.stringify(rows),encoding:'utf8'}));
  for(const row of rows) assert.deepEqual([row.owner_membership_id,row.owner_bonus_quarters],result.awards[row.id]);
  return result;
}

(async()=>{
  pg=new PGlite(statePath);
  await pg.exec(`create role anon; create role authenticated; create role service_role bypassrls;
    create schema storage;
    create table storage.buckets(id text primary key,name text,public boolean);
    create table storage.objects(id text,bucket_id text);
    alter table storage.objects enable row level security;
    grant usage on schema public,storage to anon,authenticated,service_role;
    alter default privileges in schema public grant all on tables to anon,authenticated,service_role;
    create table public.test_clock(at_time timestamptz);
    insert into public.test_clock values('2026-11-19T18:00:00Z');`);
  await pg.exec(fs.readFileSync('schema.sql','utf8').replace('create extension if not exists pgcrypto;',''));
  await pg.exec(fs.readFileSync('migrations/004_server_game_tables.sql','utf8'));
  await pg.exec(fs.readFileSync('migrations/setup_checkin_photo_storage.sql','utf8'));
  await pg.exec(`insert into players(id,display_name,first_name,last_name,pin_hash,email) values
    ('${uid(1)}','Mia','M','A','fixture-only','mia@example.com'),
    ('${uid(2)}','Leo','L','B','fixture-only','leo@example.com'),
    ('${uid(3)}','Eva','E','C','fixture-only','eva@example.com');
    insert into lobbies(id,name,invite_code) values('${uid(100)}','Test lobby','TESTCODE');
    insert into lobby_memberships(id,player_id,lobby_id) values
    ('${uid(11)}','${uid(1)}','${uid(100)}'),('${uid(12)}','${uid(2)}','${uid(100)}'),('${uid(13)}','${uid(3)}','${uid(100)}');
    insert into territories(id,name,boundary) values('shortys','Shortys','{}');
    insert into seasons(id,lobby_id,starts_at,ends_at,length_choice) values
    ('${uid(200)}','${uid(100)}','2026-10-01','2026-10-31','1_month');
    insert into drink_entries(id,membership_id,season_id,drink_type,amount,photo_ref,territory_id,location_check_result,points_awarded,submitted_at)
    values('${uid(201)}','${uid(11)}','${uid(200)}','beer',1,'legacy','shortys','matched',99,'2026-10-01');`);
  // Clock substitution exists only in this isolated test. Production RPCs
  // accept no client timestamp for eligibility or correction deadlines.
  const migration=fs.readFileSync('migrations/005_scoring_v1.sql','utf8')
      .replaceAll('statement_timestamp()','(select at_time from public.test_clock)');
  await pg.exec(migration); await pg.exec(migration);
  assert.equal((await q('select points_awarded,rule_version from drink_entries where id=$1',[uid(201)])).rows[0].points_awarded,99);
  await pg.exec('set role service_role');
  const game=(await q('select * from public.start_scoring_season($1,$2,$3,$4,$5)',
    [uid(1),uid(100),'1_month','Europe/Lisbon',rules])).rows[0];
  const season=game.id;
  assert.equal(game.scoring_version,'v1');
  for(const [kind,sizes] of Object.entries(rules.points)) for(const [size,points] of Object.entries(sizes)) {
    assert.equal((await q('select public._scoring_points($1,$2,$3) as points',[rules,kind,size])).rows[0].points,points);
  }
  await assert.rejects(q('select * from public.start_scoring_season($1,$2,$3,$4,$5)',
    [uid(1),uid(100),'1_week','Europe/Lisbon',rules]),/season_still_active/);
  await assert.rejects(q("update seasons set timezone_name='Asia/Tokyo' where id=$1",[season]),/season_rules_frozen/);
  await assert.rejects(q("update seasons set scoring_rules='{}' where id=$1",[season]),/season_rules_frozen/);
  await accept(1,11,301,'beer','large',season);
  await clock('2026-11-19T18:01:00Z');
  await accept(2,12,302,'beer','medium',season);
  await clock('2026-11-19T18:02:59Z');
  await assert.rejects(accept(2,12,303,'wine','large',season),/cooldown/);
  await clock('2026-11-19T18:03:00Z');
  await accept(2,12,303,'wine','large',season);
  await clock('2026-11-19T18:03:15Z');
  await accept(3,13,304,'shot',null,season);
  let before=await checkPythonReplay(season);
  assert.deepEqual(before.quarters,{[uid(11)]:18,[uid(12)]:28,[uid(13)]:16});
  assert.equal(before.owners.shortys,uid(12));
  await clock('2026-11-19T18:04:00Z');
  await assert.rejects(correct(3,303,'wine','small'),/permission_denied/);
  const changed=await correct(2,303,'wine','small');
  assert.equal(changed.points_awarded,1); assert.equal(changed.revision,1);
  let after=await checkPythonReplay(season);
  assert.deepEqual(after.quarters,{[uid(11)]:19,[uid(12)]:12,[uid(13)]:16});
  assert.equal(after.owners.shortys,uid(13));
  assert.equal((await correct(2,303,'wine','small')).revision,1);
  assert.equal((await q('select count(*)::int as n from drink_entry_revisions')).rows[0].n,1);
  await assert.rejects(correct(2,303,'wine','medium'),/correction_conflict/);
  await clock('2026-11-19T18:04:59Z');
  await assert.rejects(accept(2,12,305,'shot',null,season),/cooldown/);
  await clock('2026-11-19T18:05:00Z');
  await assert.rejects(correct(2,303,'wine','medium',1),/correction_closed/);
  await accept(2,12,305,'mixed','small',season);
  await clock('2026-11-19T18:05:15Z');
  await accept(3,13,306,'beer','medium',season);
  await clock('2026-11-19T18:07:15Z');
  const own=await accept(3,13,307,'beer','small',season);
  assert.equal(own.owner_bonus_quarters,0); assert.equal(own.owner_membership_id,null);
  const outside=await accept(1,11,308,'shot',null,season,true);
  assert.equal(outside.territory_id,null); assert.equal(outside.owner_bonus_quarters,0);
  await checkPythonReplay(season);
  await clock('2026-11-22T17:59:30Z');
  await accept(1,11,309,'mixed','large',season);
  await clock('2026-11-22T18:00:00Z');
  await assert.rejects(accept(2,12,310,'shot',null,season),/scoring_closed/);
  await correct(1,309,'wine','large'); // existing correction can finish after weekly close
  const retry=await accept(1,11,309,'mixed','large',season);
  assert.equal(retry.points_awarded,4); // original ID recovers corrected result, never reawards
  await assert.rejects(accept(2,12,309,'mixed','large',season),/permission_denied/);
  await clock('2026-11-22T18:01:30Z');
  await assert.rejects(correct(1,309,'wine','small',1),/correction_closed/);
  const end=new Date(game.ends_at);
  await clock(new Date(end.getTime()-30000).toISOString());
  await accept(1,11,311,'beer','small',season);
  await clock(end.toISOString());
  await assert.rejects(correct(1,311,'wine','small'),/correction_closed/);
  await checkPythonReplay(season);
  const next=(await q('select * from public.start_scoring_season($1,$2,$3,$4,$5)',
    [uid(1),uid(100),'1_week','Europe/Lisbon',rules])).rows[0];
  assert.notEqual(next.id,season);
  assert.equal((await q('select count(*)::int as n from drink_entries where season_id=$1',[next.id])).rows[0].n,0);
  await pg.exec('reset role; set role anon');
  await assert.rejects(q('select * from public.correct_scoring_checkin($1,$2,$3,$4,$5)',[uid(1),uid(309),'beer','large',1]),/permission denied/);
  await assert.rejects(q('select * from public.drink_entry_revisions'),/permission denied/);
  await pg.exec('reset role');
  const saved=(await q('select * from drink_entries where id=$1',[uid(309)])).rows[0];
  await pg.close();
  pg=new PGlite(statePath);
  const reopened=(await q('select * from drink_entries where id=$1',[uid(309)])).rows[0];
  assert.deepEqual(reopened,saved);
  assert.equal((await q('select count(*)::int as n from drink_entry_revisions')).rows[0].n,2);
  assert.equal((await q('select points_awarded from drink_entries where id=$1',[uid(201)])).rows[0].points_awarded,99);
  // New QA seasons use an explicit frozen window. Existing seasons stay unchanged.
  await pg.exec(fs.readFileSync('migrations/009_single_competition_lobbies.sql','utf8'));
  await pg.exec(`insert into lobbies(id,name,invite_code) values('${uid(600)}','QA camera','QA600');
    insert into lobby_memberships(id,player_id,lobby_id) values('${uid(601)}','${uid(1)}','${uid(600)}');`);
  const qaRules = JSON.parse(execFileSync(python, ['-c',
    'import json; from core.scoring_v1 import new_rules; print(json.dumps(new_rules(test_mode=True)))'], {encoding:'utf8'}));
  await clock('2026-11-18T07:59:59Z');
  const qa = (await q('select * from public.start_scoring_season($1,$2,$3,$4,$5)',
    [uid(1),uid(600),'1_week','Europe/Lisbon',qaRules])).rows[0];
  await assert.rejects(accept(1,601,602,'beer','small',qa.id,false,600),/scoring_closed/);
  await clock('2026-11-18T08:00:00Z');
  await accept(1,601,602,'beer','small',qa.id,false,600);
  assert.equal((await q('select public._scoring_window_open($1,$2,$3) as open',
    [currentTime,'Europe/Lisbon',rules])).rows[0].open,false);
  await clock('2026-11-22T17:59:59Z');
  await accept(1,601,603,'beer','small',qa.id,false,600);
  await clock('2026-11-22T18:00:00Z');
  await assert.rejects(accept(1,601,604,'beer','small',qa.id,false,600),/scoring_closed/);
  await assert.rejects(q("update seasons set scoring_rules=$1 where id=$2",[rules,qa.id]),/season_rules_frozen/);
  await pg.close(); pg=new PGlite(statePath);
  const qaRestored = (await q('select scoring_rules from seasons where id=$1',[qa.id])).rows[0].scoring_rules;
  assert.deepEqual(qaRestored,qaRules);
  assert.deepEqual((await q('select scoring_rules from seasons where id=$1',[season])).rows[0].scoring_rules,rules);
  await pg.close();
  console.log('PostgreSQL checks passed: migration repeat, legacy preservation, exact table, frozen season, authoritative cutoff, shared cooldown, captures, corrections/replay, retry recovery, access control, new season reset, QA Wednesday/Sunday boundaries and rule persistence after restart.');
})().catch(async error=>{
  console.error(error.stack);
  if(pg)await pg.close().catch(()=>{});
  process.exitCode=1;
});
