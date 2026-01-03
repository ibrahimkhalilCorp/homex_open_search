import re
from typing import Dict, Optional, List
from app.config import Config
from app.opensearch_client import get_opensearch_client
from app.indexer import generate_embedding


def parse_query(user_input: str) -> Dict:
    """Parse user query for filters"""
    query = user_input.lower().strip()
    filters = {"must": [], "filter": []}

    # Bedrooms
    bedroom_match = re.search(r'(\d+)\s*(?:bed(?:room)?s?|br)', query)
    if bedroom_match:
        filters["must"].append({
            "term": {"property_details.allBuildingsSummary.bedroomsCount": int(bedroom_match.group(1))}
        })

    # Assessed value - under
    under_match = re.search(r'(?:under|below|less than)\s*\$?\s*([\d,]+)k?', query)
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

    # Cities
    cities = ['honolulu', 'san francisco', 'los angeles', 'new york']
    for city in cities:
        if city in query:
            filters["must"].append({"term": {"propertyAddress.city": city.upper()}})
            break

    # Land use
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

    return {"filters": filters}


def hybrid_search(user_query: str, page: int = 1, size: int = 20) -> Optional[Dict]:
    """Hybrid search combining semantic + keyword"""
    opensearch_client = get_opensearch_client()

    # Generate embedding
    query_vector = generate_embedding(user_query)
    if not query_vector:
        return None

    # Parse filters
    parsed = parse_query(user_query)

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
                                "k": 100
                            }
                        }
                    }
                ]
            }
        }
    }

    # Add filters
    if parsed["filters"]["must"]:
        query_body["query"]["bool"]["must"].extend(parsed["filters"]["must"])
    if parsed["filters"]["filter"]:
        query_body["query"]["bool"]["filter"] = parsed["filters"]["filter"]

    try:
        response = opensearch_client.search(index=Config.INDEX_NAME, body=query_body)
        return response
    except Exception as e:
        print(f"Search failed: {e}")
        return None
