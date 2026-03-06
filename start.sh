#!/bin/bash
# Binance数据采集器启动脚本

# 脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 配置
PID_FILE="$SCRIPT_DIR/collector.pid"
LOG_DIR="$SCRIPT_DIR/logs"
PYTHON_CMD="python3"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查Python环境
check_python() {
    if ! command -v $PYTHON_CMD &> /dev/null; then
        echo -e "${RED}错误: 未找到 $PYTHON_CMD${NC}"
        exit 1
    fi
}

# 检查依赖
check_dependencies() {
    echo "检查Python依赖..."
    $PYTHON_CMD -c "import websocket, pandas, pyarrow, requests" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo -e "${YELLOW}警告: 缺少依赖，尝试安装...${NC}"
        pip install -r requirements.txt
    fi
}

# 检查是否已运行
is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            return 0
        else
            # PID文件存在但进程不存在，清理
            rm -f "$PID_FILE"
            return 1
        fi
    fi
    return 1
}

# 启动采集器
start() {
    if is_running; then
        PID=$(cat "$PID_FILE")
        echo -e "${YELLOW}采集器已在运行 (PID: $PID)${NC}"
        exit 1
    fi

    echo "启动Binance数据采集器..."

    # 创建日志目录
    mkdir -p "$LOG_DIR"

    # 启动程序（后台运行）
    nohup $PYTHON_CMD main.py > "$LOG_DIR/nohup.log" 2>&1 &
    PID=$!

    # 保存PID
    echo $PID > "$PID_FILE"

    # 等待2秒检查是否启动成功
    sleep 2

    if ps -p $PID > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 采集器启动成功 (PID: $PID)${NC}"
        echo "日志文件: $LOG_DIR/main.log"
        echo "查看日志: tail -f $LOG_DIR/main.log"
    else
        echo -e "${RED}✗ 采集器启动失败${NC}"
        echo "查看错误日志: cat $LOG_DIR/nohup.log"
        rm -f "$PID_FILE"
        exit 1
    fi
}

# 停止采集器
stop() {
    if ! is_running; then
        echo -e "${YELLOW}采集器未运行${NC}"
        exit 1
    fi

    PID=$(cat "$PID_FILE")
    echo "停止采集器 (PID: $PID)..."

    # 发送SIGTERM信号（优雅关闭）
    kill -TERM $PID

    # 等待最多30秒
    for i in {1..30}; do
        if ! ps -p $PID > /dev/null 2>&1; then
            echo -e "${GREEN}✓ 采集器已停止${NC}"
            rm -f "$PID_FILE"
            exit 0
        fi
        sleep 1
    done

    # 如果还未停止，强制杀死
    echo -e "${YELLOW}采集器未响应，强制停止...${NC}"
    kill -9 $PID
    rm -f "$PID_FILE"
    echo -e "${GREEN}✓ 采集器已强制停止${NC}"
}

# 重启采集器
restart() {
    echo "重启采集器..."
    if is_running; then
        stop
        sleep 2
    fi
    start
}

# 查看状态
status() {
    if is_running; then
        PID=$(cat "$PID_FILE")
        echo -e "${GREEN}采集器运行中${NC}"
        echo "PID: $PID"
        echo "运行时间: $(ps -p $PID -o etime= | tr -d ' ')"
        echo "内存使用: $(ps -p $PID -o rss= | awk '{printf "%.1f MB\n", $1/1024}')"
        echo "CPU使用: $(ps -p $PID -o %cpu= | tr -d ' ')%"
        echo ""
        echo "日志文件:"
        ls -lh "$LOG_DIR"/*.log 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
    else
        echo -e "${RED}采集器未运行${NC}"
        exit 1
    fi
}

# 查看日志
logs() {
    if [ ! -d "$LOG_DIR" ]; then
        echo -e "${RED}日志目录不存在${NC}"
        exit 1
    fi

    LOG_FILE="$LOG_DIR/main.log"
    if [ ! -f "$LOG_FILE" ]; then
        echo -e "${RED}日志文件不存在: $LOG_FILE${NC}"
        exit 1
    fi

    # 默认显示最后100行，支持-f参数实时跟踪
    if [ "$1" == "-f" ]; then
        tail -f "$LOG_FILE"
    else
        tail -n 100 "$LOG_FILE"
    fi
}

# 显示帮助
usage() {
    cat << EOF
Binance数据采集器管理脚本

用法: $0 {start|stop|restart|status|logs}

命令:
  start      启动采集器（后台运行）
  stop       停止采集器（优雅关闭）
  restart    重启采集器
  status     查看运行状态
  logs       查看日志（最后100行）
  logs -f    实时跟踪日志

示例:
  $0 start          # 启动采集器
  $0 status         # 查看状态
  $0 logs -f        # 实时查看日志
  $0 stop           # 停止采集器

EOF
}

# 主逻辑
case "$1" in
    start)
        check_python
        check_dependencies
        start
        ;;
    stop)
        stop
        ;;
    restart)
        check_python
        check_dependencies
        restart
        ;;
    status)
        status
        ;;
    logs)
        logs "$2"
        ;;
    *)
        usage
        exit 1
        ;;
esac
