from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from flasgger import Swagger, swag_from
from src.root.swagger_config import *
from src.helper.helper import *
app = Flask(__name__)
CORS(app)
swagger = Swagger(app, config=swagger_config)

@app.route('/api/search/hybrid', methods=['POST'])
@swag_from({
    'tags': ['Hybrid Search'],
    'summary': 'Hybrid Search - Semantic + Keyword',
    'description': '''
    **Ultimate search combining:**
    - 🧠 Semantic understanding (vector embeddings)
    - 🔍 Exact filters (bedrooms, price, location)
    - ⚡ Smart caching (5-minute TTL)

    **Examples:**
    - "cozy family home with backyard" (semantic)
    - "3 bed in SF under 600k" (filters + semantic)
    - "modern luxury estate near schools" (both)
    ''',
    'parameters': [{
        'name': 'body',
        'in': 'body',
        'required': True,
        'schema': {
            'type': 'object',
            'required': ['query'],
            'properties': {
                'query': {'type': 'string', 'example': 'cozy family home with backyard'},
                'cache': {'type': 'boolean', 'default': True},
                'page': {'type': 'integer', 'default': 1, 'minimum': 1},
                'size': {'type': 'integer', 'default': 20, 'minimum': 1, 'maximum': 100}
            }
        }
    }],
    'responses': {
        200: {
            'description': 'Successful search with results',
            'examples': {
                'application/json': {
                    'query': 'cozy family home with backyard',
                    'total': 2,
                    'properties': [
                        {
                            'id': 'MLS-2024-43494',
                            'price': 575000,
                            'address': {
                                'city': 'San Francisco',
                                'state': 'CA',
                                'streetAddress': '0336 Thomas Flats'
                            },
                            'details': {
                                'bedrooms': 3,
                                'bathrooms': 4.0,
                                'squareFeet': 0
                            },
                            'photos': ['https://cdn.realestate.com/photos/1_1.jpg'],
                            'status': 'Active',
                            'description': 'Listing MLS-2024-43494: Active Land. 3 bedroom, 4.0 bathroom property...',
                            'score': 0.89
                        }
                    ],
                    'performance': {
                        'parse_time': 0.5,
                        'search_time': 234.2,
                        'total_time': 235.1,
                        'method': 'hybrid_semantic'
                    },
                    'from_cache': False,
                    'page': 1,
                    'filters_applied': {
                        'filters': {'must': [], 'filter': [{'term': {'status': 'Active'}}]},
                        'sort': None
                    }
                }
            }
        },
        400: {
            'description': 'Bad request - query is required'
        },
        500: {
            'description': 'Search failed'
        }
    }
})
def hybrid_search():
    """Hybrid search endpoint"""
    data = request.json
    user_query = data.get('query', '')
    use_cache = data.get('cache', True)
    page = data.get('page', 1)
    size = data.get('size', 20)

    if not user_query:
        return jsonify({'error': 'Query is required'}), 400

    start_total = time.time()

    # Check cache
    if use_cache:
        cache_key = get_cache_key(user_query + str(page))
        if cache_key in query_cache:
            cached = query_cache[cache_key]
            print(f"[CACHE HIT] {user_query}")

            return jsonify({
                'query': user_query,
                'total': cached['total'],
                'properties': cached['properties'],
                'performance': {
                    'total_time': round((time.time() - start_total) * 1000, 1),
                    'method': 'cached'
                },
                'from_cache': True,
                'page': page
            })

    # Parse filters (fast)
    start_parse = time.time()
    parsed = parse_query_fast(user_query)
    parse_time = time.time() - start_parse

    # Execute hybrid search
    start_search = time.time()
    search_results = search_hybrid(user_query, parsed, page, size)
    search_time = time.time() - start_search

    if not search_results:
        return jsonify({'error': 'Search failed'}), 500

    # Format results
    properties = format_properties(search_results)
    total = search_results['hits']['total']['value']

    # Cache results
    if use_cache and page == 1:
        cache_key = get_cache_key(user_query + str(page))
        query_cache[cache_key] = {
            'total': total,
            'properties': properties,
            'cached_at': time.time()
        }
        clean_cache()

    total_time = time.time() - start_total

    return jsonify({
        'query': user_query,
        'total': total,
        'properties': properties,
        'performance': {
            'parse_time': round(parse_time * 1000, 1),
            'search_time': round(search_time * 1000, 1),
            'total_time': round(total_time * 1000, 1),
            'method': 'hybrid_semantic'
        },
        'from_cache': False,
        'page': page,
        'filters_applied': parsed
    })


@app.route('/api/search', methods=['POST'])
@swag_from({
    'tags': ['Search'],
    'summary': 'Standard Search (Keyword Only)',
    'description': 'Traditional keyword search without semantic understanding'
})
def standard_search():
    """Standard keyword-only search (backward compatible)"""
    data = request.json
    user_query = data.get('query', '')
    page = data.get('page', 1)
    size = data.get('size', 20)

    if not user_query:
        return jsonify({'error': 'Query is required'}), 400

    start = time.time()

    # Parse filters
    parsed = parse_query_fast(user_query)

    # Keyword-only search
    search_results = search_keyword_only(parsed, page, size)

    if not search_results:
        return jsonify({'error': 'Search failed'}), 500

    properties = format_properties(search_results)
    total_time = time.time() - start

    return jsonify({
        'query': user_query,
        'total': search_results['hits']['total']['value'],
        'properties': properties,
        'performance': {
            'total_time': round(total_time * 1000, 1),
            'method': 'keyword_only'
        },
        'page': page
    })


@app.route('/api/cache/clear', methods=['POST'])
def clear_cache():
    """Clear query cache"""
    count = len(query_cache)
    query_cache.clear()
    return jsonify({'message': f'Cleared {count} entries', 'status': 'success'})


if __name__ == '__main__':
    app.run(debug=True, port=5000)