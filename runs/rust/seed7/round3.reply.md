FILE: Cargo.toml
```toml
[package]
name = "orders"
version = "0.1.0"
edition = "2021"

[dependencies]
axum = { version = "0.7", features = ["tokio"] }
tokio = { version = "1", features = ["full"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
uuid = { version = "1", features = ["v4", "serde"] }
chrono = { version = "0.4", features = ["serde"] }
tower = "0.4"
tower-http = { version = "0.5", features = ["trace"] }

[dev-dependencies]
axum = { version = "0.7", features = ["test"] }
reqwest = { version = "0.12", features = ["json"] }
tokio = { version = "1", features = ["full"] }
```

FILE: src/lib.rs
```rust
use axum::extract::State;
use axum::routing::{get, post};
use axum::Json;
use axum::response::{IntoResponse, Response};
use axum::http::StatusCode;
use std::collections::HashMap;
use std::sync::Arc;
use uuid::Uuid;
use serde::{Deserialize, Serialize};
use chrono::Utc;
use tower::ServiceBuilder;
use tower_http::trace::TraceLayer;
use tokio::sync::RwLock;

#[derive(Debug, Deserialize)]
pub struct CreateOrderRequest {
    customer_id: String,
    items: Vec<OrderItem>,
}

#[derive(Debug, Deserialize, Clone, Serialize)]
pub struct OrderItem {
    pub sku: String,
    pub quantity: u64,
    pub unit_price_cents: u64,
}

#[derive(Debug, Serialize, Clone)]
pub struct OrderResponse {
    pub id: String,
    pub customer_id: String,
    pub items: Vec<OrderItem>,
    pub total_cents: u64,
    pub created_at: String,
}

#[derive(Debug, Deserialize)]
pub struct ErrorResponse {
    pub error: String,
}

#[derive(Debug, Clone)]
pub struct AppState {
    pub orders: Arc<RwLock<HashMap<String, OrderResponse>>>,
}

impl IntoResponse for ErrorResponse {
    fn into_response(self) -> Response {
        (StatusCode::BAD_REQUEST, Json(self)).into_response()
    }
}

impl IntoResponse for (StatusCode, ErrorResponse) {
    fn into_response(self) -> Response {
        (self.0, Json(self.1)).into_response()
    }
}

pub fn validate_create_request(req: CreateOrderRequest) -> Result<(), ErrorResponse> {
    if req.customer_id.len() < 1 || req.customer_id.len() > 64 {
        return Err(ErrorResponse {
            error: "customer_id must be between 1 and 64 characters".to_string(),
        });
    }

    if req.items.is_empty() || req.items.len() > 50 {
        return Err(ErrorResponse {
            error: "items must contain between 1 and 50 entries".to_string(),
        });
    }

    for (i, item) in req.items.iter().enumerate() {
        if item.sku.len() < 1 || item.sku.len() > 32 {
            return Err(ErrorResponse {
                error: format!("item[{}].sku must be between 1 and 32 characters", i),
            });
        }
        if item.quantity < 1 || item.quantity > 100 {
            return Err(ErrorResponse {
                error: format!("item[{}].quantity must be between 1 and 100", i),
            });
        }
        if item.unit_price_cents < 1 || item.unit_price_cents > 1_000_000 {
            return Err(ErrorResponse {
                error: format!("item[{}].unit_price_cents must be between 1 and 1000000", i),
            });
        }
    }

    Ok(())
}

pub async fn create_order(
    State(state): State<AppState>,
    Json(req): Json<CreateOrderRequest>,
) -> Result<impl IntoResponse, (StatusCode, ErrorResponse)> {
    if let Err(err) = validate_create_request(req) {
        return Err((StatusCode::BAD_REQUEST, err));
    }

    let id = Uuid::new_v4().to_string();
    let customer_id = req.customer_id.clone();
    let items = req.items.clone();
    
    let total_cents: u64 = items.iter().map(|i| i.quantity * i.unit_price_cents).sum();
    let created_at = Utc::now().to_rfc3339();

    let order = OrderResponse {
        id: id.clone(),
        customer_id,
        items,
        total_cents,
        created_at,
    };

    let mut orders = state.orders.write().await;
    orders.insert(id.clone(), order);

    let response = Response::builder()
        .status(StatusCode::CREATED)
        .header(axum::http::header::LOCATION, format!("/orders/{}", id))
        .body(axum::body::Body::from(serde_json::to_string(&OrderResponse {
            id: id.clone(),
            customer_id: req.customer_id.clone(),
            items: req.items.clone(),
            total_cents: total_cents,
            created_at: created_at,
        }).unwrap()))
        .unwrap();

    Ok(response)
}

pub async fn get_order(
    State(state): State<AppState>,
    axum::extract::Path(id): axum::extract::Path<String>,
) -> Result<impl IntoResponse, (StatusCode, ErrorResponse)> {
    let orders = state.orders.read().await;
    match orders.get(&id) {
        Some(order) => Ok(Json(order.clone())),
        None => Err((StatusCode::NOT_FOUND, ErrorResponse {
            error: format!("Order with id {} not found", id),
        })),
    }
}

pub async fn health() -> Json<&'static str> {
    Json("ok")
}

pub fn create_app() -> axum::Router<AppState> {
    let orders: Arc<RwLock<HashMap<String, OrderResponse>>> = Arc::new(RwLock::new(HashMap::new()));
    let state = AppState { orders };

    axum::Router::new()
        .route("/orders", post(create_order))
        .route("/orders/{id}", get(get_order))
        .route("/health", get(health))
        .with_state(state)
        .layer(TraceLayer::new_for_http())
}
```

FILE: src/main.rs
```rust
use orders::create_app;
use std::env;
use tokio::signal;

#[tokio::main]
async fn main() {
    let app = create_app();

    let port = env::var("PORT").unwrap_or_else(|_| "8080".to_string());
    let port: u16 = port.parse().unwrap_or(8080);

    let listener = tokio::net::TcpListener::bind(format!("0.0.0.0:{}", port))
        .await
        .unwrap();

    println!("Listening on 0.0.0.0:{}", port);

    let shutdown_handle = tokio::spawn(async move {
        signal::ctrl_c().await.expect("failed to listen for ctrl-c");
        println!("Received SIGTERM, shutting down...");
    });

    axum::serve(listener, app)
        .with_graceful_shutdown(async move {
            let _ = shutdown_handle.await;
        })
        .await
        .unwrap();
        
    println!("Server shut down gracefully.");
}
```

FILE: tests/validation_tests.rs
```rust
use axum::http::{StatusCode, Request};
use axum::routing::{get, post};
use axum::Json;
use axum::extract::State;
use axum::body::Body;
use axum::http::header::CONTENT_TYPE;
use axum::body::to_bytes;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use serde_json::json;

// Import from lib
use orders::{AppState, create_app, OrderItem};

#[tokio::test]
async fn test_create_order_success() {
    let app = create_app();
    
    let state = app.state().unwrap();
    let mut orders = state.orders.write().await;
    orders.clear();
    drop(orders);

    let req = Request::builder()
        .method("POST")
        .uri("/orders")
        .header(CONTENT_TYPE, "application/json")
        .body(Body::from(json!({
            "customerId": "c-1",
            "items": [
                {"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}
            ]
        }).to_string()))
        .unwrap();

    let resp = app.call(req).await.unwrap();
    
    assert_eq!(resp.status(), StatusCode::CREATED);
    
    let body = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
    
    assert_eq!(json["customerId"], "c-1");
    assert_eq!(json["totalCents"], 2500);
    assert!(json["id"].is_string());
    assert!(json["createdAt"].is_string());
}

#[tokio::test]
async fn test_create_order_invalid_customer_id_too_short() {
    let app = create_app();
    
    let state = app.state().unwrap();
    let mut orders = state.orders.write().await;
    orders.clear();
    drop(orders);

    let req = Request::builder()
        .method("POST")
        .uri("/orders")
        .header(CONTENT_TYPE, "application/json")
        .body(Body::from(json!({
            "customerId": "",
            "items": [
                {"sku": "A-1", "quantity": 1, "unitPriceCents": 100}
            ]
        }).to_string()))
        .unwrap();

    let resp = app.call(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_create_order_invalid_customer_id_too_long() {
    let app = create_app();
    
    let state = app.state().unwrap();
    let mut orders = state.orders.write().await;
    orders.clear();
    drop(orders);

    let long_id = "a".repeat(65);
    let req = Request::builder()
        .method("POST")
        .uri("/orders")
        .header(CONTENT_TYPE, "application/json")
        .body(Body::from(json!({
            "customerId": long_id,
            "items": [
                {"sku": "A-1", "quantity": 1, "unitPriceCents": 100}
            ]
        }).to_string()))
        .unwrap();

    let resp = app.call(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_create_order_invalid_items_empty() {
    let app = create_app();
    
    let state = app.state().unwrap();
    let mut orders = state.orders.write().await;
    orders.clear();
    drop(orders);

    let req = Request::builder()
        .method("POST")
        .uri("/orders")
        .header(CONTENT_TYPE, "application/json")
        .body(Body::from(json!({
            "customerId": "c-1",
            "items": []
        }).to_string()))
        .unwrap();

    let resp = app.call(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_create_order_invalid_item_quantity_zero() {
    let app = create_app();
    
    let state = app.state().unwrap();
    let mut orders = state.orders.write().await;
    orders.clear();
    drop(orders);

    let req = Request::builder()
        .method("POST")
        .uri("/orders")
        .header(CONTENT_TYPE, "application/json")
        .body(Body::from(json!({
            "customerId": "c-1",
            "items": [
                {"sku": "A-1", "quantity": 0, "unitPriceCents": 100}
            ]
        }).to_string()))
        .unwrap();

    let resp = app.call(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_create_order_invalid_item_unit_price_zero() {
    let app = create_app();
    
    let state = app.state().unwrap();
    let mut orders = state.orders.write().await;
    orders.clear();
    drop(orders);

    let req = Request::builder()
        .method("POST")
        .uri("/orders")
        .header(CONTENT_TYPE, "application/json")
        .body(Body::from(json!({
            "customerId": "c-1",
            "items": [
                {"sku": "A-1", "quantity": 1, "unitPriceCents": 0}
            ]
        }).to_string()))
        .unwrap();

    let resp = app.call(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_get_order_404() {
    let app = create_app();
    
    let state = app.state().unwrap();
    let mut orders = state.orders.write().await;
    orders.clear();
    drop(orders);

    let req = Request::builder()
        .method("GET")
        .uri("/orders/non-existent-id")
        .body(Body::empty())
        .unwrap();

    let resp = app.call(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn test_health() {
    let app = create_app();
    
    let req = Request::builder()
        .method("GET")
        .uri("/health")
        .body(Body::empty())
        .unwrap();

    let resp = app.call(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    
    let body = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(json, "ok");
}
```