import argparse
import json
import os
import signal
import subprocess
import time

from . import config
from .acceptance import Client, order
from .proc import free_port

ORDERS = 64


def wait_healthy(client: Client, deadline: float) -> None:
    while time.time() < deadline:
        try:
            if client.call("GET", "/health").status == 200:
                return
        except OSError:
            pass
        time.sleep(0.2)
    raise RuntimeError("the service never answered GET /health")


def trial(project, workers: int) -> dict:
    port = free_port()
    argv = [str(project / ".venv/bin/uvicorn"), "main:app", "--host", "127.0.0.1", "--port", str(port),
            "--no-access-log", "--workers", str(workers)]
    server = subprocess.Popen(argv, cwd=project, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              env=os.environ | {"PORT": str(port)}, start_new_session=True)
    try:
        client = Client(port)
        wait_healthy(client, time.time() + 60)
        ids = [client.call("POST", "/orders", order(customer=f"c-{i}")).body["id"] for i in range(ORDERS)]
        statuses = [client.call("GET", f"/orders/{oid}").status for oid in ids]
    finally:
        os.killpg(server.pid, signal.SIGTERM)
        server.wait(timeout=20)
    return {"workers": workers, "orders": ORDERS, "read_back": statuses.count(200), "not_found": statuses.count(404)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create orders, then read each back, with one uvicorn worker and with one per core.")
    parser.add_argument("--seed", type=int, default=2)
    args = parser.parse_args()
    project = config.RUNS_DIR / "python" / f"seed{args.seed}" / "project"
    results = [trial(project, 1), trial(project, os.cpu_count())]
    out = config.RESULTS_DIR / "python-workers.json"
    out.write_text(json.dumps({"seed": args.seed, "trials": results}, indent=2))
    for r in results:
        print(f"{r['workers']} worker(s): {r['read_back']} of {r['orders']} orders read back, {r['not_found']} returned 404")


if __name__ == "__main__":
    main()
