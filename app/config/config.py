import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # CoreLogic API
    ACCESS_TOKEN_URL = os.getenv("ACCESS_TOKEN_URL")
    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    COOKIE = os.getenv("COOKIE")
    DEVELOPER_EMAIL = os.getenv("DEVELOPER_EMAIL")
    PROPERTY_API_BASE_URL = "https://property.corelogicapi.com/v2"

    # OpenSearch Configuration
    OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "localhost")
    OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", "9200"))
    OPENSEARCH_USER = os.getenv("OPENSEARCH_USER", "admin")
    OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "Ibr@#25085#@")

    # OpenSearch Performance Settings
    OPENSEARCH_MAX_RETRIES = int(os.getenv("OPENSEARCH_MAX_RETRIES", "3"))
    OPENSEARCH_RETRY_ON_TIMEOUT = True
    OPENSEARCH_TIMEOUT = int(os.getenv("OPENSEARCH_TIMEOUT", "30"))

    # Redis Cache Configuration
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "200"))

    # Cache TTL Settings (seconds)
    CACHE_QUERY_RESULTS_TTL = int(os.getenv("CACHE_QUERY_RESULTS_TTL", "300"))  # 5 min
    CACHE_EMBEDDING_TTL = int(os.getenv("CACHE_EMBEDDING_TTL", "3600"))  # 1 hour
    CACHE_FILTERS_TTL = int(os.getenv("CACHE_FILTERS_TTL", "600"))  # 10 min

    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_API_EMBEDDING_MODEL = os.getenv("OPENAI_API_EMBEDDING_MODEL", "text-embedding-3-small")

    # LM Studio Configuration
    LM_STUDIO_ENDPOINT = os.getenv("LM_STUDIO_ENDPOINT", "http://172.30.160.1:1234/v1")
    LM_STUDIO_API_KEY = os.getenv("LM_STUDIO_API_KEY", "lm-studio")
    LM_STUDIO_EMBEDDING_MODEL = os.getenv("LM_STUDIO_EMBEDDING_MODEL", "text-embedding-nomic-embed-text-v1.5")

    # Index Configuration
    INDEX_NAME = "corelogic_properties_vector"
    # EMBEDDING_DIMENSION = 1536  # For OpenAI API
    EMBEDDING_DIMENSION = 768  # For LM Studio API

    # Performance & Scalability Settings
    MAX_WORKERS = int(os.getenv("MAX_WORKERS", "10"))  # For async operations
    BULK_INDEX_BATCH_SIZE = int(os.getenv("BULK_INDEX_BATCH_SIZE", "100"))
    SEARCH_MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "10000"))

    # Rate Limiting (for 50k+ users)
    RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "1000"))

    # Background Tasks
    CACHE_WARMING_ENABLED = os.getenv("CACHE_WARMING_ENABLED", "true").lower() == "true"
    CACHE_WARMING_INTERVAL = int(os.getenv("CACHE_WARMING_INTERVAL", "1800"))  # 30 min

    # Monitoring
    ENABLE_METRICS = os.getenv("ENABLE_METRICS", "true").lower() == "true"
    METRICS_PORT = int(os.getenv("METRICS_PORT", "9090"))

    # Feature Flags
    ENABLE_QUERY_CACHE = os.getenv("ENABLE_QUERY_CACHE", "true").lower() == "true"
    ENABLE_EMBEDDING_CACHE = os.getenv("ENABLE_EMBEDDING_CACHE", "true").lower() == "true"
    ENABLE_FILTER_CACHE = os.getenv("ENABLE_FILTER_CACHE", "true").lower() == "true"

    @classmethod
    def validate(cls):
        """Validate critical configuration"""
        errors = []

        # Check Redis connection
        if not cls.REDIS_HOST:
            errors.append("REDIS_HOST not configured")

        # Check OpenSearch connection
        if not cls.OPENSEARCH_HOST:
            errors.append("OPENSEARCH_HOST not configured")

        # Check embedding service
        if not cls.OPENAI_API_KEY and not cls.LM_STUDIO_ENDPOINT:
            errors.append("No embedding service configured (OpenAI or LM Studio)")

        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")

        return True