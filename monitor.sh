#!/bin/bash
# Binance数据采集器监控脚本
# 用于监控采集器运行状态，可配置为cron任务

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/collector.pid"
LOG_DIR="$SCRIPT_DIR/logs"
DATA_DIR="$SCRIPT_DIR/data"

# 告警配置
ALERT_EMAIL=""  # 留空则不发送邮件
ALERT_WEBHOOK=""  # 钉钉/企业微信webhook URL

# 检查进程是否运行
check_process() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# 检查磁盘空间（GB）
check_disk_space() {
    local free_space=$(df "$DATA_DIR" | awk 'NR==2 {print $4}')
    local free_gb=$((free_space / 1024 / 1024))

    if [ $free_gb -lt 5 ]; then
        echo "WARNING: 磁盘空间不足 ${free_gb}GB"
        return 1
    fi
    return 0
}

# 检查最近是否有数据文件生成
check_recent_data() {
    local recent_files=$(find "$DATA_DIR" -name "*.parquet" -mmin -10 | wc -l)

    if [ $recent_files -eq 0 ]; then
        echo "WARNING: 最近10分钟无新数据文件生成"
        return 1
    fi
    return 0
}

# 检查日志中的错误
check_errors() {
    local error_count=$(grep -i "error\|critical" "$LOG_DIR/main.log" 2>/dev/null | tail -n 100 | wc -l)

    if [ $error_count -gt 10 ]; then
        echo "WARNING: 最近日志中有 ${error_count} 条错误"
        return 1
    fi
    return 0
}

# 检查内存使用（MB）
check_memory() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            local mem_mb=$(ps -p $PID -o rss= | awk '{print $1/1024}')
            local mem_int=${mem_mb%.*}

            if [ $mem_int -gt 1024 ]; then
                echo "WARNING: 内存使用过高 ${mem_int}MB"
                return 1
            fi
        fi
    fi
    return 0
}

# 发送告警
send_alert() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local full_message="[Binance Collector Alert] $timestamp\n$message"

    # 发送邮件
    if [ -n "$ALERT_EMAIL" ]; then
        echo -e "$full_message" | mail -s "Binance Collector Alert" "$ALERT_EMAIL"
    fi

    # 发送Webhook（钉钉/企业微信）
    if [ -n "$ALERT_WEBHOOK" ]; then
        curl -X POST "$ALERT_WEBHOOK" \
            -H 'Content-Type: application/json' \
            -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"$full_message\"}}" \
            > /dev/null 2>&1
    fi

    # 记录到日志
    echo -e "$full_message" >> "$LOG_DIR/monitor.log"
}

# 自动重启
auto_restart() {
    echo "尝试自动重启采集器..."
    ./start.sh restart

    if [ $? -eq 0 ]; then
        send_alert "采集器已自动重启"
    else
        send_alert "采集器自动重启失败，需要人工介入"
    fi
}

# 主监控逻辑
main() {
    local issues=()

    # 检查进程
    if ! check_process; then
        issues+=("进程未运行")
        auto_restart
        return
    fi

    # 检查磁盘空间
    if ! check_disk_space; then
        issues+=("磁盘空间不足")
    fi

    # 检查数据生成
    if ! check_recent_data; then
        issues+=("无新数据生成")
    fi

    # 检查错误日志
    if ! check_errors; then
        issues+=("日志中有大量错误")
    fi

    # 检查内存使用
    if ! check_memory; then
        issues+=("内存使用过高")
    fi

    # 如果有问题，发送告警
    if [ ${#issues[@]} -gt 0 ]; then
        local message="检测到以下问题:\n"
        for issue in "${issues[@]}"; do
            message+="- $issue\n"
        done
        send_alert "$message"
    fi

    # 输出状态报告
    if [ "$1" == "--verbose" ]; then
        echo "=== Binance Collector 监控报告 ==="
        echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
        echo ""

        if check_process; then
            PID=$(cat "$PID_FILE")
            echo "✓ 进程状态: 运行中 (PID: $PID)"
            echo "  运行时间: $(ps -p $PID -o etime= | tr -d ' ')"
            echo "  内存使用: $(ps -p $PID -o rss= | awk '{printf "%.1f MB\n", $1/1024}')"
            echo "  CPU使用: $(ps -p $PID -o %cpu= | tr -d ' ')%"
        else
            echo "✗ 进程状态: 未运行"
        fi

        echo ""
        echo "磁盘空间: $(df -h "$DATA_DIR" | awk 'NR==2 {print $4}') 可用"
        echo "数据目录大小: $(du -sh "$DATA_DIR" 2>/dev/null | awk '{print $1}')"
        echo "最近10分钟新文件: $(find "$DATA_DIR" -name "*.parquet" -mmin -10 | wc -l) 个"
        echo "总数据文件: $(find "$DATA_DIR" -name "*.parquet" 2>/dev/null | wc -l) 个"

        if [ ${#issues[@]} -gt 0 ]; then
            echo ""
            echo "⚠ 发现问题:"
            for issue in "${issues[@]}"; do
                echo "  - $issue"
            done
        fi

        echo ""
        echo "==================================="
    fi
}

# 运行监控
main "$@"
