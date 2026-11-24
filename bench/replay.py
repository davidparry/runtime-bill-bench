"""Replay the Rust runs where the feedback limit hid compiler errors, sending whole logs instead.

The repair loop sends the last 150 lines (12,000 characters) of a failed step. rustc prints its errors in order
with no summary at the end, so a long log loses its first errors; Maven and pytest end with a summary, and no Go
log reached the limit. Each replay keeps the model's real replies through the first round that lost an error,
sends that round's whole log, and runs the rounds that remain with whole logs.
"""
import json
import re
import shutil
import time
from pathlib import Path

from . import config, llm
from .files import parse_files, write_files
from .generate import FORMAT_HELP, accept, feedback
from .langs import LANGS, Lang
from .proc import run_step, tail

RUST_ERROR = re.compile(r"^error(?:\[E\d{4}\])?: (?!could not compile|aborting)", re.M)
REPLAY_DIR = config.RUNS_DIR / "rust-replay"


def error_count(text: str) -> int:
    return len(RUST_ERROR.findall(text))


def failed_log(run_dir: Path, number: int) -> Path:
    return sorted(run_dir.glob(f"round{number}.build*.log"))[-1]


def first_hidden_round(run_dir: Path, result: dict) -> int | None:
    for record in result["round_records"]:
        if record.get("failed_step") in ("cargo build --release", "cargo test --release"):
            log = failed_log(run_dir, record["round"])
            if error_count(tail(log)) < error_count(log.read_text(errors="replace")):
                return record["round"]
    return None


def whole_log_failure(display: str, what: str, log_path: Path) -> tuple[str, str]:
    return display, f"`{display}` {what}. Its output:\n```\n{log_path.read_text(errors='replace')}\n```"


def build(lang: Lang, project: Path, artifacts: Path, run_dir: Path, number: int, written: set[str]):
    lang.clean(project, artifacts)
    env = lang.env()
    for index, step in enumerate(lang.build_steps(project), 1):
        log_path = run_dir / f"round{number}.build{index}.log"
        code = run_step(step.argv, project, env, step.timeout, log_path)
        if code != 0:
            return whole_log_failure(step.display, "timed out" if code is None else f"exited with status {code}", log_path)
    error = lang.post_build(project, artifacts)
    if error:
        return "post-build", error
    if not lang.has_tests(project, written):
        return "post-build", "The spec asks for unit tests for the validation rules and the 404 case, and the project has no tests."
    return None


def replay(run_dir: Path) -> dict | None:
    lang = LANGS["rust"]
    result = json.loads((run_dir / "result.json").read_text())
    hidden = first_hidden_round(run_dir, result)
    if hidden is None:
        return None
    original = json.loads((run_dir / "conversation.json").read_text())
    out = REPLAY_DIR / run_dir.name
    shutil.rmtree(out, ignore_errors=True)
    project, artifacts = out / "project", out / "artifacts"
    project.mkdir(parents=True)
    written: set[str] = set()
    for number in range(1, hidden + 1):
        files = parse_files(original[2 * number]["content"])
        write_files(project, files)
        written |= set(files)
    kept = result["round_records"][hidden - 1]
    what = re.match(r"`[^`]+` (exited with status \d+|timed out)", kept["failure"]).group(1)
    step, detail = whole_log_failure(kept["failed_step"], what, failed_log(run_dir, hidden))
    messages = original[: 2 * hidden + 1]
    messages.append({"role": "user", "content": feedback(step, detail, kept.get("done_reason") == "length")})
    rounds = result["round_records"][:hidden]
    passed = False
    for number in range(hidden + 1, config.MAX_REPAIRS + 2):
        reply, meta = llm.chat(messages, result["seed"])
        (out / f"round{number}.reply.md").write_text(reply)
        messages.append({"role": "assistant", "content": reply})
        files = parse_files(reply)
        write_files(project, files)
        written |= set(files)
        record = {"round": number, **meta, "files": sorted(files)}
        if not files:
            failure = ("format", f"Your reply contained no files in the required format. {FORMAT_HELP}")
        else:
            failure = build(lang, project, artifacts, out, number, written)
            if failure is None:
                failure = accept(lang, project, artifacts, out, number, record)
        record["failed_step"] = failure[0] if failure else None
        record["failure"] = failure[1][:6000] if failure else None
        rounds.append(record)
        status = "PASS" if failure is None else f"fail at {failure[0]}"
        print(
            f"{time.strftime('%H:%M:%S')} rust {run_dir.name} replay round{number}: "
            f"in={meta['prompt_eval_count']} out={meta['eval_count']} {status}",
            flush=True,
        )
        if failure is None:
            passed = True
            break
        messages.append({"role": "user", "content": feedback(*failure, meta.get("done_reason") == "length")})
    outcome = {
        "lang": "rust",
        "seed": result["seed"],
        "model": config.MODEL,
        "replayed_from": f"runs/rust/{run_dir.name}",
        "whole_logs_from_round": hidden,
        "passed": passed,
        "rounds": len(rounds),
        "input_tokens": sum(r["prompt_eval_count"] or 0 for r in rounds),
        "output_tokens": sum(r["eval_count"] or 0 for r in rounds),
        "files": sorted(written),
        "round_records": rounds,
    }
    (out / "result.json").write_text(json.dumps(outcome, indent=2))
    (out / "conversation.json").write_text(json.dumps(messages, indent=2))
    return outcome


def main() -> None:
    for result_path in sorted((config.RUNS_DIR / "rust").glob("seed*/result.json")):
        outcome = replay(result_path.parent)
        if outcome is None:
            print(f"rust {result_path.parent.name}: every round showed all of its compiler errors; nothing to replay", flush=True)
            continue
        print(
            f"== rust {result_path.parent.name} with whole logs from round {outcome['whole_logs_from_round']}: "
            f"{'PASSED' if outcome['passed'] else 'FAILED'} after {outcome['rounds']} rounds",
            flush=True,
        )


if __name__ == "__main__":
    main()
