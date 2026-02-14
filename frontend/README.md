"""
Streamlit Frontend for News Central
Complete Setup and Usage Guide
"""

# News Central - Streamlit Frontend

A modern, secure Streamlit application for the News Central API with personalized recommendations powered by reinforcement learning.

## Features

### Pages
1. **Landing Page** - Introduction and platform overview
2. **Login/Register** - Secure authentication with JWT
3. **News Feed** - Personalized feed with infinite scroll
4. **Article View** - Full article with summaries
5. **Preferences** - Topic selection and feed customization
6. **Profile** - User management and reading analytics

### Security Features
- JWT token authentication
- Secure session management
- XSS prevention (input sanitization)
- CSRF protection (enabled in Streamlit)
- Secure API calls with authorization headers
- Password strength validation
- Email validation

### UI Features
- Responsive design
- Infinite scroll news feed
- Article cards with summaries
- Like/Dislike feedback buttons
- Topic filtering
- Search functionality
- Reading time tracking
- Visualizations (Plotly)
- Custom CSS styling
- Toast notifications

## Project Structure

```
frontend/
- Home.py                     # Landing page (main entry)
- frontend_config.py          # Configuration management
- requirements.txt            # Python dependencies
- Dockerfile                  # Docker configuration
- .env.example                # Environment template
- .streamlit/
  - config.toml                # Streamlit settings
- pages/                      # Multi-page app
  - 02_Login.py               # Authentication page
  - 03_News_Feed.py           # Main news feed
  - 04_Article_View.py        # Article detail view
  - 05_Preferences.py         # User preferences
  - 06_Profile.py             # Profile management
- services/
  - api_service.py            # API client layer
- utils/
  - auth.py                   # Authentication utilities
  - ui_helpers.py             # UI helper functions
```

## Installation

### 1. Prerequisites
- Python 3.12+
- Backend API running on `http://localhost:8000`

### 2. Setup

```bash
# Navigate to frontend directory
cd frontend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
```

### 3. Configure Environment

Edit `.env` file:

```env
API_BASE_URL=http://localhost:8000
API_VERSION=v1
SECRET_KEY=your-secret-key-for-streamlit-session
DEBUG=false
```

## Running the Application

### Development Mode

```bash
streamlit run Home.py
```

The app will open at: `http://localhost:8501`

### Production Mode

```bash
streamlit run Home.py --server.port=8501 --server.address=0.0.0.0
```

### Using Docker

```bash
# Build image
docker build -t news-frontend .

# Run container
docker run -d \
  --name news-frontend \
  -p 8501:8501 \
  --env-file .env \
  news-frontend
```

## Security Implementation

### 1. JWT Authentication
```python
# Tokens stored in session_state (server-side)
st.session_state.access_token = "..."
st.session_state.refresh_token = "..."

# Automatically included in API calls
headers["Authorization"] = f"Bearer {token}"
```

### 2. Input Validation
```python
# Email validation
def validate_email(email: str) -> bool:
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

# Password strength check
def validate_password(password: str) -> tuple[bool, str]:
    # Min 8 chars, uppercase, lowercase, number, special char
    ...
```

### 3. XSS Prevention
```python
# Streamlit automatically escapes user input
# Additional sanitization in display
st.markdown(user_input)  # Safe by default
```

### 4. CSRF Protection
```toml
# .streamlit/config.toml
[server]
enableXsrfProtection = true
```

## Page Details

### Landing Page (Home.py)
- Platform introduction
- Feature highlights
- Quick navigation
- Statistics dashboard

### Login/Register (02_Login.py)
- Dual tabs for login and registration
- Real-time password validation
- Email format validation
- Username validation
- Secure credential handling

### News Feed (03_News_Feed.py)
- Three feed types:
  - Personalized (RL recommendations)
  - Latest (all sources)
  - Search (keyword-based)
- Topic filtering
- Infinite scroll
- Like/dislike feedback
- Article cards with metadata

### Article View (04_Article_View.py)
- Full article display
- Summary generation
- Reading time tracking
- Feedback submission
- Related articles
- Source attribution

### Preferences (05_Preferences.py)
- Topic selection (by category)
- Learned interests visualization
- Exploration vs personalization slider
- Display settings
- Privacy controls

### Profile (06_Profile.py)
- Personal information management
- Reading history
- Analytics dashboard
- Account security
- Session management
- Account deletion

## Customization

### Custom CSS Styling

The app includes custom CSS in `utils/ui_helpers.py`:

```python
def apply_custom_css():
    st.markdown("""
    <style>
    .main { padding: 2rem; }
    .stButton > button { border-radius: 5px; }
    /* ... more styles ... */
    </style>
    """, unsafe_allow_html=True)
```

### Theme Configuration

Edit `.streamlit/config.toml`:

```toml
[theme]
primaryColor = "#667eea"      # Change primary color
backgroundColor = "#ffffff"   # Background
textColor = "#262730"         # Text color
```

## API Service Layer

The `api_service.py` provides a clean interface to the backend:

```python
from services.api_service import api_service

# Authentication
result = api_service.login(email, password)
result = api_service.register(email, password, username, full_name)
result = api_service.logout()

# News
result = api_service.get_latest_news(page=1, limit=10)
result = api_service.search_news(query="science", page=1)
result = api_service.get_article(article_id)

# Recommendations
result = api_service.get_recommendations(limit=10)
result = api_service.submit_feedback(article_id, "positive", time_spent_seconds=120)

# User
result = api_service.get_profile()
result = api_service.update_profile(data)
result = api_service.get_preferences()
```

All methods return:
```python
{
    "success": True/False,
    "data": {...} or None,
    "error": "message" or None
}
```

## Testing

### Manual Testing
1. Start backend API: `python main.py`
2. Start frontend: `streamlit run Home.py`
3. Register new user
4. Browse news feed
5. Read articles and provide feedback
6. Check preferences update

### Test User Flow
```
1. Visit landing page
2. Click "Register"
3. Fill registration form
4. Login with credentials
5. Explore personalized feed
6. Click article to read
7. Submit feedback (like/dislike)
8. Check preferences page
9. View profile and analytics
10. Logout
```

## Features Showcase

### Infinite Scroll
```python
# Load more button in feed
if st.button("Load More"):
    st.session_state.feed_page += 1
    # Load more articles...
    st.rerun()
```

### Real-time Feedback
```python
# Immediate feedback submission
if st.button("Like"):
    result = api_service.submit_feedback(article_id, "positive")
    if result["success"]:
        show_toast("Feedback submitted!")
```

### Reading Time Tracking
```python
# Track time on article page
start_time = time.time()
# ... user reads article ...
reading_time = int(time.time() - start_time)
api_service.submit_feedback(article_id, "neutral", time_spent_seconds=reading_time)
```

## Troubleshooting

### Connection Errors
```bash
# Check backend is running
curl http://localhost:8000/health

# Update API_BASE_URL in .env
API_BASE_URL=http://localhost:8000
```

### Authentication Issues
```bash
# Clear session state
# In Streamlit: Press 'C' to clear cache
# Or restart: Ctrl+C and run again
```

### Port Already in Use
```bash
# Use different port
streamlit run Home.py --server.port=8502
```

## Deployment

### Deploy to Streamlit Cloud

1. Push code to GitHub
2. Go to https://streamlit.io/cloud
3. Connect repository
4. Set environment variables
5. Deploy

### Deploy with Docker Compose

Add to main `docker-compose.yml`:

```yaml
frontend:
  build: ./frontend
  ports:
    - "8501:8501"
  environment:
    API_BASE_URL: http://api:8000
  depends_on:
    - api
```

## Security Best Practices

1. Never commit `.env` file
2. Use environment variables for secrets
3. Enable XSRF protection
4. Validate all user inputs
5. Use HTTPS in production
6. Implement rate limiting
7. Regular dependency updates
8. Monitor for vulnerabilities

## Performance Optimization

1. **Caching**: Use `@st.cache_data` for API calls
2. **Session State**: Minimize data stored
3. **Lazy Loading**: Load articles on demand
4. **Image Optimization**: Use compressed images
5. **API Batching**: Batch multiple requests

## Next Steps

- [ ] Add dark mode toggle
- [ ] Implement email notifications
- [ ] Add export functionality
- [ ] Create mobile app version
- [ ] Add social sharing
- [ ] Implement bookmarks
- [ ] Add comments section

## Support

- Issues: Create GitHub issue
- Documentation: Check README.md
- API Docs: http://localhost:8000/docs

---

**Built with Streamlit and Python 3.12**
