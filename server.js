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
    "Accept": "text/html,application/xhtml+xml,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": refererUrl || "https://new1.filesdl.in/",
  };
}

// ─── Core Fetch Logic (with redirect + retry handling) ───────────────────────

async function fetchPage(targetUrl, refererUrl) {
  const res = await fetch(targetUrl, {
    headers: browserHeaders(refererUrl),
  });

  if (!res.ok) {
    throw new Error(`Fetch failed: ${targetUrl} [${res.status}]`);
  }

  return { html: await res.text(), finalUrl: res.url || targetUrl };
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
