"""
CF Bypass Scraper API — Free Tier Edition
cloudscraper only, Render Free compatible
"""

import asyncio
import json
import logging
import random
import re
import time
from typing import Any, Optional

import cloudscraper
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

BROWSER_PROFILES = [
    {"browser": "chrome",  "platform": "windows", "mobile": False},
    {"browser": "chrome",  "platform": "linux",   "mobile": False},
    {"browser": "firefox", "platform": "windows", "mobile": False},
    {"browser": "firefox", "platform": "linux",   "mobile": False},
]

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

app = FastAPI(
    title="CF Bypass Scraper API",
    description="Cloudflare bypass via cloudscraper — Render Free compatible",
    version="2.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ─────────────────────────────────────
class ScrapeRequest(BaseModel):
    url: str
    method: str = "GET"
    post_data: Optional[dict] = None
    headers: Optional[dict] = None
    cookies: Optional[dict] = None
    extract_selector: Optional[str] = None
    return_html: bool = True
    return_text: bool = False
    return_json: bool = False
    timeout: int = 30


class BatchRequest(BaseModel):
    urls: list
    extract_selector: Optional[str] = None
    return_html: bool = True
    return_text: bool = False
    timeout: int = 30
    concurrency: int = 3


# ── Core Scraper ───────────────────────────────
def _do_scrape(req: ScrapeRequest) -> dict:
    profile = random.choice(BROWSER_PROFILES)
    scraper = cloudscraper.create_scraper(browser=profile, delay=5)

    hdrs = {**DEFAULT_HEADERS}
    if req.headers:
        hdrs.update(req.headers)
    scraper.headers.update(hdrs)

    if req.cookies:
        scraper.cookies.update(req.cookies)

    try:
        if req.method.upper() == "POST":
            resp = scraper.post(req.url, json=req.post_data, timeout=req.timeout)
        else:
            resp = scraper.get(req.url, timeout=req.timeout)

        if resp.status_code == 403 and "cloudflare" in resp.text.lower():
            return {"success": False, "error": "CF 403 blocked", "status_code": 403}
        if resp.status_code == 503 and "Just a moment" in resp.text:
            return {"success": False, "error": "CF 503 IUAM — bypass failed", "status_code": 503}

        html = resp.text
        result: dict = {
            "success": True,
            "status_code": resp.status_code,
            "html": html,
            "cookies": dict(scraper.cookies),
        }

        if req.extract_selector:
            try:
                soup = BeautifulSoup(html, "html.parser")
                elems = soup.select(req.extract_selector)
                result["extracted"] = "\n".join(e.get_text(strip=True) for e in elems) if elems else None
            except Exception as e:
                result["extracted"] = None

        if req.return_text:
            try:
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(["script", "style", "noscript", "meta", "link"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
                result["text"] = re.sub(r"\n{3,}", "\n\n", text)
            except Exception:
                result["text"] = None

        if req.return_json:
            try:
                result["json_data"] = json.loads(html)
            except Exception:
                try:
                    m = re.search(r"({[\s\S]*}|\[[\s\S]*\])", html)
                    result["json_data"] = json.loads(m.group(0)) if m else None
                except Exception:
                    result["json_data"] = None

        if not req.return_html:
            result["html"] = None

        logger.info(f"✅ {resp.status_code} | {len(html)} bytes | {req.url}")
        return result

    except cloudscraper.exceptions.CloudflareChallengeError as e:
        return {"success": False, "error": f"CF challenge unsolvable: {e}"}
    except requests.exceptions.Timeout:
        return {"success": False, "error": f"Timeout after {req.timeout}s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def scrape_async(req: ScrapeRequest) -> dict:
    return await asyncio.to_thread(_do_scrape, req)


# ── FilesdL Parser ─────────────────────────────
def parse_filesdl(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    body_text = soup.get_text(separator="\n", strip=True)

    # Filename — first meaningful line or <title>
    filename = None
    title_tag = soup.find("title")
    if title_tag:
        filename = title_tag.get_text(strip=True)

    # Size
    size = None
    size_match = re.search(r"Size[:\s]+([0-9.,]+\s*(?:MB|GB|KB))", body_text, re.IGNORECASE)
    if size_match:
        size = size_match.group(1).strip()

    # Date
    date = None
    date_match = re.search(r"Date[:\s]+(\d{4}-\d{2}-\d{2}[^\n]*)", body_text)
    if date_match:
        date = date_match.group(1).strip()

    # All links with labels
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        label = a.get_text(strip=True)
        if href.startswith("http") and label:
            links.append({"label": label, "url": href})

    # Categorize known link types
    categorized = {}
    for link in links:
        u = link["url"].lower()
        l = link["label"].lower()
        if "r2.dev" in u or "cloud direct" in l:
            categorized["cloud_direct"] = link["url"]
        elif "fffast.filesdl" in u or "10gbps" in l or "direct download" in l:
            categorized["direct_download"] = link["url"]
        elif "pixeldrain" in u or "pixeldrain" in l:
            categorized["pixeldrain"] = link["url"]
        elif "hubcloud" in u or "hubcloud" in l:
            categorized["hubcloud"] = link["url"]
        elif "gdflix" in u or "gdflix" in l:
            categorized["gdflix"] = link["url"]
        elif "gofile" in u or "gofile" in l:
            categorized["gofile"] = link["url"]
        elif "fuckingfast" in u or "buzz" in l:
            categorized["buzz"] = link["url"]
        elif "bmf.filesdl" in u or "slowcloud" in l:
            categorized["slowcloud"] = link["url"]

    return {
        "success": True,
        "source_url": url,
        "filename": filename,
        "size": size,
        "date": date,
        "links": categorized,
        "all_links": links,
    }


# ── Endpoints ──────────────────────────────────
@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "CF Bypass Scraper API (Free Tier)",
        "version": "2.3.0",
        "engine": "cloudscraper",
        "endpoints": {
            "filesdl":      "GET  /filesdl?url=https://new1.filesdl.in/cloud/xxx",
            "browser_test": "GET  /target?url=https://site.com",
            "scrape":       "POST /scrape",
            "batch":        "POST /scrape/batch",
            "health":       "GET  /health",
        },
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": int(time.time())}


# ── /filesdl — dedicated filesdl parser ────────
@app.get("/filesdl")
async def filesdl_get(url: str, timeout: int = 30):
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="url must start with http:// or https://")

    start = time.time()
    req = ScrapeRequest(url=url, return_html=True, timeout=timeout)
    result = await scrape_async(req)

    if not result.get("success"):
        return JSONResponse(content={
            "success": False,
            "error": result.get("error"),
            "elapsed_ms": int((time.time() - start) * 1000),
        })

    parsed = parse_filesdl(result["html"], url)
    parsed["elapsed_ms"] = int((time.time() - start) * 1000)
    return JSONResponse(content=parsed)


# ── /target — browser friendly generic ─────────
@app.get("/target")
async def target_get(
    url: str,
    extract: Optional[str] = None,
    text: bool = False,
    timeout: int = 30,
):
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="url must start with http:// or https://")

    start = time.time()
    req = ScrapeRequest(
        url=url,
        extract_selector=extract,
        return_html=True,
        return_text=text,
        timeout=timeout,
    )
    result = await scrape_async(req)
    result["elapsed_ms"] = int((time.time() - start) * 1000)
    result["url"] = url

    if extract and result.get("extracted") is not None:
        result.pop("html", None)
    elif text and result.get("text"):
        result.pop("html", None)

    return JSONResponse(content=result)


@app.post("/scrape")
async def scrape(req: ScrapeRequest):
    start = time.time()
    result = await scrape_async(req)
    result["elapsed_ms"] = int((time.time() - start) * 1000)
    result["url"] = req.url
    return JSONResponse(content=result)


@app.post("/scrape/batch")
async def batch_scrape(req: BatchRequest):
    sem = asyncio.Semaphore(req.concurrency)

    async def one(url: str):
        async with sem:
            r = ScrapeRequest(
                url=url,
                extract_selector=req.extract_selector,
                return_html=req.return_html,
                return_text=req.return_text,
                timeout=req.timeout,
            )
            start = time.time()
            res = await scrape_async(r)
            res["elapsed_ms"] = int((time.time() - start) * 1000)
            res["url"] = url
            return res

    results = await asyncio.gather(*[one(u) for u in req.urls])
    return {
        "total":   len(req.urls),
        "success": sum(1 for r in results if r.get("success")),
        "failed":  sum(1 for r in results if not r.get("success")),
        "results": results,
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
