use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;
use tracing_subscriber::EnvFilter;

use binance_collector::collectors;
use binance_collector::config::Config;

#[derive(Debug, Parser)]
#[command(name = "binance-collector")]
#[command(about = "Collect Binance public market data into hourly Parquet files")]
struct Cli {
    #[arg(short, long, default_value = "config.toml")]
    config: PathBuf,
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    let config = Config::load(Some(&cli.config))?;
    init_logging(&config)?;
    collectors::run(config).await
}

fn init_logging(config: &Config) -> Result<()> {
    std::fs::create_dir_all(&config.log_dir)?;
    let file_appender = tracing_appender::rolling::daily(&config.log_dir, "collector.log");
    let (non_blocking, guard) = tracing_appender::non_blocking(file_appender);
    Box::leak(Box::new(guard));

    let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_writer(non_blocking)
        .with_ansi(false)
        .init();
    Ok(())
}
