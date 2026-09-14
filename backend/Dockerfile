FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 80
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-80} --workers ${WEB_CONCURRENCY:-2} --timeout-keep-alive 30 --proxy-headers"]