import concurrent.futures
import http.client
import json
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

RFC3339_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$")
LOG_KEYS = ("method", "path", "status", "durationMs")


@dataclass
class Reply:
    status: int
    headers: dict
    text: str
    body: object


class Client:
    def __init__(self, port: int):
        self.port = port
        self.sent = 0
        self._lock = threading.Lock()

    def call(self, method: str, path: str, body=None, raw: str | None = None) -> Reply:
        data = raw.encode() if raw is not None else (json.dumps(body).encode() if body is not None else None)
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request(method, path, body=data, headers=headers)
            response = conn.getresponse()
            text = response.read().decode("utf-8", "replace")
            reply_headers = {key.lower(): value for key, value in response.getheaders()}
            status = response.status
        finally:
            conn.close()
            with self._lock:
                self.sent += 1
        try:
            parsed = json.loads(text) if text else None
        except ValueError:
            parsed = None
        return Reply(status, reply_headers, text, parsed)


def item(**changes) -> dict:
    return {"sku": "A-1", "quantity": 2, "unitPriceCents": 1250} | changes


def order(customer: str = "c-123", items: list | None = None, **extra) -> dict:
    if items is None:
        items = [item(), item(sku="B-2", quantity=1, unitPriceCents=999)]
    return {"customerId": customer, "items": items} | extra


def without(data: dict, key: str) -> dict:
    return {k: v for k, v in data.items() if k != key}


INVALID = [
    ("malformed JSON", None, '{"customerId": "c-1", "items": ['),
    ("no customerId", {"items": [item()]}, None),
    ("an empty customerId", order(customer=""), None),
    ("a 65-character customerId", order(customer="c" * 65), None),
    ("no items", {"customerId": "c-1"}, None),
    ("an empty items array", order(items=[]), None),
    ("51 items", order(items=[item() for _ in range(51)]), None),
    ("quantity 0", order(items=[item(quantity=0)]), None),
    ("quantity 101", order(items=[item(quantity=101)]), None),
    ("no quantity", order(items=[without(item(), "quantity")]), None),
    ("unitPriceCents 0", order(items=[item(unitPriceCents=0)]), None),
    ("unitPriceCents 1000001", order(items=[item(unitPriceCents=1000001)]), None),
    ("an empty sku", order(items=[item(sku="")]), None),
    ("a 33-character sku", order(items=[item(sku="S" * 33)]), None),
    ("no sku", order(items=[without(item(), "sku")]), None),
]


def expect_status(reply: Reply, expected: int) -> list[str]:
    if reply.status == expected:
        return []
    return [f"expected status {expected}, got {reply.status} with body {reply.text[:300]!r}"]


def expect_json(reply: Reply) -> list[str]:
    ctype = reply.headers.get("content-type", "")
    return [] if ctype.startswith("application/json") else [f"Content-Type is {ctype!r}, expected application/json"]


def expect_error_body(reply: Reply) -> list[str]:
    if isinstance(reply.body, dict) and isinstance(reply.body.get("error"), str):
        return []
    return [f'expected a JSON object with a string "error" field, got {reply.text[:300]!r}']


def order_problems(body, sent: dict, total: int) -> list[str]:
    if not isinstance(body, dict):
        return [f"expected a JSON object, got {str(body)[:300]!r}"]
    problems = []
    oid = body.get("id")
    try:
        if uuid.UUID(str(oid)).version != 4:
            problems.append(f"id {oid!r} is not a version 4 UUID")
    except ValueError:
        problems.append(f"id {oid!r} is not a UUID")
    if body.get("customerId") != sent["customerId"]:
        problems.append(f"customerId is {body.get('customerId')!r}, expected {sent['customerId']!r}")
    items = body.get("items")
    if not isinstance(items, list) or len(items) != len(sent["items"]):
        problems.append(f"items {str(items)[:200]!r} do not match the {len(sent['items'])} items sent")
    else:
        for got, want in zip(items, sent["items"]):
            if not isinstance(got, dict) or any(got.get(k) != want[k] for k in ("sku", "quantity", "unitPriceCents")):
                problems.append(f"item {got!r} does not match the item sent, {want!r}")
                break
    got_total = body.get("totalCents")
    if not (isinstance(got_total, int) and not isinstance(got_total, bool) and got_total == total):
        problems.append(f"totalCents is {got_total!r}, expected {total}")
    created_at = body.get("createdAt")
    if not (isinstance(created_at, str) and RFC3339_UTC.match(created_at)):
        problems.append(f"createdAt {created_at!r} is not an RFC 3339 timestamp in UTC")
    return problems


def check_health(client: Client) -> list[str]:
    reply = client.call("GET", "/health")
    problems = expect_status(reply, 200) + expect_json(reply)
    if not (isinstance(reply.body, dict) and reply.body.get("status") == "ok"):
        problems.append(f'expected {{"status": "ok"}}, got {reply.text[:200]!r}')
    return problems


def check_create(client: Client, created: dict) -> list[str]:
    sent = order()
    reply = client.call("POST", "/orders", sent)
    problems = expect_status(reply, 201) + expect_json(reply)
    if reply.status != 201:
        return problems
    problems += order_problems(reply.body, sent, 2 * 1250 + 999)
    oid = reply.body.get("id") if isinstance(reply.body, dict) else None
    location = reply.headers.get("location", "")
    if not (oid and location.endswith(f"/orders/{oid}")):
        problems.append(f"Location header is {location!r}, expected /orders/{oid}")
    if oid:
        created["body"] = reply.body
    return problems


def check_read_back(client: Client, body: dict) -> list[str]:
    reply = client.call("GET", f"/orders/{body['id']}")
    problems = expect_status(reply, 200) + expect_json(reply)
    if reply.status == 200 and isinstance(reply.body, dict):
        for key in ("id", "customerId", "items", "totalCents", "createdAt"):
            if reply.body.get(key) != body.get(key):
                problems.append(f"{key} is {reply.body.get(key)!r}, but the create response had {body.get(key)!r}")
    return problems


def check_unknown_id(client: Client) -> list[str]:
    reply = client.call("GET", f"/orders/{uuid.uuid4()}")
    return expect_status(reply, 404) + expect_json(reply) + expect_error_body(reply)


def check_invalid(client: Client, body, raw) -> list[str]:
    reply = client.call("POST", "/orders", body, raw)
    return expect_status(reply, 400) + expect_json(reply) + expect_error_body(reply)


def check_largest(client: Client) -> list[str]:
    sent = order(items=[item(sku=f"S-{i}", quantity=100, unitPriceCents=1000000) for i in range(50)])
    reply = client.call("POST", "/orders", sent)
    problems = expect_status(reply, 201)
    return problems or order_problems(reply.body, sent, 5_000_000_000)


def check_unknown_fields(client: Client) -> list[str]:
    sent = order(items=[item(color="red")], coupon="SAVE10")
    reply = client.call("POST", "/orders", sent)
    problems = expect_status(reply, 201)
    return problems or order_problems(reply.body, sent, 2500)


def check_concurrent(client: Client) -> list[str]:
    sends = [order(customer=f"c-{i}", items=[item(quantity=1 + i % 100)]) for i in range(200)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
        created = list(pool.map(lambda body: client.call("POST", "/orders", body), sends))
        failed = [r for r in created if r.status != 201 or not isinstance(r.body, dict)]
        if failed:
            return [f"{len(failed)} of 200 creates failed; the first got status {failed[0].status} with body {failed[0].text[:200]!r}"]
        ids = [r.body.get("id") for r in created]
        if len(set(ids)) != len(ids):
            return ["ids were not unique across 200 concurrent creates"]
        reads = list(pool.map(lambda oid: client.call("GET", f"/orders/{oid}"), ids))
    missing = [
        i for i, r in enumerate(reads)
        if r.status != 200 or not isinstance(r.body, dict) or r.body.get("customerId") != sends[i]["customerId"]
    ]
    return [f"{len(missing)} of 200 created orders could not be read back"] if missing else []


def run_checks(client: Client) -> list[str]:
    failures: list[str] = []

    def check(name, fn):
        try:
            problems = fn()
        except Exception as exc:
            problems = [f"request failed: {exc!r}"]
        failures.extend(f"{name}: {problem}" for problem in problems)

    check("GET /health", lambda: check_health(client))
    created: dict = {}
    check("POST /orders with a valid order", lambda: check_create(client, created))
    if "body" in created:
        check("GET /orders/{id} for the created order", lambda: check_read_back(client, created["body"]))
    check("GET /orders/{id} for an unknown id", lambda: check_unknown_id(client))
    for name, body, raw in INVALID:
        check(f"POST /orders with {name}", lambda body=body, raw=raw: check_invalid(client, body, raw))
    check("POST /orders with the largest allowed order", lambda: check_largest(client))
    check("POST /orders with unknown fields", lambda: check_unknown_fields(client))
    check("200 concurrent POST /orders, then GET each", lambda: check_concurrent(client))
    return failures


def log_problems(stdout: Path, sent: int) -> list[str]:
    lines = stdout.read_text(errors="replace").splitlines() if stdout.exists() else []
    good = 0
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and all(key in entry for key in LOG_KEYS):
            good += 1
    if good >= sent:
        return []
    sample = "\n".join(lines[-5:]) or "(nothing)"
    return [
        f"request log: expected at least {sent} stdout lines that are JSON objects with the top-level keys "
        f"method, path, status, and durationMs (one per request); found {good}. Last stdout lines:\n{sample}"
    ]


def shutdown_problems(exited: bool, code: int | None) -> list[str]:
    if not exited:
        return ["SIGTERM: the service did not exit within 10 seconds"]
    # 143 is the JVM's exit after its shutdown hooks run; uvicorn re-raises SIGTERM after a clean shutdown (-15).
    if code in (0, 143, -15):
        return []
    if code is not None and code < 0:
        return [f"SIGTERM: the service died from signal {-code} instead of shutting down"]
    return [f"SIGTERM: the service exited with status {code}; a clean shutdown exits with 0"]
