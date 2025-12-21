# Swagger Configuration
swagger_config = {
    "headers": [],
    "specs": [{"endpoint": 'apispec', "route": '/apispec.json'}],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/api/docs"
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "HomeX Hybrid Search API - Semantic + Keyword",
        "description": "Ultimate real estate search with vector embeddings and rule-based filters",
        "version": "3.0.0"
    },
    "host": "localhost:5000",
    "basePath": "/",
    "schemes": ["http"]
}