# Visibility checklist

The **Auto** column says whether `audit.py` checks the item (✓), checks it only partly (◐), or leaves it to a manual review (–).

## 1. Crawlability & indexing

| Check | Target | Auto |
|---|---|---|
| Homepage returns 200, `text/html` | — | ✓ |
| HTTPS with valid certificate | http:// → https:// by a single 301/308 | ✓ |
| One canonical host | www ↔ apex: one 301s to the other | ✓ |
| Redirect chains | ≤1 hop, permanent | ✓ |
| No `noindex` in production | meta robots and the `X-Robots-Tag` header | ✓ |
| Unknown URLs return 404/410 | No soft 404s (SPA fallbacks returning 200) | ✓ |
| robots.txt | Exists, 200 (a 5xx makes Google treat it as disallow-all), doesn't block `/`, CSS or JS, has an absolute `Sitemap:` line | ✓ |
| XML sitemap | Valid XML, ≤50,000 URLs / 50 MB per file (use an index above that), absolute production URLs, only 200 + indexable + self-canonical URLs, `lastmod` that reflects real changes | ✓ |
| Sitemap URLs on the production host | No localhost, staging or `*.vercel.app` URLs | ✓ |
| Sampled pages healthy | 200, not redirected, self-canonical, indexable | ✓ |
| Internal linking | Every important page reachable by `<a href>` within ~3 clicks | ◐ |
| Preview/staging deployments noindexed | Env-gated | – |

## 2. On-page SEO (per page)

| Check | Target | Auto |
|---|---|---|
| `<title>` | Unique, ~50–60 chars, ≤600px (Arial 20px), topic first, brand last | ✓ |
| Meta description | Unique, 120–160 chars; Google rewrites it often, but social cards and AI tools reuse it | ✓ |
| One `<h1>` and a logical H2/H3 outline | — | ✓ |
| `<html lang>`, `<meta charset>`, viewport | Viewport required for mobile-first indexing | ✓ |
| Canonical | One, absolute, self-referencing unless deliberately pointing elsewhere | ✓ |
| Image `alt` | Meaningful images described; decorative images use `alt=""` | ✓ |
| Mixed content | None | ✓ |
| hreflang (multilingual) | Absolute URLs, reciprocal, includes self and `x-default` | ◐ |
| Clean URLs | Lowercase, hyphens, readable, stable | – |
| Content | Matches search intent, original, enough depth, clear headings | – |

## 3. Social share cards

| Check | Target | Auto |
|---|---|---|
| `og:title`, `og:description`, `og:url` (= canonical), `og:type`, `og:site_name` | — | ✓ |
| `og:image` | Absolute https URL, 1200×630 (1.91:1), PNG/JPG, <~600 KB (hard limits: 5 MB on X, 8 MB on Facebook), not SVG | ✓ |
| `og:image:width`, `:height`, `:alt` | Width and height let the first share render immediately | ✓ |
| `twitter:card` | `summary_large_image` (X falls back to og:* for title, description and image) | ✓ |
| `og:locale` | e.g. `en_US`, `ro_RO` | – |
| Per-page images for articles and products | — | – |

To refresh the platforms' cached previews, use the Facebook Sharing Debugger or LinkedIn Post Inspector. On X, the card refreshes on its own after about a week; there's no tool.

## 4. Favicon & app icons

| Check | Target | Auto |
|---|---|---|
| `<link rel="icon">` on the homepage | Google requirement | ✓ |
| Google-compatible favicon | Square, size a multiple of 48px (48, 96, 144, 192…) or SVG; stable URL; crawlable by Googlebot and Googlebot-Image | ✓ |
| `/favicon.ico` at the root | 16/32/48 inside; the fallback browsers and other tools request | ✓ |
| `apple-touch-icon` | 180×180 PNG, solid background | ✓ |
| Web manifest | name, short_name, 192 and 512 icons, theme_color | ✓ |
| `theme-color` meta | — | ✓ |

## 5. Structured data (JSON-LD)

| Check | Target | Auto |
|---|---|---|
| Valid JSON, `@context: https://schema.org` | — | ✓ |
| `WebSite` on the homepage | `name`, `alternateName`, `url`; Google uses it for the site name in results | ✓ |
| `Organization` / `LocalBusiness` / `Person` | name, url, logo (≥112px, crawlable), sameAs; for local businesses also address, geo, telephone and openingHours | ✓ |
| Page types | `BreadcrumbList`, `Article`/`BlogPosting`, `Product` + `Offer`, `Service`, `Event`, `FAQPage`, `Recipe`… as relevant | ◐ |
| Matches visible content | No fake reviews or ratings | – |

## 6. AI / LLM visibility (LLMO, GEO, AEO)

| Check | Target | Auto |
|---|---|---|
| Content in server HTML | ≥250 words of real text on key pages without running JavaScript | ✓ |
| AI search/user bots allowed in robots.txt | OAI-SearchBot, ChatGPT-User, Claude-SearchBot, Claude-User, PerplexityBot, Perplexity-User, DuckAssistBot, Applebot, Bingbot, Googlebot | ✓ |
| Training bots | A business decision: GPTBot, ClaudeBot, Google-Extended, Applebot-Extended, CCBot, Meta-ExternalAgent, Bytespider | ✓ |
| CDN/WAF doesn't block them | Cloudflare AI Crawl Control / bot fight settings | ◐ |
| `/llms.txt` | H1 name, `>` summary, `##` sections of `- [Title](url): note`, working links, served as text | ✓ |
| `/llms-full.txt` | Optional full-text Markdown | ✓ |
| Semantic HTML | `<main>`, `<article>`, `<nav>`, `<header>`, `<footer>` | ✓ |
| Entity clarity | About page, contact details, consistent name/address/phone, Organization with sameAs | ✓ |
| Answerable content | Question headings with direct answers, FAQs, comparisons, concrete numbers, sources | ◐ |
| Freshness | datePublished/dateModified and visible "Updated" dates | ◐ |
| No `nosnippet` / `max-snippet:0` | These also remove the content from Google AI Overviews | ✓ |

## 7. Search engines & verification

| Check | Target | Auto |
|---|---|---|
| Google Search Console | Domain property (DNS TXT) | ◐ (meta tag or DNS TXT only) |
| Bing Webmaster Tools | Imported from GSC or verified | ◐ (meta tag or BingSiteAuth.xml) |
| Sitemap submitted to both | — | – |
| IndexNow key and pings | — | – |
| Analytics installed | GA4, Plausible, Fathom, Umami, Cloudflare… | ✓ |
| Local listings | Google Business Profile, Bing Places, Apple Business Connect | – |

## 8. Performance & security basics

| Check | Target | Auto |
|---|---|---|
| Server response | <0.8s TTFB | ✓ |
| Compression | Brotli or gzip | ✓ |
| HSTS | `max-age` ≥ 1 year | ✓ |
| HTML size | <500 KB | ✓ |
| Render-blocking head scripts | ≤2 | ✓ |
| Image width/height set | Avoids CLS | ✓ |
| Core Web Vitals (p75) | LCP ≤2.5s, INP ≤200ms, CLS ≤0.1 (`--psi`) | ✓ |
| Modern images | AVIF/WebP, responsive `srcset`, lazy-load below the fold | – |
| Security headers | `X-Content-Type-Options`, `Referrer-Policy`, CSP | ◐ |
