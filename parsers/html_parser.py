import httpx
from bs4 import BeautifulSoup
import asyncio
from datetime import datetime
from urllib.parse import urljoin
from database.db_manager import save_article


async def parse_single_article_content(url: str):
    """
    Scrapes a single article page to get its title and content.
    This is used for manually adding articles.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            title_element = soup.find('title')
            title = title_element.text.strip() if title_element else ''

            body = soup.find('body')
            if body:
                for script_or_style in body(['script', 'style']):
                    script_or_style.decompose()
                content = body.get_text(separator='\n', strip=True)
            else:
                content = ''

            return title, content
    except Exception as e:
        print(f"An unexpected error occurred while parsing article {url}: {e}")
        return "", ""


async def parse_html(pool, source):
    """
    Parses an HTML page to find articles, then scrapes and adds them to the database.
    """
    print(f"Parsing HTML source: {source['name']}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(source['url'])
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Handle both old and new selector formats
            selectors = source.get('selectors', source)
            
            items = soup.select(selectors.get('article', selectors.get('item', 'article.post-box')))
            print(f"Found {len(items)} items")

            for item in items:
                try:
                    title_elem = item.select_one(selectors.get('title'))
                    if not title_elem:
                        continue

                    link_elem = item.select_one(selectors.get('link'))
                    if not link_elem or not link_elem.get('href'):
                        continue

                    link = urljoin(source['url'], link_elem['href'])
                    article_response = await client.get(link)
                    article_response.raise_for_status()
                    article_soup = BeautifulSoup(article_response.text, 'html.parser')

                    title = title_elem.text.strip()
                    content = article_soup.get_text(separator='\n', strip=True)

                    await save_article(
                        pool,
                        title,
                        link,
                        content,
                        source['name'],
                        source.get('default_tags', source.get('tags', []))
                    )
                    print(f"  > Added article: {title}")
                    await asyncio.sleep(1)  # Be polite
                except httpx.HTTPStatusError as e:
                    print(f"Error fetching article: {e}")
                except Exception as e:
                    print(f"Error parsing article: {e}")

    except httpx.RequestError as e:
        print(f"Error requesting {source['url']}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred while parsing {source['name']}: {e}")
