"""Local-only SQL bridge for two real Streamlit browser sessions."""
import sys,json,os,time
from pathlib import Path
from tempfile import TemporaryDirectory
from http.server import BaseHTTPRequestHandler,HTTPServer
from datetime import datetime,timezone,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.time_postgres import LocalPostgres
from tests.time_duel_fixture import Fixture


def serve(f):
    l=f.lobby(qa=True);start=time.monotonic();base=f.now()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            try:
                body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or '{}')
                name=body['name'];p=body.get('parameters',{})
                f.clock(base+timedelta(seconds=time.monotonic()-start))
                if name=='fixture':result={**l,'players':f.players}
                elif name=='time_status':result=f.rpc('select time_status(%s,%s) data',(p['actor_player'],p['target_season']))['data']
                elif name=='invite_time_duel':result=f.rpc('select invite_time_duel(%s,%s,%s,%s) data',(p['actor_player'],p['target_season'],p['invitation_id'],p['opponent_member']))['data']
                elif name=='time_action':result=f.rpc('select time_action(%s,%s,%s,%s,%s) data',(p['actor_player'],p['target_duel'],p['selected_action'],p.get('expected_round'),p.get('elapsed')))['data']
                else:raise ValueError('Unknown route')
            except Exception as error:result={'error':str(error)}
            data=json.dumps(result,default=str).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(data)
    print('Time Duel local fixture ready',flush=True)
    HTTPServer(('127.0.0.1',int(os.environ.get('TIME_DUEL_FIXTURE_PORT', '8781'))),Handler).serve_forever()


if __name__=='__main__':
    os.environ['LC_ALL']='C'
    with TemporaryDirectory(prefix='wego-time-browser-',dir='/private/tmp') as directory:
        with LocalPostgres(directory) as server:
            try:serve(Fixture(server))
            except KeyboardInterrupt:pass
