#!/bin/bash
# Binance Collector Deployment Script
# Usage: ./deploy.sh [install|start|stop|restart|status]

set -e

INSTALL_DIR="/opt/binance_collector"
DATA_DIR="/data"
SERVICE_NAME="binance-collector"
PYTHON_CMD="python3"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Please run as root or with sudo"
        exit 1
    fi
}

install() {
    log_info "Starting installation..."

    # Check system dependencies
    log_info "Checking system dependencies..."
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 not found. Installing..."
        apt-get update && apt-get install -y python3 python3-pip python3-venv
    fi

    # Create data directory
    if [ ! -d "$DATA_DIR" ]; then
        log_warn "$DATA_DIR does not exist. Creating..."
        mkdir -p "$DATA_DIR"
        chmod 755 "$DATA_DIR"
    fi

    # Check if running from correct directory
    if [ ! -f "main.py" ]; then
        log_error "main.py not found. Please run from project directory"
        exit 1
    fi

    # Create virtual environment
    log_info "Creating Python virtual environment..."
    $PYTHON_CMD -m venv venv

    # Install dependencies
    log_info "Installing Python dependencies..."
    ./venv/bin/pip3 install -r requirements.txt

    # Set permissions
    chmod +x *.sh 2>/dev/null || true

    log_info "Installation completed successfully"
}

start() {
    log_info "Starting $SERVICE_NAME..."

    # Check if venv exists
    if [ ! -d "venv" ]; then
        log_error "Virtual environment not found. Run './deploy.sh install' first"
        exit 1
    fi

    # Check if already running
    if [ -f "collector.pid" ]; then
        PID=$(cat collector.pid)
        if ps -p $PID > /dev/null 2>&1; then
            log_warn "Collector is already running (PID: $PID)"
            exit 0
        fi
    fi

    # Start collector
    nohup ./venv/bin/python3 main.py > logs/nohup.log 2>&1 &
    echo $! > collector.pid

    sleep 2

    if ps -p $(cat collector.pid) > /dev/null 2>&1; then
        log_info "Collector started successfully (PID: $(cat collector.pid))"
    else
        log_error "Failed to start collector. Check logs/nohup.log"
        exit 1
    fi
}

stop() {
    log_info "Stopping $SERVICE_NAME..."

    if [ ! -f "collector.pid" ]; then
        log_warn "PID file not found. Collector may not be running"
        return
    fi

    PID=$(cat collector.pid)
    if ps -p $PID > /dev/null 2>&1; then
        kill -TERM $PID
        sleep 3

        if ps -p $PID > /dev/null 2>&1; then
            log_warn "Process still running, forcing kill..."
            kill -9 $PID
        fi

        rm -f collector.pid
        log_info "Collector stopped"
    else
        log_warn "Collector is not running"
        rm -f collector.pid
    fi
}

restart() {
    stop
    sleep 2
    start
}

status() {
    if [ -f "collector.pid" ]; then
        PID=$(cat collector.pid)
        if ps -p $PID > /dev/null 2>&1; then
            log_info "Collector is running (PID: $PID)"
            ps -p $PID -o pid,ppid,cmd,%mem,%cpu,etime
        else
            log_warn "PID file exists but process is not running"
        fi
    else
        log_warn "Collector is not running"
    fi

    # Show data directory size
    if [ -d "$DATA_DIR" ]; then
        echo ""
        log_info "Data directory: $(du -sh $DATA_DIR 2>/dev/null | cut -f1)"
    fi
}

case "$1" in
    install)
        check_root
        install
        ;;
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 {install|start|stop|restart|status}"
        echo ""
        echo "Commands:"
        echo "  install  - Install dependencies and setup environment (requires root)"
        echo "  start    - Start the collector"
        echo "  stop     - Stop the collector"
        echo "  restart  - Restart the collector"
        echo "  status   - Show collector status"
        exit 1
        ;;
esac

exit 0
