"""PTY on macOS/Linux; native ConPTY on Windows. No terminal-app integration."""
import errno
import os
import select
import signal


class PosixPty:
    def __init__(self, command, env, rows, columns, *, pass_fds=(), **kwargs):
        import pty
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            try:
                for fd in pass_fds: os.set_inheritable(fd, True)
                self._resize(0, rows, columns)
                os.execvpe(command[0], command, env)
            except BaseException:
                os.write(2, b"RunLobby: could not start agent\r\n")
                os._exit(127)
        self.returncode = None

    @staticmethod
    def _resize(fd, rows, columns):
        import fcntl, struct, termios
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))

    def resize(self, rows, columns): self._resize(self.fd, rows, columns)

    def read(self, timeout=.02):
        if select.select([self.fd], [], [], timeout)[0]:
            try: return os.read(self.fd, 65536)
            except OSError as exc:
                if exc.errno == errno.EIO: return b""
                raise
        return b""

    def write(self, data):
        while data:
            try: size = os.write(self.fd, data)
            except OSError:
                if self.poll() is not None: return
                raise
            data = data[size:]

    def poll(self):
        if self.returncode is None:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid: self.returncode = os.waitstatus_to_exitcode(status)
        return self.returncode

    def close(self):
        import time
        if self.fd is None:
            return
        try: os.close(self.fd)
        except OSError: pass
        self.fd = None
        for sig, timeout in ((None, .2), (signal.SIGHUP, .5), (signal.SIGTERM, .5)):
            if self.poll() is not None:
                return
            if sig is not None:
                try: os.killpg(self.pid, sig)
                except ProcessLookupError: pass
            deadline = time.monotonic() + timeout
            while self.poll() is None and time.monotonic() < deadline: time.sleep(.01)
        if self.poll() is None:
            try: os.killpg(self.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            _, status = os.waitpid(self.pid, 0)
            self.returncode = os.waitstatus_to_exitcode(status)


class WindowsPty:
    def __init__(self, command, env, rows, columns, startupinfo=None, **kwargs):
        import codecs
        from winpty import PtyProcess
        from .windows import transfer_leases
        self.process = PtyProcess.spawn(command, env=env, dimensions=(rows, columns), backend="0")
        self.pid = self.process.pid
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        try:
            attributes = getattr(startupinfo, "lpAttributeList", None) or {}
            transfer_leases(self.pid, attributes.get("handle_list", []))
        except BaseException:
            self.process.close(force=True)
            raise

    def read(self, timeout=.02):
        if select.select([self.process.fileobj], [], [], timeout)[0]:
            try: return self.process.read(65536).encode("utf-8")
            except EOFError: return b""
        return b""

    def write(self, data):
        text = self.decoder.decode(data)
        if text: self.process.write(text)
    def resize(self, rows, columns): self.process.setwinsize(rows, columns)
    def poll(self): return None if self.process.isalive() else self.process.exitstatus or 0
    def close(self): self.process.close(force=True)


def spawn_terminal(command, env, rows, columns, **options):
    cls = WindowsPty if os.name == "nt" else PosixPty
    return cls(command, env, rows, columns, **options)


def read_input(timeout=.02):
    if os.name != "nt":
        import sys
        if select.select([sys.stdin.fileno()], [], [], timeout)[0]:
            return os.read(sys.stdin.fileno(), 65536)
        return b""
    import msvcrt, time
    deadline = time.monotonic() + timeout
    while not msvcrt.kbhit():
        if time.monotonic() >= deadline: return b""
        time.sleep(.005)
    result = ""
    while msvcrt.kbhit():
        key = msvcrt.getwch()
        if key in ("\x00", "\xe0"):
            key = {"H":"\x1b[A", "P":"\x1b[B", "K":"\x1b[D", "M":"\x1b[C",
                   "G":"\x1b[H", "O":"\x1b[F", "S":"\x1b[3~", "I":"\x1b[5~", "Q":"\x1b[6~",
                   "R":"\x1b[2~", ";":"\x1bOP", "<":"\x1bOQ", "=":"\x1bOR", ">":"\x1bOS",
                   "?":"\x1b[15~", "@":"\x1b[17~", "A":"\x1b[18~", "B":"\x1b[19~",
                   "C":"\x1b[20~", "D":"\x1b[21~", "\x85":"\x1b[23~", "\x86":"\x1b[24~",
                   "s":"\x1b[1;5D", "t":"\x1b[1;5C", "\x0f":"\x1b[Z"}.get(msvcrt.getwch(), "")
        result += key
    return result.encode("utf-16", errors="surrogatepass").decode("utf-16", errors="replace").encode("utf-8")
