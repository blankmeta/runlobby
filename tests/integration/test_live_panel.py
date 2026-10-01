"""Actual PTY/ConPTY processes, synthetic logs; no accounts or LLM calls."""
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

from codex_switch.infrastructure.platforms.pty_process import spawn_terminal


def receive(process, needle, timeout=12):
    data=getattr(process,'_test_unread',b''); end=time.monotonic()+timeout
    while time.monotonic()<end:
        if needle in data:
            boundary=data.index(needle)+len(needle)
            process._test_unread=data[boundary:]
            return data[:boundary]
        chunk=process.read(.05)
        data+=chunk
        if not chunk and process.poll() is not None: break
    raise AssertionError(f'Expected marker {needle!r}; got {data[-1500:]!r}')


class NativePanelTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'POSIX PTY cleanup')
    def test_close_reaps_a_child_that_ignores_hangup_and_terminate(self):
        script = "import signal,time;signal.signal(signal.SIGHUP,signal.SIG_IGN);signal.signal(signal.SIGTERM,signal.SIG_IGN);print('READY',flush=True);time.sleep(60)"
        process = spawn_terminal([sys.executable, '-c', script], dict(os.environ), 25, 90)
        try:
            receive(process, b'READY')
            process.close()
            self.assertIsNotNone(process.returncode)
            with self.assertRaises(ChildProcessError): os.waitpid(process.pid, os.WNOHANG)
        finally:
            process.close()

    @unittest.skipIf(os.name == 'nt', 'POSIX descriptors only')
    def test_repeated_pty_cleanup_does_not_close_a_reused_descriptor(self):
        process = spawn_terminal([sys.executable, '-c', "print('READY',flush=True)"], dict(os.environ), 25, 90)
        try:
            receive(process, b'READY')
            old_fd = process.fd
            process.close()
            with open(os.devnull, 'rb') as handle:
                if handle.fileno() != old_fd:
                    os.dup2(handle.fileno(), old_fd)
                    self.addCleanup(os.close, old_fd)
                process.close()
                os.fstat(old_fd)
        finally:
            process.close()

    @unittest.skipIf(os.name == 'nt', 'POSIX descriptors only')
    def test_repeated_launch_and_close_does_not_accumulate_descriptors(self):
        import psutil
        current = psutil.Process()
        before = current.num_fds()
        for _ in range(12):
            process = spawn_terminal([sys.executable, '-c', "print('READY',flush=True)"], dict(os.environ), 25, 90)
            try:
                receive(process, b'READY')
            finally:
                process.close()
        self.assertEqual(current.num_fds(), before)

    def test_account_lease_outlives_the_wrapper_scope(self):
        from codex_switch.infrastructure.platforms import current_platform
        locks = current_platform().locks
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'account.lock'
            process = None
            try:
                with locks.acquire(path) as lease:
                    with lease.child_options() as options:
                        process = spawn_terminal([sys.executable,'-c',"print('READY',flush=True);input()"],
                                                 dict(os.environ),25,90,**options)
                    receive(process,b'READY')
                with self.assertRaises(BlockingIOError):
                    with locks.acquire(path): pass
                process.write(b'\r')
                end = time.monotonic()+5
                while process.poll() is None and time.monotonic()<end: process.read(.02)
                self.assertEqual(process.poll(),0)
                with locks.acquire(path): pass
            finally:
                if process: process.close()

    def test_pty_input_resize_and_exit_status(self):
        script="import os,sys;print('READY',os.isatty(0),flush=True);v=input();s=os.get_terminal_size();print('GOT',v,s.columns,s.lines,flush=True);sys.exit(7)"
        process=spawn_terminal([sys.executable,'-c',script],dict(os.environ),25,90)
        try:
            receive(process,b'READY True')
            process.resize(30,110);process.write(b'hello\r')
            receive(process,b'GOT hello 110 30')
            end=time.monotonic()+5
            while process.poll() is None and time.monotonic()<end:process.read(.02)
            self.assertEqual(process.poll(),7)
        finally:process.close()

    def test_live_panel_updates_without_a_model_and_agent_keeps_input(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder);(home/'sessions').mkdir()
            agent=home/'agent.py'
            agent.write_text('''import json,os,sys,time
from pathlib import Path
path=Path(os.environ['CODEX_HOME'])/'sessions'/'demo.jsonl'
def emit(kind,payload):
 with path.open('a') as f:f.write(json.dumps({'type':kind,'payload':payload,'timestamp':'2026-09-22T12:00:00Z'})+'\\n')
emit('session_meta',{'id':'demo','cwd':os.getcwd()})
emit('response_item',{'type':'message','role':'user','content':[{'type':'input_text','text':'DEMO_SESSION'}]})
emit('response_item',{'type':'function_call','name':'exec_command','call_id':'a','arguments':json.dumps({'cmd':'gh run view 123'})})
emit('token_usage_record',{'response_id':'r','usage':{'input_tokens':1000,'output_tokens':50}})
print('AGENT_READY',flush=True)
text=input()
print('INPUT_'+text,flush=True)
emit('token_usage_record',{'response_id':'r2','usage':{'input_tokens':2000,'output_tokens':50}})
time.sleep(1)
''')
            launch=home/'launch.py'
            launch.write_text('''import os,sys
from codex_switch.infrastructure.live_runner import LiveRunner
from codex_switch.infrastructure.platforms import current_platform
from codex_switch.domain.models import Preferences
class Settings:
 def load(self):return Preferences(True)
result=LiveRunner(Settings(),current_platform().terminal,'codex')([sys.executable,sys.argv[1]],env=dict(os.environ))
print('WRAPPER_DONE',result.returncode,flush=True)
''')
            env={**os.environ,'CODEX_HOME':str(home),'TERM':'xterm-256color','RUNLOBBY_MONITOR':'1'}
            process=spawn_terminal([sys.executable,str(launch),str(agent)],env,32,140)
            try:
                receive(process,b'AGENT_READY')
                receive(process,b'1.1k')
                process.write(b'hello\r')
                receive(process,b'INPUT_hello')
                receive(process,b'3.1k')
                receive(process,b'WRAPPER_DONE 0')
            finally:process.close()
