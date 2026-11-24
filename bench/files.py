import re
from pathlib import Path, PurePosixPath

HEADER = re.compile(r"^\s*(?:#+\s*)?(?:\*\*)?FILE:\s*`?(?P<path>[^`*]+?)`?(?:\*\*)?\s*$")


def parse_files(reply: str) -> dict[str, str]:
    lines = reply.splitlines()
    files: dict[str, str] = {}
    i = 0
    while i < len(lines):
        match = HEADER.match(lines[i])
        if not match:
            i += 1
            continue
        path = clean_path(match.group("path"))
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        opener = lines[j].strip() if j < len(lines) else ""
        if path is None or not opener.startswith("```"):
            i += 1
            continue
        fence = opener[: len(opener) - len(opener.lstrip("`"))]
        body: list[str] = []
        k = j + 1
        while k < len(lines) and lines[k].strip() != fence:
            body.append(lines[k])
            k += 1
        if k < len(lines):
            files[path] = "\n".join(body) + "\n"
        i = k + 1
    return files


def clean_path(raw: str) -> str | None:
    text = raw.strip().removeprefix("./")
    if not text:
        return None
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        return None
    return str(path)


def write_files(project: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        target = project / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
