import http.client
import os
import signal
import socket
import subprocess
import time
from pathlib import Path


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def tail(path: Path, lines: int = 150, chars: int = 12000) -> str:
    try:
        text = path.read_text(errors="replace")
    except FileNotFoundError:
        return ""
    return "\n".join(text.splitlines()[-lines:])[-chars:]


def run_step(argv: list[str], cwd: Path, env: dict, timeout: int, log_path: Path) -> int | None:
    with open(log_path, "wb") as log:
        try:
            proc = subprocess.Popen(
                argv, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
            )
        except OSError as exc:
            log.write(f"could not start {argv[0]}: {exc}\n".encode())
            return 127
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            return None


def get_status(port: int, path: str, timeout: float = 1.0) -> int | None:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", path, headers={"Accept": "application/json"})
        response = conn.getresponse()
        response.read()
        return response.status
    except (OSError, http.client.HTTPException):
        return None
    finally:
        conn.close()


class Server:
    def __init__(self, argv: list[str], cwd: Path, env: dict, stdout: Path | None, stderr: Path | None):
        self.argv, self.cwd, self.env = argv, cwd, env
        self.stdout_path, self.stderr_path = stdout, stderr
        self.proc: subprocess.Popen | None = None
        self._files = []

    def _open(self, path: Path | None):
        if path is None:
            return subprocess.DEVNULL
        handle = open(path, "wb")
        self._files.append(handle)
        return handle

    def start(self) -> None:
        out, err = self._open(self.stdout_path), self._open(self.stderr_path)
        self.started = time.perf_counter()
        self.proc = subprocess.Popen(
            self.argv, cwd=self.cwd, env=self.env, stdout=out, stderr=err, start_new_session=True
        )

    def wait_healthy(self, port: int, timeout: float) -> float | None:
        deadline = self.started + timeout
        while time.perf_counter() < deadline:
            if self.proc.poll() is not None:
                return None
            if get_status(port, "/health") == 200:
                return time.perf_counter() - self.started
            time.sleep(0.02)
        return None

    def terminate(self, grace: float = 10.0) -> tuple[bool, int | None]:
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                return False, None
        return True, self.proc.returncode

    def close(self) -> None:
        if self.proc is not None:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            self.proc.wait()
        for handle in self._files:
            handle.close()
        self._files.clear()
