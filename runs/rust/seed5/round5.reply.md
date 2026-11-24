FILE: tests/integration_tests.rs
```rust
use reqwest::Client;
use serde_json::json;

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
        .await
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
        .await
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
        .await
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
        .await
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
        .await
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
        .await
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
        .await
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
        .await
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
        .await
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
        .await
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