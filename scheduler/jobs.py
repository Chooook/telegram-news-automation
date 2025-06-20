from parsers.main_parser import run_parsing
from search.embeddings import update_embeddings
from rag.weekly_summary import create_weekly_summary
from utils.config import TELEGRAM_CHANNEL
import httpx
from database.db_manager import get_setting, find_similar_articles, get_published_links, add_published_link

async def scheduled_parsing(client, pool):
    """Job to run parsing of all sources."""
    print("Scheduler: Running scheduled parsing...")
    await run_parsing(client, pool)
    print("Scheduler: Scheduled parsing finished.")

async def scheduled_embedding_update(pool):
    """Job to update embeddings for new articles."""
    print("Scheduler: Running scheduled embedding update...")
    await update_embeddings(pool)
    print("Scheduler: Scheduled embedding update finished.")

async def scheduled_weekly_summary(client, pool):
    """Job to create and post a weekly summary based on the theme in DB."""
    print("Scheduler: Checking for weekly summary job...")
    theme = await get_setting(pool, 'weekly_theme')

    if not theme:
        print("Scheduler: Weekly theme not set. Skipping summary generation.")
        return

    print(f"Scheduler: Creating weekly summary for theme '{theme}'...")
    summary = await create_weekly_summary(theme, pool)
    await client.send_message(TELEGRAM_CHANNEL, summary)
    print("Scheduler: Weekly summary posted.")

from search.embeddings import generate_embedding

async def scheduled_post_publication(client, pool):
    """Job to find a relevant article based on the weekly theme, and publish it."""
    print("Scheduler: Running scheduled post publication...")

    theme = await get_setting(pool, 'weekly_theme')
    if not theme:
        print("Scheduler: Weekly theme not set. Skipping post publication.")
        return

    published_links = await get_published_links(pool)

    try:
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            # 1. Generate embedding for the theme
            theme_embedding = await generate_embedding(theme, http_client)
            if not theme_embedding:
                print(f"Scheduler: Could not generate embedding for theme '{theme}'.")
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
                print("Scheduler: No new articles found for the current theme to publish.")
                return

            # 4. Publish the article
            message = f"**{post_to_publish['title']}**\n\n{post_to_publish['description'] or ''}\n\n[Read more]({post_to_publish['link']})"

            await client.send_message(TELEGRAM_CHANNEL, message, link_preview=True, parse_mode='markdown')
            await add_published_link(pool, post_to_publish['link'])

            print(f"Scheduler: Successfully published post: {post_to_publish['link']}")

    except Exception as e:
        print(f"Scheduler: Error during post publication: {e}")
