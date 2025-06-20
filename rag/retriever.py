from datetime import datetime, timedelta
from search.lm_search import semantic_search

async def retrieve_relevant_articles(theme: str, pool, days_back=7, top_k=10):
    """
    Retrieves articles relevant to a theme from the last N days using semantic search.
    """
    print(f"Retrieving top {top_k} articles for theme '{theme}' from the last {days_back} days.")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    # This will require updating semantic_search to accept date ranges
    relevant_articles = await semantic_search(
        query=theme,
        pool=pool,
        top_k=top_k,
        start_date=start_date,
        end_date=end_date
    )
    
    print(f"Found {len(relevant_articles)} relevant articles.")
    return relevant_articles
