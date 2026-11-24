FILE: tests/validation_tests.rs
```rust
use axum::http::StatusCode;
use reqwest::StatusCode as ReqwestStatusCode;

#[tokio::test]
async fn test_invalid_customer_id_too_short() {
    let client = reqwest::Client::new();
    let url = "http://127.0.0.1:8080/orders";
    
    let body = serde_json::json!({
        "customerId": "",
        "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
    });

    let res = client.post(url).json(&body).send().await.unwrap();
    assert_eq!(res.status(), ReqwestStatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_invalid_customer_id_too_long() {
    let client = reqwest::Client::new();
    let url = "http://127.0.0.1:8080/orders";
    
    let customer_id = "a".repeat(65);
    let body = serde_json::json!({
        "customerId": customer_id,
        "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
    });

    let res = client.post(url).json(&body).send().await.unwrap();
    assert_eq!(res.status(), ReqwestStatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_empty_items() {
    let client = reqwest::Client::new();
    let url = "http://127.0.0.1:8080/orders";
    
    let body = serde_json::json!({
        "customerId": "c-1",
        "items": []
    });

    let res = client.post(url).json(&body).send().await.unwrap();
    assert_eq!(res.status(), ReqwestStatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_too_many_items() {
    let client = reqwest::Client::new();
    let url = "http://127.0.0.1:8080/orders";
    
    let items: Vec<_> = (0..51).map(|i| {
        serde_json::json!({
            "sku": format!("SKU-{}", i),
            "quantity": 1,
            "unitPriceCents": 100
        })
    }).collect();
    
    let body = serde_json::json!({
        "customerId": "c-1",
        "items": items
    });

    let res = client.post(url).json(&body).send().await.unwrap();
    assert_eq!(res.status(), ReqwestStatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_invalid_quantity_zero() {
    let client = reqwest::Client::new();
    let url = "http://127.0.0.1:8080/orders";
    
    let body = serde_json::json!({
        "customerId": "c-1",
        "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]
    });

    let res = client.post(url).json(&body).send().await.unwrap();
    assert_eq!(res.status(), ReqwestStatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_invalid_quantity_too_high() {
    let client = reqwest::Client::new();
    let url = "http://127.0.0.1:8080/orders";
    
    let body = serde_json::json!({
        "customerId": "c-1",
        "items": [{"sku": "A-1", "quantity": 101, "unitPriceCents": 100}]
    });

    let res = client.post(url).json(&body).send().await.unwrap();
    assert_eq!(res.status(), ReqwestStatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_invalid_unit_price_zero() {
    let client = reqwest::Client::new();
    let url = "http://127.0.0.1:8080/orders";
    
    let body = serde_json::json!({
        "customerId": "c-1",
        "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]
    });

    let res = client.post(url).json(&body).send().await.unwrap();
    assert_eq!(res.status(), ReqwestStatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_invalid_unit_price_too_high() {
    let client = reqwest::Client::new();
    let url = "http://127.0.0.1:8080/orders";
    
    let body = serde_json::json!({
        "customerId": "c-1",
        "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 1000001}]
    });

    let res = client.post(url).json(&body).send().await.unwrap();
    assert_eq!(res.status(), ReqwestStatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_invalid_sku_too_long() {
    let client = reqwest::Client::new();
    let url = "http://127.0.0.1:8080/orders";
    
    let body = serde_json::json!({
        "customerId": "c-1",
        "items": [{"sku": "a".repeat(33), "quantity": 1, "unitPriceCents": 100}]
    });

    let res = client.post(url).json(&body).send().await.unwrap();
    assert_eq!(res.status(), ReqwestStatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_404_on_nonexistent_order() {
    let client = reqwest::Client::new();
    let url = "http://127.0.0.1:8080/orders/non-existent-id";
    
    let res = client.get(url).send().await.unwrap();
    assert_eq!(res.status(), ReqwestStatusCode::NOT_FOUND);
}
```