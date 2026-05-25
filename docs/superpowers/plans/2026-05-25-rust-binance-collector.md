# Rust Binance Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Rust replacement for the Python Binance collector that writes the same local hourly Parquet files and leaves PikPak upload to rclone scripts.

**Architecture:** One Tokio binary runs three collection loops and one writer. Collectors parse Binance data into typed records and send them over bounded channels. The writer owns all Parquet buffers and uses temp files plus atomic rename for hourly single-file writes.

**Tech Stack:** Rust, Tokio, tokio-tungstenite, reqwest, serde, parquet/arrow, tracing, clap, toml, shell scripts for rclone.

---

### Task 1: Rust Project Skeleton

**Files:**
- Create: `Cargo.toml`
- Create: `src/lib.rs`
- Create: `src/main.rs`
- Create: `src/config.rs`

- [ ] Add a minimal Cargo project with dependencies.
- [ ] Add `Config::default()` matching the Python defaults.
- [ ] Add a test that checks default symbols and paths.
- [ ] Run `cargo test config`.

### Task 2: Data Types and Binance Parsers

**Files:**
- Create: `src/records.rs`
- Create: `src/binance.rs`

- [ ] Write tests for spot depth, futures depth, funding merge, and missing-field failures.
- [ ] Run parser tests and verify they fail because code is missing.
- [ ] Implement typed records and parsers.
- [ ] Run parser tests and verify they pass.

### Task 3: File Naming and Parquet Writer

**Files:**
- Create: `src/paths.rs`
- Create: `src/writer.rs`

- [ ] Write tests for exact Python-compatible paths.
- [ ] Write tests that a rewrite keeps old and new rows.
- [ ] Implement path helpers and writer.
- [ ] Run writer tests and verify they pass.

### Task 4: Collectors and Runtime

**Files:**
- Create: `src/collectors.rs`
- Modify: `src/main.rs`

- [ ] Add async spot, futures, and funding loops.
- [ ] Add bounded channels and graceful shutdown.
- [ ] Add reconnect/backoff for WebSockets and REST timeout handling.
- [ ] Run `cargo test` and `cargo build`.

### Task 5: rclone Scripts and Deploy Script

**Files:**
- Create: `scripts/sync_pikpak.sh`
- Create: `scripts/sync_completed_hours.sh`
- Modify: `deploy.sh`

- [ ] Add sync scripts that ignore `*.tmp` and default to completed UTC hours.
- [ ] Replace Python deploy behavior with Rust build/start/stop/status behavior.
- [ ] Add script tests or shell syntax checks.
- [ ] Run `bash -n deploy.sh scripts/*.sh`.

### Task 6: Final Verification

**Files:**
- Modify as needed based on test/build results.

- [ ] Run `cargo fmt --check`.
- [ ] Run `cargo test`.
- [ ] Run `cargo build --release`.
- [ ] Run `bash -n deploy.sh scripts/*.sh`.
- [ ] Review `git diff` for unrelated changes.
