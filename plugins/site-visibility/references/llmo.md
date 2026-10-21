# LLMO / GEO: being found and cited by AI assistants

LLMO (LLM optimisation) is also called GEO (generative engine optimisation) or AEO (answer engine optimisation). Its goal is that ChatGPT, Claude, Perplexity, Gemini, Copilot, Google AI Overviews and AI Mode can find your pages, understand them and cite them.

Most of LLMO is good technical SEO plus clear writing. There is no secret tag.

## How AI assistants get your content

1. **Their own crawlers or fetchers** at answer time: OAI-SearchBot, ChatGPT-User, Claude-SearchBot, Claude-User, PerplexityBot, Perplexity-User, DuckAssistBot. Most of them do **not run JavaScript**: if the text isn't in the HTML, they don't see it.
2. **Search indexes:**
   - Google (AI Overviews and AI Mode use Google's index; Googlebot-rendered)
   - Bing (Copilot and several partners)
   - Being well indexed in both is the foundation.
3. **Training data:** GPTBot, ClaudeBot, Google-Extended, CCBot and others. This shapes what models "know" about your brand without browsing. Blocking these is a legitimate business choice. It doesn't remove you from AI search answers.

## Technical requirements (the audit checks these)

- **Server-render or prerender** every page you want cited (SSR/SSG). This is the biggest LLMO failure on modern JS sites.
- **Allow AI search and user bots** in robots.txt, and make sure the CDN/WAF doesn't challenge them. Cloudflare in particular can block AI crawlers by default on some plans; check *AI Crawl Control* and the bot settings.
- **Fast, stable, 200-status pages** with canonical URLs and an up-to-date sitemap with real `lastmod`.
- **`/llms.txt`:** a curated Markdown index of your most useful pages. It's a proposed standard (llmstxt.org): cheap to add and useful to agents and IDE tools, with uneven crawler adoption. Keep it short, factual and current.
- **Structured data:** Organization/LocalBusiness with `sameAs`, WebSite, Article with author and dates, Product with offers, and FAQ. This helps machines resolve *who* you are.
- **Semantic HTML:** `<main>`, `<article>`, headings, `<table>` for tabular data, real lists. Avoid content locked in images, canvas, tabs that load on click, or PDFs only.
- **Don't use `nosnippet` or `max-snippet:0`** on content you want cited. They also remove you from Google's AI features.

## Content that gets cited

- **Say what you are in the first paragraph:** "Acme Studio is a web design agency in Cluj-Napoca, Romania, building fast marketing sites for clinics and real-estate agencies since 2016." Name, category, location, audience and proof.
- **Answer real questions directly:** use a question as the H2, then a 1–3 sentence direct answer, then detail. FAQ sections and "How much does X cost?" pages are frequently quoted.
- **Be specific and verifiable:** numbers, prices or price ranges, dates, named clients (with permission), methods, comparisons and tables. Vague marketing copy rarely gets cited.
- **Show expertise (E-E-A-T):**
  - author names with bios and credentials on articles
  - an About page with the team, history and address
  - case studies
  - outbound citations to reputable sources
- **Keep facts consistent everywhere:** the same name, address, phone, services and prices on the site, Google Business Profile, LinkedIn, directories and Wikipedia/Wikidata if you have them. LLMs cross-check.
- **Freshness:** update key pages, show "Updated on", and keep `dateModified` and the sitemap `lastmod` honest.
- **Comparison and "best X for Y" content:** be honest, and include your own offering where it fits.
- **Earn mentions:** reviews, press, podcasts, community answers (Reddit, Quora, forums) and listicles. Off-site mentions strongly influence what assistants say.
- **Multilingual sites:** publish real translated pages with hreflang. Don't rely on auto-translate widgets, because crawlers don't see the result.

## Measuring

- **Referral traffic** in analytics from `chatgpt.com`, `perplexity.ai`, `claude.ai`, `gemini.google.com`, `copilot.microsoft.com` and `chat.mistral.ai`. ChatGPT adds `utm_source=chatgpt.com` to many links.
- **Search Console:** AI Overviews and AI Mode traffic is counted in the normal Performance report.
- **Bing Webmaster Tools:** check its reports for Copilot/AI data where available.
- **Manual spot checks:** ask several assistants about your brand, your category in your city or niche, and your top questions. Note whether you're cited and what they get wrong. Then fix the source content or the inconsistent profiles.
- **Server logs or CDN analytics:** see which AI bots actually crawl you and which pages they hit.

## llms.txt format (llmstxt.org)

```markdown
# Brand name

> One or two sentence summary: what you are, for whom, where.

Optional short paragraphs with key facts (founded, locations, pricing model, contact).

## Services
- [Web design](https://example.com/services/web-design): Custom marketing sites built with Astro, from €3,000.
- [SEO audit](https://example.com/services/seo-audit): Technical + content audit delivered in 5 days.

## Company
- [About](https://example.com/about): Team, history and office in Cluj-Napoca.
- [Contact](https://example.com/contact): Email, phone, address and opening hours.

## Optional
- [Blog](https://example.com/blog): Articles on web performance and SEO.
```

Rules:

- The H1 is required.
- The blockquote summary is strongly recommended.
- Each H2 section is a list of links with short notes.
- `## Optional` marks content an agent may skip when it's short of context.
- Serve it as `text/plain` or `text/markdown`.
- Optionally provide a `.md` version of pages (`/page.md`) and `/llms-full.txt` with full content.
