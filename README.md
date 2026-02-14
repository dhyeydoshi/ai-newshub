# News Central API

FastAPI-based news platform for multi-source ingestion, normalization, deduplication, personalization, and analytics.

## Current State (Updated)

This README reflects the current codebase and recent refactors.

- DB startup is migration-first (Alembic), not `create_all` at runtime.
- Ingestion is centralized through `NewsIngestionService`.
- Topic-aware RSS feed selection is supported.
- Article text is normalized to plain text (HTML tags stripped).
- Celery worker health warning is emitted at app startup when zero workers are active.
- Frontend + backend logout flows are implemented (`/auth/logout`, `/auth/logout-all`).
- Integration pull endpoints enforce API key scope (`feed:read`) and strict `sort` validation (`date|relevance`).
- Webhook delivery security hardening is active:
  - Telegram chat id + bot token format validation
  - HTML-escaped email rendering for article fields
  - Redacted external HTTP errors persisted to delivery jobs
- Webhook planner uses Redis lock to prevent duplicate batch planning runs.
- Webhook test endpoint has dedicated throttling.

## Core Features

- Multi-source ingestion: NewsAPI, GDELT, RSS
- Unified normalization and persistence pipeline
- Deduplication by URL/hash + similarity
- Topic and tag persistence for articles
- Personalized feed with RL-based scoring and fallback scoring
- Celery tasks for scheduled and manual fetches
- Redis-backed caching and rate limiting
- JWT auth (RS256), secure middleware stack

## High-Level Architecture

1. FastAPI app (`main.py`) exposes API routes under `/api/v1`.
2. Middleware enforces auth, request validation, CORS, and security headers.
3. News ingestion flow:
   - fetch via `NewsAggregatorService`
   - normalize/validate via `NewsIngestionService`
   - save via `ArticlePersistenceService`
4. Celery worker/beat execute periodic ingestion tasks.
5. PostgreSQL stores users/articles/interactions.
6. Redis supports cache, task state checks, and rate-limiting primitives.

## Requirements

- Python 3.12 recommended
- PostgreSQL
- Redis
- Optional: Docker + Docker Compose

## Quick Start

```bash
# 1) Clone
git clone <repo-url>
cd News

# 2) Create venv
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 3) Install deps
pip install -r requirements.txt

# 4) Generate JWT keys
python generate_keys.py

# 5) Configure env
copy .env.example .env  # Windows
# cp .env.example .env  # Linux/Mac

# 6) Run migrations
alembic upgrade head

# 7) Start API
python main.py
```

## Environment Configuration

Use `.env` for runtime settings.

Important: current backend DB config is built from `DB_*` values in `config.py`.

```env
ENVIRONMENT=development
DEBUG=false

DB_USER=postgres
DB_PASSWORD=password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=news_summarizer

REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

SECRET_KEY=<min-32-chars>
JWT_ALGORITHM=RS256
JWT_PRIVATE_KEY_PATH=keys/private_key.pem
JWT_PUBLIC_KEY_PATH=keys/public_key.pem

CORS_ORIGINS=http://localhost:8501,http://localhost:8000

NEWSAPI_KEY=
ENABLE_RSS_FEEDS=true

ENABLE_INTEGRATION_API=true
ENABLE_INTEGRATION_DELIVERY=true
INTEGRATION_KEY_HEADER=X-Integration-Key
INTEGRATION_ENCRYPTION_KEY_CURRENT=<fernet-key>
INTEGRATION_WEBHOOK_TEST_RATE_LIMIT_PER_HOUR=30
```

## Database and Migrations

Schema management is Alembic-driven.

```bash
alembic current
alembic history
alembic upgrade head
```

Startup behavior:

- app checks DB connectivity
- app checks for `alembic_version` table
- app does not auto-create tables

## Running Services

### API

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Celery

Windows note: `-B/--beat` is not supported on worker command.

Run worker and beat separately:

```bash
# Worker
celery -A app.celery_config:celery_app worker --loglevel=info

# Beat (separate terminal)
celery -A app.celery_config:celery_app beat --loglevel=info
```

Or use project scripts:

- `start_celery.bat`
- `start_celery.sh`

## Phase 5 Validation

Run end-to-end integration validation (auth, integration key/feed/bundle/webhook, optional Celery checks):

```bash
python scripts/validate_phase5_e2e.py --base-url http://localhost:8000
```

Useful options:

- `--no-run-celery-checks` to skip Celery inspect checks
- `--no-cleanup` to keep created resources for manual inspection
- `--email <existing-email> --password <password>` to reuse an existing user

Integration delivery operations:

- Celery beat schedules:
  - `plan_webhook_batches` every 5 minutes (when integration delivery enabled)
  - `flush_api_key_usage` every 10 minutes (when integration API enabled)
  - `cleanup_integration_delivery_history` daily at 04:30 UTC (when integration API enabled)

## Integration Security Notes

- Public integration endpoints require:
  - valid integration key
  - required scope (`feed:read`)
  - per-key rate limit
- Query validation:
  - `sort` supports only `date` or `relevance`
- Webhook validation:
  - Telegram target must be a valid chat id / channel username
  - Telegram bot token must match expected token format
  - URL targets are HTTPS-only and blocked for private/local networks
- Delivery safety:
  - Planner acquires distributed Redis lock before scheduling
  - External webhook error payloads are redacted before persistence
  - Webhook test endpoint is rate-limited separately from management APIs

## News Ingestion Pipeline

Primary orchestration: `app/services/news_ingestion_service.py`

Pipeline stages:

1. Resolve sources and topic hints
2. Resolve RSS feeds from `RSS_TOPIC_FEED_URLS`
3. Fetch from source adapters
4. Normalize and sanitize text fields
5. Validate required fields
6. Drop invalid/duplicate items
7. Persist accepted records

Returned pipeline stats include:

- `input_count`
- `accepted_count`
- `dropped_invalid`
- `dropped_duplicates`

## RSS Topic Mapping

`config.py` supports topic feed routing via:

- `RSS_TOPIC_FEED_URLS`
- `get_rss_feed_urls_for_topics(topics)`
- `get_all_rss_feed_urls()`

When topics are provided from UI/API, ingestion uses mapped RSS feeds and persists normalized topics to DB.

## API Endpoints (Current)

### Public endpoints

- `GET /`
- `GET /health`
- Auth flows:
  - `POST /api/v1/auth/register`
  - `POST /api/v1/auth/login`
  - `POST /api/v1/auth/refresh`
  - `POST /api/v1/auth/logout`
  - `POST /api/v1/auth/verify-email`
  - `POST /api/v1/auth/resend-verification`
  - `POST /api/v1/auth/password-reset-request`
  - `POST /api/v1/auth/password-reset`

### Authenticated examples

- News and articles:
  - `GET /api/v1/news/articles`
  - `GET /api/v1/news/article/{article_id}`
  - `GET /api/v1/news/summary/{article_id}`
  - `GET /api/v1/news/search`
  - `GET /api/v1/news/personalized`
  - `GET /api/v1/news/trending`
  - `POST /api/v1/news/fetch-now`
  - `GET /api/v1/news/task-status/{task_id}`
  - `GET /api/v1/news/scheduler/status`
  - `GET /api/v1/news/scheduler/tasks`
  - `GET /api/v1/news/aggregate`
  - `POST /api/v1/news/rss/fetch`
  - `GET /api/v1/news/sources`
  - `GET /api/v1/news/health`
- User/profile:
  - `GET /api/v1/user/profile`
  - `PUT /api/v1/user/profile`
  - `GET /api/v1/user/preferences`
  - `PUT /api/v1/user/preferences`
  - `GET /api/v1/user/reading-history`
- Feedback/analytics/recommendations:
  - `/api/v1/feedback/*`
  - `/api/v1/analytics/*`
  - `GET /api/v1/recommendations/`
- Integration APIs:
  - Management (auth required): `/api/v1/integrations/*`
  - Pull feeds (integration key required): `/api/v1/integration/feeds/{slug}`, `/rss`, `/atom`
  - Pull bundles (integration key required): `/api/v1/integration/bundles/{slug}`, `/rss`, `/atom`

## Frontend

Streamlit app is under `frontend/`.

```bash
cd frontend
pip install -r requirements.txt
streamlit run Home.py
```

Set frontend API target with environment variables:

```env
API_BASE_URL=http://localhost:8000
API_VERSION=v1
```

For Docker Compose, set `FRONTEND_API_BASE_URL` (default is `http://api:8000`).

## RL and Training Scripts

Available scripts include:

- `scripts/train_rl_model.py`
- `scripts/evaluate_model.py`
- `scripts/export_training_data.py`
- `scripts/gradual_rollout.py`

Use these for offline training/evaluation and rollout workflows.

## Troubleshooting

### `alembic_version` warning at startup

Run:

```bash
alembic upgrade head
```

### Celery shows 0 workers in startup logs

Start worker process and ensure Redis is reachable.

### RSS not fetching expected topics

Verify topic keys in `RSS_TOPIC_FEED_URLS` and pass topic values consistently from UI/API.

### HTML tags in article text

Current ingestion sanitizes to plain text. Re-ingest older records if legacy rows still contain markup.

## Deployment Notes

For free-tier cloud deployment (OCI recommended for this architecture), run API + worker + beat + Redis + Postgres with process separation.

Do not rely on runtime schema creation; always run migrations during deploy.
