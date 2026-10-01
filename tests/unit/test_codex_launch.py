import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from codex_switch.domain.errors import SwitchError
from codex_switch.infrastructure.processes import CodexProcess, codex_launch_command, codex_supports_no_daemon, prepare_file_limit
from codex_switch.infrastructure.providers.codex import CodexProvider


class CodexLaunchTests(unittest.TestCase):
    def setUp(self):
        patcher = patch('codex_switch.infrastructure.processes.codex_supports_no_daemon', return_value=True)
        self.supports = patcher.start()
        self.addCleanup(patcher.stop)

    def test_older_codex_forces_embedded_server_with_file_credentials(self):
        self.supports.return_value = False
        command = codex_launch_command('/bin/codex', ['resume', 'session'])
        self.assertEqual(command, ['/bin/codex', '-c', 'cli_auth_credentials_store="file"', 'resume', 'session'])

    def test_original_account_launch_does_not_reuse_shared_server(self):
        runner = Mock(return_value=SimpleNamespace(returncode=7))
        with patch('codex_switch.infrastructure.processes.require_binary', return_value='/bin/codex'):
            self.assertEqual(CodexProcess(runner).run(['resume', 'session']), 7)
        self.assertEqual(runner.call_args.args[0], ['/bin/codex', '--no-daemon', 'resume', 'session'])

    def test_profile_launch_keeps_account_home_and_avoids_shared_server(self):
        provider = CodexProvider(binary='/bin/codex')
        home = Path('selected')
        command = provider.launch_command(home, ['resume', 'session'])
        self.assertEqual(command[:2], ['/bin/codex', '--no-daemon'])
        self.assertIn('cli_auth_credentials_store="file"', command)
        self.assertEqual(command[-2:], ['resume', 'session'])
        self.assertEqual(provider.environment(home)['CODEX_HOME'], str(home))

    def test_remote_override_cannot_bypass_selected_account(self):
        for args in (['--remote', 'unix://'], ['resume', '--remote=unix://']):
            with self.subTest(args=args), self.assertRaises(SwitchError):
                codex_launch_command('/bin/codex', args)
        self.assertEqual(codex_launch_command('/bin/codex', ['--', '--remote=example']),
                         ['/bin/codex', '--no-daemon', '--', '--remote=example'])

    @unittest.skipIf(os.name == 'nt', 'POSIX limits only')
    def test_file_limit_respects_hard_limit_and_never_lowers_existing_limit(self):
        import resource
        for soft, hard, target in ((256, resource.RLIM_INFINITY, 4096), (256, 1024, 1024),
                                   (8192, 16384, None), (resource.RLIM_INFINITY, resource.RLIM_INFINITY, None)):
            with self.subTest(soft=soft, hard=hard), \
                    patch('resource.getrlimit', return_value=(soft, hard)), patch('resource.setrlimit') as setter:
                prepare_file_limit()
                if target is None:
                    setter.assert_not_called()
                else:
                    setter.assert_called_once_with(resource.RLIMIT_NOFILE, (target, hard))

    @unittest.skipIf(os.name == 'nt', 'POSIX limits only')
    def test_file_limit_failure_does_not_block_launch(self):
        with patch('resource.getrlimit', return_value=(256, 4096)), \
                patch('resource.setrlimit', side_effect=OSError('denied')):
            prepare_file_limit()


class CodexCapabilitiesTests(unittest.TestCase):
    def test_help_selects_supported_launch_mode(self):
        for help_text, expected in [('Usage: codex --no-daemon', True), ('Usage: codex', False)]:
            with self.subTest(help=help_text), patch('pathlib.Path.is_file', return_value=True), \
                    patch('subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=help_text)) as runner:
                self.assertEqual(codex_supports_no_daemon.__wrapped__('/bin/codex'), expected)
                self.assertEqual(runner.call_args.args[0], ['/bin/codex', '--help'])

    def test_failed_probe_does_not_launch_with_uncertain_server_mode(self):
        with patch('pathlib.Path.is_file', return_value=True), \
                patch('subprocess.run', return_value=SimpleNamespace(returncode=1, stdout='')):
            with self.assertRaises(SwitchError): codex_supports_no_daemon.__wrapped__('/bin/codex')
