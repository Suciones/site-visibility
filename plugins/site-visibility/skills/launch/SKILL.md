---
name: launch
description: Post-launch search visibility setup and submission. Covers Google Search Console (Domain property via DNS, sitemap submission, URL inspection), Bing Webmaster Tools (import from Search Console, sitemap), IndexNow pings, Google Business Profile, Bing Places and Apple Business Connect for local businesses, analytics, AI referral tracking and a monitoring routine. Use when a site has just gone live, moved to a new domain, or "isn't showing on Google, Bing or ChatGPT".
---

# Launch: get the site discovered

Search engines don't need to be told about a site, but registering it speeds up indexing a lot. It also gives you error reports and lets you control the sitemap.

Use `${CLAUDE_PLUGIN_ROOT}/references/search-engines.md` for step-by-step instructions for each console. If that variable is unset, the plugin root is two levels above this skill's base directory.

## Workflow

1. **Pre-flight:** run the audit against the live URL (`audit` skill) and fix every Crawlability failure first. Submitting a site that is noindexed, blocked or missing a sitemap wastes the first crawl.
2. **Collect facts:**
   - the live domain and preferred host
   - the DNS provider (Cloudflare, registrar, Vercel, etc.)
   - whether the user already has Search Console, Bing or analytics accounts
   - whether it's a local business (then the profile listings matter most)
3. **Walk through the checklist with the user.** The user signs in to every account themselves and approves every verification. You can:
   - open the console pages in the browser pane for them
   - give the exact DNS record to add
   - add verification meta tags or files to the codebase when they give you the code
   - check from the terminal that a DNS TXT record has propagated: `dig +short TXT example.com`
4. **Ping IndexNow (Bing, Yandex, Seznam, Naver):**
   1. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/generate.py" indexnow-key --out <public dir>`, then deploy.
   2. `generate.py indexnow --site-url https://… --key KEY --from-sitemap --dry-run` to review the URL list.
   3. Run it without `--dry-run` only after the user confirms. It sends their URLs to an external API.
   4. For ongoing use, suggest a post-deploy hook or CI step, or the host's built-in integration (Cloudflare Crawler Hints, the IndexNow plugin for WordPress).
5. **Give the user a status table:** each item marked done, waiting on the user, or not applicable, with what to check later.

## Checklist

| # | Item | Why |
|---|------|-----|
| 1 | Google Search Console: **Domain property** verified by DNS TXT | Covers http/https and all subdomains, and gives indexing, query and error data |
| 2 | Submit `sitemap.xml` in Search Console → Sitemaps | Faster discovery; lets you see the indexed vs submitted gap |
| 3 | URL Inspection → *Request indexing* for the homepage and 3–10 key pages | Gets the first crawl started |
| 4 | Bing Webmaster Tools: *Import from Google Search Console*, or verify by DNS/meta/XML file | Bing feeds Copilot, DuckDuckGo, Ecosia and Yahoo, and is used by several AI assistants |
| 5 | Submit the sitemap in Bing and enable IndexNow | Near-instant Bing updates |
| 6 | Analytics: GA4, Plausible, Fathom, Umami or Cloudflare. Link GA4 to Search Console | Measures search and AI referrals |
| 7 | Local business: Google Business Profile, Bing Places (can import from Google) and Apple Business Connect, with name, address, phone and hours matching the site | Map pack, local AI answers and the knowledge panel |
| 8 | Consistent profiles (LinkedIn, Instagram, Facebook, Crunchbase, directories) linking back, listed in `sameAs` | Entity confidence for Google and LLMs |
| 9 | Moved domain? 301 every old URL to its new URL, then use Search Console *Change of Address* | Keeps rankings |
| 10 | Optional: Yandex Webmaster (RU/TR/KZ markets), Naver (KR), Baidu (CN), Seznam (CZ) | Regional engines; IndexNow already covers Yandex, Seznam and Naver |

## What to expect

Tell the user these timelines:

- **Google:** first indexing usually takes days to a few weeks for a new domain. The favicon and site name in results can take weeks to update after changes.
- **Bing with IndexNow:** often within hours to days.
- **AI assistants:** ChatGPT, Claude and Perplexity search cite pages from their own crawls and partner indexes. They need crawler access, server-rendered content and clear entity information. Being in Bing and Google is a strong base.
- **Rankings** depend on content quality, relevance and links. Registration makes the site eligible; it doesn't make it rank.

## Monitoring

- **Week 1:** check Search Console → Pages (indexing) for errors, and Sitemaps status.
- **Monthly:**
  - Performance report (queries, CTR), Core Web Vitals and Enhancements (structured data errors)
  - Bing: the same reports
  - Re-run the audit with `--psi`
- **AI referrals:** in analytics, watch referrers such as `chatgpt.com`, `perplexity.ai`, `claude.ai`, `gemini.google.com`, `copilot.microsoft.com` and `chat.mistral.ai`.
- **AI answers:** periodically ask the assistants about the brand and category ("best X in Y") to see whether and how the site is cited.
- If the user wants this tracked, offer to set up a recurring audit (scheduled task or CI job using `audit.py --strict`).
