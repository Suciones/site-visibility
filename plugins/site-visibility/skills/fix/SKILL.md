---
name: fix
description: Implement search and AI visibility fixes in a website codebase. Covers titles, meta descriptions, canonical, lang/hreflang, Open Graph and X cards with a 1200×630 og:image, the favicon set and web manifest, robots.txt with an AI crawler policy, the XML sitemap, llms.txt, JSON-LD (Organization/LocalBusiness/WebSite/Breadcrumb/Article/FAQ), server-rendering for AI crawlers and real 404s. Use after a visibility audit or when asked to "make the site SEO-ready", "add llms.txt / sitemap / favicon / OG image / schema", or "prepare the site for Google and ChatGPT". Framework-aware: Next.js, Astro, Nuxt, SvelteKit, Remix/React Router, Gatsby, Vite/React SPA, Hugo, Jekyll, Eleventy, WordPress and plain HTML.
---

# Fix site visibility

Make the changes in the user's codebase, prefer framework-native mechanisms so everything stays correct as the site grows, then prove it with a re-audit.

Plugin files (if `${CLAUDE_PLUGIN_ROOT}` is unset, the plugin root is two levels above this skill's base directory):

- `scripts/audit.py`: the audit. See the `audit` skill.
- `scripts/generate.py`: generators.
  - `robots`, `sitemap TARGET`, `llms TARGET`: crawl-based drafts.
  - `favicons SOURCE`: the full icon set plus manifest.
  - `head`: `<head>` tags plus JSON-LD.
  - `indexnow-key`, `indexnow`.
  - Run `python3 generate.py <cmd> -h` for options.
- `references/frameworks.md`: where each item lives in each framework. Read the section for this project's stack before editing.
- `references/llmo.md`: how to write for AI answer engines.

## 1. Gather inputs

- **Findings:** use `report.json` from a recent audit. If there isn't one, run the audit first (see the `audit` skill).
- **Framework and rendering mode:** SSG, SSR or SPA. Also the hosting (Vercel, Netlify, Cloudflare, Apache/Nginx, WordPress host), because it decides redirects, headers and the 404 behaviour.
- **Facts you must not invent.** Read them from the site content and config first, and ask the user only for what's missing (one compact question):
  - production URL and preferred host (www or apex)
  - brand name, a one-sentence description and the main language(s)
  - logo or icon source (SVG, or a PNG ≥512px)
  - social and profile URLs for `sameAs`
  - for a local business: legal name, address, phone, opening hours and Google Business Profile URL
  - AI training crawler policy: allow (default, more brand exposure) or block training while still allowing AI search crawlers
  - verification codes for Search Console or Bing, if they want meta-tag verification (DNS is better; see the `launch` skill)

## 2. Implement in priority order

1. **Indexing blockers:** remove production `noindex`, `Disallow: /` and the `X-Robots-Tag` header. Gate them to preview environments with an env check, e.g. `VERCEL_ENV !== 'production'`. Make unknown routes return a real 404.
2. **Server-rendered content:** if the raw HTML has little text, switch the affected pages to SSG or SSR (framework option), or add prerendering for SPAs. This matters most for AI crawlers.
3. **Per-page metadata in the shared layout or template, including dynamic routes:**
   - `<title>`: 50–60 characters, main topic first, brand last (`Topic – Brand`).
   - Meta description: 120–160 characters, value and a reason to click, written in the page language.
   - Absolute canonical, `<html lang>`, viewport and charset.
   - Every page gets a unique title and description. Derive them from page data (post title or excerpt, product name), not from hard-coded strings.
4. **Social cards:**
   - Tags: `og:title`, `og:description`, `og:url` (= canonical), `og:type`, `og:site_name`, `og:locale`, `og:image` plus `:width`, `:height` and `:alt`, and `twitter:card=summary_large_image`.
   - **og:image:** 1200×630 PNG or JPG, under ~600 KB, absolute https URL, with key text kept inside the central safe area.
   - If none exists, create one on brand. Use the framework's generator (e.g. Next `opengraph-image.tsx`, Astro/Satori), or build an HTML template and screenshot it at 1200×630 with Playwright or headless Chrome. Per-post images for blogs are a plus.
5. **Favicon set:** run `generate.py favicons <logo> --out <public dir> --name "<Brand>" --theme-color "#hex"`. It produces `favicon.ico` (16/32/48), `favicon-96x96.png`, `apple-touch-icon.png` (180, solid background), 192/512 manifest icons and `site.webmanifest`. Add `icon.svg` if the logo is SVG.
   - Link the files in `<head>`, or use framework file conventions (Next `app/icon.*`).
   - Google needs a square favicon whose size is a multiple of 48px, at a stable URL that is crawlable from the homepage.
6. **robots.txt:** use the framework's route if it has one (Next `app/robots.ts`, Nuxt robots module, Astro integration). Otherwise generate a static file with `generate.py robots --site-url … [--block-training] [--disallow /admin/ …]`.
   - Always allow Googlebot, Bingbot and the AI search/user bots.
   - Always include the absolute `Sitemap:` line.
7. **XML sitemap:** generated at build time from the routes, including dynamic ones. Use absolute production URLs, include `lastmod`, and leave out noindex, redirected and canonicalised URLs. Use `generate.py sitemap` only for plain static sites with no plugin option.
8. **Structured data (JSON-LD)** in the root layout:
   - `WebSite` (name, alternateName, url): this drives the site name Google shows.
   - `Organization`, or `LocalBusiness` subtype or `Person`: name, url, logo, sameAs, contactPoint; for local businesses also address, geo, telephone and openingHoursSpecification.
   - Page-level types where they apply: `BreadcrumbList`, `Article`/`BlogPosting` (author, datePublished, dateModified, image), `Product`/`Offer`, `FAQPage` (Google only shows FAQ rich results for some authoritative sites, but the markup still helps machines), `Service`, `Event`.
   - Keep it consistent with the visible content.
9. **llms.txt:**
   - Draft it from the built site with `generate.py llms <build dir or URL> --site-url … --name "…" --summary "…"`.
   - Then curate it by hand. Order sections by importance, rewrite link notes as one-line factual descriptions, drop thin or legal pages (or move them to `## Optional`), and add a short paragraph with key facts: what you do, for whom, where, and pricing model or contact.
   - Serve it as `text/plain` or `text/markdown` at `/llms.txt`. Prefer a build-time route that regenerates from content (Next route handler, Astro endpoint). Otherwise put a static file in `public/`.
   - Add `llms-full.txt` (`--full`) for docs or product sites where a single full-text file is useful.
10. **On-page LLMO quick wins** (only with the user's agreement on copy):
    - a clear "what we do / who for / where" paragraph near the top
    - an About page and visible contact details
    - an FAQ section with direct answers
    - "Updated on" dates on articles
    - descriptive alt text
    - `<main>`, `<nav>`, `<footer>` landmarks
    - See `references/llmo.md`.
11. **Hosting:**
    - http→https and www/apex as single 301 redirects
    - HSTS
    - Brotli/gzip compression
    - long-cache headers for hashed assets
    - Check CDN bot settings: Cloudflare's AI crawler blocking can silently block AI search bots.
12. **Verification and analytics:**
    - Add Search Console/Bing meta tags only if the user gives you codes. DNS verification needs no code change.
    - Add privacy-friendly analytics if missing and the user wants it. Respect cookie-consent requirements in the EU.

## 3. Verify

- Rebuild, re-run the audit with the same target and `--site-url`, and show the before and after scores plus anything left.
- Open `report.html` to show the new Google preview and share card.
- For live sites, give these links:
  - Rich Results Test: `https://search.google.com/test/rich-results?url=…`
  - Schema validator: `https://validator.schema.org/`
  - LinkedIn Post Inspector: `https://www.linkedin.com/post-inspector/`
  - Facebook Sharing Debugger: `https://developers.facebook.com/tools/debug/`
  - These also force the share cache to refresh.

## Rules

- Don't invent business facts, reviews, ratings or addresses for schema. `AggregateRating` must reflect real, on-page reviews.
- Don't add `meta keywords`, hidden text or keyword-stuffed alt text. They don't help and can hurt.
- Keep changes in the project's existing style and file conventions. Don't add new dependencies when a built-in framework feature exists.
- Ask before touching DNS, hosting dashboards, or anything outside the repository.
