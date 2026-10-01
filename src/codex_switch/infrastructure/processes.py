import os
from functools import lru_cache
import shutil
import subprocess
import sys
from pathlib import Path

from codex_switch.domain.errors import MissingTool, SwitchError

PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "WS_PROXY", "WSS_PROXY")


def connection_environment(proxy: str | None, base: dict | None = None) -> dict:
    env = dict(os.environ if base is None else base)
    if proxy:
        for key in PROXY_KEYS:
            env[key] = env[key.lower()] = proxy
        env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost,::1,*.local"
        env["NODE_USE_ENV_PROXY"] = "1"
    from .tools import NativeTools
    node = NativeTools().installed("node")
    if node:
        env["CODEX_AUTH_NODE_EXECUTABLE"] = node
        env["PATH"] = str(Path(node).parent) + os.pathsep + env.get("PATH", "")
    return env


def binary_override(name: str) -> str | None:
    suffix = name.upper().replace("-", "_") + "_BINARY"
    return os.environ.get("RUNLOBBY_" + suffix) or os.environ.get("CODEX_LOBBY_" + suffix)


def require_binary(name: str) -> str:
    override = binary_override(name)
    if override:
        return str(Path(override).expanduser().resolve())
    # Release bundles keep native dependencies alongside the launcher. Native
    # binaries preserve inherited profile locks; npm shell shims need not do so.
    root = Path(sys.executable).parent if getattr(sys, "frozen", False) else None
    candidates = [root / "tools" / (name + (".exe" if os.name == "nt" else ""))] if root else []
    from .tools import NativeTools
    binary = next((str(p) for p in candidates if p.is_file()), None) or NativeTools().installed(name) or shutil.which(name)
    if not binary and name == "claude":
        candidate = Path.home() / ".local/bin" / ("claude.exe" if os.name == "nt" else "claude")
        binary = str(candidate) if candidate.is_file() else None
    if not binary:
        raise MissingTool(name)
    return binary


def command_for(binary, *args):
    binary = str(binary)
    if not binary.endswith(".py"):
        return [binary, *args]
    if not getattr(sys, "frozen", False):
        return [sys.executable, binary, *args]
    # In a standalone build sys.executable is RunLobby, not Python. Using it
    # for a configured .py tool recursively launches another account picker.
    if os.name != "nt" and os.access(binary, os.X_OK):
        return [binary, *args]  # Respect the script's own shebang/interpreter.
    for name in ("python3", "python"):
        interpreter = shutil.which(name)
        if interpreter and Path(interpreter).resolve() != Path(sys.executable).resolve():
            return [interpreter, binary, *args]
    raise SwitchError("This configured .py tool needs Python. Install Python or select a native executable.")


@lru_cache(maxsize=16)
def codex_supports_no_daemon(binary):
    if not Path(binary).is_file():
        return False
    try:
        result = subprocess.run(command_for(binary, "--help"), stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        raise SwitchError("Could not check Codex launch options. Check the installation: runlobby doctor") from None
    if result.returncode:
        raise SwitchError("Could not check Codex launch options. Check the installation: runlobby doctor")
    return "--no-daemon" in result.stdout


def codex_launch_command(binary, args):
    # A shared server retains its own account and MCP processes after TUI exit.
    for arg in args:
        if arg == "--":
            break
        if arg == "--remote" or arg.startswith("--remote="):
            raise SwitchError("Remote Codex servers cannot use the selected account. Launch remote Codex directly.")
    if codex_supports_no_daemon(binary):
        return command_for(binary, "--no-daemon", *args)
    # Older Codex embeds its server whenever CLI config overrides are present.
    return command_for(binary, "-c", 'cli_auth_credentials_store="file"', *args)


def prepare_file_limit():
    if os.name == "nt":
        return
    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    target = 4096 if hard == resource.RLIM_INFINITY else min(4096, hard)
    if soft != resource.RLIM_INFINITY and soft < target:
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
        except (OSError, ValueError):
            pass  # Keep working under an administrator-imposed limit.


class CodexProcess:
    def __init__(self, runner=subprocess.run):
        self.runner = runner

    def run(self, args: list[str], *, proxy: str | None = None) -> int:
        try:
            result = self.runner(codex_launch_command(require_binary("codex"), args), env=connection_environment(proxy))
            return result.returncode
        except KeyboardInterrupt:
            return 130


class ProcessDiagnostics:
    def dependencies(self) -> dict[str, str]:
        found = {}
        for name in ("codex", "codex-auth", "claude", "xray"):
            try:
                found[name] = require_binary(name)
            except SwitchError:
                found[name] = "Not installed (optional until used)"
        return found


def profile_environment(home, proxy: str | None, base: dict | None = None) -> dict:
    env = connection_environment(proxy, base)
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "CODEX_SQLITE_HOME"):
        env.pop(key, None)
    env["CODEX_HOME"] = str(home)
    env["CODEX_SQLITE_HOME"] = str(home)
    return env
