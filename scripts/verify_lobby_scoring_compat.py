"""Verify migration 007 on a disposable local PostgreSQL cluster, never Supabase.

Optional test dependencies: pgserver==0.1.4, psycopg[binary]==3.2.13,
fasteners==0.20. Run from the repository root. The script uses only the
pgserver-generated local URI, isolated data/lock paths and synthetic fixtures.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import fasteners
import pgserver
import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.scoring_v1 import new_rules, scoring_open
from core.models import Season

NOW = datetime(2026, 11, 19, 18, tzinfo=timezone.utc)
SCHEMA = (ROOT / 'schema.sql').read_text().replace('create extension if not exists pgcrypto;', '')
SCORING = (ROOT / 'migrations/005_scoring_v1.sql').read_text()
MIGRATION = (ROOT / 'migrations/007_lobby_battles.sql').read_text()


def install_test_clock(conn, at=NOW):
    # Only the disposable test copy gets a fixed server receipt clock. No
    # production SQL is edited and clients never choose this time in the app.
    value = at.isoformat().replace("'", "''")
    conn.execute(SCORING.replace('statement_timestamp()', f"'{value}'::timestamptz"))


def expect_error(operation, message):
    try:
        operation()
    except psycopg.Error as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError(f'Expected SQL error containing {message!r}')


def snapshot(conn, table):
    # Table names below are fixed test constants, never user input.
    return conn.execute(f'select coalesce(jsonb_agg(to_jsonb(t) order by id), \'[]\') from {table} t').fetchone()[0]


def account(conn):
    pid = uuid4()
    conn.execute("insert into players(id,display_name,first_name,last_name,pin_hash) values(%s,%s,'Test','Only','fake')", (pid, str(pid)))
    return pid


def lobby(conn, actor):
    lid, mid = uuid4(), uuid4()
    conn.execute("insert into lobbies values(%s,'Compatibility test',%s)", (lid, str(lid)))
    conn.execute('insert into lobby_memberships(id,player_id,lobby_id,joined_at) values(%s,%s,%s,%s)', (mid, actor, lid, NOW))
    return lid, mid


def start(conn, actor, lid, length='1_week', zone='Europe/Lisbon'):
    return conn.execute('select * from start_scoring_season(%s,%s,%s,%s,%s)', (actor, lid, length, zone, Jsonb(new_rules()))).fetchone()


def accept(conn, actor, mid, lid, sid, capture, drink='beer', size='large', photo_time=NOW):
    return conn.execute('select * from accept_scoring_checkin(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
        (actor, capture, mid, sid, drink, size, 'compat-territory', 'matched', f'{lid}/{capture}.jpg', photo_time)).fetchone()


def role_query(conn, role, sql):
    with conn.transaction():
        conn.execute('set local role ' + role)  # fixed role constants below
        return conn.execute(sql).fetchall()


def verify(server):
    uri = server.get_uri()
    with psycopg.connect(uri, autocommit=True) as conn:
        for role in ('anon', 'authenticated'):
            conn.execute('create role ' + role)
        conn.execute('create role service_role bypassrls')
        conn.execute(SCHEMA)
        install_test_clock(conn)
        alice, bob, outsider = [account(conn) for _ in range(3)]
        legacy_lid, legacy_mid = lobby(conn, alice)
        legacy_sid, legacy_entry = uuid4(), uuid4()
        conn.execute("insert into seasons(id,lobby_id,starts_at,ends_at,length_choice) values(%s,%s,%s,%s,'1_week')",
                     (legacy_sid, legacy_lid, NOW-timedelta(days=20), NOW-timedelta(days=13)))
        conn.execute("insert into drink_entries(id,membership_id,season_id,drink_type,photo_ref,location_check_result,points_awarded,submitted_at) values(%s,%s,%s,'beer','legacy.jpg','outside',10,%s)",
                     (legacy_entry, legacy_mid, legacy_sid, NOW-timedelta(days=19)))
        # Freeze a populated v1 season too, so migration preservation covers
        # dates, rules, revision metadata, points and historical legacy rows.
        existing_lid, existing_mid = lobby(conn, alice)
        existing_sid = start(conn, alice, existing_lid)[0]
        conn.execute("insert into territories values('compat-territory','Compatibility territory','{}')")
        existing_capture = uuid4()
        accept(conn, alice, existing_mid, existing_lid, existing_sid, existing_capture)
        preserved = {t: snapshot(conn, t) for t in ('players','lobbies','lobby_memberships','seasons','drink_entries')}
        conn.execute(MIGRATION)
        assert preserved == {t: snapshot(conn, t) for t in preserved}
        assert conn.execute("select relkind from pg_class where oid='public.lobby_states'::regclass").fetchone()[0] == 'v'
        assert conn.execute("select to_regprocedure('public.guard_battle_entry()'),to_regprocedure('public.save_lobby_state(jsonb,uuid)')").fetchone() == (None, None)
        legacy_state = conn.execute('select state from lobby_states where lobby_id=%s',(legacy_lid,)).fetchone()[0]
        assert legacy_state['members'][0]['id'] == str(legacy_mid)
        assert legacy_state['seasons'][0]['id'] == str(legacy_sid)
        assert legacy_state['seasons'][0]['scoring_version'] == 'legacy'
        print('PASS: populated legacy/v1 data preserved; no incompatible write RPC or trigger')

        # Same direct writes as current data/db.py: no owner setup, capacity
        # rule, second player or new lobby-state call is required.
        lid, mid = lobby(conn, alice)
        assert conn.execute('select jsonb_array_length(state->\'members\') from lobby_states where lobby_id=%s',(lid,)).fetchone()[0] == 1
        bob_mid = uuid4()
        conn.execute('insert into lobby_memberships(id,player_id,lobby_id,joined_at) values(%s,%s,%s,%s)', (bob_mid,bob,lid,NOW))
        # A current member other than the creator may still start the season.
        sid = start(conn, bob, lid, '1_month', 'America/New_York')[0]
        state = conn.execute('select state from lobby_states where lobby_id=%s',(lid,)).fetchone()[0]
        season = state['seasons'][0]
        assert len(state['members']) == 2
        assert season['scoring_version'] == 'v1' and season['scoring_rules'] == new_rules()
        assert season['timezone_name'] == 'America/New_York'
        assert datetime.fromisoformat(season['ends_at']) - datetime.fromisoformat(season['starts_at']) == timedelta(days=30)
        expect_error(lambda: start(conn, outsider, lid), 'permission_denied')
        expect_error(lambda: start(conn, alice, lid), 'season_still_active')
        expect_error(lambda: conn.execute("update seasons set timezone_name='UTC' where id=%s",(sid,)), 'season_rules_frozen')
        for length, days in [('1_week',7),('3_months',91)]:
            extra_lid, _ = lobby(conn, alice)
            extra_sid = start(conn, alice, extra_lid, length)[0]
            assert conn.execute('select ends_at-starts_at from seasons where id=%s',(extra_sid,)).fetchone()[0] == timedelta(days=days)
        # Views are derived, not copied: ordinary renames show up immediately.
        conn.execute("update lobbies set name='Renamed lobby' where id=%s", (lid,))
        assert conn.execute("select state->>'name' from lobby_states where lobby_id=%s",(lid,)).fetchone()[0] == 'Renamed lobby'
        print('PASS: unchanged create/join/member-start flow, frozen rules/timezone, 7/30/91 days, nonmember and overlap rejection')

        for zone in ('Europe/Lisbon','America/New_York'):
            model = Season('s','l',NOW-timedelta(days=1),NOW+timedelta(days=8),'1_week',zone,'v1',new_rules())
            for at in (NOW-timedelta(seconds=1), NOW, NOW+timedelta(days=3,seconds=-1),NOW+timedelta(days=3),NOW+timedelta(hours=5)):
                actual=conn.execute('select _scoring_window_open(%s,%s,%s)',(at,zone,Jsonb(new_rules()))).fetchone()[0]
                assert actual == scoring_open(at,model), (zone,at)
        score_lid, score_mid = lobby(conn, alice)
        score_bob_mid = uuid4()
        conn.execute('insert into lobby_memberships(id,player_id,lobby_id,joined_at) values(%s,%s,%s,%s)',(score_bob_mid,bob,score_lid,NOW))
        score_sid = start(conn, alice, score_lid)[0]
        first, second = uuid4(), uuid4()
        accept(conn,alice,score_mid,score_lid,score_sid,first)
        accept(conn,bob,score_bob_mid,score_lid,score_sid,second,'mixed','large')
        awarded=conn.execute('select points_awarded,owner_membership_id,owner_bonus_quarters from drink_entries where id=%s',(second,)).fetchone()
        assert awarded == (5,score_mid,5)  # 1.25 additional season points, unchanged
        conn.execute('select * from correct_scoring_checkin(%s,%s,%s,%s,%s)',(alice,first,'beer','small',0))
        assert conn.execute('select points_awarded,revision from drink_entries where id=%s',(first,)).fetchone() == (1,1)
        expect_error(lambda:conn.execute('select * from correct_scoring_checkin(%s,%s,%s,%s,%s)',(alice,first,'mixed','large',0)),'correction_conflict')
        assert conn.execute('select count(*) from drink_entry_revisions where entry_id=%s',(first,)).fetchone()[0] == 1
        rows_before=snapshot(conn,'drink_entries')
        accept(conn,bob,score_bob_mid,score_lid,score_sid,second,'mixed','large')
        expect_error(lambda:accept(conn,bob,score_bob_mid,score_lid,score_sid,uuid4(),'beer','large'),'cooldown')
        expect_error(lambda:accept(conn,outsider,score_mid,score_lid,score_sid,uuid4()),'permission_denied')
        assert snapshot(conn,'drink_entries') == rows_before
        # Shift only the disposable copy's server receipt clock to Sunday 18:00.
        install_test_clock(conn,NOW+timedelta(days=3))
        expect_error(lambda:accept(conn,alice,score_mid,score_lid,score_sid,uuid4()),'scoring_closed')
        assert snapshot(conn,'drink_entries') == rows_before
        print('PASS: Python/SQL weekly boundaries agree; acceptance, duplicate retry, cooldown, corrections, owner income and closed-window rejection unchanged')

        for role in ('anon','authenticated'):
            expect_error(lambda:role_query(conn,role,'select * from lobby_states'),'permission denied')
        assert role_query(conn,'service_role','select * from lobby_states')
        expect_error(lambda:role_query(conn,'service_role',"update lobby_states set lobby_id=gen_random_uuid()"),'permission denied')
        expected=conn.execute('select * from lobby_states order by lobby_id').fetchall()
        conn.execute(MIGRATION)  # safe repeat: no reseeding, timestamps or rules changed
        assert expected == conn.execute('select * from lobby_states order by lobby_id').fetchall()
        print('PASS: server read-only access, public-client denial and safe migration repeat')
    pgserver.pg_ctl(['-w','stop'], pgdata=server.pgdata)
    server.ensure_postgres_running()
    with psycopg.connect(server.get_uri(),autocommit=True) as conn:
        assert expected == conn.execute('select * from lobby_states order by lobby_id').fetchall()
    print('PASS: real PostgreSQL restart preserves lobby snapshots and scoring records')
    with psycopg.connect(server.get_uri(),autocommit=True) as conn:
        conn.execute('create database old_lobby_draft_test')
    with psycopg.connect(server.get_uri('old_lobby_draft_test'),autocommit=True) as old:
        old.execute(SCHEMA)
        install_test_clock(old)
        old.execute('create table lobby_states(lobby_id uuid primary key,state jsonb not null)')
        marker=uuid4()
        old.execute('insert into lobby_states values(%s,%s)',(marker,Jsonb({'preserve':'old draft'})))
        expect_error(lambda:old.execute(MIGRATION),'is not a view')
        old.rollback()
        assert old.execute('select state from lobby_states where lobby_id=%s',(marker,)).fetchone()[0] == {'preserve':'old draft'}
    print('PASS: an already-installed old draft is refused without changing its data')


if __name__ == '__main__':
    os.environ['LC_ALL']='C'
    with TemporaryDirectory(prefix='wegopub-lobby-compat-') as directory:
        pgserver.PostgresServer.runtime_path=Path(directory)
        pgserver.PostgresServer._lock=fasteners.InterProcessLock(Path(directory)/'.lock')
        with pgserver.get_server(Path(directory)/'data') as server:
            verify(server)
