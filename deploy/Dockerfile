# Gink login server (send-otp / verify-otp / health).
# Build from the PROJECT ROOT:  docker build -f deploy/Dockerfile -t gink-server .
FROM python:3.11-slim
WORKDIR /srv
COPY deploy/requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt
# backend_server.py (+ billing_catalog.py) run on their own, without the rest of the app.
COPY src/ginkassistant/services/backend_server.py ./backend_server.py
# billing: country detection, prices and payment methods (imported by backend_server.py)
COPY src/ginkassistant/services/billing_catalog.py ./billing_catalog.py
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend_server:app --host 0.0.0.0 --port ${PORT}"]
