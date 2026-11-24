use orders::create_app;
use std::env;
use tokio::signal;

#[tokio::main]
async fn main() {
    let app = create_app();

    let port = env::var("PORT").unwrap_or_else(|_| "8080".to_string());
    let port: u16 = port.parse().unwrap_or(8080);

    let listener = tokio::net::TcpListener::bind(format!("0.0.0.0:{}", port))
        .await
        .unwrap();

    println!("Listening on 0.0.0.0:{}", port);

    let shutdown_handle = tokio::spawn(async move {
        signal::ctrl_c().await.expect("failed to listen for ctrl-c");
        println!("Received SIGTERM, shutting down...");
    });

    axum::serve(listener, app)
        .with_graceful_shutdown(async move {
            let _ = shutdown_handle.await;
        })
        .await
        .unwrap();
        
    println!("Server shut down gracefully.");
}
