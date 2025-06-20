import feedparser
import asyncio
from datetime import datetime
from database.db_manager import save_article

async def parse_rss(pool, source):
    """
    Parses an RSS feed and adds new articles to the database.
    """
    print(f"Parsing RSS source: {source['name']}")
    for tag in source.get('tags', []):
        try:
            feed_url = source['url'].format(tag=tag)
            feed = feedparser.parse(feed_url)

            for entry in feed.entries:
                title = entry.title
                url = entry.link
                content = entry.summary
                if hasattr(entry, 'content'):
                    content = entry.content[0].value

                await save_article(pool, title, url, content, source['name'], [tag])
                print(f"  > Added article: {title}")
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Error parsing RSS feed for tag {tag}: {e}")
