use std::path::PathBuf;
use std::time::Duration;

use anyhow::Result;
use serde::Deserialize;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Config {
    pub symbols: Vec<String>,
    pub spot_ws_base: String,
    pub futures_ws_base: String,
    pub futures_rest_base: String,
    pub depth_level: usize,
    pub depth_speed: String,
    pub funding_poll_interval: Duration,
    pub save_interval: Duration,
    pub data_dir: PathBuf,
    pub log_dir: PathBuf,
    pub channel_capacity: usize,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            symbols: default_symbols(),
            spot_ws_base: "wss://stream.binance.com:9443/ws".to_string(),
            futures_ws_base: "wss://fstream.binance.com/ws".to_string(),
            futures_rest_base: "https://fapi.binance.com".to_string(),
            depth_level: 20,
            depth_speed: "100ms".to_string(),
            funding_poll_interval: Duration::from_secs(15),
            save_interval: Duration::from_secs(10),
            data_dir: default_data_dir(),
            log_dir: PathBuf::from("logs"),
            channel_capacity: 10_000,
        }
    }
}

#[derive(Debug, Deserialize, Default)]
struct FileConfig {
    symbols: Option<Vec<String>>,
    spot_ws_base: Option<String>,
    futures_ws_base: Option<String>,
    futures_rest_base: Option<String>,
    depth_level: Option<usize>,
    depth_speed: Option<String>,
    funding_poll_interval_secs: Option<u64>,
    save_interval_secs: Option<u64>,
    data_dir: Option<PathBuf>,
    log_dir: Option<PathBuf>,
    channel_capacity: Option<usize>,
}

impl Config {
    pub fn load(path: Option<&std::path::Path>) -> Result<Self> {
        let mut config = Self::default();
        let Some(path) = path else {
            return Ok(config);
        };
        if !path.exists() {
            return Ok(config);
        }

        let raw = std::fs::read_to_string(path)?;
        let file: FileConfig = toml::from_str(&raw)?;

        if let Some(value) = file.symbols {
            config.symbols = value;
        }
        if let Some(value) = file.spot_ws_base {
            config.spot_ws_base = value;
        }
        if let Some(value) = file.futures_ws_base {
            config.futures_ws_base = value;
        }
        if let Some(value) = file.futures_rest_base {
            config.futures_rest_base = value;
        }
        if let Some(value) = file.depth_level {
            config.depth_level = value;
        }
        if let Some(value) = file.depth_speed {
            config.depth_speed = value;
        }
        if let Some(value) = file.funding_poll_interval_secs {
            config.funding_poll_interval = Duration::from_secs(value);
        }
        if let Some(value) = file.save_interval_secs {
            config.save_interval = Duration::from_secs(value);
        }
        if let Some(value) = file.data_dir {
            config.data_dir = value;
        }
        if let Some(value) = file.log_dir {
            config.log_dir = value;
        }
        if let Some(value) = file.channel_capacity {
            config.channel_capacity = value;
        }

        Ok(config)
    }
}

fn default_symbols() -> Vec<String> {
    [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT",
    ]
    .into_iter()
    .map(str::to_string)
    .collect()
}

fn default_data_dir() -> PathBuf {
    let data = PathBuf::from("/data");
    if data.is_dir() && can_write_dir(&data) {
        data
    } else {
        PathBuf::from("data")
    }
}

fn can_write_dir(path: &std::path::Path) -> bool {
    let probe = path.join(".binance_collector_write_test");
    match std::fs::OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&probe)
    {
        Ok(_) => {
            let _ = std::fs::remove_file(probe);
            true
        }
        Err(_) => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_match_python_collector_symbols_and_intervals() {
        let config = Config::default();

        assert_eq!(
            config.symbols,
            vec![
                "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT",
                "LINKUSDT"
            ]
        );
        assert_eq!(config.depth_level, 20);
        assert_eq!(config.depth_speed, "100ms");
        assert_eq!(config.funding_poll_interval, Duration::from_secs(15));
        assert_eq!(config.save_interval, Duration::from_secs(10));
        assert_eq!(config.log_dir, PathBuf::from("logs"));
    }
}
