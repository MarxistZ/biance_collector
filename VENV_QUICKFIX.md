# Python venv快速修复指南

## 问题描述

在Vultr VPS上运行`sudo python3 main.py`时出现错误：
```
ModuleNotFoundError: No module named 'websocket'
```

## 问题原因

你创建了Python虚拟环境（venv）并在其中安装了依赖，但使用`sudo python3`运行时会使用系统Python，而不是venv中的Python，导致找不到已安装的模块。

## 立即解决方案

### 方案1：使用venv中的Python运行（推荐）

```bash
# 在Vultr VPS上执行
cd /opt/binance_collector

# 直接使用venv中的python（不需要激活）
/opt/binance_collector/venv/bin/python3 main.py
```

### 方案2：激活venv后运行

```bash
cd /opt/binance_collector

# 激活虚拟环境
source venv/bin/activate

# 确认使用的是venv中的python
which python3
# 应该显示: /opt/binance_collector/venv/bin/python3

# 运行程序（不需要sudo）
python3 main.py
```

## 配置systemd服务使用venv

如果你想通过systemd服务运行，需要修改service文件：

```bash
# 1. 修改service文件，让它使用venv中的Python
sudo sed -i 's|ExecStart=/usr/bin/python3|ExecStart=/opt/binance_collector/venv/bin/python3|' /opt/binance_collector/binance-collector.service

# 2. 复制到systemd目录
sudo cp /opt/binance_collector/binance-collector.service /etc/systemd/system/

# 3. 重载systemd配置
sudo systemctl daemon-reload

# 4. 启动服务
sudo systemctl start binance-collector

# 5. 检查状态
sudo systemctl status binance-collector

# 6. 查看日志
sudo journalctl -u binance-collector -f
```

## 验证修复

```bash
# 1. 验证venv中已安装websocket-client
/opt/binance_collector/venv/bin/pip3 list | grep websocket
# 应该显示: websocket-client  1.6.4

# 2. 测试导入模块
/opt/binance_collector/venv/bin/python3 -c "import websocket; print('websocket模块导入成功')"

# 3. 测试运行程序（运行30秒后按Ctrl+C停止）
/opt/binance_collector/venv/bin/python3 /opt/binance_collector/main.py

# 4. 检查数据文件是否生成
ls -lh /data/spot/BTCUSDT/$(date +%Y%m%d)/
```

## 重要提示

**不要使用 `sudo python3 main.py`！**

原因：
- `sudo`会使用系统Python（`/usr/bin/python3`）
- 系统Python无法访问venv中安装的依赖包
- 应该直接使用venv中的Python路径

**正确的运行方式：**
```bash
# 方式1：直接指定venv中的python路径
/opt/binance_collector/venv/bin/python3 main.py

# 方式2：激活venv后运行
source venv/bin/activate
python3 main.py
```

## 为什么使用venv？

- ✅ 隔离项目依赖，不污染系统Python环境
- ✅ 避免与其他Python项目的依赖冲突
- ✅ 符合Python最佳实践
- ✅ 便于管理和升级依赖版本

## 更多信息

详细的venv部署说明请参考：
- [DEPLOYMENT.md - Python虚拟环境部署说明](DEPLOYMENT.md#python虚拟环境部署说明)
- [README.md - 安装依赖](README.md#安装依赖)
