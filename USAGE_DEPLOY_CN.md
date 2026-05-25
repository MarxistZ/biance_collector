# Binance Collector 使用和部署说明

本文档只说明 Rust 版采集器的使用、部署、运行管理和 PikPak 同步方式。

## 1. 程序作用

本程序采集 Binance 公共行情数据，并保存为本地 Parquet 文件。

采集内容：

- 现货 orderbook 深度：`<symbol>@depth20@100ms`
- U 本位合约 orderbook 深度：`<symbol>@depth20@100ms`
- U 本位合约资金费率和市场统计数据

默认交易对：

```text
BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, DOGEUSDT, AVAXUSDT, LINKUSDT
```

PikPak 上传不在 Rust 程序内执行，使用 `scripts/` 里的 rclone 脚本单独同步。

## 2. 环境要求

服务器需要：

- Rust/Cargo
- rclone
- 可写数据目录，推荐 `/data`

检查命令：

```bash
cargo --version
rclone version
```

如果没有配置 PikPak remote，先执行：

```bash
rclone config
```

建议 remote 名称使用：

```text
pikpak
```

默认同步目标是：

```text
pikpak:binance_collector
```

## 3. 配置文件

第一次启动时，`deploy.sh start` 会自动把 `config.example.toml` 复制为 `config.toml`。

也可以手动复制：

```bash
cp config.example.toml config.toml
```

默认配置：

```toml
symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT"]
spot_ws_base = "wss://stream.binance.com:9443/ws"
futures_ws_base = "wss://fstream.binance.com/ws"
futures_rest_base = "https://fapi.binance.com"
depth_level = 20
depth_speed = "100ms"
funding_poll_interval_secs = 15
save_interval_secs = 10
data_dir = "data"
log_dir = "logs"
channel_capacity = 10000
```

如果服务器有 `/data` 并且想写入 `/data`，把配置改成：

```toml
data_dir = "/data"
```

## 4. 构建

在项目目录执行：

```bash
./deploy.sh build
```

生成的二进制文件：

```text
target/release/binance-collector
```

## 5. 启动、停止、查看状态

启动：

```bash
./deploy.sh start
```

停止：

```bash
./deploy.sh stop
```

重启：

```bash
./deploy.sh restart
```

查看状态：

```bash
./deploy.sh status
```

指定其他配置文件：

```bash
CONFIG_FILE=/path/to/config.toml ./deploy.sh start
```

## 6. 数据目录结构

程序保持原 Python 版本的小时文件布局：

```text
data/
├── spot/{SYMBOL}/spot_{SYMBOL}_{YYYYMMDDHH}.parquet
└── futures/{SYMBOL}/
    ├── future_{SYMBOL}_{YYYYMMDDHH}.parquet
    └── funding_{SYMBOL}_{YYYYMMDDHH}.parquet
```

示例：

```text
data/spot/BTCUSDT/spot_BTCUSDT_2026052516.parquet
data/futures/BTCUSDT/future_BTCUSDT_2026052516.parquet
data/futures/BTCUSDT/funding_BTCUSDT_2026052516.parquet
```

程序写文件时会先写临时文件：

```text
*.parquet.tmp
```

写入成功并校验后，再原子替换成最终的 `.parquet` 文件。同步脚本会忽略 `*.tmp`。

## 7. 日志

启动脚本输出：

```text
logs/nohup.log
```

Rust 程序日志：

```text
logs/collector.log.YYYY-MM-DD
```

查看最近日志：

```bash
tail -f logs/nohup.log
tail -f logs/collector.log.*
```

## 8. 同步到 PikPak

### 8.1 同步已完成小时文件

推荐日常使用这个脚本：

```bash
./scripts/sync_completed_hours.sh
```

它会：

- 查找 `data/` 下的 `.parquet` 文件
- 跳过当前 UTC 小时的文件
- 跳过 `*.tmp`
- 复制到临时 staging 目录
- 调用 rclone 上传到 PikPak

默认上传目标：

```text
pikpak:binance_collector
```

### 8.2 修改 PikPak 目标目录

使用环境变量：

```bash
PIKPAK_REMOTE="pikpak:/my/path/binance_collector" ./scripts/sync_completed_hours.sh
```

### 8.3 指定数据目录

如果数据写在 `/data`：

```bash
DATA_DIR=/data ./scripts/sync_completed_hours.sh
```

### 8.4 强制同步当前小时

一般不建议同步当前小时，因为采集器可能还在重写当前小时文件。

如果已经停止采集器，可以强制同步：

```bash
FORCE_CURRENT=1 ./scripts/sync_completed_hours.sh
```

### 8.5 直接同步某个目录

```bash
./scripts/sync_pikpak.sh data
```

或：

```bash
PIKPAK_REMOTE="pikpak:/my/path/binance_collector" ./scripts/sync_pikpak.sh /data
```

## 9. 推荐定时同步

可以用 cron 每小时同步一次已完成小时文件。

编辑 crontab：

```bash
crontab -e
```

示例，每小时第 5 分钟同步：

```cron
5 * * * * cd /path/to/biance_collector && DATA_DIR=/data PIKPAK_REMOTE="pikpak:binance_collector" ./scripts/sync_completed_hours.sh >> logs/rclone.log 2>&1
```

如果使用项目本地 `data/`：

```cron
5 * * * * cd /path/to/biance_collector && ./scripts/sync_completed_hours.sh >> logs/rclone.log 2>&1
```

## 10. 常见操作

完整部署流程：

```bash
cp config.example.toml config.toml
# 按需编辑 config.toml
./deploy.sh build
./deploy.sh start
./deploy.sh status
```

停止后同步所有文件：

```bash
./deploy.sh stop
FORCE_CURRENT=1 ./scripts/sync_completed_hours.sh
```

查看本地数据大小：

```bash
du -sh data
du -sh /data
```

查看进程：

```bash
cat collector.pid
ps -p "$(cat collector.pid)" -o pid,ppid,cmd,%mem,%cpu,etime
```

## 11. 故障排查

### 程序启动失败

查看：

```bash
tail -100 logs/nohup.log
```

常见原因：

- `config.toml` 格式错误
- 无法写入 `data_dir`
- 网络无法连接 Binance

### 没有生成数据

检查：

```bash
./deploy.sh status
tail -f logs/nohup.log
find data -type f | head
```

如果 `data_dir = "/data"`，改查：

```bash
find /data -type f | head
```

### rclone 上传失败

检查：

```bash
rclone listremotes
rclone lsd pikpak:
tail -100 logs/rclone.log
```

如果 remote 名称不是 `pikpak`，同步时指定：

```bash
PIKPAK_REMOTE="你的remote名:binance_collector" ./scripts/sync_completed_hours.sh
```

### 磁盘空间不足

查看：

```bash
df -h
du -sh data /data 2>/dev/null
```

程序写 Parquet 前会检查目标目录剩余空间，低于 1 GiB 会跳过保存并记录错误。

## 12. 注意事项

- rclone 不要同步 `*.parquet.tmp`。
- 默认只同步已完成 UTC 小时，避免上传正在被重写的当前小时文件。
- 当前小时文件会被程序重复读取、追加、重写，这是为了保持原来的单小时单文件布局。
- 修改交易对后需要重启采集器。
- 修改 `data_dir` 后，rclone 同步脚本也要用相同的 `DATA_DIR`。
