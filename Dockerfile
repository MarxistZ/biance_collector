FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY *.py .

# 创建数据和日志目录
RUN mkdir -p /app/data /app/logs

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV TZ=UTC

# 运行应用
CMD ["python3", "main.py"]
