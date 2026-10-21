# Implementation by framework and host

These are framework-native ways to implement each visibility item. Check the project's framework version and existing conventions before editing. APIs change, so verify against the installed version's docs when in doubt.

## Next.js (App Router)

- **Site URL:** set `metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? 'https://example.com')` in the root `app/layout.tsx` metadata. Without it, relative og:image and canonical URLs break.
- **Metadata:** `export const metadata: Metadata` in layouts and pages, or `export async function generateMetadata({ params })` for dynamic routes. A full example:
  ```ts
  export const metadata: Metadata = {
    metadataBase: new URL('https://example.com'),
    title: { default: 'Brand – What you do', template: '%s – Brand' },
    description: '120–160 chars…',
    alternates: { canonical: '/' },
    openGraph: { type: 'website', siteName: 'Brand', locale: 'en_US', url: '/' },
    twitter: { card: 'summary_large_image' },
    robots: { index: process.env.VERCEL_ENV === 'production' || !process.env.VERCEL_ENV },
    verification: { google: '…', other: { 'msvalidate.01': '…' } },
  };
  ```
  Set `alternates.canonical` per page, e.g. `/blog/${slug}`.
- **Icons:** use the file conventions.
  - `app/favicon.ico` (root `app/` only)
  - `app/icon.png` or `icon.svg` (use 96×96 or 192×192 to satisfy Google's 48px-multiple rule)
  - `app/apple-icon.png` (180×180)
  - `app/manifest.ts` (returns `MetadataRoute.Manifest`)
- **OG image:** `app/opengraph-image.png` (1200×630), or `opengraph-image.tsx` using `ImageResponse` from `next/og` for dynamic per-route images. `twitter-image.*` is optional; X falls back to OG.
- **robots.txt:** `app/robots.ts` returning `MetadataRoute.Robots`:
  ```ts
  { rules: [{ userAgent: '*', allow: '/' }], sitemap: 'https://example.com/sitemap.xml' }
  ```
  Add per-bot rules if needed.
- **Sitemap:** `app/sitemap.ts` returning `MetadataRoute.Sitemap`. Include dynamic routes from your CMS or database. Use `generateSitemaps` above 50k URLs.
- **JSON-LD:** render in a Server Component:
  ```tsx
  <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, '\\u003c') }} />
  ```
- **llms.txt:** `app/llms.txt/route.ts` with `export const dynamic = 'force-static'` and a `GET` that builds Markdown from your content source. Return it with `Content-Type: text/plain; charset=utf-8`. A static `public/llms.txt` also works.
- **Rendering:** keep pages as Server Components. Fetch data on the server, and push `"use client"` down to interactive leaves. Content fetched in `useEffect` is invisible to AI crawlers.
- **404:** `app/not-found.tsx`; call `notFound()` for missing slugs so they return a real 404.
- **Previews:** Vercel sends `X-Robots-Tag: noindex` on preview deployments. Don't add your own global noindex.

## Next.js (Pages Router)

- `next/head` in `_app`/pages for title, meta and OG.
- `next-sitemap` (postbuild) for the sitemap and robots.txt, or `pages/sitemap.xml.ts` using `getServerSideProps` to write XML.
- Static files go in `public/`.
- Use `getStaticProps`/`getServerSideProps`, not client fetching, for indexable content.

## Astro

- `site: 'https://example.com'` in `astro.config.mjs`. Required for the sitemap and canonical URLs.
- **Sitemap:** the `@astrojs/sitemap` integration outputs `/sitemap-index.xml` and `/sitemap-0.xml`. Reference `sitemap-index.xml` in robots.txt. Use its `filter` option to exclude noindex pages.
- **Head:** a `BaseHead.astro` component used by every layout:
  - canonical: `new URL(Astro.url.pathname, Astro.site)`
  - OG and Twitter tags from props
  - JSON-LD: `<script type="application/ld+json" set:html={JSON.stringify(data)} />`
- **robots.txt and llms.txt:** static files in `public/`, or endpoints like `src/pages/robots.txt.ts` and `src/pages/llms.txt.ts` exporting `GET` (prerendered). Build llms.txt from `getCollection()` so it stays in sync.
- **Icons:** in `public/` (favicon.ico, icon.svg, apple-touch-icon.png, site.webmanifest), linked in BaseHead.
- **OG images:** static files, or generate them at build time (e.g. Satori + resvg in an endpoint, or `astro-og-canvas`).
- **404:** `src/pages/404.astro`.
- Astro is static by default, so content is in the HTML. Avoid `client:only` for main content.

## Nuxt 3/4

- Install `@nuxtjs/seo`. It bundles sitemap, robots, og-image, schema-org and link checking.
- Set `site: { url: 'https://example.com', name: 'Brand' }` in `nuxt.config`.
- Per page: `useSeoMeta({ title, description, ogTitle, ogDescription, ogImage, twitterCard: 'summary_large_image' })`. Set the language with `useHead({ htmlAttrs: { lang: 'en' } })` (or app config).
- Schema: `useSchemaOrg([defineOrganization({...}), defineWebSite({...})])`.
- llms.txt: the `nuxt-llms` module, or `server/routes/llms.txt.ts` returning text, or `public/llms.txt`.
- Keep `ssr: true` (the default). `ssr: false` makes the site invisible to AI crawlers. Use `nuxi generate` for static hosting.

## SvelteKit

- Use `<svelte:head>` in `+layout.svelte` and `+page.svelte` for title, meta, OG and JSON-LD. Pass the data from `load` functions.
- Set `lang` in `src/app.html`.
- **Sitemap:** `src/routes/sitemap.xml/+server.ts` with `export const prerender = true`, returning XML.
- **robots.txt and llms.txt:** `static/robots.txt`, `static/llms.txt`, or `+server.ts` routes.
- **Red flags:** `export const ssr = false`, or adapter-static with a SPA `fallback` page (soft 404s).

## Remix / React Router v7 (framework mode)

- Route `meta` export:
  ```ts
  [{ title }, { name: 'description', content }, { property: 'og:image', content }, { tagName: 'link', rel: 'canonical', href }]
  ```
  With React 19 you can also render `<title>`/`<meta>` inside components.
- **Resource routes:** `app/routes/sitemap[.]xml.ts`, `robots[.]txt.ts` and `llms[.]txt.ts` with a `loader` returning `new Response(body, { headers })`.
- For static hosting, use `prerender` in `react-router.config.ts`.

## Gatsby

- Head API: `export const Head = () => (<><title>…</title><meta …/></>)`.
- `siteMetadata.siteUrl` in config.
- Plugins: `gatsby-plugin-sitemap`, `gatsby-plugin-robots-txt`, and `gatsby-plugin-manifest` (also generates favicons and manifest icons).
- `static/llms.txt`.

## Vite + React / Vue / Svelte SPA (client-rendered)

The raw HTML is an empty `<div id="root">`. Google renders JS (slowly). Social scrapers and most AI crawlers do not. Options, from best to cheapest:

1. Move to a framework with SSG/SSR: Astro, Next, React Router framework mode with `prerender`, Nuxt, SvelteKit, or Vike.
2. Prerender routes at build time, with `vite-prerender-plugin` or a Playwright script that saves each route's HTML.
3. At minimum:
   - Put the real title, description, OG/Twitter tags, JSON-LD and a meaningful `<noscript>` or static content block in `index.html`.
   - Add `public/robots.txt`, `public/sitemap.xml`, `public/llms.txt` and the icons.
   - `react-helmet-async` / `@unhead/vue` per-route tags help Google only.
- **Host config:** the SPA catch-all (`/* /index.html 200`) makes every URL return 200 (soft 404). List the real routes, or prerender a 404 page.

## Static site generators

- **Hugo:**
  - Set `baseURL`. `sitemap.xml` is automatic.
  - `enableRobotsTXT = true` with `layouts/robots.txt`.
  - Use the embedded OpenGraph, Twitter Cards and Schema templates in the head partial.
  - Static files go in `static/`. llms.txt is a custom output format or `static/llms.txt`.
- **Jekyll:**
  - Set `url` in `_config.yml`.
  - `jekyll-seo-tag` (`{% seo %}`) for title, meta, OG and JSON-LD; `jekyll-sitemap` for the sitemap.
  - `robots.txt` and `llms.txt` as pages with `permalink:` and `layout: null`.
- **Eleventy:**
  - A head include with front-matter data.
  - `sitemap.njk` with `permalink: /sitemap.xml` looping over `collections.all`.
  - `llms.njk` with `permalink: /llms.txt`.

## WordPress

- **Settings → Reading → "Discourage search engines" must be unchecked.** It adds noindex site-wide and is often left on after development.
- An SEO plugin (Yoast SEO, Rank Math or SEOPress) handles titles, descriptions, OG/Twitter, schema (Organization/LocalBusiness, Breadcrumb, Article), XML sitemaps (replacing core `wp-sitemap.xml`), the robots.txt editor and verification codes.
- Recent Yoast and Rank Math versions can also generate llms.txt. Otherwise use a dedicated plugin or a static file in the web root.
- **Site icon:** Appearance → Customize → Site Identity → Site Icon (upload 512×512). WP outputs 32, 180, 192 and 270 sizes; 192 satisfies Google.
- **IndexNow:** Rank Math has it built in, or use the official IndexNow plugin.
- Check that the caching/CDN plugin doesn't strip `<head>` tags. Check the theme outputs one H1.

## Hosted builders (Webflow, Framer, Wix, Squarespace, Shopify)

- Use the platform's SEO panels:
  - per-page title, description and OG image
  - favicon (Webflow also has a webclip)
  - robots.txt editor
  - auto sitemap
  - Google verification field
  - custom head code for JSON-LD
- CMS/collection templates must map fields to the SEO title, description and OG image.
- If the platform can't host `/llms.txt` at the root, check for a native option first. If there is none, serve it via a proxy (e.g. a Cloudflare Worker route), or skip it. It's optional.

## Hosting & CDN

- **Vercel:**
  - Domains → set one primary domain and redirect the other (www/apex).
  - `vercel.json` `redirects` / `headers`. Preview deployments are noindexed automatically.
- **Netlify:**
  - `_redirects` / `netlify.toml` for redirects and `[[headers]]`.
  - A `404.html` is served with status 404. Avoid `/* /index.html 200` unless needed.
- **Cloudflare (Pages and proxied sites):**
  - Pages without a `404.html` behaves like an SPA: unknown URLs return index.html with 200.
  - In the dashboard, check Security → Bots and **AI Crawl Control**. The "Block AI bots" toggle and the managed robots.txt can block or disallow AI crawlers, including ones you may want.
  - Enable Brotli, Always Use HTTPS, HSTS, and Crawler Hints (IndexNow).
- **Apache (`.htaccess`):** force HTTPS and the canonical host with one `RewriteRule … [R=301,L]`. Add `mod_deflate`/`mod_brotli`, `Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains"`, and `ErrorDocument 404 /404.html`.
- **Nginx:** add a `return 301 https://example.com$request_uri;` server block for the http and www variants. Enable `gzip on;` (plus brotli if the module is present), `add_header Strict-Transport-Security …`, and `error_page 404 /404.html;`.
