# Search engine & listing setup: step by step

The user signs in to each service and approves each verification. Claude can open the pages, prepare DNS records, add meta tags or files to the code, and check propagation.

## Google Search Console — https://search.google.com/search-console

1. **Add property → Domain** and enter `example.com`, with no protocol and no www. A Domain property covers every protocol and subdomain.
2. Google shows a TXT record: `google-site-verification=…`.
   1. Add it at the DNS provider: host `@`, type `TXT`.
   2. Check it with `dig +short TXT example.com`. Propagation takes minutes to a few hours.
   3. Click **Verify**.
3. If DNS isn't possible, add a **URL-prefix** property (`https://example.com/`) and verify with one of:
   - the HTML file
   - `<meta name="google-site-verification" content="…">`
   - Google Analytics or Tag Manager
4. **Sitemaps:** submit the full URL, e.g. `https://example.com/sitemap.xml` or `sitemap-index.xml`. Status should become *Success*. "Couldn't fetch" right after submitting is normal; check again later.
5. **URL Inspection:** inspect the homepage → *Request indexing*. Repeat for the key pages; there is a small daily quota. Use *Test live URL* → *View tested page* to see Google's rendered HTML and screenshot. This is useful for JS sites.
6. **Settings → Users:** add teammates. **Links:** associate GA4.
7. **Check after a few days:**
   - **Pages:** "Indexed" vs "Not indexed" reasons (Crawled – currently not indexed, Duplicate without user-selected canonical, Excluded by noindex).
   - **Enhancements:** structured data.
   - **Core Web Vitals**, and **HTTPS**.

Google's sitemap "ping" endpoint is deprecated. Submit sitemaps in Search Console and through robots.txt.

## Bing Webmaster Tools — https://www.bing.com/webmasters

1. Sign in with a Microsoft, Google or Facebook account.
2. **Import from Google Search Console.** This is the fastest route: it imports verified sites and sitemaps.
3. Or add the site manually and verify with one of:
   - an XML file `BingSiteAuth.xml` at the root
   - `<meta name="msvalidate.01" content="…">`
   - a DNS CNAME record
4. **Sitemaps:** submit the sitemap URL.
5. **IndexNow:** enable it in the IndexNow section, or use your own key (below).
6. **URL Submission** is available for urgent pages.
7. Review **Site Explorer**, **Search Performance** and **Recommendations** (SEO issues).

Bing's index powers Bing, Copilot, DuckDuckGo, Ecosia and Yahoo, and is used by various AI assistants.

## IndexNow — https://www.indexnow.org

The protocol is shared by Bing, Yandex, Seznam, Naver and others. Google does not use it.

1. Generate a key: `generate.py indexnow-key --out public/`. This writes `public/<key>.txt` containing the key.
2. Deploy, then confirm `https://example.com/<key>.txt` returns the key.
3. Submit:
   1. `generate.py indexnow --site-url https://example.com --key <key> --from-sitemap --dry-run` to review.
   2. Run it again without `--dry-run`. Responses 200/202 mean it was accepted. 403 means the key file wasn't found. 422 means a URL doesn't match the host.
4. **Automate it:** ping changed URLs after each deploy (CI step), or use built-in integrations:
   - Cloudflare Crawler Hints
   - Rank Math, or Microsoft's IndexNow plugin for WordPress
   - Wix and Duda have it built in

## Analytics

- **GA4:** create a property and web data stream, then add the gtag snippet or use GTM. Link it in Search Console. In the EU, use Consent Mode and a consent banner.
- **Privacy-first alternatives** (often no cookie banner needed): Plausible, Fathom, Umami, Cloudflare Web Analytics, Simple Analytics, Matomo.
- **AI referrals:** create a segment or channel for referrers `chatgpt.com`, `perplexity.ai`, `claude.ai`, `gemini.google.com`, `copilot.microsoft.com`, `chat.mistral.ai`, `deepseek.com` and `you.com`.

## Local business listings

Keep name, address, phone, website, hours and categories **identical** everywhere (the NAP consistency principle).

- **Google Business Profile** — https://business.google.com
  - Create or claim the business, then verify (video, postcard, phone or email; Google picks the method).
  - Fill in categories, services, hours, photos, website URL (with UTM parameters if you want), and booking links.
  - Ask customers for reviews.
- **Bing Places** — https://www.bingplaces.com: import from Google Business Profile.
- **Apple Business Connect** — https://businessconnect.apple.com: Apple Maps, Siri and Spotlight.
- **Others:** industry directories, the chamber of commerce, Facebook page, LinkedIn company page, Yelp/TripAdvisor (if relevant), and local directories in the country.

## Regional search engines (only if those markets matter)

- **Yandex Webmaster** (https://webmaster.yandex.com): verify with the `yandex-verification` meta tag, DNS or a file. IndexNow covers fast updates.
- **Naver Search Advisor** (Korea), **Baidu Ziyuan** (China; needs a Chinese phone number, and ICP licensing helps), **Seznam Webmaster** (Czechia).

## Domain change / redesign

1. Map every old URL to its new equivalent with a 301. No blanket redirects to the homepage.
2. Keep the old domain's DNS and redirects live for at least a year.
3. Verify both domains in Search Console → old property → **Settings → Change of address**.
4. Submit the new sitemap. Update profiles, `sameAs` and backlinks you control.

## Ongoing checks

| When | Check |
|---|---|
| Launch +3 days | GSC Sitemaps status, URL Inspection of the homepage, first indexing |
| Launch +2 weeks | GSC Pages report: unexpected exclusions; Bing Site Explorer |
| Monthly | GSC Performance (queries, CTR); fix low-CTR titles and descriptions; Core Web Vitals; structured data errors; re-run `audit.py --psi` |
| Quarterly | Ask AI assistants about the brand and category; update key content and llms.txt; review robots.txt AI bot policy; refresh `lastmod` |
