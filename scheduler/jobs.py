import logging
from parsers.main_parser import run_parsing
from search.embeddings import update_embeddings, generate_embedding
from rag.weekly_summary import create_weekly_summary
from utils.config import TELEGRAM_CHANNEL
import httpx
from database.db_manager import get_setting, find_similar_articles, get_published_links, add_published_link
from utils.telegram_web import send_web_message

logger = logging.getLogger(__name__)

async def scheduled_parsing(client, pool):
    """Job to run parsing of all sources."""
    logger.info("Scheduler: Running scheduled parsing...")
    await run_parsing(client, pool)
    logger.info("Scheduler: Scheduled parsing finished.")

async def scheduled_embedding_update(pool):
    """Job to update embeddings for new articles."""
    logger.info("Scheduler: Running scheduled embedding update...")
    await update_embeddings(pool)
    logger.info("Scheduler: Scheduled embedding update finished.")

async def scheduled_weekly_summary(client, pool):
    """Job to create and post a weekly summary based on the theme in DB."""
    logger.info("Scheduler: Checking for weekly summary job...")
    theme = await get_setting(pool, 'weekly_theme')

    if not theme:
        logger.warning("Scheduler: Weekly theme not set. Skipping summary generation.")
        return

    logger.info(f"Scheduler: Creating weekly summary for theme '{theme}'...")
    summary = await create_weekly_summary(theme, pool)
    
    # Send using web API instead of client
    success = await send_web_message(
        chat_id=TELEGRAM_CHANNEL,
        text=summary,
        parse_mode='Markdown'
    )
    
    if success:
        logger.info("Scheduler: Weekly summary posted.")
    else:
        logger.error("Scheduler: Failed to post weekly summary")

async def scheduled_post_publication(client, pool):
    """Job to find a relevant article based on the weekly theme, and publish it."""
    logger.info("Scheduler: Running scheduled post publication...")

    theme = await get_setting(pool, 'weekly_theme')
    if not theme:
        logger.warning("Scheduler: Weekly theme not set. Skipping post publication.")
        return

    published_links = await get_published_links(pool)

    try:
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            # 1. Generate embedding for the theme
            theme_embedding = await generate_embedding(theme, http_client)
            if not theme_embedding:
                logger.error(f"Scheduler: Could not generate embedding for theme '{theme}'.")
                return

            # 2. Find similar articles
            similar_articles = await find_similar_articles(pool, theme_embedding, limit=10)

            # 3. Find the first unpublished article
            post_to_publish = None
            for article in similar_articles:
                if article['link'] not in published_links:
                    post_to_publish = article
                    break

            if not post_to_publish:
                logger.info("Scheduler: No new articles found for the current theme to publish.")
                return

            # 4. Publish the article using web API
            message = f"<b>{post_to_publish['title']}</b>\n\n{post_to_publish['description'] or ''}\n\n<a href=\"{post_to_publish['link']}\">Read more</a>"
            
            success = await send_web_message(
                chat_id=TELEGRAM_CHANNEL,
                text=message,
                parse_mode='HTML',
                disable_web_page_preview=False
            )
            
            if success:
                await add_published_link(pool, post_to_publish['link'])
                logger.info(f"Scheduler: Successfully published post: {post_to_publish['link']}")
            else:
                logger.error(f"Scheduler: Failed to publish post: {post_to_publish['link']}")

    except Exception as e:
        logger.error(f"Scheduler: Error during post publication: {e}", exc_info=True)
