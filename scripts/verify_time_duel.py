"""Run against disposable PostgreSQL with synthetic accounts only."""
import os,sys,json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import psycopg
from psycopg.types.json import Jsonb
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.time_duel_fixture import Fixture
from tests.time_postgres import LocalPostgres
from core.time_duel import CONFIG
from core.scoring_v1 import replay_season
from data.db import _row_to_drink_entry
from data.quiz_questions import prepare_duel_deck


def rejected(call,reason):
    try:call()
    except psycopg.Error as e:assert reason in str(e),str(e)
    else:raise AssertionError('Expected '+reason)


def verify_invite_badge(f):
    lobby, other = f.lobby(), f.lobby()
    season, recipient = lobby['sid'], lobby['mids'][1]

    def count(player, selected_season=season):
        return f.rpc('select pending_minigame_invite_count(%s,%s) as n',
                     (f.players[player], selected_season))['n']

    def tiles(player, selected_season=season):
        return f.rpc('select * from pending_minigame_invites(%s,%s)',
                     (f.players[player], selected_season))

    time_duel = f.invite(lobby)
    quiz = uuid4()
    f.checkin(lobby, 2, size='large')
    f.checkin(lobby, 1, size='large')
    f.rpc('select invite_quiz_duel(%s,%s,%s,%s,%s,%s)',
          (f.players[2], season, quiz, recipient, 3, Jsonb(prepare_duel_deck(str(quiz)))))
    chug = uuid4()
    f.rpc('select * from invite_chug_duel(%s,%s,%s,%s,%s,%s)',
          (f.players[3], season, chug, recipient, 'beer', 'small'))
    assert count(1) == 3
    assert tiles(1) == dict(chug=1, quiz=1, time=1)
    assert tiles(0) == tiles(2) == tiles(3) == tiles(6) == tiles(1, other['sid']) == dict(chug=0, quiz=0, time=0)
    assert count(0) == count(2) == count(3) == count(6) == count(1, other['sid']) == 0
    second_time_duel = f.invite(lobby, 4, 1)
    assert tiles(1)['time'] == 2 and count(1) == 4
    f.act(second_time_duel, 4, 'cancel')
    assert tiles(1)['time'] == 1 and count(1) == 3
    f.conn.execute('set role anon')
    try:
        rejected(lambda: f.conn.execute('select pending_minigame_invite_count(%s,%s)',
                                        (f.players[1], season)), 'permission denied')
        rejected(lambda: f.conn.execute('select * from pending_minigame_invites(%s,%s)',
                                        (f.players[1], season)), 'permission denied')
    finally:
        f.conn.execute('reset role')
    f.act(time_duel, 1, 'decline')
    assert count(1) == 2
    assert tiles(1) == dict(chug=1, quiz=1, time=0)
    f.rpc('select quiz_action(%s,%s,%s,%s,%s)', (f.players[1], quiz, 'accept', None, None))
    assert count(1) == 1
    assert tiles(1) == dict(chug=1, quiz=0, time=0)
    f.advance(600)
    assert count(1) == 0
    assert tiles(1) == dict(chug=0, quiz=0, time=0)
    assert f.conn.execute('select status from chug_duels where id=%s', (chug,)).fetchone()['status'] == 'invited'
    print('PASS: Games and tile badges scope all three counts and exclude handled and expired invites')


def verify_invitations(f):
    for qa in (False, True):
        l = f.lobby(qa=qa)
        first = f.invite(l)
        assert f.status(l, 1)['duels'][0]['id'] == first['id']
        assert not f.status(l)['outgoing']
        assert f.invite(l, id=first['id'])['id'] == first['id']
        rejected(lambda: f.invite(l, 0, 2), 'time_pending')
        rejected(lambda: f.invite(l), 'time_pending')
        rejected(lambda: f.invite(l, 0, 2, first['id']), 'permission_denied')
        assert f.act(first, 1, 'decline')['status'] == 'declined'
        assert f.status(l)['outgoing']
        first = f.invite(l)
        assert f.act(first, 0, 'cancel')['status'] == 'cancelled'
        first = f.invite(l)
        f.advance(599)
        assert f.status(l)['duels'][0]['status'] == 'invited'
        f.advance(1)
        assert next(d for d in f.status(l)['duels'] if d['id'] == first['id'])['status'] == 'expired'
        assert f.act(first, 1, 'accept')['status'] == 'expired'
        assert f.status(l)['outgoing']
        # Both players' pending invites are resolved in the acceptance transaction.
        first = f.invite(l)
        other = f.invite(l, 2, 1)
        outgoing = f.invite(l, 1, 3)
        host_incoming = f.invite(l, 4, 0)
        unrelated = f.invite(l, 3, 5)
        assert f.act(first, 1, 'accept')['status'] == 'accepted'
        states = {str(r['id']): r['status'] for r in f.conn.execute(
            'select id,status from time_duels where season_id=%s', (l['sid'],))}
        assert states[other['id']] == states[host_incoming['id']] == 'declined'
        assert states[outgoing['id']] == 'cancelled' and states[unrelated['id']] == 'invited'
        for player in (0, 1):
            assert not f.status(l, player)['outgoing'] and not f.status(l, player)['incoming']
            rejected(lambda: f.invite(l, player, 5), 'time_busy' if qa or player == 1 else 'time_limit')
        rejected(lambda: f.invite(l, 2, 0), 'time_busy')
        assert f.act(first, 1, 'accept')['status'] == 'accepted'
        f.act(first, 0, 'cancel')
        assert f.status(l)['outgoing'] and f.status(l, 1)['outgoing']
        # History must never displace an open invitation from the inbox.
        for _ in range(22):
            d = f.invite(l)
            f.act(d, 1, 'decline')
        d = f.invite(l)
        assert any(x['id'] == d['id'] for x in f.status(l, 1)['duels'])
        f.act(d, 0, 'cancel')
        assert f.conn.execute('select count(*) n from drink_entries where season_id=%s',
                              (l['sid'],)).fetchone()['n'] == 0
        assert not f.status(l)['boost_ends_at'] and not f.status(l, 1)['boost_ends_at']
    # Simultaneous sends from separate tabs must create exactly one invitation.
    l = f.lobby(qa=True)
    barrier = Barrier(2)
    def send(opponent):
        with psycopg.connect(f.server.get_uri(), autocommit=True) as connection:
            connection.execute('set role service_role')
            barrier.wait()
            try:
                return connection.execute('select invite_time_duel(%s,%s,%s,%s)',
                    (f.players[0], l['sid'], uuid4(), l['mids'][opponent])).fetchone()[0]['status']
            except psycopg.Error as error:
                return str(error).splitlines()[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(send, [1, 2])) == ['invited', 'time_pending']
    # A pending invite survives a real server restart and still blocks another send.
    pending = f.status(l)['duels'][0]
    f.conn.close(); f.server.stop(); f.server.ensure_postgres_running()
    from psycopg.rows import dict_row
    f.conn = psycopg.connect(f.server.get_uri(), autocommit=True, row_factory=dict_row)
    assert f.status(l)['duels'][0] == pending
    rejected(lambda: f.invite(l, 0, 3), 'time_pending')
    print('PASS: Time Duel invitation delivery, duplicates, expiry, atomic cleanup, busy guards and restart')


def verify(f):
    verify_invitations(f)
    c=f.conn;l=f.lobby();qa=f.lobby(qa=True)
    assert c.execute('select _time_rules() data').fetchone()['data']==CONFIG
    rejected(lambda:f.status(l,6),'permission_denied')
    rejected(lambda:f.invite(l,0,0),'permission_denied')
    id=uuid4();d=f.invite(l,id=id);assert f.invite(l,id=id)['id']==d['id']
    assert d['target_ms'] is None and 'targets' not in d and not d['rounds']
    rejected(lambda:f.invite(l,2,1,id),'permission_denied')
    rejected(lambda:f.act(d,2,'accept'),'permission_denied')
    rejected(lambda:f.act(d,0,'stop',8000),'time_action')
    d=f.act(d,1,'accept');assert not f.status(l)['outgoing'] and not f.status(l,1)['incoming']
    rejected(lambda:f.invite(l,0,2),'time_limit')
    rejected(lambda:f.rpc('select leave_lobby(%s,%s)',(f.players[0],l['lid'])),'time_busy')
    # Cross-game locks work in both directions.
    chug=uuid4();f.rpc('select * from invite_chug_duel(%s,%s,%s,%s,%s,%s)',(f.players[0],l['sid'],chug,l['mids'][2],'beer','small'))
    rejected(lambda:f.rpc('select chug_duel_action(%s,%s,%s,%s)',(f.players[2],chug,'accept',None)),'time_busy')
    f.act(d,0,'cancel');assert f.status(l)['outgoing']
    f.rpc('select chug_duel_action(%s,%s,%s,%s)',(f.players[2],chug,'accept',None))
    rejected(lambda:f.invite(l),'quiz_busy')
    f.rpc('select chug_duel_action(%s,%s,%s,%s)',(f.players[0],chug,'cancel',None))
    d=f.invite(l);d=f.act(d,1,'accept');d=f.act(d,0,'ready');assert d['target_ms'] is None
    d=f.act(d,1,'ready');assert 5000<=d['target_ms']<=12000 and d['target_ms']%1000==0
    assert all(r['target_ms'] is None for r in d['rounds']), 'Future targets stay private'
    target=d['target_ms'];f.act(d,0,'start');f.advance(15);d=f.act(d,0,'stop',target+50)
    retried=f.act(d,0,'stop',target+2000)
    assert next(r for r in retried['rounds'] if r['membership_id']==str(l['mids'][0]))['elapsed_ms']==target+50
    hidden=f.status(l,1)['duels'][0];assert next(r for r in hidden['rounds'] if r['membership_id']==str(l['mids'][0]))['elapsed_ms'] is None
    d=f.act(d,1,'start');assert next(r for r in d['rounds'] if r['membership_id']==str(l['mids'][0]))['elapsed_ms']==target+50
    rejected(lambda:f.act(d,1,'stop',True),'does not exist')
    rejected(lambda:f.act(d,1,'stop',-1),'time_evidence')
    rejected(lambda:f.act(d,1,'stop',30001),'time_evidence')
    rejected(lambda:f.act(d,1,'stop',target),'time_evidence')
    f.advance(15);d=f.act(d,1,'stop',target+100);assert d['round_no']==1
    f.act(d,0,'start',round=0);assert not any(r['started'] for r in f.status(l)['duels'][0]['rounds'] if r['round_no']==1)
    for _ in range(2):d=f.round(d)
    assert d['winner_id']==str(l['mids'][0]) and d['status']=='completed'
    saved=d;assert f.act(d,1,'stop',0)==saved
    rejected(lambda:f.invite(l),'time_limit')
    assert f.status(l)['incoming'] and f.status(l,1)['outgoing']
    # Reward is season-only, exactly-once, correction-stable, and non-retroactive.
    f.checkin(l,2,'mixed','large');drink=f.checkin(l,0)
    assert drink['points_awarded']==1 and drink['time_bonus']==.25 and drink['owner_bonus_quarters']==1
    assert str(drink['time_duel_id'])==d['id']
    rows=c.execute('select * from drink_entries where season_id=%s order by event_order',(l['sid'],)).fetchall()
    replay=replay_season([_row_to_drink_entry(r) for r in json.loads(json.dumps(rows,default=str))]);assert dict(replay.season_rows())[str(l['mids'][0])]==1.25
    changed=f.rpc('select * from correct_scoring_checkin(%s,%s,%s,%s,%s)',(f.players[0],drink['id'],'beer','large',0))
    assert changed['points_awarded']==3 and changed['time_bonus']==.75 and changed['owner_bonus_quarters']==3
    # Focus wins over Time while retaining its existing owner/territory effects.
    focus=uuid4();now=f.now()
    c.execute("insert into focus_attempts(id,membership_id,season_id,game_night,attempt_number,status,phase,challenge,started_at,expires_at,deadline,completed_at,boost_ends_at) values(%s,%s,%s,'2026-11-19',1,'passed','reaction_ready','{}',%s,%s,%s,%s,%s)",
     (focus,l['mids'][0],l['sid'],now,now+timedelta(minutes=3),now+timedelta(seconds=30),now,now+timedelta(minutes=5)))
    f.advance(120);overlap=f.checkin(l,0);assert overlap['points_awarded']==1.5 and overlap['time_bonus']==0 and overlap['owner_bonus_quarters']==1.5
    f.advance(181);again=f.checkin(l,0);assert again['points_awarded']==1 and again['time_bonus']==.25
    f.clock(d['boost_ends_at']);expired=f.checkin(l,0);assert expired['time_bonus']==0
    # Exact complete ties grant both. Incomplete ties grant neither.
    tie=f.win(qa,tie=True);assert tie['status']=='draw' and tie['boost_ends_at']
    assert f.status(qa)['boost_ends_at'] and f.status(qa,1)['boost_ends_at']
    incomplete=f.invite(qa);incomplete=f.act(incomplete,1,'accept')
    for _ in range(3):incomplete=f.round(incomplete,abandon_a=True,abandon_b=True)
    assert incomplete['status']=='draw' and incomplete['boost_ends_at'] is None
    # Fewer forfeits beats even a much smaller valid-round error.
    abandoned=f.invite(qa);abandoned=f.act(abandoned,1,'accept')
    abandoned=f.round(abandoned,abandon_a=True)
    for _ in range(2):abandoned=f.round(abandoned,offset_a=0,offset_b=5000)
    assert abandoned['winner_id']==str(qa['mids'][1])
    # A timer timeout is recorded; it cannot be restarted or replaced.
    timed=f.invite(qa);timed=f.act(timed,1,'accept');timed=f.ready(timed);f.act(timed,0,'start');f.advance(30)
    timed=f.status(qa)['duels'][0];assert next(r for r in timed['rounds'] if r['membership_id']==str(qa['mids'][0]))['abandoned']
    f.act(timed,0,'stop',8000);assert next(r for r in f.status(qa)['duels'][0]['rounds'] if r['membership_id']==str(qa['mids'][0]))['abandoned']
    f.advance(600);assert f.status(qa)['duels'][0]['status']=='expired'
    # QA outside weekly window, season-end and normal 06:00 boundaries.
    f.clock('2026-11-23T12:00:00Z');assert not f.status(l)['open'] and f.status(qa)['open']
    rejected(lambda:f.invite(l),'scoring_closed')
    qd=f.invite(qa);f.act(qd,1,'accept');f.advance(601);assert f.status(qa)['duels'][0]['status']=='expired'
    f.clock('2026-11-20T05:59:00Z');assert not f.status(l)['outgoing']
    f.clock('2026-11-20T06:00:00Z');assert f.status(l)['outgoing']
    # Team eligibility and own-entry season contribution.
    team=f.lobby(qa=True,team=True);rejected(lambda:f.invite(team,0,2),'duel_team')
    tw=f.win(team);team_drink=f.checkin(team,0);assert team_drink['time_bonus']==.25 and team_drink['team_id']==team['teams'][0]
    # Concurrent acceptance cannot reserve one membership for two duels.
    race=f.lobby(qa=True);first=f.invite(race,0,1);second=f.invite(race,2,1);barrier=Barrier(2)
    def race_accept(duel):
        with psycopg.connect(f.server.get_uri(),autocommit=True) as connection:
            connection.execute('set role service_role');barrier.wait()
            try:return connection.execute('select time_action(%s,%s,%s,%s,%s)',
                (f.players[1],duel['id'],'accept',None,None)).fetchone()[0]['status']
            except psycopg.Error as error:return str(error).splitlines()[0]
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(race_accept,[first,second]))
    assert sorted(results)==['accepted','declined'],results
    # Departed members cannot read or submit. No public-role access.
    f.rpc('select leave_lobby(%s,%s)',(f.players[3],l['lid']));rejected(lambda:f.status(l,3),'permission_denied')
    for role in ('anon','authenticated'):
        assert not c.execute("select has_table_privilege(%s,'time_duels','SELECT') ok",(role,)).fetchone()['ok']
        assert not c.execute("select has_function_privilege(%s,'time_action(uuid,uuid,text,integer,integer)','EXECUTE') ok",(role,)).fetchone()['ok']
    # Restart the actual database with a round in progress; no clock/target reroll.
    restart=f.invite(qa);restart=f.act(restart,1,'accept');restart=f.ready(restart);f.act(restart,0,'start')
    before=f.status(qa)['duels'][0];f.conn.close()
    f.server.stop();f.server.ensure_postgres_running()
    from psycopg.rows import dict_row
    f.conn=psycopg.connect(f.server.get_uri(),autocommit=True,row_factory=dict_row)
    assert f.status(qa)['duels'][0]==before
    print('PASS: Time Duel SQL lifecycle, access, reward/correction/Focus/territory parity, QA/night boundaries and database restart')


if __name__=='__main__':
    os.environ['LC_ALL']='C'
    with TemporaryDirectory(prefix='wego-time-',dir='/private/tmp') as directory:
        with LocalPostgres(directory) as server:
            fixture = Fixture(server)
            verify(fixture)
            fixture.clock('2026-11-19T20:00:00Z')
            verify_invite_badge(fixture)
