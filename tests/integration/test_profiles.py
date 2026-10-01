from dataclasses import asdict
import json
import os
import psutil
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from codex_switch.domain.errors import SwitchError
from codex_switch.domain.models import Account
from codex_switch.infrastructure.profiles import LocalProfiles, ProfileBusy, profile_lock
from codex_switch.infrastructure.projects import JsonProjects
from codex_switch.infrastructure.storage import atomic_json


class LocalAuth:
    def __init__(self, home): self.home = home
    def list(self, **kwargs):
        data = json.loads((self.home / "auth.json").read_text())
        return [Account(data["identity"], data["identity"], data["identity"] + "@example.com", "plus", True)]


def seed(root, name):
    home = root / "profiles" / name
    atomic_json(home / "auth.json", {"identity": name, "test_only": True})
    atomic_json(home / "profile.json", {"schema_version": 1, "account": asdict(Account(name, name, name + "@example.com", "plus", True))})
    return home


class ProfileStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_binding_uses_git_root_from_subdirectories_and_resolves_symlinks(self):
        repo = self.root / "repo"
        (repo / ".git").mkdir(parents=True)
        sub = repo / "src"
        sub.mkdir()
        linked = self.root / "linked"
        try:
            linked.symlink_to(sub, target_is_directory=True)
        except OSError:
            linked = sub
        store = JsonProjects(self.root / "app", cwd=lambda: linked)
        store.bind("work")
        self.assertEqual(store.current(), str(repo.resolve()))
        self.assertEqual(JsonProjects(self.root / "app", cwd=lambda: repo).bound(), "work")
        if os.name != "nt":
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)
        self.assertFalse((repo / "projects.json").exists())
        store.unbind()
        self.assertIsNone(store.bound())

    def test_corrupt_bindings_are_not_overwritten(self):
        store = JsonProjects(self.root)
        store.path.write_text("{broken")
        with self.assertRaises(SwitchError): store.bind("work")
        self.assertEqual(store.path.read_text(), "{broken")

    def test_running_profile_status_uses_cache_without_touching_auth(self):
        home = seed(self.root, "work")
        home.joinpath("auth.json").write_text("updating")
        def forbidden(**kwargs): raise AssertionError("must not touch live auth")
        adapter = LocalProfiles(self.root, auth_factory=forbidden)
        with profile_lock(self.root / "profiles/.work.lock"):
            status = adapter.inspect("work", refresh=True)
            self.assertTrue(status.running)
            self.assertEqual(status.account.key, "work")
            with self.assertRaises(ProfileBusy): adapter.run("work", [])

    def test_corrupt_profile_does_not_hide_healthy_profiles(self):
        seed(self.root, "work")
        broken = seed(self.root, "personal")
        broken.joinpath("profile.json").write_text("{broken")
        adapter = LocalProfiles(self.root, auth_factory=LocalAuth)
        rows = [adapter.inspect(name) for name in adapter.names()]
        self.assertTrue(rows[0].problem)
        self.assertIsNone(rows[1].problem)

    def test_external_identity_change_prevents_launch(self):
        home = seed(self.root, "work")
        atomic_json(home / "auth.json", {"identity": "someone-else"})
        def forbidden(*a, **k): raise AssertionError("must not launch")
        adapter = LocalProfiles(self.root, runner=forbidden, auth_factory=LocalAuth)
        with self.assertRaises(SwitchError): adapter.run("work", [])

    def login_runner(self, identity, code=0):
        def runner(args, **kwargs):
            atomic_json(Path(kwargs["env"]["CODEX_HOME"]) / "auth.json", {"identity": identity})
            return SimpleNamespace(returncode=code)
        return runner

    def test_login_commits_complete_private_profile_without_touching_original_home(self):
        original = self.root / "original"
        atomic_json(original / "auth.json", {"original": True})
        adapter = LocalProfiles(self.root, self.login_runner("work"), LocalAuth, "/fake/codex")
        adapter.login("work")
        self.assertEqual(adapter.names(), ["work"])
        if os.name != "nt":
            self.assertEqual((adapter.home("work") / "auth.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads((original / "auth.json").read_text()), {"original": True})
        self.assertEqual(list(adapter.directory.glob(".login-*")), [])

    def test_cancelled_and_wrong_account_reauthentication_preserve_profile(self):
        home = seed(self.root, "work")
        history = home / "history.jsonl"
        history.write_text("keep history")
        before = (home / "auth.json").read_bytes()
        for who, code in (("work", 1), ("wrong", 0)):
            adapter = LocalProfiles(self.root, self.login_runner(who, code), LocalAuth, "/fake/codex")
            with self.assertRaises(SwitchError): adapter.login("work")
            self.assertEqual((home / "auth.json").read_bytes(), before)
            self.assertEqual(history.read_text(), "keep history")

    def test_reauthentication_preserves_history_and_rejects_duplicate_profile_identity(self):
        home = seed(self.root, "work")
        (home / "history.jsonl").write_text("keep")
        adapter = LocalProfiles(self.root, self.login_runner("work"), LocalAuth, "/fake/codex")
        adapter.login("work")
        self.assertEqual((home / "history.jsonl").read_text(), "keep")
        with self.assertRaises(SwitchError): adapter.login("duplicate")
        self.assertFalse(adapter.home("duplicate").exists())

    def test_parallel_processes_keep_separate_homes_and_hold_lifetime_locks(self):
        for name in ("work", "personal"): seed(self.root, name)
        fake = self.root / "codex.py"
        fake.write_text(f'''#!{sys.executable}
import os,time,json,sys
from pathlib import Path
if sys.argv[1:]==['--help']:
 print('Usage: codex --no-daemon');sys.exit(0)
home=Path(os.environ['CODEX_HOME'])
assert os.environ['CODEX_SQLITE_HOME']==str(home)
(home/'started').write_text(str(os.getpid()))
while not (home/'finish').exists(): time.sleep(0.02)
(home/'history.jsonl').write_text(home.name)
''')
        fake.chmod(0o755)
        worker = '''import sys
from pathlib import Path
from codex_switch.infrastructure.profiles import LocalProfiles
from tests.integration.test_profiles import LocalAuth
raise SystemExit(LocalProfiles(Path(sys.argv[1]),auth_factory=LocalAuth,codex_binary=sys.argv[2]).run(sys.argv[3],[]))'''
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[2] / "src") + os.pathsep + str(Path(__file__).parents[2])}
        procs = [subprocess.Popen([sys.executable, "-c", worker, str(self.root), str(fake), name], env=env) for name in ("work", "personal")]
        import time
        try:
            deadline = time.monotonic() + 10
            while not all((self.root / "profiles" / n / "started").exists() for n in ("work", "personal")):
                if time.monotonic() > deadline: self.fail("children did not start")
                time.sleep(0.02)
            adapter = LocalProfiles(self.root, auth_factory=LocalAuth)
            for name in ("work", "personal"):
                self.assertTrue(adapter.inspect(name).running)
            # Even losing a wrapper must not permit a competing writer.
            procs[0].kill()
            procs[0].wait(timeout=5)
            self.assertTrue(adapter.inspect("work").running)
        finally:
            for name in ("work", "personal"):
                (self.root / "profiles" / name / "finish").touch()
            for process in procs:
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
        deadline = time.monotonic() + 5
        while adapter.inspect("work").running and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(adapter.inspect("work").running)
        for name in ("work", "personal"):
            self.assertEqual((self.root / "profiles" / name / "history.jsonl").read_text(), name)

    def test_reauthentication_repairs_corrupt_metadata_without_losing_history(self):
        home = seed(self.root, "work")
        (home / "profile.json").write_text("{broken")
        (home / "history.jsonl").write_text("keep")
        adapter = LocalProfiles(self.root, self.login_runner("work"), LocalAuth, "/fake/codex")
        adapter.login("work")
        self.assertEqual(adapter.inspect("work").account.key, "work")
        self.assertEqual((home / "history.jsonl").read_text(), "keep")

    def test_human_name_survives_inspection_and_reauthentication(self):
        home = seed(self.root, "work")
        (home / "history.jsonl").write_text("keep")
        adapter = LocalProfiles(self.root, self.login_runner("work"), LocalAuth, "/fake/codex")
        adapter.rename("work", "Рабочий аккаунт")
        self.assertEqual(adapter.inspect("work").title, "Рабочий аккаунт")
        adapter.login("work")
        self.assertEqual(adapter.inspect("work").title, "Рабочий аккаунт")
        self.assertEqual((home / "history.jsonl").read_text(), "keep")
        self.assertEqual(adapter.names(), ["work"])

    def test_remove_only_deletes_selected_idle_account(self):
        seed(self.root, "work")
        personal = seed(self.root, "personal")
        adapter = LocalProfiles(self.root, auth_factory=LocalAuth)
        with profile_lock(self.root / "profiles/.work.lock"):
            with self.assertRaises(ProfileBusy): adapter.remove("work")
        adapter.remove("work")
        self.assertEqual(adapter.names(), ["personal"])
        self.assertTrue((personal / "auth.json").exists())

    def test_saving_unselected_vless_does_not_implicitly_enable_it_on_clean_install(self):
        from codex_switch.infrastructure.storage import JsonSettings, JsonServers
        from tests.unit.fakes import application
        from tests.unit.test_domain import LINK
        app, _ = application()
        app.servers = JsonServers(self.root / "app")
        app.settings = JsonSettings(self.root / "app", app.servers)
        previous = app.settings.load()
        app.add_server(LINK, select=False)
        self.assertEqual(app.settings.load(), previous)

    @unittest.skipUnless(os.environ.get("CODEX_SWITCH_TEST_CODEX_BINARY"), "Set CODEX_SWITCH_TEST_CODEX_BINARY for native child lock test")
    def test_native_codex_app_server_inherits_profile_lock(self):
        import signal
        import time
        seed(self.root, "work")
        marker = self.root / "child.pid"
        native = os.environ["CODEX_SWITCH_TEST_CODEX_BINARY"]
        worker = """import sys,subprocess
from pathlib import Path
from types import SimpleNamespace
from codex_switch.infrastructure.profiles import LocalProfiles
from tests.integration.test_profiles import LocalAuth
def runner(args, **kwargs):
    child=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**kwargs)
    Path(sys.argv[3]).write_text(str(child.pid))
    return SimpleNamespace(returncode=child.wait())
raise SystemExit(LocalProfiles(Path(sys.argv[1]),runner=runner,auth_factory=LocalAuth,codex_binary=sys.argv[2]).run('work',['app-server']))
"""
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[2] / "src") + os.pathsep + str(Path(__file__).parents[2])}
        parent = subprocess.Popen([sys.executable, "-c", worker, str(self.root), native, str(marker)], env=env, stdin=subprocess.PIPE)
        child_pid = None
        adapter = LocalProfiles(self.root, auth_factory=LocalAuth)
        try:
            deadline = time.monotonic() + 10
            while not marker.exists():
                if parent.poll() is not None or time.monotonic() > deadline:
                    self.fail("native child did not start")
                time.sleep(0.02)
            child_pid = int(marker.read_text())
            time.sleep(0.5)
            self.assertIsNone(parent.poll(), "native app-server exited before the test")
            parent.kill()
            parent.wait(timeout=5)
            self.assertTrue(psutil.pid_exists(child_pid))
            self.assertTrue(adapter.inspect("work").running)
        finally:
            if parent.poll() is None:
                parent.kill(); parent.wait(timeout=5)
            if parent.stdin: parent.stdin.close()
            if child_pid:
                try: psutil.Process(child_pid).terminate()
                except psutil.NoSuchProcess: pass
        deadline = time.monotonic() + 5
        while adapter.inspect("work").running and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(adapter.inspect("work").running)
