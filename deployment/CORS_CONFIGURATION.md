# CORS Configuration for Production

The default CORS configuration in `backend/app/main.py` allows all origins, which is fine for development but should be restricted in production.

## Current Configuration (Development)

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Recommended Production Configuration

### Option 1: Environment-Based Configuration (Recommended)

Update `backend/app/main.py` to use environment-based CORS:

```python
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="FT Strategy Backend")

# ... router includes ...

# CORS configuration based on environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

if ENVIRONMENT == "production":
    # Production: Only allow your domain
    allowed_origins = [
        "https://your-domain.com",
        "https://www.your-domain.com",
    ]
else:
    # Development: Allow all origins
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
```

Then add to `.env.production`:
```bash
ENVIRONMENT=production
```

### Option 2: Specific Origins Only

If you prefer to always specify origins:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://your-domain.com",
        "https://www.your-domain.com",
        # Add any other trusted origins
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)
```

### Option 3: No CORS Middleware (Most Secure)

Since your Nginx serves both frontend and backend on the same domain, you can remove CORS middleware entirely in production:

```python
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="FT Strategy Backend")

# ... router includes ...

# Only add CORS in development
if os.getenv("ENVIRONMENT", "development") != "production":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

## Why This Matters

1. **Security**: Restricting origins prevents unauthorized domains from making requests to your API
2. **CSRF Protection**: When combined with proper authentication, it helps prevent cross-site request forgery
3. **Data Protection**: Ensures only your frontend can access the API

## Implementation Steps

1. Choose one of the options above
2. Update `backend/app/main.py`
3. Add `ENVIRONMENT=production` to `.env.production` (if using Option 1)
4. Test locally first with `ENVIRONMENT=production`
5. Deploy to production

## Testing CORS Configuration

Test that CORS is properly configured:

```bash
# This should be rejected (different origin)
curl -H "Origin: https://evil-site.com" \
     -H "Access-Control-Request-Method: POST" \
     -H "Access-Control-Request-Headers: Content-Type" \
     -X OPTIONS \
     https://your-domain.com/api/auth/login

# This should be allowed (same origin)
curl -H "Origin: https://your-domain.com" \
     -H "Access-Control-Request-Method: POST" \
     -H "Access-Control-Request-Headers: Content-Type" \
     -X OPTIONS \
     https://your-domain.com/api/auth/login
```

## Alternative: Nginx-Level CORS

You can also handle CORS at the Nginx level instead of in the application. Add to `/etc/nginx/sites-available/ft-bot.conf`:

```nginx
location /api/ {
    # Only add CORS headers if needed
    if ($http_origin ~* (https://your-domain\.com|https://www\.your-domain\.com)) {
        add_header 'Access-Control-Allow-Origin' "$http_origin" always;
        add_header 'Access-Control-Allow-Credentials' 'true' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, PATCH, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Content-Type, Authorization' always;
    }
    
    if ($request_method = 'OPTIONS') {
        return 204;
    }
    
    proxy_pass http://ft_backend/;
    # ... rest of proxy config ...
}
```

Then remove the CORS middleware from FastAPI entirely.

## Recommendation for Your Setup

Since your Nginx serves both the React frontend and proxies to the FastAPI backend on the same domain (`https://your-domain.com`), **Option 3 (No CORS in production)** is the most secure and simplest approach.

The frontend and backend will be on the same origin, so CORS is not needed in production. Keep it only for local development when the frontend dev server (port 5173) needs to access the backend (port 8000).
