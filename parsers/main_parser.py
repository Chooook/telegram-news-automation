import logging
from utils.config import SOURCES
from parsers.rss_parser import parse_rss
from parsers.html_parser import parse_html
from parsers.telegram_parser import parse_telegram

logger = logging.getLogger(__name__)

async def run_parsing(client, pool):
    """
    Runs the parsing process for all sources defined in the config.
    Now only supports HTML, RSS, and telegram_web sources.
    """
    for source in SOURCES:
        try:
            if source['type'] == 'rss':
                logger.info(f"[PARSER] Processing RSS source: {source['name']}")
                await parse_rss(pool, source)
            elif source['type'] == 'html':
                logger.info(f"[PARSER] Processing HTML source: {source['name']}")
                await parse_html(pool, source)
            elif source['type'] == 'telegram_web':
                logger.info(f"[PARSER] Processing Telegram web source: {source['name']}")
                await parse_telegram(client, pool, source)
            else:
                logger.warning(f"[PARSER] Unsupported source type: {source.get('type')} for {source.get('name')}")
        except Exception as e:
            logger.error(f"[PARSER] Error processing source {source.get('name')}: {e}", exc_info=True)
