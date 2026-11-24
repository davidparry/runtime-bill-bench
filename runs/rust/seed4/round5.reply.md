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
futures-util = "0.3"

[dev-dependencies]
reqwest = { version = "0.11", features = ["json"] }
tokio = { version = "1", features = ["full", "test-util"] }
```

FILE: tests/integration.rs
```rust
use axum::routing::get;
use axum::Router;
use orders::AppState;
use orders::create_order;
use orders::get_order;
use orders::OrderItem;
use serde::Deserialize;
use serde_json::json;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;

#[derive(Deserialize)]
struct ErrorResponse {
    error: String,
}

#[derive(Deserialize)]
struct OrderResponse {
    id: String,
    customer_id: String,
    items: Vec<OrderItem>,
    total_cents: i64,
    created_at: String,
}

#[tokio::test]
async fn test_get_order_not_found() {
    let orders = Arc::new(RwLock::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders/{id}", get(get_order))
        .with_state(state);

    let client = reqwest::Client::new();
    
    let res = client
        .get("http://localhost:8080/orders/non-existent-id")
        .send()
        .await
        .unwrap();

    assert_eq!(res.status(), reqwest::StatusCode::NOT_FOUND);
    
    let json: serde_json::Value = res.json().await.unwrap();
    assert!(json.get("error").is_some());
}

#[tokio::test]
async fn test_create_and_get_order() {
    let orders = Arc::new(RwLock::new(HashMap::new()));
    let state = AppState { orders };

    let app = Router::new()
        .route("/orders", axum::routing::post(create_order))
        .route("/orders/{id}", get(get_order))
        .with_state(state);

    let client = reqwest::Client::new();
    let body = json!({
        "customerId": "c-1",
        "items": [
            { "sku": "A-1", "quantity": 2, "unitPriceCents": 1250 }
        ]
    });

    let res = client
        .post("http://localhost:8080/orders")
        .json(&body)
        .send()
        .await
        .unwrap();

    assert_eq!(res.status(), reqwest::StatusCode::CREATED);
    
    let location = res.headers().get("Location").unwrap().to_str().unwrap();
    let order_id = location.trim_start_matches("/orders/");

    // Get the order
    let get_res = client
        .get(format!("http://localhost:8080/orders/{}", order_id))
        .send()
        .await
        .unwrap();

    assert_eq!(get_res.status(), reqwest::StatusCode::OK);
    
    let json: serde_json::Value = get_res.json().await.unwrap();
    assert_eq!(json["id"], order_id);
    assert_eq!(json["customerId"], "c-1");
    assert_eq!(json["totalCents"], 2500);
}
```