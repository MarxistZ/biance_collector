# Rust Binance Collector Design

## Context

The current Python project collects Binance market data and writes hourly Parquet files:

- Spot partial order book depth for configured symbols.
- USD-M futures partial order book depth for configured symbols.
- USD-M futures funding and market statistics from REST endpoints.

The Rust replacement keeps the same data product and directory layout while improving runtime robustness. PikPak upload remains outside the collector and is handled by rclone scripts.

## Goals

- Replace the Python collector with a Rust binary.
- Preserve the existing hourly single-file layout and Parquet schemas where practical.
- Improve long-running reliability on a small VPS.
- Make writes safer with temp files and atomic rename.
- Keep rclone/PikPak sync separate from the Rust program.
- Support graceful shutdown that flushes buffered data before exit.

## Non-Goals

- No embedded rclone calls from Rust.
- No chunked Parquet file layout.
- No change to collected symbols unless configuration overrides them.
- No trading, order placement, or private Binance API usage.
- No direct PikPak API integration.

## External Contracts

The collector uses Binance public market data APIs:

- Spot WebSocket streams: `wss://stream.binance.com:9443/ws/<streamName>` and stream names such as `<symbol>@depth20@100ms`.
  Source: https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams
- USD-M futures partial book depth streams: `<symbol>@depth<levels>@100ms`.
  Source: https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Partial-Book-Depth-Streams
- USD-M futures REST market data for premium index, 24h ticker, and open interest.
  Sources:
  - https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price
  - https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics
  - https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest

rclone is configured and operated outside the Rust process.

- PikPak backend documentation: https://rclone.org/pikpak/

## Configuration

Configuration should be loaded from a checked-in example config plus environment overrides.

Default values match the current Python project:

- Symbols: `BTCUSDT`, `ETHUSDT`, `BNBUSDT`, `SOLUSDT`, `XRPUSDT`, `DOGEUSDT`, `AVAXUSDT`, `LINKUSDT`
- Spot WebSocket base: `wss://stream.binance.com:9443/ws`
- Futures WebSocket base: `wss://fstream.binance.com/ws`
- Futures REST base: `https://fapi.binance.com`
- Depth level: `20`
- Depth speed: `100ms`
- Funding poll interval: `15s`
- Save interval: `10s`
- Data directory: `/data` if writable, otherwise local `data`
- Log directory: local `logs`

## Architecture

The Rust program is one binary with async task supervision.

Primary components:

- `config`: load and validate runtime configuration.
- `binance`: parse Binance WebSocket and REST payloads into internal records.
- `collectors`: run spot, futures, and funding collection loops.
- `writer`: buffer records by dataset and symbol, then write hourly Parquet files.
- `health`: track last message time, connection state, reconnect attempts, and buffer pressure.
- `shutdown`: coordinate signal handling, task cancellation, final flush, and exit.

Data flow:

```text
Binance WebSocket/REST
  -> parser
  -> bounded async channel
  -> writer buffer
  -> hourly Parquet temp file
  -> validated atomic rename
  -> final hourly Parquet file
```

## File Layout

The Rust collector preserves the current layout exactly:

```text
data/
├── spot/{SYMBOL}/spot_{SYMBOL}_{YYYYMMDDHH}.parquet
└── futures/{SYMBOL}/
    ├── future_{SYMBOL}_{YYYYMMDDHH}.parquet
    └── funding_{SYMBOL}_{YYYYMMDDHH}.parquet
```

Temporary files use the same directory as the target file:

```text
spot_BTCUSDT_2026052516.parquet.tmp
future_BTCUSDT_2026052516.parquet.tmp
funding_BTCUSDT_2026052516.parquet.tmp
```

rclone scripts must ignore `*.tmp`.

## Write Strategy

Because the user chose the existing hourly single-file layout, the writer appends by rewriting the hourly file:

1. Drain buffered records for a dataset and symbol.
2. Read existing hourly Parquet file if present.
3. Concatenate existing rows and new rows.
4. Write the full table to a `.tmp` file in the same directory.
5. Open/read the `.tmp` file to validate it as Parquet.
6. Atomically rename `.tmp` over the target file.
7. If any step fails, keep the drained records in memory and retry on the next save cycle.

This keeps the current analysis workflow intact, but the hourly file grows during the hour. The implementation should keep batch sizes bounded and log save latency so file growth problems are visible.

## Schemas

The Rust schemas should match `raw_data_schema.md`.

Spot order book:

- `timestamp`
- `local_timestamp`
- `symbol`
- `market_type`
- `first_update_id`
- `bid1_price` through `bid20_price`
- `bid1_qty` through `bid20_qty`
- `ask1_price` through `ask20_price`
- `ask1_qty` through `ask20_qty`
- `last_update_id`

Futures order book:

- `timestamp`
- `local_timestamp`
- `symbol`
- `market_type`
- `transaction_time`
- `first_update_id`
- `prev_update_id`
- `bid1_price` through `bid20_price`
- `bid1_qty` through `bid20_qty`
- `ask1_price` through `ask20_price`
- `ask1_qty` through `ask20_qty`
- `last_update_id`

Funding:

- `timestamp`
- `local_timestamp`
- `symbol`
- `funding_rate`
- `mark_price`
- `index_price`
- `next_funding_time`
- `open_interest`
- `volume_24h`

Numeric fields remain `int64` or `float64`; symbols and market type remain strings.

## Robustness

The Rust collector should improve these areas:

- Bounded channels to prevent unbounded memory growth.
- Per-source reconnect with exponential backoff and jitter.
- WebSocket ping/pong support through the selected Rust WebSocket library.
- Health warnings when a symbol has no data for 5 minutes.
- Forced reconnect when a symbol has no data for 10 minutes.
- Disk space checks before save.
- Atomic temp-file replacement for Parquet writes.
- Graceful shutdown on `SIGINT` and `SIGTERM`.
- Structured logs with per-component context.
- REST request timeouts and handling for Binance `429` and `418` responses.

## rclone Sync Scripts

rclone is script-managed, not Rust-managed.

Expected scripts:

- `scripts/sync_pikpak.sh`: sync selected local data to a configured PikPak remote.
- `scripts/sync_completed_hours.sh`: sync files older than the current UTC hour by default.

Script behavior:

- Ignore `*.tmp`.
- Prefer syncing completed previous-hour files.
- Optionally provide a manual mode for current-hour files after the collector is stopped.
- Leave rclone remote names and credentials in rclone config, not in Rust config.

## Deployment

The existing `deploy.sh` should be replaced or extended for Rust:

- Build release binary with Cargo.
- Install binary under the project or a configured install directory.
- Create `data` and `logs` directories.
- Start/stop/status commands should manage the Rust process.
- rclone scripts remain separate commands or cron/systemd timer jobs.

## Testing

Implementation should use test-first development for parsing and writer behavior.

Initial test coverage:

- Spot depth payload parses into the expected schema fields.
- Futures depth payload parses into the expected schema fields.
- Funding REST payloads combine into one funding record.
- Invalid payloads are rejected without panics.
- Hourly file naming matches the existing Python format.
- Writer preserves existing rows when rewriting an hourly file.
- Writer keeps drained records if temp write or rename fails.
- rclone scripts ignore `*.tmp` files and select completed-hour files.

## Open Decisions

The following decisions are fixed by user direction:

- Preserve hourly single-file layout.
- Do not use chunked Parquet files.
- Keep rclone/PikPak sync in scripts, not in Rust.

The implementation may choose specific Rust crates after checking current official crate documentation and compatibility.
