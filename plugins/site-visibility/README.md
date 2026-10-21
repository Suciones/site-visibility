# site-visibility: a Claude Code plugin

This plugin checks and fixes everything a website needs for basic visibility in Google, Bing and AI assistants. Use it before launch (on a build folder or localhost) or on a live site.

| Skill | What it does |
|---|---|
| `/site-visibility:audit <url or folder>` | Runs about 90 checks across crawlability, on-page SEO, social cards, favicon, structured data, LLMO/AI crawler access, llms.txt, verification, analytics and speed. Writes an HTML report with a Google result preview, share-card previews and favicon previews. |
| `/site-visibility:fix` | Implements the fixes in your codebase using your framework's native features (Next.js, Astro, Nuxt, SvelteKit, Remix, Gatsby, SPA, Hugo, Jekyll, Eleventy, WordPress…), then re-audits. |
| `/site-visibility:launch` | Walks through post-launch setup: Google Search Console (DNS verification, sitemap, URL inspection), Bing Webmaster Tools, IndexNow, Google Business Profile, Bing Places, Apple Business Connect, analytics and monitoring. |

Claude also invokes these skills on its own when you ask things like "is my site ready for launch?", "check SEO", "why doesn't my link preview show?" or "add llms.txt".

## Install

From a local folder:

```bash
claude plugin marketplace add /path/to/site-visibility
```

```bash
claude plugin install site-visibility@site-visibility-tools
```

Or straight from GitHub:

```bash
claude plugin marketplace add Suciones/site-visibility
```

```bash
claude plugin install site-visibility@site-visibility-tools
```

Restart Claude Code after installing.

## Use the scripts directly

The scripts need only Python 3.8+ and have no dependencies. Pillow is optional, for `favicon.ico`.

```bash
python3 plugins/site-visibility/scripts/audit.py https://example.com --pages 20 --psi
```

```bash
python3 plugins/site-visibility/scripts/audit.py ./dist --site-url https://example.com --out report
```

```bash
python3 plugins/site-visibility/scripts/generate.py --help
```

The generators are `robots`, `sitemap`, `llms`, `favicons`, `head`, `indexnow-key` and `indexnow`.

For `--psi`, set `PSI_API_KEY` (a free Google Cloud key); the keyless quota is often exhausted.

In CI, `audit.py … --strict` exits 1 when any check fails.

## What's checked

- **Crawlability:**
  - 200 status, HTTPS and the http→https redirect
  - www/apex consolidation, redirect chains
  - noindex in meta tags and `X-Robots-Tag`
  - soft 404s
  - robots.txt: blocking, Sitemap line, CSS/JS access
  - XML sitemap: validity, host, http URLs, duplicates, lastmod, sampled URL health
- **On-page:** title length in pixels, description length, H1 and heading outline, lang, viewport, charset, canonical, alt text, mixed content, hreflang, duplicate titles and descriptions across pages, internal links
- **Social cards:**
  - og:title, og:description, og:url, og:type, og:site_name, twitter:card
  - og:image: fetchable, format, dimensions, ratio, file size, alt
- **Favicon:**
  - `<link rel=icon>`, `/favicon.ico`
  - Google's rule (square, multiple of 48px or SVG), robots access
  - apple-touch-icon, web manifest (192/512), theme-color
- **Structured data:** JSON-LD validity, WebSite name (Google site name), Organization/LocalBusiness/Person fields, sameAs, address
- **LLMO:**
  - text in server HTML (JS-rendering detection), semantic landmarks
  - About/contact signals, question headings, freshness, nosnippet/noai
  - llms.txt structure and links, llms-full.txt
  - robots.txt policy for 18 search and AI bots
  - live user-agent tests for CDN/WAF blocks
- **Engines:** Search Console verification (meta tag or DNS TXT), Bing verification (meta tag or BingSiteAuth.xml), other verifications, analytics detection, IndexNow
- **Performance:** response time, compression, HSTS, security headers, HTML size, render-blocking scripts, image dimensions, plus optional PageSpeed Insights (Lighthouse and real-user Core Web Vitals)

## License

MIT — see [LICENSE](LICENSE).
