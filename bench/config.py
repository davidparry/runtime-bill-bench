import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC_DIR = ROOT / "spec"
RUNS_DIR = ROOT / "runs"
RESULTS_DIR = ROOT / "results"
CARGO_TARGET_DIR = ROOT / ".cargo-target"

MODEL = "qwen3.6:35b-a3b-coding"
OLLAMA_URL = "http://127.0.0.1:11434"
NUM_CTX = 65536
NUM_PREDICT = 16384
MAX_REPAIRS = 4
SEEDS = (1, 2, 3, 4, 5)
LANGS = ("java", "go", "rust", "python")

SYSTEM_PROMPT = (
    "You are a senior software engineer. Follow the specification exactly and "
    "return complete files in the requested format."
)

JAVA_HOME = Path.home() / ".jenv/versions/temurin64-25.0.5"
PYTHON_VERSION = "3.14"

MVN = shutil.which("mvn")
GO = shutil.which("go")
CARGO = shutil.which("cargo")
UV = shutil.which("uv")
TRIVY = shutil.which("trivy")
OHA = shutil.which("oha") or str(Path.home() / ".cargo/bin/oha")

# Prices used to turn measurements into dollars (checked November 2026).
FARGATE_VCPU_HOUR = 0.04048  # Linux/x86, us-east-1
FARGATE_GB_HOUR = 0.004445
OPUS_INPUT_PER_M = 4.00  # Claude Opus 5.5
OPUS_OUTPUT_PER_M = 20.00
