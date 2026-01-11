from openai import OpenAI
from typing import List, Optional
from app.config.config import Config

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

