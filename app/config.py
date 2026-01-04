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

    # OpenSearch
    OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "localhost")
    OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", "9200"))
    OPENSEARCH_USER = os.getenv("OPENSEARCH_USER", "admin")
    OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "Ibr@#25085#@")

    # OpenAI
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_API_EMBEDDING_MODEL = os.getenv("OPENAI_API_EMBEDDING_MODEL", "text-embedding-3-small")

    #LM Studio
    LM_STUDIO_ENDPOINT = os.getenv("LM_STUDIO_ENDPOINT", "http://172.30.160.1:1234/v1")
    LM_STUDIO_API_KEY = os.getenv("LM_STUDIO_API_KEY", "lm-studio")
    LM_STUDIO_EMBEDDING_MODEL = os.getenv("LM_STUDIO_EMBEDDING_MODEL", "text-embedding-nomic-embed-text-v1.5")

    # Index Configuration
    INDEX_NAME = "corelogic_properties_vector"
    # EMBEDDING_DIMENSION = 1536 ## For Open AI API
    EMBEDDING_DIMENSION = 768 ## For LM Studio API