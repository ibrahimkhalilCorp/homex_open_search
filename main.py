from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging, time
from app.settings.opensearch_client import get_opensearch_client
from app.service.optimized_search_service import hybrid_search
from app.service.redis_cache_service import get_cache_service
from app.config.config import Config
from app.settings.schemas import LoginRequest, SearchRequest, RegistrationRequest, RoleUpdateRequest
from app.auth.auth import require_role
from app.auth.registration import user_registration, update_user_role, verify_user_and_generate_token
from app.auth.dependencies import success

# Logger
logging.basicConfig(level=logging.INFO)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)


app = FastAPI(
    title="Property Data API - MVP Edition",
    description="Scalable property search API with multi-layer caching for 500+ users",
    version="1.0.0"
)


# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    logging.info(f"{request.method} {request.url.path} {time.time()-start}")
    return response

@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = "max-age=63072000"
    return response


@app.get("/")
async def read_root():
    """Root endpoint with API overview"""
    cache_service = get_cache_service()
    # cache_health = cache_service.health_check()

    return {
        "message": "Property Data API - Enterprise Edition",
        "version": "1.0.0",
        "scalability": "Optimized for 500+ concurrent users",
        # "cache_status": cache_health['status'],
        # "features": [
        #     "=> Multi-layer Redis caching (5ms response)",
        #     "=> Semantic + keyword hybrid search",
        #     "=> Embedding cache (saves 100ms per query)",
        #     "=> Query result cache (instant repeat queries)",
        #     "=> Filter cache (2ms parse time)",
        #     "=> Smart rate limiting",
        #     "=> Cache warming for popular queries",
        #     "=> Auto-index management"
        # ],
        # "performance": {
        #     "cached_query": "~5ms",
        #     "cached_embedding": "~150ms",
        #     "cold_query": "~280ms"
        # },
        "endpoints": {
            "POST /api/search": "Hybrid search with multi-layer caching",
            "POST /registration": "User Registration",
            "POST /login": "User Login",
            "POST /generate_access_token": "Generate access token",
            "POST /admin/update-role": "Update user role",
            # "POST /api/data-load": "Load and index properties",
            # "GET /api/cache/stats": "Comprehensive cache statistics",
            # "POST /api/cache/clear": "Clear cache (all/queries/embeddings)",
            # "POST /api/cache/warm": "Warm cache with popular queries",
            # "GET /health": "System health check",
            # "GET /docs": "Swagger documentation"
        }
    }

@app.post("/generate_access_token")
@limiter.limit("5/minute")
async def generate_access_token(request: Request, payload: LoginRequest):
    token = await verify_user_and_generate_token(payload.email, payload.password)
    return success({"access_token": token})


@app.post("/login")
@limiter.limit("5/minute")
async def login(request: Request,form_data: OAuth2PasswordRequestForm = Depends()):
    token = await verify_user_and_generate_token(form_data.username, form_data.password)
    return {
        "access_token": token,
        "token_type": "bearer"
    }

@app.post("/registration")
@limiter.limit("5/minute")
async def registration(request: Request, payload: RegistrationRequest):
    result = await user_registration(payload)
    return success({"result": result})

@app.put("/admin/update-role")
@limiter.limit("5/minute")
async def update_role(payload: RoleUpdateRequest, user=Depends(require_role("admin"))):
    result = await update_user_role(payload)
    return {"message": result}

@app.post("/api/search")
@limiter.limit(f"{Config.RATE_LIMIT_PER_MINUTE}/minute")
async def search_properties(request: Request, search_request: SearchRequest, user=Depends(require_role("admin"))):
    """
    Enterprise hybrid search with multi-layer caching

    Cache Layers:
    1. Query result cache (5ms) - Full results
    2. Filter cache (2ms) - Parsed filters
    3. Embedding cache (instant) - Query vectors

    Performance:
    - Fully cached: ~5ms
    - Partial cache: ~150ms
    - Cold query: ~280ms
    """
    try:
        client = get_opensearch_client()
        if not client.indices.exists(index=Config.INDEX_NAME):
            raise HTTPException(
                status_code=404,
                detail=f"Index '{Config.INDEX_NAME}' does not exist. Load properties first."
            )

        # Execute search with multi-layer caching
        start = time.time()
        results = hybrid_search(
            user_query=search_request.query,
            page=search_request.page,
            size=search_request.size,
            use_cache=search_request.use_cache
        )

        if not results:
            raise HTTPException(status_code=500, detail="Search failed")

        performance = results.pop('performance', {})

        properties = []
        for hit in results['hits']['hits']:
            source = hit['_source']
            prop_details = source.get('property_details', {})

            # Extract assessed value
            assessed_value = None
            tax_year = None
            tax_assessments = prop_details.get('taxAssessment', [])
            if tax_assessments and len(tax_assessments) > 0:
                assessment = tax_assessments[0].get('assessedValue', {})
                assessed_value = assessment.get('calculatedTotalValue')
                tax_year = assessment.get('taxAssessedYear')

            properties.append({
                'clip': source.get('clip'),
                'address': source.get('propertyAddress'),
                'description': source.get('description', ''),
                'score': hit.get('_score'),
                'details': {
                    'bedrooms': prop_details.get('allBuildingsSummary', {}).get('bedroomsCount'),
                    'bathrooms': prop_details.get('allBuildingsSummary', {}).get('bathroomsCount'),
                    'livingAreaSqFt': prop_details.get('allBuildingsSummary', {}).get('livingAreaSquareFeet'),
                    'totalAreaSqFt': prop_details.get('allBuildingsSummary', {}).get('totalAreaSquareFeet')
                },
                'assessedValue': {
                    'total': assessed_value,
                    'year': tax_year
                }
            })

        return {
            "query": search_request.query,
            "total": results['hits']['total']['value'],
            "page": search_request.page,
            "size": search_request.size,
            "properties": properties,
            "performance": performance
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        workers=4  # Multiple workers for production
    )