"""Disposable PostgreSQL fixture. Optional dependencies documented in TIME_DUEL.md."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from core.scoring_v1 import new_rules

ROOT=Path(__file__).resolve().parents[1]
MIGRATIONS=['004_server_game_tables.sql','005_scoring_v1.sql','009_single_competition_lobbies.sql',
 '010_team_lobbies.sql','011_chug_duel.sql','012_qa_minigames.sql','012_player_lobby_choices.sql',
 '014_focus_challenge.sql','015_focus_test_replays.sql','016_quiz_duel.sql','016_leave_lobby.sql','017_time_duel.sql',
 '021_time_duel_invitations.sql']


class Fixture:
    def __init__(self,server):
        self.server=server
        self.conn=psycopg.connect(server.get_uri(),autocommit=True,row_factory=dict_row)
        c=self.conn
        for role in ('anon','authenticated','service_role'):c.execute('create role '+role+' bypassrls')
        c.execute((ROOT/'schema.sql').read_text().replace('create extension if not exists pgcrypto;',''))
        c.execute("create table test_clock(at_time timestamptz); insert into test_clock values('2026-11-19T20:00:00Z')")
        c.execute('grant select on test_clock to service_role')
        c.execute('create function test_now() returns timestamptz language sql as $$ select at_time from test_clock $$')
        for name in MIGRATIONS:c.execute((ROOT/'migrations'/name).read_text().replace('statement_timestamp()','public.test_now()'))
        c.execute((ROOT/'migrations/021_time_duel_invitations.sql').read_text().replace('statement_timestamp()','public.test_now()'))
        self.players=[uuid4() for _ in range(7)]
        for n,p in enumerate(self.players):c.execute("insert into players(id,display_name,first_name,last_name,pin_hash) values(%s,%s,'Test','Only','fake')",(p,'Player '+str(n+1)))
        c.execute("insert into territories values('time-test','Time test','{}')")

    def now(self):return self.conn.execute('select at_time from test_clock').fetchone()['at_time']
    def advance(self,seconds):self.clock(self.now()+timedelta(seconds=seconds))
    def clock(self,at):self.conn.execute('update test_clock set at_time=%s',(at,))
    def rpc(self,sql,args=()):
        self.conn.execute('set role service_role')
        try:return self.conn.execute(sql,args).fetchone()
        finally:self.conn.execute('reset role')
    def lobby(self,qa=False,team=False):
        lid=uuid4()
        self.conn.execute("insert into lobbies(id,name,invite_code,game_mode,team_count,team_capacity,team_assignment) values(%s,'Time test',%s,%s,%s,%s,%s)",
         (lid,str(lid),'team' if team else 'individual',2 if team else None,4 if team else None,'manual' if team else None))
        teams=[r['id'] for r in self.conn.execute('select id from lobby_teams where lobby_id=%s order by number',(lid,))] if team else []
        mids=[uuid4() for _ in range(6)]
        for i,mid in enumerate(mids):self.conn.execute('insert into lobby_memberships(id,player_id,lobby_id,team_id) values(%s,%s,%s,%s)',(mid,self.players[i],lid,teams[i%2] if team else None))
        sid=self.rpc('select * from start_scoring_season(%s,%s,%s,%s,%s)',(self.players[0],lid,'1_month','Europe/Lisbon',Jsonb(new_rules(test_mode=qa))))['id']
        return dict(lid=lid,sid=sid,mids=mids,teams=teams)
    def invite(self,l,p=0,o=1,id=None):return self.rpc('select invite_time_duel(%s,%s,%s,%s) data',(self.players[p],l['sid'],id or uuid4(),l['mids'][o]))['data']
    def act(self,d,p,action,ms=None,round=None):return self.rpc('select time_action(%s,%s,%s,%s,%s) data',(self.players[p],d['id'],action,d['round_no'] if round is None else round,ms))['data']
    def status(self,l,p=0):return self.rpc('select time_status(%s,%s) data',(self.players[p],l['sid']))['data']
    def checkin(self,l,p,kind='beer',size='small',territory='time-test'):
        id=uuid4()
        return self.rpc('select * from accept_scoring_checkin(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
         (self.players[p],id,l['mids'][p],l['sid'],kind,size,territory,'matched' if territory else 'outside',f"{l['lid']}/{id}.jpg",self.now()))
    def ready(self,d,a=0,b=1):
        d=self.act(d,a,'ready');return self.act(d,b,'ready')
    def round(self,d,a=0,b=1,offset_a=0,offset_b=200,abandon_a=False,abandon_b=False):
        d=self.ready(d,a,b);target=d['target_ms'];self.act(d,a,'start');self.act(d,b,'start');self.advance(15)
        self.act(d,a,'abandon' if abandon_a else 'stop',None if abandon_a else target+offset_a)
        return self.act(d,b,'abandon' if abandon_b else 'stop',None if abandon_b else target+offset_b)
    def win(self,l,a=0,b=1,tie=False):
        d=self.invite(l,a,b);d=self.act(d,b,'accept')
        for _ in range(3):d=self.round(d,a,b,offset_b=0 if tie else 200)
        return d
