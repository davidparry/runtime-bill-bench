import json
import urllib.request
import uuid

from . import config

COUNTERS = (
    "prompt_eval_count",
    "eval_count",
    "prompt_eval_duration",
    "eval_duration",
    "load_duration",
    "total_duration",
    "done_reason",
)


def chat(messages: list[dict], seed: int) -> tuple[str, dict]:
    # A new first line on every request defeats Ollama's prompt cache, so
    # prompt_eval_count is the whole conversation, the way a hosted API bills input.
    system = {"role": "system", "content": f"Session {uuid.uuid4()}\n{messages[0]['content']}"}
    body = {
        "model": config.MODEL,
        "messages": [system, *messages[1:]],
        "stream": False,
        "think": False,
        "keep_alive": "30m",
        "options": {"seed": seed, "num_ctx": config.NUM_CTX, "num_predict": config.NUM_PREDICT},
    }
    request = urllib.request.Request(
        f"{config.OLLAMA_URL}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=7200) as response:
        data = json.load(response)
    message = data.get("message", {})
    meta = {key: data.get(key) for key in COUNTERS}
    meta["thinking_chars"] = len(message.get("thinking") or "")
    return message.get("content", ""), meta


def unload() -> None:
    body = {"model": config.MODEL, "keep_alive": 0}
    request = urllib.request.Request(
        f"{config.OLLAMA_URL}/api/generate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        response.read()
