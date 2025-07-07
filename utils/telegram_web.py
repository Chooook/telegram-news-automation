import asyncio

import httpx
import logging
from typing import Optional
from utils.config import BOT_TOKEN

logger = logging.getLogger(__name__)

async def get_chat_info(chat_id: str) -> Optional[dict]:
    """
    Get information about a chat/channel.

    Args:
        chat_id: The chat ID or username with @

    Returns:
        dict: Chat information or None if error
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChat"

    # Ensure chat_id has @ prefix for channels
    if not chat_id.startswith('@') and not chat_id.startswith('-100'):
        chat_id = f"@{chat_id}"

    payload = {'chat_id': chat_id}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()['result']
    except Exception as e:
        logger.error(f"Error getting chat info for {chat_id}: {e}")
        return None

async def send_web_message(
        chat_id: str, text: str, parse_mode: str = 'HTML',
        disable_web_page_preview: bool = False, retry: bool = False) -> bool:
    """
    Send a message to a chat using Telegram Bot API via web.

    Args:
        chat_id: The chat ID or username with @
        text: The message text
        parse_mode: 'HTML' or 'Markdown'
        disable_web_page_preview: Whether to disable link previews
        retry: Whether to retry sending the message

    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    # Ensure chat_id has @ prefix for channels
    if not chat_id.startswith('@') and not chat_id.startswith('-100'):
        chat_id = f"@{chat_id}"

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
            logger.info(f"Message sent successfully to {chat_id}")
            await asyncio.sleep(5)
            return True
    except Exception as e:
        logger.error(f"Error sending message to {chat_id}: {e}")
        await asyncio.sleep(5)
        if not retry:
            await send_web_message(chat_id, text, parse_mode,
                                   disable_web_page_preview, True)
        return False
