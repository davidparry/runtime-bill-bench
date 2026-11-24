FILE: src/middleware.rs
```rust
use axum::http::Request;
use serde_json::json;
use std::time::Instant;
use tower::Layer;
use tower::Service;
use tower::ServiceExt;

#[derive(Clone)]
pub struct JsonLogger;

impl<S> Layer<S> for JsonLogger {
    type Service = JsonLoggerLayer<S>;

    fn layer(&self, service: S) -> Self::Service {
        JsonLoggerLayer { service }
    }
}

#[derive(Clone)]
pub struct JsonLoggerLayer<S> {
    service: S,
}

impl<S, B> Service<Request<B>> for JsonLoggerLayer<S>
where
    S: Service<Request<B>, Response = axum::http::Response<B>> + Clone + Send + 'static,
    S::Error: std::fmt::Display,
    S::Future: Send + 'static,
    B: Send + 'static,
{
    type Response = axum::http::Response<B>;
    type Error = S::Error;
    type Future =
        std::pin::Pin<Box<dyn std::future::Future<Output = Result<Self::Response, Self::Error>> + Send>>;

    fn poll_ready(
        &mut self,
        cx: &mut std::task::Context<'_>,
    ) -> std::task::Poll<Result<(), Self::Error>> {
        self.service.poll_ready(cx)
    }

    fn call(&mut self, mut req: Request<B>) -> Self::Future {
        let method = req.method().to_string();
        let path = req.uri().path().to_string();
        let start = Instant::now();

        let service = self.service.clone();
        Box::pin(async move {
            let res = service.oneshot(req).await?;
            let duration = start.elapsed();
            let status = res.status().as_u16();

            let log_entry = json!({
                "method": method,
                "path": path,
                "status": status,
                "durationMs": duration.as_millis()
            });

            println!("{}", serde_json::to_string(&log_entry).unwrap());

            Ok(res)
        })
    }
}
```