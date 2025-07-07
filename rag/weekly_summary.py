import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from .generator import generate_summary
from database.db_manager import get_articles_by_date_range, find_similar_articles
from search.embeddings import generate_embedding

logger = logging.getLogger(__name__)

async def create_weekly_summary(theme: str, pool,
                                articles: List[Dict[str, Any]] = None) -> str:
    """
    Creates a weekly summary for the given theme using relevant articles.

    Args:
        theme: The weekly theme
        pool: Database connection pool
        articles: Optional pre-fetched list of articles

    Returns:
        str: Formatted summary text with markdown formatting
    """
    logger.info(f"Creating weekly summary for theme: {theme}")

    try:
        if articles is None:
            try:
                # Get all relevant articles for the theme
                theme_embedding = await generate_embedding(theme)
                if not theme_embedding:
                    logger.error("Failed to generate theme embedding")
                    return "Ошибка: не удалось обработать тему."

                # Get top 20 most relevant articles (we'll filter them later)
                articles = await find_similar_articles(pool, theme_embedding, limit=20)

                if not articles:
                    # Fallback to recent articles if no similar found
                    logger.warning(f"No similar articles found for theme: {theme}, falling back to recent articles")
                    today = datetime.now()
                    week_ago = (today - timedelta(days=7)).strftime('%Y-%m-%d')
                    today_str = today.strftime('%Y-%m-%d')
                    articles = await get_articles_by_date_range(pool, week_ago, today_str)

                    if not articles:
                        logger.warning("No recent articles found either")
                        return f"Не найдено статей по теме '{theme}'. Попробуйте позже."

                    # Sort by published date, newest first
                    articles = sorted(articles, key=lambda x: x.get('published', ''), reverse=True)[:20]
            except Exception as e:
                logger.error(f"Error finding articles: {e}", exc_info=True)
                return f"Ошибка при поиске статей: {str(e)}"

        if not articles:
            logger.warning(f"No relevant articles found for theme: {theme}")
            return f"По теме '{theme}' не найдено релевантных статей."

        logger.info(f"Found {len(articles)} relevant articles for summary")

        # Generate summary using the RAG model
        summary_text = await generate_summary(theme, articles)

        if not summary_text:
            logger.error("Failed to generate summary text")
            return "Не удалось сгенерировать обзор. Пожалуйста, попробуйте позже."
        raise
        # Format the summary with markdown

    except Exception as e:
        logger.error(f"Error in create_weekly_summary: {e}", exc_info=True)
        return (
            f"📅 *{theme}*\n\n"
            "К сожалению, не удалось сгенерировать полный дайджест. "
            "Вот несколько статей, которые могут быть вам интересны:\n\n" +
            "\n\n".join(
                f"📌 *{a['title']}*\n🔗 [Читать статью]({a.get('link', '')})"
                for a in articles[:3]
            )
        )
