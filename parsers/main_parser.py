import logging
from typing import Optional
from utils.config import SOURCES
from parsers.rss_parser import parse_rss
from parsers.html_parser import parse_html
from parsers.telegram_parser import parse_telegram

logger = logging.getLogger(__name__)

async def run_parsing(client: Optional[object] = None, pool=None):
    """
    Runs the parsing process for all sources defined in the config.
    Now only supports HTML, RSS, and telegram_web sources.
    
    Args:
        client: Kept for backward compatibility, not used anymore
        pool: Database connection pool
    """
    if not pool:
        logger.error("Database pool is required for parsing")
        return
        
    for source in SOURCES:
        try:
            logger.info(f"[PARSER] Processing source: {source.get('name')} (type: {source.get('type')})")
            
            if source['type'] == 'rss':
                await parse_rss(pool, source)
            elif source['type'] == 'html':
                await parse_html(pool, source)
            elif source['type'] == 'telegram_web':
                # We pass None as client since we don't need it anymore
                await parse_telegram(None, pool, source)
            else:
                logger.warning(f"[PARSER] Unsupported source type: {source.get('type')} for {source.get('name')}")
                
            logger.info(f"[PARSER] Finished processing source: {source.get('name')}")
            
        except Exception as e:
            logger.error(f"[PARSER] Error processing source {source.get('name')}: {e}", exc_info=True)
