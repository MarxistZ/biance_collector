use anyhow::{Context, Result, bail};
use serde_json::Value;

use crate::records::{BookLevel, FundingRecord, FuturesOrderBookRecord, SpotOrderBookRecord};

pub fn parse_spot_depth(
    message: &str,
    symbol: &str,
    local_timestamp: i64,
) -> Result<SpotOrderBookRecord> {
    let data: Value = serde_json::from_str(message).context("invalid spot depth JSON")?;
    let last_update_id = required_i64(&data, "lastUpdateId")?;
    let bids = required_levels(&data, "bids")?;
    let asks = required_levels(&data, "asks")?;

    Ok(SpotOrderBookRecord {
        timestamp: local_timestamp,
        local_timestamp,
        symbol: symbol.to_string(),
        market_type: "spot".to_string(),
        first_update_id: last_update_id,
        bids,
        asks,
        last_update_id,
    })
}

pub fn parse_futures_depth(
    message: &str,
    symbol: &str,
    local_timestamp: i64,
) -> Result<Option<FuturesOrderBookRecord>> {
    let data: Value = serde_json::from_str(message).context("invalid futures depth JSON")?;
    if data.get("e").and_then(Value::as_str) != Some("depthUpdate") {
        return Ok(None);
    }

    Ok(Some(FuturesOrderBookRecord {
        timestamp: required_i64(&data, "E")?,
        local_timestamp,
        symbol: symbol.to_string(),
        market_type: "futures".to_string(),
        transaction_time: required_i64(&data, "T")?,
        first_update_id: required_i64(&data, "U")?,
        prev_update_id: required_i64(&data, "pu")?,
        bids: required_levels(&data, "b")?,
        asks: required_levels(&data, "a")?,
        last_update_id: required_i64(&data, "u")?,
    }))
}

pub fn parse_funding(
    premium: &str,
    ticker: &str,
    open_interest: &str,
    symbol: &str,
    local_timestamp: i64,
) -> Result<FundingRecord> {
    let premium: Value = serde_json::from_str(premium).context("invalid premium index JSON")?;
    let ticker: Value = serde_json::from_str(ticker).context("invalid ticker JSON")?;
    let open_interest: Value =
        serde_json::from_str(open_interest).context("invalid open interest JSON")?;

    Ok(FundingRecord {
        timestamp: required_i64(&premium, "time")?,
        local_timestamp,
        symbol: symbol.to_string(),
        funding_rate: optional_f64(&premium, "lastFundingRate"),
        mark_price: optional_f64(&premium, "markPrice"),
        index_price: optional_f64(&premium, "indexPrice"),
        next_funding_time: optional_i64(&premium, "nextFundingTime"),
        open_interest: optional_f64(&open_interest, "openInterest"),
        volume_24h: optional_f64(&ticker, "volume"),
    })
}

fn required_i64(data: &Value, field: &str) -> Result<i64> {
    data.get(field)
        .and_then(value_to_i64)
        .with_context(|| format!("missing or invalid field {field}"))
}

fn optional_i64(data: &Value, field: &str) -> i64 {
    data.get(field).and_then(value_to_i64).unwrap_or_default()
}

fn optional_f64(data: &Value, field: &str) -> f64 {
    data.get(field).and_then(value_to_f64).unwrap_or_default()
}

fn value_to_i64(value: &Value) -> Option<i64> {
    value
        .as_i64()
        .or_else(|| value.as_str().and_then(|s| s.parse::<i64>().ok()))
}

fn value_to_f64(value: &Value) -> Option<f64> {
    value
        .as_f64()
        .or_else(|| value.as_str().and_then(|s| s.parse::<f64>().ok()))
}

fn required_levels(data: &Value, field: &str) -> Result<Vec<BookLevel>> {
    let levels = data
        .get(field)
        .and_then(Value::as_array)
        .with_context(|| format!("missing or invalid field {field}"))?;

    levels
        .iter()
        .map(|level| {
            let pair = level
                .as_array()
                .with_context(|| format!("invalid level in {field}"))?;
            if pair.len() < 2 {
                bail!("invalid level in {field}");
            }

            let price =
                value_to_f64(&pair[0]).with_context(|| format!("invalid price in {field}"))?;
            let qty = value_to_f64(&pair[1]).with_context(|| format!("invalid qty in {field}"))?;
            Ok(BookLevel { price, qty })
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_spot_partial_depth_record() {
        let json = r#"{
            "lastUpdateId": 160,
            "bids": [["50000.10", "1.25"], ["49999.00", "2.00"]],
            "asks": [["50001.20", "0.75"]]
        }"#;

        let record = parse_spot_depth(json, "BTCUSDT", 1_700_000_000_123).unwrap();

        assert_eq!(record.timestamp, 1_700_000_000_123);
        assert_eq!(record.local_timestamp, 1_700_000_000_123);
        assert_eq!(record.symbol, "BTCUSDT");
        assert_eq!(record.market_type, "spot");
        assert_eq!(record.first_update_id, 160);
        assert_eq!(record.last_update_id, 160);
        assert_eq!(record.bids[0].price, 50000.10);
        assert_eq!(record.bids[0].qty, 1.25);
        assert_eq!(record.asks[0].price, 50001.20);
        assert_eq!(record.asks[0].qty, 0.75);
    }

    #[test]
    fn parses_futures_depth_update_record() {
        let json = r#"{
            "e": "depthUpdate",
            "E": 1700000000100,
            "T": 1700000000090,
            "s": "BTCUSDT",
            "U": 100,
            "u": 120,
            "pu": 99,
            "b": [["50000.10", "1.25"]],
            "a": [["50001.20", "0.75"]]
        }"#;

        let record = parse_futures_depth(json, "BTCUSDT", 1_700_000_000_123)
            .unwrap()
            .unwrap();

        assert_eq!(record.timestamp, 1_700_000_000_100);
        assert_eq!(record.local_timestamp, 1_700_000_000_123);
        assert_eq!(record.symbol, "BTCUSDT");
        assert_eq!(record.market_type, "futures");
        assert_eq!(record.transaction_time, 1_700_000_000_090);
        assert_eq!(record.first_update_id, 100);
        assert_eq!(record.prev_update_id, 99);
        assert_eq!(record.last_update_id, 120);
        assert_eq!(record.bids[0].price, 50000.10);
        assert_eq!(record.asks[0].qty, 0.75);
    }

    #[test]
    fn combines_funding_rest_payloads() {
        let premium = r#"{
            "symbol": "BTCUSDT",
            "markPrice": "50000.1",
            "indexPrice": "49990.2",
            "lastFundingRate": "0.0001",
            "nextFundingTime": 1700000020000,
            "time": 1700000010000
        }"#;
        let ticker = r#"{"volume": "12345.6"}"#;
        let open_interest = r#"{"openInterest": "987.65"}"#;

        let record =
            parse_funding(premium, ticker, open_interest, "BTCUSDT", 1_700_000_010_123).unwrap();

        assert_eq!(record.timestamp, 1_700_000_010_000);
        assert_eq!(record.local_timestamp, 1_700_000_010_123);
        assert_eq!(record.symbol, "BTCUSDT");
        assert_eq!(record.funding_rate, 0.0001);
        assert_eq!(record.mark_price, 50000.1);
        assert_eq!(record.index_price, 49990.2);
        assert_eq!(record.next_funding_time, 1_700_000_020_000);
        assert_eq!(record.open_interest, 987.65);
        assert_eq!(record.volume_24h, 12345.6);
    }

    #[test]
    fn rejects_missing_required_spot_fields() {
        let error = parse_spot_depth(r#"{"bids":[],"asks":[]}"#, "BTCUSDT", 1).unwrap_err();

        assert!(error.to_string().contains("lastUpdateId"));
    }

    #[test]
    fn ignores_non_depth_futures_event() {
        assert!(
            parse_futures_depth(r#"{"e":"trade"}"#, "BTCUSDT", 1)
                .unwrap()
                .is_none()
        );
    }
}
