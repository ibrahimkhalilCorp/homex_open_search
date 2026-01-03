from openai import OpenAI
from typing import List, Dict, Optional
from app.config import Config
from app.opensearch_client import get_opensearch_client

openai_client = OpenAI(api_key=Config.OPENAI_API_KEY)


def generate_embedding(text: str) -> Optional[List[float]]:
    """Generate vector embedding from text using OpenAI"""
    try:
        response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding
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
    try:
        opensearch_client = get_opensearch_client()

        # Generate description and embedding
        description = create_property_description(property_data)
        embedding = generate_embedding(description)

        if embedding is None:
            print(f"Skipping {property_data.get('clip')} - embedding failed")
            return False

        # Add generated fields
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
            id=property_data['clip'],
            body=property_data,
            refresh=True
        )

        return True

    except Exception as e:
        print(f"Failed to index {property_data.get('clip')}: {e}")
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