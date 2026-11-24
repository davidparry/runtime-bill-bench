import json
import statistics
from collections import Counter

from . import config


def median(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 3) if values else None


def fmt(value, digits: int = 0) -> str:
    return "n/a" if value is None else f"{value:,.{digits}f}"


def token_dollars(input_tokens: int, output_tokens: int) -> float:
    return input_tokens / 1e6 * config.OPUS_INPUT_PER_M + output_tokens / 1e6 * config.OPUS_OUTPUT_PER_M


def cpu_dollars_per_million(cpu_seconds_per_100k: float) -> float:
    return cpu_seconds_per_100k * 10 / 3600 * config.FARGATE_VCPU_HOUR


def python_one_worker_loads() -> list[dict]:
    path = config.RESULTS_DIR / "python-one-worker.json"
    if not path.exists():
        return []
    return [run["load"] for run in json.loads(path.read_text()).values() if "error" not in run["load"]]


def load_medians(loads: list[dict]) -> dict:
    keys = ("startup_ms", "idle_rss_mb", "peak_rss_mb", "cpu_seconds_per_100k", "rps", "p99_ms")
    return {key: median([l[key] for l in loads]) for key in keys}


def fixed_rate() -> dict:
    path = config.RESULTS_DIR / "fixed-rate.json"
    return json.loads(path.read_text()) if path.exists() else {"rate": None, "languages": {}}


def summarize_lang(name: str) -> dict:
    results, measures = [], []
    for result_path in sorted((config.RUNS_DIR / name).glob("seed*/result.json")):
        result = json.loads(result_path.read_text())
        results.append(result)
        measure_path = result_path.parent / "measure.json"
        if measure_path.exists():
            measured = json.loads(measure_path.read_text())
            if result["passed"] or measured.get("salvaged"):
                measures.append(measured)
    for measure_path in sorted((config.RUNS_DIR / name).glob("handfix-seed*/measure.json")):
        measures.append(json.loads(measure_path.read_text()))
    passing = [r for r in results if r["passed"]]
    all_in = sum(r["input_tokens"] for r in results)
    all_out = sum(r["output_tokens"] for r in results)
    vulns = [v for m in measures for v in m["vulnerabilities"]]
    distinct = {(v["id"], v["package"]) for v in vulns}
    severities = Counter(sev for (vid, pkg), sev in {(v["id"], v["package"]): v["severity"] for v in vulns}.items())
    loads = [m["load"] for m in measures if "load" in m and "error" not in m["load"]]
    sixteen_workers = None
    if name == "python" and python_one_worker_loads():
        # measure.py ran Python's load test with one worker per core, which splits the in-memory store and fails the spec.
        sixteen_workers, loads = load_medians(loads), python_one_worker_loads()
    summary = {
        "lang": name,
        "runs": len(results),
        "passed": len(passing),
        "rounds": [r["rounds"] for r in passing],
        "first_try": sum(1 for r in passing if r["rounds"] == 1),
        "measured_builds": len(measures),
        "salvaged_builds": sum(1 for m in measures if m.get("salvaged")),
        "hand_fixed_builds": [m["hand_fixed"] | {"seed": m["seed"]} for m in measures if m.get("hand_fixed")],
        "median_input_tokens": median([r["input_tokens"] for r in passing]),
        "median_output_tokens": median([r["output_tokens"] for r in passing]),
        "all_input_tokens": all_in,
        "all_output_tokens": all_out,
        "output_tokens_per_working_service": round(all_out / len(passing)) if passing else None,
        "token_dollars_per_working_service": round(token_dollars(all_in, all_out) / len(passing), 4) if passing else None,
        "loc_source": median([m["loc"]["source"] for m in measures]),
        "loc_test": median([m["loc"]["test"] for m in measures]),
        "loc_total": median([m["loc"]["total"] for m in measures]),
        "runtime_deps": median([len(m["runtime_deps"]) for m in measures]),
        "vulns_per_build": median([len(m["vulnerabilities"]) for m in measures]),
        "builds_with_vulns": sum(1 for m in measures if m["vulnerabilities"]),
        "distinct_vulns": len(distinct),
        "distinct_vulns_by_severity": dict(severities),
        "vulns_with_fix": len({(v["id"], v["package"]) for v in vulns if v.get("fixed")}),
        "pins": [m["pins"] for m in measures],
        **load_medians(loads),
    }
    if sixteen_workers:
        summary["load_workers"] = 1
        summary["sixteen_workers"] = sixteen_workers
    steady = (fixed_rate()["languages"].get(name) or {}).get("median") or {}
    summary["fixed_rate_cpu_seconds_per_100k"] = steady.get("cpu_seconds_per_100k")
    summary["fixed_rate_p99_ms"] = steady.get("p99_ms")
    if summary["cpu_seconds_per_100k"] is not None:
        summary["cpu_dollars_per_million"] = round(cpu_dollars_per_million(summary["cpu_seconds_per_100k"]), 5)
    return summary


def break_even(lang: dict, baseline: dict, cpu_key: str) -> dict:
    extra_tokens = lang["token_dollars_per_working_service"] - baseline["token_dollars_per_working_service"]
    saved_per_request = (baseline[cpu_key] - lang[cpu_key]) / 100_000 / 3600 * config.FARGATE_VCPU_HOUR
    entry = {"extra_token_dollars": round(extra_tokens, 4), "cpu_dollars_saved_per_million": round(saved_per_request * 1e6, 5)}
    if extra_tokens <= 0:
        entry["requests_to_break_even"] = 0
    elif saved_per_request > 0:
        entry["requests_to_break_even"] = round(extra_tokens / saved_per_request)
    else:
        entry["requests_to_break_even"] = None
    return entry


def beats_python(s: dict, even: dict) -> str:
    if s["lang"] == "python":
        return "baseline"
    requests = even.get(s["lang"], {}).get("requests_to_break_even")
    return "n/a" if requests is None else f"{requests:,}"


def markdown(summaries: list[dict], even: dict) -> str:
    rate = fixed_rate()["rate"]
    steady = f"at {rate:,} a second" if rate else "at a fixed rate"
    rows = [
        ("Passed (of runs)", lambda s: f"{s['passed']} of {s['runs']}"),
        ("Passed on the first try", lambda s: str(s["first_try"])),
        ("Builds measured", lambda s: f"{s['measured_builds']}"
            + (f" ({s['salvaged_builds']} salvaged)" if s["salvaged_builds"] else "")
            + (f" ({len(s['hand_fixed_builds'])} hand-fixed)" if s["hand_fixed_builds"] else "")),
        ("Token cost of all runs (Opus 5.5 rates)", lambda s: f"${token_dollars(s['all_input_tokens'], s['all_output_tokens']):.2f}"),
        ("Output tokens per working service", lambda s: fmt(s["output_tokens_per_working_service"])),
        ("Token cost per working service (Opus 5.5 rates)", lambda s: "n/a" if s["token_dollars_per_working_service"] is None else f"${s['token_dollars_per_working_service']:.2f}"),
        ("Lines of code the model wrote", lambda s: fmt(s["loc_total"])),
        ("Runtime dependencies", lambda s: fmt(s["runtime_deps"])),
        ("Known vulnerabilities per build (median)", lambda s: fmt(s["vulns_per_build"])),
        ("Startup to first healthy response (ms)", lambda s: fmt(s["startup_ms"])),
        ("CPU-seconds per 100k orders, flat out", lambda s: fmt(s["cpu_seconds_per_100k"], 1)),
        (f"CPU-seconds per 100k orders {steady}", lambda s: fmt(s["fixed_rate_cpu_seconds_per_100k"], 1)),
        ("Peak memory under load (MB)", lambda s: fmt(s["peak_rss_mb"])),
        ("Throughput, flat out (requests per second)", lambda s: fmt(s["rps"])),
        ("p99 latency, flat out (ms)", lambda s: fmt(s["p99_ms"], 1)),
        (f"p99 latency {steady} (ms)", lambda s: fmt(s["fixed_rate_p99_ms"], 1)),
        ("Compute cost per million orders, flat out (Fargate)", lambda s: f"${s['cpu_dollars_per_million']:.4f}" if s.get("cpu_dollars_per_million") is not None else "n/a"),
        ("Requests until it beats Python, flat out", lambda s: beats_python(s, even["cpu_seconds_per_100k"])),
        (f"Requests until it beats Python {steady}", lambda s: beats_python(s, even["fixed_rate_cpu_seconds_per_100k"])),
    ]
    header = "| Measure | " + " | ".join(s["lang"].capitalize() for s in summaries) + " |"
    lines = [header, "|---|" + "---|" * len(summaries)]
    for label, cell in rows:
        lines.append(f"| {label} | " + " | ".join(cell(s) for s in summaries) + " |")
    for s in summaries:
        if s.get("sixteen_workers"):
            w = s["sixteen_workers"]
            lines += [
                "",
                f"{s['lang'].capitalize()}'s load numbers come from one uvicorn worker, the command its stack contract gives and the "
                "acceptance test ran (`bench/single_worker.py`). With one worker per core it split its in-memory store "
                f"(`results/python-workers.json`) and used {fmt(w['cpu_seconds_per_100k'], 1)} CPU-seconds per 100k orders, "
                f"{fmt(w['peak_rss_mb'])} MB at peak, and {fmt(w['rps'])} requests per second.",
            ]
    return "\n".join(lines) + "\n"


def main() -> None:
    summaries = [summarize_lang(name) for name in config.LANGS]
    by_name = {s["lang"]: s for s in summaries}
    baseline = by_name.get("python")
    even = {}
    for cpu_key in ("cpu_seconds_per_100k", "fixed_rate_cpu_seconds_per_100k"):
        even[cpu_key] = {}
        if baseline and baseline["passed"] and baseline[cpu_key] is not None:
            for s in summaries:
                if s["lang"] != "python" and s["passed"] and s[cpu_key] is not None:
                    even[cpu_key][s["lang"]] = break_even(s, baseline, cpu_key)
    out = {"model": config.MODEL, "languages": summaries, "break_even_vs_python": even,
           "prices": {"fargate_vcpu_hour": config.FARGATE_VCPU_HOUR, "fargate_gb_hour": config.FARGATE_GB_HOUR,
                      "opus_input_per_m": config.OPUS_INPUT_PER_M, "opus_output_per_m": config.OPUS_OUTPUT_PER_M}}
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / "summary.json").write_text(json.dumps(out, indent=2))
    (config.RESULTS_DIR / "summary.md").write_text(markdown(summaries, even))
    print(markdown(summaries, even))
    print(json.dumps(even, indent=2))


if __name__ == "__main__":
    main()
