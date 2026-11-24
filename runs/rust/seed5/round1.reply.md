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
tokio = { version = "1", features = ["full"] }
```

FILE: src/main.rs
```rust
use axum::{
    extract::Path,
    http::{HeaderName, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    sync::{Arc, RwLock},
    time::Instant,
};
use tokio::signal;
use tower_http::trace::TraceLayer;
use uuid::Uuid;

#[derive(Debug, Deserialize)]
struct CreateOrderRequest {
    #[serde(rename = "customerId")]
    customer_id: String,
    items: Vec<OrderItemRequest>,
}

#[derive(Debug, Deserialize)]
struct OrderItemRequest {
    sku: String,
    quantity: i64,
    #[serde(rename = "unitPriceCents")]
    unit_price_cents: i64,
}

#[derive(Debug, Serialize)]
struct CreateOrderResponse {
    id: String,
    #[serde(rename = "customerId")]
    customer_id: String,
    items: Vec<OrderItemResponse>,
    #[serde(rename = "totalCents")]
    total_cents: i64,
    #[serde(rename = "createdAt")]
    created_at: String,
}

#[derive(Debug, Serialize)]
struct OrderItemResponse {
    sku: String,
    quantity: i64,
    #[serde(rename = "unitPriceCents")]
    unit_price_cents: i64,
}

#[derive(Debug, Serialize)]
struct ErrorResponse {
    error: String,
}

#[derive(Debug, Clone, Serialize)]
struct StoredOrder {
    id: String,
    #[serde(rename = "customerId")]
    customer_id: String,
    items: Vec<OrderItemResponse>,
    #[serde(rename = "totalCents")]
    total_cents: i64,
    #[serde(rename = "createdAt")]
    created_at: String,
}

type OrderStore = Arc<RwLock<HashMap<String, StoredOrder>>>;

async fn health() -> impl IntoResponse {
    Json(serde_json::json!({ "status": "ok" }))
}

async fn create_order(
    store: OrderStore,
    Json(payload): Json<CreateOrderRequest>,
) -> impl IntoResponse {
    let validation_result = validate_create_order_request(&payload);
    if let Err(e) = validation_result {
        return (StatusCode::BAD_REQUEST, Json(ErrorResponse { error: e })).into_response();
    }

    let id = Uuid::new_v4().to_string();
    let created_at = Utc::now().to_rfc3339();

    let items: Vec<OrderItemResponse> = payload
        .items
        .iter()
        .map(|item| OrderItemResponse {
            sku: item.sku.clone(),
            quantity: item.quantity,
            unit_price_cents: item.unit_price_cents,
        })
        .collect();

    let total_cents: i64 = items
        .iter()
        .map(|item| item.quantity * item.unit_price_cents)
        .sum();

    let stored_order = StoredOrder {
        id: id.clone(),
        customer_id: payload.customer_id,
        items,
        total_cents,
        created_at: created_at.clone(),
    };

    {
        let mut store_write = store.write().unwrap();
        store_write.insert(id.clone(), stored_order);
    }

    let response = CreateOrderResponse {
        id,
        customer_id: payload.customer_id,
        items: payload
            .items
            .iter()
            .map(|item| OrderItemResponse {
                sku: item.sku.clone(),
                quantity: item.quantity,
                unit_price_cents: item.unit_price_cents,
            })
            .collect(),
        total_cents,
        created_at,
    };

    let mut res = Json(response).into_response();
    res.headers_mut()
        .insert(HeaderName::from_static("location"), "/orders/".parse().unwrap());
    res.status_mut() = StatusCode::CREATED;
    res
}

async fn get_order(
    store: OrderStore,
    Path(id): Path<String>,
) -> impl IntoResponse {
    let store_read = store.read().unwrap();
    match store_read.get(&id) {
        Some(order) => Json(order).into_response(),
        None => (
            StatusCode::NOT_FOUND,
            Json(ErrorResponse {
                error: "Order not found".to_string(),
            }),
        )
            .into_response(),
    }
}

fn validate_create_order_request(payload: &CreateOrderRequest) -> Result<(), String> {
    let customer_id = &payload.customer_id;
    if customer_id.len() < 1 || customer_id.len() > 64 {
        return Err("customerId must be between 1 and 64 characters".to_string());
    }

    let items = &payload.items;
    if items.len() < 1 || items.len() > 50 {
        return Err("items must have between 1 and 50 entries".to_string());
    }

    for item in items {
        if item.sku.len() < 1 || item.sku.len() > 32 {
            return Err("sku must be between 1 and 32 characters".to_string());
        }
        if item.quantity < 1 || item.quantity > 100 {
            return Err("quantity must be between 1 and 100".to_string());
        }
        if item.unit_price_cents < 1 || item.unit_price_cents > 1000000 {
            return Err("unitPriceCents must be between 1 and 1000000".to_string());
        }
    }

    Ok(())
}

#[tokio::main]
async fn main() {
    let store: OrderStore = Arc::new(RwLock::new(HashMap::new()));

    let app = Router::new()
        .route("/health", get(health))
        .route("/orders", post(create_order))
        .route("/orders/{id}", get(get_order))
        .layer(TraceLayer::new_for_http())
        .with_state(store);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:8080")
        .await
        .expect("Failed to bind to port 8080");

    println!("Listening on 0.0.0.0:8080");

    let shutdown_signal = async {
        signal::ctrl_c().await.expect("Failed to install Ctrl+C handler");
    };

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal)
        .await
        .unwrap();
}
```

FILE: tests/integration_tests.rs
```rust
use reqwest::Client;
use serde_json::json;
use std::time::Instant;

const BASE_URL: &str = "http://127.0.0.1:8080";

async fn client() -> Client {
    Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .unwrap()
}

#[tokio::test]
async fn test_create_order_success() {
    let res = client()
        .post(format!("{}/orders", BASE_URL))
        .json(&json!({
            "customerId": "c-1",
            "items": [
                {
                    "sku": "A-1",
                    "quantity": 2,
                    "unitPriceCents": 1250
                }
            ]
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(res.status(), 201);
    
    let location = res.headers().get("location").unwrap().to_str().unwrap();
    assert!(location.starts_with("/orders/"));
    
    let body: serde_json::Value = res.json().await.unwrap();
    assert_eq!(body["customerId"], "c-1");
    assert_eq!(body["items"].as_array().unwrap().len(), 1);
    assert_eq!(body["totalCents"], 2500);
    assert!(body["createdAt"].is_string());
}

#[tokio::test]
async fn test_get_order_success() {
    // Create an order first
    let create_res = client()
        .post(format!("{}/orders", BASE_URL))
        .json(&json!({
            "customerId": "c-2",
            "items": [
                {
                    "sku": "B-2",
                    "quantity": 1,
                    "unitPriceCents": 500
                }
            ]
        }))
        .send()
        .await
        .unwrap();

    let location = create_res.headers().get("location").unwrap().to_str().unwrap();
    let order_id = location.strip_prefix("/orders/").unwrap();

    // Get the order
    let get_res = client()
        .get(format!("{}/orders/{}", BASE_URL, order_id))
        .send()
        .await
        .unwrap();

    assert_eq!(get_res.status(), 200);
    let body: serde_json::Value = get_res.json().await.unwrap();
    assert_eq!(body["id"], order_id);
    assert_eq!(body["customerId"], "c-2");
    assert_eq!(body["totalCents"], 500);
}

#[tokio::test]
async fn test_get_order_not_found() {
    let res = client()
        .get(format!("{}/orders/non-existent-id", BASE_URL))
        .send()
        .await
        .unwrap();

    assert_eq!(res.status(), 404);
    let body: serde_json::Value = res.json().await.unwrap();
    assert!(body["error"].is_string());
}

#[tokio::test]
async fn test_create_order_invalid_customer_id_too_short() {
    let res = client()
        .post(format!("{}/orders", BASE_URL))
        .json(&json!({
            "customerId": "",
            "items": [
                {
                    "sku": "A-1",
                    "quantity": 1,
                    "unitPriceCents": 100
                }
            ]
        }))
        .send()
        .await
       
.unwrap();

    assert_eq!(res.status(), 400);
    let body: serde_json::Value = res.json().await.unwrap();
    assert!(body["error"].is_string());
}

#[tokio::test]
async fn test_create_order_invalid_customer_id_too_long() {
    let long_id = "a".repeat(65);
    let res = client()
        .post(format!("{}/orders", BASE_URL))
        .json(&json!({
            "customerId": long_id,
            "items": [
                {
                    "sku": "A-1",
                    "quantity": 1,
                    "unitPriceCents": 100
                }
            ]
        }))
        .send()
        .await()
        .unwrap();

    assert_eq!(res.status(), 400);
    let body: serde_json::Value = res.json().await.unwrap();
    assert!(body["error"].is_string());
}

#[tokio::test]
async fn test_create_order_empty_items() {
    let res = client()
        .post(format!("{}/orders", BASE_URL))
        .json(&json!({
            "customerId": "c-1",
            "items": []
        }))
        .send()
        .await()
        .unwrap();

    assert_eq!(res.status(), 400);
    let body: serde_json::Value = res.json().await.unwrap();
    assert!(body["error"].is_string());
}

#[tokio::test]
async fn test_create_order_quantity_zero() {
    let res = client()
        .post(format!("{}/orders", BASE_URL))
        .json(&json!({
            "customerId": "c-1",
            "items": [
                {
                    "sku": "A-1",
                    "quantity": 0,
                    "unitPriceCents": 100
                }
            ]
        }))
        .send()
        .await()
        .unwrap();

    assert_eq!(res.status(), 400);
    let body: serde_json::Value = res.json().await.unwrap();
    assert!(body["error"].is_string());
}

#[tokio::test]
async fn test_create_order_unit_price_zero() {
    let res = client()
        .post(format!("{}/orders", BASE_URL))
        .json(&json!({
            "customerId": "c-1",
            "items": [
                {
                    "sku": "A-1",
                    "quantity": 1,
                    "unitPriceCents": 0
                }
            ]
        }))
        .send()
        .await()
        .unwrap();

    assert_eq!(res.status(), 400);
    let body: serde_json::Value = res.json().await.unwrap();
    assert!(body["error"].is_string());
}

#[tokio::test]
async fn test_create_order_invalid_json() {
    let res = client()
        .post(format!("{}/orders", BASE_URL))
        .body("not json")
        .header("Content-Type", "application/json")
        .send()
        .await()
        .unwrap();

    assert_eq!(res.status(), 400);
    let body: serde_json::Value = res.json().await.unwrap();
    assert!(body["error"].is_string());
}
```