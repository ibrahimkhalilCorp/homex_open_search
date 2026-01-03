import re
import time
import hashlib
from typing import Dict, Optional, List
from app.config import Config
from app.opensearch_client import get_opensearch_client
from app.indexer import generate_embedding

# Cache configuration
query_cache = {}
CACHE_TTL = 300  # 5 minutes


def parse_query_fast(user_input: str) -> Dict:
    """
    Fast rule-based parser for extracting filters from CoreLogic data
    This runs BEFORE embedding generation to save API calls
    """
    query = user_input.lower().strip()
    filters = {"must": [], "filter": []}
    sort_by = None

    # Extract bedrooms
    bedroom_match = re.search(r'(\d+)\s*(?:bed(?:room)?s?|br)', query)
    if bedroom_match:
        filters["must"].append({
            "term": {"property_details.allBuildingsSummary.bedroomsCount": int(bedroom_match.group(1))}
        })

    # Extract bathrooms
    bathroom_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:bath(?:room)?s?)', query)
    if bathroom_match:
        filters["must"].append({
            "term": {"property_details.allBuildingsSummary.bathroomsCount": int(float(bathroom_match.group(1)))}
        })

    # Extract assessed value - under/below
    under_match = re.search(r'(?:under|below|less than|max)\s*\$?\s*([\d,]+)k?', query)
    if under_match:
        value = int(under_match.group(1).replace(',', ''))
        if 'k' in under_match.group(0).lower() and value < 10000:
            value *= 1000
        filters["filter"].append({
            "nested": {
                "path": "property_details.taxAssessment",
                "query": {
                    "range": {
                        "property_details.taxAssessment.assessedValue.calculatedTotalValue": {"lte": value}
                    }
                }
            }
        })

    # Extract assessed value - over/above
    over_match = re.search(r'(?:over|above|more than|min)\s*\$?\s*([\d,]+)k?', query)
    if over_match:
        value = int(over_match.group(1).replace(',', ''))
        if 'k' in over_match.group(0).lower() and value < 10000:
            value *= 1000
        filters["filter"].append({
            "nested": {
                "path": "property_details.taxAssessment",
                "query": {
                    "range": {
                        "property_details.taxAssessment.assessedValue.calculatedTotalValue": {"gte": value}
                    }
                }
            }
        })

    # Extract square footage
    sqft_match = re.search(r'(\d+)\s*(?:sq\.?\s*ft|square\s*feet|sqft)', query)
    if sqft_match:
        sqft = int(sqft_match.group(1))
        filters["filter"].append({
            "range": {
                "property_details.allBuildingsSummary.livingAreaSquareFeet": {"gte": sqft}
            }
        })

    # Extract cities (expanded list)
    cities = [
        'honolulu', 'san francisco', 'los angeles', 'new york', 'chicago',
        'houston', 'phoenix', 'philadelphia', 'san antonio', 'san diego',
        'dallas', 'austin', 'seattle', 'denver', 'boston', 'portland',
        'miami', 'atlanta', 'las vegas', 'detroit', 'nashville'
    ]

    for city in cities:
        if city in query:
            filters["must"].append({"term": {"propertyAddress.city": city.upper()}})
            break

    # Extract states (2-letter codes)
    state_match = re.search(r'\b([A-Z]{2})\b', user_input)
    if state_match:
        filters["must"].append({"term": {"propertyAddress.state": state_match.group(1)}})

    # Extract counties
    county_match = re.search(r'(\w+)\s+county', query)
    if county_match:
        filters["must"].append({"term": {"propertyAddress.county": county_match.group(1).upper()}})

    # Land use type
    if 'residential' in query:
        filters["must"].append({
            "term": {"property_details.siteLocation.landUseAndZoningCodes.stateLandUseDescription": "RESIDENTIAL"}
        })
    elif 'commercial' in query:
        filters["must"].append({
            "term": {"property_details.siteLocation.landUseAndZoningCodes.stateLandUseDescription": "COMMERCIAL"}
        })
    elif 'industrial' in query:
        filters["must"].append({
            "term": {"property_details.siteLocation.landUseAndZoningCodes.stateLandUseDescription": "INDUSTRIAL"}
        })

    # Corporate ownership filter
    if 'corporate' in query or 'company' in query:
        filters["filter"].append({
            "nested": {
                "path": "property_details.ownership.currentOwners.ownerNames",
                "query": {
                    "term": {"property_details.ownership.currentOwners.ownerNames.isCorporate": True}
                }
            }
        })

    # Lot size (acres)
    acres_match = re.search(r'(\d+(?:\.\d+)?)\s*acres?', query)
    if acres_match:
        acres = float(acres_match.group(1))
        filters["filter"].append({
            "range": {"property_details.siteLocation.lot.areaAcres": {"gte": acres}}
        })

    # Sorting
    if any(word in query for word in ['cheap', 'affordable', 'lowest', 'least expensive']):
        sort_by = [{
            "property_details.taxAssessment.assessedValue.calculatedTotalValue": {
                "order": "asc",
                "nested": {"path": "property_details.taxAssessment"}
            }
        }]
    elif any(word in query for word in ['expensive', 'luxury', 'highest', 'most valuable']):
        sort_by = [{
            "property_details.taxAssessment.assessedValue.calculatedTotalValue": {
                "order": "desc",
                "nested": {"path": "property_details.taxAssessment"}
            }
        }]
    elif any(word in query for word in ['largest', 'biggest']):
        sort_by = [{"property_details.allBuildingsSummary.livingAreaSquareFeet": {"order": "desc"}}]
    elif any(word in query for word in ['smallest']):
        sort_by = [{"property_details.allBuildingsSummary.livingAreaSquareFeet": {"order": "asc"}}]

    return {"filters": filters, "sort": sort_by}


def get_cache_key(query: str, page: int) -> str:
    """Generate cache key from query and page"""
    normalized = f"{query.lower().strip()}_{page}"
    return hashlib.md5(normalized.encode()).hexdigest()


def clean_cache():
    """Remove expired cache entries"""
    current_time = time.time()
    expired = [k for k, v in query_cache.items()
               if current_time - v['cached_at'] > CACHE_TTL]
    for k in expired:
        del query_cache[k]


def hybrid_search(user_query: str, page: int = 1, size: int = 20, use_cache: bool = True) -> Optional[Dict]:
    """
    Hybrid search with caching and optimized performance

    Performance:
    - Cached: ~5ms
    - With embedding: ~250ms
    - Keyword only: ~130ms
    """

    # Check cache first (fastest path)
    if use_cache:
        cache_key = get_cache_key(user_query, page)
        if cache_key in query_cache:
            cached = query_cache[cache_key]
            print(f"[CACHE HIT] {user_query}")

            # Add performance metadata
            cached_result = cached['result'].copy()
            cached_result['performance'] = {
                'total_time_ms': round((time.time() - cached['cached_at']) * 1000, 1),
                'method': 'cached',
                'from_cache': True
            }
            return cached_result

    start_time = time.time()

    # Parse query for filters (fast - ~2ms)
    parse_start = time.time()
    parsed = parse_query_fast(user_query)
    parse_time = time.time() - parse_start

    opensearch_client = get_opensearch_client()

    # Generate embedding for semantic search
    embedding_start = time.time()
    query_vector = generate_embedding(user_query)
    embedding_time = time.time() - embedding_start

    if not query_vector:
        print("[WARNING] Embedding failed, using keyword-only search")
        return search_keyword_only(parsed, page, size)

    # Build hybrid query
    search_start = time.time()
    query_body = {
        "size": size,
        "from": (page - 1) * size,
        "query": {
            "bool": {
                "must": [
                    {
                        "knn": {
                            "description_vector": {
                                "vector": query_vector,
                                "k": 100  # Find top 100 nearest neighbors
                            }
                        }
                    }
                ]
            }
        }
    }

    # Add keyword filters
    if parsed["filters"]["must"]:
        query_body["query"]["bool"]["must"].extend(parsed["filters"]["must"])
    if parsed["filters"]["filter"]:
        query_body["query"]["bool"]["filter"] = parsed["filters"]["filter"]

    # Add sorting
    if parsed.get("sort"):
        query_body["sort"] = parsed["sort"]

    query_body["timeout"] = "500ms"

    try:
        response = opensearch_client.search(
            index=Config.INDEX_NAME,
            body=query_body,
            request_timeout=2
        )
        search_time = time.time() - search_start
        total_time = time.time() - start_time

        # Add performance metadata
        response['performance'] = {
            'parse_time_ms': round(parse_time * 1000, 1),
            'embedding_time_ms': round(embedding_time * 1000, 1),
            'search_time_ms': round(search_time * 1000, 1),
            'total_time_ms': round(total_time * 1000, 1),
            'method': 'hybrid_semantic',
            'from_cache': False
        }

        # Cache the result (only cache first page)
        if use_cache and page == 1:
            cache_key = get_cache_key(user_query, page)
            query_cache[cache_key] = {
                'result': response,
                'cached_at': time.time()
            }
            clean_cache()  # Clean expired entries

        return response

    except Exception as e:
        print(f"[ERROR] Hybrid search failed: {e}")
        return None


def search_keyword_only(parsed_filters: Dict, page: int = 1, size: int = 20) -> Optional[Dict]:
    """
    Fallback to keyword-only search if embeddings fail
    Faster but less intelligent than hybrid search
    """
    opensearch_client = get_opensearch_client()

    query_body = {
        "size": size,
        "from": (page - 1) * size,
        "query": {
            "bool": parsed_filters.get("filters", {"must": [], "filter": []})
        }
    }

    if parsed_filters.get("sort"):
        query_body["sort"] = parsed_filters["sort"]

    try:
        start_time = time.time()
        response = opensearch_client.search(
            index=Config.INDEX_NAME,
            body=query_body,
            request_timeout=1
        )
        total_time = time.time() - start_time

        # Add performance metadata
        response['performance'] = {
            'total_time_ms': round(total_time * 1000, 1),
            'method': 'keyword_only',
            'from_cache': False
        }

        return response

    except Exception as e:
        print(f"[ERROR] Keyword search failed: {e}")
        return None


def get_cache_stats() -> Dict:
    """Get cache statistics"""
    return {
        'total_entries': len(query_cache),
        'ttl_seconds': CACHE_TTL,
        'entries': [
            {
                'query': list(query_cache.keys())[i][:50] + '...',
                'age_seconds': round(time.time() - v['cached_at'], 1)
            }
            for i, v in enumerate(list(query_cache.values())[:5])
        ]
    }


def clear_cache():
    """Clear all cache entries"""
    count = len(query_cache)
    query_cache.clear()
    return count