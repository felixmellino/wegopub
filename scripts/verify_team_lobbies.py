"""Run 010 against disposable PostgreSQL; no Supabase credentials used.

Optional packages and invocation: see docs/TEAM_MODE.md.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import fasteners
import pgserver
import psycopg
from psycopg.rows import dict_row

from verify_lobby_scoring_compat import ROOT, SCHEMA, NOW, account, expect_error, install_test_clock, start

SQL = (ROOT/'migrations/010_team_lobbies.sql').read_text()


def snapshot(conn, table):
    return conn.execute(f"select coalesce(jsonb_agg(to_jsonb(t) order by id), '[]') as rows from {table} t").fetchone()['rows']


def verify(server):
    uri = server.get_uri()
    with psycopg.connect(uri,autocommit=True,row_factory=dict_row) as conn:
        for role in ('anon','authenticated','service_role'):
            conn.execute('create role '+role)
        conn.execute(SCHEMA)
        install_test_clock(conn)
        conn.execute((ROOT/'migrations/009_single_competition_lobbies.sql').read_text())
        # A populated individual lobby must survive the migration unchanged.
        actors = [account(conn) for _ in range(12)]
        legacy, legacy_member = uuid4(),uuid4()
        conn.execute("insert into lobbies(id,name,invite_code) values(%s,'Individual',%s)",(legacy,str(legacy)))
        conn.execute('insert into lobby_memberships(id,player_id,lobby_id) values(%s,%s,%s)',(legacy_member,actors[0],legacy))
        legacy_season = start(conn,actors[0],legacy)['id']
        conn.execute("insert into territories values('territory-a','Test','{}')")
        def accept(actor,member,lid,sid,kind='mixed',size='large'):
            capture = uuid4()
            return conn.execute('select * from accept_scoring_checkin(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (actor,capture,member,sid,kind,size,'territory-a','matched',f'{lid}/{capture}.jpg',NOW)).fetchone()
        accept(actors[0],legacy_member,legacy,legacy_season)
        previous = snapshot(conn,'drink_entries')
        conn.execute(SQL)
        conn.execute(SQL)
        assert snapshot(conn,'drink_entries') == [dict(row,team_id=None,owner_team_id=None) for row in previous]
        def lobby(assignment='manual',capacity=2):
            lid = uuid4()
            conn.execute("insert into lobbies(id,name,invite_code,game_mode,team_count,team_capacity,team_assignment) values(%s,'Teams',%s,'team',2,%s,%s)",(lid,str(lid),capacity,assignment))
            teams = conn.execute('select * from lobby_teams where lobby_id=%s order by number',(lid,)).fetchall()
            assert [t['name'] for t in teams] == ['Team 1','Team 2']
            return lid,[t['id'] for t in teams]
        def join(actor,lid):
            return conn.execute('insert into lobby_memberships(id,player_id,lobby_id) values(%s,%s,%s) returning *',(uuid4(),actor,lid)).fetchone()
        def choose(actor,lid,team):
            conn.execute('select choose_lobby_team(%s,%s,%s)',(actor,lid,team))
        def edit(actor,team,name='Tigers',photo=None,change=False):
            conn.execute('select edit_lobby_team(%s,%s,%s,%s,%s)',(actor,team,name,photo,change))
        lid,(A,B) = lobby()
        ma,mb,mc,md = [join(a,lid) for a in actors[:4]]
        sid = start(conn,actors[0],lid)['id']
        expect_error(lambda: accept(actors[0],ma['id'],lid,sid),'team_required')
        assert not conn.execute('select 1 from drink_entries where season_id=%s',(sid,)).fetchall()
        choose(actors[0],lid,A); choose(actors[1],lid,A)
        expect_error(lambda: choose(actors[2],lid,A),'team_full')
        choose(actors[2],lid,B); choose(actors[3],lid,B)
        expect_error(lambda: join(actors[4],lid),'lobby_full')
        expect_error(lambda: edit(actors[2],A),'permission_denied')
        edit(actors[0],A,'Tigers','aGVsbG8=',True)
        edit(actors[1],A,'Lions')
        assert conn.execute('select name,photo_base64 from lobby_teams where id=%s',(A,)).fetchone() == {'name':'Lions','photo_base64':'aGVsbG8='}
        expect_error(lambda: edit(actors[2],B,'lions'),'duplicate key')
        expect_error(lambda: edit(actors[0],A,' '),'invalid_team_name')
        a = accept(actors[0],ma['id'],lid,sid)
        b = accept(actors[1],mb['id'],lid,sid,kind='shot',size=None)
        c = accept(actors[2],mc['id'],lid,sid)
        assert a['team_id'] == A and a['owner_bonus_quarters'] == 0
        assert b['team_id'] == A and b['owner_bonus_quarters'] == 0
        assert c['owner_team_id'] == A and c['owner_membership_id'] is None and c['owner_bonus_quarters'] == 5
        expect_error(lambda: choose(actors[0],lid,B),'team_locked')
        expect_error(lambda: conn.execute('update drink_entries set team_id=%s where id=%s',(B,a['id'])),'entry_identity_frozen')
        # Correction replays owner income and agrees with Python.
        conn.execute('select * from correct_scoring_checkin(%s,%s,%s,%s,0)',(actors[0],a['id'],'beer','small'))
        from data.db import _row_to_drink_entry
        from core.scoring_v1 import replay_season
        entries = conn.execute('select * from drink_entries where season_id=%s order by event_order',(sid,)).fetchall()
        parsed = [_row_to_drink_entry({k:(v.isoformat() if hasattr(v,'isoformat') else str(v) if k in ('id','membership_id','season_id','team_id','owner_team_id','owner_membership_id') and v is not None else v) for k,v in r.items()}) for r in entries]
        replay = replay_season(parsed)
        for e in parsed:
            assert replay.awards[e.id] == (e.owner_team_id,e.owner_bonus_quarters)
        # Snapshot and winner survive restart below.
        saved = {t:snapshot(conn,t) for t in ('lobbies','lobby_memberships','lobby_teams','drink_entries')}
        random_lid,random_teams = lobby('random')
        assigned = [join(a,random_lid)['team_id'] for a in actors[:4]]
        assert sorted(assigned.count(t) for t in random_teams) == [2,2]
        other_team = next(t for t in random_teams if t != assigned[0])
        expect_error(lambda: choose(actors[0],random_lid,other_team),'random_team_locked')
        # Two simultaneous joins for a last team slot: exactly one succeeds.
        race_lid,(race_team,_) = lobby(capacity=1)
        for actor in actors[4:6]:
            join(actor,race_lid)
        def race(actor):
            with psycopg.connect(uri,autocommit=True) as other:
                try:
                    other.execute('select choose_lobby_team(%s,%s,%s)',(actor,race_lid,race_team))
                    return 'joined'
                except psycopg.Error as exc:
                    assert 'team_full' in str(exc)
                    return 'full'
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(race,actors[4:6])) == ['full','joined']
        other_lid,other_teams = lobby()
        expect_error(lambda: choose(actors[3],lid,other_teams[0]),'invalid_team')
        for role in ('anon','authenticated'):
            assert not conn.execute("select has_table_privilege(%s,'lobby_teams','SELECT') as ok",(role,)).fetchone()['ok']
            assert not conn.execute("select has_function_privilege(%s,'choose_lobby_team(uuid,uuid,uuid)','EXECUTE') as ok",(role,)).fetchone()['ok']
        saved = {t:snapshot(conn,t) for t in saved}
    pgserver.pg_ctl(['-w','stop'],pgdata=server.pgdata)
    server.ensure_postgres_running()
    with psycopg.connect(server.get_uri(),autocommit=True,row_factory=dict_row) as conn:
        assert saved == {t:snapshot(conn,t) for t in saved}
    print('PASS: migration repeat, individual preservation, capacity/concurrent joins, random balance, permissions, names/pictures, team scoring, teammate income exclusion, correction replay parity and restart persistence')


if __name__ == '__main__':
    os.environ['LC_ALL']='C'
    with TemporaryDirectory(prefix='wego-teams-',dir='/private/tmp') as directory:
        pgserver.PostgresServer.runtime_path=Path(directory)
        pgserver.PostgresServer._lock=fasteners.InterProcessLock(Path(directory)/'.lock')
        with pgserver.get_server(Path(directory)/'data') as server:
            verify(server)
