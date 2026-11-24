import os
import sys
import uuid
import time
import json
import logging
import signal
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# --- Data Models ---

class Item(BaseModel):
    sku: str = Field(..., min_length=1, max_length=32)
    quantity: int = Field(..., ge=1, le=100)
    unitPriceCents: int = Field(..., ge=1, le=1000000)

    class Config:
        # Ignore unknown fields as per spec
        extra = "ignore"

class OrderRequest(BaseModel):
    customerId: str = Field(..., min_length=1, max_length=64)
    items: List[Item] = Field(..., min_length=1, max_length=50)

    class Config:
        # Ignore unknown fields as per spec
        extra = "ignore"

class OrderResponse(BaseModel):
    id: str
    customerId: str
    items: List[Item]
    totalCents: int
    createdAt: str

    class Config:
        use_enum_values = False

# --- In-Memory Store ---

class OrderStore:
    def __init__(self):
        self._orders: Dict[str, OrderResponse] = {}
        self._lock = asyncio.Lock()

    async def create_order(self, request: OrderRequest) -> OrderResponse:
        order_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        total_cents = 0
        for item in request.items:
            total_cents += item.quantity * item.unitPriceCents

        response_data = {
            "id": order_id,
            "customerId": request.customerId,
            "items": [item.model_dump() for item in request.items],
            "totalCents": total_cents,
            "createdAt": now
        }
        
        order = OrderResponse(**response_data)
        
        async with self._lock:
            self._orders[order_id] = order
            
        return order

    async def get_order(self, order_id: str) -> Optional[OrderResponse]:
        async with self._lock:
            return self._orders.get(order_id)

store = OrderStore()

# --- FastAPI App ---

app = FastAPI()

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    response = await call_next(request)
    
    duration_ms = (time.time() - start_time) * 1000
    
    # Log the request directly to stdout as JSON
    log_entry = {
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "durationMs": round(duration_ms, 2)
    }
    print(json.dumps(log_entry), flush=True)
    
    return response

@app.post("/orders", status_code=201)
async def create_order(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    try:
        order_req = OrderRequest(**body)
    except Exception as e:
        # Pydantic validation errors
        if hasattr(e, 'errors') and e.errors():
            error_msg = e.errors()[0]['msg']
        else:
            error_msg = str(e)
        raise HTTPException(status_code=400, detail=error_msg)

    order = await store.create_order(order_req)
    
    # Return 201 with Location header
    return JSONResponse(
        status_code=201,
        content=order.model_dump(),
        headers={"Location": f"/orders/{order.id}"}
    )

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    order = await store.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order.model_dump()

@app.get("/health")
async def health():
    return {"status": "ok"}

# --- Custom Exception Handlers to return "error" field ---

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error"}
    )

# --- Graceful Shutdown ---

def setup_shutdown():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    event = asyncio.Event()

    def handle_signal(signum, frame):
        event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    
    return event

shutdown_event = setup_shutdown()

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8080))
    
    async def main():
        config = uvicorn.Config(
            "main:app",
            host="0.0.0.0",
            port=port,
            log_level="error", # Disable uvicorn logs to avoid cluttering stdout/stderr
            access_log=False
        )
        server = uvicorn.Server(config)
        
        # Start server
        task = asyncio.create_task(server.serve())
        
        # Wait for shutdown signal
        await shutdown_event.wait()
        
        # Graceful shutdown
        server.should_exit = True
        await server.shutdown()

    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
