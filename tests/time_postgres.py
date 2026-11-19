"""Start only our disposable PostgreSQL instance; no process or account scanning."""
from pathlib import Path
from subprocess import run, PIPE, STDOUT
from urllib.parse import urlencode
import pgserver


class LocalPostgres:
    def __init__(self,directory):
        self.directory=Path(directory)
        self.pgdata=self.directory/'data'
        self.bin=Path(pgserver.__file__).parent/'pginstall'/'bin'
    def command(self,name,*args):
        result=run([str(self.bin/name),*map(str,args)],stdout=PIPE,stderr=STDOUT,text=True)
        if result.returncode:raise RuntimeError(result.stdout)
    def __enter__(self):
        self.command('initdb','-D',self.pgdata,'--auth=trust','--encoding=UTF8','--no-locale','-U','postgres')
        self.ensure_postgres_running()
        return self
    def ensure_postgres_running(self):
        self.command('pg_ctl','-D',self.pgdata,'-l',self.directory/'postgres.log','-o',f"-k {self.directory} -h ''",'-w','start')
    def stop(self):self.command('pg_ctl','-D',self.pgdata,'-m','fast','-w','stop')
    def get_uri(self):return 'postgresql://postgres@/postgres?'+urlencode({'host':str(self.directory)})
    def __exit__(self,*exc):self.stop()
