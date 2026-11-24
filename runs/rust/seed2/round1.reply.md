FILE: Cargo.toml
```toml
[package]
name = "orders"
version = "0.1.0"
edition = "2021"

[dependencies]
axum = { version = "0.7", features = ["json"] }
tokio = { version = "1", features = ["full"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
uuid = { version = "1", features = ["v4", "serde"] }
chrono = { version = "0.4", features = ["serde"] }
tower = "0.5"
tower-http = { version = "0.5", features = ["trace"] }

[dev-dependencies]
hyper = { version = "1", features = ["full"] }
hyper-util = { version = "0.1", features = ["full"] }
http-body-util = "0.1"
```

FILE: src/main.rs
```rust
use axum::{
    extract::{Path, State},
    http::{HeaderName, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
    time::Instant,
};
use tokio::signal;
use uuid::Uuid;

// --- Models ---

#[derive(Debug, Deserialize)]
struct CreateOrderRequest {
    customer_id: String,
    items: Vec<OrderItem>,
}

#[derive(Debug, Deserialize)]
struct OrderItem {
    sku: String,
    quantity: i64,
    unit_price_cents: i64,
}

#[derive(Debug, Serialize)]
struct OrderResponse {
    id: String,
    customer_id: String,
    items: Vec<OrderItem>,
    total_cents: i64,
    created_at: String,
}

// --- State ---

#[derive(Clone)]
struct AppState {
    orders: Arc<Mutex<HashMap<String, OrderResponse>>>,
}

impl AppState {
    fn new() -> Self {
        AppState {
            orders: Arc::new(Mutex::new(HashMap::new())),
        }
    }
}

// --- Handlers ---

async fn create_order(
    State(state): State<AppState>,
    Json(payload): Json<CreateOrderRequest>,
) -> Result<Response, AppError> {
    // Validation
    if payload.customer_id.len() < 1 || payload.customer_id.len() > 64 {
        return Err(AppError::BadRequest("customerId must be 1 to 64 characters".into()));
    }

    if payload.items.len() < 1 || payload.items.len() > 50 {
        return Err(AppError::BadRequest(
            "items must contain 1 to 50 entries".into(),
        ));
    }

    let mut total_cents: i64 = 0;
    let mut validated_items = Vec::with_capacity(payload.items.len());

    for item in payload.items {
        if item.sku.len() < 1 || item.sku.len() > 32 {
            return Err(AppError::BadRequest(
                "sku must be 1 to 32 characters".into(),
            ));
        }
        if item.quantity < 1 || item.quantity > 100 {
            return Err(AppError::BadRequest(
                "quantity must be 1 to 100".into(),
            ));
        }
        if item.unit_price_cents < 1 || item.unit_price_cents > 1_000_000 {
            return Err(AppError::BadRequest(
                "unitPriceCents must be 1 to 1000000".into(),
            ));
        }

        // Check for overflow before adding
        let item_total = item.quantity * item.unit_price_cents;
        if item_total < 0 {
             return Err(AppError::BadRequest(
                "item total overflow".into(),
            ));
        }
        
        total_cents = total_cents
            .checked_add(item_total)
            .ok_or_else(|| AppError::BadRequest("totalCents overflow".into()))?;
        
        validated_items.push(item);
    }

    let order_id = Uuid::new_v4().to_string();
    let created_at = Utc::now().to_rfc3339();

    let response = OrderResponse {
        id: order_id.clone(),
        customer_id: payload.customer_id,
        items: validated_items,
        total_cents,
        created_at: created_at.clone(),
    };

    {
        let mut store = state.orders.lock().unwrap();
        store.insert(order_id, response);
    }

    let mut res = (
        StatusCode::CREATED,
        [(HeaderName::from_static("location"), format!("/orders/{}", order_id))],
        Json(OrderResponse {
            id: order_id,
            customer_id: response.customer_id.clone(),
            items: response.items.clone(),
            total_cents: response.total_cents,
            created_at: response.created_at.clone(),
        }),
    )
    .into_response();

    // Ensure content type is set explicitly for 201
    *res.status_mut() = StatusCode::CREATED;
    res.headers_mut()
        .insert(axum::http::header::CONTENT_TYPE, "application/json".into());
    
    Ok(res)
}

async fn get_order(
    State(state): State<AppState>,
    Path(order_id): Path<String>,
) -> Result<Json<OrderResponse>, AppError> {
    let store = state.orders.lock().unwrap();
    match store.get(&order_id) {
        Some(order) => Ok(Json(order.clone())),
        None => Err(AppError::NotFound(format!("Order {} not found", order_id))),
    }
}

async fn health_check() -> Json<serde_json::Value> {
    Json(serde_json::json!({"status": "ok"}))
}

// --- Error Handling & Logging ---

#[derive(Debug)]
enum AppError {
    BadRequest(String),
    NotFound(String),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, message) = match self {
            AppError::BadRequest(msg) => (StatusCode::BAD_REQUEST, msg),
            AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg),
        };

        let body = Json(serde_json::json!({"error": message}));
        let mut res = body.into_response();
        res.headers_mut()
            .insert(axum::http::header::CONTENT_TYPE, "application/json".into());
        res
    }
}

#[tokio::main]
async fn main() {
    // Initialize tracing/logging if needed, but we'll use custom log lines per request
    
    let state = AppState::new();
    let app = Router::new()
        .route("/orders", post(create_order))
        .route("/orders/{id}", get(get_order))
        .route("/health", get(health_check))
        .with_state(state);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:8080")
        .await
        .expect("Failed to bind to port 8080");

    println!("Listening on 0.0.0.0:8080");

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await
        .unwrap();
}

async fn shutdown_signal() {
    let ctrl_c = async {
        signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("failed to install signal handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }

    println!("Shutting down gracefully...");
}
```

Wait, the requirement specifies: "Write one JSON log line to standard output per request, with at least the keys "method", "path", "status", and "durationMs"."

Axum's `tower_http::Trace` layer can do this, but implementing it manually ensures we hit the exact spec without relying on default trace formats which might vary. I will replace the standard handler logic with a custom layer or wrap the handlers. Given the simplicity, I'll use `tower_http::trace::TraceLayer` but configure it to output JSON. However, `TraceLayer` default JSON format might not match exactly "method", "path", "status", "durationMs" keys without customizing the `MakeSpan` and `OnResponse`.

To be safe and precise, I will implement a simple middleware layer in `main.rs` or use a custom `tower` layer.

Let's refine `main.rs` to include the logging middleware explicitly.

FILE: src/main.rs
```rust
use axum::{
    extract::{Path, State},
    http::{HeaderName, StatusCode, Method},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
    time::Instant,
};
use tokio::signal;
use tower::{Layer, ServiceExt};
use uuid::Uuid;

// --- Models ---

#[derive(Debug, Deserialize)]
struct CreateOrderRequest {
    customer_id: String,
    items: Vec<OrderItem>,
}

#[derive(Debug, Deserialize, Clone, Serialize)]
struct OrderItem {
    sku: String,
    quantity: i64,
    unit_price_cents: i64,
}

#[derive(Debug, Clone, Serialize)]
struct OrderResponse {
    id: String,
    customer_id: String,
    items: Vec<OrderItem>,
    total_cents: i64,
    created_at: String,
}

// --- State ---

#[derive(Clone)]
struct AppState {
    orders: Arc<Mutex<HashMap<String, OrderResponse>>>,
}

impl AppState {
    fn new() -> Self {
        AppState {
            orders: Arc::new(Mutex::new(HashMap::new())),
        }
    }
}

// --- Handlers ---

async fn create_order(
    State(state): State<AppState>,
    Json(payload): Json<CreateOrderRequest>,
) -> Result<Response, AppError> {
    // Validation
    if payload.customer_id.len() < 1 || payload.customer_id.len() > 64 {
        return Err(AppError::BadRequest("customerId must be 1 to 64 characters".into()));
    }

    if payload.items.len() < 1 || payload.items.len() > 50 {
        return Err(AppError::BadRequest(
            "items must contain 1 to 50 entries".into(),
        ));
    }

    let mut total_cents: i64 = 0;
    let mut validated_items = Vec::with_capacity(payload.items.len());

    for item in &payload.items {
        if item.sku.len() < 1 || item.sku.len() > 32 {
            return Err(AppError::BadRequest(
                "sku must be 1 to 32 characters".into(),
            ));
        }
        if item.quantity < 1 || item.quantity > 100 {
            return Err(AppError::BadRequest(
                "quantity must be 1 to 100".into(),
            ));
        }
        if item.unit_price_cents < 1 || item.unit_price_cents > 1_000_000 {
            return Err(AppError::BadRequest(
                "unitPriceCents must be 1 to 1000000".into(),
            ));
        }

        let item_total = item.quantity * item.unit_price_cents;
        if item_total < 0 {
             return Err(AppError::BadRequest(
                "item total overflow".into(),
            ));
        }
        
        total_cents = total_cents
            .checked_add(item_total)
            .ok_or_else(|| AppError::BadRequest("totalCents overflow".into()))?;
    }

    let order_id = Uuid::new_v4().to_string();
    let created_at = Utc::now().to_rfc3339();

    let response = OrderResponse {
        id: order_id.clone(),
        customer_id: payload.customer_id,
        items: validated_items,
        total_cents,
        created_at: created_at.clone(),
    };

    {
        let mut store = state.orders.lock().unwrap();
        store.insert(order_id.clone(), response);
    }

    let mut res = (
        StatusCode::CREATED,
        [(HeaderName::from_static("location"), format!("/orders/{}", order_id))],
        Json(OrderResponse {
            id: order_id,
            customer_id: response.customer_id.clone(),
            items: response.items.clone(),
            total_cents: response.total_cents,
            created_at: response.created_at.clone(),
        }),
    )
    .into_response();

    res.headers_mut()
        .insert(axum::http::header::CONTENT_TYPE, "application/json".into());
    
    Ok(res)
}

async fn get_order(
    State(state): State<AppState>,
    Path(order_id): Path<String>,
) -> Result<Json<OrderResponse>, AppError> {
    let store = state.orders.lock().unwrap();
    match store.get(&order_id) {
        Some(order) => Ok(Json(order.clone())),
        None => Err(AppError::NotFound(format!("Order {} not found", order_id))),
    }
}

async fn health_check() -> Json<serde_json::Value> {
    Json(json!({"status": "ok"}))
}

// --- Error Handling ---

#[derive(Debug)]
enum AppError {
    BadRequest(String),
    NotFound(String),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, message) = match self {
            AppError::BadRequest(msg) => (StatusCode::BAD_REQUEST, msg),
            AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg),
        };

        let body = Json(json!({"error": message}));
        let mut res = body.into_response();
        res.headers_mut()
            .insert(axum::http::header::CONTENT_TYPE, "application/json".into());
        res
    }
}

// --- Logging Middleware ---

struct JsonLogger;

impl<S> Layer<S> for JsonLogger {
    type Service = JsonLoggerLayer<S>;

    fn layer(&self, service: S) -> Self::Service {
        JsonLoggerLayer { service }
    }
}

struct JsonLoggerLayer<S> {
    service: S,
}

impl<S, B> axum::extract::RequestExt for JsonLoggerLayer<S> {} // No-op for bounds

impl<S, B> tower::Service<axum::http::Request<B>> for JsonLoggerLayer<S>
where
    S: tower::Service<axum::http::Request<B>, Response = axum::http::Response<B>>,
    S::Error: std::fmt::Display,
    S::Future: Send + 'static,
    B: Send + 'static,
{
    type Response = axum::http::Response<B>;
    type Error = S::Error;
    type Future = std::pin::Pin<Box<dyn std::future::Future<Output = Result<Self::Response, Self::Error>> + Send>>;

    fn poll_ready(
        &mut self,
        cx: &mut std::task::Context<'_>,
    ) -> std::task::Poll<Result<(), Self::Error>> {
        self.service.poll_ready(cx)
    }

    fn call(&mut self, mut req: axum::http::Request<B>) -> Self::Future {
        let method = req.method().clone();
        let path = req.uri().path().to_string();
        let start = Instant::now();

        let service = self.service.clone();
        Box::pin(async move {
            let res = service.oneshot(req).await?;
            let duration = start.elapsed();
            let status = res.status().as_u16();

            let log_entry = json!({
                "method": method,
                "path": path,
                "status": status,
                "durationMs": duration.as_millis()
            });
            
            println!("{}", serde_json::to_string(&log_entry).unwrap());
            
            Ok(res)
        })
    }
}

// --- Main ---

#[tokio::main]
async fn main() {
    let state = AppState::new();
    
    let app = Router::new()
        .route("/orders", post(create_order))
        .route("/orders/{id}", get(get_order))
        .route("/health", get(health_check))
        .with_state(state);

    // Apply logging layer
    let app = app.layer(JsonLogger);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:8080")
        .await
        .expect("Failed to bind to port 8080");

    println!("Listening on 0.0.0.0:8080");

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await
        .unwrap();
}

async fn shutdown_signal() {
    let ctrl_c = async {
        signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("failed to install signal handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }

    println!("Shutting down gracefully...");
}
```

FILE: tests/integration_tests.rs
```rust
use axum::http::{HeaderName, StatusCode};
use hyper::body::Bytes;
use hyper_util::rt::TokioExecutor;
use orders::AppState; // Note: AppState is not pub in main, so we need to expose it or test via HTTP
// Since AppState is inside main, we can't easily inject it into tests unless we make it pub or use a separate test helper.
// Better approach: Spin up the server and hit it.

use std::net::SocketAddr;
use tower::ServiceBuilder;
use tower::ServiceExt; // for ready()
use axum::Router;
use tokio::sync::OnceCell;

// We need to make AppState public or create a test setup function.
// To keep files clean, I'll modify main.rs slightly to expose a test setup function if needed,
// but usually integration tests hit the network.

// However, the prompt says "Return every file in the project". I can't modify main.rs structure arbitrarily if I already returned it.
// I will make AppState pub(crate) or pub in main.rs? 
// Actually, I'll just write the integration tests to hit the server.

static ADDR: OnceCell<SocketAddr> = OnceCell::const_new();

async fn get_addr() -> &'static SocketAddr {
    ADDR.get_or_init(|| async {
        let state = orders::AppState::new();
        let app = Router::new()
            .route("/orders", axum::routing::post(orders::handlers::create_order)) // This won't work if handlers aren't pub
            .route("/orders/{id}", axum::routing::get(orders::handlers::get_order))
            .route("/health", axum::routing::get(orders::handlers::health_check))
            .with_state(state);
        
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        
        tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        
        &addr
    }).await
}

// This approach is tricky because handlers are not pub.
// I will refactor main.rs to make handlers and AppState accessible for testing, 
// OR I will write the tests to just start the binary? No, that's slow.
// I will make AppState and handlers pub(crate) or pub in main.rs?
// The prompt says "Return every file". I will update main.rs to expose what's needed.

// Actually, simpler: I'll write the tests as unit tests inside `src/main.rs` or a `src/lib.rs`?
// The prompt says "binary target".
// I'll add a `tests` directory.

// To make testing possible without changing main.rs structure too much, 
// I'll assume the test harness can run `cargo test`.
// I will write the tests in `tests/api_tests.rs` and they will use `hyper::Client` to hit the server.
// But I need to start the server first.

// Let's refine the plan:
// 1. main.rs exposes AppState and handlers as `pub` for testing? No, that's bad practice.
// 2. Instead, I'll put the logic in a separate module `app.rs` and include it in main.
// But I can only return files I create.
// I'll create `src/app.rs` and `src/main.rs`.

// Let's re-structure slightly to allow clean testing.
```

Let's do a clean re-structure to ensure testability and correctness.

FILE: Cargo.toml
```toml
[package]
name = "orders"
version = "0.1.0"
edition = "2021"

[dependencies]
axum = { version = "0.7", features = ["json"] }
tokio = { version = "1", features = ["full"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
uuid = { version = "1", features = ["v4", "serde"] }
chrono = { version = "0.4", features = ["serde"] }
tower = "0.5"

[dev-dependencies]
hyper = { version = "1", features = ["full"] }
hyper-util = { version = "0.1", features = ["full"] }
http-body-util = "0.1"
```

FILE: src/lib.rs
```rust
use axum::{
    extract::{Path, State},
    http::{HeaderName, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use uuid::Uuid;

pub mod handlers;
pub mod state;
pub mod middleware;

pub fn create_router() -> Router {
    let state = state::AppState::new();
    
    let app = Router::new()
        .route("/orders", post(handlers::create_order))
        .route("/orders/{id}", get(handlers::get_order))
        .route("/health", get(handlers::health_check))
        .with_state(state);

    // Apply logging layer
    app.layer(middleware::JsonLogger)
}

// Re-export for testing if needed, though lib.rs is often separate from binary.
// For a binary-only project, lib.rs is still good for shared logic.
```

FILE: src/state.rs
```rust
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};

#[derive(Debug, Deserialize)]
pub struct CreateOrderRequest {
    pub customer_id: String,
    pub items: Vec<OrderItem>,
}

#[derive(Debug, Deserialize, Clone, Serialize)]
pub struct OrderItem {
    pub sku: String,
    pub quantity: i64,
    pub unit_price_cents: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct OrderResponse {
    pub id: String,
    pub customer_id: String,
    pub items: Vec<OrderItem>,
    pub total_cents: i64,
    pub created_at: String,
}

#[derive(Clone)]
pub struct AppState {
    pub orders: Arc<Mutex<HashMap<String, OrderResponse>>>,
}

impl AppState {
    pub fn new() -> Self {
        AppState {
            orders: Arc::new(Mutex::new(HashMap::new())),
        }
    }
}
```

FILE: src/handlers.rs
```rust
use crate::state::{AppState, CreateOrderRequest, OrderResponse};
use axum::{
    extract::{Path, State},
    http::{HeaderName, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use chrono::Utc;
use serde_json::json;
use uuid::Uuid;

#[derive(Debug)]
pub enum AppError {
    BadRequest(String),
    NotFound(String),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, message) = match self {
            AppError::BadRequest(msg) => (StatusCode::BAD_REQUEST, msg),
            AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg),
        };

        let body = Json(json!({"error": message}));
        let mut res = body.into_response();
        res.headers_mut()
            .insert(axum::http::header::CONTENT_TYPE, "application/json".into());
        res
    }
}

pub async fn create_order(
    State(state): State<AppState>,
    Json(payload): Json<CreateOrderRequest>,
) -> Result<Response, AppError> {
    if payload.customer_id.len() < 1 || payload.customer_id.len() > 64 {
        return Err(AppError::BadRequest("customerId must be 1 to 64 characters".into()));
    }

    if payload.items.len() < 1 || payload.items.len() > 50 {
        return Err(AppError::BadRequest(
            "items must contain 1 to 50 entries".into(),
        ));
    }

    let mut total_cents: i64 = 0;
    let mut validated_items = Vec::with_capacity(payload.items.len());

    for item in &payload.items {
        if item.sku.len() < 1 || item.sku.len() > 32 {
            return Err(AppError::BadRequest(
                "sku must be 1 to 32 characters".into(),
            ));
        }
        if item.quantity < 1 || item.quantity > 100 {
            return Err(AppError::BadRequest(
                "quantity must be 1 to 100".into(),
            ));
        }
        if item.unit_price_cents < 1 || item.unit_price_cents > 1_000_000 {
            return Err(AppError::BadRequest(
                "unitPriceCents must be 1 to 1000000".into(),
            ));
        }

        let item_total = item.quantity * item.unit_price_cents;
        if item_total < 0 {
             return Err(AppError::BadRequest(
                "item total overflow".into(),
            ));
        }
        
        total_cents = total_cents
            .checked_add(item_total)
            .ok_or_else(|| AppError::BadRequest("totalCents overflow".into()))?;
    }

    let order_id = Uuid::new_v4().to_string();
    let created_at = Utc::now().to_rfc3339();

    let response = OrderResponse {
        id: order_id.clone(),
        customer_id: payload.customer_id,
        items: validated_items,
        total_cents,
        created_at: created_at.clone(),
    };

    {
        let mut store = state.orders.lock().unwrap();
        store.insert(order_id.clone(), response);
    }

    let mut res = (
        StatusCode::CREATED,
        [(HeaderName::from_static("location"), format!("/orders/{}", order_id))],
        Json(OrderResponse {
            id: order_id,
            customer_id: response.customer_id.clone(),
            items: response.items.clone(),
            total_cents: response.total_cents,
            created_at: response.created_at.clone(),
        }),
    )
    .into_response();

    res.headers_mut()
        .insert(axum::http::header::CONTENT_TYPE, "application/json".into());
    
    Ok(res)
}

pub async fn get_order(
    State(state): State<AppState>,
    Path(order_id): Path<String>,
) -> Result<Json<OrderResponse>, AppError> {
    let store = state.orders.lock().unwrap();
    match store.get(&order_id) {
        Some(order) => Ok(Json(order.clone())),
        None => Err(AppError::NotFound(format!("Order {} not found", order_id))),
    }
}

pub async fn health_check() -> Json<serde_json::Value> {
    Json(json!({"status": "ok"}))
}
```

FILE: src/middleware.rs
```rust
use axum::http::{HeaderName, Method, Request};
use serde_json::json;
use std::time::Instant;
use tower::Layer;
use tower::Service;

pub struct JsonLogger;

impl<S> Layer<S> for JsonLogger {
    type Service = JsonLoggerLayer<S>;

    fn layer(&self, service: S) -> Self::Service {
        JsonLoggerLayer { service }
    }
}

pub struct JsonLoggerLayer<S> {
    service: S,
}

impl<S, B> Service<Request<B>> for JsonLoggerLayer<S>
where
    S: Service<Request<B>, Response = axum::http::Response<B>>,
    S::Error: std::fmt::Display,
    S::Future: Send + 'static,
    B: Send + 'static,
{
    type Response = axum::http::Response<B>;
    type Error = S::Error;
    type Future = std::pin::Pin<Box<dyn std::future::Future<Output = Result<Self::Response, Self::Error>> + Send>>;

    fn poll_ready(
        &mut self,
        cx: &mut std::task::Context<'_>,
    ) -> std::task::Poll<Result<(), Self::Error>> {
        self.service.poll_ready(cx)
    }

    fn call(&mut self, mut req: Request<B>) -> Self::Future {
        let method = req.method().clone();
        let path = req.uri().path().to_string();
        let start = Instant::now();

        let service = self.service.clone();
        Box::pin(async move {
            let res = service.oneshot(req).await?;
            let duration = start.elapsed();
            let status = res.status().as_u16();

            let log_entry = json!({
                "method": method,
                "path": path,
                "status": status,
                "durationMs": duration.as_millis()
            });
            
            println!("{}", serde_json::to_string(&log_entry).unwrap());
            
            Ok(res)
        })
    }
}
```

FILE: src/main.rs
```rust
use orders_lib::create_router;
use std::net::SocketAddr;
use tokio::signal;

#[tokio::main]
async fn main() {
    let app = create_router();

    let listener = tokio::net::TcpListener::bind("0.0.0.0:8080")
        .await
        .expect("Failed to bind to port 8080");

    println!("Listening on 0.0.0.0:8080");

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await
        .unwrap();
}

async fn shutdown_signal() {
    let ctrl_c = async {
        signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("failed to install signal handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }

    println!("Shutting down gracefully...");
}
```

FILE: tests/api_tests.rs
```rust
use axum::http::{Request, StatusCode};
use hyper::body::Bytes;
use hyper_util::rt::TokioExecutor;
use orders_lib::create_router;
use std::net::SocketAddr;
use tower::ServiceExt;
use serde_json::json;

static mut ADDR: Option<SocketAddr> = None;
static INIT: tokio::sync::OnceCell<()> = tokio::sync::OnceCell::const_new();

async fn init_server() -> &'static SocketAddr {
    INIT.get_or_init(|| async {
        let app = create_router();
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        
        tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        
        &addr
    }).await
}

async fn make_request(path: &str, body: Option<serde_json::Value>) -> (StatusCode, String) {
    let addr = init_server().await;
    let url = format!("http://127.0.0.1:{}/{}", addr.port(), path);
    
    let client = hyper_util::client::legacy::Client::builder(TokioExecutor::new())
        .build_http();

    let req = if let Some(b) = body {
        Request::builder()
            .method("POST")
            .uri(&url)
            .header("Content-Type", "application/json")
            .body(hyper::body::Body::from(b.to_string()))
            .unwrap()
    } else {
        Request::builder()
            .method("GET")
            .uri(&url)
            .body(hyper::body::Body::empty())
            .unwrap()
    };

    let res = client.request(req).await.unwrap();
    let status = res.status();
    let body_bytes = hyper::body::to_bytes(res.into_body()).await.unwrap();
    let body_str = String::from_utf8(body_bytes.to_vec()).unwrap();
    
    (status, body_str)
}

#[tokio::test]
async fn test_health_check() {
    let (status, body) = make_request("/health", None).await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert_eq!(json["status"], "ok");
}

#[tokio::test]
async fn test_create_order_success() {
    let body = json!({
        "customerId": "c-1",
        "items": [
            {"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}
        ]
    });
    let (status, response_body) = make_request("/orders", Some(body)).await;
    assert_eq!(status, StatusCode::CREATED);
    
    let json: serde_json::Value = serde_json::from_str(&response_body).unwrap();
    assert_eq!(json["customerId"], "c-1");
    assert_eq!(json["totalCents"], 2500);
    assert!(json["id"].is_string());
    assert!(json["createdAt"].is_string());
}

#[tokio::test]
async fn test_create_order_invalid_customer_id() {
    let body = json!({
        "customerId": "",
        "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
    });
    let (status, response_body) = make_request("/orders", Some(body)).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    let json: serde_json::Value = serde_json::from_str(&response_body).unwrap();
    assert!(json["error"].is_string());
}

#[tokio::test]
async fn test_create_order_invalid_quantity() {
    let body = json!({
        "customerId": "c-1",
        "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]
    });
    let (status, response_body) = make_request("/orders", Some(body)).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_get_order_404() {
    let (status, response_body) = make_request("/orders/non-existent-id", None).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
    let json: serde_json::Value = serde_json::from_str(&response_body).unwrap();
    assert!(json["error"].is_string());
}

#[tokio::test]
async fn test_get_order_success() {
    // Create first
    let create_body = json!({
        "customerId": "c-1",
        "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
    });
    let (status, response_body) = make_request("/orders", Some(create_body)).await;
    assert_eq!(status, StatusCode::CREATED);
    let json: serde_json::Value = serde_json::from_str(&response_body).unwrap();
    let order_id = json["id"].as_str().unwrap();

    // Retrieve
    let (status, get_body) = make_request(&format!("/orders/{}", order_id), None).await;
    assert_eq!(status, StatusCode::OK);
    let get_json: serde_json::Value = serde_json::from_str(&get_body).unwrap();
    assert_eq!(get_json["id"], order_id);
    assert_eq!(get_json["totalCents"], 100);
}
```