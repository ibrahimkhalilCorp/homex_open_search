import json
import hashlib
import time
from typing import Dict, Optional, List, Any
from app.config.config import Config
import pickle


class MockCacheService:
    """In-memory cache service (no Redis required)"""

    def __init__(self):
        # In-memory cache dictionaries
        self._query_cache = {}
        self._embedding_cache = {}
        self._filter_cache = {}
        self._popular_queries = {}
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "embedding_cache_hits": 0,
            "embedding_cache_misses": 0
        }

        # Cache TTLs (seconds)
        self.QUERY_RESULTS_TTL = 300
        self.EMBEDDING_TTL = 3600
        self.FILTER_CACHE_TTL = 600
        self.POPULAR_QUERIES_TTL = 1800

        # Cache key prefixes
        self.PREFIX_QUERY = "query:"
        self.PREFIX_EMBEDDING = "embed:"
        self.PREFIX_FILTER = "filter:"
        self.PREFIX_POPULAR = "popular:"

        print("[MOCK CACHE] Using in-memory cache (Redis not required)")



# Singleton instance
_cache_service = None


def get_cache_service() -> MockCacheService:
    """Get cache service singleton"""
    global _cache_service
    if _cache_service is None:
        _cache_service = MockCacheService()
    return _cache_service