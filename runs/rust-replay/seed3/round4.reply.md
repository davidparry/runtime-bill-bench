FILE: tests/validation_tests.rs
```rust
use axum::http::StatusCode;
use reqwest::Client;
use std::net::TcpListener;

fn create_test_app() -> axum::Router {
    use orders::AppState;
    use std::sync::Arc;
    use tokio::sync::RwLock;

    let state = AppState {
        orders: Arc::new(RwLock::new(Vec::new())),
    };
    axum::Router::new()
        .route("/orders", axum::routing::post(|state: axum::extract::State<AppState>, body: String| async move {
            orders::create_order(state, body).await
        }))
        .route("/orders/{id}", axum::routing::get(|state: axum::extract::State<AppState>, Path(id): axum::extract::Path<String>| async move {
            orders::get_order(state, id).await
        }))
        .route("/health", axum::routing::get(|| async {
            orders::health_check().await
        }))
        .with_state(state)
}

// Note: The previous implementation had a complex handler signature that didn't match the exported functions.
// To fix the compilation and testing issues cleanly, we will move the logic into functions that can be called by the router
// and also tested directly if needed, but here we will just fix the test file to use standard HTTP client testing
// against a running server or mock. However, since we can't easily run a server in a unit test without async runtime complexity
// in the test file itself without proper setup, and the previous test file was malformed, let's replace it with a simpler
// integration-style test structure that actually works with the binary.

// Actually, the simplest fix for the harness is to ensure the binary compiles and the tests compile.
// The previous test file tried to import internal modules which failed.
// Let's rewrite the test file to be a proper integration test that starts a server in the background.

// However, axum's TestClient is often easier for unit/integration tests within the same crate.
// Let's use axum::http::StatusCode from the 'http' crate which reqwest also depends on (usually compatible or we cast).
// The error was `reqwest::StatusCode` vs `axum::http::StatusCode`.
// We should compare against the status code value (u16) or use `reqwest::StatusCode` for both.

// Let's rewrite the test file to be clean and compilable.

mod tests {
    use axum::http::StatusCode;
    use reqwest::Client;
    use std::process::{Command, Stdio};
    use std::thread;
    use std::time::Duration;

    // Helper to find a free port
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

    fn wait_for_server(port: u16) {
        let client = Client::new();
        for _ in 0..50 {
            if client.get(format!("http://127.0.0.1:{}/health", port)).send().await.unwrap().status().is_success() {
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

        assert_eq!(res.status(), StatusCode::CREATED);
        
        // Cleanup
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

        assert_eq!(res.status(), StatusCode::BAD_REQUEST);
        
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

        assert_eq!(res.status(), StatusCode::BAD_REQUEST);
        
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

        assert_eq!(res.status(), StatusCode::BAD_REQUEST);
        
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

        assert_eq!(res.status(), StatusCode::BAD_REQUEST);
        
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

        assert_eq!(res.status(), StatusCode::BAD_REQUEST);
        
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

        assert_eq!(res.status(), StatusCode::BAD_REQUEST);
        
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

        assert_eq!(res.status(), StatusCode::BAD_REQUEST);
        
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

        assert_eq!(res.status(), StatusCode::BAD_REQUEST);
        
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

        assert_eq!(res.status(), StatusCode::BAD_REQUEST);
        
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

        assert_eq!(res.status(), StatusCode::NOT_FOUND);
        
        child.kill().ok();
    }
}
```