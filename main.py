from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from bs4 import BeautifulSoup
import re

app = FastAPI(title="FilesDL Scraper API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://new1.filesdl.in/",
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

@app.get("/")
def root():
    return {"status": "ok", "message": "FilesDL Scraper API is running!"}

@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_links(request: ScrapeRequest):
    url = request.url.strip()

    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=HEADERS) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Page fetch error: {str(e)}")

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract filename
    filename = ""
    title_tag = soup.find("title")
    if title_tag:
        filename = title_tag.get_text(strip=True)

    # Extract size and date
    size = ""
    date = ""
    text = soup.get_text()
    size_match = re.search(r"Size[:\s]+([\d.]+ \w+)", text)
    date_match = re.search(r"Date[:\s]+([\d\-: ]+)", text)
    if size_match:
        size = size_match.group(1).strip()
    if date_match:
        date = date_match.group(1).strip()

    # Extract all download links
    links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        label = a.get_text(strip=True) or "Download"

        # Filter only download/cloud links
        if href.startswith("http") and href not in seen:
            # Skip same-site navigation links
            if any(kw in href.lower() for kw in [
                "download", "cloud", "r2.dev", "gofile", "pixeldrain",
                "hubcloud", "gdflix", "bmf.", "fuckingfast", "filesdl", "fffast"
            ]):
                seen.add(href)
                links.append(DownloadLink(label=label, url=href))

    if not links:
        raise HTTPException(status_code=404, detail="Koi download link nahi mila")

    return ScrapeResponse(
        filename=filename,
        size=size,
        date=date,
        links=links
    )
