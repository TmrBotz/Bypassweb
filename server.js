// server.js - Universal Scraper Microservice (Render)
// Reusable "self-hosted ScraperAPI" — bypasses bot detection via server IP + browser-like headers.
// Usage: GET /fetch?url=<target-url>  →  returns raw HTML of that page

const express = require("express");
const app = express();
const PORT = process.env.PORT || 3000;

// ─── Config ───────────────────────────────────────────────────────────────────

// Simple API key protection (optional but recommended so randoms can't abuse your service)
const ACCESS_KEY = process.env.ACCESS_KEY || ""; // set this in Render env vars; leave empty to disable

function browserHeaders(refererUrl) {
  return {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": refererUrl || "https://google.com/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Windows"',
    "Cache-Control": "max-age=0",
  };
}

// ─── Core Fetch Logic (with redirect + retry handling) ───────────────────────

async function fetchPage(targetUrl, refererUrl) {
  // Step 1: manual redirect to discover real final domain (some sites 403 on
  // the alias domain but allow the resolved target — handling it ourselves
  // lets us set a correct Referer for the second hop)
  let res = await fetch(targetUrl, {
    headers: browserHeaders(refererUrl),
    redirect: "manual",
  });

  if (res.status >= 300 && res.status < 400) {
    const location = res.headers.get("location");
    if (location) {
      const resolvedUrl = new URL(location, targetUrl).toString();
      res = await fetch(resolvedUrl, {
        headers: browserHeaders(targetUrl),
        redirect: "follow",
      });
      if (!res.ok) {
        throw new Error(`Fetch failed after redirect: ${resolvedUrl} [${res.status}]`);
      }
      return { html: await res.text(), finalUrl: resolvedUrl };
    }
  }

  if (res.ok) {
    return { html: await res.text(), finalUrl: targetUrl };
  }

  // Step 2: one retry with auto-follow, in case manual redirect handling missed something
  const retryRes = await fetch(targetUrl, {
    headers: browserHeaders(refererUrl),
    redirect: "follow",
  });
  if (retryRes.ok) {
    return { html: await retryRes.text(), finalUrl: retryRes.url || targetUrl };
  }

  throw new Error(`Fetch failed: ${targetUrl} [${retryRes.status}]`);
}

// ─── Routes ───────────────────────────────────────────────────────────────────

app.get("/", (req, res) => {
  res.json({ status: "ok", message: "Universal scraper microservice running" });
});

app.get("/fetch", async (req, res) => {
  const { url: targetUrl, referer, key, raw } = req.query;

  if (ACCESS_KEY && key !== ACCESS_KEY) {
    return res.status(401).json({ error: "Unauthorized: invalid or missing key" });
  }

  if (!targetUrl) {
    return res.status(400).json({ error: "Missing 'url' parameter" });
  }

  try {
    const { html, finalUrl } = await fetchPage(targetUrl, referer);

    if (raw === "1" || raw === "true") {
      // Return raw HTML (like ScraperAPI does)
      res.set("Content-Type", "text/html; charset=utf-8");
      return res.status(200).send(html);
    }

    // Return JSON wrapper with metadata
    return res.status(200).json({ finalUrl, html });

  } catch (err) {
    return res.status(502).json({ error: "Fetch failed", detail: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`Universal scraper microservice listening on port ${PORT}`);
});
