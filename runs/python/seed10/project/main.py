import os
import sys
import uuid
import time
import json
import logging
import signal
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, ConfigDict

# Configure logging to output JSON lines to stdout
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "method": getattr(record, "method", None),
            "path": getattr(record, "path", None),
            "status": getattr(record, "status", None),
            "durationMs": getattr(record, "duration_ms", None),
            "message": record.getMessage(),
            "level": record.levelname,
        }
        return json.dumps(log_data)

logger = logging.getLogger("orders_service")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)

# --- Pydantic Models ---

class Item(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    sku: str = Field(..., min_length=1, max_length=32)
    quantity: int = Field(..., ge=1, le=100)
    unitPriceCents: int = Field(..., ge=1, le=1000000)

class OrderRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    customerId: str = Field(..., min_length=1, max_length=64)
    items: List[Item] = Field(..., min_length=1, max_length=50)

class OrderResponse(BaseModel):
    id: str
    customerId: str
    items: List[Item]
    totalCents: int
    createdAt: str

# --- In-Memory Store ---

class OrderStore:
    def __init__(self):
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._lock = __import__('threading').Lock()

    def create_order(self, order_id: str, request: OrderRequest, created_at: datetime) -> OrderResponse:
        total_cents = sum(item.quantity * item.unitPriceCents for item in request.items)
        
        order_data = {
            "id": order_id,
            "customerId": request.customerId,
            "items": [item.model_dump() for item in request.items],
            "totalCents": total_cents,
            "createdAt": created_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        with self._lock:
            self._orders[order_id] = order_data
            
        return OrderResponse(
            id=order_id,
            customerId=request.customerId,
            items=request.items,
            totalCents=total_cents,
            createdAt=order_data["createdAt"]
        )

    def get_order(self, order_id: str) -> Optional[OrderResponse]:
        with self._lock:
            data = self._orders.get(order_id)
        
        if data is None:
            return None
            
        return OrderResponse(
            id=data["id"],
            customerId=data["customerId"],
            items=[Item(**item) for item in data["items"]],
            totalCents=data["totalCents"],
            createdAt=data["createdAt"]
        )

store = OrderStore()

# --- FastAPI App ---

app = FastAPI(title="Orders Service")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start_time) * 1000)
    
    logger.info(
        f"{request.method} {request.url.path} {response.status_code} {duration_ms}ms",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms
        }
    )
    
    return response

@app.post("/orders", status_code=201)
async def create_order(request: OrderRequest):
    order_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)
    
    response = store.create_order(order_id, request, created_at)
    
    return JSONResponse(
        content=response.model_dump(),
        status_code=201,
        headers={"Location": f"/orders/{order_id}"}
    )

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    order = store.get_order(order_id)
    if order is None:
        # Return 404 with {"error": "Order not found"}
        return JSONResponse(
            status_code=404,
            content={"error": "Order not found"}
        )
    
    return order

@app.get("/health")
async def health():
    return {"status": "ok"}

# --- Error Handlers ---

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Extract the first error message for simplicity
    errors = exc.errors()
    if errors:
        # Use the 'msg' field from the first error
        msg = errors[0].get('msg', 'Validation error')
    else:
        msg = 'Validation error'
        
    return JSONResponse(
        status_code=400,
        content={"error": msg}
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )

# --- Graceful Shutdown ---

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    loop = __import__('asyncio').get_running_loop()
    
    def signal_handler():
        # Stop accepting new connections
        app.state.should_exit = True
        # Uvicorn will handle the rest if we exit the main loop or call shutdown
        # We'll rely on uvicorn's signal handling or explicit exit
        import os
        os._exit(0)
        
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
        
    yield
    
    # Shutdown
    logger.info("Shutting down gracefully")

app.router.lifespan_context = lifespan

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
