"""Real pseudo-terminal journeys through CLI, menu, storage and child launch."""
import os
from pathlib import Path
import select
import struct
import subprocess
import sys
import tempfile
import time
import unittest

from .test_profiles import seed

if os.name != "nt":
    import fcntl
    import pty
    import termios


@unittest.skipIf(os.name == "nt", "POSIX PTY; native Windows console has its own integration tests")
class TerminalJourneyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("personal", "work"):
            seed(self.root, name)
        binary = self.root / "codex"
        binary.write_text(f'''#!{sys.executable}
import os,sys
from pathlib import Path
if sys.argv[1:]==['--help']:
 print('Usage: codex --no-daemon');sys.exit(0)
print('CHILD_ACCOUNT=' + Path(os.environ['CODEX_HOME']).name, flush=True)
''')
        binary.chmod(0o755)
        self.master, self.slave = pty.openpty()
        self.addCleanup(os.close, self.master)
        self.addCleanup(os.close, self.slave)
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 90, 0, 0))
        self.before = termios.tcgetattr(self.slave)
        program = '''import sys
from pathlib import Path
from tests.unit.fakes import application
from tests.integration.test_profiles import LocalAuth
from codex_switch.infrastructure.profiles import LocalProfiles
from codex_switch.infrastructure.projects import JsonProjects
from codex_switch.presentation.cli import CLI
from codex_switch.presentation.console import Console
app,_=application()
app.accounts.items=[]
root=Path(sys.argv[1])
app.profiles=LocalProfiles(root, auth_factory=LocalAuth, codex_binary=str(root/'codex'))
app.projects=JsonProjects(root, cwd=lambda:root)
app.projects.bind('work')
from codex_switch.infrastructure.platforms import current_platform
raise SystemExit(CLI(app,Console(language='en',terminal=current_platform().terminal)).run([]))
'''
        repo = Path(__file__).parents[2]
        env = {**os.environ, "TERM": "xterm-256color", "CODEX_SWITCH_LANG": "en",
               "PYTHONPATH": str(repo / "src") + os.pathsep + str(repo)}
        self.process = subprocess.Popen([sys.executable, "-c", program, str(self.root)],
                                        stdin=self.slave, stdout=self.slave, stderr=self.slave, env=env)
        self.addCleanup(self.stop)
        self.output = b""

    def stop(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=5)

    def assert_terminal_restored(self):
        actual = termios.tcgetattr(self.slave)
        expected = list(self.before)
        # Darwin sets PENDIN when returning to canonical mode; it is a kernel
        # input-reprocessing marker, not a mode left enabled by the picker.
        pending = getattr(termios, "PENDIN", 0)
        actual[3] &= ~pending
        expected[3] &= ~pending
        self.assertEqual(actual, expected)

    def until(self, value):
        deadline = time.monotonic() + 10
        while value not in self.output:
            if time.monotonic() >= deadline:
                self.fail("Terminal did not display expected text: " + repr(value) + "\n" + self.output.decode(errors="replace"))
            if select.select([self.master], [], [], 0.1)[0]:
                self.output += os.read(self.master, 65536)
            elif self.process.poll() is not None:
                self.fail("Terminal exited early: " + self.output.decode(errors="replace"))

    def test_arrow_switch_and_enter_launch_the_visible_account_and_restore_terminal(self):
        self.until(b"Enter: launch Codex")
        os.write(self.master, b"\x1b[A\r")
        self.until(b"CHILD_ACCOUNT=personal")
        self.assertEqual(self.process.wait(timeout=5), 0)
        self.assert_terminal_restored()
        self.assertIn(b"\x1b[?1049l", self.output)

    def test_escape_returns_without_launching_or_changing_the_default(self):
        self.until(b"Enter: launch Codex")
        os.write(self.master, b"\x1b")
        self.until(b"\x1b[?1049l")
        self.assertEqual(self.process.wait(timeout=5), 0)
        self.assert_terminal_restored()
        self.assertNotIn(b"CHILD_ACCOUNT", self.output)
        from codex_switch.infrastructure.projects import JsonProjects
        self.assertEqual(JsonProjects(self.root, cwd=lambda:self.root).bound(), "work")

    def test_settings_and_back_keep_the_account_selected(self):
        self.until(b"Enter: launch Codex")
        # End -> Exit, up -> Settings. Selection stays on work when returning.
        os.write(self.master, b"\x1b[F\x1b[A\r")
        self.until(b"Language / ")
        os.write(self.master, b"\x1b")
        time.sleep(0.1)
        self.output = b""
        self.until(b"Enter: launch Codex")
        os.write(self.master, b"\r")
        self.until(b"CHILD_ACCOUNT=work")
        self.assertEqual(self.process.wait(timeout=5), 0)

    def test_right_arrow_opens_actions_for_the_selected_account(self):
        self.until(b"Enter: launch Codex")
        os.write(self.master, b"\x1b[C")
        self.until(b"Rename account")
        os.write(self.master, b"q")
        time.sleep(0.1)
        self.output = b""
        self.until(b"Enter: launch Codex")
        os.write(self.master, b"\r")
        self.until(b"CHILD_ACCOUNT=work")
        self.assertEqual(self.process.wait(timeout=5), 0)
