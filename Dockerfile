FROM node:24-bookworm-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-tk ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --gid nogroup app

WORKDIR /app
RUN mkdir -p /app/data /app/data/uploads && chown -R 10001:nogroup /app/data
COPY requirements.txt ./
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
COPY app.py lot_export.py web_app.py web_main.py ./
COPY server ./server
COPY app_icon.png ./
COPY web ./web
COPY --from=frontend-build /frontend/dist ./frontend/dist

ENV PYTHONUNBUFFERED=1 MUASAMCONG_NO_BROWSER=1 PORT=8080 REACT_FRONTEND_ENABLED=1 ALLOW_LOCAL_STORAGE=1 AUTO_MIGRATE=1
USER 10001:65534
EXPOSE 8080
CMD ["/opt/venv/bin/python", "web_main.py"]
