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
        "startup_ms": median([l["startup_ms"] for l in loads]),
        "idle_rss_mb": median([l["idle_rss_mb"] for l in loads]),
        "peak_rss_mb": median([l["peak_rss_mb"] for l in loads]),
        "cpu_seconds_per_100k": median([l["cpu_seconds_per_100k"] for l in loads]),
        "rps": median([l["rps"] for l in loads]),
        "p99_ms": median([l["p99_ms"] for l in loads]),
    }
    if summary["cpu_seconds_per_100k"] is not None:
        summary["cpu_dollars_per_million"] = round(cpu_dollars_per_million(summary["cpu_seconds_per_100k"]), 5)
    return summary


def break_even(lang: dict, baseline: dict) -> dict:
    extra_tokens = lang["token_dollars_per_working_service"] - baseline["token_dollars_per_working_service"]
    saved_per_request = (baseline["cpu_seconds_per_100k"] - lang["cpu_seconds_per_100k"]) / 100_000 / 3600 * config.FARGATE_VCPU_HOUR
    entry = {"extra_token_dollars": round(extra_tokens, 4), "cpu_dollars_saved_per_million": round(saved_per_request * 1e6, 5)}
    if extra_tokens <= 0:
        entry["requests_to_break_even"] = 0
    elif saved_per_request > 0:
        entry["requests_to_break_even"] = round(extra_tokens / saved_per_request)
    else:
        entry["requests_to_break_even"] = None
    return entry


def markdown(summaries: list[dict], even: dict) -> str:
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
        ("CPU-seconds per 100k orders", lambda s: fmt(s["cpu_seconds_per_100k"], 1)),
        ("Peak memory under load (MB)", lambda s: fmt(s["peak_rss_mb"])),
        ("Throughput (requests per second)", lambda s: fmt(s["rps"])),
        ("p99 latency (ms)", lambda s: fmt(s["p99_ms"], 1)),
        ("Compute cost per million orders (Fargate)", lambda s: f"${s['cpu_dollars_per_million']:.4f}" if s.get("cpu_dollars_per_million") is not None else "n/a"),
        ("Requests until it beats Python", lambda s: (
            "baseline" if s["lang"] == "python"
            else "n/a" if even.get(s["lang"], {}).get("requests_to_break_even") is None
            else f"{even[s['lang']]['requests_to_break_even']:,}"
        )),
    ]
    header = "| Measure | " + " | ".join(s["lang"].capitalize() for s in summaries) + " |"
    lines = [header, "|---|" + "---|" * len(summaries)]
    for label, cell in rows:
        lines.append(f"| {label} | " + " | ".join(cell(s) for s in summaries) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    summaries = [summarize_lang(name) for name in config.LANGS]
    by_name = {s["lang"]: s for s in summaries}
    baseline = by_name.get("python")
    even = {}
    if baseline and baseline["passed"] and baseline["cpu_seconds_per_100k"] is not None:
        for s in summaries:
            if s["lang"] != "python" and s["passed"] and s["cpu_seconds_per_100k"] is not None:
                even[s["lang"]] = break_even(s, baseline)
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
