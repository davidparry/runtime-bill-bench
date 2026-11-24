"""Build a failed run's final code without its own tests and run the acceptance test against it.

Used only for a language with fewer than two runs that passed the whole gate, so its runtime can still be
measured on a service that answers every acceptance check. Results are labeled as salvaged everywhere.
"""
import argparse
import json
import shutil

from . import config
from .generate import accept
from .langs import LANGS, Lang, Step
from .proc import run_step, tail

SALVAGE_TARGET = config.ROOT / ".cargo-target-salvage"


def service_steps(lang: Lang, project) -> list[Step]:
    if lang.name == "rust":
        return [Step("cargo build --release", [config.CARGO, "build", "--release"], 1800)]
    if lang.name == "go":
        return [Step("go build -o orders .", [config.GO, "build", "-o", "orders", "."], 300)]
    if lang.name == "java":
        return [Step("mvn -B -DskipTests package", [config.MVN, "-B", "-ntp", "-Dstyle.color=never", "-DskipTests", "package"], 1500)]
    return [step for step in lang.build_steps(project) if step.display != "pytest"]


def salvage(lang: Lang, run_dir) -> dict:
    project, artifacts = run_dir / "project", run_dir / "artifacts"
    env = lang.env()
    if lang.name == "rust":
        # A separate target directory, so this never touches the binary a running generator is building.
        shutil.rmtree(artifacts, ignore_errors=True)
        env["CARGO_TARGET_DIR"] = str(SALVAGE_TARGET)
        (SALVAGE_TARGET / "release" / "orders").unlink(missing_ok=True)
    else:
        lang.clean(project, artifacts)
    for index, step in enumerate(service_steps(lang, project), 1):
        log_path = run_dir / f"salvage.build{index}.log"
        if run_step(step.argv, project, env, step.timeout, log_path) != 0:
            return {"service_passed": False, "failed_step": step.display, "detail": tail(log_path, 30)}
    if lang.name == "rust":
        binary = SALVAGE_TARGET / "release" / "orders"
        if not binary.exists():
            return {"service_passed": False, "failed_step": "post-build", "detail": "no orders binary"}
        artifacts.mkdir(parents=True, exist_ok=True)
        shutil.copy2(binary, artifacts / "orders")
    else:
        error = lang.post_build(project, artifacts)
        if error:
            return {"service_passed": False, "failed_step": "post-build", "detail": error}
    record: dict = {}
    failure = accept(lang, project, artifacts, run_dir, "salvage", record)
    return {
        "service_passed": failure is None,
        "failed_step": failure[0] if failure else None,
        "detail": failure[1][:4000] if failure else None,
        "acceptance_failures": record.get("acceptance_failures"),
        "startup_seconds": record.get("startup_seconds"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--langs", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for name in args.langs.split(","):
        lang = LANGS[name]
        for result_path in sorted((config.RUNS_DIR / name).glob("seed*/result.json")):
            result = json.loads(result_path.read_text())
            if result["passed"] or ((result_path.parent / "salvage.json").exists() and not args.force):
                continue
            outcome = salvage(lang, result_path.parent)
            (result_path.parent / "salvage.json").write_text(json.dumps(outcome, indent=2))
            status = "service passed acceptance" if outcome["service_passed"] else f"failed at {outcome['failed_step']}"
            extra = f" ({outcome.get('acceptance_failures')} acceptance failures)" if outcome["failed_step"] == "acceptance" else ""
            print(f"{name} {result_path.parent.name}: {status}{extra}", flush=True)


if __name__ == "__main__":
    main()
