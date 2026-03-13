FROM node:20-slim AS frontend-build
WORKDIR /app/frontend

# Build args (Railway injects from service variables; defaults allow build to succeed)
ARG VITE_SUPABASE_URL=
ARG VITE_SUPABASE_ANON_KEY=
ARG VITE_BOT_API_SECRET=
ARG VITE_BACKEND_URL=
ARG VITE_WS_URL=
ARG VITE_ADMIN_EMAILS=

ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY \
    VITE_BOT_API_SECRET=$VITE_BOT_API_SECRET \
    VITE_BACKEND_URL=$VITE_BACKEND_URL \
    VITE_WS_URL=$VITE_WS_URL \
    VITE_ADMIN_EMAILS=$VITE_ADMIN_EMAILS

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY run.py ./
COPY core/ ./core/
COPY ai/ ./ai/
COPY api/ ./api/
COPY agent/ ./agent/
COPY billing/ ./billing/
COPY executors/ ./executors/
COPY safety/ ./safety/
COPY strategy/ ./strategy/
COPY learning/ ./learning/
COPY feeds/ ./feeds/
COPY tools/ ./tools/
COPY utils/ ./utils/
COPY workers/ ./workers/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN mkdir -p logs backups data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "run.py"]
