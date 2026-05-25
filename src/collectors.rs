use std::collections::HashMap;
use std::path::PathBuf;
use std::time::Duration;

use anyhow::{Context, Result};
use futures_util::StreamExt;
use rand::Rng;
use reqwest::StatusCode;
use tokio::sync::mpsc;
use tokio::task::JoinSet;
use tokio::time::{Instant, sleep, timeout};
use tokio_tungstenite::connect_async;
use tracing::{error, info, warn};

use crate::binance::{parse_funding, parse_futures_depth, parse_spot_depth};
use crate::config::Config;
use crate::paths::{funding_path, futures_path, spot_path, utc_hour};
use crate::writer::{
    CollectorRecord, write_funding_records, write_futures_records, write_spot_records,
};

pub async fn run(config: Config) -> Result<()> {
    std::fs::create_dir_all(&config.data_dir)?;
    std::fs::create_dir_all(&config.log_dir)?;

    let (tx, rx) = mpsc::channel(config.channel_capacity);
    let writer_config = config.clone();
    let writer = tokio::spawn(async move { writer_loop(writer_config, rx).await });

    let spot = tokio::spawn(run_spot_collectors(config.clone(), tx.clone()));
    let futures = tokio::spawn(run_futures_collectors(config.clone(), tx.clone()));
    let funding = tokio::spawn(run_funding_collector(config.clone(), tx.clone()));

    shutdown_signal().await?;
    info!("shutdown signal received");

    spot.abort();
    futures.abort();
    funding.abort();
    drop(tx);

    match timeout(config.save_interval + Duration::from_secs(10), writer).await {
        Ok(joined) => joined??,
        Err(_) => warn!("writer did not shut down before timeout"),
    }

    Ok(())
}

async fn run_spot_collectors(config: Config, tx: mpsc::Sender<CollectorRecord>) -> Result<()> {
    let mut tasks = JoinSet::new();
    for symbol in config.symbols.clone() {
        let config = config.clone();
        let tx = tx.clone();
        tasks.spawn(async move {
            supervise_websocket(
                symbol,
                config.spot_ws_base,
                config.depth_level,
                config.depth_speed,
                tx,
                true,
            )
            .await;
        });
    }
    while tasks.join_next().await.is_some() {}
    Ok(())
}

async fn run_futures_collectors(config: Config, tx: mpsc::Sender<CollectorRecord>) -> Result<()> {
    let mut tasks = JoinSet::new();
    for symbol in config.symbols.clone() {
        let config = config.clone();
        let tx = tx.clone();
        tasks.spawn(async move {
            supervise_websocket(
                symbol,
                config.futures_ws_base,
                config.depth_level,
                config.depth_speed,
                tx,
                false,
            )
            .await;
        });
    }
    while tasks.join_next().await.is_some() {}
    Ok(())
}

async fn supervise_websocket(
    symbol: String,
    base_url: String,
    depth_level: usize,
    depth_speed: String,
    tx: mpsc::Sender<CollectorRecord>,
    is_spot: bool,
) {
    let stream = format!(
        "{}@depth{}@{}",
        symbol.to_lowercase(),
        depth_level,
        depth_speed
    );
    let url = format!("{base_url}/{stream}");
    let mut attempt = 0_u32;

    loop {
        match collect_websocket(&url, &symbol, tx.clone(), is_spot).await {
            Ok(()) => attempt = 0,
            Err(err) => {
                attempt = attempt.saturating_add(1);
                warn!(%symbol, %err, "websocket disconnected");
            }
        }

        let delay = reconnect_delay(attempt);
        sleep(delay).await;
    }
}

async fn collect_websocket(
    url: &str,
    symbol: &str,
    tx: mpsc::Sender<CollectorRecord>,
    is_spot: bool,
) -> Result<()> {
    let (stream, _) = connect_async(url).await?;
    info!(%symbol, %url, "websocket connected");
    let (_, mut read) = stream.split();

    loop {
        let message = match timeout(Duration::from_secs(300), read.next()).await {
            Ok(Some(message)) => message,
            Ok(None) => return Ok(()),
            Err(_) => {
                warn!(%symbol, "stream has no data for 300 seconds");
                match timeout(Duration::from_secs(300), read.next()).await {
                    Ok(Some(message)) => message,
                    Ok(None) => return Ok(()),
                    Err(_) => anyhow::bail!("{symbol} had no data for 600 seconds"),
                }
            }
        };
        let message = message?;
        if !message.is_text() {
            continue;
        }
        let local_ts = now_ms();
        let text = message.to_text()?;
        let record = if is_spot {
            Some(CollectorRecord::Spot(parse_spot_depth(
                text, symbol, local_ts,
            )?))
        } else {
            parse_futures_depth(text, symbol, local_ts)?.map(CollectorRecord::Futures)
        };

        if let Some(record) = record {
            tx.send(record).await.context("writer channel closed")?;
        }
    }
}

async fn run_funding_collector(config: Config, tx: mpsc::Sender<CollectorRecord>) -> Result<()> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(5))
        .build()?;

    loop {
        let cycle_start = Instant::now();
        for symbol in &config.symbols {
            match fetch_funding(&client, &config.futures_rest_base, symbol).await {
                Ok((premium, ticker, open_interest)) => {
                    let record =
                        parse_funding(&premium, &ticker, &open_interest, symbol, now_ms())?;
                    tx.send(CollectorRecord::Funding(record))
                        .await
                        .context("writer channel closed")?;
                }
                Err(err) => warn!(%symbol, %err, "funding fetch failed"),
            }
            sleep(Duration::from_millis(100)).await;
        }

        let elapsed = cycle_start.elapsed();
        if elapsed < config.funding_poll_interval {
            sleep(config.funding_poll_interval - elapsed).await;
        }
    }
}

async fn fetch_funding(
    client: &reqwest::Client,
    base: &str,
    symbol: &str,
) -> Result<(String, String, String)> {
    let premium = get_text(client, base, "/fapi/v1/premiumIndex", symbol, true).await?;
    let ticker = get_text(client, base, "/fapi/v1/ticker/24hr", symbol, false)
        .await
        .unwrap_or_else(|_| "{}".to_string());
    let open_interest = get_text(client, base, "/fapi/v1/openInterest", symbol, false)
        .await
        .unwrap_or_else(|_| "{}".to_string());
    Ok((premium, ticker, open_interest))
}

async fn get_text(
    client: &reqwest::Client,
    base: &str,
    endpoint: &str,
    symbol: &str,
    required: bool,
) -> Result<String> {
    let url = format!("{base}{endpoint}");
    let response = client.get(url).query(&[("symbol", symbol)]).send().await?;
    match response.status() {
        StatusCode::OK => Ok(response.text().await?),
        StatusCode::TOO_MANY_REQUESTS => {
            sleep(Duration::from_secs(60)).await;
            anyhow::bail!("Binance rate limit 429")
        }
        StatusCode::IM_A_TEAPOT => {
            sleep(Duration::from_secs(600)).await;
            anyhow::bail!("Binance IP ban 418")
        }
        status if required => anyhow::bail!("required request failed with HTTP {status}"),
        status => anyhow::bail!("optional request failed with HTTP {status}"),
    }
}

async fn writer_loop(config: Config, mut rx: mpsc::Receiver<CollectorRecord>) -> Result<()> {
    let mut spot: HashMap<PathBuf, Vec<_>> = HashMap::new();
    let mut futures: HashMap<PathBuf, Vec<_>> = HashMap::new();
    let mut funding: HashMap<PathBuf, Vec<_>> = HashMap::new();
    let mut interval = tokio::time::interval(config.save_interval);

    loop {
        tokio::select! {
            record = rx.recv() => {
                match record {
                    Some(CollectorRecord::Spot(record)) => {
                        let path = spot_path(&config.data_dir, &record.symbol, &utc_hour(record.timestamp));
                        spot.entry(path).or_default().push(record);
                    }
                    Some(CollectorRecord::Futures(record)) => {
                        let path = futures_path(&config.data_dir, &record.symbol, &utc_hour(record.timestamp));
                        futures.entry(path).or_default().push(record);
                    }
                    Some(CollectorRecord::Funding(record)) => {
                        let path = funding_path(&config.data_dir, &record.symbol, &utc_hour(record.timestamp));
                        funding.entry(path).or_default().push(record);
                    }
                    None => break,
                }
            }
            _ = interval.tick() => {
                flush_all(&mut spot, &mut futures, &mut funding).await;
            }
        }
    }

    flush_all(&mut spot, &mut futures, &mut funding).await;
    Ok(())
}

async fn flush_all(
    spot: &mut HashMap<PathBuf, Vec<crate::records::SpotOrderBookRecord>>,
    futures: &mut HashMap<PathBuf, Vec<crate::records::FuturesOrderBookRecord>>,
    funding: &mut HashMap<PathBuf, Vec<crate::records::FundingRecord>>,
) {
    flush_map(spot, write_spot_records, "spot").await;
    flush_map(futures, write_futures_records, "futures").await;
    flush_map(funding, write_funding_records, "funding").await;
}

async fn flush_map<T>(
    buffers: &mut HashMap<PathBuf, Vec<T>>,
    writer: fn(&std::path::Path, &[T]) -> Result<()>,
    label: &str,
) {
    let paths: Vec<PathBuf> = buffers.keys().cloned().collect();
    for path in paths {
        let records = buffers.remove(&path).unwrap_or_default();
        if records.is_empty() {
            continue;
        }
        let count = records.len();
        match writer(&path, &records) {
            Ok(()) => info!(?path, count, dataset = label, "saved records"),
            Err(err) => {
                error!(?path, count, dataset = label, %err, "save failed; keeping records");
                buffers.entry(path).or_default().extend(records);
            }
        }
    }
}

fn reconnect_delay(attempt: u32) -> Duration {
    let base = 5_u64.saturating_mul(2_u64.saturating_pow(attempt.saturating_sub(1)));
    let capped = base.min(300);
    let jitter = rand::rng().random_range(0..=3);
    Duration::from_secs(capped + jitter)
}

fn now_ms() -> i64 {
    chrono::Utc::now().timestamp_millis()
}

async fn shutdown_signal() -> Result<()> {
    #[cfg(unix)]
    {
        let mut sigterm =
            tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
        tokio::select! {
            result = tokio::signal::ctrl_c() => result?,
            _ = sigterm.recv() => {}
        }
        Ok(())
    }

    #[cfg(not(unix))]
    {
        tokio::signal::ctrl_c().await?;
        Ok(())
    }
}
