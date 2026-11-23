FROM python:3.11-slim

WORKDIR /app

# 依赖固定为运行期最小集合；不使用任何会向境外发送数据的 SDK
COPY requirements.txt ./
RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn>=0.27"

COPY app ./app

ENV PYTHONUNBUFFERED=1 \
    APP_ENV=prod \
    LOG_LEVEL=INFO

EXPOSE 8000

# 刻意不加 --no-access-log：验证默认访问日志是否被应用自身关闭
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
