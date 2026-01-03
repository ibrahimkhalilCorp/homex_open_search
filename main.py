from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict, Any
from app.api_client import CoreLogicAPIClient
from app.utils import save_to_json, generate_filename
from app.indexer import index_property, create_index
from app.search_service import (
    hybrid_search,
    get_cache_stats,
    clear_cache as clear_search_cache
)
from app.opensearch_client import get_opensearch_client
from app.config import Config

app = FastAPI(
    title="Property Data API with OpenSearch",
    description="API for loading, indexing, and searching CoreLogic property data with semantic search and caching",
    version="2.1.0"
)


# Pydantic models
class PropertyAddress(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "street": "811 MIDDLE ST",
                "city": "HONOLULU",
                "state": "HI",
                "zip_code": "96819",
                "county": "HONOLULU"
            }
        }
    )
    street: str
    city: str
    state: str
    zip_code: str
    county: str


class DataLoadRequest(BaseModel):
    addresses: List[PropertyAddress]
    save_to_file: Optional[bool] = True
    index_in_opensearch: Optional[bool] = True


class SearchRequest(BaseModel):
    query: Optional[str] = "property with 2+ acres in HI"
    page: Optional[int] = 1
    size: Optional[int] = 20
    use_cache: Optional[bool] = True


# Helper functions
def ensure_index_exists_with_knn():
    """
    Ensure index exists with proper k-NN vector configuration.
    Auto-creates if missing, auto-fixes if misconfigured.
    Returns: (exists, is_healthy, message)
    """
    client = get_opensearch_client()

    try:
        # Check if index exists
        if not client.indices.exists(index=Config.INDEX_NAME):
            print(f"Index '{Config.INDEX_NAME}' does not exist. Creating...")
            result = create_index()
            return True, True, f"Created new index: {result['message']}"

        # Index exists - verify it has proper k-NN configuration
        mapping = client.indices.get_mapping(index=Config.INDEX_NAME)
        properties = mapping[Config.INDEX_NAME]['mappings']['properties']

        # Check critical fields
        has_vector = 'description_vector' in properties
        is_knn_vector = properties.get('description_vector', {}).get('type') == 'knn_vector'
        correct_dimension = properties.get('description_vector', {}).get('dimension') == Config.EMBEDDING_DIMENSION

        if not (has_vector and is_knn_vector and correct_dimension):
            # Index exists but has wrong schema - need to recreate
            print(f"Index '{Config.INDEX_NAME}' has incorrect schema. Recreating...")

            # Get current document count
            count = client.count(index=Config.INDEX_NAME)
            doc_count = count['count']

            if doc_count > 0:
                print(f"WARNING: Deleting index with {doc_count} documents")

            # Delete old index
            client.indices.delete(index=Config.INDEX_NAME)
            print("Deleted old index")

            # Create new index with proper k-NN support
            result = create_index()

            message = f"Recreated index with k-NN support. Previous documents ({doc_count}) were deleted."
            if doc_count > 0:
                message += " You'll need to reindex your data."

            return True, True, message

        # Index exists and is properly configured
        count = client.count(index=Config.INDEX_NAME)
        doc_count = count['count']
        return True, True, f"Index exists and is healthy ({doc_count} documents)"

    except Exception as e:
        return False, False, f"Error checking/creating index: {str(e)}"


def process_property(client: CoreLogicAPIClient, address: dict) -> Optional[Dict[str, Any]]:
    """Process a single property address"""
    search_results = client.search_property(address)
    if not search_results or not search_results.get("items"):
        return None

    for idx, property_item in enumerate(search_results["items"]):
        clip = property_item.get("clip")
        if not clip:
            continue

        details = client.get_property_details(clip)

        if details:
            property_details = {
                'allBuildingsSummary': details.get("buildings", {}).get("data", {}).get("allBuildingsSummary"),
                'ownership': details.get("ownership", {}).get("data"),
                'siteLocation': details.get("siteLocation", {}).get("data"),
                'taxAssessment': details.get("taxAssessment", {}).get("items"),
                'mostRecentOwnerTransfer': details.get("mostRecentOwnerTransfer", {}).get("items"),
                'lastMarketSale': details.get("lastMarketSale", {}).get("items")
            }
            search_results["items"][idx]["property_details"] = property_details

    return search_results


# API Endpoints
@app.get("/")
def read_root():
    """Root endpoint"""
    return {
        "message": "Property Data API with OpenSearch",
        "version": "2.1.0",
        "features": [
            "Hybrid semantic + keyword search",
            "Smart query caching (5-minute TTL)",
            "Auto-index creation and fixing",
            "Advanced query parsing",
            "CoreLogic API integration"
        ],
        "endpoints": {
            "POST /api/data-load": "Load property data from CoreLogic (auto-creates index if needed)",
            "POST /api/search": "Hybrid semantic search with caching",
            "POST /api/cache/clear": "Clear search cache",
            "GET /api/cache/stats": "Get cache statistics",
            "POST /api/index/create": "Create OpenSearch index",
            "POST /api/index/load-from-file": "Load and index from JSON file (auto-creates index if needed)",
            "GET /api/index/stats": "Get index statistics",
            "GET /api/index/list": "List all indexed properties",
            "DELETE /api/index/delete": "Delete OpenSearch index",
            "GET /health": "Health check",
            "GET /docs": "Swagger documentation"
        }
    }


@app.post("/api/data-load")
def load_property_data(request: DataLoadRequest):
    """
    Load property data from CoreLogic API

    If index_in_opensearch is true, automatically ensures the index
    exists with proper k-NN vector configuration before indexing.
    """
    try:
        # If indexing is requested, ensure index exists with proper k-NN config
        if request.index_in_opensearch:
            exists, healthy, message = ensure_index_exists_with_knn()
            if not exists or not healthy:
                raise HTTPException(
                    status_code=500,
                    detail=f"Index configuration failed: {message}"
                )
            print(f"✅ Index check: {message}")

        # Authenticate with CoreLogic API
        client = CoreLogicAPIClient()
        if not client.authenticate():
            raise HTTPException(status_code=401, detail="Authentication failed")

        results = []
        files_saved = []
        indexed_count = 0
        failed_count = 0

        for addr in request.addresses:
            address_dict = {
                'street': addr.street,
                'city': addr.city,
                'state': addr.state,
                'zip_code': addr.zip_code,
                'county': addr.county
            }

            result = process_property(client, address_dict)

            if result:
                results.append(result)

                # Save to file
                if request.save_to_file:
                    filename = generate_filename(addr.street)
                    save_to_json(result, filename)
                    files_saved.append(filename)

                # Index in OpenSearch
                if request.index_in_opensearch:
                    for item in result.get('items', []):
                        if index_property(item):
                            indexed_count += 1
                        else:
                            failed_count += 1

        return {
            "status": "success",
            "message": f"Processed {len(results)} properties",
            "properties_processed": len(results),
            "files_saved": files_saved if request.save_to_file else None,
            "indexed_count": indexed_count if request.index_in_opensearch else 0,
            "failed_count": failed_count if request.index_in_opensearch else 0
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.post("/api/search")
def search_properties(request: SearchRequest):
    """
    Hybrid semantic search with caching

    Features:
    - Semantic vector search for understanding meaning
    - Smart query parsing for filters (bedrooms, price, location)
    - 5-minute cache for faster repeated queries
    - Automatic sorting based on query intent
    """
    try:
        # Check if index exists before searching
        client = get_opensearch_client()
        if not client.indices.exists(index=Config.INDEX_NAME):
            raise HTTPException(
                status_code=404,
                detail=f"Index '{Config.INDEX_NAME}' does not exist. Load some properties first using POST /api/data-load with index_in_opensearch: true"
            )

        # Execute hybrid search with caching
        results = hybrid_search(
            user_query=request.query,
            page=request.page,
            size=request.size,
            use_cache=request.use_cache
        )

        if not results:
            raise HTTPException(status_code=500, detail="Search failed")

        # Extract performance metrics
        performance = results.pop('performance', {})

        properties = []
        for hit in results['hits']['hits']:
            source = hit['_source']
            prop_details = source.get('property_details', {})

            # Extract assessed value safely
            assessed_value = None
            tax_year = None
            tax_assessments = prop_details.get('taxAssessment', [])
            if tax_assessments and len(tax_assessments) > 0:
                assessment = tax_assessments[0].get('assessedValue', {})
                assessed_value = assessment.get('calculatedTotalValue')
                tax_year = assessment.get('taxAssessedYear')

            properties.append({
                'clip': source.get('clip'),
                'address': source.get('propertyAddress'),
                'description': source.get('description', ''),
                'score': hit.get('_score'),
                'details': {
                    'bedrooms': prop_details.get('allBuildingsSummary', {}).get('bedroomsCount'),
                    'bathrooms': prop_details.get('allBuildingsSummary', {}).get('bathroomsCount'),
                    'livingAreaSqFt': prop_details.get('allBuildingsSummary', {}).get('livingAreaSquareFeet'),
                    'totalAreaSqFt': prop_details.get('allBuildingsSummary', {}).get('totalAreaSquareFeet')
                },
                'assessedValue': {
                    'total': assessed_value,
                    'year': tax_year
                }
            })

        return {
            "query": request.query,
            "total": results['hits']['total']['value'],
            "page": request.page,
            "size": request.size,
            "properties": properties,
            "performance": performance
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.post("/api/cache/clear")
def clear_cache():
    """Clear search query cache"""
    try:
        count = clear_search_cache()
        return {
            "status": "success",
            "message": f"Cleared {count} cache entries"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/api/cache/stats")
def cache_stats():
    """Get cache statistics"""
    try:
        stats = get_cache_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.post("/api/index/create")
def create_opensearch_index():
    """Create OpenSearch index"""
    try:
        client = get_opensearch_client()

        if client.indices.exists(index=Config.INDEX_NAME):
            return {
                "status": "exists",
                "message": f"Index '{Config.INDEX_NAME}' already exists"
            }

        result = create_index()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.post("/api/index/load-from-file")
def load_from_json_file(filepath: str = "property_search_data.json"):
    """
    Load and index properties from a JSON file
    Automatically ensures index exists with proper k-NN configuration
    """
    try:
        import json

        # Ensure index exists with proper k-NN configuration
        exists, healthy, message = ensure_index_exists_with_knn()
        if not exists or not healthy:
            raise HTTPException(
                status_code=500,
                detail=f"Index configuration failed: {message}"
            )
        print(f"✅ Index check: {message}")

        # Load JSON file
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Handle CoreLogic structure
        if isinstance(data, dict) and 'items' in data:
            properties = data['items']
        elif isinstance(data, list):
            properties = data
        else:
            properties = [data]

        # Index each property
        indexed_count = 0
        failed_count = 0

        for prop in properties:
            if index_property(prop):
                indexed_count += 1
            else:
                failed_count += 1

        return {
            "status": "success",
            "message": f"Indexed {indexed_count} properties from {filepath}",
            "indexed": indexed_count,
            "failed": failed_count,
            "total": len(properties)
        }

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {filepath}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/api/index/stats")
def get_index_stats():
    """Get index statistics"""
    try:
        client = get_opensearch_client()

        if not client.indices.exists(index=Config.INDEX_NAME):
            return {
                "status": "not_found",
                "message": f"Index '{Config.INDEX_NAME}' does not exist"
            }

        count = client.count(index=Config.INDEX_NAME)
        return {
            "index": Config.INDEX_NAME,
            "document_count": count['count']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/api/index/list")
def list_properties():
    """List all indexed properties"""
    try:
        client = get_opensearch_client()

        if not client.indices.exists(index=Config.INDEX_NAME):
            raise HTTPException(
                status_code=404,
                detail=f"Index '{Config.INDEX_NAME}' does not exist"
            )

        # Get all properties
        query = {
            "size": 100,
            "query": {"match_all": {}},
            "_source": ["clip", "propertyAddress", "description"]
        }

        results = client.search(index=Config.INDEX_NAME, body=query)

        properties = []
        for hit in results['hits']['hits']:
            source = hit['_source']
            properties.append({
                'clip': source.get('clip'),
                'address': source.get('propertyAddress', {}),
                'description': source.get('description', '')[:200] + '...' if len(
                    source.get('description', '')) > 200 else source.get('description', '')
            })

        return {
            "total": results['hits']['total']['value'],
            "properties": properties
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.delete("/api/index/delete")
def delete_opensearch_index():
    """Delete OpenSearch index"""
    try:
        client = get_opensearch_client()

        if not client.indices.exists(index=Config.INDEX_NAME):
            return {
                "status": "not_found",
                "message": f"Index '{Config.INDEX_NAME}' does not exist"
            }

        client.indices.delete(index=Config.INDEX_NAME)

        return {
            "status": "deleted",
            "message": f"Index '{Config.INDEX_NAME}' deleted successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/health")
def health_check():
    """Health check endpoint"""
    try:
        client = get_opensearch_client()
        client.cluster.health()
        opensearch_status = "connected"

        # Check index health if it exists
        index_status = "not_created"
        doc_count = 0
        is_knn_enabled = False

        if client.indices.exists(index=Config.INDEX_NAME):
            count = client.count(index=Config.INDEX_NAME)
            doc_count = count['count']

            # Check k-NN configuration
            mapping = client.indices.get_mapping(index=Config.INDEX_NAME)
            properties = mapping[Config.INDEX_NAME]['mappings']['properties']
            is_knn_enabled = properties.get('description_vector', {}).get('type') == 'knn_vector'

            if is_knn_enabled:
                index_status = "healthy"
            else:
                index_status = "misconfigured"

    except:
        opensearch_status = "disconnected"
        index_status = "unknown"
        doc_count = 0
        is_knn_enabled = False

    # Get cache stats
    cache_info = get_cache_stats()

    return {
        "status": "healthy" if opensearch_status == "connected" else "unhealthy",
        "opensearch": opensearch_status,
        "index": {
            "name": Config.INDEX_NAME,
            "status": index_status,
            "document_count": doc_count,
            "knn_enabled": is_knn_enabled
        },
        "cache": {
            "entries": cache_info['total_entries'],
            "ttl_seconds": cache_info['ttl_seconds']
        }
    }


@app.on_event("startup")
async def startup_event():
    """Display startup information"""
    print("\n" + "=" * 70)
    print("🏠 PROPERTY DATA API - STARTUP")
    print("=" * 70)
    print("\n✨ Features:")
    print("  • Hybrid semantic + keyword search")
    print("  • Smart query caching (5-minute TTL)")
    print("  • Auto-creates OpenSearch index with k-NN support")
    print("  • Auto-fixes misconfigured indexes")
    print("  • Advanced query parsing (bedrooms, price, location, etc.)")
    print("  • CoreLogic API integration")
    print("\n📊 Performance:")
    print("  • Cached queries: ~5ms")
    print("  • Hybrid search: ~250ms")
    print("  • Keyword only: ~130ms")
    print("\n📚 API Documentation: http://localhost:8000/docs")
    print("\n💡 Quick Start:")
    print("  1. POST /api/data-load with index_in_opensearch: true")
    print("  2. POST /api/search with your query")
    print("  3. Check cache stats: GET /api/cache/stats")
    print("\n🔍 Example Queries:")
    print('  • "industrial property in Honolulu"')
    print('  • "3 bedroom residential under 500k"')
    print('  • "corporate owned commercial properties"')
    print('  • "property with 2+ acres in HI"')
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)