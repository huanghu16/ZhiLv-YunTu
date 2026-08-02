FROM python:3.11-slim

WORKDIR /app

# 先复制 requirements.txt 单独安装依赖
# 这样改代码时不会重新安装依赖，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p db/chroma_db data

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
