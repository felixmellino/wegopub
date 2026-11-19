"""Disposable PostgreSQL checks for 009; never connects to Supabase.

Use the optional pgserver/psycopg/fasteners packages documented in
LOBBY_MIGRATION_REVIEW.md. Synthetic data and a temporary cluster only.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import fasteners
import pgserver
import psycopg

from verify_lobby_scoring_compat import (
    NOW, ROOT, SCHEMA, account, expect_error, install_test_clock, lobby, snapshot, start,
)

MIGRATION = (ROOT / 'migrations/009_single_competition_lobbies.sql').read_text()


def verify(server):
    uri = server.get_uri()
    with psycopg.connect(uri, autocommit=True) as conn:
        for role in ('anon', 'authenticated', 'service_role'):
            conn.execute('create role ' + role)
        conn.execute(SCHEMA)
        install_test_clock(conn)
        actor, outsider = account(conn), account(conn)
        historical, _ = lobby(conn, actor)
        # Preserve even pre-existing multi-season legacy history.
        for days in (30, 20):
            conn.execute("insert into seasons(id,lobby_id,starts_at,ends_at,length_choice) values(%s,%s,%s,%s,'1_week')",
                         (uuid4(), historical, NOW-timedelta(days=days), NOW-timedelta(days=days-7)))
        preserved = snapshot(conn, 'seasons')
        conn.execute(MIGRATION)
        conn.execute(MIGRATION)
        assert snapshot(conn, 'seasons') == preserved
        expect_error(lambda: start(conn, actor, historical), 'lobby_already_started')
        fresh, _ = lobby(conn, actor)
        expect_error(lambda: start(conn, outsider, fresh), 'permission_denied')
        game = start(conn, actor, fresh)
        assert len(snapshot(conn, 'seasons')) == 3
        expect_error(lambda: start(conn, actor, fresh), 'season_still_active')
        # At the exact end, the previous RPC allowed renewal; 009 forbids it.
        install_test_clock(conn, NOW+timedelta(days=7))
        expect_error(lambda: start(conn, actor, fresh), 'lobby_already_started')
        expect_error(lambda: conn.execute(
            "insert into seasons(id,lobby_id,starts_at,ends_at,length_choice) values(%s,%s,%s,%s,'1_week')",
            (uuid4(), fresh, NOW+timedelta(days=7), NOW+timedelta(days=14))), 'lobby_already_started')
        # Moving an imported legacy competition cannot bypass the guard.
        other, _ = lobby(conn, actor)
        imported = uuid4()
        conn.execute("insert into seasons(id,lobby_id,starts_at,ends_at,length_choice) values(%s,%s,%s,%s,'1_week')",
                     (imported, other, NOW, NOW+timedelta(days=7)))
        expect_error(lambda: conn.execute('update seasons set lobby_id=%s where id=%s', (fresh, imported)), 'lobby_already_started')
        racing, _ = lobby(conn, actor)
        def compete(_):
            with psycopg.connect(uri, autocommit=True) as rival:
                try:
                    start(rival, actor, racing)
                    return 'started'
                except psycopg.Error as error:
                    assert 'season_still_active' in str(error) or 'lobby_already_started' in str(error)
                    return 'rejected'
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(compete, range(2))) == ['rejected', 'started']
        assert conn.execute('select count(*) from seasons where lobby_id=%s', (racing,)).fetchone()[0] == 1
        saved = snapshot(conn, 'seasons')
    pgserver.pg_ctl(['-w', 'stop'], pgdata=server.pgdata)
    server.ensure_postgres_running()
    with psycopg.connect(server.get_uri(), autocommit=True) as conn:
        assert snapshot(conn, 'seasons') == saved
        expect_error(lambda: start(conn, actor, historical), 'lobby_already_started')
    print('PASS: migration repeat, legacy history, first start, nonmember denial, active/expired renewal denial, direct insert/update guards, concurrent start and PostgreSQL restart persistence')


if __name__ == '__main__':
    os.environ['LC_ALL'] = 'C'
    with TemporaryDirectory(prefix='wego-once-', dir='/private/tmp') as directory:
        pgserver.PostgresServer.runtime_path = Path(directory)
        pgserver.PostgresServer._lock = fasteners.InterProcessLock(Path(directory) / '.lock')
        with pgserver.get_server(Path(directory) / 'data') as server:
            verify(server)
