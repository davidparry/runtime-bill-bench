"""A minimal stdlib implementation of spec/orders.md, used to prove the acceptance test is passable."""

import json
import os
import signal
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ORDERS: dict[str, dict] = {}
LOCK = threading.Lock()


def validate(body) -> str | None:
    if not isinstance(body, dict):
        return "body must be a JSON object"
    customer = body.get("customerId")
    if not isinstance(customer, str) or not 1 <= len(customer) <= 64:
        return "customerId must be a string of 1 to 64 characters"
    items = body.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 50:
        return "items must have 1 to 50 entries"
    for entry in items:
        if not isinstance(entry, dict):
            return "each item must be an object"
        sku = entry.get("sku")
        if not isinstance(sku, str) or not 1 <= len(sku) <= 32:
            return "sku must be a string of 1 to 32 characters"
        for key, high in (("quantity", 100), ("unitPriceCents", 1000000)):
            value = entry.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= high:
                return f"{key} must be an integer from 1 to {high}"
    return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def send_json(self, status: int, payload: dict, headers: dict | None = None):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)
        self.status = status

    def handle_one(self, method: str):
        started = time.perf_counter()
        self.status = 500
        try:
            if method == "GET" and self.path == "/health":
                self.send_json(200, {"status": "ok"})
            elif method == "GET" and self.path.startswith("/orders/"):
                with LOCK:
                    found = ORDERS.get(self.path.removeprefix("/orders/"))
                if found:
                    self.send_json(200, found)
                else:
                    self.send_json(404, {"error": "order not found"})
            elif method == "POST" and self.path == "/orders":
                length = int(self.headers.get("Content-Length", 0))
                try:
                    body = json.loads(self.rfile.read(length))
                except ValueError:
                    self.send_json(400, {"error": "body is not valid JSON"})
                    return
                problem = validate(body)
                if problem:
                    self.send_json(400, {"error": problem})
                    return
                items = [{k: e[k] for k in ("sku", "quantity", "unitPriceCents")} for e in body["items"]]
                created = {
                    "id": str(uuid.uuid4()),
                    "customerId": body["customerId"],
                    "items": items,
                    "totalCents": sum(e["quantity"] * e["unitPriceCents"] for e in items),
                    "createdAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                }
                with LOCK:
                    ORDERS[created["id"]] = created
                self.send_json(201, created, {"Location": f"/orders/{created['id']}"})
            else:
                self.send_json(404, {"error": "not found"})
        finally:
            line = {"method": method, "path": self.path, "status": self.status,
                    "durationMs": round((time.perf_counter() - started) * 1000, 3)}
            sys.stdout.write(json.dumps(line) + "\n")
            sys.stdout.flush()

    def do_GET(self):
        self.handle_one("GET")

    def do_POST(self):
        self.handle_one("POST")


class Server(ThreadingHTTPServer):
    request_queue_size = 128


def main():
    server = Server(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler)
    server.daemon_threads = True
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    server.serve_forever()
    server.server_close()


if __name__ == "__main__":
    main()
