import httpx
import logging
from typing import Optional
from utils.config import BOT_TOKEN

logger = logging.getLogger(__name__)

async def send_web_message(chat_id: str, text: str, parse_mode: str = 'HTML', disable_web_page_preview: bool = False) -> bool:
    """
    Send a message to a chat using Telegram Bot API via web.
    
    Args:
        chat_id: The chat ID or username with @
        text: The message text
        parse_mode: 'HTML' or 'Markdown'
        disable_web_page_preview: Whether to disable link previews
        
    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    # Remove @ if present in chat_id
    chat_id = chat_id.lstrip('@')
    
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode,
        'disable_web_page_preview': disable_web_page_preview
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return True
    except Exception as e:
        logger.error(f"Error sending message to {chat_id}: {e}")
        return False
