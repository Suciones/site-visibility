#!/usr/bin/env python3
"""Generate visibility files: robots.txt, sitemap.xml, llms.txt, favicon set, <head> tags, IndexNow.

Subcommands
  robots       --site-url URL [--block-training] [--disallow /admin/ ...]
  sitemap      TARGET --site-url URL [--max 500]          crawl a live/local site or build folder
  llms         TARGET --site-url URL [--name ..] [--summary ..] [--full]
  favicons     SOURCE_IMAGE --out DIR [--name ..] [--theme-color #hex] [--background #hex]
  head         --site-url URL --title .. --description .. [--image ..] [--site-name ..] [--logo ..] [--same-as URL ...]
  indexnow-key --out PUBLIC_DIR
  indexnow     --site-url URL --key KEY (--urls URL ... | --from-sitemap) [--dry-run]

Python 3.8+, standard library only (Pillow used for favicons when installed, otherwise macOS `sips`).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from collections import OrderedDict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urldefrag, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from audit import (AI_BOTS, LOCAL_HOSTS, Fetcher, Page, Robots, node_types,  # noqa: E402
                   parse_sitemap, serve_directory)

SKIP_EXT = re.compile(r"\.(pdf|jpe?g|png|gif|webp|avif|svg|ico|zip|gz|mp4|webm|mp3|css|js|json|xml|txt|woff2?)$", re.I)


# --------------------------------------------------------------------------- crawling

def open_target(target, site_url):
    server = None
    if os.path.isdir(target):
        server, base = serve_directory(target)
        base += "/"
    else:
        base = target if re.match(r"^https?://", target) else "https://" + target
        if not urlparse(base).path:
            base += "/"
    f = Fetcher()
    o = lambda u: "%s://%s" % (urlparse(u).scheme, urlparse(u).netloc)  # noqa: E731
    if site_url and o(site_url) != o(base):
        f.rewrite = (o(site_url), o(base))
    return f, base, server


def to_public(url, base, site_url):
    """Map a fetched (possibly local) URL to its production URL."""
    if not site_url:
        return url
    b = urlparse(base)
    u = urlparse(url)
    if u.netloc == b.netloc:
        return site_url.rstrip("/") + (u.path or "/") + (("?" + u.query) if u.query else "")
    return url


def path_key(url):
    path = re.sub(r"/index\.html?$", "/", urlparse(url).path)
    return path.rstrip("/") or "/"


def crawl(target, site_url, max_pages=500, quiet=False):
    """Breadth-first crawl of same-host HTML pages. Returns list of dicts (public url, title, description, ...)."""
    f, base, server = open_target(target, site_url)
    host = urlparse(base).netloc
    prod_host = urlparse(site_url).netloc if site_url else host
    hosts = {host, prod_host, prod_host.replace("www.", ""), "www." + prod_host.replace("www.", "")}
    queue, seen, pages = [base], set(), []
    try:
        while queue and len(pages) < max_pages:
            u = queue.pop(0)
            fetch_u = f.map(u)
            key = path_key(fetch_u)
            if key in seen:
                continue
            seen.add(key)
            r = f.get(fetch_u)
            if not r.ok or "html" not in r.content_type:
                continue
            if urlparse(r.final_url).netloc not in hosts:
                continue
            final_key = path_key(r.final_url)
            if r.chain and final_key in seen and final_key != key:
                continue
            seen.add(final_key)
            pg = Page(r)
            noindex = "noindex" in pg.robots_meta or "noindex" in r.header("x-robots-tag").lower()
            canon = pg.canonicals[0] if pg.canonicals else None
            public = to_public(r.final_url, base, site_url)
            if canon and urlparse(canon).netloc in hosts:
                cpath = path_key(canon)
                if cpath != final_key:
                    noindex = True  # canonicalised elsewhere: keep out of sitemap
                else:
                    public = to_public(f.map(canon), base, site_url) if site_url else canon
            lm = r.header("last-modified")
            lastmod = None
            if lm:
                try:
                    lastmod = parsedate_to_datetime(lm).date().isoformat()
                except Exception:
                    pass
            for n in pg.jsonld_nodes:
                if n.get("dateModified"):
                    lastmod = str(n["dateModified"])[:10]
                    break
            if not noindex:
                pages.append({"url": public, "title": pg.p.title or "", "description": pg.meta.get("description", ""),
                              "h1": next((t for l, t in pg.p.headings if l == 1), ""), "lastmod": lastmod,
                              "words": pg.words, "text": pg.text})
                if not quiet:
                    print("  crawled %s" % public, file=sys.stderr)
            for link in pg.internal_links(hosts):
                link = urldefrag(link)[0]
                if SKIP_EXT.search(urlparse(link).path) or "?" in link:
                    continue
                queue.append(f.map(link))
    finally:
        if server:
            server.shutdown()
    return pages


# --------------------------------------------------------------------------- robots

SEARCH_BOTS = [b for b, _o, _p, kind in AI_BOTS if kind == "search" and b not in ("Googlebot", "Bingbot", "Applebot")]
TRAINING_BOTS = [b for b, _o, _p, kind in AI_BOTS if kind == "training"]


def cmd_robots(a):
    site = a.site_url.rstrip("/")
    dis = a.disallow or []
    lines = ["# robots.txt for %s" % site, "", "User-agent: *", "Allow: /"]
    lines += ["Disallow: %s" % d for d in dis]
    lines += ["", "# AI search & assistant crawlers: allowed so the site can be cited in AI answers"]
    lines += ["User-agent: %s" % b for b in SEARCH_BOTS]
    lines += ["Allow: /"] + ["Disallow: %s" % d for d in dis]
    if a.block_training:
        lines += ["", "# Model-training crawlers: blocked (does not affect Google/Bing or AI search visibility)"]
        lines += ["User-agent: %s" % b for b in TRAINING_BOTS]
        lines += ["Disallow: /"]
    else:
        lines += ["", "# Model-training crawlers (GPTBot, ClaudeBot, Google-Extended, CCBot...) follow the * rules above."]
    lines += ["", "Sitemap: %s/sitemap.xml" % site, ""]
    out = "\n".join(lines)
    write_or_print(out, a.out)


# --------------------------------------------------------------------------- sitemap

def cmd_sitemap(a):
    pages = crawl(a.target, a.site_url, a.max)
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    seen = set()
    for p in pages:
        if p["url"] in seen:
            continue
        seen.add(p["url"])
        xml.append("  <url>")
        xml.append("    <loc>%s</loc>" % html.escape(p["url"]))
        if p.get("lastmod"):
            xml.append("    <lastmod>%s</lastmod>" % p["lastmod"])
        xml.append("  </url>")
    xml.append("</urlset>")
    write_or_print("\n".join(xml) + "\n", a.out)
    print("sitemap: %d URLs" % len(seen), file=sys.stderr)


# --------------------------------------------------------------------------- llms.txt

def section_name(url):
    parts = [p for p in urlparse(url).path.split("/") if p]
    if len(parts) <= 1:
        return "Pages"
    return parts[0].replace("-", " ").replace("_", " ").title()


def clean_title(t, site_name):
    if not t:
        return t
    for sep in (" | ", " – ", " — ", " - ", " · ", " :: "):
        if sep in t:
            parts = [x.strip() for x in t.split(sep)]
            parts = [x for x in parts if x.lower() != (site_name or "").lower()] or parts
            return parts[0]
    return t


def cmd_llms(a):
    pages = crawl(a.target, a.site_url, a.max)
    if not pages:
        sys.exit("No pages found to build llms.txt from.")
    home = pages[0]
    name = a.name or clean_title(home["title"], "") or urlparse(a.site_url or home["url"]).netloc
    summary = a.summary or home["description"] or "TODO: one or two sentences on who you are, what you offer and for whom."
    groups = OrderedDict()
    for p in pages[1:]:
        groups.setdefault(section_name(p["url"]), []).append(p)
    # Put small root pages first, big collections (blog/news) into Optional
    lines = ["# %s" % name, "", "> %s" % summary.strip(), ""]
    lines += ["%s is at %s. Key pages are listed below; each link has a one-line description." %
              (name, (a.site_url or home["url"]).rstrip("/")), ""]
    optional = []
    for sec, items in groups.items():
        if sec.lower() in ("blog", "news", "posts", "articles", "tag", "tags", "category", "author", "page") and len(items) > 8:
            optional.extend(items[:30])
            continue
        lines.append("## %s" % sec)
        lines.append("")
        for p in items[:40]:
            title = clean_title(p["title"], name) or p["h1"] or p["url"]
            desc = p["description"]
            lines.append("- [%s](%s)%s" % (title, p["url"], (": " + desc) if desc else ""))
        lines.append("")
    if optional:
        lines += ["## Optional", ""]
        for p in optional:
            lines.append("- [%s](%s)" % (clean_title(p["title"], name) or p["url"], p["url"]))
        lines.append("")
    write_or_print("\n".join(lines), a.out)
    if a.full:
        full = ["# %s" % name, "", "> %s" % summary.strip(), ""]
        for p in pages:
            full += ["## %s" % (clean_title(p["title"], name) or p["url"]), "", "Source: %s" % p["url"], "", p["text"][:20000], ""]
        path = os.path.join(os.path.dirname(a.out) if a.out else ".", "llms-full.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(full))
        print("wrote %s" % path, file=sys.stderr)
    print("llms.txt: %d pages in %d sections — review and curate before publishing" % (len(pages), len(groups)), file=sys.stderr)


# --------------------------------------------------------------------------- favicons

def _rasterize_svg(src, size, tmp):
    if shutil.which("rsvg-convert"):
        out = os.path.join(tmp, "src.png")
        subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), "-o", out, src], check=True)
        return out
    if sys.platform == "darwin" and shutil.which("qlmanage"):
        subprocess.run(["qlmanage", "-t", "-s", str(size), "-o", tmp, src], check=True, capture_output=True)
        out = os.path.join(tmp, os.path.basename(src) + ".png")
        if os.path.exists(out):
            return out
    sys.exit("Cannot rasterize SVG here. Install librsvg (brew install librsvg) or pass a PNG ≥512px.")


def cmd_favicons(a):
    os.makedirs(a.out, exist_ok=True)
    src = a.source
    tmp = tempfile.mkdtemp()
    made = []
    if src.lower().endswith(".svg"):
        shutil.copy(src, os.path.join(a.out, "icon.svg"))
        made.append("icon.svg")
        src = _rasterize_svg(src, 1024, tmp)
    try:
        from PIL import Image  # type: ignore
        im = Image.open(src).convert("RGBA")
        side = max(im.size)
        sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        sq.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
        if side < 512:
            print("warning: source is %dpx; use ≥512px for crisp icons" % side, file=sys.stderr)

        def save(size, name, bg=None):
            img = sq.resize((size, size), Image.LANCZOS)
            if bg:
                base = Image.new("RGBA", img.size, bg)
                base.alpha_composite(img)
                img = base.convert("RGB")
            img.save(os.path.join(a.out, name))
            made.append(name)

        sq.resize((48, 48), Image.LANCZOS).save(os.path.join(a.out, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])
        made.append("favicon.ico")
        save(96, "favicon-96x96.png")
        save(180, "apple-touch-icon.png", bg=a.background)
        save(192, "web-app-manifest-192x192.png")
        save(512, "web-app-manifest-512x512.png")
    except ImportError:
        if not shutil.which("sips"):
            sys.exit("Need Pillow (pip install pillow) or macOS sips to resize images.")
        for size, name in ((96, "favicon-96x96.png"), (180, "apple-touch-icon.png"),
                           (192, "web-app-manifest-192x192.png"), (512, "web-app-manifest-512x512.png")):
            subprocess.run(["sips", "-s", "format", "png", "-z", str(size), str(size), src, "--out",
                            os.path.join(a.out, name)], check=True, capture_output=True)
            made.append(name)
        print("note: favicon.ico not generated (needs Pillow: pip3 install pillow). favicon-96x96.png covers Google.",
              file=sys.stderr)
    manifest = {
        "name": a.name or "Site name", "short_name": (a.name or "Site")[:12],
        "icons": [{"src": "/web-app-manifest-192x192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                  {"src": "/web-app-manifest-512x512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"}],
        "theme_color": a.theme_color, "background_color": "#ffffff", "display": "standalone", "start_url": "/",
    }
    with open(os.path.join(a.out, "site.webmanifest"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    made.append("site.webmanifest")
    print("created in %s: %s\n" % (a.out, ", ".join(made)), file=sys.stderr)
    snippet = ['<link rel="icon" href="/favicon.ico" sizes="48x48">']
    if "icon.svg" in made:
        snippet.append('<link rel="icon" href="/icon.svg" type="image/svg+xml">')
    snippet += ['<link rel="icon" href="/favicon-96x96.png" type="image/png" sizes="96x96">',
                '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
                '<link rel="manifest" href="/site.webmanifest">',
                '<meta name="theme-color" content="%s">' % a.theme_color]
    print("\n".join(snippet))


# --------------------------------------------------------------------------- head snippet

def cmd_head(a):
    e = lambda s: html.escape(s or "", quote=True)  # noqa: E731
    site = a.site_url.rstrip("/")
    url = a.url or site + "/"
    img = a.image if (a.image or "").startswith("http") else (site + "/" + a.image.lstrip("/") if a.image else None)
    t = ['<meta charset="utf-8">', '<meta name="viewport" content="width=device-width, initial-scale=1">',
         "<title>%s</title>" % e(a.title), '<meta name="description" content="%s">' % e(a.description),
         '<link rel="canonical" href="%s">' % e(url), "",
         '<meta property="og:type" content="website">', '<meta property="og:url" content="%s">' % e(url),
         '<meta property="og:title" content="%s">' % e(a.og_title or a.title),
         '<meta property="og:description" content="%s">' % e(a.description),
         '<meta property="og:site_name" content="%s">' % e(a.site_name or a.title)]
    if a.locale:
        t.append('<meta property="og:locale" content="%s">' % e(a.locale))
    if img:
        t += ['<meta property="og:image" content="%s">' % e(img), '<meta property="og:image:width" content="1200">',
              '<meta property="og:image:height" content="630">',
              '<meta property="og:image:alt" content="%s">' % e(a.image_alt or a.site_name or a.title)]
    t.append('<meta name="twitter:card" content="summary_large_image">')
    if a.twitter:
        t.append('<meta name="twitter:site" content="%s">' % e(a.twitter))
    graph = [{"@type": "WebSite", "@id": site + "/#website", "name": a.site_name or a.title, "url": site + "/",
              "publisher": {"@id": site + "/#org"}}]
    org = {"@type": a.org_type, "@id": site + "/#org", "name": a.site_name or a.title, "url": site + "/"}
    if a.logo:
        org["logo"] = a.logo if a.logo.startswith("http") else site + "/" + a.logo.lstrip("/")
    if a.same_as:
        org["sameAs"] = a.same_as
    graph.append(org)
    t += ["", '<script type="application/ld+json">',
          json.dumps({"@context": "https://schema.org", "@graph": graph}, indent=2, ensure_ascii=False), "</script>"]
    print("\n".join(t))


# --------------------------------------------------------------------------- IndexNow

def cmd_indexnow_key(a):
    key = secrets.token_hex(16)
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, key + ".txt")
    with open(path, "w") as fh:
        fh.write(key)
    print(key)
    print("wrote %s — deploy it so https://your-domain/%s.txt returns the key" % (path, key), file=sys.stderr)


def cmd_indexnow(a):
    site = a.site_url.rstrip("/")
    host = urlparse(site).netloc
    urls = list(a.urls or [])
    f = Fetcher()
    if a.from_sitemap:
        r = f.get(site + "/robots.txt")
        maps = Robots(r.text).sitemaps if r.ok else []
        for sm in maps or [site + "/sitemap.xml"]:
            sr = f.get(sm, max_bytes=20_000_000)
            parsed, err = parse_sitemap(sr.body) if sr.ok else (None, "HTTP %s" % sr.status)
            if err:
                continue
            if parsed["kind"] == "index":
                for child in parsed["urls"][:20]:
                    cr = f.get(child, max_bytes=20_000_000)
                    cp, cerr = parse_sitemap(cr.body) if cr.ok else (None, "x")
                    if not cerr:
                        urls += cp["urls"]
            else:
                urls += parsed["urls"]
    urls = [u for u in dict.fromkeys(urls) if urlparse(u).netloc == host][:10000]
    if not urls:
        sys.exit("No URLs on %s to submit." % host)
    key_url = "%s/%s.txt" % (site, a.key)
    kr = f.get(key_url)
    if not kr.ok or kr.text.strip() != a.key:
        sys.exit("Key file %s is not live (HTTP %s). Deploy it first." % (key_url, kr.status))
    payload = {"host": host, "key": a.key, "keyLocation": key_url, "urlList": urls}
    if a.dry_run:
        print(json.dumps(payload, indent=2))
        print("dry run: %d URLs not submitted" % len(urls), file=sys.stderr)
        return
    import urllib.error
    import urllib.request
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print("IndexNow: HTTP %d — %d URLs submitted (200/202 = accepted)" % (resp.status, len(urls)))
    except urllib.error.HTTPError as e:
        meaning = {400: "bad request", 403: "key not valid / key file not found", 422: "URLs don't match host or key",
                   429: "too many requests"}.get(e.code, "")
        sys.exit("IndexNow: HTTP %d %s" % (e.code, meaning))


# --------------------------------------------------------------------------- utils

def write_or_print(text, out):
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("wrote %s" % out, file=sys.stderr)
    else:
        sys.stdout.write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("robots", help="robots.txt with AI crawler policy")
    p.add_argument("--site-url", required=True)
    p.add_argument("--block-training", action="store_true", help="Disallow model-training crawlers")
    p.add_argument("--disallow", nargs="*", help="Paths to keep out of crawlers, e.g. /admin/ /api/")
    p.add_argument("--out")
    p.set_defaults(func=cmd_robots)

    for name, func, helptext in (("sitemap", cmd_sitemap, "crawl and write sitemap.xml"),
                                 ("llms", cmd_llms, "crawl and draft llms.txt")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("target", help="URL, localhost URL or build folder")
        p.add_argument("--site-url", required=name == "sitemap", help="Production origin used in output URLs")
        p.add_argument("--max", type=int, default=500)
        p.add_argument("--out")
        if name == "llms":
            p.add_argument("--name")
            p.add_argument("--summary")
            p.add_argument("--full", action="store_true", help="Also write llms-full.txt next to --out")
        p.set_defaults(func=func)

    p = sub.add_parser("favicons", help="favicon.ico, PNG icons, apple-touch-icon, web manifest")
    p.add_argument("source")
    p.add_argument("--out", required=True)
    p.add_argument("--name")
    p.add_argument("--theme-color", default="#ffffff")
    p.add_argument("--background", default="#ffffff", help="Fill for apple-touch-icon (iOS shows black behind transparency)")
    p.set_defaults(func=cmd_favicons)

    p = sub.add_parser("head", help="print recommended <head> tags + JSON-LD")
    p.add_argument("--site-url", required=True)
    p.add_argument("--url", help="Canonical URL of this page (default: homepage)")
    p.add_argument("--title", required=True)
    p.add_argument("--og-title")
    p.add_argument("--description", required=True)
    p.add_argument("--image", help="og:image path or URL (1200×630)")
    p.add_argument("--image-alt")
    p.add_argument("--site-name")
    p.add_argument("--locale", help="e.g. en_US, ro_RO")
    p.add_argument("--twitter", help="@handle")
    p.add_argument("--org-type", default="Organization", help="Organization, LocalBusiness, Person, ...")
    p.add_argument("--logo")
    p.add_argument("--same-as", nargs="*", help="Social/profile URLs")
    p.set_defaults(func=cmd_head)

    p = sub.add_parser("indexnow-key", help="create an IndexNow key file")
    p.add_argument("--out", required=True, help="Public/static folder of the site")
    p.set_defaults(func=cmd_indexnow_key)

    p = sub.add_parser("indexnow", help="submit URLs to IndexNow (Bing, Yandex, Seznam, Naver)")
    p.add_argument("--site-url", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--urls", nargs="*")
    p.add_argument("--from-sitemap", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_indexnow)

    a = ap.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
