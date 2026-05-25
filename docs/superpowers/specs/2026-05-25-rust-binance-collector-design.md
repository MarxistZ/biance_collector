# Rust Binance Collector Design

## Purpose

Replace the current Python Binance collector with a simpler Rust collector that is easier to run for long periods. The Rust program collects data and writes local Parquet files only. PikPak upload stays in rclone scripts.

The existing data layout and schemas are preserved so old and new data can be queried the same way.

## Fixed Decisions

- Keep the current hourly single-file layout.
- Do not write chunked Parquet files.
- Do not call rclone from Rust.
- Keep spot depth, futures depth, and futures funding/stat data.
- Keep the current default symbols:
  `BTCUSDT`, `ETHUSDT`, `BNBUSDT`, `SOLUSDT`, `XRPUSDT`, `DOGEUSDT`, `AVAXUSDT`, `LINKUSDT`.

## Data Sources

The collector uses Binance public market data only.

- Spot order book depth: `<symbol>@depth20@100ms`
  Source: https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams
- USD-M futures order book depth: `<symbol>@depth20@100ms`
  Source: https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Partial-Book-Depth-Streams
- USD-M futures REST data:
  - premium index
  - 24h ticker
  - open interest

Sources:

- https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price
- https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics
- https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest

## Runtime Shape

Use one Rust binary with four long-running async tasks:

1. Spot depth collector.
2. Futures depth collector.
3. Funding/stat collector.
4. Parquet writer.

Collectors parse Binance messages into typed records and send them through bounded channels. The writer is the only task that owns file buffers and writes Parquet files. This avoids shared mutable state and avoids per-symbol writer threads.

```text
Binance WebSocket/REST
  -> collector task
  -> bounded channel
  -> single writer task
  -> .parquet.tmp
  -> atomic rename
  -> hourly .parquet file
```

## Configuration

Keep configuration small:

- `config.toml` for symbols, data directory, endpoints, intervals, and depth.
- Built-in defaults matching the Python project.
- Environment variables only for standard runtime controls such as log level.

Default paths:

- Use `/data` if it exists and is writable.
- Otherwise use local `data/`.
- Write logs to local `logs/`.

## File Layout

Preserve the current layout exactly:

```text
data/
├── spot/{SYMBOL}/spot_{SYMBOL}_{YYYYMMDDHH}.parquet
└── futures/{SYMBOL}/
    ├── future_{SYMBOL}_{YYYYMMDDHH}.parquet
    └── funding_{SYMBOL}_{YYYYMMDDHH}.parquet
```

Temporary files are written next to the final file:

```text
spot_BTCUSDT_2026052516.parquet.tmp
future_BTCUSDT_2026052516.parquet.tmp
funding_BTCUSDT_2026052516.parquet.tmp
```

rclone scripts must ignore `*.tmp`.

## Writer Strategy

The writer keeps unsaved records grouped by target file path. Every save interval:

1. For each target file with unsaved records, build the full output table.
2. If the hourly file already exists, read it and append the unsaved rows.
3. Write the result to a `.tmp` file in the same directory.
4. Close the file and verify the Parquet metadata can be read.
5. Rename the `.tmp` file over the final hourly file.
6. Clear that file's unsaved records only after rename succeeds.

If writing fails, the writer keeps the unsaved records and retries on the next interval. No collector thread reads or writes Parquet directly.

This keeps the current single-file hourly format. The tradeoff is that the active hourly file is rewritten repeatedly during the hour, so the writer should log save duration and row counts.

## Schemas

Match `old/raw_data_schema.md`.

Spot order book:

- `timestamp`, `local_timestamp`, `symbol`, `market_type`
- `first_update_id`, `last_update_id`
- `bid1_price` through `bid20_price`
- `bid1_qty` through `bid20_qty`
- `ask1_price` through `ask20_price`
- `ask1_qty` through `ask20_qty`

Futures order book:

- `timestamp`, `local_timestamp`, `symbol`, `market_type`
- `transaction_time`, `first_update_id`, `prev_update_id`, `last_update_id`
- `bid1_price` through `bid20_price`
- `bid1_qty` through `bid20_qty`
- `ask1_price` through `ask20_price`
- `ask1_qty` through `ask20_qty`

Funding/stat:

- `timestamp`, `local_timestamp`, `symbol`
- `funding_rate`, `mark_price`, `index_price`
- `next_funding_time`, `open_interest`, `volume_24h`

Use `int64`, `float64`, and strings as in the Python schema.

## Robustness Rules

Keep these rules in the first Rust version:

- Bounded channels so memory cannot grow without limit.
- Reconnect WebSockets with exponential backoff and jitter.
- Treat 5 minutes without data as a warning.
- Reconnect a stream after 10 minutes without data.
- Use request timeouts for REST calls.
- Handle Binance `429` by backing off and `418` by sleeping longer.
- Check disk space before writing.
- Write temp files and atomically rename them.
- On `SIGINT` or `SIGTERM`, stop collectors, flush writer buffers, then exit.

Do not add extra supervision frameworks, plugin systems, embedded schedulers, or a database unless a concrete failure requires it.

## rclone Scripts

rclone sync is outside the Rust program.

Keep scripts simple:

- `scripts/sync_pikpak.sh`: run the actual rclone command.
- `scripts/sync_completed_hours.sh`: choose files older than the current UTC hour and call `sync_pikpak.sh`.

Script requirements:

- Ignore `*.tmp`.
- Default to completed-hour files.
- Allow a manual force mode for current-hour files after the collector is stopped.
- Keep PikPak credentials in rclone config.

rclone PikPak backend source: https://rclone.org/pikpak/

## Deployment

Replace the Python deployment flow with a Rust flow:

- Build with `cargo build --release`.
- Run the release binary from `deploy.sh`.
- Keep `start`, `stop`, `restart`, and `status` commands.
- Keep rclone upload scripts separate from collector start/stop.

## Success Criteria

The Rust rewrite is done when:

- It writes the same three dataset types as the Python collector.
- It uses the same directory and file naming layout.
- Parquet columns and types match `old/raw_data_schema.md`.
- It survives WebSocket disconnects and resumes collection.
- It flushes remaining records on shutdown.
- It never leaves a final `.parquet` file from a partial write.
- rclone scripts can sync completed-hour files while ignoring active `.tmp` files.

## Tests

Start with focused tests:

- Spot depth JSON parses into the expected record.
- Futures depth JSON parses into the expected record.
- Funding REST JSON responses combine into the expected record.
- Bad JSON or missing fields return errors instead of panicking.
- File naming matches the Python format.
- Writer preserves old rows and new rows when rewriting an hourly file.
- Writer keeps unsaved rows when a write fails.
- Sync file selection excludes `*.tmp` and the current UTC hour by default.
