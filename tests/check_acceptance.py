"""Run the acceptance suite against the reference server; it should report no failures."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bench import acceptance  # noqa: E402
from bench.proc import Server, free_port  # noqa: E402


def main() -> int:
    port = free_port()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "server.out"
        server = Server(
            [sys.executable, str(Path(__file__).with_name("reference_server.py"))],
            Path(tmp), dict(os.environ, PORT=str(port)), out, Path(tmp) / "server.err",
        )
        server.start()
        try:
            if server.wait_healthy(port, 30) is None:
                print("reference server never became healthy")
                return 1
            client = acceptance.Client(port)
            failures = acceptance.run_checks(client)
            failures += acceptance.shutdown_problems(*server.terminate(10))
            failures += acceptance.log_problems(out, client.sent)
        finally:
            server.close()
    for failure in failures:
        print(failure)
    print(f"{client.sent} requests, {len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
