FILE: main.py
```python
import json
import os
import sys
import time
import uuid
import signal
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator

# --- Models ---

class Item(BaseModel):
    sku: Annotated[str, Field(min_length=1, max_length=32)]
    quantity: Annotated[int, Field(ge=1, le=100)]
    unitPriceCents: Annotated[int, Field(ge=1, le=1000000)]

class OrderRequest(BaseModel):
    customerId: Annotated[str, Field(min_length=1, max_length=64)]
    items: Annotated[list[Item], Field(min_length=1, max_length=50)]

    model_config = {"extra": "ignore"}

class OrderResponse(BaseModel):
    id: str
    customerId: str
    items: list[Item]
    totalCents: int
    createdAt: str

    model_config = {"extra": "ignore"}

class ErrorResponse(BaseModel):
    error: str

# --- In-Memory Store ---

class OrderStore:
    def __init__(self):
        self._orders: dict[str, OrderResponse] = {}
        self._lock = asyncio.Lock()

    async def create_order(self, request: OrderRequest) -> OrderResponse:
        order_id = uuid.uuid4().hex  # UUID v4 hex string
        total_cents = sum(item.quantity * item.unitPriceCents for item in request.items)
        created_at = datetime.now(timezone.utc).isoformat()
        
        order = OrderResponse(
            id=order_id,
            customerId=request.customerId,
            items=request.items,
            totalCents=total_cents,
            createdAt=created_at
        )
        
        async with self._lock:
            self._orders[order_id] = order
            
        return order

    async def get_order(self, order_id: str) -> OrderResponse | None:
        async with self._lock:
            return self._orders.get(order_id)

    async def delete_order(self, order_id: str) -> None:
        async with self._lock:
            if order_id in self._orders:
                del self._orders[order_id]

store = OrderStore()

# --- Lifespan / Graceful Shutdown ---

shutdown_event = asyncio.Event()

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    
    def signal_handler():
        shutdown_event.set()
        
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
        
    yield
    
    # Shutdown
    shutdown_event.set()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.remove_signal_handler(sig)

app = FastAPI(lifespan=lifespan)

# --- Middleware for Logging ---

@app.middleware("http")
async def log_request(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start_time) * 1000)
    
    log_data = {
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "durationMs": duration_ms
    }
    
    # Log to stdout as JSON
    print(json.dumps(log_data), flush=True)
    
    return response

# --- Routes ---

@app.post("/orders", status_code=201)
async def create_order(req: OrderRequest):
    try:
        order = await store.create_order(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
    
    # Return 201 with Location header
    response = JSONResponse(
        content=order.model_dump(),
        status_code=201,
        headers={"Location": f"/orders/{order.id}"}
    )
    return response

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    order = await store.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/health")
async def health():
    return {"status": "ok"}

# --- Custom Validation Error Handler ---

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Extract validation errors
    errors = exc.errors()
    error_messages = []
    for err in errors:
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        msg = err.get("msg", "")
        error_messages.append(f"{loc}: {msg}")
    
    error_msg = "; ".join(error_messages) if error_messages else "Validation failed"
    return JSONResponse(
        status_code=400,
        content={"error": error_msg}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # For 404s, return standard format
    if exc.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={"error": exc.detail}
        )
    
    # For other HTTP errors
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )

# --- Entry Point ---

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    
    # Run uvicorn and wait for shutdown event
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
```