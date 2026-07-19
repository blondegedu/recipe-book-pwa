FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
COPY index.html .
COPY manifest.json .
COPY service-worker.js .
COPY icon-512.png .
COPY feature-graphic.png .
COPY assetlinks.json .
EXPOSE 8080
CMD ["python", "server.py"]
