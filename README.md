# News Summarizer & Recommendation API

A comprehensive, production-ready FastAPI-based news aggregation, summarization, and personalized recommendation system with reinforcement learning capabilities.

##  Features

### Core Capabilities
- **News Aggregation**: Multi-source news collection (NewsAPI, GDELT, RSS feeds)
- **Summarization**: Extractive article summaries for quick reading
- **Personalized Recommendations**: RL-based content recommendation engine
- **User Management**: Complete authentication and authorization system
- **Analytics Dashboard**: User behavior tracking and insights
- **Background Processing**: Celery-based task queue for news fetching
- **Auto-scheduling**: Fetch news every 2 hours automatically

### Security Features
- JWT-based authentication (RS256)
- Rate limiting with Redis (dependency injection)
- CORS protection
- Security headers (HSTS, CSP, XSS protection)
- Request validation middleware
- Password strength validation (Argon2)
- Email verification (optional)
- Input sanitization and XSS prevention
- Circuit breaker pattern for API resilience

### Machine Learning & Optimization
- **Reinforcement Learning**: Contextual bandit with epsilon-greedy exploration
- **Online Learning**: Real-time model updates from user feedback
- **Gym Environment**: Custom RL environment for advanced training
- **MLflow Integration**: Experiment tracking and model registry
- **Centralized Cache Manager**: Automatic compression, batch operations
- **Database Connection Pooling**: Optimized for high performance
- **Content Deduplication**: SHA-256 hashing + Jaccard similarity

---

##  Table of Contents

1. [Architecture](#architecture)
2. [Prerequisites](#prerequisites)
3. [Quick Start](#quick-start)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Running the Application](#running-the-application)
7. [API Documentation](#api-documentation)
8. [Database Setup](#database-setup)
9. [Rate Limiting](#rate-limiting)
10. [News Aggregation](#news-aggregation)
11. [RL Service](#rl-service)
12. [Frontend Application](#frontend-application)
13. [Testing](#testing)
14. [Deployment](#deployment)
15. [Troubleshooting](#troubleshooting)

---

##  Architecture

High-level flow:
1. Client applications (web, mobile, third-party)
2. API gateway layer (FastAPI + middleware: CORS, auth, rate limiting, validation)
3. Service APIs (Auth, News, User)
4. Data layer (PostgreSQL, Redis cache, RL service)
5. External services (NewsAPI, GDELT, RSS)

---

##  Prerequisites

### Required Software
- **Python**: 3.8 or higher (tested on 3.11+)
- **PostgreSQL**: 12 or higher
- **Redis**: 6.0 or higher
- **Docker** (optional): For containerized deployment
- **Git**: For version control

### API Keys (Optional but Recommended)
- **NewsAPI**: https://newsapi.org/ (free tier available)

---

##  Quick Start

The fastest way to get started (5 minutes):

```bash
# 1. Clone and enter directory
git clone <repository-url>
cd News

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Generate RSA keys for JWT
python generate_keys.py

# 5. Setup environment
cp .env.example .env
# Edit .env with your configuration

# 6. Start Redis (required)
redis-server

# 7. Setup database
alembic upgrade head

# 8. Run the application
python main.py
```

Access the API at: http://localhost:8000/docs

---

##  Installation

### 1. Clone Repository

```bash
git clone <repository-url>
cd News
```

### 2. Create Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Generate RSA Keys for JWT

```bash
python generate_keys.py
```

This creates:
- `keys/private_key.pem` - For signing tokens (keep secret!)
- `keys/public_key.pem` - For verifying tokens

---

##  Configuration

### 1. Create Environment File

```bash
cp .env.example .env
```

### 2. Configure `.env`

```env
# Application
APP_NAME=News Summarizer API
APP_VERSION=1.0.0
ENVIRONMENT=development
DEBUG=true

# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/news_summarizer

# Redis
REDIS_URL=redis://redis:6379/0
REDIS_MAX_CONNECTIONS=50
REDIS_CACHE_TTL=900

# Security
SECRET_KEY=your-secret-key-here-minimum-32-characters
JWT_ALGORITHM=RS256
JWT_PRIVATE_KEY_PATH=keys/private_key.pem
JWT_PUBLIC_KEY_PATH=keys/public_key.pem

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:8080,http://localhost:8501

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=100

# News APIs
NEWSAPI_KEY=your_newsapi_key_here
ENABLE_NEWS_SCHEDULER=true
NEWS_FETCH_INTERVAL_HOURS=2

# Email (optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
EMAIL_VERIFICATION_REQUIRED=false
```

---

##  Running the Application

### Development Mode

#### 1. Start PostgreSQL and Redis

```bash
# Using Docker
docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=password postgres:14
docker run -d --name redis -p 6379:6379 redis:7

# Or use local installations
```

#### 2. Initialize Database

```bash
# Run migrations
alembic upgrade head

# View current version
alembic current

# View migration history
alembic history
```

#### 3. Start Application

```bash
# Method 1: Direct Python
python main.py

# Method 2: Uvicorn with hot reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Method 3: Using batch file (Windows)
run.bat
```

#### 4. Start Celery Worker (for background news fetching)

```bash
# Windows
start_celery.bat

# Linux/Mac
chmod +x start_celery.sh
./start_celery.sh
```

#### 5. Access API

- **API Documentation**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

### Production Mode

```bash
# Set environment
export ENVIRONMENT=production
export DEBUG=false

# Run with multiple workers
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

# Or use Docker Compose
docker-compose up -d
```

---

##  API Documentation

### Authentication Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Register new user |
| POST | `/api/v1/auth/login` | Login and get tokens |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| POST | `/api/v1/auth/logout` | Logout user |
| POST | `/api/v1/auth/verify-email` | Verify email |
| POST | `/api/v1/auth/forgot-password` | Request password reset |
| POST | `/api/v1/auth/reset-password` | Reset password |

### News Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/news/aggregate` | Aggregate news from all sources |
| GET | `/api/v1/news/latest` | Get latest cached news |
| GET | `/api/v1/news/search` | Search articles |
| POST | `/api/v1/news/fetch-now` | Manually trigger news fetch |
| GET | `/api/v1/news/scheduler/status` | Get scheduler status |
| GET | `/api/v1/articles/{article_id}` | Get article details |

### Recommendation Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/recommendations` | Get personalized recommendations |
| POST | `/api/v1/feedback` | Submit article feedback |
| GET | `/api/v1/analytics/user-stats` | Get user analytics |

### Example Requests

#### 1. Register User

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "StrongPass123!",
    "username": "john_doe",
    "full_name": "John Doe"
  }'
```

#### 2. Aggregate News

```bash
curl -X GET "http://localhost:8000/api/v1/news/aggregate?query=technology&sources=newsapi,gdelt" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### 3. Get Recommendations

```bash
curl -X GET http://localhost:8000/api/v1/recommendations \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

---

##  Database Setup

### Schema Overview

The database includes tables for:
- **users** - User accounts with UUID primary keys
- **articles** - News articles with topics and metadata
- **reading_history** - User-article interactions
- **user_feedback** - Explicit feedback (likes/dislikes)
- **user_preferences** - Topic preferences
- **rl_training_data** - RL training episodes
- **user_sessions** - Session management
- **login_attempts** - Brute force protection

### Alembic Migrations

```bash
# Create new migration (auto-generate)
alembic revision --autogenerate -m "Description of changes"

# Apply migrations (upgrade)
alembic upgrade head

# Rollback migration (downgrade)
alembic downgrade -1

# View current version
alembic current

# View migration history
alembic history --verbose
```

### Performance Indexes

The following indexes are created for optimal performance:
- User lookups by email, username, user_id
- Article lookups by article_id, published date
- Feedback queries by user and article
- Session management indexes

---

##  Rate Limiting

### How to Use Rate Limiting

Rate limiting uses **dependency injection** instead of middleware for better async compatibility.

#### Method 1: Using the Decorator (Recommended)

```python
from app.dependencies.rate_limit import rate_limit

@router.get("/news")
@rate_limit()  # Default: 100 req/min
async def get_news():
    return {"articles": [...]}
```

#### Method 2: Using Depends

```python
from fastapi import Depends
from app.dependencies.rate_limit import check_rate_limit

@router.get("/news")
async def get_news(_: None = Depends(check_rate_limit)):
    return {"articles": [...]}
```

#### Method 3: Pre-configured Presets

```python
from app.dependencies.rate_limit import RateLimitPresets

# Strict (10 req/min) - for expensive operations
@router.post("/summarize")
async def summarize(_: None = Depends(RateLimitPresets.strict)):
    return expensive_operation()

# Lenient (200 req/min) - for lightweight operations
@router.get("/health")
async def health(_: None = Depends(RateLimitPresets.lenient)):
    return {"status": "ok"}
```

### Rate Limit Features

- **Per-user limits**: Tracks by JWT token or IP
- **Exponential backoff**: Penalties for violations
- **Automatic ban**: Temporary bans after 5 violations
- **Dynamic limits**: Reduces from 100  50  25  12
- **Rate limit headers**: X-RateLimit-* headers in responses

---

##  News Aggregation

### Features

- **Multi-source aggregation**: NewsAPI, GDELT, RSS feeds
- **Automatic scheduling**: Fetch every 2 hours
- **Circuit breaker**: Prevents cascading failures
- **Content deduplication**: SHA-256 + Jaccard similarity (80% threshold)
- **XSS prevention**: HTML sanitization
- **Redis caching**: 15-minute TTL
- **Database persistence**: Permanent storage

### Supported Sources

1. **NewsAPI** - 70,000+ sources, requires API key
2. **GDELT** - Global news database, no API key required
3. **RSS Feeds** - Custom feeds from any source

### Manual News Fetch

```bash
# Trigger immediate fetch via API
curl -X POST http://localhost:8000/api/v1/news/fetch-now \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Configuration

```env
ENABLE_NEWS_SCHEDULER=true
NEWS_FETCH_INTERVAL_HOURS=2
NEWS_SOURCES=newsapi,gdelt
NEWS_FETCH_QUERIES=technology,AI,business,science
ENABLE_RSS_FEEDS=true
RSS_FEED_URLS=https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml
```

---

##  RL Service

### Overview

The RL service provides personalized news recommendations using a **contextual bandit** approach:

- **Epsilon-greedy exploration** (default: 10%)
- **Online learning** from user feedback
- **Multi-signal rewards** (clicks, time spent, feedback, diversity)
- **No pre-training required** - learns incrementally

### Configuration

```python
# In config.py or .env
RL_EPSILON=0.1           # 10% exploration
RL_LEARNING_RATE=0.01    # Slow, stable learning
```

### Advanced: MLOps Pipeline

For production ML workflows:

```bash
# Train model with PPO
python scripts/train_rl_model.py \
    --config configs/training_config.json \
    --output models/trained

# Evaluate model
python scripts/evaluate_model.py \
    --model-path models/trained/final_model \
    --n-episodes 100

# Deploy with gradual rollout
python scripts/gradual_rollout.py \
    --version v1.0.0 \
    --traffic-pct 10
```

**MLOps Stack:**
- **MLflow**: Experiment tracking
- **Prometheus**: Metrics collection
- **Grafana**: Monitoring dashboards

---

##  Frontend Application

A Streamlit-based web interface is available in the `frontend/` directory.

### Features

- Landing page with platform overview
- User authentication (login/register)
- Personalized news feed with infinite scroll
- Article view with AI summaries
- User preferences and profile management
- Reading analytics dashboard

### Running the Frontend

```bash
cd frontend
pip install -r requirements.txt
streamlit run Home.py
```

Access at: http://localhost:8501

---

##  Testing

### Run Unit Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/test_auth.py

# With coverage
pytest --cov=app --cov-report=html

# View coverage report
# Open htmlcov/index.html
```

### Run Integration Tests

```bash
# RL service
python test_rl_service.py

# News aggregator
python test_news_service.py

```

### Manual Testing

Use the Swagger UI at http://localhost:8000/docs for interactive testing.

---

##  Deployment

### Docker Deployment (Recommended)

#### 1. Build and Run with Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop services
docker-compose down
```

#### 2. Individual Container

```bash
# Build image
docker build -t news-api .

# Run container
docker run -d \
  --name news-api \
  -p 8000:8000 \
  --env-file .env \
  news-api
```

### Production Checklist

- [ ] Set `ENVIRONMENT=production`
- [ ] Set `DEBUG=false`
- [ ] Use strong `SECRET_KEY` (32+ chars)
- [ ] Generate RSA keys on server (don't copy from dev)
- [ ] Configure proper CORS origins (only your domain)
- [ ] Set up SSL/TLS certificates (HTTPS)
- [ ] Enable rate limiting
- [ ] Configure database backups
- [ ] Set up monitoring (Prometheus, Grafana)
- [ ] Review security headers
- [ ] Set strong database password
- [ ] Configure Redis password
- [ ] Disable API docs in production (automatic when DEBUG=false)

### Environment-Specific Settings

```bash
# Development
ENVIRONMENT=development
DEBUG=true
RATE_LIMIT_PER_MINUTE=1000  # Relaxed

# Production
ENVIRONMENT=production
DEBUG=false
RATE_LIMIT_PER_MINUTE=60    # Strict
```

---

##  Project Structure

```
News/
- app/
  - api/
    - auth.py
    - news.py
    - recommendations.py
    - rl_serving.py
    - ...
  - core/
    - database.py
    - cache.py
    - jwt.py
    - security.py
    - ...
  - middleware/
    - authentication.py
    - cors.py
    - security_headers.py
    - request_validation.py
  - dependencies/
    - rate_limit.py
  - models/
    - user.py
    - article.py
    - feedback.py
  - schemas/
  - services/
    - auth_service.py
    - news_aggregator.py
    - rl_service.py
    - rl_training.py
    - ...
  - tasks/
    - news_tasks.py
  - utils/
    - date_parser.py
    - pagination.py
    - benchmark.py
- alembic/
- frontend/
- scripts/
- tests/
- monitoring/
- config.py
- main.py
- docker-compose.yml
- Dockerfile
- README.md
```

---

##  Troubleshooting

### Common Issues

**1. Database Connection Error**
```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Test connection
psql -h localhost -U postgres -d news_summarizer
```

**2. Redis Connection Error**
```bash
# Check Redis is running
redis-cli ping
# Should return: PONG

# Start Redis if not running
redis-server
```

**3. JWT Token Errors**
```bash
# Regenerate keys
python generate_keys.py

# Ensure keys are in the correct location
ls keys/
```

**4. Import Errors**
```bash
# Reinstall dependencies
pip install -r requirements.txt

# Check Python version
python --version  # Should be 3.8+
```

**5. Rate Limiting Not Working**
```bash
# Ensure Redis is connected
# Check logs for "Redis connection failed"

# Temporarily disable for debugging
# In .env: RATE_LIMIT_ENABLED=false
```

**6. Celery Worker Not Starting**
```bash
# Check Redis connection
redis-cli ping

# Check for port conflicts
netstat -an | findstr 6379

# View Celery logs
celery -A app.celery_config:celery_app worker --loglevel=debug
```

**7. Alembic Migration Errors**
```bash
# Check current version
alembic current

# If out of sync, stamp current version
alembic stamp head

# Then try upgrade again
alembic upgrade head
```

---

##  Performance Optimization

### Database
-  Connection pooling configured (pool_size: 20, max_overflow: 30)
-  Performance indexes on frequently queried columns
-  Batch operations for bulk inserts
-  Query monitoring available (`app/utils/db_monitoring.py`)

### Caching
-  Centralized cache manager with compression
-  Automatic compression for payloads > 1KB (70-80% memory reduction)
-  Batch operations (5-10x faster)
-  Pattern-based invalidation

### API
-  Async operations throughout
-  Response caching for expensive operations
-  Circuit breaker pattern for external APIs
-  Request timeout protection

---

##  Security Best Practices

1. **Never commit secrets** - Use `.env` file (gitignored)
2. **Rotate JWT keys** - Regenerate periodically in production
3. **Use HTTPS in production** - SSL/TLS required
4. **Enable rate limiting** - Prevent abuse and DDoS
5. **Validate all inputs** - Pydantic schemas enforce validation
6. **Sanitize user content** - XSS prevention implemented
7. **Use strong passwords** - Argon2 hashing + strength validation
8. **Monitor logs** - Check for suspicious activity
9. **Keep dependencies updated** - Run `pip list --outdated`
10. **Use security headers** - HSTS, CSP, X-Frame-Options enabled

---

##  Monitoring & Metrics

### Health Endpoints

- `/health` - Basic health check
- `/api/v1/status` - Detailed service status
- `/api/v1/news/scheduler/status` - Celery scheduler status

### Prometheus Metrics (Optional)

Start monitoring stack:
```bash
docker-compose --profile with-monitoring up -d
```

Access:
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)

---

##  License

[Your License Here]

---

##  Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

---

##  Acknowledgments

- FastAPI framework for modern API development
- NewsAPI and GDELT for news data
- Stable-Baselines3 for RL utilities
- PostgreSQL, Redis, and Celery teams

---

**Built with  using FastAPI, PostgreSQL, Redis, and Reinforcement Learning**

**Version:** 1.0.0 | **Last Updated:** October 23, 2025



