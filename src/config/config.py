import os
from openai import OpenAI
from opensearchpy import OpenSearch
from dotenv import load_dotenv

load_dotenv()

# Fetch username and password from environment variables
opensearch_username = os.environ.get('OPEN_SEARCH_USERNAME')
opensearch_password = os.environ.get('OPEN_SEARCH_PASSWORD')
open_api_key = os.environ.get("OPENAI_API_KEY")
deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY")


# OpenSearch client
opensearch_client = OpenSearch(
    hosts=[{'host': 'localhost', 'port': 9200}],
    http_auth=(opensearch_username, opensearch_password),
    use_ssl=True,
    verify_certs=False,
    ssl_show_warn=False
)

# OpenAI client (for embeddings)
openai_client = OpenAI(
    api_key=open_api_key
)

# DeepSeek client (for fallback AI query generation)
deepseek_client = OpenAI(
    api_key=deepseek_api_key,
    base_url="https://api.deepseek.com"
)