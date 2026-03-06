# 后台运行部署指南

本文档提供多种方式在后台运行Binance数据采集器。

## Vultr VPS生产环境部署（推荐）

### 环境准备

**系统要求：**
- Ubuntu 20.04+ / Debian 11+ / CentOS 8+
- Python 3.8+
- 至少2GB内存
- `/data` 挂载点至少100GB可用空间

**1. 检查并准备数据目录**

```bash
# 检查/data挂载点
df -h /data

# 如果/data不存在，创建并挂载（示例：挂载额外磁盘）
# 假设额外磁盘为/dev/vdb
sudo mkfs.ext4 /dev/vdb
sudo mkdir -p /data
sudo mount /dev/vdb /data

# 添加到/etc/fstab实现开机自动挂载
echo "/dev/vdb /data ext4 defaults 0 0" | sudo tee -a /etc/fstab

# 设置权限
sudo chmod 755 /data
```

**2. 安装系统依赖**

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3 python3-pip git

# CentOS/RHEL
sudo yum install -y python3 python3-pip git
```

### 部署步骤

**1. 克隆代码**

```bash
cd /opt
sudo git clone <your-repo-url> binance_collector
cd binance_collector
```

**2. 安装Python依赖**

```bash
sudo pip3 install -r requirements.txt
```

**3. 设置执行权限**

```bash
sudo chmod +x /opt/binance_collector/*.sh
```

**4. 验证配置**

```bash
# 检查config.py中的DATA_DIR配置
grep DATA_DIR /opt/binance_collector/config.py
# 应该显示: DATA_DIR = "/data"

# 测试数据目录可写性
sudo touch /data/test && sudo rm /data/test && echo "OK"
```

**5. 测试运行**

```bash
cd /opt/binance_collector
sudo python3 main.py
# 等待30秒后按Ctrl+C停止

# 检查是否生成数据文件
ls -lh /data/spot/BTCUSDT/$(date +%Y%m%d)/
```

**6. 安装systemd服务**

```bash
# 复制服务文件
sudo cp /opt/binance_collector/binance-collector.service /etc/systemd/system/

# 重载systemd配置
sudo systemctl daemon-reload

# 启用开机自启动
sudo systemctl enable binance-collector

# 启动服务
sudo systemctl start binance-collector

# 检查状态
sudo systemctl status binance-collector
```

**7. 配置监控（可选但推荐）**

```bash
# 编辑root用户的crontab
sudo crontab -e

# 添加以下行
*/5 * * * * cd /opt/binance_collector && ./monitor.sh
@reboot sleep 30 && systemctl start binance-collector
```

### 验证部署

```bash
# 1. 检查服务状态
sudo systemctl status binance-collector

# 2. 查看实时日志
sudo journalctl -u binance-collector -f

# 3. 检查数据文件
ls -lh /data/spot/BTCUSDT/$(date +%Y%m%d)/
ls -lh /data/futures/BTCUSDT/$(date +%Y%m%d)/

# 4. 监控磁盘使用
df -h /data

# 5. 测试自动重启（可选）
# 强制终止进程，观察是否在10秒内自动重启
sudo kill -9 $(pgrep -f "python3.*main.py")
sleep 15
sudo systemctl status binance-collector
```

### 安全建议（root用户部署）

当使用root用户运行时，建议采取以下安全措施：

```bash
# 1. 限制文件权限
sudo chmod 700 /opt/binance_collector
sudo chmod 600 /opt/binance_collector/config.py

# 2. 配置防火墙（仅允许出站HTTPS）
sudo ufw allow out 443/tcp
sudo ufw enable

# 3. 定期更新系统
sudo apt update && sudo apt upgrade -y  # Ubuntu/Debian
```

**可选：创建专用用户（更安全）**

如果不想使用root用户，可以创建专用用户：

```bash
# 创建系统用户
sudo useradd -r -s /bin/bash -d /opt/binance_collector binance

# 设置目录权限
sudo chown -R binance:binance /opt/binance_collector
sudo chown -R binance:binance /data

# 修改systemd服务文件
sudo sed -i 's/User=root/User=binance/' /etc/systemd/system/binance-collector.service
sudo sed -i 's/Group=root/Group=binance/' /etc/systemd/system/binance-collector.service

# 重载并重启服务
sudo systemctl daemon-reload
sudo systemctl restart binance-collector
```

---

## 方法1: 使用启动脚本（推荐）

### 快速开始

```bash
# 启动采集器
./start.sh start

# 查看状态
./start.sh status

# 查看日志
./start.sh logs

# 实时跟踪日志
./start.sh logs -f

# 停止采集器
./start.sh stop

# 重启采集器
./start.sh restart
```

### 特性

- ✅ 自动检查Python环境和依赖
- ✅ PID文件管理，防止重复启动
- ✅ 优雅关闭（SIGTERM）
- ✅ 启动状态检查
- ✅ 资源使用监控
- ✅ 日志管理

### 开机自启动（crontab）

```bash
# 编辑crontab
crontab -e

# 添加以下行（根据实际安装路径调整）
@reboot cd /opt/binance_collector && ./start.sh start
```

---

## 方法2: 使用systemd服务（生产环境推荐）

### 安装服务

```bash
# 复制服务文件
sudo cp binance-collector.service /etc/systemd/system/

# 重载systemd配置
sudo systemctl daemon-reload

# 启用开机自启动
sudo systemctl enable binance-collector

# 启动服务
sudo systemctl start binance-collector
```

### 管理命令

```bash
# 查看状态
sudo systemctl status binance-collector

# 查看日志
sudo journalctl -u binance-collector -f

# 停止服务
sudo systemctl stop binance-collector

# 重启服务
sudo systemctl restart binance-collector

# 禁用开机自启动
sudo systemctl disable binance-collector
```

### 特性

- ✅ 系统级管理
- ✅ 自动重启（崩溃后10秒重启）
- ✅ 资源限制（内存2GB，文件句柄65536）
- ✅ 日志集成到systemd journal
- ✅ 开机自启动
- ✅ 安全隔离（PrivateTmp, NoNewPrivileges）

---

## 方法3: 使用Docker Compose（容器化部署）

### 前置要求

```bash
# 安装Docker和Docker Compose
sudo apt-get update
sudo apt-get install docker.io docker-compose
sudo usermod -aG docker $USER
```

### 启动容器

```bash
# 构建并启动
docker-compose up -d

# 查看状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 停止容器
docker-compose down

# 重启容器
docker-compose restart
```

### 特性

- ✅ 环境隔离
- ✅ 自动重启（unless-stopped）
- ✅ 资源限制（CPU 2核，内存2GB）
- ✅ 健康检查
- ✅ 日志轮转（100MB x 10个文件）
- ✅ 数据持久化
- ✅ 一键部署

### 更新容器

```bash
# 拉取最新代码
git pull

# 重新构建并启动
docker-compose up -d --build
```

---

## 方法4: 使用nohup（简单方式）

### 启动

```bash
# 后台运行
nohup python3 main.py > logs/nohup.log 2>&1 &

# 保存PID
echo $! > collector.pid
```

### 停止

```bash
# 读取PID并停止
kill -TERM $(cat collector.pid)

# 或强制停止
kill -9 $(cat collector.pid)
```

### 查看日志

```bash
tail -f logs/nohup.log
```

---

## 方法5: 使用screen（调试推荐）

### 启动

```bash
# 创建screen会话
screen -S binance-collector

# 在screen中运行
python3 main.py

# 按 Ctrl+A 然后按 D 分离会话
```

### 管理

```bash
# 列出所有会话
screen -ls

# 重新连接
screen -r binance-collector

# 终止会话（在会话内）
exit
```

---

## 方法6: 使用tmux（多窗口管理）

### 启动

```bash
# 创建tmux会话
tmux new -s binance-collector

# 在tmux中运行
python3 main.py

# 按 Ctrl+B 然后按 D 分离会话
```

### 管理

```bash
# 列出所有会话
tmux ls

# 重新连接
tmux attach -t binance-collector

# 终止会话
tmux kill-session -t binance-collector
```

---

## 监控和维护

### 查看进程

```bash
# 查找进程
ps aux | grep main.py

# 查看资源使用
top -p $(cat collector.pid)

# 查看网络连接
netstat -anp | grep $(cat collector.pid)
```

### 日志管理

```bash
# 查看所有日志文件
ls -lh logs/

# 查看主日志
tail -f logs/main.log

# 查看现货orderbook日志
tail -f logs/orderbook_spot.log

# 查看合约orderbook日志
tail -f logs/orderbook_futures.log

# 查看资金费率日志
tail -f logs/funding_rate.log

# 清理旧日志（保留最近7天）
find logs/ -name "*.log.*" -mtime +7 -delete
```

### 数据检查

```bash
# 查看数据目录大小
du -sh data/

# 查看今天的数据文件
find data/ -name "*.parquet" -mtime -1 -ls

# 统计数据文件数量
find data/ -name "*.parquet" | wc -l
```

### 磁盘空间监控

```bash
# 查看磁盘使用
df -h

# 监控数据目录增长
watch -n 60 'du -sh data/'
```

---

## 故障排查

### 程序无法启动

```bash
# 检查Python版本
python3 --version

# 检查依赖
pip list | grep -E "websocket|pandas|pyarrow|requests"

# 手动运行查看错误
python3 main.py

# 检查端口占用
netstat -anp | grep ESTABLISHED | grep binance
```

### 程序频繁重启

```bash
# 查看系统日志
sudo journalctl -xe

# 查看内存使用
free -h

# 查看磁盘空间
df -h

# 检查网络连接
ping -c 3 fstream.binance.com
```

### 数据未保存

```bash
# 检查磁盘空间
df -h

# 检查目录权限
ls -ld data/

# 查看错误日志
grep -i error logs/main.log
```

---

## 性能优化

### 减少交易对数量

编辑 `config.py`:

```python
SPOT_SYMBOLS = ["BTCUSDT", "ETHUSDT"]  # 只保留主要交易对
FUTURES_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
```

### 调整保存间隔

编辑 `orderbook_collector.py` 和 `funding_rate_collector.py`:

```python
self.save_interval = 300  # 改为5分钟保存一次
```

### 启用数据压缩

已默认启用Snappy压缩，无需额外配置。

---

## 安全建议

1. **限制文件权限**
   ```bash
   chmod 700 /opt/binance_collector
   chmod 600 /opt/binance_collector/config.py
   ```

2. **使用专用用户（推荐）**
   ```bash
   sudo useradd -r -s /bin/bash -d /opt/binance_collector binance
   sudo chown -R binance:binance /opt/binance_collector
   sudo chown -R binance:binance /data
   # 然后修改systemd服务文件中的User和Group
   ```

3. **配置防火墙**
   ```bash
   # 仅允许出站HTTPS连接
   sudo ufw allow out 443/tcp
   ```

4. **定期备份**
   ```bash
   # 备份数据到远程服务器或对象存储
   tar -czf backup_$(date +%Y%m%d).tar.gz /data/
   ```

---

## 推荐配置

| 场景 | 推荐方法 | 理由 |
|------|---------|------|
| 开发测试 | screen/tmux | 方便调试和查看输出 |
| 个人使用 | start.sh脚本 | 简单易用，功能完整 |
| 生产环境 | systemd服务 | 稳定可靠，系统集成 |
| 容器化部署 | Docker Compose | 环境隔离，易于迁移 |
| 临时运行 | nohup | 快速启动，无需配置 |

---

## 常见问题

**Q: 如何确认程序正在运行？**

A: 使用 `./start.sh status` 或 `ps aux | grep main.py`

**Q: 如何查看实时日志？**

A: 使用 `./start.sh logs -f` 或 `tail -f logs/main.log`

**Q: 程序崩溃后会自动重启吗？**

A: 使用systemd服务会自动重启，其他方法需要手动重启或配置crontab监控

**Q: 如何修改配置后重启？**

A: 编辑 `config.py` 后执行 `./start.sh restart`

**Q: 数据存储在哪里？**

A: 生产环境默认在 `/data/` 目录（独立挂载点），开发环境可在 `config.py` 中修改为其他路径

**Q: 如何停止程序？**

A: 使用 `./start.sh stop` 或 `kill -TERM $(cat collector.pid)`
