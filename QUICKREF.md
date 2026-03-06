# 快速参考

## 常用命令

### 启动和停止
```bash
./start.sh start      # 启动采集器
./start.sh stop       # 停止采集器
./start.sh restart    # 重启采集器
./start.sh status     # 查看状态
```

### 查看日志
```bash
./start.sh logs       # 查看最后100行日志
./start.sh logs -f    # 实时跟踪日志
tail -f logs/main.log # 直接查看主日志
```

### 监控
```bash
./monitor.sh --verbose  # 查看详细监控报告
watch -n 60 './monitor.sh --verbose'  # 每分钟刷新监控
```

### 数据检查
```bash
# 查看数据目录大小
du -sh data/

# 查看今天的数据
find data/ -name "*.parquet" -mtime -1

# 统计数据文件数量
find data/ -name "*.parquet" | wc -l
```

## 配置cron自动任务

**注意：** 以下示例使用 `/opt/binance_collector` 作为安装路径（生产环境标准）。如果您的安装路径不同，请相应调整。

```bash
# 编辑crontab
crontab -e

# 添加以下任务

# 开机自启动
@reboot cd /opt/binance_collector && ./start.sh start

# 每5分钟检查一次（自动重启）
*/5 * * * * cd /opt/binance_collector && ./monitor.sh

# 每天凌晨2点清理30天前的日志
0 2 * * * find /opt/binance_collector/logs/ -name "*.log.*" -mtime +30 -delete

# 每周日凌晨3点备份数据
0 3 * * 0 tar -czf /backup/binance_$(date +\%Y\%m\%d).tar.gz /data/
```

## systemd服务管理

```bash
# 安装服务
sudo cp binance-collector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable binance-collector
sudo systemctl start binance-collector

# 管理服务
sudo systemctl status binance-collector   # 查看状态
sudo systemctl restart binance-collector  # 重启
sudo systemctl stop binance-collector     # 停止
sudo journalctl -u binance-collector -f   # 查看日志
```

## Docker管理

```bash
# 启动
docker-compose up -d

# 查看状态
docker-compose ps
docker-compose logs -f

# 停止
docker-compose down

# 重启
docker-compose restart

# 更新
git pull
docker-compose up -d --build
```

## 故障排查

```bash
# 检查进程
ps aux | grep main.py

# 检查网络连接
netstat -anp | grep python3

# 查看错误日志
grep -i error logs/main.log | tail -20

# 检查磁盘空间
df -h

# 检查内存使用
free -h

# 手动运行（调试）
python3 main.py
```

## 性能监控

```bash
# 实时监控进程
top -p $(cat collector.pid)

# 查看网络流量
iftop

# 查看磁盘I/O
iotop

# 监控数据增长
watch -n 60 'du -sh data/'
```

## 配置修改

编辑 `config.py`:

```python
# 修改交易对
SPOT_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
FUTURES_SYMBOLS = ["BTCUSDT", "ETHUSDT"]

# 修改数据目录
DATA_DIR = "/mnt/data"
```

修改后重启:
```bash
./start.sh restart
```

## 告警配置

编辑 `monitor.sh`:

```bash
# 邮件告警
ALERT_EMAIL="your@email.com"

# 钉钉/企业微信Webhook
ALERT_WEBHOOK="https://your-webhook-url"
```

## 备份和恢复

```bash
# 备份数据
tar -czf backup_$(date +%Y%m%d).tar.gz data/

# 恢复数据
tar -xzf backup_20260307.tar.gz

# 备份到远程服务器
rsync -avz data/ user@remote:/backup/binance/
```

## 日志分析

```bash
# 统计错误数量
grep -c "ERROR" logs/main.log

# 查看最近的错误
grep "ERROR" logs/main.log | tail -10

# 按时间过滤日志
grep "2026-03-07 14:" logs/main.log

# 统计每个交易对的数据量
grep "已保存" logs/orderbook_spot.log | awk '{print $3}' | sort | uniq -c
```

## 资源限制

如果需要限制资源使用，可以使用 `ulimit`:

```bash
# 限制内存（2GB）
ulimit -v 2097152

# 限制CPU时间
ulimit -t unlimited

# 限制文件大小
ulimit -f unlimited

# 启动采集器
python3 main.py
```

或使用 `systemd` 的资源限制（推荐）。
