"""Verify migration 016 using disposable PostgreSQL and synthetic accounts only.

Optional tools: pgserver==0.1.4, psycopg[binary]==3.2.13, fasteners==0.20.
Run with the same Python environment as scripts/verify_team_lobbies.py.
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import fasteners
import pgserver
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_lobby_scoring_compat import SCHEMA, NOW, account, expect_error
from data.db import _row_to_drink_entry
from core.scoring_v1 import replay_season, new_rules


def verify(server):
    with psycopg.connect(server.get_uri(), autocommit=True, row_factory=dict_row) as conn:
        for role in ('anon', 'authenticated', 'service_role'):
            conn.execute('create role ' + role)
        conn.execute(SCHEMA)
        conn.execute("create table test_clock(at_time timestamptz)")
        conn.execute("insert into test_clock values(%s)", (NOW,))
        conn.execute('create function test_now() returns timestamptz language sql as $$ select at_time from test_clock $$')
        for name in ('005_scoring_v1.sql', '009_single_competition_lobbies.sql', '010_team_lobbies.sql',
                     '011_chug_duel.sql', '012_qa_minigames.sql', '012_player_lobby_choices.sql',
                     '014_focus_challenge.sql', '015_focus_test_replays.sql', '016_leave_lobby.sql'):
            conn.execute((ROOT / 'migrations' / name).read_text().replace('statement_timestamp()', 'public.test_now()'))
        # The migration can be reapplied safely, including the active view.
        conn.execute((ROOT / 'migrations/016_leave_lobby.sql').read_text().replace('statement_timestamp()', 'public.test_now()'))
        actors = [account(conn) for _ in range(6)]
        def setup(team=False, qa=False):
            lid = uuid4()
            if team:
                conn.execute("insert into lobbies(id,name,invite_code,game_mode,team_count,team_capacity,team_assignment) values(%s,'Teams',%s,'team',2,1,'random')", (lid,str(lid)))
            else:
                conn.execute("insert into lobbies(id,name,invite_code) values(%s,'Leave test',%s)", (lid,str(lid)))
            mids = []
            for actor in actors[:2] if team else actors[:4]:
                mid = uuid4()
                conn.execute('insert into lobby_memberships(id,player_id,lobby_id) values(%s,%s,%s)', (mid,actor,lid))
                mids.append(mid)
            season = conn.execute('select * from start_scoring_season(%s,%s,%s,%s,%s)',
                (actors[0],lid,'1_week','Europe/Lisbon',Jsonb(new_rules(test_mode=qa)))).fetchone()
            return lid, mids, season['id']
        conn.execute("insert into territories values('territory-a','Test','{}')")
        lid, mids, sid = setup()
        def accept(index, kind='beer', size='small'):
            capture = uuid4()
            return conn.execute('select * from accept_scoring_checkin(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (actors[index],capture,mids[index],sid,kind,size,'territory-a','matched',f'{lid}/{capture}.jpg',NOW)).fetchone()
        owner = accept(0, 'mixed', 'large')
        before = accept(1)
        assert before['owner_membership_id'] == mids[0] and before['owner_bonus_quarters'] == 1
        conn.execute('insert into player_lobby_choices values(%s,%s)', (actors[0],lid))
        expect_error(lambda: conn.execute('select leave_lobby(%s,%s)', (actors[5],lid)), 'permission_denied')
        conn.execute('select leave_lobby(%s,%s)', (actors[0],lid))
        conn.execute('select leave_lobby(%s,%s)', (actors[0],lid))
        assert conn.execute('select 1 from lobby_memberships where id=%s and left_at is not null', (mids[0],)).fetchone()
        assert not conn.execute('select 1 from active_lobby_memberships where id=%s', (mids[0],)).fetchone()
        assert not conn.execute('select 1 from player_lobby_choices where player_id=%s', (actors[0],)).fetchone()
        expect_error(lambda: accept(0), 'permission_denied')
        expect_error(lambda: conn.execute('select list_chug_duels(%s,%s)', (actors[0],sid)), 'permission_denied')
        expect_error(lambda: conn.execute('select focus_status(%s,%s)', (actors[0],sid)), 'permission_denied')
        away = accept(2)
        assert away['owner_membership_id'] is None and away['owner_bonus_quarters'] == 0
        assert away['absent_member_ids'] == [mids[0]]
        conn.execute('select rejoin_lobby(%s,%s)', (actors[0],lid))
        expect_error(lambda: accept(0), 'cooldown')
        returned = accept(3)
        assert returned['owner_membership_id'] == mids[0] and returned['owner_bonus_quarters'] == 1
        conn.execute('select * from correct_scoring_checkin(%s,%s,%s,%s,0)', (actors[0],owner['id'],'wine','large'))
        rows = conn.execute('select * from drink_entries where season_id=%s order by event_order', (sid,)).fetchall()
        def parsed(row):
            return _row_to_drink_entry({k:v.isoformat() if hasattr(v,'isoformat') else
                [str(x) for x in v] if k=='absent_member_ids' else str(v) if hasattr(v,'hex') else v for k,v in row.items()})
        replay = replay_season([parsed(row) for row in rows])
        assert replay.season_quarters[str(mids[0])] == 18 # four earned points + two quarter bonuses
        for row in rows:
            recipient, bonus = replay.awards[str(row['id'])]
            assert recipient == (str(row['owner_membership_id']) if row['owner_membership_id'] else None)
            assert bonus == row['owner_bonus_quarters']
        expect_error(lambda: conn.execute("update drink_entries set absent_member_ids='{}' where id=%s", (away['id'],)), 'entry_identity_frozen')
        # Accepted duel blocks leaving; an unaccepted invitation is cancelled.
        invitation = uuid4()
        conn.execute('select invite_chug_duel(%s,%s,%s,%s,%s,%s)', (actors[0],sid,invitation,mids[1],'beer','small'))
        conn.execute("select chug_duel_action(%s,%s,'accept')", (actors[1],invitation))
        expect_error(lambda: conn.execute('select leave_lobby(%s,%s)', (actors[0],lid)), 'minigame_active')
        conn.execute("select chug_duel_action(%s,%s,'cancel')", (actors[0],invitation))
        invitation = uuid4()
        conn.execute('select invite_chug_duel(%s,%s,%s,%s,%s,%s)', (actors[0],sid,invitation,mids[1],'beer','small'))
        conn.execute('select leave_lobby(%s,%s)', (actors[0],lid))
        assert conn.execute('select status from chug_duels where id=%s',(invitation,)).fetchone()['status']=='cancelled'
        conn.execute('select rejoin_lobby(%s,%s)', (actors[0],lid))
        # QA Focus starts without uploads; a running attempt blocks departure.
        lid2, mids2, sid2 = setup(qa=True)
        conn.execute('select start_focus_attempt(%s,%s,%s)', (actors[0],sid2,uuid4()))
        expect_error(lambda: conn.execute('select leave_lobby(%s,%s)', (actors[0],lid2)), 'minigame_active')
        conn.execute("update test_clock set at_time=at_time+interval '11 minutes'")
        conn.execute('select leave_lobby(%s,%s)', (actors[0],lid2))
        # Team slot and assignment remain reserved, even while departed.
        team_lid, team_mids, team_sid = setup(team=True)
        original = conn.execute('select team_id from lobby_memberships where id=%s',(team_mids[0],)).fetchone()['team_id']
        conn.execute('select leave_lobby(%s,%s)', (actors[0],team_lid))
        expect_error(lambda: conn.execute('select choose_lobby_team(%s,%s,%s)', (actors[0],team_lid,original)), 'permission_denied')
        expect_error(lambda: conn.execute('insert into lobby_memberships(id,player_id,lobby_id) values(%s,%s,%s)',(uuid4(),actors[5],team_lid)), 'lobby_full')
        conn.execute('select rejoin_lobby(%s,%s)', (actors[0],team_lid))
        assert conn.execute('select team_id from lobby_memberships where id=%s',(team_mids[0],)).fetchone()['team_id']==original
        # A simultaneous visitor check-in and owner departure serialize.
        race_lid, race_mids, race_sid = setup()
        capture = uuid4()
        conn.execute('select * from accept_scoring_checkin(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (actors[0],capture,race_mids[0],race_sid,'mixed','large','territory-a','matched',f'{race_lid}/{capture}.jpg',NOW))
        barrier = Barrier(2)
        def race(action):
            with psycopg.connect(server.get_uri(),autocommit=True,row_factory=dict_row) as other:
                barrier.wait(timeout=10)
                if action=='leave':
                    other.execute('select leave_lobby(%s,%s)',(actors[0],race_lid))
                    return None
                capture = uuid4()
                return other.execute('select * from accept_scoring_checkin(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (actors[1],capture,race_mids[1],race_sid,'beer','small','territory-a','matched',f'{race_lid}/{capture}.jpg',NOW)).fetchone()
        with ThreadPoolExecutor(max_workers=2) as pool:
            visitor, _ = list(pool.map(race,('score','leave')))
        absent = race_mids[0] in visitor['absent_member_ids']
        assert visitor['owner_bonus_quarters'] == (0 if absent else 1)
        assert visitor['owner_membership_id'] == (None if absent else race_mids[0])
        for role in ('anon','authenticated'):
            assert not conn.execute("select has_function_privilege(%s,'leave_lobby(uuid,uuid)','EXECUTE') as ok",(role,)).fetchone()['ok']
            assert not conn.execute("select has_table_privilege(%s,'active_lobby_memberships','SELECT') as ok",(role,)).fetchone()['ok']
        conn.execute('select leave_lobby(%s,%s)',(actors[0],lid))
        saved = conn.execute('select * from drink_entries where season_id=%s order by event_order',(sid,)).fetchall()
    pgserver.pg_ctl(['-w','stop'],pgdata=server.pgdata)
    server.ensure_postgres_running()
    with psycopg.connect(server.get_uri(),autocommit=True,row_factory=dict_row) as conn:
        assert conn.execute('select * from drink_entries where season_id=%s order by event_order',(sid,)).fetchall()==saved
        assert conn.execute('select left_at from lobby_memberships where id=%s',(mids[0],)).fetchone()['left_at'] is not None
    print('PASS: leave/rejoin, retained scores/team slots, paused income and correction parity, access checks, duel/Focus blocking, expiry, permissions and restart persistence')


if __name__=='__main__':
    os.environ['LC_ALL']='C'
    with TemporaryDirectory(prefix='wego-leave-',dir='/private/tmp') as directory:
        pgserver.PostgresServer.runtime_path=Path(directory)
        pgserver.PostgresServer._lock=fasteners.InterProcessLock(Path(directory)/'.lock')
        with pgserver.get_server(Path(directory)/'data') as server:
            verify(server)
