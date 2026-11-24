import argparse
import json
import re
import shutil
import statistics
import subprocess
import threading
import tomllib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import psutil

from . import config, llm
from .langs import LANGS, Lang
from .proc import Server, free_port

LOAD_BODY = {
    "customerId": "c-load",
    "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}, {"sku": "B-2", "quantity": 1, "unitPriceCents": 999}],
}
WARMUP = 20_000
MEASURED = 100_000
CONCURRENCY = 64
TRIALS = 3
USER_AGENT = "runtime-bill-bench/0.1 (+https://davidparry.com)"
_http_cache: dict[str, object] = {}


def run(argv: list[str], cwd: Path | None = None, env: dict | None = None, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def fetch(url: str, as_json: bool = True):
    if url in _http_cache:
        return _http_cache[url]
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response) if as_json else response.read().decode()
    except Exception:
        data = None
    _http_cache[url] = data
    return data


def count_loc(lang: Lang, project: Path, files: list[str]) -> dict:
    totals = dict.fromkeys(("source", "test", "manifest", "config", "other"), 0)
    for rel in files:
        path = project / rel
        if not path.exists():
            continue
        lines = [line for line in path.read_text(errors="replace").splitlines() if line.strip()]
        category = lang.categorize(rel)
        if lang.name == "rust" and category == "source":
            start = next((i for i, line in enumerate(lines) if line.strip().startswith("#[cfg(test)]")), None)
            if start is not None:
                totals["test"] += len(lines) - start
                lines = lines[:start]
        totals[category] += len(lines)
    totals["total"] = sum(totals.values())
    return totals


# Runtime dependencies: what ships with the service, not what its tests need.

def java_deps(run_dir: Path) -> list[str]:
    with zipfile.ZipFile(run_dir / "artifacts" / "app.jar") as archive:
        return sorted(
            name.removeprefix("BOOT-INF/lib/")
            for name in archive.namelist()
            if name.startswith("BOOT-INF/lib/") and name.endswith(".jar")
        )


def go_deps(project: Path) -> list[str]:
    lines = run([config.GO, "list", "-m", "all"], cwd=project, env=LANGS["go"].env()).stdout.splitlines()
    return [line for line in lines[1:] if line.strip()]


def rust_deps(project: Path) -> list[str]:
    out = run(
        [config.CARGO, "tree", "-e", "normal", "--prefix", "none", "--color", "never"],
        cwd=project, env=LANGS["rust"].env(),
    ).stdout.splitlines()
    names = []
    for line in out:
        entry = line.replace(" (*)", "").replace(" (proc-macro)", "").strip()
        entry = re.sub(r" \(/.*\)$", "", entry)
        if entry:
            names.append(entry)
    return sorted(set(names[1:]) - {names[0]}) if names else []


def python_runtime_venv(project: Path, run_dir: Path) -> Path:
    venv = run_dir / "runtime-venv"
    shutil.rmtree(venv, ignore_errors=True)
    run([config.UV, "venv", "--quiet", "--python", config.PYTHON_VERSION, str(venv)])
    run([config.UV, "pip", "install", "--quiet", "--python", str(venv / "bin/python"), "-r", "requirements.txt"], cwd=project)
    return venv


def python_deps(venv: Path) -> list[str]:
    out = run([config.UV, "pip", "list", "--python", str(venv / "bin/python"), "--format", "json"]).stdout
    return sorted(f"{p['name']} {p['version']}" for p in json.loads(out or "[]") if p["name"] not in ("pip", "setuptools", "wheel"))


# Known vulnerabilities, scanned on the artifact that ships.

def trivy(mode: str, target: Path) -> list[dict]:
    out = run([
        config.TRIVY, mode, "--scanners", "vuln", "--format", "json", "--quiet",
        "--skip-db-update", "--skip-java-db-update", str(target),
    ], timeout=900)
    data = json.loads(out.stdout or "{}")
    found: dict[tuple, dict] = {}
    for result in data.get("Results") or []:
        for vuln in result.get("Vulnerabilities") or []:
            key = (vuln["VulnerabilityID"], vuln["PkgName"], vuln.get("InstalledVersion"))
            found[key] = {
                "id": vuln["VulnerabilityID"],
                "package": vuln["PkgName"],
                "installed": vuln.get("InstalledVersion"),
                "fixed": vuln.get("FixedVersion"),
                "severity": vuln.get("Severity"),
            }
    return sorted(found.values(), key=lambda v: (v["severity"] or "", v["package"], v["id"]))


def scan(lang: Lang, project: Path, run_dir: Path, deps: list[str]) -> list[dict]:
    if lang.name in ("java", "go"):
        return trivy("rootfs", run_dir / "artifacts")
    if lang.name == "python":
        return trivy("rootfs", run_dir / "runtime-venv")
    target = run_dir / "scan"
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir()
    shutil.copy2(project / "Cargo.lock", target / "Cargo.lock")
    shipped = {dep.split(" v")[0] for dep in deps}
    return [v for v in trivy("fs", target) if v["package"] in shipped]


# The versions the model asked for, next to what the registry has today.

def maven_release_date(group: str, artifact: str, version: str) -> str | None:
    query = urllib.parse.quote(f'g:"{group}" AND a:"{artifact}" AND v:"{version}"')
    data = fetch(f"https://search.maven.org/solrsearch/select?q={query}&wt=json")
    docs = (data or {}).get("response", {}).get("docs") or []
    if docs:
        return datetime.fromtimestamp(docs[0]["timestamp"] / 1000, UTC).date().isoformat()
    # The search index lags new releases; the repository listing shows the upload date.
    listing = fetch(f"https://repo1.maven.org/maven2/{group.replace('.', '/')}/{artifact}/{version}/", as_json=False)
    match = re.search(rf"{re.escape(artifact)}-{re.escape(version)}\.pom</a>\s+(\d{{4}}-\d{{2}}-\d{{2}})", listing or "")
    return match.group(1) if match else None


def java_pins(project: Path, deps: list[str]) -> dict:
    ns = {"m": "http://maven.apache.org/POM/4.0.0"}
    root = ET.parse(project / "pom.xml").getroot()

    def text(node, path):
        found = node.find(path, ns) if node is not None else None
        return found.text.strip() if found is not None and found.text else None

    boot = None
    parent = root.find("m:parent", ns)
    if text(parent, "m:artifactId") == "spring-boot-starter-parent":
        boot = text(parent, "m:version")
    for dep in root.findall("m:dependencyManagement/m:dependencies/m:dependency", ns):
        if text(dep, "m:artifactId") == "spring-boot-dependencies":
            boot = text(dep, "m:version")
    properties = root.find("m:properties", ns)
    if boot and boot.startswith("${") and properties is not None:
        boot = text(properties, f"m:{boot[2:-1]}")
    metadata = fetch("https://repo1.maven.org/maven2/org/springframework/boot/spring-boot/maven-metadata.xml", as_json=False)
    current = None
    if metadata:
        match = re.search(r"<release>([^<]+)</release>", metadata)
        current = match.group(1) if match else None
    resolved = {
        name: next((d.removeprefix(name + "-").removesuffix(".jar") for d in deps if re.match(rf"{name}-\d", d)), None)
        for name in ("spring-boot", "spring-web", "tomcat-embed-core", "jackson-databind")
    }
    return {
        "framework": "spring-boot",
        "pinned": boot,
        "pinned_released": maven_release_date("org.springframework.boot", "spring-boot", boot) if boot else None,
        "current": current,
        "current_released": maven_release_date("org.springframework.boot", "spring-boot", current) if current else None,
        "java_version": text(properties, "m:java.version"),
        "resolved": resolved,
    }


def crate_info(name: str, version: str | None) -> dict:
    data = fetch(f"https://crates.io/api/v1/crates/{name}") or {}
    current = (data.get("crate") or {}).get("max_stable_version")
    released = None
    for entry in data.get("versions") or []:
        if entry.get("num") == version:
            released = (entry.get("created_at") or "")[:10] or None
    return {"current": current, "released": released}


def rust_pins(project: Path) -> dict:
    manifest = tomllib.loads((project / "Cargo.toml").read_text())
    lock = tomllib.loads((project / "Cargo.lock").read_text())
    locked = {}
    for package in lock.get("package", []):
        locked.setdefault(package["name"], package["version"])
    pins = {}
    for name in ("axum", "tokio", "serde", "serde_json", "uuid", "tracing"):
        spec = manifest.get("dependencies", {}).get(name)
        if spec is None:
            continue
        requirement = spec if isinstance(spec, str) else spec.get("version")
        info = crate_info(name, locked.get(name))
        pins[name] = {"requirement": requirement, "resolved": locked.get(name), "resolved_released": info["released"], "current": info["current"]}
    return {"framework": "axum", "pinned": pins.get("axum", {}).get("requirement"), "crates": pins}


def pypi_info(name: str, version: str | None) -> dict:
    data = fetch(f"https://pypi.org/pypi/{name}/json") or {}
    current = (data.get("info") or {}).get("version")
    released = None
    files = (data.get("releases") or {}).get(version or "", [])
    if files:
        released = files[0].get("upload_time_iso_8601", "")[:10] or None
    current_files = (data.get("releases") or {}).get(current or "", [])
    current_released = current_files[0].get("upload_time_iso_8601", "")[:10] if current_files else None
    return {"current": current, "released": released, "current_released": current_released}


def python_pins(project: Path, deps: list[str]) -> dict:
    declared = {}
    for line in (project / "requirements.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        match = re.match(r"^([A-Za-z0-9_.\-\[\]]+)\s*([=<>!~]=?.*)?$", line)
        if match and not line.startswith("-"):
            declared[re.sub(r"\[.*\]", "", match.group(1)).lower()] = (match.group(2) or "").strip() or None
    installed = {d.split(" ")[0].lower(): d.split(" ")[1] for d in deps}
    pins = {}
    for name in ("fastapi", "uvicorn", "pydantic", "pydantic-core", "starlette"):
        version = installed.get(name)
        info = pypi_info(name, version)
        pins[name] = {"requirement": declared.get(name), "resolved": version, "resolved_released": info["released"],
                      "current": info["current"], "current_released": info["current_released"]}
    return {"framework": "fastapi", "pinned": pins["fastapi"]["requirement"], "packages": pins}


def go_pins(project: Path) -> dict:
    match = re.search(r"^go\s+(\S+)", (project / "go.mod").read_text(), re.M)
    toolchain = run([config.GO, "env", "GOVERSION"]).stdout.strip()
    return {"framework": "standard library", "pinned": match.group(1) if match else None, "toolchain": toolchain}


# Load: what it costs to run.

def tree_usage(pid: int) -> tuple[float, int]:
    try:
        root = psutil.Process(pid)
        procs = [root, *root.children(recursive=True)]
    except psutil.NoSuchProcess:
        return 0.0, 0
    cpu, rss = 0.0, 0
    for proc in procs:
        try:
            times = proc.cpu_times()
            cpu += times.user + times.system
            rss += proc.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return cpu, rss


class PeakMemory(threading.Thread):
    def __init__(self, pid: int):
        super().__init__(daemon=True)
        self.pid, self.peak, self._stop = pid, 0, threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            self.peak = max(self.peak, tree_usage(self.pid)[1])
            self._stop.wait(0.2)

    def stop(self) -> None:
        self._stop.set()
        self.join()


def oha(port: int, requests: int) -> dict:
    out = run([
        config.OHA, "-n", str(requests), "-c", str(CONCURRENCY), "-m", "POST", "-T", "application/json",
        "-d", json.dumps(LOAD_BODY), "--no-tui", "--output-format", "json", f"http://127.0.0.1:{port}/orders",
    ], timeout=3600)
    return json.loads(out.stdout)


def load_trial(lang: Lang, project: Path, run_dir: Path, index: int) -> dict:
    port = free_port()
    env = lang.env() | {"PORT": str(port)}
    artifacts = run_dir / "artifacts"
    server = Server(lang.start_argv(project, artifacts, port, load=True), project, env, None, run_dir / f"load{index}.err")
    server.start()
    try:
        startup = server.wait_healthy(port, 120)
        if startup is None:
            return {"error": "the service did not become healthy"}
        _, idle_rss = tree_usage(server.proc.pid)
        oha(port, WARMUP)
        cpu_before, _ = tree_usage(server.proc.pid)
        peak = PeakMemory(server.proc.pid)
        peak.start()
        result = oha(port, MEASURED)
        peak.stop()
        cpu_after, _ = tree_usage(server.proc.pid)
    finally:
        server.terminate(10)
        server.close()
    return {
        "startup_ms": round(startup * 1000, 1),
        "idle_rss_mb": round(idle_rss / 2**20, 1),
        "peak_rss_mb": round(peak.peak / 2**20, 1),
        "cpu_seconds_per_100k": round((cpu_after - cpu_before) * 100_000 / MEASURED, 3),
        "rps": round(result["summary"]["requestsPerSec"], 1),
        "p50_ms": round(result["latencyPercentiles"]["p50"] * 1000, 3),
        "p99_ms": round(result["latencyPercentiles"]["p99"] * 1000, 3),
        "success_rate": result["summary"]["successRate"],
        "status_codes": result.get("statusCodeDistribution"),
        "errors": result.get("errorDistribution"),
    }


def median_trial(trials: list[dict]) -> dict:
    good = [t for t in trials if "error" not in t]
    if not good:
        return {"error": "no trial completed"}
    keys = ("startup_ms", "idle_rss_mb", "peak_rss_mb", "cpu_seconds_per_100k", "rps", "p50_ms", "p99_ms")
    return {key: round(statistics.median(t[key] for t in good), 3) for key in keys}


def measure_run(lang: Lang, run_dir: Path, result: dict, skip_load: bool) -> dict:
    project = run_dir / "project"
    measured = {"lang": lang.name, "seed": result["seed"], "loc": count_loc(lang, project, result["files"])}
    if lang.name == "java":
        deps = java_deps(run_dir)
    elif lang.name == "go":
        deps = go_deps(project)
    elif lang.name == "rust":
        deps = rust_deps(project)
    else:
        deps = python_deps(python_runtime_venv(project, run_dir))
    measured["runtime_deps"] = deps
    measured["vulnerabilities"] = scan(lang, project, run_dir, deps)
    if lang.name == "java":
        measured["pins"] = java_pins(project, deps)
    elif lang.name == "go":
        measured["pins"] = go_pins(project)
    elif lang.name == "rust":
        measured["pins"] = rust_pins(project)
    else:
        measured["pins"] = python_pins(project, deps)
    if not skip_load:
        trials = [load_trial(lang, project, run_dir, i) for i in range(1, TRIALS + 1)]
        measured["load_trials"] = trials
        measured["load"] = median_trial(trials)
    return measured


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure every passing run: size, dependencies, vulnerabilities, and load.")
    parser.add_argument("--langs", default=",".join(config.LANGS))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-load", action="store_true")
    args = parser.parse_args()
    if not args.skip_load:
        llm.unload()
    run([config.TRIVY, "image", "--download-db-only", "--quiet"])
    run([config.TRIVY, "image", "--download-java-db-only", "--quiet"])
    version = json.loads(run([config.TRIVY, "version", "--format", "json"]).stdout or "{}")
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / "trivy-db.json").write_text(json.dumps(version, indent=2))
    for name in args.langs.split(","):
        lang = LANGS[name]
        for result_path in sorted((config.RUNS_DIR / name).glob("seed*/result.json")):
            run_dir = result_path.parent
            result = json.loads(result_path.read_text())
            salvage_path = run_dir / "salvage.json"
            salvaged = (
                not result["passed"]
                and salvage_path.exists()
                and json.loads(salvage_path.read_text())["service_passed"]
            )
            if not result["passed"] and not salvaged:
                continue
            out = run_dir / "measure.json"
            if out.exists() and not args.force:
                print(f"skip {name} {run_dir.name}: already measured", flush=True)
                continue
            measured = measure_run(lang, run_dir, result, args.skip_load)
            measured["salvaged"] = salvaged
            out.write_text(json.dumps(measured, indent=2))
            report(name, run_dir, measured)
        for fix_path in sorted((config.RUNS_DIR / name).glob("handfix-seed*/handfix.json")):
            run_dir = fix_path.parent
            fix = json.loads(fix_path.read_text())
            out = run_dir / "measure.json"
            if not fix["service_passed"] or (out.exists() and not args.force):
                continue
            measured = measure_run(lang, run_dir, {"seed": fix["seed"], "files": fix["files"]}, args.skip_load)
            measured["hand_fixed"] = {"change": fix["change"], "changed_lines": fix["changed_lines"]}
            out.write_text(json.dumps(measured, indent=2))
            report(name, run_dir, measured)


def report(name: str, run_dir: Path, measured: dict) -> None:
    load = measured.get("load", {})
    print(
        f"{name} {run_dir.name}: {measured['loc']['total']} lines, {len(measured['runtime_deps'])} deps, "
        f"{len(measured['vulnerabilities'])} vulns, cpu/100k={load.get('cpu_seconds_per_100k')}s, "
        f"peak={load.get('peak_rss_mb')}MB, rps={load.get('rps')}",
        flush=True,
    )


if __name__ == "__main__":
    main()
