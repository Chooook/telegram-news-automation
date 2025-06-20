from search.embeddings import generate_embedding
from database.db_manager import find_similar_articles

import httpx

async def semantic_search(query: str, pool, top_k=5, start_date=None, end_date=None):
    """
    Performs semantic search for a given query, with optional date filtering.

    Args:
        query (str): The user's search query.
        pool: The database connection pool.
        top_k (int): The number of top results to return.
        start_date (str): The start date for filtering articles (inclusive).
        end_date (str): The end date for filtering articles (inclusive).

    Returns:
        list: A list of the most relevant articles.
    """
    if not query:
        return []

    # 1. Generate embedding for the query
    async with httpx.AsyncClient(timeout=30.0) as client:
        query_embedding = await generate_embedding(query, client)
        if query_embedding is None:
            return []

        # 2. Find similar articles using the database function
        similar_articles = await find_similar_articles(
            pool,
            embedding=query_embedding,
            limit=top_k,
            start_date=start_date,
            end_date=end_date
        )

        return similar_articles
