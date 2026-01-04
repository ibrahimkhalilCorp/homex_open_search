from openai import OpenAI
from typing import List, Dict, Optional
from app.config import Config
from app.opensearch_client import get_opensearch_client
import time

# # For Open AI API
# openai_client = OpenAI(api_key=Config.OPENAI_API_KEY)
# embedding_model = Config.OPENAI_API_EMBEDDING_MODEL

# Point to your local LM Studio server
embedding_model = Config.LM_STUDIO_EMBEDDING_MODEL
openai_client = OpenAI(
    base_url=Config.LM_STUDIO_ENDPOINT,
    api_key=Config.LM_STUDIO_API_KEY  # LM Studio doesn't require a real key, but the client needs something
)

def generate_embedding(text: str) -> Optional[List[float]]:
    if not text or not text.strip():
        print(f"[SKIP] Empty text provided for embedding")
        return None

    try:
        response = openai_client.embeddings.create(
            model=embedding_model,
            input=text
        )
        embedding = response.data[0].embedding
        # Validate embedding
        if not embedding or len(embedding) == 0:
            print(f"[ERROR] Empty embedding returned")
            return None

        if len(embedding) != Config.EMBEDDING_DIMENSION:
            print(f"[ERROR] Embedding dimension mismatch: expected {Config.EMBEDDING_DIMENSION}, got {len(embedding)}")
            return None

        return embedding
    except Exception as e:
        print(f"Embedding generation failed: {e}")
        return None


def create_property_description(property_data: Dict) -> str:
    """Create a rich text description for embedding"""
    parts = []

    clip = property_data.get('clip', 'Unknown')
    parts.append(f"Property ID {clip}")

    # Address
    addr = property_data.get('propertyAddress', {})
    street = addr.get('streetAddress', '')
    city = addr.get('city', '')
    state = addr.get('state', '')
    county = addr.get('county', '')

    if street and city and state:
        parts.append(f"Located at {street}, {city}, {state}")
    if county:
        parts.append(f"in {county} County")

    # Property details
    prop_details = property_data.get('property_details', {})
    buildings = prop_details.get('allBuildingsSummary', {})

    bedrooms = buildings.get('bedroomsCount')
    bathrooms = buildings.get('bathroomsCount')
    living_sqft = buildings.get('livingAreaSquareFeet')
    total_sqft = buildings.get('totalAreaSquareFeet')

    # Only add bedroom/bathroom info if they exist and are not null
    if bedrooms and bathrooms:
        parts.append(f"{bedrooms} bedroom, {bathrooms} bathroom property")
    if living_sqft:
        parts.append(f"with {living_sqft:,} square feet of living space")
    elif total_sqft:
        parts.append(f"with {total_sqft:,} total square feet")

    # Site location
    site = prop_details.get('siteLocation', {})
    land_use = site.get('landUseAndZoningCodes', {})
    state_land_use = land_use.get('stateLandUseDescription', '')

    if state_land_use:
        parts.append(f"Classified as {state_land_use.lower()}")

    # Lot information
    lot = site.get('lot', {})
    lot_acres = lot.get('areaAcres')
    if lot_acres:
        parts.append(f"on {lot_acres:.2f} acre lot")

    # Ownership
    ownership = prop_details.get('ownership', {})
    current_owners = ownership.get('currentOwners', {})
    owner_names = current_owners.get('ownerNames', [])

    if owner_names and owner_names[0].get('fullName'):
        owner_name = owner_names[0]['fullName']
        is_corporate = owner_names[0].get('isCorporate', False)
        ownership_type = "Corporate" if is_corporate else "Individual"
        parts.append(f"Owned by {owner_name} ({ownership_type} ownership)")

    # Tax assessment
    tax_assessments = prop_details.get('taxAssessment', [])
    if tax_assessments:
        tax = tax_assessments[0]
        assessed_value = tax.get('assessedValue', {})
        total_value = assessed_value.get('calculatedTotalValue')
        tax_year = assessed_value.get('taxAssessedYear')

        if total_value and tax_year:
            parts.append(f"Assessed value ({tax_year}): ${total_value:,.0f}")

    description = ". ".join(parts) + "."
    return description


def index_property(property_data: Dict) -> bool:
    """Index a single property with vector embedding"""
    clip = property_data.get('clip', 'Unknown')

    try:
        opensearch_client = get_opensearch_client()

        # Generate description
        description = create_property_description(property_data)

        if not description or not description.strip():
            print(f"[SKIP] {clip} - Empty description generated")
            return False

        print(f"\n[PROCESSING] {clip}")
        print(f"   Description: {description[:100]}...")
        print(f"   Length: {len(description)} chars")

        # Generate embedding
        print(f"   Generating embedding...")
        start = time.time()
        embedding = generate_embedding(description)
        elapsed = time.time() - start

        if embedding is None:
            print(f"[SKIP] {clip} - Embedding generation failed")
            return False

        print(f"   ✅ Embedding generated in {elapsed:.2f}s")
        print(f"   Dimension: {len(embedding)}")

        # Validate embedding before adding to property_data
        if len(embedding) != Config.EMBEDDING_DIMENSION:
            print(f"[SKIP] {clip} - Invalid embedding dimension: {len(embedding)}")
            return False

        # Add generated fields ONLY if embedding was successful
        property_data['description'] = description
        property_data['description_vector'] = embedding

        # Convert coordinates to geo_point format
        if 'property_details' in property_data:
            site = property_data['property_details'].get('siteLocation', {})

            parcel_coords = site.get('coordinatesParcel', {})
            if parcel_coords and 'lat' in parcel_coords and 'lng' in parcel_coords:
                site['coordinatesParcel'] = {
                    "lat": parcel_coords['lat'],
                    "lon": parcel_coords['lng']
                }

        # Index in OpenSearch
        opensearch_client.index(
            index=Config.INDEX_NAME,
            id=clip,
            body=property_data,
            refresh=True
        )

        print(f"[SUCCESS] ✅ Indexed {clip}\n")
        return True

    except Exception as e:
        print(f"[ERROR] ❌ Failed to index {clip}: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_index():
    """Create OpenSearch index with vector support"""
    opensearch_client = get_opensearch_client()

    if opensearch_client.indices.exists(index=Config.INDEX_NAME):
        return {"status": "exists", "message": "Index already exists"}

    index_body = {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "knn": True
            }
        },
        "mappings": {
            "properties": {
                "clip": {"type": "keyword"},
                "propertyAddress": {
                    "properties": {
                        "streetAddress": {"type": "text"},
                        "city": {"type": "keyword"},
                        "state": {"type": "keyword"},
                        "zipCode": {"type": "keyword"},
                        "county": {"type": "keyword"}
                    }
                },
                "property_details": {
                    "properties": {
                        "allBuildingsSummary": {
                            "properties": {
                                "bedroomsCount": {"type": "integer"},
                                "bathroomsCount": {"type": "integer"},
                                "livingAreaSquareFeet": {"type": "integer"},
                                "totalAreaSquareFeet": {"type": "integer"}
                            }
                        },
                        "ownership": {
                            "properties": {
                                "currentOwners": {
                                    "properties": {
                                        "ownerNames": {
                                            "type": "nested",
                                            "properties": {
                                                "fullName": {"type": "text"},
                                                "isCorporate": {"type": "boolean"}
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "siteLocation": {
                            "properties": {
                                "coordinatesParcel": {"type": "geo_point"},
                                "landUseAndZoningCodes": {
                                    "properties": {
                                        "stateLandUseDescription": {"type": "keyword"}
                                    }
                                },
                                "lot": {
                                    "properties": {
                                        "areaAcres": {"type": "float"}
                                    }
                                }
                            }
                        },
                        "taxAssessment": {
                            "type": "nested",
                            "properties": {
                                "assessedValue": {
                                    "properties": {
                                        "calculatedTotalValue": {"type": "float"}
                                    }
                                }
                            }
                        }
                    }
                },
                "description": {"type": "text"},
                "description_vector": {
                    "type": "knn_vector",
                    "dimension": Config.EMBEDDING_DIMENSION,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "lucene"
                    }
                }
            }
        }
    }

    opensearch_client.indices.create(index=Config.INDEX_NAME, body=index_body)
    return {"status": "created", "message": "Index created successfully"}