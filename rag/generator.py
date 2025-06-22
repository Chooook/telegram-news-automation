from typing import List, Dict, Optional
import logging
from .llm_utils import generate_theme_description, generate_article_summary, should_exclude_article

logger = logging.getLogger(__name__)

async def generate_summary(theme: str, articles: List[Dict]) -> str:
    """
    Generates a summary for a given theme based on a list of articles.
    Uses LLM to generate a coherent and informative summary.
    """
    if not articles:
        return f"На этой неделе не было найдено статей по теме '{theme}'."
    
    try:
        # Generate theme description
        theme_desc = await generate_theme_description(theme)
        
        # Filter out unwanted articles
        filtered_articles = [a for a in articles if not should_exclude_article(a)]
        
        if not filtered_articles:
            return (
                f"📅 *{theme}*\n\n"
                f"{theme_desc}\n\n"
                "К сожалению, на этой неделе не нашлось подходящих статей по теме. "
                "Возвращайтесь на следующей неделе за новыми материалами!"
            )
        
        # Limit to top 5 articles for the summary
        top_articles = filtered_articles[:5]
        
        # Generate summaries for each article
        article_summaries = []
        for article in top_articles:
            summary = await generate_article_summary(article)
            article_summaries.append({
                'title': article['title'],
                'summary': summary,
                'link': article.get('link', '')
            })
        
        # Format the final summary
        summary_parts = [
            f"📅 *{theme}*\n\n"
            f"{theme_desc}\n\n"
            "📚 *Главные материалы недели:*\n\n"
        ]
        
        for i, article in enumerate(article_summaries, 1):
            summary_parts.append(
                f"{i}. *{article['title']}*\n"
                f"{article['summary']}\n"
                f"🔗 [Читать статью]({article['link']})\n"
            )
        
        summary_parts.append(
            "\nЧто из этого вам было наиболее интересно? "
            "Какие аспекты темы вы бы хотели изучить подробнее?"
        )
        
        return "\n".join(summary_parts)
        
    except Exception as e:
        logger.error(f"Error generating summary: {e}", exc_info=True)
        # Fallback to simple format if LLM fails
        return (
            f"📅 *{theme}*\n\n"
            "Вот что интересного нашли на этой неделе:\n\n" +
            "\n\n".join(
                f"📌 *{a['title']}*\n🔗 [Читать статью]({a.get('link', '')})"
                for a in articles[:5]
            )
        )
