import asyncio
import httpx
from bs4 import BeautifulSoup
from database.db_manager import save_article
import datetime
import logging

logger = logging.getLogger(__name__)

async def parse_telegram(client, pool, source):
    """
    Parses a Telegram channel using web interface and adds new messages to the database.
    """
    logger.info(f"[WEB] Parsing Telegram channel: {source['name']}")
    
    username = source['username'].lstrip('@')
    url = f"https://t.me/s/{username}"
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        )
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            # First request to get the channel page
            response = await http_client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            messages = soup.find_all("div", class_="tgme_widget_message")
            logger.info(f"[WEB] Found {len(messages)} messages in {username}")

            articles_added = 0
            for i, msg in enumerate(messages[:50], 1):
                try:
                    # Extract message text
                    text_elem = msg.find("div", class_="tgme_widget_message_text")
                    text = text_elem.get_text(separator="\n", strip=True) if text_elem else ''
                    
                    # Extract message date
                    date_elem = msg.find("time")
                    date = datetime.datetime.now()
                    if date_elem and 'datetime' in date_elem.attrs:
                        try:
                            date = datetime.datetime.strptime(
                                date_elem['datetime'], 
                                '%Y-%m-%dT%H:%M:%S%z'
                            )
                        except (ValueError, KeyError) as e:
                            logger.warning(f"Could not parse date: {e}")
                    
                    # Extract message link
                    link_elem = msg.find("a", class_="tgme_widget_message_date")
                    if link_elem and 'href' in link_elem.attrs:
                        link = link_elem['href']
                    else:
                        link = f"https://t.me/s/{username}/{i}"
                    
                    # Prepare article data
                    title = text.split('\n')[0][:100] if text else f"Message from {username}"
                    
                    # Save to database
                    await save_article(
                        pool,
                        title,
                        link,
                        text,
                        source['name'],
                        source.get('tags', [])
                    )
                    
                    articles_added += 1
                    logger.info(f"[WEB] Added message: {title}")
                    
                    # Be nice to the server
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Error processing message {i}: {e}")
                    continue
            
            logger.info(f"[WEB] Successfully added {articles_added} messages from {username}")
            
    except httpx.HTTPStatusError as e:
        logger.error(f"[WEB] HTTP error {e.response.status_code} while fetching {url}")
    except httpx.RequestError as e:
        logger.error(f"[WEB] Request error while fetching {url}: {e}")
    except Exception as e:
        logger.error(f"[WEB] Error parsing {username}: {e}", exc_info=True)
