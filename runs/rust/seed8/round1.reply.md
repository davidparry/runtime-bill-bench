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
reqwest = { version = "0.11", features = ["json"] }
tokio = { version = "1", features = ["full", "test-util"] }
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
use tower_http::{trace::TraceLayer};
use uuid::Uuid;

// --- Models ---

#[derive(Debug, Deserialize)]
struct CreateOrderRequest {
    customer_id: String,
    items: Vec<OrderItemRequest>,
}

#[derive(Debug, Deserialize)]
struct OrderItemRequest {
    sku: String,
    quantity: u32,
    unit_price_cents: u64,
}

#[derive(Debug, Serialize, Clone)]
struct OrderResponse {
    id: String,
    customer_id: String,
    items: Vec<OrderItemResponse>,
    total_cents: u64,
    created_at: String,
}

#[derive(Debug, Serialize, Clone)]
struct OrderItemResponse {
    sku: String,
    quantity: u32,
    unit_price_cents: u64,
}

#[derive(Debug, Serialize)]
struct ErrorResponse {
    error: String,
}

// --- State ---

#[derive(Clone)]
struct AppState {
    orders: Arc<Mutex<HashMap<String, OrderResponse>>>,
}

// --- Validation Helpers ---

fn validate_customer_id(id: &str) -> Result<(), String> {
    let len = id.len();
    if len < 1 || len > 64 {
        return Err("customerId must be between 1 and 64 characters".to_string());
    }
    Ok(())
}

fn validate_items(items: &[OrderItemRequest]) -> Result<(), String> {
    let len = items.len();
    if len < 1 || len > 50 {
        return Err("items must contain between 1 and 50 entries".to_string());
    }

    for (i, item) in items.iter().enumerate() {
        let sku_len = item.sku.len();
        if sku_len < 1 || sku_len > 32 {
            return Err(format!("item[{}].sku must be between 1 and 32 characters", i));
        }
        if item.quantity < 1 || item.quantity > 100 {
            return Err(format!("item[{}].quantity must be between 1 and 100", i));
        }
        if item.unit_price_cents < 1 || item.unit_price_cents > 1_000_000 {
            return Err(format!("item[{}].unitPriceCents must be between 1 and 1000000", i));
        }
    }
    Ok(())
}

// --- Handlers ---

async fn create_order(
    State(state): State<AppState>,
    Json(payload): Json<CreateOrderRequest>,
) -> Result<Response, (StatusCode, Json<ErrorResponse>)> {
    // Validation
    if let Err(e) = validate_customer_id(&payload.customer_id) {
        return Err((
            StatusCode::BAD_REQUEST,
            Json(ErrorResponse { error: e }),
        ));
    }

    if let Err(e) = validate_items(&payload.items) {
        return Err((
            StatusCode::BAD_REQUEST,
            Json(ErrorResponse { error: e }),
        ));
    }

    let id = Uuid::new_v4().to_string();
    let now = Utc::now();
    let created_at = now.to_rfc3339();

    let items_resp: Vec<OrderItemResponse> = payload
        .items
        .iter()
        .map(|i| OrderItemResponse {
            sku: i.sku.clone(),
            quantity: i.quantity,
            unit_price_cents: i.unit_price_cents,
        })
        .collect();

    let total_cents: u64 = items_resp
        .iter()
        .map(|i| i.quantity as u64 * i.unit_price_cents)
        .sum();

    let order = OrderResponse {
        id: id.clone(),
        customer_id: payload.customer_id,
        items: items_resp,
        total_cents,
        created_at,
    };

    // Store
    {
        let mut store = state.orders.lock().unwrap();
        store.insert(id.clone(), order);
    }

    let mut response = (
        StatusCode::CREATED,
        Json(OrderResponse {
            id: id.clone(),
            customer_id: order.customer_id,
            items: order.items,
            total_cents: order.total_cents,
            created_at: order.created_at,
        }),
    )
    .into_response();
    response.headers_mut().insert(
        HeaderName::from_static("location"),
        format!("/orders/{}", id)
            .parse()
            .unwrap(),
    );

    Ok(response)
}

async fn get_order(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<OrderResponse>, (StatusCode, Json<ErrorResponse>)> {
    let store = state.orders.lock().unwrap();
    match store.get(&id) {
        Some(order) => Ok(Json(order.clone())),
        None => Err((
            StatusCode::NOT_FOUND,
            Json(ErrorResponse {
                error: format!("Order not found: {}", id),
            }),
        )),
    }
}

async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({ "status": "ok" }))
}

// --- Main ---

#[tokio::main]
async fn main() {
    let orders = Arc::new(Mutex::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .route("/orders/{id}", get(get_order))
        .route("/health", get(health))
        .with_state(state)
        .layer(TraceLayer::new_for_http());

    let listener = tokio::net::TcpListener::bind("0.0.0.0:8080")
        .await
        .expect("Failed to bind to port 8080");

    println!("Server listening on 0.0.0.0:8080");

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
}
```

FILE: tests/validation_tests.rs
```rust
use axum::{
    body::Body,
    http::{Request, StatusCode},
    routing::post,
    Router,
};
use serde_json::json;
use std::sync::Arc;
use tokio::sync::Mutex;

// Re-use types from the main crate to avoid duplication if possible, 
// but for integration tests, we often reconstruct the app or use the public API.
// Since the types aren't pub, we will use raw JSON and parse responses.

#[tokio::test]
async fn test_valid_order_creation() {
    let orders = Arc::new(Mutex::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "c-1",
            "items": [
                { "sku": "A-1", "quantity": 2, "unitPriceCents": 1250 }
            ]
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::CREATED);
    let body: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(body["customerId"], "c-1");
    assert_eq!(body["totalCents"], 2500);
    assert!(!body["id"].is_null());
    assert!(!body["createdAt"].is_null());
}

#[tokio::test]
async fn test_invalid_customer_id_too_long() {
    let orders = Arc::new(Mutex::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "a".repeat(65),
            "items": [
                { "sku": "A-1", "quantity": 1, "unitPriceCents": 100 }
            ]
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let body: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(body["error"], "customerId must be between 1 and 64 characters");
}

#[tokio::test]
async fn test_invalid_customer_id_empty() {
    let orders = Arc::new(Mutex::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "",
            "items": [
                { "sku": "A-1", "quantity": 1, "unitPriceCents": 100 }
            ]
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_invalid_items_empty() {
    let orders = Arc::new(Mutex::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "c-1",
            "items": []
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let body: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(body["error"], "items must contain between 1 and 50 entries");
}

#[tokio::test]
async fn test_invalid_quantity_zero() {
    let orders = Arc::new(Mutex::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "c-1",
            "items": [
                { "sku": "A-1", "quantity": 0, "unitPriceCents": 100 }
            ]
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let body: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(body["error"], "item[0].quantity must be between 1 and 100");
}

#[tokio::test]
async fn test_invalid_unit_price_zero() {
    let orders = Arc::new(Mutex::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "c-1",
            "items": [
                { "sku": "A-1", "quantity": 1, "unitPriceCents": 0 }
            ]
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_invalid_sku_too_long() {
    let orders = Arc::new(Mutex::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "c-1",
            "items": [
                { "sku": "a".repeat(33), "quantity": 1, "unitPriceCents": 100 }
            ]
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_invalid_quantity_too_high() {
    let orders = Arc::new(Mutex::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "c-1",
            "items": [
                { "sku": "A-1", "quantity": 101, "unitPriceCents": 100 }
            ]
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_invalid_unit_price_too_high() {
    let orders = Arc::new(Mutex::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "c-1",
            "items": [
                { "sku": "A-1", "quantity": 1, "unitPriceCents": 1000001 }
            ]
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_get_order_404() {
    let orders = Arc::new(Mutex::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders/{id}", get(get_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .get("http://localhost:8080/orders/non-existent-id")
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    let body: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(body["error"], "Order not found: non-existent-id");
}

#[tokio::test]
async fn test_get_order_404_after_creation() {
    // First create an order to ensure the path works
    let orders = Arc::new(Mutex::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .route("/orders/{id}", get(get_order))
        .with_state(state);

    let client = reqwest::Client::new();
    
    // Create
    let create_resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "c-1",
            "items": [
                { "sku": "A-1", "quantity": 1, "unitPriceCents": 100 }
            ]
        }))
        .send()
        .await
        .unwrap();
    
    let create_body: serde_json::Value = create_resp.json().await.unwrap();
    let order_id = create_body["id"].as_str().unwrap();

    // Get it
    let get_resp = client
        .get(format!("http://localhost:8080/orders/{}", order_id))
        .send()
        .await
        .unwrap();
    assert_eq!(get_resp.status(), StatusCode::OK);

    // Now test 404 for a different ID
    let not_found_resp = client
        .get("http://localhost:8080/orders/another-non-existent-id")
        .send()
        .await
        .unwrap();
    
    assert_eq!(not_found_resp.status(), StatusCode::NOT_FOUND);
    let body: serde_json::Value = not_found_resp.json().await.unwrap();
    assert_eq!(body["error"], "Order not found: another-non-existent-id");
}

// Helper to include necessary imports for the test file to compile if it were standalone
// In the actual project, these would be in main.rs or lib.rs, but for the purpose of 
// this single-file output constraint, I'm putting them here to ensure the test compiles 
// if pasted into a tests/ directory. However, since I can't modify main.rs to be pub,
// I will assume the tests file is part of the same package and uses the private types
// via re-export or just relies on the binary being built. 
// Actually, for the harness `cargo test`, the tests are compiled against the crate.
// To make this work without a lib.rs, I need to make the types in main.rs pub or 
// move them to lib.rs. 
// The prompt asks for "every file in the project". I should add a lib.rs to expose the types
// for testing, or just make main.rs types pub. Making main.rs types pub is safer for 
// a simple binary project structure if lib.rs isn't strictly required.
// However, standard practice is lib.rs for logic and main.rs for entry.
// Let's refactor slightly to include a lib.rs to expose the types for testing.

// Wait, the prompt says "Return every file in the project". 
// If I add lib.rs, I must include it.
// Let's add lib.rs to make the types accessible for testing.

// But wait, I already wrote src/main.rs. 
// If I add src/lib.rs, the binary target in Cargo.toml points to src/main.rs.
// This is fine.

// Let's create src/lib.rs content.

// FILE: src/lib.rs
// (This content will be provided in the next block)
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
use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
};
use uuid::Uuid;

// --- Models ---

#[derive(Debug, Deserialize)]
pub struct CreateOrderRequest {
    customer_id: String,
    items: Vec<OrderItemRequest>,
}

#[derive(Debug, Deserialize)]
pub struct OrderItemRequest {
    sku: String,
    quantity: u32,
    unit_price_cents: u64,
}

#[derive(Debug, Serialize, Clone)]
pub struct OrderResponse {
    pub id: String,
    pub customer_id: String,
    pub items: Vec<OrderItemResponse>,
    pub total_cents: u64,
    pub created_at: String,
}

#[derive(Debug, Serialize, Clone)]
pub struct OrderItemResponse {
    pub sku: String,
    pub quantity: u32,
    pub unit_price_cents: u64,
}

#[derive(Debug, Serialize)]
pub struct ErrorResponse {
    pub error: String,
}

// --- State ---

#[derive(Clone)]
pub struct AppState {
    pub orders: Arc<Mutex<HashMap<String, OrderResponse>>>,
}

// --- Validation Helpers ---

fn validate_customer_id(id: &str) -> Result<(), String> {
    let len = id.len();
    if len < 1 || len > 64 {
        return Err("customerId must be between 1 and 64 characters".to_string());
    }
    Ok(())
}

fn validate_items(items: &[OrderItemRequest]) -> Result<(), String> {
    let len = items.len();
    if len < 1 || len > 50 {
        return Err("items must contain between 1 and 50 entries".to_string());
    }

    for (i, item) in items.iter().enumerate() {
        let sku_len = item.sku.len();
        if sku_len < 1 || sku_len > 32 {
            return Err(format!("item[{}].sku must be between 1 and 32 characters", i));
        }
        if item.quantity < 1 || item.quantity > 100 {
            return Err(format!("item[{}].quantity must be between 1 and 100", i));
        }
        if item.unit_price_cents < 1 || item.unit_price_cents > 1_000_000 {
            return Err(format!("item[{}].unitPriceCents must be between 1 and 1000000", i));
        }
    }
    Ok(())
}

// --- Handlers ---

pub async fn create_order(
    State(state): State<AppState>,
    Json(payload): Json<CreateOrderRequest>,
) -> Result<Response, (StatusCode, Json<ErrorResponse>)> {
    // Validation
    if let Err(e) = validate_customer_id(&payload.customer_id) {
        return Err((
            StatusCode::BAD_REQUEST,
            Json(ErrorResponse { error: e }),
        ));
    }

    if let Err(e) = validate_items(&payload.items) {
        return Err((
            StatusCode::BAD_REQUEST,
            Json(ErrorResponse { error: e }),
        ));
    }

    let id = Uuid::new_v4().to_string();
    let now = Utc::now();
    let created_at = now.to_rfc3339();

    let items_resp: Vec<OrderItemResponse> = payload
        .items
        .iter()
        .map(|i| OrderItemResponse {
            sku: i.sku.clone(),
            quantity: i.quantity,
            unit_price_cents: i.unit_price_cents,
        })
        .collect();

    let total_cents: u64 = items_resp
        .iter()
        .map(|i| i.quantity as u64 * i.unit_price_cents)
        .sum();

    let order = OrderResponse {
        id: id.clone(),
        customer_id: payload.customer_id,
        items: items_resp,
        total_cents,
        created_at,
    };

    // Store
    {
        let mut store = state.orders.lock().unwrap();
        store.insert(id.clone(), order);
    }

    let mut response = (
        StatusCode::CREATED,
        Json(OrderResponse {
            id: id.clone(),
            customer_id: order.customer_id,
            items: order.items,
            total_cents: order.total_cents,
            created_at: order.created_at,
        }),
    )
    .into_response();
    response.headers_mut().insert(
        HeaderName::from_static("location"),
        format!("/orders/{}", id)
            .parse()
            .unwrap(),
    );

    Ok(response)
}

pub async fn get_order(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<OrderResponse>, (StatusCode, Json<ErrorResponse>)> {
    let store = state.orders.lock().unwrap();
    match store.get(&id) {
        Some(order) => Ok(Json(order.clone())),
        None => Err((
            StatusCode::NOT_FOUND,
            Json(ErrorResponse {
                error: format!("Order not found: {}", id),
            }),
        )),
    }
}

pub async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({ "status": "ok" }))
}
```

FILE: tests/validation_tests.rs
```rust
use axum::{routing::get, routing::post, Router};
use orders::{AppState, create_order, get_order, health};
use serde_json::json;
use std::sync::Arc;
use tokio::sync::Mutex;
use reqwest::StatusCode;

#[tokio::test]
async fn test_valid_order_creation() {
    let orders = Arc::new(Mutex::new(std::collections::HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "c-1",
            "items": [
                { "sku": "A-1", "quantity": 2, "unitPriceCents": 1250 }
            ]
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::CREATED);
    let body: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(body["customerId"], "c-1");
    assert_eq!(body["totalCents"], 2500);
    assert!(!body["id"].is_null());
    assert!(!body["createdAt"].is_null());
}

#[tokio::test]
async fn test_invalid_customer_id_too_long() {
    let orders = Arc::new(Mutex::new(std::collections::HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "a".repeat(65),
            "items": [
                { "sku": "A-1", "quantity": 1, "unitPriceCents": 100 }
            ]
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let body: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(body["error"], "customerId must be between 1 and 64 characters");
}

#[tokio::test]
async fn test_invalid_customer_id_empty() {
    let orders = Arc::new(Mutex::new(std::collections::HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "",
            "items": [
                { "sku": "A-1", "quantity": 1, "unitPriceCents": 100 }
            ]
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_invalid_items_empty() {
    let orders = Arc::new(Mutex::new(std::collections::HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "c-1",
            "items": []
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let body: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(body["error"], "items must contain between 1 and 50 entries");
}

#[tokio::test]
async fn test_invalid_quantity_zero() {
    let orders = Arc::new(Mutex::new(std::collections::HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "c-1",
            "items": [
                { "sku": "A-1", "quantity": 0, "unitPriceCents": 100 }
            ]
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    let body: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(body["error"], "item[0].quantity must be between 1 and 100");
}

#[tokio::test]
async fn test_invalid_unit_price_zero() {
    let orders = Arc::new(Mutex::new(std::collections::HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "c-1",
            "items": [
                { "sku": "A-1", "quantity": 1, "unitPriceCents": 0 }
            ]
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_invalid_sku_too_long() {
    let orders = Arc::new(Mutex::new(std::collections::HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "c-1",
            "items": [
                { "sku": "a".repeat(33), "quantity": 1, "unitPriceCents": 100 }
            ]
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_invalid_quantity_too_high() {
    let orders = Arc::new(Mutex::new(std::collections::HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "c-1",
            "items": [
                { "sku": "A-1", "quantity": 101, "unitPriceCents": 100 }
            ]
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_invalid_unit_price_too_high() {
    let orders = Arc::new(Mutex::new(std::collections::HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "c-1",
            "items": [
                { "sku": "A-1", "quantity": 1, "unitPriceCents": 1000001 }
            ]
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_get_order_404() {
    let orders = Arc::new(Mutex::new(std::collections::HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders/{id}", get(get_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let resp = client
        .get("http://localhost:8080/orders/non-existent-id")
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    let body: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(body["error"], "Order not found: non-existent-id");
}

#[tokio::test]
async fn test_get_order_404_after_creation() {
    // First create an order to ensure the path works
    let orders = Arc::new(Mutex::new(std::collections::HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", post(create_order))
        .route("/orders/{id}", get(get_order))
        .with_state(state);

    let client = reqwest::Client::new();
    
    // Create
    let create_resp = client
        .post("http://localhost:8080/orders")
        .json(&json!({
            "customerId": "c-1",
            "items": [
                { "sku": "A-1", "quantity": 1, "unitPriceCents": 100 }
            ]
        }))
        .send()
        .await
        .unwrap();
    
    let create_body: serde_json::Value = create_resp.json().await.unwrap();
    let order_id = create_body["id"].as_str().unwrap();

    // Get it
    let get_resp = client
        .get(format!("http://localhost:8080/orders/{}", order_id))
        .send()
        .await
        .unwrap();
    assert_eq!(get_resp.status(), StatusCode::OK);

    // Now test 404 for a different ID
    let not_found_resp = client
        .get("http://localhost:8080/orders/another-non-existent-id")
        .send()
        .await
        .unwrap();
    
    assert_eq!(not_found_resp.status(), StatusCode::NOT_FOUND);
    let body: serde_json::Value = not_found_resp.json().await.unwrap();
    assert_eq!(body["error"], "Order not found: another-non-existent-id");
}
```