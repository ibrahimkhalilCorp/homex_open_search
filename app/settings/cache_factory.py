"""
Cache Factory - Automatically uses Redis if available, otherwise uses in-memory mock
Place this file as: app/cache_factory.py
"""
import redis
from app.config.config import Config
from app.service.redis_cache_service import get_cache_service as get_redis_cache
from app.service.mock_cache_service import get_cache_service as get_mock_cache

def get_cache_service():
    """
    Get appropriate cache service based on Redis availability

    Returns:
        RedisCacheService if Redis is available
        MockCacheService if Redis is not available
    """
    try:
        # Try to connect to Redis
        test_client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            password=Config.REDIS_PASSWORD,
            socket_connect_timeout=2
        )
        test_client.ping()

        # Redis is available - use real Redis cache
        print(f"✅ Redis available at {Config.REDIS_HOST}:{Config.REDIS_PORT}")

        return get_redis_cache()

    except (redis.ConnectionError, redis.TimeoutError, Exception) as e:
        # Redis not available - use mock cache
        print(f"⚠️  Redis not available: {e}")
        print(f"📦 Using in-memory cache (for local testing)")

        return get_mock_cache()