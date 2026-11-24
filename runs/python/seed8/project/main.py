import asyncio
import json
import os
import signal
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

# --- Models ---

class OrderItem(BaseModel):
    sku: str = Field(..., min_length=1, max_length=32)
    quantity: int = Field(..., ge=1, le=100)
    unitPriceCents: int = Field(..., ge=1, le=1000000)

class CreateOrderRequest(BaseModel):
    customerId: str = Field(..., min_length=1, max_length=64)
    items: list[OrderItem] = Field(..., min_length=1, max_length=50)

    @field_validator("items")
    @classmethod
    def validate_items_not_empty(cls, v: list[OrderItem]) -> list[OrderItem]:
        if not v:
            raise ValueError("items must not be empty")
        return v

class OrderResponse(BaseModel):
    id: str
    customerId: str
    items: list[OrderItem]
    totalCents: int
    createdAt: str

# --- Store ---

class InMemoryStore:
    def __init__(self):
        self._orders: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create_order(self, request: CreateOrderRequest) -> OrderResponse:
        order_id = uuid.uuid4().hex
        total_cents = sum(item.quantity * item.unitPriceCents for item in request.items)
        now = datetime.now(timezone.utc)
        created_at = now.isoformat()

        order_data = {
            "id": order_id,
            "customerId": request.customerId,
            "items": [item.model_dump() for item in request.items],
            "totalCents": total_cents,
            "createdAt": created_at,
        }

        async with self._lock:
            self._orders[order_id] = order_data

        return OrderResponse(
            id=order_id,
            customerId=request.customerId,
            items=request.items,
            totalCents=total_cents,
            createdAt=created_at,
        )

    async def get_order(self, order_id: str) -> OrderResponse | None:
        async with self._lock:
            order_data = self._orders.get(order_id)
        
        if not order_data:
            return None
        
        return OrderResponse(**order_data)

store = InMemoryStore()

# --- App Setup ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic if needed
    yield
    # Shutdown logic handled by signal handler in main block or here if preferred.
    # We'll handle graceful shutdown via the signal handler in the main block 
    # to ensure uvicorn's shutdown hook interacts correctly.

app = FastAPI(lifespan=lifespan)

# --- Logging Middleware ---

@app.middleware("http")
async def log_request(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
        return response
    finally:
        duration_ms = (time.time() - start_time) * 1000
        log_entry = {
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "durationMs": round(duration_ms, 2),
        }
        # Write JSON log line to stdout
        print(json.dumps(log_entry), flush=True)

# --- Routes ---

@app.post("/orders", status_code=201)
async def create_order(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON body"}
        )

    try:
        validated_data = CreateOrderRequest(**body)
    except Exception as e:
        # Pydantic validation errors contain details in .errors()
        # We flatten them or take the first one for a simple message.
        # The prompt asks for {"error": "<message>"}.
        errors = e.errors()
        error_msg = f"Validation error: {errors[0]['msg']}" if errors else "Validation failed"
        return JSONResponse(
            status_code=400,
            content={"error": error_msg}
        )

    order = await store.create_order(validated_data)
    
    response = JSONResponse(
        status_code=201,
        content=order.model_dump()
    )
    response.headers["Location"] = f"/orders/{order.id}"
    return response

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    order = await store.get_order(order_id)
    if not order:
        return JSONResponse(
            status_code=404,
            content={"error": "Order not found"}
        )
    return JSONResponse(
        status_code=200,
        content=order.model_dump()
    )

@app.get("/health")
async def health_check():
    return JSONResponse(
        status_code=200,
        content={"status": "ok"}
    )

if __name__ == "__main__":
    import uvicorn
    import signal as signal_module

    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 8080))

    # Graceful shutdown setup
    shutdown_event = asyncio.Event()

    def handle_signal(signum, frame):
        shutdown_event.set()

    signal_module.signal(signal_module.SIGTERM, handle_signal)
    signal_module.signal(signal_module.SIGINT, handle_signal)

    async def run():
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        
        # Handle shutdown
        async def shutdown():
            server.should_exit = True
            await asyncio.sleep(10) # Wait up to 10 seconds for in-flight requests
            sys.exit(0)

        # Start server
        task = asyncio.create_task(server.serve())
        
        # Wait for shutdown signal
        await shutdown_event.wait()
        print("Shutting down gracefully...", flush=True)
        await shutdown()

    asyncio.run(run())
