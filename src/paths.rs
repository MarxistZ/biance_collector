use std::path::{Path, PathBuf};

use chrono::{DateTime, Utc};

pub fn spot_path(root: &Path, symbol: &str, hour: &str) -> PathBuf {
    root.join("spot")
        .join(symbol)
        .join(format!("spot_{symbol}_{hour}.parquet"))
}

pub fn futures_path(root: &Path, symbol: &str, hour: &str) -> PathBuf {
    root.join("futures")
        .join(symbol)
        .join(format!("future_{symbol}_{hour}.parquet"))
}

pub fn funding_path(root: &Path, symbol: &str, hour: &str) -> PathBuf {
    root.join("futures")
        .join(symbol)
        .join(format!("funding_{symbol}_{hour}.parquet"))
}

pub fn utc_hour(timestamp_ms: i64) -> String {
    DateTime::<Utc>::from_timestamp_millis(timestamp_ms)
        .unwrap_or(DateTime::<Utc>::UNIX_EPOCH)
        .format("%Y%m%d%H")
        .to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    #[test]
    fn builds_python_compatible_hourly_paths() {
        let root = Path::new("data");

        assert_eq!(
            spot_path(root, "BTCUSDT", "2026052516"),
            Path::new("data/spot/BTCUSDT/spot_BTCUSDT_2026052516.parquet")
        );
        assert_eq!(
            futures_path(root, "ETHUSDT", "2026052516"),
            Path::new("data/futures/ETHUSDT/future_ETHUSDT_2026052516.parquet")
        );
        assert_eq!(
            funding_path(root, "SOLUSDT", "2026052516"),
            Path::new("data/futures/SOLUSDT/funding_SOLUSDT_2026052516.parquet")
        );
    }

    #[test]
    fn formats_utc_hour() {
        assert_eq!(utc_hour(1_700_000_000_000), "2023111422");
    }
}
