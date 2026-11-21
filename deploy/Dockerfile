# Gink server: sign-in, AI, sync, payments, images, voices -- and Gink on the web at /app.
# Build from the PROJECT ROOT:  docker build -f deploy/Dockerfile -t gink-server .
FROM python:3.12-slim
WORKDIR /srv
COPY deploy/requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt
# the server runs as this unprivileged user, never as root (deploy/start.py hands it the data disk first)
RUN useradd --system --uid 10001 --user-group --home-dir /srv --shell /usr/sbin/nologin gink
# backend_server.py (+ billing_catalog.py) run on their own, without the rest of the app.
COPY src/ginkassistant/services/backend_server.py ./backend_server.py
# billing: country detection, prices and payment methods (imported by backend_server.py)
COPY src/ginkassistant/services/billing_catalog.py ./billing_catalog.py
# Gink on the web (/app): the safe formatter and the pre-built web app (tools/build_web_app.py)
COPY src/ginkassistant/services/markdown_render.py ./markdown_render.py
COPY src/ginkassistant/services/attachments.py ./attachments.py
# real-time information in answers (weather, time, currency...): backend_server._add_live_context
COPY src/ginkassistant/services/live_info.py ./live_info.py
# big files on disk or in object storage (Cloudflare R2, Backblaze B2, S3): backend_server._blob_module
COPY src/ginkassistant/services/blob_store.py ./blob_store.py
# Media Studio's looks and ideas, the same in the apps, the web app and the API
COPY src/ginkassistant/services/image_ideas.py ./image_ideas.py
# what counts as a memory worth offering, and which facts replace older ones (web app, API)
COPY src/ginkassistant/services/memory_rules.py ./memory_rules.py
# what Gink does with a photo (every client): works out what it needs, careful with health and patients
COPY src/ginkassistant/services/vision_rules.py ./vision_rules.py
# real maps (0.1.160): Gink's map style for /vmap/style.json; Gink's own links for Genie's prompt
COPY src/ginkassistant/services/map_style.py ./map_style.py
COPY src/ginkassistant/services/about_gink.py ./about_gink.py
# reading for answers (0.1.161): pasted pages, GitHub code
COPY src/ginkassistant/services/web_reader.py ./web_reader.py
COPY src/ginkassistant/services/code_reader.py ./code_reader.py
COPY src/ginkassistant/services/web_app ./web_app
# server-only libraries (0.1.161: Mermaid for diagram artifacts) -- not in the apps' packages
COPY deploy/vendor ./vendor
# starts the server as "gink" (Render mounts /var/data owned by root: this hands it over, then drops root)
COPY deploy/start.py ./start.py
RUN chown -R gink:gink /srv
ENV PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000
# Docker's own check (Render uses healthCheckPath: /health from render.yaml)
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=4)"]
CMD ["python", "start.py"]
