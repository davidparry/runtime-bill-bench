import json
import re
import statistics
import subprocess
from collections import Counter
from pathlib import Path

from . import config
from .langs import LANGS
from .proc import tail
from .replay import REPLAY_DIR, error_count

# The header each tool prints before its closing list of failures. A tail that holds the header holds the whole list.
CLOSING_SUMMARY = {
    "java": ("[INFO] Results:", "COMPILATION ERROR"),
    "python": ("short test summary info",),
}
COMMENT = {
    "python": re.compile(r"^\s*#"),
    "go": re.compile(r"^\s*(?://|/\*|\*)"),
    "java": re.compile(r"^\s*(?://|/\*|\*)"),
    "rust": re.compile(r"^\s*(?://|/\*|\*)"),
}
RUST_ERROR = re.compile(r"error\[(E\d{4})\]")


def median(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 1) if values else None


def test_cases_run(lang, run_dir: Path, result: dict) -> int | None:
    """Test cases the passing round ran, counting each table row, subtest, or parametrized case once."""
    if lang.name == "go":
        out = subprocess.run(
            [config.GO, "test", "-v", "-count=1", "./..."], cwd=run_dir / "project", env=lang.env(), capture_output=True, text=True
        ).stdout
        names = re.findall(r"^\s*--- PASS: (\S+)", out, re.M)
        parents = {name.rsplit("/", 1)[0] for name in names if "/" in name}
        return sum(1 for name in names if name not in parents)
    log = sorted(run_dir.glob(f"round{result['rounds']}.build*.log"))[-1].read_text(errors="replace")
    if lang.name == "python":
        match = re.search(r"(\d+) passed", log)
        return int(match.group(1)) if match else None
    if lang.name == "java":
        totals = re.findall(r"^\[INFO\] Tests run: (\d+), Failures: 0, Errors: 0, Skipped: \d+$", log, re.M)
        return int(totals[-1]) if totals else None
    return None


def project_stats(lang, run_dir: Path, result: dict) -> dict:
    project = run_dir / "project"
    comments = code = 0
    for rel in result["files"]:
        path = project / rel
        if not path.is_file() or lang.categorize(rel) not in ("source", "test"):
            continue
        for line in path.read_text(errors="replace").splitlines():
            if not line.strip():
                continue
            if COMMENT[lang.name].match(line):
                comments += 1
            else:
                code += 1
    return {"test_cases_run": test_cases_run(lang, run_dir, result), "comment_lines": comments, "code_lines": code}


def feedback_audit(name: str, run_dirs: list[Path], results: list[dict]) -> dict:
    """How much of each failed build or test log fit in the 150-line, 12,000-character tail sent back to the model."""
    failed = over = kept = 0
    seen = total = hid = 0
    for run_dir, result in zip(run_dirs, results):
        for record in result["round_records"]:
            if record.get("failed_step") in (None, "acceptance", "format", "post-build"):
                continue
            failed += 1
            log = sorted(run_dir.glob(f"round{record['round']}.build*.log"))[-1]
            text = log.read_text(errors="replace")
            if len(text.splitlines()) <= 150 and len(text) <= 12000:
                continue
            over += 1
            sent = tail(log)
            if name == "rust":
                if error_count(sent) < error_count(text):
                    hid += 1
                    seen += error_count(sent)
                    total += error_count(text)
            elif any(mark in sent for mark in CLOSING_SUMMARY.get(name, ())):
                kept += 1
            else:
                hid += 1
    out = {"failed_build_or_test_rounds": failed, "logs_over_the_limit": over, "rounds_where_the_tail_hid_errors": hid}
    if name == "rust":
        out["errors_seen_in_those_rounds"] = seen
        out["errors_in_those_rounds"] = total
    else:
        out["cut_logs_that_kept_the_closing_summary"] = kept
    return out


def audit_lang(name: str) -> dict:
    lang = LANGS[name]
    paths = sorted((config.RUNS_DIR / name).glob("seed*/result.json"))
    results = [json.loads(p.read_text()) for p in paths]
    rounds = [h for r in results for h in r["round_records"]]
    passing = [r for r in results if r["passed"]]
    failures = [h.get("failure") or "" for h in rounds]
    stats = [project_stats(lang, path.parent, r) for path, r in zip(paths, results) if r["passed"]]
    summary = {
        "runs": len(results),
        "passed": len(passing),
        "first_try": sum(1 for r in passing if r["rounds"] == 1),
        "rounds_all_runs": len(rounds),
        "rounds_per_passing_run": median([r["rounds"] for r in passing]),
        "output_tokens_first_round": median([r["round_records"][0]["eval_count"] for r in results]),
        "output_tokens_per_round": median([h["eval_count"] for h in rounds]),
        "input_tokens_per_round": median([h["prompt_eval_count"] for h in rounds]),
        "output_tokens_all_runs": sum(h["eval_count"] for h in rounds),
        "input_tokens_all_runs": sum(h["prompt_eval_count"] for h in rounds),
        "truncated_replies": sum(1 for h in rounds if h.get("done_reason") == "length"),
        "step_timeouts": sum(1 for f in failures if "` timed out." in f),
        "health_timeouts": sum(1 for f in failures if "did not answer GET /health" in f),
        "failed_steps": dict(Counter(h.get("failed_step") or "passed" for h in rounds)),
        "final_failed_step": dict(Counter(r["round_records"][-1].get("failed_step") for r in results if not r["passed"])),
        "feedback": feedback_audit(name, [p.parent for p in paths], results),
        "passing_builds": {
            "test_cases_run": median([s["test_cases_run"] for s in stats]),
            "comment_lines": median([s["comment_lines"] for s in stats]),
            "code_lines": median([s["code_lines"] for s in stats]),
        },
    }
    if name == "rust":
        build_fail = [h["failure"] for h in rounds if h.get("failed_step") == "cargo build --release"]
        test_fail = [h["failure"] for h in rounds if h.get("failed_step") == "cargo test --release"]
        summary["rust"] = {
            "compile_error_codes": dict(Counter(code for f in build_fail for code in set(RUST_ERROR.findall(f))).most_common(8)),
            "test_rounds_needing_a_live_server": sum(1 for f in test_fail if "Connection refused" in f or "ConnectionRefused" in f),
            "test_rounds_that_did_not_compile": sum(1 for f in test_fail if RUST_ERROR.search(f)),
            "test_rounds": len(test_fail),
            "salvage": {},
        }
        for path in sorted((config.RUNS_DIR / name).glob("seed*/salvage.json")):
            s = json.loads(path.read_text())
            summary["rust"]["salvage"][path.parent.name] = {
                "service_passed": s["service_passed"],
                "failed_step": s["failed_step"],
                "acceptance_failures": s.get("acceptance_failures"),
            }
        summary["rust"]["replay_with_whole_logs"] = {
            path.parent.name: {
                "whole_logs_from_round": r["whole_logs_from_round"],
                "passed": r["passed"],
                "rounds": r["rounds"],
                "final_failed_step": r["round_records"][-1].get("failed_step"),
            }
            for path in sorted(REPLAY_DIR.glob("seed*/result.json"))
            for r in [json.loads(path.read_text())]
        }
    return summary


def main() -> None:
    out = {name: audit_lang(name) for name in config.LANGS}
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / "audit.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
