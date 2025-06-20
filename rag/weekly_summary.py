from .retriever import retrieve_relevant_articles
from .generator import generate_summary

async def create_weekly_summary(theme: str, pool):
    """
    Creates a weekly summary for a given theme.
    
    1. Retrieves relevant articles from the last week.
    2. Generates a summary based on these articles.
    """
    print(f"Creating weekly summary for theme: {theme}")
    
    # 1. Retrieve articles
    articles = await retrieve_relevant_articles(theme, pool)
    
    # 2. Generate summary
    summary_text = generate_summary(theme, articles)
    
    print("Weekly summary created successfully.")
    return summary_text
