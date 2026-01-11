import re
import time
from typing import Dict, Optional, List
from app.config.config import Config
from app.settings.opensearch_client import get_opensearch_client
from app.helper.indexer import generate_embedding
from app.settings.cache_factory import get_cache_service


def parse_query_filters(user_input: str) -> Dict:
    """
    Fast rule-based parser with caching
    Extracts filters before expensive operations

    Performance: ~2ms (or instant if cached)
    """
    cache_service = get_cache_service()

    # Check filter cache first
    cached_filters = cache_service.get_parsed_filters(user_input)
    if cached_filters:
        print(f"[FILTER CACHE HIT] {user_input[:50]}")
        return cached_filters

    query = user_input.lower().strip()
    filters = {"must": [], "filter": []}
    sort_by = None

    # Extract bedrooms
    bedroom_match = re.search(r'(\d+)\s*(?:\+)?\s*(?:bed(?:room)?s?|br)', query)
    if bedroom_match:
        beds = int(bedroom_match.group(1))
        if '+' in bedroom_match.group(0):
            filters["filter"].append({
                "range": {"property_details.allBuildingsSummary.bedroomsCount": {"gte": beds}}
            })
        else:
            filters["must"].append({
                "term": {"property_details.allBuildingsSummary.bedroomsCount": beds}
            })

    # Extract bathrooms
    bathroom_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:\+)?\s*(?:bath(?:room)?s?)', query)
    if bathroom_match:
        baths = float(bathroom_match.group(1))
        if '+' in bathroom_match.group(0):
            filters["filter"].append({
                "range": {"property_details.allBuildingsSummary.bathroomsCount": {"gte": baths}}
            })
        else:
            filters["must"].append({
                "term": {"property_details.allBuildingsSummary.bathroomsCount": int(baths)}
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
    sqft_match = re.search(r'(\d+)\s*(?:\+)?\s*(?:sq\.?\s*ft|square\s*feet|sqft)', query)
    if sqft_match:
        sqft = int(sqft_match.group(1))
        if '+' in sqft_match.group(0):
            filters["filter"].append({
                "range": {"property_details.allBuildingsSummary.livingAreaSquareFeet": {"gte": sqft}}
            })

    # Extract cities - comprehensive list
    cities = [
        'honolulu', 'san francisco', 'los angeles', 'new york', 'chicago',
        'houston', 'phoenix', 'philadelphia', 'san antonio', 'san diego',
        'dallas', 'austin', 'seattle', 'denver', 'boston', 'portland',
        'miami', 'atlanta', 'las vegas', 'detroit', 'nashville', 'memphis',
        'louisville', 'baltimore', 'milwaukee', 'albuquerque', 'tucson',
        'fresno', 'sacramento', 'kansas city', 'mesa', 'virginia beach',
        'oakland', 'minneapolis', 'tulsa', 'arlington', 'tampa', 'orlando'
    ]

    for city in cities:
        if city in query:
            filters["must"].append({"term": {"propertyAddress.city": city.upper()}})
            break

    # Extract states (2-letter codes or full names)
    state_match = re.search(r'\b([A-Z]{2})\b', user_input)
    if state_match:
        filters["must"].append({"term": {"propertyAddress.state": state_match.group(1)}})

    # Extract counties
    county_match = re.search(r'(\w+)\s+county', query)
    if county_match:
        filters["must"].append({"term": {"propertyAddress.county": county_match.group(1).upper()}})

    # Land use types
    land_use_keywords = {
        'residential': 'RESIDENTIAL',
        'commercial': 'COMMERCIAL',
        'industrial': 'INDUSTRIAL',
        'agricultural': 'AGRICULTURAL',
        'vacant': 'VACANT'
    }

    for keyword, value in land_use_keywords.items():
        if keyword in query:
            filters["must"].append({
                "term": {"property_details.siteLocation.landUseAndZoningCodes.stateLandUseDescription": value}
            })
            break

    # Corporate ownership
    if any(word in query for word in ['corporate', 'company', 'corporation', 'llc', 'inc']):
        filters["filter"].append({
            "nested": {
                "path": "property_details.ownership.currentOwners.ownerNames",
                "query": {
                    "term": {"property_details.ownership.currentOwners.ownerNames.isCorporate": True}
                }
            }
        })

    # Lot size (acres)
    acres_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:\+)?\s*acres?', query)
    if acres_match:
        acres = float(acres_match.group(1))
        if '+' in acres_match.group(0):
            filters["filter"].append({
                "range": {"property_details.siteLocation.lot.areaAcres": {"gte": acres}}
            })

    # Sorting logic
    if any(word in query for word in ['cheap', 'affordable', 'lowest', 'least expensive']):
        sort_by = [{
            "property_details.taxAssessment.assessedValue.calculatedTotalValue": {
                "order": "asc",
                "nested": {"path": "property_details.taxAssessment"}
            }
        }]
    elif any(word in query for word in ['expensive', 'luxury', 'highest', 'most valuable', 'premium']):
        sort_by = [{
            "property_details.taxAssessment.assessedValue.calculatedTotalValue": {
                "order": "desc",
                "nested": {"path": "property_details.taxAssessment"}
            }
        }]
    elif any(word in query for word in ['largest', 'biggest', 'spacious']):
        sort_by = [{"property_details.allBuildingsSummary.livingAreaSquareFeet": {"order": "desc"}}]
    elif any(word in query for word in ['smallest', 'compact']):
        sort_by = [{"property_details.allBuildingsSummary.livingAreaSquareFeet": {"order": "asc"}}]

    result = {"filters": filters, "sort": sort_by}

    # Cache the parsed filters
    cache_service.set_parsed_filters(user_input, result)

    return result


def get_or_generate_embedding(text: str) -> Optional[List[float]]:
    """
    Get embedding with caching to save API calls

    Performance:
    - Cache hit: instant
    - Cache miss: ~100ms (API call)
    """
    cache_service = get_cache_service()

    # Check embedding cache
    cached_embedding = cache_service.get_embedding(text)
    if cached_embedding:
        print(f"[EMBEDDING CACHE HIT] {text[:50]}")
        return cached_embedding

    # Generate new embedding
    print(f"[GENERATING EMBEDDING] {text[:50]}")
    embedding = generate_embedding(text)

    if embedding:
        # Cache for future use
        cache_service.set_embedding(text, embedding)

    return embedding


def search_keyword_only(parsed_filters: Dict, page: int = 1, size: int = 20) -> Optional[Dict]:
    """
    Fallback keyword-only search
    Used when embeddings fail or for simple filter queries
    """
    opensearch_client = get_opensearch_client()

    query_body = {
        "size": size,
        "from": (page - 1) * size,
        "query": {
            "bool": {}
        },
        "_source": {
            "excludes": ["description_vector"]
        }
    }

    # Add filters
    if parsed_filters.get("filters", {}).get("must"):
        query_body["query"]["bool"]["must"] = parsed_filters["filters"]["must"]
    if parsed_filters.get("filters", {}).get("filter"):
        query_body["query"]["bool"]["filter"] = parsed_filters["filters"]["filter"]

    # If no filters at all, use match_all
    if not query_body["query"]["bool"]:
        query_body["query"] = {"match_all": {}}

    if parsed_filters.get("sort"):
        query_body["sort"] = parsed_filters["sort"]

    try:
        start_time = time.time()
        response = opensearch_client.search(
            index=Config.INDEX_NAME,
            body=query_body,
            request_timeout=2
        )
        total_time = time.time() - start_time

        response['performance'] = {
            'total_time_ms': round(total_time * 1000, 2),
            'method': 'keyword_only',
            'from_cache': False
        }

        return response

    except Exception as e:
        print(f"[ERROR] Keyword search failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def hybrid_search(user_query: str, page: int = 1, size: int = 20, use_cache: bool = True) -> Optional[Dict]:
    """
    Multi-layer cached hybrid search optimized for 50k+ users

    Cache Strategy (in order):
    1. Check full query result cache (~5ms)
    2. Check filter cache (~2ms)
    3. Check embedding cache (saves ~100ms API call)
    4. Execute search only if necessary

    Performance:
    - Fully cached: ~5ms
    - Filters + embedding cached: ~150ms (only search executes)
    - Embedding cached: ~180ms (parse + search)
    - Cold (no cache): ~280ms (parse + embed + search)
    """

    start_time = time.time()
    cache_service = get_cache_service()

    # LAYER 1: Check full result cache (fastest)
    if use_cache:
        # Parse filters first for cache key
        parsed = parse_query_filters(user_query)

        cached_result = cache_service.get_query_result(user_query, page, parsed['filters'])
        if cached_result:
            print(f"[QUERY RESULT CACHE HIT] {user_query[:50]}")
            elapsed = time.time() - start_time

            # Add fresh performance metrics
            cached_result['performance'] = {
                'total_time_ms': round(elapsed * 1000, 2),
                'method': 'cached_full_result',
                'from_cache': True,
                'cache_layer': 'query_result'
            }
            return cached_result
    else:
        parsed = parse_query_filters(user_query)

    # LAYER 2: Filters already cached from above
    parse_time = time.time() - start_time

    # LAYER 3: Get embedding (cached or generate)
    embedding_start = time.time()
    query_vector = get_or_generate_embedding(user_query)
    embedding_time = time.time() - embedding_start

    if not query_vector:
        print("[WARNING] Embedding failed, using keyword-only search")
        return search_keyword_only(parsed, page, size)

    # Execute hybrid search
    opensearch_client = get_opensearch_client()
    search_start = time.time()

    # Build hybrid query using knn query (required for knn_vector fields)
    # For knn_vector fields with HNSW, we MUST use knn query syntax
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
                                "k": 100  # Number of nearest neighbors to find
                            }
                        }
                    }
                ]
            }
        },
        "_source": {
            "excludes": ["description_vector"]
        }
    }

    # Add keyword filters to the bool query
    if parsed["filters"]["must"]:
        query_body["query"]["bool"]["must"].extend(parsed["filters"]["must"])

    if parsed["filters"]["filter"]:
        query_body["query"]["bool"]["filter"] = parsed["filters"]["filter"]

    # Add sorting
    if parsed.get("sort"):
        query_body["sort"] = parsed["sort"]

    query_body["timeout"] = "1000ms"

    try:
        response = opensearch_client.search(
            index=Config.INDEX_NAME,
            body=query_body,
            request_timeout=3
        )
        search_time = time.time() - search_start
        total_time = time.time() - start_time

        # Add performance metadata
        response['performance'] = {
            'parse_time_ms': round(parse_time * 1000, 2),
            'embedding_time_ms': round(embedding_time * 1000, 2),
            'search_time_ms': round(search_time * 1000, 2),
            'total_time_ms': round(total_time * 1000, 2),
            'method': 'hybrid_semantic',
            'from_cache': False,
            'cache_layer': 'none'
        }

        # Cache the result
        if use_cache and page == 1:
            cache_service.set_query_result(user_query, page, parsed['filters'], response)

        return response

    except Exception as e:
        print(f"[ERROR] Hybrid search failed: {e}")
        import traceback
        traceback.print_exc()
        return None

