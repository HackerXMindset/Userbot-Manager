use std::{net::SocketAddr, sync::Arc};

use anyhow::Result;
use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::get,
    Json, Router,
};
use tokio::sync::watch;
use tracing::{error, info};

use crate::api::{ApiClient, DexPayload};

#[derive(Clone)]
struct AppState {
    api_client: Arc<ApiClient>,
}

pub async fn run_http_server(
    api_client: Arc<ApiClient>,
    mut shutdown: watch::Receiver<bool>,
) -> Result<()> {
    let bind_addr = std::env::var("RUST_HTTP_ADDR").unwrap_or_else(|_| "0.0.0.0:8080".to_string());
    let addr: SocketAddr = bind_addr.parse()?;

    let state = AppState { api_client };
    let router = Router::new()
        .route("/dex/:address", get(get_dex_payload))
        .with_state(state);

    info!("HTTP server listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await?;

    axum::serve(listener, router.into_make_service())
        .with_graceful_shutdown(async move {
            while !*shutdown.borrow() {
                if shutdown.changed().await.is_err() {
                    break;
                }
            }
        })
        .await?;

    Ok(())
}

async fn get_dex_payload(
    State(state): State<AppState>,
    Path(address): Path<String>,
) -> Result<Json<DexPayload>, (StatusCode, String)> {
    match state.api_client.fetch_dex_payload(&address).await {
        Ok(payload) => Ok(Json(payload)),
        Err(err) => {
            error!("Dex payload error for {}: {:?}", address, err);
            Err((
                StatusCode::BAD_GATEWAY,
                "Failed to fetch Dex data".to_string(),
            ))
        }
    }
}
