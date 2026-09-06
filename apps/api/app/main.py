from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1 import auth, users, buffer, media, campaigns, publications, settings as settings_api, ai
from app.api.v1 import blog_writer_sites, blog_writer_articles
from app.api.v1 import omnichannel, omnichannel_webhooks
from app.api.v1 import statistics
from app.api.v1 import public_stats

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend services for Buffer-integrated multi-tenant social publishing platform.",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# CORS Configuration
# In production, this must be locked down to the configured frontend origin.
# Wildcards are rejected to preserve authentication cookie/credentials transport.
origins = [
    "http://localhost:3000",
    "http://app.example.com",
    "https://app.162-55-187-18.sslip.io",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API V1 Router registration
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
app.include_router(buffer.router, prefix=f"{settings.API_V1_STR}/buffer", tags=["buffer"])
app.include_router(media.router, prefix=f"{settings.API_V1_STR}/media", tags=["media"])
app.include_router(campaigns.router, prefix=f"{settings.API_V1_STR}/campaigns", tags=["campaigns"])
app.include_router(publications.router, prefix=f"{settings.API_V1_STR}/publications", tags=["publications"])
app.include_router(settings_api.router, prefix=f"{settings.API_V1_STR}/settings", tags=["settings"])
app.include_router(ai.router, prefix=f"{settings.API_V1_STR}/ai", tags=["ai"])
app.include_router(blog_writer_sites.router, prefix=f"{settings.API_V1_STR}/blog-writer/sites", tags=["blog-writer"])
app.include_router(blog_writer_articles.router, prefix=f"{settings.API_V1_STR}/blog-writer/articles", tags=["blog-writer"])
app.include_router(omnichannel.router, prefix=f"{settings.API_V1_STR}/omnichannel-responder", tags=["omnichannel-responder"])
app.include_router(omnichannel_webhooks.router, prefix=f"{settings.API_V1_STR}/omnichannel-responder", tags=["omnichannel-responder"])
app.include_router(statistics.router, prefix=f"{settings.API_V1_STR}/statistics", tags=["statistics"])
app.include_router(public_stats.router, prefix=f"{settings.API_V1_STR}/public/stats", tags=["public"])

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "docs_url": "/docs"
    }
