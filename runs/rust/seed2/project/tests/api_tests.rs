use axum::http::{Request, StatusCode};
use hyper_util::client::legacy::Client;
use hyper_util::rt::TokioExecutor;
use orders::create_router;
use std::net::SocketAddr;
use tower::ServiceExt;

static INIT: tokio::sync::OnceCell<SocketAddr> = tokio::sync::OnceCell::const_new();

async fn get_addr() -> SocketAddr {
    INIT.get_or_init(|| async {
        let app = create_router();
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();

        tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });

        addr
    })
    .await
}

async fn make_request(path: &str, body: Option<serde_json::Value>) -> (StatusCode, String) {
    let addr = get_addr().await;
    let url = format!("http://127.0.0.1:{}/{}", addr.port(), path);

    let client: Client<_, hyper::body::Incoming> =
        Client::builder(TokioExecutor::new()).build_http();

    let req = if let Some(b) = body {
        Request::builder()
            .method("POST")
            .uri(&url)
            .header("Content-Type", "application/json")
            .body(hyper::body::Body::from(b.to_string()))
            .unwrap()
    } else {
        Request::builder()
            .method("GET")
            .uri(&url)
            .body(hyper::body::Body::empty())
            .unwrap()
    };

    let res = client.request(req).await.unwrap();
    let status = res.status();
    let body_bytes = hyper::body::to_bytes(res.into_body()).await.unwrap();
    let body_str = String::from_utf8(body_bytes.to_vec()).unwrap();

    (status, body_str)
}

#[tokio::test]
async fn test_health_check() {
    let (status, body) = make_request("/health", None).await;
    assert_eq!(status, StatusCode::OK);
    let json: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert_eq!(json["status"], "ok");
}

#[tokio::test]
async fn test_create_order_success() {
    let body = serde_json::json!({
        "customerId": "c-1",
        "items": [
            {"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}
        ]
    });
    let (status, response_body) = make_request("/orders", Some(body)).await;
    assert_eq!(status, StatusCode::CREATED);

    let json: serde_json::Value = serde_json::from_str(&response_body).unwrap();
    assert_eq!(json["customerId"], "c-1");
    assert_eq!(json["totalCents"], 2500);
    assert!(json["id"].is_string());
    assert!(json["createdAt"].is_string());
}

#[tokio::test]
async fn test_create_order_invalid_customer_id() {
    let body = serde_json::json!({
        "customerId": "",
        "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
    });
    let (status, response_body) = make_request("/orders", Some(body)).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    let json: serde_json::Value = serde_json::from_str(&response_body).unwrap();
    assert!(json["error"].is_string());
}

#[tokio::test]
async fn test_create_order_invalid_quantity() {
    let body = serde_json::json!({
        "customerId": "c-1",
        "items": [{"sku": "A-1", "quantity": 0, "unitPriceCents": 100}]
    });
    let (status, response_body) = make_request("/orders", Some(body)).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_get_order_404() {
    let (status, response_body) =
        make_request("/orders/non-existent-id", None).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
    let json: serde_json::Value = serde_json::from_str(&response_body).unwrap();
    assert!(json["error"].is_string());
}

#[tokio::test]
async fn test_get_order_success() {
    // Create first
    let create_body = serde_json::json!({
        "customerId": "c-1",
        "items": [{"sku": "A-1", "quantity": 1, "unitPriceCents": 100}]
    });
    let (status, response_body) = make_request("/orders", Some(create_body)).await;
    assert_eq!(status, StatusCode::CREATED);
    let json: serde_json::Value = serde_json::from_str(&response_body).unwrap();
    let order_id = json["id"].as_str().unwrap();

    // Retrieve
    let (status, get_body) = make_request(&format!("/orders/{}", order_id), None).await;
    assert_eq!(status, StatusCode::OK);
    let get_json: serde_json::Value = serde_json::from_str(&get_body).unwrap();
    assert_eq!(get_json["id"], order_id);
    assert_eq!(get_json["totalCents"], 100);
}
