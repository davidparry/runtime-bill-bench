"""Acceptance-test a hand-fixed copy of a failed run, kept in runs/<lang>/handfix-seed<N>/.

The copy's diff against the run's own final code is saved as fix.patch, and every number measured on it is
labeled hand-fixed. Its tokens and pass/fail stay with the original run.
"""
import argparse
import json
import subprocess

from . import config
from .langs import LANGS
from .salvage import salvage


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--change", required=True, help="one sentence describing the hand fix")
    args = parser.parse_args()
    lang = LANGS[args.lang]
    original = config.RUNS_DIR / args.lang / f"seed{args.seed}"
    fixed = config.RUNS_DIR / args.lang / f"handfix-seed{args.seed}"
    patch = subprocess.run(
        ["diff", "-ru", "-x", "target", "-x", "Cargo.lock", str(original / "project"), str(fixed / "project")],
        capture_output=True, text=True,
    ).stdout
    (fixed / "fix.patch").write_text(patch)
    changed = sum(1 for line in patch.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))
    outcome = salvage(lang, fixed)
    result = json.loads((original / "result.json").read_text())
    record = {"seed": args.seed, "files": result["files"], "change": args.change, "changed_lines": changed, **outcome}
    (fixed / "handfix.json").write_text(json.dumps(record, indent=2))
    print(f"{args.lang} handfix-seed{args.seed}: {changed} changed lines; "
          f"{'service passed acceptance' if outcome['service_passed'] else 'failed at ' + str(outcome['failed_step'])}")
    if outcome["detail"]:
        print(outcome["detail"][:3000])


if __name__ == "__main__":
    main()
