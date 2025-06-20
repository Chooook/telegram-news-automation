import os
import httpx
import asyncio
from database.db_manager import get_articles_without_embeddings, add_embedding

# Get API Key from environment variables. Ensure .env is loaded in main.py
API_KEY = os.getenv("HF_API_TOKEN")
API_URL = "https://api-inference.huggingface.co/models/sentence-transformers/all-MiniLM-L6-v2"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

async def generate_embedding(text: str, client: httpx.AsyncClient):
    """
    Generates a vector embedding for the given text using Hugging Face API.
    """
    if not text or not isinstance(text, str):
        return None

    payload = {"inputs": text, "options": {"wait_for_model": True}}
    
    try:
        response = await client.post(API_URL, headers=HEADERS, json=payload)
        
        if response.status_code == 503: # Model is loading
            print("Model is loading on Hugging Face, waiting 20 seconds to retry...")
            await asyncio.sleep(20)
            response = await client.post(API_URL, headers=HEADERS, json=payload)

        response.raise_for_status()
        result = response.json()
        
        # The API returns a list of floats for a single string input.
        if isinstance(result, list) and len(result) > 0 and isinstance(result[0], float):
             return result
        # If it returns a list of lists (for multiple sentences), take the first.
        if isinstance(result, list) and len(result) > 0 and isinstance(result[0], list):
            return result[0]

        print(f"Unexpected API response format: {result}")
        return None

    except httpx.HTTPStatusError as e:
        print(f"API request failed with status {e.response.status_code}: {e.response.text}")
        return None
    except Exception as e:
        print(f"An error occurred while generating embedding: {e}")
        return None

async def update_embeddings(pool):
    """
    Finds articles without embeddings, generates them, and saves to the DB via API.
    """
    if not API_KEY:
        print("\nERROR: Hugging Face API key not found.")
        print("Please get a key from https://huggingface.co/settings/tokens and add it to your .env file as:")
        print('HF_API_TOKEN="hf_..."\n')
        return

    print("Starting to update embeddings via API...")
    articles_to_process = await get_articles_without_embeddings(pool)
    
    if not articles_to_process:
        print("No new articles to generate embeddings for.")
        return

    count = 0
    # Using a single client session is more efficient
    async with httpx.AsyncClient(timeout=60.0) as client:
        for article in articles_to_process:
            text_to_embed = f"{article['title']} {article['description'] or ''}".strip()
            if text_to_embed:
                # Adding a small delay to be respectful to the free API tier
                await asyncio.sleep(1)

                embedding = await generate_embedding(text_to_embed, client)

                if embedding is not None:
                    await add_embedding(pool, article['link'], embedding)
                    count += 1
                    print(f"  > Generated embedding for article: {article['link']}")
                else:
                    print(f"  > Failed to generate embedding for article: {article['link']}")
    
    print(f"Successfully generated {count} new embeddings.")
