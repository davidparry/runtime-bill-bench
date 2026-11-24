"""Load-test every measured build at the same fixed rate, so no service runs flat out.

measure.py drives each service as hard as 64 connections can, which pegs Python's one worker while the others
have cores to spare. Here every service gets the same 2,000 orders a second over the same 64 connections.
"""
import json
import statistics

from . import config, llm, measure
from .langs import LANGS
from .proc import Server, free_port
from .single_worker import OneWorkerPython

RATE = 2_000
MEASURED = 40_000


def measured_builds(name: str) -> list:
    builds = []
    for result_path in sorted((config.RUNS_DIR / name).glob("seed*/result.json")):
        measure_path = result_path.parent / "measure.json"
        if not measure_path.exists():
            continue
        if json.loads(result_path.read_text())["passed"] or json.loads(measure_path.read_text()).get("salvaged"):
            builds.append(result_path.parent)
    builds += [path.parent for path in sorted((config.RUNS_DIR / name).glob("handfix-seed*/measure.json"))]
    return builds


def oha_at_rate(port: int, requests: int) -> dict:
    out = measure.run([
        config.OHA, "-n", str(requests), "-c", str(measure.CONCURRENCY), "-q", str(RATE), "-m", "POST",
        "-T", "application/json", "-d", json.dumps(measure.LOAD_BODY), "--no-tui", "--output-format", "json",
        f"http://127.0.0.1:{port}/orders",
    ], timeout=3600)
    return json.loads(out.stdout)


def trial(lang, run_dir) -> dict:
    project = run_dir / "project"
    port = free_port()
    env = lang.env() | {"PORT": str(port)}
    server = Server(lang.start_argv(project, run_dir / "artifacts", port, load=True), project, env, None, run_dir / "fixed-rate.err")
    server.start()
    try:
        if server.wait_healthy(port, 120) is None:
            return {"error": "the service did not become healthy"}
        measure.oha(port, measure.WARMUP)
        cpu_before, _ = measure.tree_usage(server.proc.pid)
        result = oha_at_rate(port, MEASURED)
        cpu_after, _ = measure.tree_usage(server.proc.pid)
    finally:
        server.terminate(10)
        server.close()
    return {
        "cpu_seconds_per_100k": round((cpu_after - cpu_before) * 100_000 / MEASURED, 3),
        "rps": round(result["summary"]["requestsPerSec"], 1),
        "p50_ms": round(result["latencyPercentiles"]["p50"] * 1000, 3),
        "p99_ms": round(result["latencyPercentiles"]["p99"] * 1000, 3),
        "success_rate": result["summary"]["successRate"],
    }


def main() -> None:
    llm.unload()
    out = {}
    for name in config.LANGS:
        lang = OneWorkerPython() if name == "python" else LANGS[name]
        runs = {}
        for run_dir in measured_builds(name):
            runs[run_dir.name] = trial(lang, run_dir)
            print(f"{name} {run_dir.name} at {RATE}/s: {runs[run_dir.name]}", flush=True)
        good = [r for r in runs.values() if "error" not in r]
        keys = ("cpu_seconds_per_100k", "rps", "p50_ms", "p99_ms")
        out[name] = {"runs": runs, "median": {k: round(statistics.median(r[k] for r in good), 3) for k in keys} if good else None}
    (config.RESULTS_DIR / "fixed-rate.json").write_text(json.dumps({"rate": RATE, "requests": MEASURED, "languages": out}, indent=2))
    for name, entry in out.items():
        print(f"{name}: {entry['median']}", flush=True)


if __name__ == "__main__":
    main()
