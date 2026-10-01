from codex_switch.domain.errors import SwitchError
from codex_switch.domain.profiles import validate_profile_arguments
from codex_switch.domain.providers import CODEX
from ..accounts import CodexAuth
from ..processes import codex_launch_command, command_for, profile_environment, require_binary


class CodexProvider:
    info = CODEX

    def __init__(self, auth_factory=CodexAuth, binary=None):
        self.auth_factory, self.binary = auth_factory, binary

    def environment(self, home, proxy=None):
        return profile_environment(home, proxy)

    def current(self, home, *, refresh=False, proxy=None):
        if not (home / "auth.json").is_file():
            raise SwitchError("Sign-in is missing. Choose Sign in again.")
        accounts = self.auth_factory(home=home).list(refresh=refresh, proxy=proxy)
        account = next((a for a in accounts if a.active), None)
        if account is None:
            raise SwitchError("No active ChatGPT account. Choose Sign in again.")
        return account

    def login_command(self, home):
        return command_for(self.binary or require_binary("codex"), "-c", 'cli_auth_credentials_store="file"',
                           "-c", 'forced_login_method="chatgpt"', "login")

    def launch_command(self, home, args):
        return codex_launch_command(self.binary or require_binary("codex"),
                                    ["-c", 'cli_auth_credentials_store="file"',
                                     "-c", 'forced_login_method="chatgpt"', "-c", 'model_provider="openai"', *args])

    def validate_arguments(self, args):
        validate_profile_arguments(args)

    def resume_arguments(self):
        return ["resume"]

    def preserve_history(self, previous, destination):
        pass  # Codex reauthentication replaces auth.json in the same home.

    def forget(self, home):
        pass  # File-backed credentials are removed with the profile directory.
