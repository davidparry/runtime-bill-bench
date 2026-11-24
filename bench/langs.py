import os
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import config


@dataclass
class Step:
    display: str
    argv: list[str]
    timeout: int


def base_env() -> dict:
    env = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CONDA_PREFIX", "JAVA_TOOL_OPTIONS"):
        env.pop(key, None)
    return env


class Lang:
    name = ""

    def stack(self) -> str:
        return (config.SPEC_DIR / "stacks" / f"{self.name}.md").read_text().strip()

    def env(self) -> dict:
        return base_env()

    def clean(self, project: Path, artifacts: Path) -> None:
        shutil.rmtree(artifacts, ignore_errors=True)

    def build_steps(self, project: Path) -> list[Step]:
        raise NotImplementedError

    def post_build(self, project: Path, artifacts: Path) -> str | None:
        return None

    def start_argv(self, project: Path, artifacts: Path, port: int, load: bool) -> list[str]:
        raise NotImplementedError

    def categorize(self, rel: str) -> str:
        raise NotImplementedError

    def has_tests(self, project: Path, written: set[str]) -> bool:
        return any(self.categorize(rel) == "test" for rel in written)


class Java(Lang):
    name = "java"

    def env(self) -> dict:
        env = base_env()
        env["JAVA_HOME"] = str(config.JAVA_HOME)
        env["PATH"] = f"{config.JAVA_HOME}/bin:{env['PATH']}"
        return env

    def clean(self, project: Path, artifacts: Path) -> None:
        super().clean(project, artifacts)
        shutil.rmtree(project / "target", ignore_errors=True)

    def build_steps(self, project: Path) -> list[Step]:
        return [Step("mvn -B package", [config.MVN, "-B", "-ntp", "-Dstyle.color=never", "package"], 1500)]

    def post_build(self, project: Path, artifacts: Path) -> str | None:
        jar = boot_jar(project / "target")
        if jar is None:
            return "`mvn -B package` succeeded, but target/ has no executable Spring Boot jar (no jar contains BOOT-INF/)."
        artifacts.mkdir(parents=True, exist_ok=True)
        shutil.copy2(jar, artifacts / "app.jar")
        return None

    def start_argv(self, project: Path, artifacts: Path, port: int, load: bool) -> list[str]:
        # Size the JVM as it would inside a 2 GB container, not from the Mac's 128 GB.
        return [str(config.JAVA_HOME / "bin/java"), "-XX:MaxRAM=2g", "-jar", str(artifacts / "app.jar")]

    def categorize(self, rel: str) -> str:
        if rel.startswith("src/test/"):
            return "test"
        if rel.endswith((".java", ".kt")):
            return "source"
        if rel in ("pom.xml", "mvnw", "mvnw.cmd") or rel.startswith(".mvn/"):
            return "manifest"
        if rel.startswith("src/main/resources/"):
            return "config"
        return "other"


def boot_jar(target: Path) -> Path | None:
    for jar in sorted(target.glob("*.jar")):
        try:
            with zipfile.ZipFile(jar) as archive:
                if any(name.startswith("BOOT-INF/") for name in archive.namelist()):
                    return jar
        except zipfile.BadZipFile:
            continue
    return None


class Go(Lang):
    name = "go"

    def env(self) -> dict:
        env = base_env()
        env["GOTOOLCHAIN"] = "local"
        return env

    def clean(self, project: Path, artifacts: Path) -> None:
        super().clean(project, artifacts)
        (project / "orders").unlink(missing_ok=True)

    def build_steps(self, project: Path) -> list[Step]:
        return [
            Step("go mod tidy", [config.GO, "mod", "tidy"], 300),
            Step("go build -o orders .", [config.GO, "build", "-o", "orders", "."], 300),
            Step("go test ./...", [config.GO, "test", "./..."], 600),
        ]

    def post_build(self, project: Path, artifacts: Path) -> str | None:
        modules = subprocess.run(
            [config.GO, "list", "-m", "all"], cwd=project, env=self.env(), capture_output=True, text=True
        ).stdout.split("\n")
        extra = [line for line in modules[1:] if line.strip()]
        if extra:
            return "The spec requires the standard library only, but `go list -m all` shows third-party modules:\n" + "\n".join(extra[:20])
        artifacts.mkdir(parents=True, exist_ok=True)
        shutil.copy2(project / "orders", artifacts / "orders")
        return None

    def start_argv(self, project: Path, artifacts: Path, port: int, load: bool) -> list[str]:
        return [str(artifacts / "orders")]

    def categorize(self, rel: str) -> str:
        if rel.endswith("_test.go"):
            return "test"
        if rel.endswith(".go"):
            return "source"
        if rel in ("go.mod", "go.sum"):
            return "manifest"
        return "other"


class Rust(Lang):
    name = "rust"

    def env(self) -> dict:
        env = base_env()
        env["CARGO_TARGET_DIR"] = str(config.CARGO_TARGET_DIR)
        env["CARGO_TERM_COLOR"] = "never"
        return env

    def clean(self, project: Path, artifacts: Path) -> None:
        super().clean(project, artifacts)
        (config.CARGO_TARGET_DIR / "release" / "orders").unlink(missing_ok=True)

    def build_steps(self, project: Path) -> list[Step]:
        return [
            Step("cargo build --release", [config.CARGO, "build", "--release"], 1800),
            Step("cargo test --release", [config.CARGO, "test", "--release"], 1200),
        ]

    def post_build(self, project: Path, artifacts: Path) -> str | None:
        binary = config.CARGO_TARGET_DIR / "release" / "orders"
        if not binary.exists():
            return "`cargo build --release` succeeded, but there is no target/release/orders binary. The package or binary target must be named orders."
        artifacts.mkdir(parents=True, exist_ok=True)
        shutil.copy2(binary, artifacts / "orders")
        return None

    def start_argv(self, project: Path, artifacts: Path, port: int, load: bool) -> list[str]:
        return [str(artifacts / "orders")]

    def categorize(self, rel: str) -> str:
        if rel.startswith("tests/"):
            return "test"
        if rel.endswith(".rs"):
            return "source"
        if rel in ("Cargo.toml", "Cargo.lock", "build.rs"):
            return "manifest"
        return "other"

    def has_tests(self, project: Path, written: set[str]) -> bool:
        if super().has_tests(project, written):
            return True
        for rel in written:
            if rel.endswith(".rs") and "#[test]" in (project / rel).read_text(errors="replace"):
                return True
        return False


class Python(Lang):
    name = "python"

    def clean(self, project: Path, artifacts: Path) -> None:
        super().clean(project, artifacts)
        shutil.rmtree(project / ".venv", ignore_errors=True)

    def build_steps(self, project: Path) -> list[Step]:
        install = [config.UV, "pip", "install", "--quiet", "--python", ".venv/bin/python", "-r", "requirements.txt"]
        display = "uv pip install -r requirements.txt"
        if (project / "requirements-dev.txt").exists():
            install += ["-r", "requirements-dev.txt"]
            display += " -r requirements-dev.txt"
        return [
            Step(f"uv venv --python {config.PYTHON_VERSION}", [config.UV, "venv", "--quiet", "--python", config.PYTHON_VERSION, ".venv"], 300),
            Step(display, install, 900),
            Step("pytest", [".venv/bin/python", "-m", "pytest", "-q", "-p", "no:cacheprovider"], 600),
        ]

    def start_argv(self, project: Path, artifacts: Path, port: int, load: bool) -> list[str]:
        argv = [str(project / ".venv/bin/uvicorn"), "main:app", "--host", "0.0.0.0", "--port", str(port), "--no-access-log"]
        if load:
            argv += ["--workers", str(os.cpu_count())]
        return argv

    def categorize(self, rel: str) -> str:
        name = rel.rsplit("/", 1)[-1]
        if rel.startswith("tests/") or name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
            return "test"
        if rel.endswith(".py"):
            return "source"
        if name.startswith("requirements") or name in ("pyproject.toml", "setup.cfg", "setup.py"):
            return "manifest"
        return "other"


LANGS: dict[str, Lang] = {lang.name: lang for lang in (Java(), Go(), Rust(), Python())}
