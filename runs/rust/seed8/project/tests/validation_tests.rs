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
