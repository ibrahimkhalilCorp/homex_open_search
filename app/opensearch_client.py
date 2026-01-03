from opensearchpy import OpenSearch
from app.config import Config

def get_opensearch_client():
    """Get OpenSearch client instance"""
    return OpenSearch(
        hosts=[{'host': Config.OPENSEARCH_HOST, 'port': Config.OPENSEARCH_PORT}],
        http_auth=(Config.OPENSEARCH_USER, Config.OPENSEARCH_PASSWORD),
        use_ssl=True,
        verify_certs=False,
        ssl_show_warn=False
    )