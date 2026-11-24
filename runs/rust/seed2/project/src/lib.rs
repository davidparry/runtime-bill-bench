use axum::{
    routing::{get, post},
    Router,
};

pub mod handlers;
pub mod middleware;
pub mod state;

pub fn create_router() -> Router {
    let state = state::AppState::new();

    let app = Router::new()
        .route("/orders", post(handlers::create_order))
        .route("/orders/{id}", get(handlers::get_order))
        .route("/health", get(handlers::health_check))
        .with_state(state);

    // Apply logging layer
    app.layer(middleware::JsonLogger)
}
