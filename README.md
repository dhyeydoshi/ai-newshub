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
- Multi-provider email: `smtp`, `graph` (app-only), `graph_msa` (delegated personal mailbox).
- Email sender alias support (`SMTP_FROM_EMAIL` / Graph `from` field).
- Shared HTML email layout with app-name footer across all templates.
- SMTP delivery offloaded to thread pool (`asyncio.to_thread`).
- Public `POST /auth/contact-developer` endpoint with strict rate limiting.
- Frontend per-user HTTP sessions (no cross-user cookie leakage).
- MD3-style Streamlit theming (light + dark) with Roboto font.
- Security hardening:
  - Token verification/reset use hash-only lookup (no plaintext fallback).
  - `TRUSTED_PROXY_COUNT` for safe `X-Forwarded-For` parsing.
  - Docker Compose requires `DB_PASSWORD` and `REDIS_PASSWORD` (fail-fast).
  - Redis runs with `--requirepass`.

## Core Features

- Multi-source ingestion: NewsAPI, GDELT, RSS
- Unified normalization and persistence pipeline
- Deduplication by URL/hash + similarity
- Topic and tag persistence for articles
- Personalized feed with RL-based scoring and fallback scoring
- Celery tasks for scheduled and manual fetches
- Redis-backed caching and rate limiting
- JWT auth (RS256), secure middleware stack
- Multi-provider email delivery (SMTP, Microsoft Graph app-only, Graph MSA delegated)
- Public developer contact form with rate-limited email dispatch
- Streamlit frontend with Material Design 3 theming

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
DB_PASSWORD=<required>
DB_HOST=localhost
DB_PORT=5432
DB_NAME=news_summarizer

REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=<required-in-production>

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

# Email delivery (choose one: smtp, graph, graph_msa)
EMAIL_DELIVERY_PROVIDER=smtp
SMTP_HOST=smtp-mail.outlook.com
SMTP_PORT=587
SMTP_USER=your@email.com
SMTP_PASSWORD=<app-password>
SMTP_FROM_EMAIL=alias@domain.com          # optional sender alias
SMTP_FROM_NAME=News Central

# Graph app-only (alternative provider)
# GRAPH_TENANT_ID=
# GRAPH_CLIENT_ID=
# GRAPH_CLIENT_SECRET=
# GRAPH_SENDER_USER=

# Graph MSA delegated (alternative provider)
# GRAPH_MSA_CLIENT_ID=
# GRAPH_MSA_AUTHORITY=https://login.microsoftonline.com/consumers
# GRAPH_MSA_SCOPES=https://graph.microsoft.com/Mail.Send
# GRAPH_MSA_TOKEN_CACHE_FILE=secrets/graph_msa_token_cache.json

# Developer contact
DEVELOPER_CONTACT_EMAIL=contact@domain.com

# Proxy trust for rate limiting
TRUSTED_PROXY_COUNT=0
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

## Email Delivery

Three providers are supported via `EMAIL_DELIVERY_PROVIDER`:

| Provider | Auth model | When to use |
|---|---|---|
| `smtp` | Username + app password | Standard SMTP relay (Outlook, Gmail, etc.) |
| `graph` | Azure AD client credentials | Server-to-server with shared/service mailbox |
| `graph_msa` | MSAL device-code (delegated) | Personal Microsoft account / consumer tenant |

All providers support a sender alias via `SMTP_FROM_EMAIL`. SMTP delivery runs in a thread pool to avoid blocking the async event loop.

For `graph_msa`, bootstrap the token cache before first use:

```bash
python scripts/bootstrap_graph_msa_token.py
```

This performs an interactive device-code login and persists the refresh token to `GRAPH_MSA_TOKEN_CACHE_FILE`.

## Contact Developer

`POST /api/v1/auth/contact-developer` is a public endpoint that sends the requester's message to `DEVELOPER_CONTACT_EMAIL`. It is rate-limited to 10 requests/minute and HTML-escapes all user input.

The Streamlit sidebar exposes a "Let's connect" form (configurable via `DEVELOPER_CONTACT_*` and `DEVELOPER_*_URL` env vars) with social links and an inline contact form. If the API call fails, the UI falls back to a `mailto:` link.

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
  - `POST /api/v1/auth/logout-all`
  - `POST /api/v1/auth/verify-email`
  - `POST /api/v1/auth/resend-verification`
  - `POST /api/v1/auth/password-reset-request`
  - `POST /api/v1/auth/password-reset`
  - `POST /api/v1/auth/contact-developer`

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
  - `POST /api/v1/user/export-data`
  - `DELETE /api/v1/user/account`
  - `POST /api/v1/auth/change-password`
  - `GET /api/v1/auth/sessions`
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

### Docker Compose

Docker Compose enforces that `DB_PASSWORD` and `REDIS_PASSWORD` are set via the `?required` interpolation syntax. Create a `.env` file with at minimum:

```env
DB_PASSWORD=<strong-password>
REDIS_PASSWORD=<strong-password>
SECRET_KEY=<min-32-chars>
```

Redis runs with `--requirepass` and the password is injected into all services that connect to it. The `keys/` volume is mounted read-only.


For free-tier cloud deployment (OCI recommended for this architecture), run API + worker + beat + Redis + Postgres with process separation.

Do not rely on runtime schema creation; always run migrations during deploy.
