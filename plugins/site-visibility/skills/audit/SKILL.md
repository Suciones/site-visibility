---
name: audit
description: Audit a website's search and AI visibility. Covers SEO, LLMO/GEO (AI answer engines), llms.txt, meta tags, Open Graph/X share cards, the favicon and how the site looks in Google results, robots.txt, XML sitemap, structured data, AI crawler access, Google Search Console and Bing verification, analytics and basic speed/security. Use before finishing or launching a website, after deploying, or when someone asks "is my site ready for Google/ChatGPT", "check my SEO", "why doesn't my favicon or link preview show", "audit visibility". Works on live URLs, localhost servers and static build folders.
---

# Site visibility audit

Goal: tell the user exactly what stops their site from being found, shown nicely and cited by Google, Bing and AI assistants, ranked by impact, with fixes for their stack.

## Tools

The audit script is in this plugin: `${CLAUDE_PLUGIN_ROOT}/scripts/audit.py`. If that variable is not set, it is `../../scripts/audit.py` relative to this skill's base directory. It needs Python 3.8+ and nothing else.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/audit.py" TARGET [--site-url https://prod-domain.com] [--pages 12] [--out DIR] [--psi] [--strict]
```

- `TARGET` can be a live URL (`https://example.com`), a local server (`http://localhost:4321`) or a static build folder (`./dist`). A folder is served on a temporary port.
- `--site-url` sets the production origin. Use it for local targets so absolute URLs (canonical, og:image, sitemap) are checked against the real domain and fetched from the local copy. If you leave it out, the script guesses it from the canonical tag.
- `--pages N` samples N more pages from the sitemap, or from homepage links if there is no sitemap.
- `--psi` adds Lighthouse and real-user Core Web Vitals from PageSpeed Insights. It only works on live sites and takes 30–60 s. The keyless quota is shared and often exhausted. If the result says "Quota exceeded", ask the user for a free API key (Google Cloud → PageSpeed Insights API) and export it as `PSI_API_KEY`.
- It writes `report.json` (every check plus raw data), `report.md` and `report.html` to `--out`. The HTML report has a Google result preview, share-card previews, favicon sizes and the crawler table.

## Workflow

### 1. Pick the target

- **The user gave a URL:** audit it as a live site.
- **You are in a website project before launch:**
  1. Detect the framework from `package.json` dependencies and config files (`next.config.*`, `astro.config.*`, `nuxt.config.*`, `svelte.config.*`, `gatsby-config.*`, `hugo.toml`, `_config.yml`, `.eleventy.js`, `wp-config.php`).
  2. Find the production URL. Look in Next `metadataBase`, Astro `site`, Nuxt `site.url`, env vars such as `NEXT_PUBLIC_SITE_URL`, `SITE_URL` or `PUBLIC_SITE_URL`, a `CNAME` file, `vercel.json`, `netlify.toml` and the README. If it isn't set anywhere, ask the user. A missing site URL is itself a finding, because absolute URLs will break.
  3. Audit the production build, not the dev server. Dev servers inject scripts and skip static generation.
     - Static output: build it (`npm run build`), then audit the folder (`out/`, `dist/`, `build/`, `public/` for Hugo, `_site/` for Jekyll/Eleventy).
     - SSR apps: build, start the production server in the background (`npm run start`, `astro preview`, `vite preview`, `node build`), then audit `http://localhost:PORT --site-url https://prod`.
- **The site is already deployed:** audit the live URL. If you also have the code, cross-check the source in step 3.

Write reports to a temporary folder, or to `.visibility-report/` in the project. In that case, add it to `.gitignore`.

### 2. Run the script and read the JSON

Read `report.json` rather than guessing from the console summary. `items[]` holds `category`, `status` (fail/warn/info/pass), `title`, `detail` and `fix`. `data` holds the robots.txt content, sitemap stats, AI bot table, social tags, icons, schema types, sampled pages and the SERP preview.

### 3. Check what the script can't see (when you have the source)

- **Dynamic routes:** blog posts, products and `[slug]` pages each need a unique title, description, canonical and og:image. Templates often hard-code the homepage values.
- **Environment leaks:** `noindex`, `Disallow: /` or `X-Robots-Tag` meant for preview/staging must be gated by environment so production stays indexable. Check that preview deployments are noindex.
- **Rendering:** look for content fetched in `useEffect`/`onMounted`, or pages that are fully `"use client"`, in a framework that could server-render them. AI crawlers mostly don't run JavaScript.
- **Sitemap source:** make sure it is generated at build time and includes dynamic routes, not a hand-written file that will go stale.
- **Internationalisation:** check `lang` per locale, hreflang pairs and translated titles and descriptions.
- **Redirects:** check `trailingSlash` consistency, www/apex redirects and old-URL redirects after a redesign.
- **Images:** check the alt text in components, and that `next/image` or similar outputs real dimensions.
- **Business facts:** the name, address and phone in structured data should match the visible footer and the Google Business Profile.

### 4. Report to the user

Keep the chat answer short and decisive.

1. Give the overall score and a one-line verdict, e.g. "Not launch-ready: Google can't index it yet" or "Solid; 4 polish items".
2. **Fix first:** list up to 8 items, all failures plus the high-impact warnings. For each, say what is wrong, why it matters in one clause, and the concrete fix for their framework. Use `${CLAUDE_PLUGIN_ROOT}/references/frameworks.md` for framework-specific fixes.
3. **Nice to have:** a short list.
4. Show the previews. Open `report.html` in the browser pane if one is available (serve the folder with `python3 -m http.server` if needed), or give the file path. Mention what the Google result and share cards will look like.
5. **After launch:** if the site is live and Search Console, Bing or IndexNow aren't set up, point to `/site-visibility:launch`.
6. Offer to implement the fixes with `/site-visibility:fix`.

Calibrate severity honestly:

- **Critical:** blocks indexing or discovery. Examples: noindex, `Disallow: /`, no server-rendered content, a 5xx robots.txt, no sitemap, sitemap URLs pointing at localhost, a broken canonical.
- **High:** visibly hurts results. Examples: missing or duplicate titles or descriptions, no og:image, a favicon that isn't a multiple of 48px, no WebSite/Organization schema, AI search bots blocked by robots.txt or a CDN.
- **Medium/low:** manifest, theme-color, HSTS, og:image:alt, lastmod coverage, question-style headings.
- **llms.txt** is cheap and worth adding, but it is a proposal, and support from AI crawlers is uneven. Don't present it as a ranking factor.
- **Never claim** Search Console or Bing verification is missing for certain. HTML-file, GA and GTM verification can't be detected from outside. Say "not detected".

### 5. Re-audit after fixes

After changes, rebuild, re-run with the same arguments, and show the before and after scores.

## Notes

- Without `--site-url`, a local audit can't check that URLs use the production host. Pass it whenever you know the domain.
- The bot user-agent test (live mode) sends requests that pretend to be GPTBot, ClaudeBot and others. CDNs that verify bot IP addresses may block those test requests while letting the real bots through. Report a block as "check your CDN/WAF bot settings", not as a confirmed block.
- In CI, `--strict` exits 1 when any check fails.
- The full checklist with thresholds and reasoning is in `${CLAUDE_PLUGIN_ROOT}/references/checklist.md`. LLMO guidance is in `references/llmo.md`.
