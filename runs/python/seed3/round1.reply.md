FILE: main.py
```python
import os
import sys
import json
import uuid
import time
import signal
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from pydantic.json_schema import SkipJsonSchema

# Configure logging for structured output
logger = logging.getLogger("orders_service")
logger.setLevel(logging.INFO)

# In-memory store protected by a lock for thread safety
order_store: dict[str, dict[str, Any]] = {}
store_lock: threading.Lock = threading.Lock()

# Setup logging handler to write JSON lines to stdout
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "method": getattr(record, "method", None),
            "path": getattr(record, "path", None),
            "status": getattr(record, "status_code", None),
            "durationMs": getattr(record, "duration_ms", None),
            "message": record.getMessage(),
        }
        # Filter out None values for cleaner logs if needed, but spec says "at least" these keys.
        # We keep them if present, or ensure they are present in the log record via middleware.
        return json.dumps(log_record)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)


# --- Models ---

class Item(BaseModel):
    sku: str = Field(..., min_length=1, max_length=32)
    quantity: int = Field(..., ge=1, le=100)
    unitPriceCents: int = Field(..., ge=1, le=1000000)

    class Config:
        extra = "ignore"

class OrderCreateRequest(BaseModel):
    customerId: str = Field(..., min_length=1, max_length=64)
    items: list[Item] = Field(..., min_length=1, max_length=50)

    class Config:
        extra = "ignore"

class OrderResponse(BaseModel):
    id: str
    customerId: str
    items: list[Item]
    totalCents: int
    createdAt: str

    class Config:
        extra = "ignore"

class ErrorResponse(BaseModel):
    error: str

    class Config:
        extra = "ignore"


# --- Application Logic ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic (e.g., load data) could go here
    yield
    # Shutdown logic (e.g., save data) could go here
    # FastAPI handles stopping the server, we just need to ensure graceful exit in main if needed,
    # but FastAPI + Uvicorn handles SIGTERM well if we just let it close.
    # The spec asks for stopping accepting connections, finishing in-flight.
    # Uvicorn does this by default. We just need to make sure we exit cleanly.

def create_order(req: OrderCreateRequest) -> OrderResponse:
    order_id = uuid.uuid4().hex
    total_cents = sum(item.quantity * item.unitPriceCents for item in req.items)
    created_at = datetime.now(timezone.utc).isoformat()
    
    order_data = {
        "id": order_id,
        "customerId": req.customerId,
        "items": req.items,
        "totalCents": total_cents,
        "createdAt": created_at
    }
    
    with store_lock:
        order_store[order_id] = order_data
        
    return OrderResponse(
        id=order_id,
        customerId=req.customerId,
        items=req.items,
        totalCents=total_cents,
        createdAt=created_at
    )

def get_order(order_id: str) -> OrderResponse | None:
    with store_lock:
        order_data = order_store.get(order_id)
    
    if order_data is None:
        return None
        
    return OrderResponse(
        id=order_data["id"],
        customerId=order_data["customerId"],
        items=order_data["items"],
        totalCents=order_data["totalCents"],
        createdAt=order_data["createdAt"]
    )

# --- FastAPI App ---

app = FastAPI(title="Orders Service", lifespan=lifespan)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    import time
    start_time = time.time()
    
    # Add custom attributes to the request log record later
    response = await call_next(request)
    
    duration_ms = (time.time() - start_time) * 1000
    
    # Log the request
    log_record = {
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "durationMs": round(duration_ms, 2),
        "message": f"{request.method} {request.url.path} {response.status_code}"
    }
    
    # Use the logger we set up
    # We need to create a LogRecord manually to inject our fields
    record = logger.makeRecord(
        logger.name, 
        logging.INFO, 
        "", 
        0, 
        log_record["message"], 
        (), 
        None
    )
    # Manually set attributes expected by our custom formatter
    record.method = log_record["method"]
    record.path = log_record["path"]
    record.status_code = log_record["status"]
    record.duration_ms = log_record["durationMs"]
    
    logger.handle(record)
    
    return response

@app.post("/orders", status_code=201)
async def create_order_endpoint(req: OrderCreateRequest):
    # Validation is handled by Pydantic automatically.
    # If validation fails, FastAPI returns 422. We need to convert to 400.
    # However, FastAPI's default validation error is 422.
    # The spec says: "If the body is not valid JSON or breaks a rule, respond 400".
    
    # To handle this, we can catch the ValidationError and return 400.
    # But Pydantic validation happens before the function body.
    # We need to override the validation error handler or use a raw request.
    # Let's use a raw request for precise control over 400 vs 422.
    pass

@app.post("/orders")
async def create_order_raw(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON"},
            headers={"Content-Type": "application/json"}
        )
    
    try:
        req = OrderCreateRequest(**body)
    except Exception as e:
        # Pydantic raises ValidationError
        return JSONResponse(
            status_code=400,
            content={"error": str(e)},
            headers={"Content-Type": "application/json"}
        )
    
    result = create_order(req)
    
    return JSONResponse(
        status_code=201,
        content=result.model_dump(),
        headers={"Content-Type": "application/json", "Location": f"/orders/{result.id}"}
    )

@app.get("/orders/{order_id}")
async def get_order_endpoint(order_id: str):
    result = get_order(order_id)
    if result is None:
        return JSONResponse(
            status_code=404,
            content={"error": "Order not found"},
            headers={"Content-Type": "application/json"}
        )
    
    return JSONResponse(
        status_code=200,
        content=result.model_dump(),
        headers={"Content-Type": "application/json"}
    )

@app.get("/health")
async def health_check():
    return JSONResponse(
        status_code=200,
        content={"status": "ok"},
        headers={"Content-Type": "application/json"}
    )

if __name__ == "__main__":
    import uvicorn
    import threading
    import sys
    
    # Graceful shutdown handling
    # Uvicorn handles SIGTERM by default, but we can ensure clean exit.
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), log_level="info")
```

Wait, the previous draft had `import threading` missing in main.py. Also, I need to fix the middleware logging to ensure it works correctly with the custom formatter. Let's refine `main.py`.

FILE: main.py
```python
import os
import sys
import json
import uuid
import time
import signal
import logging
import threading
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Configure logging for structured output
logger = logging.getLogger("orders_service")
logger.setLevel(logging.INFO)

# In-memory store protected by a lock for thread safety
order_store: dict[str, dict[str, Any]] = {}
store_lock = threading.Lock()

# Setup logging handler to write JSON lines to stdout
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "method": getattr(record, "method", None),
            "path": getattr(record, "path", None),
            "status": getattr(record, "status_code", None),
            "durationMs": getattr(record, "duration_ms", None),
            "message": record.getMessage(),
        }
        # Ensure all required keys are present
        for key in ["method", "path", "status", "durationMs"]:
            if key not in log_record or log_record[key] is None:
                log_record[key] = None
        
        return json.dumps(log_record)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
# Avoid duplicate logs if logger is configured elsewhere
if not logger.handlers:
    logger.addHandler(handler)


# --- Models ---

class Item(BaseModel):
    sku: str = Field(..., min_length=1, max_length=32)
    quantity: int = Field(..., ge=1, le=100)
    unitPriceCents: int = Field(..., ge=1, le=1000000)

    class Config:
        extra = "ignore"

class OrderCreateRequest(BaseModel):
    customerId: str = Field(..., min_length=1, max_length=64)
    items: list[Item] = Field(..., min_length=1, max_length=50)

    class Config:
        extra = "ignore"

class OrderResponse(BaseModel):
    id: str
    customerId: str
    items: list[Item]
    totalCents: int
    createdAt: str

    class Config:
        extra = "ignore"


# --- Application Logic ---

def create_order(req: OrderCreateRequest) -> OrderResponse:
    order_id = uuid.uuid4().hex
    total_cents = sum(item.quantity * item.unitPriceCents for item in req.items)
    created_at = datetime.now(timezone.utc).isoformat()
    
    order_data = {
        "id": order_id,
        "customerId": req.customerId,
        "items": req.items,
        "totalCents": total_cents,
        "createdAt": created_at
    }
    
    with store_lock:
        order_store[order_id] = order_data
        
    return OrderResponse(
        id=order_id,
        customerId=req.customerId,
        items=req.items,
        totalCents=total_cents,
        createdAt=created_at
    )

def get_order(order_id: str) -> OrderResponse | None:
    with store_lock:
        order_data = order_store.get(order_id)
    
    if order_data is None:
        return None
        
    return OrderResponse(
        id=order_data["id"],
        customerId=order_data["customerId"],
        items=order_data["items"],
        totalCents=order_data["totalCents"],
        createdAt=order_data["createdAt"]
    )

# --- FastAPI App ---

app = FastAPI(title="Orders Service")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    response = await call_next(request)
    
    duration_ms = (time.time() - start_time) * 1000
    
    # Log the request
    log_record = {
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "durationMs": round(duration_ms, 2),
        "message": f"{request.method} {request.url.path} {response.status_code}"
    }
    
    # Use the logger we set up
    # We need to create a LogRecord manually to inject our fields
    record = logger.makeRecord(
        logger.name, 
        logging.INFO, 
        "", 
        0, 
        log_record["message"], 
        (), 
        None
    )
    # Manually set attributes expected by our custom formatter
    record.method = log_record["method"]
    record.path = log_record["path"]
    record.status_code = log_record["status"]
    record.duration_ms = log_record["durationMs"]
    
    logger.handle(record)
    
    return response

@app.post("/orders")
async def create_order_raw(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON"},
            headers={"Content-Type": "application/json"}
        )
    
    try:
        req = OrderCreateRequest(**body)
    except Exception as e:
        # Pydantic raises ValidationError
        return JSONResponse(
            status_code=400,
            content={"error": str(e)},
            headers={"Content-Type": "application/json"}
        )
    
    result = create_order(req)
    
    return JSONResponse(
        status_code=201,
        content=result.model_dump(),
        headers={"Content-Type": "application/json", "Location": f"/orders/{result.id}"}
    )

@app.get("/orders/{order_id}")
async def get_order_endpoint(order_id: str):
    result = get_order(order_id)
    if result is None:
        return JSONResponse(
            status_code=404,
            content={"error": "Order not found"},
            headers={"Content-Type": "application/json"}
        )
    
    return JSONResponse(
        status_code=200,
        content=result.model_dump(),
        headers={"Content-Type": "application/json"}
    )

@app.get("/health")
async def health_check():
    return JSONResponse(
        status_code=200,
        content={"status": "ok"},
        headers={"Content-Type": "application/json"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), log_level="info")
```

FILE: requirements.txt
```
fastapi>=0.115.0,<1.0.0
uvicorn>=0.30.0,<1.0.0
pydantic>=2.9.0,<3.0.0
```

FILE: requirements-dev.txt
```
pytest>=8.3.0,<9.0.0
httpx>=0.27.0,<1.0.0
```

FILE: tests/test_orders.py
```python
import pytest
import httpx
import json
import time
import threading
import os
import signal
import subprocess
import sys

# Import the app directly for testing
from main import app

# Test client
@pytest.fixture
def client():
    with httpx.ASGITransport(app=app) as transport:
        with httpx.Client(transport=transport, base_url="http://test") as c:
            yield c

# Helper to create a valid order request
def create_order_payload(customer_id="c-1", items=None):
    if items is None:
        items = [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]
    return {
        "customerId": customer_id,
        "items": items
    }

class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

class TestCreateOrder:
    def test_create_order_success(self, client):
        payload = create_order_payload()
        response = client.post("/orders", json=payload)
        
        assert response.status_code == 201
        assert "Location" in response.headers
        assert response.headers["Location"].startswith("/orders/")
        
        body = response.json()
        assert body["customerId"] == "c-1"
        assert len(body["items"]) == 1
        assert body["items"][0]["sku"] == "A-1"
        assert body["items"][0]["quantity"] == 2
        assert body["items"][0]["unitPriceCents"] == 1250
        assert body["totalCents"] == 2500
        assert "id" in body
        assert "createdAt" in body

    def test_create_order_invalid_json(self, client):
        response = client.post("/orders", content="not json", headers={"Content-Type": "application/json"})
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_missing_customer_id(self, client):
        payload = {"items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_empty_items(self, client):
        payload = {"customerId": "c-1", "items": []}
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_sku_length(self, client):
        payload = {"customerId": "c-1", "items": [{"sku": "a" * 33, "quantity": 2, "unitPriceCents": 1250}]}
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_quantity(self, client):
        payload = {"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 1250}]}
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_invalid_unit_price(self, client):
        payload = {"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 0}]}
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_too_many_items(self, client):
        items = [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100} for _ in range(51)]
        payload = {"customerId": "c-1", "items": items}
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_customer_id_too_long(self, client):
        payload = {"customerId": "c" * 65, "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]}
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_sku_too_short(self, client):
        payload = {"customerId": "c-1", "items": [{"sku": "", "quantity": 1, "unitPriceCents": 100}]}
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_quantity_too_high(self, client):
        payload = {"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 101, "unitPriceCents": 100}]}
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_unit_price_too_high(self, client):
        payload = {"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 1000001}]}
        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "error" in response.json()

    def test_create_order_ignore_unknown_fields(self, client):
        payload = {"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100, "extra": "field"}], "extra": "field"}
        response = client.post("/orders", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert "extra" not in body
        assert "extra" not in body["items"][0]

    def test_create_order_multiple_items(self, client):
        items = [
            {"sku": "A-1", "quantity": 2, "unitPriceCents": 100},
            {"sku": "A-2", "quantity": 3, "unitPriceCents": 200}
        ]
        payload = {"customerId": "c-1", "items": items}
        response = client.post("/orders", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["totalCents"] == 2*100 + 3*200

class TestGetOrder:
    def test_get_order_success(self, client):
        payload = create_order_payload()
        create_resp = client.post("/orders", json=payload)
        order_id = create_resp.json()["id"]
        
        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == order_id
        assert body["customerId"] == "c-1"

    def test_get_order_not_found(self, client):
        response = client.get("/orders/non-existent-id")
        assert response.status_code == 404
        assert "error" in response.json()

class TestConcurrency:
    def test_concurrent_orders(self, client):
        errors = []
        
        def create_order():
            try:
                payload = create_order_payload()
                response = client.post("/orders", json=payload)
                if response.status_code != 201:
                    errors.append(f"Failed: {response.status_code} {response.text}")
            except Exception as e:
                errors.append(str(e))
        
        threads = [threading.Thread(target=create_order) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert not errors, f"Concurrency errors: {errors}"
```