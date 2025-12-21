import json
import time
import re
import hashlib
from typing import Dict, Optional, Tuple, List
from src.config.config import openai_client, opensearch_client

# Cache configuration
query_cache = {}
CACHE_TTL = 300  # 5 minutes

# ============================================================================
# RULE-BASED QUERY PARSER (Fast - 2ms)
# ============================================================================

def parse_query_fast(user_input: str) -> Optional[Dict]:
    """Fast rule-based parser for extracting filters"""
    query = user_input.lower().strip()
    filters = {"must": [], "filter": []}
    sort_by = None

    # Extract bedrooms
    bedroom_match = re.search(r'(\d+)\s*(?:bed(?:room)?s?|br)', query)
    if bedroom_match:
        filters["must"].append({"term": {"details.bedrooms": int(bedroom_match.group(1))}})

    # Extract bathrooms
    bathroom_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:bath(?:room)?s?)', query)
    if bathroom_match:
        filters["must"].append({"term": {"details.totalBathrooms": float(bathroom_match.group(1))}})

    # Extract price - under/below
    under_match = re.search(r'(?:under|below|less than|max)\s*\$?\s*([\d,]+)k?', query)
    if under_match:
        price = int(under_match.group(1).replace(',', ''))
        if 'k' in under_match.group(0).lower() and price < 10000:
            price *= 1000
        filters["filter"].append({"range": {"listPrice": {"lte": price}}})

    # Extract price - over/above
    over_match = re.search(r'(?:over|above|more than|min)\s*\$?\s*([\d,]+)k?', query)
    if over_match:
        price = int(over_match.group(1).replace(',', ''))
        if 'k' in over_match.group(0).lower() and price < 10000:
            price *= 1000
        filters["filter"].append({"range": {"listPrice": {"gte": price}}})

    # Extract cities
    cities = [
        'san francisco', 'los angeles', 'new york', 'chicago', 'houston',
        'phoenix', 'philadelphia', 'san antonio', 'san diego', 'dallas',
        'austin', 'seattle', 'denver', 'boston', 'portland', 'miami',
        'atlanta', 'las vegas', 'detroit', 'nashville'
    ]

    for city in cities:
        if city in query:
            filters["must"].append({"term": {"address.city": city.title()}})
            break

    # Extract states
    state_match = re.search(r'\b([A-Z]{2})\b', user_input)
    if state_match:
        filters["must"].append({"term": {"address.state": state_match.group(1)}})

    # Property type
    if 'condo' in query:
        filters["must"].append({"term": {"property.propertyType": "Condo"}})
    elif 'townhouse' in query:
        filters["must"].append({"term": {"property.propertyType": "Townhouse"}})
    elif 'land' in query:
        filters["must"].append({"term": {"property.propertyType": "Land"}})

    # Status
    if 'sold' in query:
        filters["filter"].append({"term": {"status": "Sold"}})
    elif 'pending' in query:
        filters["filter"].append({"term": {"status": "Pending"}})
    else:
        filters["filter"].append({"term": {"status": "Active"}})

    # Sorting
    if any(word in query for word in ['cheap', 'affordable', 'lowest']):
        sort_by = [{"listPrice": {"order": "asc"}}]
    elif any(word in query for word in ['expensive', 'luxury', 'highest']):
        sort_by = [{"listPrice": {"order": "desc"}}]

    return {"filters": filters, "sort": sort_by}


# ============================================================================
# VECTOR EMBEDDING GENERATION
# ============================================================================

def generate_embedding(text: str) -> Optional[List[float]]:
    """Generate vector embedding from text"""
    try:
        response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"[ERROR] Embedding generation failed: {e}")
        return None


# ============================================================================
# HYBRID SEARCH (Semantic + Filters)
# ============================================================================

def search_hybrid(user_query: str, parsed_filters: Dict, page: int = 1, size: int = 20) -> Optional[Dict]:
    """
    Hybrid search combining:
    1. Vector semantic search (k-NN)
    2. Keyword filters (exact matches)
    """

    # Generate query embedding
    query_vector = generate_embedding(user_query)

    if query_vector is None:
        print("[WARNING] Using keyword-only search (embedding failed)")
        return search_keyword_only(parsed_filters, page, size)

    # Build hybrid query
    query_body = {
        "size": size,
        "from": (page - 1) * size,
        "_source": [
            "listingId", "listPrice", "status", "description",
            "address", "details.bedrooms", "details.totalBathrooms",
            "details.squareFeet", "media.photos"
        ],
        "query": {
            "bool": {
                "must": [
                    # Semantic search with k-NN
                    {
                        "knn": {
                            "description_vector": {
                                "vector": query_vector,
                                "k": 100  # Find top 100 nearest neighbors
                            }
                        }
                    }
                ],
                "filter": []
            }
        }
    }

    # Add keyword filters
    if parsed_filters:
        filters = parsed_filters.get("filters", {})

        # Add must conditions (bedrooms, city, type)
        if filters.get("must"):
            query_body["query"]["bool"]["must"].extend(filters["must"])

        # Add filter conditions (price, status)
        if filters.get("filter"):
            query_body["query"]["bool"]["filter"].extend(filters["filter"])

        # Add sorting
        if parsed_filters.get("sort"):
            query_body["sort"] = parsed_filters["sort"]

    # Add request cache
    # query_body["request_cache"] = True
    query_body["timeout"] = "500ms"

    try:
        response = opensearch_client.search(
            index='mls_listings_vector',
            body=query_body,
            request_timeout=2
        )
        return response
    except Exception as e:
        print(f"[ERROR] Hybrid search failed: {e}")
        return None


def search_keyword_only(parsed_filters: Dict, page: int = 1, size: int = 20) -> Optional[Dict]:
    """Fallback to keyword-only search if embeddings fail"""

    query_body = {
        "size": size,
        "from": (page - 1) * size,
        "_source": [
            "listingId", "listPrice", "status", "description",
            "address", "details.bedrooms", "details.totalBathrooms",
            "details.squareFeet", "media.photos"
        ],
        "query": {"bool": parsed_filters.get("filters", {"must": [], "filter": []})}
    }

    if parsed_filters.get("sort"):
        query_body["sort"] = parsed_filters["sort"]

    try:
        return opensearch_client.search(
            index='mls_listings_vector',
            body=query_body,
            request_timeout=1
        )
    except Exception as e:
        print(f"[ERROR] Keyword search failed: {e}")
        return None


# ============================================================================
# CACHE MANAGEMENT
# ============================================================================

def get_cache_key(query: str) -> str:
    """Generate cache key"""
    normalized = query.lower().strip()
    return hashlib.md5(normalized.encode()).hexdigest()


def clean_cache():
    """Remove expired entries"""
    current_time = time.time()
    expired = [k for k, v in query_cache.items()
               if current_time - v['cached_at'] > CACHE_TTL]
    for k in expired:
        del query_cache[k]


# ============================================================================
# RESPONSE FORMATTING
# ============================================================================

def format_properties(search_results: Dict) -> List[Dict]:
    """Format property data for response"""
    properties = []
    for hit in search_results['hits']['hits']:
        listing = hit['_source']
        properties.append({
            'id': listing.get('listingId'),
            'price': listing.get('listPrice'),
            'address': listing.get('address', {}),
            'details': {
                'bedrooms': listing.get('details', {}).get('bedrooms'),
                'bathrooms': listing.get('details', {}).get('totalBathrooms'),
                'squareFeet': listing.get('details', {}).get('squareFeet')
            },
            'photos': listing.get('media', {}).get('photos', [])[:3],
            'status': listing.get('status'),
            'description': listing.get('description', '')[:200] + '...',
            'score': hit.get('_score')  # Relevance score
        })
    return properties
