import argparse
import json
import shutil
import time
from pathlib import Path

from . import acceptance, config, llm
from .files import parse_files, write_files
from .langs import LANGS, Lang
from .proc import Server, free_port, run_step, tail

FORMAT_HELP = "Return each file as a line `FILE: <relative path>` followed by a fenced code block with its complete contents."


def build_prompt(lang: Lang) -> str:
    return (config.SPEC_DIR / "orders.md").read_text().replace("{stack}", lang.stack())


def build(lang: Lang, project: Path, artifacts: Path, run_dir: Path, number: int, written: set[str]):
    lang.clean(project, artifacts)
    env = lang.env()
    for index, step in enumerate(lang.build_steps(project), 1):
        log_path = run_dir / f"round{number}.build{index}.log"
        code = run_step(step.argv, project, env, step.timeout, log_path)
        if code != 0:
            what = "timed out" if code is None else f"exited with status {code}"
            return step.display, f"`{step.display}` {what}. The last lines of its output:\n```\n{tail(log_path)}\n```"
    error = lang.post_build(project, artifacts)
    if error:
        return "post-build", error
    if not lang.has_tests(project, written):
        return "post-build", "The spec asks for unit tests for the validation rules and the 404 case, and the project has no tests."
    return None


def accept(lang: Lang, project: Path, artifacts: Path, run_dir: Path, number: int, record: dict):
    port = free_port()
    env = lang.env() | {"PORT": str(port)}
    out, err = run_dir / f"round{number}.server.out", run_dir / f"round{number}.server.err"
    server = Server(lang.start_argv(project, artifacts, port, load=False), project, env, out, err)
    server.start()
    try:
        startup = server.wait_healthy(port, 120)
        if startup is None:
            code = server.proc.poll()
            state = f"exited with status {code}" if code is not None else "was still running"
            logs = f"{tail(out, 40)}\n{tail(err, 60)}".strip()
            return "acceptance", (
                f"The harness started the service with PORT={port}, and it did not answer GET /health on that port "
                f"with status 200 within 120 seconds (it {state}). Server output:\n```\n{logs}\n```"
            )
        record["startup_seconds"] = round(startup, 3)
        client = acceptance.Client(port)
        failures = acceptance.run_checks(client)
        if server.proc.poll() is not None:
            failures.append(f"the service exited during the checks with status {server.proc.returncode}")
        else:
            failures += acceptance.shutdown_problems(*server.terminate(10))
        failures += acceptance.log_problems(out, client.sent)
    finally:
        server.close()
    record["acceptance_failures"] = len(failures)
    if not failures:
        return None
    detail = "These checks failed:\n" + "\n".join(f"- {f}" for f in failures[:25])
    if len(failures) > 25:
        detail += f"\n- and {len(failures) - 25} more"
    errors = tail(err, 40).strip()
    if errors:
        detail += f"\n\nThe service's standard error:\n```\n{errors}\n```"
    return "acceptance", detail


def feedback(step: str, detail: str, truncated: bool) -> str:
    note = "Your previous reply hit the output limit and was cut off, so files after the cutoff were not saved.\n\n" if truncated else ""
    return (
        f"{note}The harness ran your project and the `{step}` step failed.\n\n{detail}\n\n"
        "Fix the project. Return only the files you change, each as a line `FILE: <relative path>` "
        "followed by a fenced code block with the complete new contents."
    )


def run_one(lang: Lang, seed: int, max_repairs: int) -> dict:
    run_dir = config.RUNS_DIR / lang.name / f"seed{seed}"
    shutil.rmtree(run_dir, ignore_errors=True)
    project, artifacts = run_dir / "project", run_dir / "artifacts"
    project.mkdir(parents=True)
    prompt = build_prompt(lang)
    (run_dir / "prompt.md").write_text(prompt)
    messages = [{"role": "system", "content": config.SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
    rounds: list[dict] = []
    written: set[str] = set()
    passed = False
    started = time.time()
    for number in range(1, max_repairs + 2):
        reply, meta = llm.chat(messages, seed)
        (run_dir / f"round{number}.reply.md").write_text(reply)
        messages.append({"role": "assistant", "content": reply})
        files = parse_files(reply)
        write_files(project, files)
        written |= set(files)
        record = {"round": number, **meta, "files": sorted(files)}
        if not files:
            failure = ("format", f"Your reply contained no files in the required format. {FORMAT_HELP}")
        else:
            failure = build(lang, project, artifacts, run_dir, number, written)
            if failure is None:
                failure = accept(lang, project, artifacts, run_dir, number, record)
        record["failed_step"] = failure[0] if failure else None
        record["failure"] = failure[1][:6000] if failure else None
        rounds.append(record)
        status = "PASS" if failure is None else f"fail at {failure[0]}"
        print(
            f"{time.strftime('%H:%M:%S')} {lang.name} seed{seed} round{number}: "
            f"in={meta['prompt_eval_count']} out={meta['eval_count']} {status}",
            flush=True,
        )
        if failure is None:
            passed = True
            break
        messages.append({"role": "user", "content": feedback(*failure, meta.get("done_reason") == "length")})
    result = {
        "lang": lang.name,
        "seed": seed,
        "model": config.MODEL,
        "passed": passed,
        "rounds": len(rounds),
        "input_tokens": sum(r["prompt_eval_count"] or 0 for r in rounds),
        "output_tokens": sum(r["eval_count"] or 0 for r in rounds),
        "wall_seconds": round(time.time() - started, 1),
        "files": sorted(written),
        "round_records": rounds,
    }
    (run_dir / "result.json").write_text(json.dumps(result, indent=2))
    (run_dir / "conversation.json").write_text(json.dumps(messages, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the orders service in each language and record tokens.")
    parser.add_argument("--langs", default=",".join(config.LANGS))
    parser.add_argument("--seeds", default=",".join(str(s) for s in config.SEEDS))
    parser.add_argument("--max-repairs", type=int, default=config.MAX_REPAIRS)
    parser.add_argument("--force", action="store_true", help="rerun runs that already have a result.json")
    args = parser.parse_args()
    langs = [LANGS[name] for name in args.langs.split(",")]
    for seed in (int(s) for s in args.seeds.split(",")):
        for lang in langs:
            if (config.RUNS_DIR / lang.name / f"seed{seed}" / "result.json").exists() and not args.force:
                print(f"skip {lang.name} seed{seed}: already has a result", flush=True)
                continue
            result = run_one(lang, seed, args.max_repairs)
            print(
                f"== {lang.name} seed{seed}: {'PASSED' if result['passed'] else 'FAILED'} after {result['rounds']} "
                f"round(s), {result['input_tokens']} in / {result['output_tokens']} out, {result['wall_seconds']}s",
                flush=True,
            )


if __name__ == "__main__":
    main()
