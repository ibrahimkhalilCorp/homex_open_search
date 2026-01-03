"""
Complete Fix Script for OpenSearch Index
Deletes, recreates, and reloads data with proper vector mappings
"""

import json
import sys
from app.opensearch_client import get_opensearch_client
from app.indexer import create_index, index_property
from app.config import Config


def main():
    print("\n" + "=" * 70)
    print("OPENSEARCH INDEX FIX - COMPLETE SOLUTION")
    print("=" * 70)

    client = get_opensearch_client()

    # Step 1: Check and delete existing index
    print(f"\n[STEP 1/4] Checking existing index '{Config.INDEX_NAME}'...")
    if client.indices.exists(index=Config.INDEX_NAME):
        print(f"⚠️  Index '{Config.INDEX_NAME}' exists (incorrect schema)")
        print("   Deleting old index...")
        try:
            client.indices.delete(index=Config.INDEX_NAME)
            print("✅ Successfully deleted old index")
        except Exception as e:
            print(f"❌ Error deleting index: {e}")
            return False
    else:
        print(f"ℹ️  Index '{Config.INDEX_NAME}' does not exist")

    # Step 2: Create new index with proper k-NN vector support
    print(f"\n[STEP 2/4] Creating new index with k-NN vector support...")
    try:
        result = create_index()
        if result['status'] == 'created':
            print(f"✅ {result['message']}")
        else:
            print(f"⚠️  {result['message']}")
    except Exception as e:
        print(f"❌ Error creating index: {e}")
        return False

    # Step 3: Verify index mappings
    print(f"\n[STEP 3/4] Verifying index mappings...")
    try:
        mapping = client.indices.get_mapping(index=Config.INDEX_NAME)
        properties = mapping[Config.INDEX_NAME]['mappings']['properties']

        # Check critical fields
        has_description_vector = 'description_vector' in properties
        is_knn_vector = properties.get('description_vector', {}).get('type') == 'knn_vector'
        vector_dim = properties.get('description_vector', {}).get('dimension')

        print(f"   ✓ description_vector field exists: {has_description_vector}")
        print(f"   ✓ description_vector is knn_vector type: {is_knn_vector}")
        print(f"   ✓ Vector dimension: {vector_dim}")

        if not (has_description_vector and is_knn_vector and vector_dim == Config.EMBEDDING_DIMENSION):
            print("❌ Index mapping is incorrect!")
            return False

        print("✅ Index mappings are correct")

    except Exception as e:
        print(f"❌ Error verifying mappings: {e}")
        return False

    # Step 4: Load and index data
    print(f"\n[STEP 4/4] Loading data from property_search_data.json...")
    try:
        with open('data/output/property_search_data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Handle CoreLogic structure
        if isinstance(data, dict) and 'items' in data:
            properties = data['items']
        elif isinstance(data, list):
            properties = data
        else:
            properties = [data]

        print(f"   Found {len(properties)} properties to index")

        # Index each property with progress
        print("\n   Indexing properties with embeddings...")
        indexed_count = 0
        failed_count = 0

        for i, prop in enumerate(properties, 1):
            clip = prop.get('clip', 'Unknown')
            print(f"   [{i}/{len(properties)}] Property {clip}...", end=" ")

            if index_property(prop):
                indexed_count += 1
                print("✅")
            else:
                failed_count += 1
                print("❌")

        # Refresh index to make documents searchable immediately
        print("\n   Refreshing index...")
        client.indices.refresh(index=Config.INDEX_NAME)

        # Verify documents were indexed
        count = client.count(index=Config.INDEX_NAME)
        doc_count = count['count']

        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"✅ Successfully indexed: {indexed_count}/{len(properties)}")
        print(f"❌ Failed: {failed_count}/{len(properties)}")
        print(f"📊 Documents in index: {doc_count}")

        if doc_count != indexed_count:
            print(f"⚠️  WARNING: Expected {indexed_count} documents, but index has {doc_count}")

        # Final verification - test vector field
        print("\n[FINAL CHECK] Testing vector search capability...")
        try:
            sample = client.search(
                index=Config.INDEX_NAME,
                body={
                    "size": 1,
                    "query": {"match_all": {}}
                }
            )

            if sample['hits']['hits']:
                doc = sample['hits']['hits'][0]['_source']
                has_vector = 'description_vector' in doc
                has_description = 'description' in doc
                vector_length = len(doc.get('description_vector', []))

                print(f"   ✓ Sample document has description: {has_description}")
                print(f"   ✓ Sample document has vector: {has_vector}")
                print(f"   ✓ Vector dimension: {vector_length}")

                if has_vector and vector_length == Config.EMBEDDING_DIMENSION:
                    print("\n✨ SUCCESS! Index is ready for semantic search!")
                    print(f"\nYou can now use the search API:")
                    print(f"  POST http://localhost:8000/api/search")
                    print(f'  Body: {{"query": "industrial property", "page": 1, "size": 10}}')
                    return True
                else:
                    print("\n❌ Vector field issue detected")
                    return False
            else:
                print("❌ No documents found in index")
                return False

        except Exception as e:
            print(f"❌ Error testing search: {e}")
            return False

    except FileNotFoundError:
        print("❌ Error: property_search_data.json not found")
        print("   Make sure the file is in the current directory")
        return False
    except Exception as e:
        print(f"❌ Error loading/indexing data: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    try:
        success = main()
        print("\n" + "=" * 70)
        if success:
            print("🎉 ALL DONE! Your search API is ready to use!")
        else:
            print("⚠️  Fix completed with errors. Please review output above.")
        print("=" * 70 + "\n")
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)