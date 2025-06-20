import logging
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
import httpx
from bs4 import BeautifulSoup
from database.db_manager import save_article

logger = logging.getLogger(__name__)

def extract_telegram_post_data(message_html: str) -> Optional[Dict[str, Any]]:
    """Extract post data from a single Telegram message HTML."""
    try:
        soup = BeautifulSoup(message_html, 'html.parser')
        
        # Extract message text
        text_elem = soup.find("div", class_="tgme_widget_message_text")
        if not text_elem:
            return None
            
        text = text_elem.get_text(separator='\n', strip=True)
        if not text:
            return None
        
        # Extract message link
        link_elem = soup.find("a", class_="tgme_widget_message_date")
        if not link_elem or not link_elem.get('href'):
            return None
            
        link = link_elem['href']
        
        # Extract message date
        time_elem = soup.find("time", class_="time")
        if time_elem and time_elem.get('datetime'):
            date_str = time_elem['datetime']
            # Parse ISO 8601 date
            date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            date = datetime.utcnow()
            
        return {
            'text': text,
            'link': link,
            'date': date
        }
    except Exception as e:
        logger.error(f"Error extracting post data: {e}", exc_info=True)
        return None

async def fetch_telegram_messages(username: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch messages from a Telegram channel web interface."""
    url = f"https://t.me/s/{username}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    }
    
    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            http2=True
        ) as http_client:
            # First request to get the page with messages
            response = await http_client.get(url, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            messages = soup.find_all("div", class_="tgme_widget_message")
            
            results = []
            for msg in messages[:limit]:
                post_data = extract_telegram_post_data(str(msg))
                if post_data:
                    results.append(post_data)
            
            return results
            
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching Telegram channel @{username}: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"Request error while fetching Telegram channel @{username}: {e}")
    except Exception as e:
        logger.error(f"Error fetching Telegram channel @{username}: {e}", exc_info=True)
    
    return []

async def parse_telegram(client, pool, source: Dict[str, Any]) -> None:
    """
    Parse a Telegram channel using web interface.
    
    Args:
        client: Not used, kept for backward compatibility
        pool: Database connection pool
        source: Dictionary containing source configuration
    """
    username = source.get('username')
    if not username:
        logger.error("No username provided for Telegram source")
        return
    
    # Remove @ if present in username
    username = username.lstrip('@')
    logger.info(f"[TELEGRAM] Starting to parse channel: @{username}")
    
    try:
        # Fetch messages from the channel
        messages = await fetch_telegram_messages(username)
        
        if not messages:
            logger.warning(f"[TELEGRAM] No messages found for channel: @{username}")
            return
            
        logger.info(f"[TELEGRAM] Found {len(messages)} messages in channel @{username}")
        
        # Save messages to database
        saved_count = 0
        for msg in messages:
            try:
                title = f"Post from {username} - {msg['date'].strftime('%Y-%m-%d %H:%M')}"
                
                await save_article(
                    pool=pool,
                    title=title,
                    link=msg['link'],
                    content=msg['text'],
                    source=source['name'],
                    published_at=msg['date'],
                    tags=source.get('tags', [])
                )
                
                saved_count += 1
                logger.debug(f"[TELEGRAM] Saved post: {title}")
                
            except Exception as e:
                logger.error(f"[TELEGRAM] Error saving message to database: {e}", exc_info=True)
                continue
                
        logger.info(f"[TELEGRAM] Successfully saved {saved_count}/{len(messages)} posts from @{username}")
        
    except Exception as e:
        logger.error(f"[TELEGRAM] Error parsing channel @{username}: {e}", exc_info=True)
