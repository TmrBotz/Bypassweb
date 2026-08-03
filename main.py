from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from bs4 import BeautifulSoup
import re
import asyncio
import random

app = FastAPI(title="FilesDL Scraper API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

def get_headers(url: str):
    from urllib.parse import urlparse
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Referer": origin,
        "Cache-Control": "max-age=0",
        "DNT": "1",
    }

class ScrapeRequest(BaseModel):
    url: str

class DownloadLink(BaseModel):
    label: str
    url: str

class ScrapeResponse(BaseModel):
    filename: str
    size: str
    date: str
    links: list[DownloadLink]

async def fetch_page(url: str) -> str:
    # Try with different strategies
    strategies = [
        {"follow_redirects": True, "timeout": 20},
        {"follow_redirects": True, "timeout": 30},
    ]
    
    last_error = None
    for strategy in strategies:
        try:
            await asyncio.sleep(random.uniform(0.5, 1.5))  # Human-like delay
            async with httpx.AsyncClient(
                **strategy,
                headers=get_headers(url),
                http2=False,
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 403:
                    # Try with slightly different headers
                    await asyncio.sleep(1)
                    h = get_headers(url)
                    h.pop("Sec-Fetch-User", None)
                    h.pop("Sec-Ch-Ua", None)
                    resp2 = await client.get(url, headers=h)
                    resp2.raise_for_status()
                    return resp2.text
                resp.raise_for_status()
                return resp.text
        except httpx.HTTPError as e:
            last_error = e
            continue
    
    raise last_error

def parse_links(html: str) -> ScrapeResponse:
    soup = BeautifulSoup(html, "html.parser")

    filename = ""
    title_tag = soup.find("title")
    if title_tag:
        filename = title_tag.get_text(strip=True)

    text = soup.get_text()
    size = ""
    date = ""
    size_match = re.search(r"Size[:\s]+([\d.]+ \w+)", text)
    date_match = re.search(r"Date[:\s]+([\d\-: ]+)", text)
    if size_match:
        size = size_match.group(1).strip()
    if date_match:
        date = date_match.group(1).strip()

    links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        label = a.get_text(strip=True) or "Download"
        if href.startswith("http") and href not in seen:
            if any(kw in href.lower() for kw in [
                "download", "cloud", "r2.dev", "gofile", "pixeldrain",
                "hubcloud", "gdflix", "bmf.", "fuckingfast", "filesdl", "fffast", "iwebp"
            ]):
                seen.add(href)
                links.append(DownloadLink(label=label, url=href))

    return ScrapeResponse(filename=filename, size=size, date=date, links=links)

@app.get("/")
async def root(url: str = None):
    if not url:
        return {"status": "ok", "message": "FilesDL Scraper API! Use /?url=YOUR_FILESDL_URL"}
    return await scrape_links(ScrapeRequest(url=url))

@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_links(request: ScrapeRequest):
    url = request.url.strip()
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")

    try:
        html = await fetch_page(url)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Site ne block kiya: {e.response.status_code}. Thodi der baad try karo.")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Page fetch error: {str(e)}")

    result = parse_links(html)

    if not result.links:
        raise HTTPException(status_code=404, detail="Koi download link nahi mila")

    return result
