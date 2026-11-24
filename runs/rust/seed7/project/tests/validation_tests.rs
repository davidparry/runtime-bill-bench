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
