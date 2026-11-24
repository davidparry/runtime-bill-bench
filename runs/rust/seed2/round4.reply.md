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
    routing::{get, post},
    Router,
};

pub mod handlers;
pub mod middleware;
pub mod state;

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
    http::StatusCode,
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
        let (_status, message) = match self {
            AppError::BadRequest(msg) => (StatusCode::BAD_REQUEST, msg),
            AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg),
        };

        let body = Json(json!({"error": message}));
        let mut res = body.into_response();
        res.headers_mut()
            .insert(
                axum::http::header::CONTENT_TYPE,
                axum::http::HeaderValue::from_static("application/json"),
            );
        res
    }
}

pub async fn create_order(
    State(state): State<AppState>,
    Json(payload): Json<CreateOrderRequest>,
) -> Result<Response, AppError> {
    if payload.customer_id.len() < 1 || payload.customer_id.len() > 64 {
        return Err(AppError::BadRequest(
            "customerId must be 1 to 64 characters".into(),
        ));
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
            return Err(AppError::BadRequest("item total overflow".into()));
        }

        total_cents = total_cents
            .checked_add(item_total)
            .ok_or_else(|| AppError::BadRequest("totalCents overflow".into()))?;
        
        validated_items.push(item.clone());
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
        store.insert(order_id.clone(), response.clone());
    }

    let mut res = (
        StatusCode::CREATED,
        [
            (
                axum::http::header::LOCATION,
                format!("/orders/{}", order_id),
            ),
        ],
        Json(response),
    )
    .into_response();

    res.headers_mut()
        .insert(
            axum::http::header::CONTENT_TYPE,
            axum::http::HeaderValue::from_static("application/json"),
        );

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
use axum::http::Request;
use serde_json::json;
use std::time::Instant;
use tower::Layer;
use tower::Service;
use tower::ServiceExt;

#[derive(Clone)]
pub struct JsonLogger;

impl<S> Layer<S> for JsonLogger {
    type Service = JsonLoggerLayer<S>;

    fn layer(&self, service: S) -> Self::Service {
        JsonLoggerLayer { service }
    }
}

#[derive(Clone)]
pub struct JsonLoggerLayer<S> {
    service: S,
}

impl<S, B> Service<Request<B>> for JsonLoggerLayer<S>
where
    S: Service<Request<B>, Response = axum::http::Response<B>> + Clone + Send + 'static,
    S::Error: std::fmt::Display,
    S::Future: Send + 'static,
    B: Send + 'static,
{
    type Response = axum::http::Response<B>;
    type Error = S::Error;
    type Future =
        std::pin::Pin<Box<dyn std::future::Future<Output = Result<Self::Response, Self::Error>> + Send>>;

    fn poll_ready(
        &mut self,
        cx: &mut std::task::Context<'_>,
    ) -> std::task::Poll<Result<(), Self::Error>> {
        self.service.poll_ready(cx)
    }

    fn call(&mut self, mut req: Request<B>) -> Self::Future {
        let method = req.method().to_string();
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
use orders::create_router;
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
use axum::http::StatusCode;
use hyper::body::Bytes;
use hyper_util::client::legacy::Client;
use hyper_util::rt::TokioExecutor;
use orders::create_router;
use std::net::SocketAddr;
use tower::ServiceExt;

static INIT: tokio::sync::OnceCell<SocketAddr> = tokio::sync::OnceCell::const_new();

async fn get_addr() -> &'static SocketAddr {
    INIT.get_or_init(|| async {
        let app = create_router();
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();

        tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });

        addr
    })
    .await
}

async fn make_request(path: &str, body: Option<serde_json::Value>) -> (StatusCode, String) {
    let addr = get_addr().await;
    let url = format!("http://127.0.0.1:{}/{}", addr.port(), path);

    let client: Client<_, hyper::body::Incoming> =
        Client::builder(TokioExecutor::new()).build_http();

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

// Import Request from axum to avoid ambiguity or missing import
use axum::http::Request;

#[tokio::test]
async fn test_health_check() {
    let (status, body) = make_request("/health", None).await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert_eq!(json["status"], "ok");
}

#[tokio::test]
async fn test_create_order_success() {
    let body = serde_json::json!({
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
    let body = serde_json::json!({
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
    let body = serde_json::json!({
        "customerId": "c-1",
        "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]
    });
    let (status, response_body) = make_request("/orders", Some(body)).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_get_order_404() {
    let (status, response_body) =
        make_request("/orders/non-existent-id", None).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
    let json: serde_json::Value = serde_json::from_str(&response_body).unwrap();
    assert!(json["error"].is_string());
}

#[tokio::test]
async fn test_get_order_success() {
    // Create first
    let create_body = serde_json::json!({
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