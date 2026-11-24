FILE: tests/validation_tests.rs
```rust
use axum::http::StatusCode;
use reqwest::Client;
use std::net::TcpListener;
use std::process::{Command, Stdio};
use std::thread;
use std::time::Duration;

fn get_free_port() -> u16 {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    listener.close().ok();
    port
}

fn start_server(port: u16) -> std::process::Child {
    let cargo_bin = format!("target/release/orders");
    Command::new(cargo_bin)
        .env("PORT", port.to_string())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap()
}

async fn wait_for_server(port: u16) {
    let client = Client::new();
    for _ in 0..50 {
        if client
            .get(format!("http://127.0.0.1:{}/health", port))
            .send()
            .await
            .unwrap()
            .status()
            .is_success()
        {
            return;
        }
        thread::sleep(Duration::from_millis(100));
    }
    panic!("Server did not start in time");
}

#[tokio::test]
async fn test_create_order_success() {
    let port = get_free_port();
    let child = start_server(port);
    wait_for_server(port).await;

    let client = Client::new();
    let body = serde_json::json!({
        "customerId": "c-1",
        "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]
    });

    let res = client
        .post(format!("http://127.0.0.1:{}/orders", port))
        .json(&body)
        .send()
        .await
        .unwrap();

    assert_eq!(res.status().as_u16(), StatusCode::CREATED.as_u16());
    
    child.kill().ok();
}

#[tokio::test]
async fn test_create_order_invalid_customer_id_too_short() {
    let port = get_free_port();
    let child = start_server(port);
    wait_for_server(port).await;

    let client = Client::new();
    let body = serde_json::json!({
        "customerId": "",
        "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
    });

    let res = client
        .post(format!("http://127.0.0.1:{}/orders", port))
        .json(&body)
        .send()
        .await
        .unwrap();

    assert_eq!(res.status().as_u16(), StatusCode::BAD_REQUEST.as_u16());
    
    child.kill().ok();
}

#[tokio::test]
async fn test_create_order_invalid_customer_id_too_long() {
    let port = get_free_port();
    let child = start_server(port);
    wait_for_server(port).await;

    let client = Client::new();
    let customer_id = "a".repeat(65);
    let body = serde_json::json!({
        "customerId": customer_id,
        "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
    });

    let res = client
        .post(format!("http://127.0.0.1:{}/orders", port))
        .json(&body)
        .send()
        .await
        .unwrap();

    assert_eq!(res.status().as_u16(), StatusCode::BAD_REQUEST.as_u16());
    
    child.kill().ok();
}

#[tokio::test]
async fn test_create_order_empty_items() {
    let port = get_free_port();
    let child = start_server(port);
    wait_for_server(port).await;

    let client = Client::new();
    let body = serde_json::json!({
        "customerId": "c-1",
        "items": []
    });

    let res = client
        .post(format!("http://127.0.0.1:{}/orders", port))
        .json(&body)
        .send()
        .await
        .unwrap();

    assert_eq!(res.status().as_u16(), StatusCode::BAD_REQUEST.as_u16());
    
    child.kill().ok();
}

#[tokio::test]
async fn test_create_order_too_many_items() {
    let port = get_free_port();
    let child = start_server(port);
    wait_for_server(port).await;

    let client = Client::new();
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

    let res = client
        .post(format!("http://127.0.0.1:{}/orders", port))
        .json(&body)
        .send()
        .await
        .unwrap();

    assert_eq!(res.status().as_u16(), StatusCode::BAD_REQUEST.as_u16());
    
    child.kill().ok();
}

#[tokio::test]
async fn test_create_order_invalid_quantity_zero() {
    let port = get_free_port();
    let child = start_server(port);
    wait_for_server(port).await;

    let client = Client::new();
    let body = serde_json::json!({
        "customerId": "c-1",
        "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]
    });

    let res = client
        .post(format!("http://127.0.0.1:{}/orders", port))
        .json(&body)
        .send()
        .await
        .unwrap();

    assert_eq!(res.status().as_u16(), StatusCode::BAD_REQUEST.as_u16());
    
    child.kill().ok();
}

#[tokio::test]
async fn test_create_order_invalid_quantity_too_high() {
    let port = get_free_port();
    let child = start_server(port);
    wait_for_server(port).await;

    let client = Client::new();
    let body = serde_json::json!({
        "customerId": "c-1",
        "items": [{"sku": "A-1", "quantity": 101, "unitPriceCents": 100}]
    });

    let res = client
        .post(format!("http://127.0.0.1:{}/orders", port))
        .json(&body)
        .send()
        .await
        .unwrap();

    assert_eq!(res.status().as_u16(), StatusCode::BAD_REQUEST.as_u16());
    
    child.kill().ok();
}

#[tokio::test]
async fn test_create_order_invalid_unit_price_zero() {
    let port = get_free_port();
    let child = start_server(port);
    wait_for_server(port).await;

    let client = Client::new();
    let body = serde_json::json!({
        "customerId": "c-1",
        "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 0}]
    });

    let res = client
        .post(format!("http://127.0.0.1:{}/orders", port))
        .json(&body)
        .send()
        .await
        .unwrap();

    assert_eq!(res.status().as_u16(), StatusCode::BAD_REQUEST.as_u16());
    
    child.kill().ok();
}

#[tokio::test]
async fn test_create_order_invalid_unit_price_too_high() {
    let port = get_free_port();
    let child = start_server(port);
    wait_for_server(port).await;

    let client = Client::new();
    let body = serde_json::json!({
        "customerId": "c-1",
        "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 1000001}]
    });

    let res = client
        .post(format!("http://127.0.0.1:{}/orders", port))
        .json(&body)
        .send()
        .await
        .unwrap();

    assert_eq!(res.status().as_u16(), StatusCode::BAD_REQUEST.as_u16());
    
    child.kill().ok();
}

#[tokio::test]
async fn test_create_order_invalid_sku_too_long() {
    let port = get_free_port();
    let child = start_server(port);
    wait_for_server(port).await;

    let client = Client::new();
    let body = serde_json::json!({
        "customerId": "c-1",
        "items": [{"sku": "a".repeat(33), "quantity": 1, "unitPriceCents": 100}]
    });

    let res = client
        .post(format!("http://127.0.0.1:{}/orders", port))
        .json(&body)
        .send()
        .await
        .unwrap();

    assert_eq!(res.status().as_u16(), StatusCode::BAD_REQUEST.as_u16());
    
    child.kill().ok();
}

#[tokio::test]
async fn test_get_order_404() {
    let port = get_free_port();
    let child = start_server(port);
    wait_for_server(port).await;

    let client = Client::new();
    let res = client
        .get(format!("http://127.0.0.1:{}/orders/non-existent-id", port))
        .send()
        .await
        .unwrap();

    assert_eq!(res.status().as_u16(), StatusCode::NOT_FOUND.as_u16());
    
    child.kill().ok();
}
```