import json

from . import config, llm, measure
from .langs import Python


class OneWorkerPython(Python):
    """Load-tests Python the way the stack contract starts it: one uvicorn worker, the only setup that passes the spec."""

    def start_argv(self, project, artifacts, port, load):
        return super().start_argv(project, artifacts, port, load=False)


def main() -> None:
    llm.unload()
    lang = OneWorkerPython()
    out = {}
    for result_path in sorted((config.RUNS_DIR / "python").glob("seed*/result.json")):
        result = json.loads(result_path.read_text())
        if not result["passed"]:
            continue
        run_dir = result_path.parent
        trials = [measure.load_trial(lang, run_dir / "project", run_dir, f"-one-worker{i}") for i in range(1, measure.TRIALS + 1)]
        out[run_dir.name] = {"trials": trials, "load": measure.median_trial(trials)}
        load = out[run_dir.name]["load"]
        print(f"python {run_dir.name} one worker: cpu/100k={load.get('cpu_seconds_per_100k')}s, "
              f"peak={load.get('peak_rss_mb')}MB, rps={load.get('rps')}, p99={load.get('p99_ms')}ms", flush=True)
    (config.RESULTS_DIR / "python-one-worker.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
