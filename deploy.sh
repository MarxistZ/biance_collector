#!/usr/bin/env bash
# Binance Collector deployment script
# Usage: ./deploy.sh [build|start|stop|restart|status]

set -euo pipefail

SERVICE_NAME="binance-collector"
BINARY="./target/release/binance-collector"
PID_FILE="collector.pid"
LOG_DIR="logs"
CONFIG_FILE="${CONFIG_FILE:-config.toml}"

log_info() {
    printf '[INFO] %s\n' "$1"
}

log_warn() {
    printf '[WARN] %s\n' "$1"
}

log_error() {
    printf '[ERROR] %s\n' "$1" >&2
}

build() {
    log_info "Building release binary..."
    cargo build --release
}

start() {
    if [ ! -x "$BINARY" ]; then
        build
    fi

    if [ -f "$PID_FILE" ]; then
        PID="$(cat "$PID_FILE")"
        if ps -p "$PID" >/dev/null 2>&1; then
            log_warn "$SERVICE_NAME is already running (PID: $PID)"
            return
        fi
    fi

    mkdir -p "$LOG_DIR"
    if [ ! -f "$CONFIG_FILE" ] && [ -f "config.example.toml" ]; then
        cp config.example.toml "$CONFIG_FILE"
        log_info "Created $CONFIG_FILE from config.example.toml"
    fi

    nohup "$BINARY" --config "$CONFIG_FILE" >> "$LOG_DIR/nohup.log" 2>&1 &
    echo "$!" > "$PID_FILE"
    sleep 2

    PID="$(cat "$PID_FILE")"
    if ps -p "$PID" >/dev/null 2>&1; then
        log_info "$SERVICE_NAME started (PID: $PID)"
    else
        log_error "$SERVICE_NAME failed to start. Check $LOG_DIR/nohup.log"
        exit 1
    fi
}

stop() {
    if [ ! -f "$PID_FILE" ]; then
        log_warn "$SERVICE_NAME is not running"
        return
    fi

    PID="$(cat "$PID_FILE")"
    if ps -p "$PID" >/dev/null 2>&1; then
        log_info "Stopping $SERVICE_NAME (PID: $PID)..."
        kill -TERM "$PID"
        for _ in $(seq 1 30); do
            if ! ps -p "$PID" >/dev/null 2>&1; then
                rm -f "$PID_FILE"
                log_info "$SERVICE_NAME stopped"
                return
            fi
            sleep 1
        done
        log_error "$SERVICE_NAME did not stop within 30 seconds"
        exit 1
    fi

    rm -f "$PID_FILE"
    log_warn "Removed stale PID file"
}

status() {
    if [ -f "$PID_FILE" ]; then
        PID="$(cat "$PID_FILE")"
        if ps -p "$PID" >/dev/null 2>&1; then
            log_info "$SERVICE_NAME is running (PID: $PID)"
            ps -p "$PID" -o pid,ppid,cmd,%mem,%cpu,etime
            return
        fi
    fi
    log_warn "$SERVICE_NAME is not running"
}

case "${1:-}" in
    build)
        build
        ;;
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        start
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 {build|start|stop|restart|status}"
        exit 1
        ;;
esac
