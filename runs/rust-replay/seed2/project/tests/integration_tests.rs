use axum::http::{HeaderName, StatusCode};
use hyper::body::Bytes;
use hyper_util::rt::TokioExecutor;
use orders::AppState; // Note: AppState is not pub in main, so we need to expose it or test via HTTP
// Since AppState is inside main, we can't easily inject it into tests unless we make it pub or use a separate test helper.
// Better approach: Spin up the server and hit it.

use std::net::SocketAddr;
use tower::ServiceBuilder;
use tower::ServiceExt; // for ready()
use axum::Router;
use tokio::sync::OnceCell;

// We need to make AppState public or create a test setup function.
// To keep files clean, I'll modify main.rs slightly to expose a test setup function if needed,
// but usually integration tests hit the network.

// However, the prompt says "Return every file in the project". I can't modify main.rs structure arbitrarily if I already returned it.
// I will make AppState pub(crate) or pub in main.rs? 
// Actually, I'll just write the integration tests to hit the server.

static ADDR: OnceCell<SocketAddr> = OnceCell::const_new();

async fn get_addr() -> &'static SocketAddr {
    ADDR.get_or_init(|| async {
        let state = orders::AppState::new();
        let app = Router::new()
            .route("/orders", axum::routing::post(orders::handlers::create_order)) // This won't work if handlers aren't pub
            .route("/orders/{id}", axum::routing::get(orders::handlers::get_order))
            .route("/health", axum::routing::get(orders::handlers::health_check))
            .with_state(state);
        
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        
        tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        
        &addr
    }).await
}

// This approach is tricky because handlers are not pub.
// I will refactor main.rs to make handlers and AppState accessible for testing, 
// OR I will write the tests to just start the binary? No, that's slow.
// I will make AppState and handlers pub(crate) or pub in main.rs?
// The prompt says "Return every file". I will update main.rs to expose what's needed.

// Actually, simpler: I'll write the tests as unit tests inside `src/main.rs` or a `src/lib.rs`?
// The prompt says "binary target".
// I'll add a `tests` directory.

// To make testing possible without changing main.rs structure too much, 
// I'll assume the test harness can run `cargo test`.
// I will write the tests in `tests/api_tests.rs` and they will use `hyper::Client` to hit the server.
// But I need to start the server first.

// Let's refine the plan:
// 1. main.rs exposes AppState and handlers as `pub` for testing? No, that's bad practice.
// 2. Instead, I'll put the logic in a separate module `app.rs` and include it in main.
// But I can only return files I create.
// I'll create `src/app.rs` and `src/main.rs`.

// Let's re-structure slightly to allow clean testing.
