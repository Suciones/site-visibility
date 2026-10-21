#!/usr/bin/env python3
"""Site visibility audit.

Checks everything a site needs for basic search and AI visibility: crawlability,
on-page SEO, social share cards, favicon/app icons, structured data, robots.txt,
sitemap, llms.txt, AI crawler access, search-engine verification and basic
performance/security headers. Writes JSON, Markdown and HTML reports (the HTML
report includes Google result, social card and favicon previews).

Targets:
  https://example.com        live site
  http://localhost:3000      local dev/preview server
  ./dist                     static build output folder (served on a temp port)

Python 3.8+, standard library only.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import html
import json
import os
import re
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time
import uuid
import zlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from functools import partial
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, urldefrag, urljoin, urlparse
import urllib.error
import urllib.request

VERSION = "1.0.0"
DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 SiteVisibilityAudit/1.0")

BOT_UAS = {
    "Googlebot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Bingbot": "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    "GPTBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.1; +https://openai.com/gptbot",
    "OAI-SearchBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot",
    "ChatGPT-User": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot",
    "ClaudeBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    "Claude-User": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-User/1.0; +Claude-User@anthropic.com)",
    "PerplexityBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
}

# (robots.txt token, owner, purpose, kind) — kind: search = needed to appear/cited, training = model training only
AI_BOTS = [
    ("Googlebot", "Google", "Google Search, AI Overviews, AI Mode", "search"),
    ("Bingbot", "Microsoft", "Bing, Copilot, DuckDuckGo & ChatGPT search index", "search"),
    ("OAI-SearchBot", "OpenAI", "ChatGPT search results", "search"),
    ("ChatGPT-User", "OpenAI", "ChatGPT fetching a page for a user", "search"),
    ("Claude-SearchBot", "Anthropic", "Claude search results", "search"),
    ("Claude-User", "Anthropic", "Claude fetching a page for a user", "search"),
    ("PerplexityBot", "Perplexity", "Perplexity search index", "search"),
    ("Perplexity-User", "Perplexity", "Perplexity fetching a page for a user", "search"),
    ("Applebot", "Apple", "Siri, Spotlight, Safari suggestions", "search"),
    ("DuckAssistBot", "DuckDuckGo", "DuckAssist AI answers", "search"),
    ("GPTBot", "OpenAI", "Model training", "training"),
    ("ClaudeBot", "Anthropic", "Model training", "training"),
    ("Google-Extended", "Google", "Gemini training & grounding (not Search)", "training"),
    ("Applebot-Extended", "Apple", "Apple Intelligence training", "training"),
    ("CCBot", "Common Crawl", "Open dataset used by many LLMs", "training"),
    ("Meta-ExternalAgent", "Meta", "Meta AI training", "training"),
    ("Amazonbot", "Amazon", "Alexa / Rufus answers & training", "training"),
    ("Bytespider", "ByteDance", "Model training", "training"),
]

CATEGORIES = [
    ("crawl", "Crawlability & indexing"),
    ("onpage", "On-page SEO"),
    ("social", "Social share cards"),
    ("icons", "Favicon & app icons"),
    ("schema", "Structured data"),
    ("llmo", "AI / LLM visibility (LLMO)"),
    ("engines", "Search engines & verification"),
    ("perf", "Performance & security basics"),
]

LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}

# Arial advance widths (1/1000 em) for estimating Google title pixel width (20px desktop).
_ARIAL = dict(zip(
    " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~",
    [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
     556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015,
     667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778,
     722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333,
     556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556,
     333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]))


def text_px(text: str, size: int = 20) -> int:
    total = 0
    for ch in text:
        if ch in _ARIAL:
            total += _ARIAL[ch]
        elif ord(ch) > 0x2E80:  # CJK and similar full-width
            total += 1000
        else:
            total += 556
    return int(total * size / 1000)


# --------------------------------------------------------------------------- HTTP

class Response:
    def __init__(self, url, status=0, headers=None, body=b"", final_url=None, chain=None,
                 elapsed=0.0, error=None):
        self.url = url
        self.status = status
        self.headers = headers or {}
        self.body = body
        self.final_url = final_url or url
        self.chain = chain or []
        self.elapsed = elapsed
        self.error = error

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status < 300

    def header(self, name: str) -> str:
        return self.headers.get(name.lower(), "")

    @property
    def content_type(self) -> str:
        return self.header("content-type").split(";")[0].strip().lower()

    @property
    def text(self) -> str:
        charset = None
        m = re.search(r"charset=([\w-]+)", self.header("content-type"), re.I)
        if m:
            charset = m.group(1)
        else:
            m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", self.body[:2048], re.I)
            if m:
                charset = m.group(1).decode("ascii", "ignore")
        try:
            return self.body.decode(charset or "utf-8", errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")

    @property
    def looks_html(self) -> bool:
        head = self.body[:600].lstrip().lower()
        return head.startswith((b"<!doctype html", b"<html", b"<head", b"<!--")) and b"<" in head[:1]

    def exists_as_file(self) -> bool:
        """True when a root file (robots.txt, llms.txt...) really exists, not an SPA fallback page."""
        return self.ok and len(self.body.strip()) > 0 and not self.looks_html


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401
        return None


class Fetcher:
    def __init__(self, ua=DEFAULT_UA, timeout=20, insecure=False):
        self.ua = ua
        self.timeout = timeout
        self.cache = {}
        self.rewrite = None  # (production_origin, local_origin)
        self.lock = threading.Lock()
        ctx = ssl.create_default_context()
        try:
            import certifi  # type: ignore
            ctx.load_verify_locations(certifi.where())
        except Exception:
            pass
        if insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        self.opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=ctx))

    def map(self, url: str) -> str:
        if self.rewrite:
            prod, local = self.rewrite
            for p in {prod, prod.replace("://www.", "://"), prod.replace("://", "://www.")}:
                if url.startswith(p + "/") or url == p:
                    return local + url[len(p):]
        return url

    def get(self, url, ua=None, method="GET", max_bytes=6_000_000, follow=True,
            accept_encoding="gzip, deflate", use_cache=True, headers=None) -> Response:
        key = (url, ua, method, accept_encoding, follow, max_bytes)
        if use_cache and key in self.cache:
            return self.cache[key]
        chain = []
        cur = self.map(url)
        start = time.time()
        resp = None
        for _ in range(10):
            h = {
                "User-Agent": ua or self.ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Encoding": accept_encoding,
                "Accept-Language": "en-US,en;q=0.9",
            }
            if headers:
                h.update(headers)
            req = urllib.request.Request(cur, method=method, headers=h)
            try:
                r = self.opener.open(req, timeout=self.timeout)
                status, hdrs = r.status, {k.lower(): v for k, v in r.headers.items()}
                body = r.read(max_bytes) if method != "HEAD" else b""
            except urllib.error.HTTPError as e:
                status, hdrs = e.code, {k.lower(): v for k, v in (e.headers or {}).items()}
                try:
                    body = e.read(max_bytes)
                except Exception:
                    body = b""
            except Exception as e:  # DNS, TLS, timeout, refused
                reason = getattr(e, "reason", e)
                resp = Response(url, 0, {}, b"", cur, chain, time.time() - start, error=str(reason))
                break
            enc = hdrs.get("content-encoding", "").lower()
            if body and enc in ("gzip", "x-gzip"):
                try:
                    body = gzip.decompress(body)
                except Exception:
                    pass
            elif body and enc == "deflate":
                try:
                    body = zlib.decompress(body)
                except Exception:
                    try:
                        body = zlib.decompress(body, -zlib.MAX_WBITS)
                    except Exception:
                        pass
            if follow and status in (301, 302, 303, 307, 308) and hdrs.get("location"):
                chain.append((cur, status))
                cur = self.map(urljoin(cur, hdrs["location"]))
                continue
            resp = Response(url, status, hdrs, body, cur, chain, time.time() - start)
            break
        if resp is None:
            resp = Response(url, 0, {}, b"", cur, chain, time.time() - start, error="Too many redirects")
        if use_cache:
            with self.lock:
                self.cache[key] = resp
        return resp


# --------------------------------------------------------------------------- local static server

class _StaticHandler(SimpleHTTPRequestHandler):
    extensions_map = dict(SimpleHTTPRequestHandler.extensions_map)
    extensions_map.update({".webmanifest": "application/manifest+json", ".md": "text/markdown",
                           ".txt": "text/plain", ".xml": "application/xml", ".svg": "image/svg+xml",
                           ".webp": "image/webp", ".avif": "image/avif", ".ico": "image/x-icon"})

    def log_message(self, *args):
        pass

    def translate_path(self, path):
        p = super().translate_path(path)
        if os.path.exists(p):
            return p
        if os.path.isfile(p + ".html"):
            return p + ".html"
        return p

    def send_error(self, code, message=None, explain=None):
        page = os.path.join(self.directory, "404.html")
        if code == 404 and os.path.isfile(page):
            with open(page, "rb") as fh:
                body = fh.read()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return
        super().send_error(code, message, explain)


def serve_directory(directory: str):
    handler = partial(_StaticHandler, directory=os.path.abspath(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, "http://127.0.0.1:%d" % server.server_address[1]


# --------------------------------------------------------------------------- parsing

class PageParser(HTMLParser):
    HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    LANDMARKS = {"main", "nav", "header", "footer", "article", "section", "aside"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = None
        self.title = None
        self.titles = 0
        self.metas = []
        self.links = []
        self.jsonld = []
        self.headings = []
        self.imgs = []
        self.anchors = []
        self.text_parts = []
        self.landmarks = set()
        self.scripts = 0
        self.blocking_head_scripts = 0
        self.itemscope = 0
        self.iframes = 0
        self.base = None
        self.charset = None
        self.resource_urls = []  # (tag, url) for mixed-content checks
        self._skip = 0
        self._svg = 0
        self._in_head = True
        self._in_title = False
        self._in_jsonld = False
        self._buf = []
        self._heading = None
        self._anchor = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v if v is not None else "") for k, v in attrs}
        if tag == "html" and self.lang is None:
            self.lang = a.get("lang")
        elif tag == "title" and not self._svg:
            self.titles += 1
            if self.title is None:
                self._in_title = True
                self._buf = []
        elif tag == "meta":
            self.metas.append(a)
            if "charset" in a:
                self.charset = a["charset"]
            elif a.get("http-equiv", "").lower() == "content-type" and "charset" in a.get("content", "").lower():
                self.charset = a["content"]
        elif tag == "link":
            self.links.append(a)
            if "stylesheet" in a.get("rel", "").lower() and a.get("href"):
                self.resource_urls.append(("link", a["href"]))
        elif tag == "base":
            self.base = a.get("href")
        elif tag == "script":
            self.scripts += 1
            stype = a.get("type", "").lower()
            if stype == "application/ld+json":
                self._in_jsonld = True
                self._buf = []
            elif self._in_head and a.get("src") and "async" not in a and "defer" not in a and stype != "module":
                self.blocking_head_scripts += 1
            if a.get("src"):
                self.resource_urls.append(("script", a["src"]))
            self._skip += 1
        elif tag in ("style", "noscript", "template"):
            self._skip += 1
        elif tag == "svg":
            self._svg += 1
            self._skip += 1
        elif tag in self.HEADINGS:
            self._heading = [int(tag[1]), []]
        elif tag == "img":
            self.imgs.append(a)
            if a.get("src"):
                self.resource_urls.append(("img", a["src"]))
        elif tag == "a":
            self._anchor = [a, []]
        elif tag == "iframe":
            self.iframes += 1
            if a.get("src"):
                self.resource_urls.append(("iframe", a["src"]))
        elif tag == "body":
            self._in_head = False
        if tag in self.LANDMARKS:
            self.landmarks.add(tag)
        if a.get("role") == "main":
            self.landmarks.add("main")
        if "itemscope" in a:
            self.itemscope += 1

    def handle_endtag(self, tag):
        if tag == "title" and self._in_title:
            self.title = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            self._in_title = False
        elif tag == "script":
            if self._in_jsonld:
                self.jsonld.append("".join(self._buf))
                self._in_jsonld = False
            self._skip = max(0, self._skip - 1)
        elif tag in ("style", "noscript", "template"):
            self._skip = max(0, self._skip - 1)
        elif tag == "svg":
            self._svg = max(0, self._svg - 1)
            self._skip = max(0, self._skip - 1)
        elif tag in self.HEADINGS and self._heading:
            self.headings.append((self._heading[0], re.sub(r"\s+", " ", "".join(self._heading[1])).strip()))
            self._heading = None
        elif tag == "a" and self._anchor:
            self.anchors.append((self._anchor[0], re.sub(r"\s+", " ", "".join(self._anchor[1])).strip()))
            self._anchor = None
        elif tag == "head":
            self._in_head = False

    def handle_data(self, data):
        if self._in_jsonld or self._in_title:
            self._buf.append(data)
            return
        if self._skip:
            return
        if self._heading is not None:
            self._heading[1].append(data)
        if self._anchor is not None:
            self._anchor[1].append(data)
        self.text_parts.append(data)


class Page:
    """Parsed HTML page with convenience accessors."""

    def __init__(self, resp: Response):
        self.resp = resp
        self.url = resp.final_url
        p = PageParser()
        try:
            p.feed(resp.text)
            p.close()
        except Exception:
            pass
        self.p = p
        self.base_url = urljoin(self.url, p.base) if p.base else self.url
        self.meta = {}
        for m in p.metas:
            key = (m.get("name") or m.get("property") or m.get("itemprop") or "").strip().lower()
            if key and key not in self.meta:
                self.meta[key] = (m.get("content") or "").strip()
        self.text = re.sub(r"\s+", " ", " ".join(p.text_parts)).strip()
        self.words = len(re.findall(r"\w+", self.text, re.UNICODE))
        self.jsonld_nodes, self.jsonld_errors = parse_jsonld(p.jsonld)

    def links_with_rel(self, rel: str):
        out = []
        for l in self.p.links:
            rels = l.get("rel", "").lower().split()
            if rel in rels:
                out.append(l)
        return out

    def abs(self, href: str) -> str:
        return urljoin(self.base_url, href.strip()) if href is not None else ""

    @property
    def canonicals(self):
        return [self.abs(l.get("href", "")) for l in self.links_with_rel("canonical")]

    @property
    def robots_meta(self) -> str:
        vals = [m.get("content", "") for m in self.p.metas
                if (m.get("name") or "").lower() in ("robots", "googlebot", "bingbot")]
        return ",".join(vals).lower()

    def internal_links(self, origin_hosts):
        out = []
        for a, _txt in self.p.anchors:
            href = a.get("href", "").strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
                continue
            u = urldefrag(self.abs(href))[0]
            if urlparse(u).netloc in origin_hosts and urlparse(u).scheme in ("http", "https"):
                out.append(u)
        return out


def parse_jsonld(blocks):
    nodes, errors = [], []
    for raw in blocks:
        txt = raw.strip()
        txt = re.sub(r"^\s*(<!--|<!\[CDATA\[)", "", txt)
        txt = re.sub(r"(-->|\]\]>)\s*$", "", txt).strip()
        if not txt:
            continue
        try:
            data = json.loads(txt)
        except Exception as e:
            errors.append(str(e)[:160])
            continue
        stack = data if isinstance(data, list) else [data]
        for item in stack:
            if isinstance(item, dict):
                ctx = item.get("@context")
                for n in item.get("@graph", []) if isinstance(item.get("@graph"), list) else []:
                    if isinstance(n, dict):
                        n.setdefault("@context", ctx)
                        nodes.append(n)
                if "@type" in item:
                    nodes.append(item)
    return nodes, errors


def node_types(node):
    t = node.get("@type", [])
    return [t] if isinstance(t, str) else [x for x in t if isinstance(x, str)]


ORG_TYPES = {"Organization", "Corporation", "LocalBusiness", "ProfessionalService", "Store", "Restaurant",
             "RealEstateAgent", "NGO", "EducationalOrganization", "MedicalOrganization", "OnlineStore",
             "OnlineBusiness", "NewsMediaOrganization", "SportsOrganization", "GovernmentOrganization",
             "Person", "Brand", "LegalService", "HomeAndConstructionBusiness", "TravelAgency",
             "LodgingBusiness", "Hotel", "FoodEstablishment", "AutomotiveBusiness", "HealthAndBeautyBusiness",
             "FinancialService", "EmploymentAgency", "Dentist", "Physician"}


def is_org(node):
    return any(t in ORG_TYPES or t.endswith(("Business", "Organization", "Service", "Store")) for t in node_types(node))


def image_info(data: bytes):
    """Return dict(format, width, height, sizes) parsed from image header bytes."""
    info = {"format": None, "width": None, "height": None, "sizes": []}
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
            w, h = struct.unpack(">II", data[16:24])
            info.update(format="png", width=w, height=h)
        elif data[:6] in (b"GIF87a", b"GIF89a"):
            w, h = struct.unpack("<HH", data[6:10])
            info.update(format="gif", width=w, height=h)
        elif data[:2] == b"\xff\xd8":
            info["format"] = "jpeg"
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker == 0xFF:
                    i += 1
                    continue
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    i += 2
                    continue
                seglen = struct.unpack(">H", data[i + 2:i + 4])[0]
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    info.update(width=w, height=h)
                    break
                i += 2 + seglen
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            info["format"] = "webp"
            chunk = data[12:16]
            if chunk == b"VP8 ":
                w, h = struct.unpack("<HH", data[26:30])
                info.update(width=w & 0x3FFF, height=h & 0x3FFF)
            elif chunk == b"VP8L":
                bits = int.from_bytes(data[21:25], "little")
                info.update(width=(bits & 0x3FFF) + 1, height=((bits >> 14) & 0x3FFF) + 1)
            elif chunk == b"VP8X":
                info.update(width=int.from_bytes(data[24:27], "little") + 1,
                            height=int.from_bytes(data[27:30], "little") + 1)
        elif data[:4] == b"\x00\x00\x01\x00":
            count = struct.unpack("<H", data[4:6])[0]
            sizes = []
            for k in range(min(count, 32)):
                e = data[6 + 16 * k: 22 + 16 * k]
                if len(e) < 16:
                    break
                sizes.append((e[0] or 256, e[1] or 256))
            info.update(format="ico", sizes=sizes)
            if sizes:
                big = max(sizes)
                info.update(width=big[0], height=big[1])
        elif data[4:12] in (b"ftypavif", b"ftypavis", b"ftypmif1"):
            info["format"] = "avif"
            k = data.find(b"ispe")
            if k > 0:
                w, h = struct.unpack(">II", data[k + 8:k + 16])
                info.update(width=w, height=h)
        elif b"<svg" in data[:4000].lower():
            info["format"] = "svg"
    except Exception:
        pass
    return info


# --------------------------------------------------------------------------- robots.txt

class Robots:
    def __init__(self, text: str):
        self.groups = []
        self.sitemaps = []
        agents, rules, last_agent = None, None, False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k, v = k.strip().lower(), v.strip()
            if k == "user-agent":
                if not last_agent:
                    agents, rules = [], []
                    self.groups.append((agents, rules))
                agents.append(v.lower())
                last_agent = True
            elif k in ("allow", "disallow"):
                last_agent = False
                if rules is not None:
                    rules.append((k == "allow", v))
            elif k == "sitemap":
                self.sitemaps.append(v)
            else:
                last_agent = False

    def _rules_for(self, token: str):
        token = token.lower()
        best, best_len = None, -1
        for ags, _ in self.groups:
            for a in ags:
                if a != "*" and token.startswith(a) and len(a) > best_len:
                    best, best_len = a, len(a)
        if best is None:
            best = "*"
        rules = []
        for ags, rs in self.groups:
            if best in ags:
                rules.extend(rs)
        return rules, best != "*"

    def explicit(self, token: str) -> bool:
        return self._rules_for(token)[1]

    @staticmethod
    def _match(pattern: str, path: str) -> bool:
        anchored = pattern.endswith("$")
        if anchored:
            pattern = pattern[:-1]
        rx = "".join(".*" if c == "*" else re.escape(c) for c in pattern)
        return re.match(rx + ("$" if anchored else ""), path) is not None

    def allowed(self, token: str, path: str = "/") -> bool:
        rules, _ = self._rules_for(token)
        best = None
        for allow, pat in rules:
            if pat == "":
                continue
            if self._match(pat, path):
                ln = len(pat)
                if best is None or ln > best[0] or (ln == best[0] and allow):
                    best = (ln, allow)
        return True if best is None else best[1]


# --------------------------------------------------------------------------- report

class Report:
    def __init__(self):
        self.items = []
        self.data = {}

    def add(self, cat, status, title, detail="", fix="", ref=None):
        self.items.append({"category": cat, "status": status, "title": title,
                           "detail": detail, "fix": fix, "ref": ref})

    def scores(self):
        out = {}
        for key, _name in CATEGORIES:
            vals = [{"pass": 1.0, "warn": 0.5, "fail": 0.0}[i["status"]]
                    for i in self.items if i["category"] == key and i["status"] in ("pass", "warn", "fail")]
            out[key] = round(100 * sum(vals) / len(vals)) if vals else None
        present = [v for v in out.values() if v is not None]
        out["overall"] = round(sum(present) / len(present)) if present else 0
        return out


def short(u: str, n: int = 90) -> str:
    return u if len(u) <= n else u[: n - 1] + "…"


def plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


# --------------------------------------------------------------------------- audit

class Auditor:
    def __init__(self, args):
        self.args = args
        self.f = Fetcher(ua=args.user_agent, timeout=args.timeout, insecure=args.insecure)
        self.rep = Report()
        self.server = None
        self.mode = "live"
        self.base = None
        self.site_url = None

    # ---- setup
    def setup(self):
        t = self.args.target
        if os.path.isdir(t):
            self.server, self.base = serve_directory(t)
            self.base += "/"
            self.mode = "folder"
        else:
            if not re.match(r"^https?://", t):
                t = "https://" + t
            self.base = t if urlparse(t).path else t + "/"
            host = urlparse(self.base).hostname or ""
            if host in LOCAL_HOSTS or host.endswith((".local", ".localhost", ".test")):
                self.mode = "local"
        self.site_url = self.args.site_url.rstrip("/") if self.args.site_url else None

    @property
    def is_live(self):
        return self.mode == "live"

    def origin(self, u):
        p = urlparse(u)
        return "%s://%s" % (p.scheme, p.netloc)

    def root(self, path):
        return urljoin(self.origin(self.base) + "/", path.lstrip("/"))

    # ---- main
    def run(self):
        self.setup()
        rep, f = self.rep, self.f
        home = f.get(self.base)
        if home.ok and home.looks_html is False and "html" not in home.content_type:
            pass
        page = Page(home) if home.ok else None

        if not self.site_url:
            if self.is_live:
                self.site_url = self.origin(home.final_url if home.ok else self.base)
            elif page:
                guess = (page.canonicals[:1] or [page.meta.get("og:url", "")])[0]
                if guess.startswith("http") and urlparse(guess).hostname not in LOCAL_HOSTS:
                    self.site_url = self.origin(guess)
        if not self.is_live and self.site_url:
            f.rewrite = (self.origin(self.site_url), self.origin(self.base))

        rep.data.update({
            "target": self.args.target, "mode": self.mode, "fetched_url": self.base,
            "site_url": self.site_url, "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "tool_version": VERSION,
        })

        self.check_home_fetch(home)
        if not page:
            return rep
        self.page = page
        robots = self.check_robots()
        sitemap_urls = self.check_sitemap(robots)
        self.check_onpage(page, home=True)
        self.check_social(page)
        self.check_icons(page, robots)
        self.check_schema(page)
        self.check_llms_txt()
        self.check_llmo(page, home)
        self.check_ai_bots(robots)
        self.check_engines(page, home)
        self.check_perf(page, home)
        self.check_sample_pages(page, sitemap_urls)
        if self.args.psi:
            self.check_psi()
        self.build_serp(page)
        return rep

    # ---- crawl / transport
    def check_home_fetch(self, home):
        rep = self.rep
        if home.error:
            rep.add("crawl", "fail", "Homepage could not be fetched", home.error,
                    "Make sure the site is reachable (DNS, TLS certificate, server running).")
            return
        if home.status != 200:
            rep.add("crawl", "fail", "Homepage returns HTTP %d" % home.status, home.final_url,
                    "The homepage must return 200 to be indexed.")
        else:
            rep.add("crawl", "pass", "Homepage returns 200", home.final_url)
        if "html" not in home.content_type:
            rep.add("crawl", "warn", "Homepage Content-Type is '%s'" % home.content_type, "",
                    "Serve HTML pages as text/html; charset=utf-8.")
        if home.chain:
            hops = " → ".join("%s (%d)" % (short(u, 60), s) for u, s in home.chain) + " → " + short(home.final_url, 60)
            temp = [s for _, s in home.chain if s in (302, 303, 307)]
            if len(home.chain) > 1:
                rep.add("crawl", "warn", "Homepage redirect chain has %d hops" % len(home.chain), hops,
                        "Redirect straight to the final URL in one 301/308 hop.")
            elif temp:
                rep.add("crawl", "warn", "Homepage uses a temporary (%d) redirect" % temp[0], hops,
                        "Use a permanent 301/308 redirect so ranking signals consolidate.")
            else:
                rep.add("crawl", "info", "Homepage redirects once", hops)
        xrt = home.header("x-robots-tag").lower()
        if "noindex" in xrt or "none" in xrt:
            rep.add("crawl", "fail", "X-Robots-Tag header blocks indexing", "X-Robots-Tag: " + xrt,
                    "Remove the noindex X-Robots-Tag header (often set on staging/preview deployments).")

        if not self.is_live:
            rep.add("crawl", "info", "HTTPS, redirects and www/non-www consolidation are checked on the live site",
                    "Mode: %s. Re-run against the production URL after deploying." % self.mode)
        else:
            final = urlparse(home.final_url)
            if final.scheme != "https":
                rep.add("crawl", "fail", "Site is not served over HTTPS", home.final_url,
                        "Install a TLS certificate and redirect all http:// traffic to https://.")
            else:
                rep.add("crawl", "pass", "Served over HTTPS")
                http_r = self.f.get("http://%s/" % final.netloc, follow=False)
                loc = http_r.header("location")
                if http_r.error:
                    rep.add("crawl", "info", "http:// version not reachable", http_r.error)
                elif http_r.status in (301, 308) and loc.startswith("https://"):
                    rep.add("crawl", "pass", "http:// permanently redirects to https://")
                elif http_r.status in (302, 307) and loc.startswith("https://"):
                    rep.add("crawl", "warn", "http:// uses a temporary redirect (%d)" % http_r.status, loc,
                            "Use a 301/308 permanent redirect from http:// to https://.")
                elif http_r.status == 200:
                    rep.add("crawl", "fail", "http:// serves content without redirecting to https://", "",
                            "Force HTTPS with a 301 redirect (host setting or server config).")
            host = final.hostname or ""
            alt = host[4:] if host.startswith("www.") else "www." + host
            if host.count(".") >= 1:
                ar = self.f.get("https://%s/" % alt)
                if ar.error:
                    rep.add("crawl", "info", "%s does not resolve or respond" % alt, ar.error,
                            "Optional: add DNS for %s and 301-redirect it to %s so typed URLs work." % (alt, host))
                elif urlparse(ar.final_url).hostname == host:
                    rep.add("crawl", "pass", "www / non-www versions consolidate to %s" % host)
                elif ar.ok:
                    rep.add("crawl", "warn", "Both %s and %s serve the site" % (host, alt),
                            "Duplicate hosts split ranking signals.",
                            "301-redirect %s to %s and keep canonicals pointing at %s." % (alt, host, host))

        nf = self.f.get(self.root("/visibility-audit-%s" % uuid.uuid4().hex[:10]))
        if nf.status in (404, 410):
            rep.add("crawl", "pass", "Unknown URLs return a real 404")
        elif nf.status == 200:
            rep.add("crawl", "warn", "Unknown URLs return 200 (soft 404)",
                    "A random URL returned 200 — typical of single-page-app fallbacks.",
                    "Configure the host to return status 404 for unknown routes (e.g. a 404.html page).")
        elif nf.status in (301, 302, 307, 308) or nf.chain:
            rep.add("crawl", "warn", "Unknown URLs redirect instead of returning 404", nf.final_url,
                    "Return 404 for missing pages; blanket redirects to the homepage are treated as soft 404s.")

    def check_robots(self):
        rep = self.rep
        r = self.f.get(self.root("/robots.txt"))
        rep.data["robots_txt"] = {"url": self.root("/robots.txt"), "status": r.status, "exists": r.exists_as_file()}
        if r.status >= 500:
            rep.add("crawl", "fail", "robots.txt returns HTTP %d" % r.status, "",
                    "Google treats a 5xx robots.txt as 'disallow everything'. Fix the server error.")
            return Robots("")
        if not r.exists_as_file():
            note = " (the server returned an HTML page instead — SPA fallback)" if r.ok and r.looks_html else ""
            rep.add("crawl", "warn", "No robots.txt" + note, "",
                    "Add /robots.txt with an Allow rule and a Sitemap: line (generate.py robots).")
            return Robots("")
        text = r.text
        robots = Robots(text)
        rep.data["robots_txt"]["content"] = text[:4000]
        if not robots.allowed("Googlebot", "/") or not robots.allowed("Bingbot", "/"):
            blocked = [b for b in ("Googlebot", "Bingbot") if not robots.allowed(b, "/")]
            rep.add("crawl", "fail", "robots.txt blocks %s from the homepage" % " & ".join(blocked),
                    "Search engines cannot crawl the site.",
                    "Remove 'Disallow: /' (a common leftover from staging).")
        else:
            rep.add("crawl", "pass", "robots.txt allows search engines")
        if robots.sitemaps:
            bad = [s for s in robots.sitemaps if not s.startswith("http")]
            if bad:
                rep.add("crawl", "warn", "robots.txt Sitemap: must be an absolute URL", ", ".join(bad),
                        "Use the full URL, e.g. Sitemap: https://example.com/sitemap.xml")
            else:
                rep.add("crawl", "pass", "robots.txt references the sitemap", ", ".join(robots.sitemaps))
            if self.site_url:
                host = urlparse(self.site_url).hostname
                wrong = [s for s in robots.sitemaps if urlparse(s).hostname not in (host, "www." + str(host), str(host).replace("www.", ""))]
                if wrong:
                    rep.add("crawl", "fail", "robots.txt Sitemap: points to another host", ", ".join(wrong),
                            "Point it at %s/sitemap.xml (stale localhost/staging URLs are a common bug)." % self.site_url)
        else:
            rep.add("crawl", "warn", "robots.txt has no Sitemap: line", "",
                    "Add 'Sitemap: %s/sitemap.xml' so every crawler finds it." % (self.site_url or "https://your-domain"))
        # CSS/JS must be crawlable for rendering
        assets = [self.page.abs(u) for t, u in self.page.p.resource_urls if t in ("link", "script")]
        blocked_assets = [u for u in assets if urlparse(u).netloc == urlparse(self.page.url).netloc
                          and not robots.allowed("Googlebot", urlparse(u).path or "/")]
        if blocked_assets:
            rep.add("crawl", "warn", "robots.txt blocks %s needed for rendering" % plural(len(blocked_assets), "CSS/JS file"),
                    ", ".join(short(u, 60) for u in blocked_assets[:4]),
                    "Allow crawlers to fetch CSS and JS so Google can render the page.")
        return robots

    def check_sitemap(self, robots):
        rep = self.rep
        candidates = [self.f.map(s) for s in robots.sitemaps if s.startswith("http")] or \
                     [self.root(p) for p in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml", "/wp-sitemap.xml")]
        found, urls, child_count, lastmods, errors = None, [], 0, 0, []
        for c in candidates:
            r = self.f.get(c, max_bytes=20_000_000)
            if not r.ok or r.looks_html:
                continue
            body = r.body
            if body[:2] == b"\x1f\x8b":
                try:
                    body = gzip.decompress(body)
                except Exception:
                    pass
            parsed, err = parse_sitemap(body)
            if err:
                errors.append("%s: %s" % (c, err))
                continue
            found = c
            if parsed["kind"] == "index":
                child_count = len(parsed["urls"])
                for child in parsed["urls"][:10]:
                    cr = self.f.get(child, max_bytes=20_000_000)
                    cb = cr.body
                    if cb[:2] == b"\x1f\x8b":
                        try:
                            cb = gzip.decompress(cb)
                        except Exception:
                            pass
                    cp, cerr = parse_sitemap(cb) if cr.ok else (None, "HTTP %d" % cr.status)
                    if cerr:
                        errors.append("%s: %s" % (child, cerr))
                        continue
                    urls.extend(cp["urls"])
                    lastmods += cp["lastmods"]
            else:
                urls, lastmods = parsed["urls"], parsed["lastmods"]
            break
        rep.data["sitemap"] = {"url": found, "url_count": len(urls), "children": child_count, "errors": errors,
                               "sample": urls[:25]}
        if errors:
            rep.add("crawl", "fail", "Sitemap XML errors", "; ".join(errors[:3]),
                    "Fix the XML so it validates against the sitemaps.org schema.")
        if not found:
            if not errors:
                rep.add("crawl", "fail", "No XML sitemap found", "Tried: " + ", ".join(short(c, 50) for c in candidates),
                        "Generate /sitemap.xml listing every indexable page and reference it in robots.txt.")
            return []
        rep.add("crawl", "pass", "XML sitemap found (%s)" % plural(len(urls), "URL"), found +
                (" — index with %s" % plural(child_count, "child sitemap") if child_count else ""))
        if not urls:
            rep.add("crawl", "fail", "Sitemap contains no URLs", found, "List every indexable page.")
            return []
        site_host = urlparse(self.site_url or self.base).hostname or ""
        bare = site_host[4:] if site_host.startswith("www.") else site_host
        hosts = {urlparse(u).hostname for u in urls}
        foreign = sorted(h for h in hosts if h and h not in (site_host,))
        local_like = [h for h in foreign if h in LOCAL_HOSTS or h.endswith((".vercel.app", ".netlify.app", ".pages.dev", ".local"))]
        if local_like:
            rep.add("crawl", "fail", "Sitemap lists URLs on %s" % ", ".join(local_like[:3]),
                    "Sitemap URLs must use the production domain.",
                    "Set the production site URL in your framework config before building the sitemap.")
        elif foreign and self.site_url:
            same_brand = all(h.replace("www.", "") == bare for h in foreign)
            rep.add("crawl", "warn" if same_brand else "fail",
                    "Sitemap URLs use a different host (%s) than the site (%s)" % (", ".join(foreign[:3]), site_host), "",
                    "Use exactly the canonical host (same www / non-www choice) in all sitemap URLs.")
        if any(u.startswith("http://") for u in urls) and (self.site_url or "").startswith("https"):
            rep.add("crawl", "warn", "Sitemap contains http:// URLs", "", "List the https:// URLs only.")
        if len(urls) != len(set(urls)):
            rep.add("crawl", "warn", "Sitemap has %d duplicate URLs" % (len(urls) - len(set(urls))), "", "Deduplicate.")
        pct = int(100 * lastmods / max(1, len(urls)))
        rep.add("crawl", "pass" if pct >= 80 else "info", "%d%% of sitemap URLs have <lastmod>" % pct, "",
                "" if pct >= 80 else "Add accurate <lastmod> dates; Google and Bing use them to schedule recrawls.")
        return urls

    # ---- on-page
    def page_issues(self, page: Page, home=False):
        """Return list of (status, key, message, fix) for a page."""
        out = []
        p, m = page.p, page.meta
        title = p.title or ""
        if not title:
            out.append(("fail", "title", "Missing <title>", "Add a unique, descriptive <title> (50–60 chars)."))
        else:
            px = text_px(title)
            if px > 600:
                out.append(("warn", "title", "Title is %d chars / ~%dpx — Google truncates around 600px" % (len(title), px),
                            "Shorten to ~50–60 characters; put the key topic first."))
            elif len(title) < 20:
                out.append(("warn", "title", "Title is short (%d chars)" % len(title),
                            "Use ~50–60 characters: topic/benefit + brand."))
        if p.titles > 1:
            out.append(("warn", "title", "%d <title> tags" % p.titles, "Keep exactly one <title>."))
        desc = m.get("description", "")
        if not desc:
            out.append(("fail" if home else "warn", "desc", "Missing meta description",
                        "Add a 120–160 character summary; used by Google snippets, social cards and AI answers."))
        elif len(desc) > 165:
            out.append(("warn", "desc", "Meta description is %d chars (truncated after ~155–160)" % len(desc),
                        "Trim to ≤160 characters."))
        elif len(desc) < 70:
            out.append(("warn", "desc", "Meta description is short (%d chars)" % len(desc), "Aim for 120–160 characters."))
        h1s = [t for lvl, t in p.headings if lvl == 1]
        if not h1s:
            out.append(("warn", "h1", "No <h1> heading", "Add one H1 that states the page topic."))
        elif len(h1s) > 1:
            out.append(("warn", "h1", "%d <h1> headings" % len(h1s), "Use a single H1 per page; use H2/H3 for sections."))
        levels = [lvl for lvl, _ in p.headings]
        skips = [(a, b) for a, b in zip(levels, levels[1:]) if b > a + 1]
        if skips:
            out.append(("info", "headings", "Heading levels skip (e.g. H%d → H%d)" % skips[0],
                        "Keep a logical outline (H1 → H2 → H3)."))
        if not p.lang:
            out.append(("warn", "lang", "<html> has no lang attribute", 'Add <html lang="en"> (or your language).'))
        if not any((x.get("name") or "").lower() == "viewport" for x in p.metas):
            out.append(("fail", "viewport", "No viewport meta tag",
                        'Add <meta name="viewport" content="width=device-width, initial-scale=1"> (mobile-first indexing).'))
        if not p.charset:
            out.append(("warn", "charset", "No charset declared", 'Add <meta charset="utf-8"> as the first tag in <head>.'))
        canon = page.canonicals
        if not canon:
            out.append(("warn", "canonical", "No canonical link", 'Add <link rel="canonical" href="https://…/this-page">.'))
        elif len(set(canon)) > 1:
            out.append(("fail", "canonical", "Multiple different canonical links", "Keep exactly one."))
        else:
            raw = page.links_with_rel("canonical")[0].get("href", "")
            if not raw.startswith("http"):
                out.append(("warn", "canonical", "Canonical is relative (%s)" % raw, "Use an absolute https:// URL."))
            c, u = urlparse(canon[0]), urlparse(page.url)
            same_path = (c.path.rstrip("/") or "/") == (u.path.rstrip("/") or "/")
            if self.is_live and (c.netloc != u.netloc or not same_path):
                out.append(("warn" if not home else "fail", "canonical",
                            "Canonical points elsewhere: %s" % short(canon[0], 80),
                            "Canonical should be this page's own preferred URL unless it is a deliberate duplicate."))
            elif not self.is_live and self.site_url and c.netloc and c.hostname != urlparse(self.site_url).hostname:
                out.append(("fail", "canonical", "Canonical uses host %s (expected %s)" % (c.netloc, urlparse(self.site_url).netloc),
                            "Build canonicals from the production site URL."))
            elif not self.is_live and not same_path:
                out.append(("warn", "canonical", "Canonical path differs: %s" % short(canon[0], 80), "Check it is intended."))
        rm = page.robots_meta
        if "noindex" in rm or "none" in rm.split(","):
            out.append(("fail", "noindex", "Page has meta robots noindex", "Remove noindex for pages that should rank."))
        imgs = p.imgs
        no_alt = [i for i in imgs if "alt" not in i]
        if no_alt:
            out.append(("warn", "alt", "%s missing alt attribute" % plural(len(no_alt), "image"),
                        'Describe meaningful images in alt; use alt="" for decorative ones.'))
        if page.url.startswith("https://"):
            mixed = [u for t, u in p.resource_urls if u.startswith("http://")]
            if mixed:
                out.append(("warn", "mixed", "%s loaded over http:// (mixed content)" % plural(len(mixed), "resource"),
                            "Load every resource over https://."))
        hreflangs = [l for l in page.links_with_rel("alternate") if l.get("hreflang")]
        if hreflangs:
            rel = [l["href"] for l in hreflangs if not l.get("href", "").startswith("http")]
            if rel:
                out.append(("warn", "hreflang", "hreflang links must be absolute URLs", "Use full https:// URLs."))
            if not any(l["hreflang"].lower() == "x-default" for l in hreflangs):
                out.append(("info", "hreflang", "hreflang set has no x-default", "Add an x-default alternate."))
        if not m.get("og:image"):
            out.append(("warn", "og", "No og:image", "Add an og:image so shares show a preview."))
        return out

    def check_onpage(self, page: Page, home=True):
        rep = self.rep
        issues = self.page_issues(page, home=True)
        keys = {k for _, k, _, _ in issues}
        for status, key, msg, fix in issues:
            if key == "og":
                continue  # covered in social
            rep.add("onpage", status, "Homepage: " + msg, "", fix)
        p = page.p
        if "title" not in keys:
            rep.add("onpage", "pass", "Title length is good (%d chars)" % len(p.title or ""), p.title or "")
        if "desc" not in keys:
            rep.add("onpage", "pass", "Meta description length is good (%d chars)" % len(page.meta.get("description", "")))
        if "h1" not in keys:
            rep.add("onpage", "pass", "Single H1", next((t for l, t in p.headings if l == 1), ""))
        for key, label in (("lang", "lang attribute set (%s)" % p.lang), ("viewport", "Viewport meta present"),
                           ("canonical", "Canonical link is correct"), ("alt", "All images have alt attributes")):
            if key not in keys:
                rep.add("onpage", "pass", label)
        if "noindex" not in keys:
            rep.add("crawl", "pass", "Homepage is indexable (no noindex)")
        internal = set(page.internal_links({urlparse(page.url).netloc}))
        if len(internal) < 3:
            rep.add("onpage", "warn", "Homepage links to only %s" % plural(len(internal), "internal page"),
                    "Crawlers discover pages through links.",
                    "Link to your key pages from the homepage/navigation with crawlable <a href> links.")

    # ---- social
    def check_social(self, page: Page):
        rep, m = self.rep, page.meta
        og = {k: v for k, v in m.items() if k.startswith(("og:", "twitter:", "article:"))}
        rep.data["social"] = og
        for k, why in (("og:title", "headline of the share card"), ("og:description", "text under the headline"),
                       ("og:url", "canonical URL of the shared page"), ("og:type", "usually 'website'"),
                       ("og:site_name", "brand name on cards")):
            if m.get(k):
                rep.add("social", "pass", "%s present" % k, short(m[k], 120))
            else:
                status = "fail" if k in ("og:title",) else "warn"
                rep.add("social", status, "Missing %s" % k, why, '<meta property="%s" content="…">' % k)
        if m.get("og:url") and page.canonicals and m["og:url"].rstrip("/") != page.canonicals[0].rstrip("/"):
            rep.add("social", "warn", "og:url differs from canonical", "%s vs %s" % (m["og:url"], page.canonicals[0]),
                    "Keep og:url identical to the canonical URL so share counts consolidate.")
        card = m.get("twitter:card", "")
        if card == "summary_large_image":
            rep.add("social", "pass", "twitter:card = summary_large_image")
        elif card:
            rep.add("social", "info", "twitter:card = %s" % card, "",
                    "Use summary_large_image for a big image preview on X.")
        else:
            rep.add("social", "warn", "Missing twitter:card", "X/Twitter shows a small or no preview without it.",
                    '<meta name="twitter:card" content="summary_large_image">')
        img = m.get("og:image") or m.get("og:image:url") or m.get("og:image:secure_url")
        if not img:
            rep.add("social", "fail", "Missing og:image", "Links shared on WhatsApp, LinkedIn, Facebook, Slack, X show no image.",
                    "Add a 1200×630 PNG/JPG og:image with an absolute https:// URL.")
            return
        if not img.startswith("http"):
            rep.add("social", "fail", "og:image is a relative URL (%s)" % img, "Most scrapers require an absolute URL.",
                    "Use the full https:// URL (e.g. set metadataBase / site URL in your framework).")
        url = page.abs(img)
        r = self.f.get(url, max_bytes=12_000_000)
        rep.data["og_image"] = {"url": url, "status": r.status}
        if not r.ok:
            rep.add("social", "fail", "og:image cannot be fetched (HTTP %s)" % (r.status or r.error), url,
                    "Make sure the image URL is public and returns 200.")
            return
        info = image_info(r.body)
        size = int(r.header("content-length") or len(r.body))
        rep.data["og_image"].update(info, bytes=size, content_type=r.content_type)
        if info["format"] in ("png", "jpeg", "webp", "gif"):
            self.rep.data.setdefault("assets", {})["og_image"] = data_uri(r.body, r.content_type or "image/" + info["format"]) \
                if size < 3_000_000 else url
        if info["format"] == "svg":
            rep.add("social", "fail", "og:image is SVG", "Facebook, LinkedIn, X and messengers don't render SVG previews.",
                    "Export a PNG or JPG.")
        elif info["format"] in ("avif",):
            rep.add("social", "warn", "og:image is AVIF", "Not supported by several platforms.", "Use PNG or JPG.")
        elif info["format"] == "webp":
            rep.add("social", "info", "og:image is WebP", "Most platforms support it; PNG/JPG is the safest choice.")
        w, h = info.get("width"), info.get("height")
        if w and h:
            ratio = w / h
            if w < 600 or h < 315:
                rep.add("social", "fail" if w < 200 or h < 200 else "warn", "og:image is small (%d×%d)" % (w, h), "",
                        "Use 1200×630 for sharp large previews.")
            elif abs(ratio - 1.91) > 0.15:
                rep.add("social", "warn", "og:image aspect ratio is %.2f:1 (%d×%d)" % (ratio, w, h),
                        "Platforms crop to ~1.91:1, so parts of the image will be cut off.", "Use 1200×630.")
            else:
                rep.add("social", "pass", "og:image is %d×%d (%s)" % (w, h, info["format"]), url)
        elif info["format"] != "svg":
            rep.add("social", "warn", "Could not read og:image dimensions", "Content-Type: %s" % r.content_type)
        if size > 5_000_000:
            rep.add("social", "fail", "og:image is %.1f MB" % (size / 1e6), "X rejects >5 MB; others time out.",
                    "Compress to well under 1 MB.")
        elif size > 1_000_000:
            rep.add("social", "warn", "og:image is %.1f MB" % (size / 1e6),
                    "Large images load slowly in scrapers and some messengers skip them.", "Compress to under ~600 KB.")
        if url.startswith("http://") and self.is_live:
            rep.add("social", "warn", "og:image uses http://", "", "Serve it over https://.")
        if not m.get("og:image:alt"):
            rep.add("social", "info", "No og:image:alt", "", "Add a short description of the image for accessibility.")
        if not (m.get("og:image:width") and m.get("og:image:height")):
            rep.add("social", "info", "No og:image:width / og:image:height", "",
                    "Declaring dimensions lets Facebook/LinkedIn render the first share without waiting.")

    # ---- icons
    def check_icons(self, page: Page, robots: Robots):
        rep = self.rep
        icons = [l for l in page.p.links if "icon" in l.get("rel", "").lower().split()
                 or l.get("rel", "").lower() == "shortcut icon"]
        apple = page.links_with_rel("apple-touch-icon") + page.links_with_rel("apple-touch-icon-precomposed")
        results = []
        for l in icons[:8]:
            u = page.abs(l.get("href", ""))
            r = self.f.get(u, max_bytes=3_000_000)
            info = image_info(r.body) if r.ok else {"format": None, "width": None, "height": None, "sizes": []}
            results.append({"href": u, "sizes": l.get("sizes", ""), "type": l.get("type", ""), "status": r.status,
                            "ok": r.ok and not r.looks_html, **info})
        rep.data["icons"] = results
        ico = self.f.get(self.root("/favicon.ico"), max_bytes=3_000_000)
        ico_ok = ico.ok and not ico.looks_html
        ico_info = image_info(ico.body) if ico_ok else {}
        if not icons:
            if ico_ok:
                rep.add("icons", "warn", "No <link rel=\"icon\"> in <head> (only /favicon.ico)", "",
                        'Declare icons explicitly: <link rel="icon" href="/favicon.ico" sizes="48x48"> and an SVG/PNG.')
            else:
                rep.add("icons", "fail", "No favicon", "No <link rel=\"icon\"> and /favicon.ico is missing.",
                        "Add favicon.ico (48×48) + icon.svg or 96×96 PNG and link them in <head>.")
        broken = [r for r in results if not r["ok"]]
        for b in broken:
            rep.add("icons", "fail", "Declared icon is broken (HTTP %s)" % b["status"], b["href"], "Fix the path or upload the file.")
        good = [r for r in results if r["ok"]]
        if ico_ok:
            rep.add("icons", "pass", "/favicon.ico exists", "sizes: " + (", ".join("%dx%d" % s for s in ico_info.get("sizes", [])) or str(ico_info.get("format"))))
        else:
            rep.add("icons", "warn", "/favicon.ico missing", "Browsers, RSS readers and some crawlers request it directly.",
                    "Add a favicon.ico (containing 16, 32 and 48 px) at the site root.")

        def google_ok(i):
            if i.get("format") == "svg":
                return True
            dims = list(i.get("sizes") or []) + ([(i["width"], i["height"])] if i.get("width") else [])
            return any(w == h and w >= 48 and w % 48 == 0 for w, h in dims)

        candidates = good + ([dict(ico_info, href=self.root("/favicon.ico"))] if ico_ok else [])
        if any(google_ok(i) for i in candidates):
            rep.add("icons", "pass", "A Google-compatible favicon exists (square, multiple of 48px or SVG)")
        elif candidates:
            dims = ", ".join("%s %sx%s" % (i.get("format"), i.get("width"), i.get("height")) for i in candidates)
            rep.add("icons", "fail", "No favicon meets Google's size rule", dims,
                    "Google search shows your favicon only if it is square and a multiple of 48px (48, 96, 144, 192…) or SVG.")
        if robots.groups:
            for i in candidates:
                path = urlparse(i.get("href", "")).path or "/"
                if not robots.allowed("Googlebot-Image", path) or not robots.allowed("Googlebot", path):
                    rep.add("icons", "fail", "robots.txt blocks the favicon", i.get("href"), "Allow Googlebot to fetch the favicon.")
                    break
        best = None
        for i in sorted(candidates, key=lambda x: (x.get("format") != "svg", -(x.get("width") or 0))):
            best = i
            break
        if best:
            br = self.f.get(best["href"], max_bytes=3_000_000)
            if br.ok:
                ctype = br.content_type or ("image/svg+xml" if best.get("format") == "svg" else "image/x-icon")
                rep.data.setdefault("assets", {})["favicon"] = data_uri(br.body, ctype)
        # apple touch icon
        at_url = page.abs(apple[0]["href"]) if apple else self.root("/apple-touch-icon.png")
        at = self.f.get(at_url, max_bytes=3_000_000)
        if at.ok and not at.looks_html:
            ai = image_info(at.body)
            if ai.get("width") and ai["width"] < 180:
                rep.add("icons", "warn", "apple-touch-icon is %sx%s" % (ai["width"], ai["height"]), at_url, "Use 180×180 PNG.")
            else:
                rep.add("icons", "pass", "apple-touch-icon present (%sx%s)" % (ai.get("width"), ai.get("height")))
            if not apple:
                rep.add("icons", "info", "apple-touch-icon not declared in <head>", "",
                        '<link rel="apple-touch-icon" href="/apple-touch-icon.png">')
        else:
            rep.add("icons", "warn", "No apple-touch-icon", "Used for iOS home screen and by some apps/aggregators.",
                    "Add a 180×180 PNG (non-transparent background) and link it.")
        # manifest
        man = page.links_with_rel("manifest")
        if not man:
            rep.add("icons", "warn", "No web app manifest", "Android/Chrome use it for install icons and theme colour.",
                    'Add /site.webmanifest with name, icons (192 & 512 px) and link rel="manifest".')
        else:
            mu = page.abs(man[0].get("href", ""))
            mr = self.f.get(mu)
            try:
                mj = json.loads(mr.text) if mr.ok else None
            except Exception:
                mj = None
            if not mj:
                rep.add("icons", "fail", "Web manifest is missing or invalid JSON", mu, "Fix the manifest file.")
            else:
                sizes = set()
                for ic in mj.get("icons", []) or []:
                    for s in str(ic.get("sizes", "")).split():
                        sizes.add(s.lower())
                missing = [s for s in ("192x192", "512x512") if s not in sizes]
                if not (mj.get("name") or mj.get("short_name")):
                    rep.add("icons", "warn", "Manifest has no name/short_name", mu, "Add name and short_name.")
                if missing:
                    rep.add("icons", "warn", "Manifest icons missing %s" % ", ".join(missing), mu, "Add 192×192 and 512×512 PNG icons.")
                else:
                    rep.add("icons", "pass", "Web manifest with 192 & 512 icons")
        tc = page.meta.get("theme-color")
        rep.add("icons", "pass" if tc else "info", "theme-color %s" % (tc or "not set"), "",
                "" if tc else '<meta name="theme-color" content="#yourBrandColor"> tints mobile browser UI.')

    # ---- structured data
    def check_schema(self, page: Page):
        rep = self.rep
        nodes, errors = page.jsonld_nodes, page.jsonld_errors
        types = sorted({t for n in nodes for t in node_types(n)})
        rep.data["schema_types"] = types
        for e in errors:
            rep.add("schema", "fail", "Invalid JSON-LD block", e, "Fix the JSON syntax (validate at validator.schema.org).")
        if not nodes:
            rep.add("schema", "fail" if not page.p.itemscope else "warn", "No JSON-LD structured data on homepage",
                    "Microdata found" if page.p.itemscope else "",
                    "Add Organization (or LocalBusiness/Person) + WebSite JSON-LD.")
            return
        rep.add("schema", "pass", "JSON-LD found: " + ", ".join(types))
        for n in nodes:
            ctx = str(n.get("@context", ""))
            if "schema.org" not in ctx:
                rep.add("schema", "warn", "JSON-LD node %s has no schema.org @context" % node_types(n), "",
                        'Add "@context": "https://schema.org".')
                break
        site = [n for n in nodes if "WebSite" in node_types(n)]
        if site and site[0].get("name"):
            rep.add("schema", "pass", "WebSite schema with name \"%s\"" % site[0]["name"],
                    "Google uses this for the site name shown above your result.")
        else:
            rep.add("schema", "warn", "No WebSite schema with a name",
                    "Google picks the site name shown in results from WebSite structured data.",
                    'Add {"@type":"WebSite","name":"Brand","alternateName":"…","url":"https://…/"} on the homepage.')
        orgs = [n for n in nodes if is_org(n)]
        if not orgs:
            rep.add("schema", "warn", "No Organization / LocalBusiness / Person schema",
                    "Entity data feeds Google's knowledge panel and helps AI models identify you.",
                    "Add Organization (or LocalBusiness with address, phone, opening hours) with name, url, logo, sameAs.")
        else:
            o = orgs[0]
            missing = [k for k in ("name", "url", "logo") if not o.get(k) and not (k == "logo" and o.get("image"))]
            if "Person" in node_types(o):
                missing = [k for k in missing if k != "logo"]
            if missing:
                rep.add("schema", "warn", "%s schema missing %s" % (node_types(o)[0], ", ".join(missing)), "",
                        "Add the missing properties (logo: square, ≥112px, crawlable).")
            else:
                rep.add("schema", "pass", "%s schema has name, url, logo" % node_types(o)[0])
            if not o.get("sameAs"):
                rep.add("schema", "warn", "%s schema has no sameAs links" % node_types(o)[0],
                        "sameAs ties your site to your social/Wikipedia/Google Business profiles (entity disambiguation).",
                        'Add "sameAs": ["https://www.linkedin.com/company/…", "https://www.instagram.com/…"].')
            if any("LocalBusiness" in t or t.endswith("Business") for t in node_types(o)) and not o.get("address"):
                rep.add("schema", "warn", "LocalBusiness without address", "", "Add PostalAddress, telephone, openingHours, geo.")
        rep.add("schema", "info", "Validate rich results", "https://search.google.com/test/rich-results?url=" +
                quote(self.site_url or self.base, safe=""))

    # ---- llms.txt
    def check_llms_txt(self):
        rep = self.rep
        r = self.f.get(self.root("/llms.txt"))
        info = {"url": self.root("/llms.txt"), "exists": r.exists_as_file()}
        rep.data["llms_txt"] = info
        if not r.exists_as_file():
            note = " (server returned an HTML fallback page)" if r.ok and r.looks_html else ""
            rep.add("llmo", "warn", "No /llms.txt" + note,
                    "llms.txt is a proposed standard: a Markdown map of your site for AI assistants and agents. "
                    "Cheap to add; adoption by AI crawlers is still uneven.",
                    "Generate a draft with generate.py llms, then curate it.")
        else:
            text = r.text
            info["content"] = text[:6000]
            lines = [l for l in text.splitlines() if l.strip()]
            problems = []
            if not lines or not re.match(r"^#\s+\S", lines[0]):
                problems.append("first line must be an H1 (# Site name)")
            if not any(l.startswith(">") for l in lines[:6]):
                problems.append("no '> summary' blockquote under the H1")
            h2 = [l for l in lines if re.match(r"^##\s+\S", l)]
            if not h2:
                problems.append("no '## Section' headings with link lists")
            links = re.findall(r"\[([^\]]+)\]\(([^)\s]+)\)", text)
            info.update(sections=len(h2), links=len(links))
            if not links:
                problems.append("no Markdown links")
            if "html" in r.content_type:
                problems.append("served as %s (use text/plain or text/markdown)" % r.content_type)
            if problems:
                rep.add("llmo", "warn", "llms.txt exists but: " + "; ".join(problems), info["url"],
                        "Follow llmstxt.org: H1 name, > summary, ## sections of '- [Title](url): note' links.")
            else:
                rep.add("llmo", "pass", "llms.txt is well-formed (%s, %s)" % (plural(len(h2), "section"), plural(len(links), "link")))
            broken = []
            for _t, href in links[:12]:
                u = urljoin(self.root("/llms.txt"), href)
                lr = self.f.get(u, max_bytes=200_000)
                if not lr.ok:
                    broken.append("%s (%s)" % (short(href, 60), lr.status or lr.error))
            if broken:
                rep.add("llmo", "fail", "llms.txt has %s" % plural(len(broken), "broken link"), "; ".join(broken[:5]),
                        "Fix or remove the dead links.")
            elif links:
                rep.add("llmo", "pass", "llms.txt links resolve (checked %d)" % min(12, len(links)))
            rel = [h for _t, h in links if not h.startswith("http")]
            if rel:
                rep.add("llmo", "info", "llms.txt uses %s" % plural(len(rel), "relative link"), "", "Absolute URLs are safest for agents.")
        full = self.f.get(self.root("/llms-full.txt"), max_bytes=300_000)
        rep.add("llmo", "pass" if full.exists_as_file() else "info",
                "/llms-full.txt %s" % ("present" if full.exists_as_file() else "not present"), "",
                "" if full.exists_as_file() else "Optional: full Markdown content of key pages in one file (useful for docs/product sites).")

    # ---- LLMO page-level
    def check_llmo(self, page: Page, home: Response):
        rep, p = self.rep, page.p
        words = page.words
        spa = re.search(rb'<div[^>]+id=["\'](root|app|__next|__nuxt|svelte)["\'][^>]*>\s*</div>', home.body[:200000], re.I)
        rep.data["raw_html_words"] = words
        if words < 80:
            rep.add("llmo", "fail", "Only %d words of text in the raw HTML" % words,
                    ("Empty app root element found — content is rendered by JavaScript. " if spa else "") +
                    "GPTBot, ClaudeBot, PerplexityBot and most AI crawlers do not run JavaScript, and Google renders it late.",
                    "Use server-side rendering or static generation/prerendering so the HTML contains the content.")
        elif words < 250:
            rep.add("llmo", "warn", "Thin raw-HTML content on homepage (%d words)" % words, "",
                    "Explain clearly in text who you are, what you offer, where, and for whom.")
        else:
            rep.add("llmo", "pass", "Content is present in server HTML (%d words)" % words)
        if "main" in p.landmarks:
            rep.add("llmo", "pass", "Semantic landmarks: " + ", ".join(sorted(p.landmarks)))
        else:
            rep.add("llmo", "warn", "No <main> landmark", "Semantic HTML helps parsers separate content from chrome.",
                    "Wrap primary content in <main>; use <header>, <nav>, <footer>, <article>.")
        hosts = {urlparse(page.url).netloc}
        links = [(a.get("href", "").lower(), t.lower()) for a, t in p.anchors]
        about_kw = ("about", "despre", "uber-uns", "ueber-uns", "a-propos", "chi-siamo", "sobre", "over-ons", "team", "company")
        contact_kw = ("contact", "kontakt", "contacto", "contatti", "impressum")
        has_about = any(any(k in h or k in t for k in about_kw) for h, t in links)
        has_contact = any(any(k in h or k in t for k in contact_kw) or h.startswith(("mailto:", "tel:")) for h, t in links)
        if has_about and has_contact:
            rep.add("llmo", "pass", "About and contact information linked from homepage")
        else:
            miss = [n for n, ok in (("About page", has_about), ("contact details", has_contact)) if not ok]
            rep.add("llmo", "warn", "No link to " + " or ".join(miss) + " found on homepage",
                    "AI answers and Google's quality systems lean on clear who/where/contact signals (E-E-A-T).",
                    "Link an About page and contact details (address/phone/email) from the header or footer.")
        q = [t for _l, t in p.headings if t.strip().endswith("?")]
        rep.add("llmo", "pass" if q else "info",
                "%s phrased as questions" % plural(len(q), "heading"),
                "; ".join(short(x, 60) for x in q[:3]),
                "" if q else "Question-style headings with direct answers (FAQ sections) are easy for answer engines to quote.")
        rm = page.robots_meta
        if "noai" in rm or "noimageai" in rm:
            rep.add("llmo", "info", "Page sets noai/noimageai robots directives", rm,
                    "Non-standard; only some crawlers honour it. Remove if you want AI visibility.")
        if "nosnippet" in rm or "max-snippet:0" in rm:
            rep.add("llmo", "warn", "nosnippet / max-snippet:0 set", rm,
                    "This hides your text from Google snippets AND from AI Overviews/AI Mode.")
        has_date = any(k in page.meta for k in ("article:modified_time", "article:published_time")) or \
            any(n.get("dateModified") or n.get("datePublished") for n in page.jsonld_nodes)
        rep.add("llmo", "info", "Freshness dates %s" % ("declared" if has_date else "not declared on homepage"), "",
                "" if has_date else "On articles/key pages, expose datePublished/dateModified (JSON-LD) and show 'Updated on'.")

    def check_ai_bots(self, robots: Robots):
        rep = self.rep
        rows = []
        for token, owner, purpose, kind in AI_BOTS:
            allowed = robots.allowed(token, "/") if robots.groups else True
            rows.append({"bot": token, "owner": owner, "purpose": purpose, "kind": kind, "robots_allowed": allowed,
                         "explicit_rule": robots.explicit(token) if robots.groups else False, "http": None})
        if self.is_live:
            base = self.f.get(self.base)
            results = {}

            def probe(name):
                results[name] = self.f.get(self.base, ua=BOT_UAS[name], max_bytes=300_000, use_cache=False)

            threads = [threading.Thread(target=probe, args=(n,)) for n in BOT_UAS]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            for row in rows:
                r = results.get(row["bot"])
                if r is None:
                    continue
                challenge = bool(re.search(rb"cf-chl|challenge-platform|Just a moment\.\.\.|Attention Required|captcha",
                                           r.body[:60000], re.I))
                blocked = r.error is not None or r.status in (401, 403, 406, 429, 451, 503) or \
                    (challenge and not re.search(rb"challenge-platform", base.body[:60000]))
                row["http"] = "error" if r.error else ("challenge" if challenge and r.status != 200 else r.status)
                row["http_blocked"] = blocked
        rep.data["ai_bots"] = rows
        s_block = [r["bot"] for r in rows if r["kind"] == "search" and not r["robots_allowed"]]
        t_block = [r["bot"] for r in rows if r["kind"] == "training" and not r["robots_allowed"]]
        if s_block:
            rep.add("llmo", "fail", "robots.txt blocks AI search crawlers: " + ", ".join(s_block),
                    "These bots fetch pages to cite them in ChatGPT, Claude, Perplexity, Copilot and Siri answers.",
                    "Allow them in robots.txt (generate.py robots writes a sensible policy).")
        else:
            rep.add("llmo", "pass", "robots.txt allows AI search/assistant crawlers")
        if t_block:
            rep.add("llmo", "info", "robots.txt blocks training crawlers: " + ", ".join(t_block),
                    "A business choice: blocking these does not remove you from AI search answers, but models learn less about your brand.")
        http_blocked = [r["bot"] for r in rows if r.get("http_blocked")]
        if http_blocked:
            rep.add("llmo", "warn", "Server/CDN refuses requests with bot user-agents: " + ", ".join(http_blocked),
                    "Detected 403/429/503 or a challenge page when using those user-agents (some CDNs also verify bot IPs, "
                    "so spoofed requests can be blocked while real bots pass).",
                    "Check Cloudflare → Security → Bots / AI Crawl Control, or your WAF, and allow the crawlers you want.")
        elif self.is_live:
            rep.add("llmo", "pass", "Server responds normally to search & AI crawler user-agents")

    # ---- engines
    def check_engines(self, page: Page, home: Response):
        rep, m = self.rep, page.meta
        body = home.text
        dns_txt = ""
        if self.is_live and shutil.which("dig"):
            host = urlparse(home.final_url).hostname or ""
            apex = host[4:] if host.startswith("www.") else host
            try:
                dns_txt = subprocess.run(["dig", "+short", "TXT", apex], capture_output=True, text=True, timeout=8).stdout
            except Exception:
                dns_txt = ""
        g = m.get("google-site-verification") or ("google-site-verification=" in dns_txt and "DNS TXT")
        b = m.get("msvalidate.01")
        bing_file = self.f.get(self.root("/BingSiteAuth.xml")) if self.is_live else None
        if bing_file is not None and bing_file.exists_as_file():
            b = b or "BingSiteAuth.xml"
        if not self.is_live:
            rep.add("engines", "info", "Search Console / Bing verification happens after launch",
                    "Run the launch skill (/site-visibility:launch) once the site is live.")
        else:
            rep.add("engines", "pass" if g else "warn",
                    "Google Search Console verification %s" % ("detected (%s)" % ("meta tag" if g is not True and g != "DNS TXT" else g) if g else "not detected"),
                    "" if g else "Verification by HTML file, GA or GTM can't be detected from outside.",
                    "" if g else "Add a Domain property in Search Console (DNS TXT), then submit the sitemap.")
            rep.add("engines", "pass" if b else "warn",
                    "Bing Webmaster Tools verification %s" % ("detected" if b else "not detected"),
                    "" if b else "Bing powers Copilot and DuckDuckGo results and feeds ChatGPT search.",
                    "" if b else "Add the site in Bing Webmaster Tools (fastest: import from Google Search Console).")
        others = [k for k in ("yandex-verification", "facebook-domain-verification", "p:domain_verify", "ahrefs-site-verification")
                  if m.get(k)]
        if others:
            rep.add("engines", "info", "Other verifications: " + ", ".join(others))
        analytics = []
        for name, pat in (("Google Analytics 4", r"googletagmanager\.com/gtag/js|gtag\(\s*['\"]config['\"]\s*,\s*['\"]G-"),
                          ("Google Tag Manager", r"googletagmanager\.com/gtm\.js|GTM-[A-Z0-9]+"),
                          ("Plausible", r"plausible\.io/js|data-domain="), ("Fathom", r"usefathom\.com"),
                          ("Umami", r"umami"), ("Matomo", r"matomo|piwik"), ("Vercel Analytics", r"/_vercel/insights|va\.vercel-scripts"),
                          ("Cloudflare Web Analytics", r"cloudflareinsights\.com"), ("Microsoft Clarity", r"clarity\.ms"),
                          ("PostHog", r"posthog"), ("Simple Analytics", r"simpleanalytics"), ("Hotjar", r"hotjar"),
                          ("Meta Pixel", r"connect\.facebook\.net/.+/fbevents\.js")):
            if re.search(pat, body, re.I):
                analytics.append(name)
        rep.data["analytics"] = analytics
        if analytics:
            rep.add("engines", "pass", "Analytics detected: " + ", ".join(analytics))
        else:
            rep.add("engines", "warn" if self.is_live else "info", "No analytics detected in the HTML",
                    "You won't see traffic from search or AI referrals.",
                    "Add GA4, Plausible, Fathom, Umami or Cloudflare Web Analytics (respect cookie consent rules).")
        rep.add("engines", "info", "IndexNow (Bing, Yandex, Seznam, Naver)", "Instant indexing pings for new/changed URLs.",
                "Host a key file and ping on deploy — see generate.py indexnow-key / indexnow.")

    # ---- perf
    def check_perf(self, page: Page, home: Response):
        rep = self.rep
        size_kb = len(home.body) / 1024
        rep.data["html_kb"] = round(size_kb, 1)
        if self.is_live:
            t = home.elapsed
            rep.add("perf", "pass" if t < 0.8 else "warn" if t < 1.8 else "fail",
                    "Homepage response time %.2fs" % t, "Single request from this machine incl. redirects.",
                    "" if t < 0.8 else "Use a CDN/static hosting and cache HTML; aim for TTFB < 0.8s.")
            enc = self.f.get(self.base, accept_encoding="br, gzip", max_bytes=2048, use_cache=False).header("content-encoding")
            rep.add("perf", "pass" if enc else "warn", "Compression: %s" % (enc or "none"), "",
                    "" if enc else "Enable Brotli or gzip compression on the server/CDN.")
            hsts = home.header("strict-transport-security")
            rep.add("perf", "pass" if hsts else "warn", "HSTS header %s" % ("set" if hsts else "missing"), hsts,
                    "" if hsts else "Add Strict-Transport-Security: max-age=31536000; includeSubDomains")
            sec = [h for h in ("content-security-policy", "x-content-type-options", "referrer-policy", "permissions-policy")
                   if home.header(h)]
            rep.add("perf", "info", "Security headers: %s" % (", ".join(sec) or "none of CSP / nosniff / referrer-policy"), "",
                    "" if len(sec) >= 2 else "Add X-Content-Type-Options: nosniff and Referrer-Policy: strict-origin-when-cross-origin.")
        rep.add("perf", "pass" if size_kb < 500 else "warn", "HTML size %.0f KB" % size_kb, "",
                "" if size_kb < 500 else "Large HTML (often inlined data/JSON) slows crawling and rendering.")
        if page.p.blocking_head_scripts > 2:
            rep.add("perf", "warn", "%d render-blocking scripts in <head>" % page.p.blocking_head_scripts, "",
                    "Add defer/async or move scripts to the end of <body>.")
        nodim = [i for i in page.p.imgs if not (i.get("width") and i.get("height"))]
        if nodim:
            rep.add("perf", "info", "%s without width/height" % plural(len(nodim), "image"), "",
                    "Set width/height (or aspect-ratio) to avoid layout shift (CLS).")
        if self.is_live:
            rep.add("perf", "info", "Core Web Vitals", "https://pagespeed.web.dev/analysis?url=" + quote(home.final_url, safe=""),
                    "Re-run with --psi to pull Lighthouse scores and field data automatically.")

    def check_psi(self):
        if not self.is_live:
            return
        url = self.site_url or self.base
        api = ("https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=%s&strategy=mobile"
               "&category=performance&category=seo&category=accessibility&category=best-practices") % quote(url, safe="")
        if os.environ.get("PSI_API_KEY"):
            api += "&key=" + os.environ["PSI_API_KEY"]
        old = self.f.timeout
        self.f.timeout = 120
        r = self.f.get(api, max_bytes=30_000_000, use_cache=False)
        self.f.timeout = old
        try:
            d = json.loads(r.text)
        except Exception:
            self.rep.add("perf", "info", "PageSpeed Insights unavailable", r.error or "HTTP %s" % r.status)
            return
        if "error" in d:
            self.rep.add("perf", "info", "PageSpeed Insights error", d["error"].get("message", "")[:200],
                         "Set PSI_API_KEY for a higher quota.")
            return
        cats = d.get("lighthouseResult", {}).get("categories", {})
        scores = {k: int(round((v.get("score") or 0) * 100)) for k, v in cats.items()}
        self.rep.data["psi"] = {"scores": scores}
        perf = scores.get("performance", 0)
        self.rep.add("perf", "pass" if perf >= 90 else "warn" if perf >= 50 else "fail",
                     "Lighthouse mobile: " + ", ".join("%s %d" % (k, v) for k, v in scores.items()))
        le = d.get("loadingExperience", {}).get("metrics", {})
        if le:
            parts = []
            for key, label in (("LARGEST_CONTENTFUL_PAINT_MS", "LCP"), ("INTERACTION_TO_NEXT_PAINT", "INP"),
                               ("CUMULATIVE_LAYOUT_SHIFT_SCORE", "CLS")):
                if key in le:
                    parts.append("%s %s (%s)" % (label, le[key].get("percentile"), le[key].get("category", "").lower()))
            overall = d.get("loadingExperience", {}).get("overall_category", "")
            self.rep.data["psi"]["field"] = parts
            self.rep.add("perf", "pass" if overall == "FAST" else "warn", "Real-user Core Web Vitals: " + "; ".join(parts))
        else:
            self.rep.add("perf", "info", "No real-user (CrUX) data yet", "Normal for new or low-traffic sites.")

    # ---- other pages
    def check_sample_pages(self, home_page: Page, sitemap_urls):
        rep = self.rep
        n = self.args.pages
        home_norm = home_page.url.rstrip("/")
        pool = [u for u in sitemap_urls if u.rstrip("/") != home_norm and self.f.map(u).rstrip("/") != home_norm]
        source = "sitemap"
        if not pool:
            pool = [u for u in dict.fromkeys(home_page.internal_links({urlparse(home_page.url).netloc}))
                    if u.rstrip("/") != home_norm and not re.search(r"\.(pdf|jpe?g|png|webp|gif|svg|zip|xml|txt)$", u, re.I)]
            source = "homepage links"
        # spread the sample across the list
        if len(pool) > n:
            step = len(pool) / n
            pool = [pool[int(i * step)] for i in range(n)]
        if not pool or n == 0:
            rep.data["pages"] = []
            return
        results = {}

        def work(u):
            results[u] = self.f.get(u)

        threads = [threading.Thread(target=work, args=(u,)) for u in pool]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        rows, by_issue, titles, descs = [], {}, {}, {}
        rows.append(self.page_row(home_page, home_page.resp))
        titles.setdefault(home_page.p.title or "", []).append(home_page.url)
        descs.setdefault(home_page.meta.get("description", ""), []).append(home_page.url)
        for u in pool:
            r = results[u]
            if not r.ok:
                by_issue.setdefault(("fail", "HTTP error / non-200 status", "Fix or remove these URLs (from %s)." % source), []).append(
                    "%s (%s)" % (short(u, 70), r.status or r.error))
                rows.append({"url": u, "status": r.status or r.error})
                continue
            if r.chain and source == "sitemap":
                by_issue.setdefault(("warn", "Sitemap URL redirects", "List final URLs in the sitemap."), []).append(short(u, 70))
            if "html" not in r.content_type:
                continue
            pg = Page(r)
            rows.append(self.page_row(pg, r))
            titles.setdefault(pg.p.title or "", []).append(u)
            descs.setdefault(pg.meta.get("description", ""), []).append(u)
            for status, key, msg, fix in self.page_issues(pg):
                label = generic_label(msg)
                if key == "noindex" and source == "sitemap":
                    status, label, fix = "fail", "noindex page listed in sitemap", "Remove noindex or drop the URL from the sitemap."
                by_issue.setdefault((status, label, fix), []).append(short(u, 70))
            if pg.words < 80:
                by_issue.setdefault(("warn", "Very little text in raw HTML (JS-rendered?)",
                                     "Server-render or prerender these pages."), []).append(short(u, 70))
        rep.data["pages"] = rows
        checked = len(pool)
        for (status, label, fix), urls in sorted(by_issue.items(), key=lambda kv: ["fail", "warn", "info"].index(kv[0][0])):
            cat = "crawl" if label.startswith(("HTTP", "Sitemap", "noindex")) else "social" if "og:image" in label else "onpage"
            rep.add(cat, status, "Other pages: %s (%d of %d)" % (label, len(urls), checked), "\n".join(urls[:8]), fix)
        dupe_t = {t: us for t, us in titles.items() if t and len(us) > 1}
        dupe_d = {d: us for d, us in descs.items() if d and len(us) > 1}
        if dupe_t:
            t, us = next(iter(dupe_t.items()))
            rep.add("onpage", "warn", "Duplicate titles across %s" % plural(sum(len(v) for v in dupe_t.values()), "page"),
                    "\"%s\" on %s" % (short(t, 60), ", ".join(short(u, 50) for u in us[:3])),
                    "Give every page a unique title.")
        else:
            rep.add("onpage", "pass", "Titles are unique across %s" % plural(len(rows), "sampled page"))
        if dupe_d:
            rep.add("onpage", "warn", "Duplicate meta descriptions across %s" % plural(sum(len(v) for v in dupe_d.values()), "page"),
                    "", "Write a unique description per page.")
        if not by_issue:
            rep.add("onpage", "pass", "%s from %s look healthy" % (plural(checked, "sampled page"), source))

    def page_row(self, pg: Page, r: Response):
        return {"url": pg.url, "status": r.status, "title": pg.p.title, "title_len": len(pg.p.title or ""),
                "desc_len": len(pg.meta.get("description", "")), "h1": sum(1 for l, _ in pg.p.headings if l == 1),
                "words": pg.words, "canonical": (pg.canonicals or [""])[0], "og_image": bool(pg.meta.get("og:image")),
                "noindex": "noindex" in pg.robots_meta, "schema": sorted({t for n in pg.jsonld_nodes for t in node_types(n)})}

    # ---- SERP preview data
    def build_serp(self, page: Page):
        site = self.site_url or self.origin(page.url)
        u = urlparse(site if not self.is_live else page.url)
        nodes = page.jsonld_nodes
        site_name = next((n.get("name") for n in nodes if "WebSite" in node_types(n) and n.get("name")), None) \
            or page.meta.get("og:site_name") or (u.hostname or "").replace("www.", "")
        crumbs = " › ".join([p for p in urlparse(page.url).path.split("/") if p][:3])
        title = page.p.title or ""
        cut_title, px = "", 0
        for ch in title:
            px += text_px(ch)
            if px > 590:
                cut_title = cut_title.rstrip() + " ..."
                break
            cut_title += ch
        desc = page.meta.get("description", "")
        cut_desc = desc if len(desc) <= 158 else desc[:155].rsplit(" ", 1)[0] + " ..."
        self.rep.data["serp"] = {"site_name": site_name, "display_url": "%s://%s" % (u.scheme, u.netloc) + (" › " + crumbs if crumbs else ""),
                                 "host": u.netloc, "title": cut_title or title, "full_title": title, "title_px": text_px(title),
                                 "description": cut_desc, "full_description": desc,
                                 "og_title": page.meta.get("og:title") or title,
                                 "og_description": page.meta.get("og:description") or desc}


_GENERIC = [
    (r"^Title is \d+ chars / .*truncates", "Title longer than ~600px (truncated in Google)"),
    (r"^Title is short", "Title too short"),
    (r"^\d+ <title> tags", "More than one <title>"),
    (r"^Meta description is \d+ chars \(truncated", "Meta description too long"),
    (r"^Meta description is short", "Meta description too short"),
    (r"^\d+ <h1> headings", "More than one H1"),
    (r"^Heading levels skip", "Heading levels skip"),
    (r"images? missing alt", "Images missing alt attribute"),
    (r"mixed content", "Mixed content (http:// resources)"),
    (r"^Canonical points elsewhere", "Canonical points to another URL"),
    (r"^Canonical path differs", "Canonical path differs from page path"),
    (r"^Canonical uses host", "Canonical uses the wrong host"),
    (r"^Canonical is relative", "Canonical is a relative URL"),
]


def generic_label(msg: str) -> str:
    for pat, label in _GENERIC:
        if re.search(pat, msg):
            return label
    return msg


def data_uri(body: bytes, ctype: str) -> str:
    return "data:%s;base64,%s" % (ctype, base64.b64encode(body).decode("ascii"))


def parse_sitemap(body: bytes):
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        return None, "invalid XML (%s)" % e
    tag = root.tag.split("}")[-1]
    if tag not in ("urlset", "sitemapindex"):
        return None, "root element is <%s>, expected <urlset> or <sitemapindex>" % tag
    urls, lastmods = [], 0
    for child in root:
        loc = lm = None
        for el in child:
            name = el.tag.split("}")[-1]
            if name == "loc" and el.text:
                loc = el.text.strip()
            elif name == "lastmod" and el.text:
                lm = el.text.strip()
        if loc:
            urls.append(loc)
            lastmods += 1 if lm else 0
    return {"kind": "index" if tag == "sitemapindex" else "urlset", "urls": urls, "lastmods": lastmods}, None


# --------------------------------------------------------------------------- output

ICON = {"pass": "✅", "warn": "⚠️", "fail": "❌", "info": "ℹ️"}


def to_markdown(rep: Report) -> str:
    d, s = rep.data, rep.scores()
    out = ["# Site visibility report", "",
           "- **Target:** %s (%s mode)" % (d.get("target"), d.get("mode")),
           "- **Production URL:** %s" % (d.get("site_url") or "unknown — pass --site-url"),
           "- **Generated:** %s" % d.get("generated"),
           "- **Overall score:** %s/100" % s["overall"], "",
           "| Area | Score | ❌ | ⚠️ |", "|---|---|---|---|"]
    for key, name in CATEGORIES:
        items = [i for i in rep.items if i["category"] == key]
        out.append("| %s | %s | %d | %d |" % (name, "–" if s[key] is None else s[key],
                                             sum(i["status"] == "fail" for i in items), sum(i["status"] == "warn" for i in items)))
    serp = d.get("serp")
    if serp:
        out += ["", "## Google result preview", "", "```", serp["site_name"], serp["display_url"], serp["title"],
                serp["description"] or "(no meta description — Google will pick text from the page)", "```"]
    out += ["", "## Fix first", ""]
    prio = [i for i in rep.items if i["status"] == "fail"] + [i for i in rep.items if i["status"] == "warn"]
    for i in prio[:15]:
        out.append("- %s **%s** — %s" % (ICON[i["status"]], i["title"], i["fix"] or i["detail"]))
    for key, name in CATEGORIES:
        items = [i for i in rep.items if i["category"] == key]
        if not items:
            continue
        out += ["", "## %s" % name, ""]
        for i in sorted(items, key=lambda x: ["fail", "warn", "info", "pass"].index(x["status"])):
            line = "- %s %s" % (ICON[i["status"]], i["title"])
            if i["detail"]:
                line += " — " + i["detail"].replace("\n", ", ")
            if i["fix"] and i["status"] != "pass":
                line += "\n  - Fix: " + i["fix"]
            out.append(line)
    bots = d.get("ai_bots")
    if bots:
        out += ["", "## AI & search crawler access", "", "| Bot | Owner | Purpose | robots.txt | HTTP |", "|---|---|---|---|---|"]
        for b in bots:
            out.append("| %s | %s | %s | %s | %s |" % (b["bot"], b["owner"], b["purpose"],
                                                     "allowed" if b["robots_allowed"] else "**blocked**",
                                                     b["http"] if b["http"] is not None else "–"))
    pages = d.get("pages")
    if pages:
        out += ["", "## Sampled pages", "", "| URL | Status | Title len | Desc len | H1 | Words | og:image |", "|---|---|---|---|---|---|---|"]
        for p in pages:
            out.append("| %s | %s | %s | %s | %s | %s | %s |" % (short(p["url"], 70), p.get("status"), p.get("title_len", ""),
                                                            p.get("desc_len", ""), p.get("h1", ""), p.get("words", ""),
                                                            "yes" if p.get("og_image") else "no" if "og_image" in p else ""))
    return "\n".join(out) + "\n"


def to_html(rep: Report) -> str:
    d, s = rep.data, rep.scores()
    e = html.escape
    serp = d.get("serp", {})
    assets = d.get("assets", {})
    fav = assets.get("favicon")
    og = assets.get("og_image")
    host = serp.get("host", "")

    def score_cls(v):
        return "na" if v is None else "good" if v >= 85 else "ok" if v >= 60 else "bad"

    cards = []
    for key, name in CATEGORIES:
        items = [i for i in rep.items if i["category"] == key]
        f_ = sum(i["status"] == "fail" for i in items)
        w_ = sum(i["status"] == "warn" for i in items)
        cards.append('<a class="cat %s" href="#%s"><span class="num">%s</span><span class="lbl">%s</span>'
                     '<span class="cnt">%s</span></a>' % (score_cls(s[key]), key, "–" if s[key] is None else s[key], e(name),
                                                         ("%d fail · %d warn" % (f_, w_)) if (f_ or w_) else "all good"))
    fav_img = '<img src="%s" alt="">' % e(fav) if fav else '<span class="globe">🌐</span>'
    serp_html = """
<div class="serp">
  <div class="serp-site">%s<div><div class="sn">%s</div><div class="su">%s</div></div></div>
  <div class="st">%s</div>
  <div class="sd">%s</div>
</div>""" % (fav_img, e(serp.get("site_name", "")), e(serp.get("display_url", "")), e(serp.get("title", "") or "(no title)"),
             e(serp.get("description") or "No meta description — Google will improvise a snippet from page text."))
    og_img = '<div class="ogimg" style="background-image:url(\'%s\')"></div>' % og if og else '<div class="ogimg empty">No og:image</div>'
    social_html = """
<div class="cards">
 <figure><figcaption>Facebook · LinkedIn · WhatsApp · Slack</figcaption>
  <div class="fb">%s<div class="fbt"><div class="fbh">%s</div><div class="fbtt">%s</div><div class="fbd">%s</div></div></div></figure>
 <figure><figcaption>X (summary_large_image)</figcaption>
  <div class="x">%s<div class="xh">%s</div></div><div class="xt">From %s</div></figure>
</div>""" % (og_img, e(host.upper()), e(serp.get("og_title", "")), e(short(serp.get("og_description", ""), 110)),
             og_img, e(short(serp.get("og_title", ""), 70)), e(host))
    tab_html = """
<div class="favrow">
  <div class="tab">%s<span>%s</span></div>
  <div class="sizes">%s</div>
</div>""" % (fav_img, e(short(serp.get("full_title", ""), 28)),
             "".join('<div><img src="%s" width="%d" height="%d" alt=""><span>%dpx</span></div>' % (e(fav), n, n, n) for n in (16, 32, 48, 96)) if fav else "No favicon found")

    sections = []
    for key, name in CATEGORIES:
        items = [i for i in rep.items if i["category"] == key]
        if not items:
            continue
        rows = []
        for i in sorted(items, key=lambda x: ["fail", "warn", "info", "pass"].index(x["status"])):
            extra = ""
            if i["detail"]:
                det = e(i["detail"])
                det = re.sub(r"(https?://[^\s<,;]+)", r'<a href="\1" target="_blank" rel="noopener">\1</a>', det).replace("\n", "<br>")
                extra += '<div class="det">%s</div>' % det
            if i["fix"] and i["status"] != "pass":
                extra += '<div class="fix"><b>Fix:</b> %s</div>' % e(i["fix"])
            rows.append('<li class="%s"><span class="badge">%s</span><div><div class="tt">%s</div>%s</div></li>'
                        % (i["status"], i["status"].upper(), e(i["title"]), extra))
        sections.append('<section id="%s"><h2>%s <small>%s</small></h2><ul class="items">%s</ul></section>'
                        % (key, e(name), "" if s[key] is None else "%d/100" % s[key], "".join(rows)))
    bots = d.get("ai_bots") or []
    bot_rows = "".join('<tr><td><b>%s</b></td><td>%s</td><td>%s</td><td class="%s">%s</td><td>%s</td></tr>' % (
        e(b["bot"]), e(b["owner"]), e(b["purpose"]), "ok" if b["robots_allowed"] else ("no" if b["kind"] == "search" else "meh"),
        "allowed" if b["robots_allowed"] else "blocked", e(str(b["http"])) if b["http"] is not None else "–") for b in bots)
    pages = d.get("pages") or []
    page_rows = "".join('<tr><td><a href="%s" target="_blank" rel="noopener">%s</a></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
        e(p["url"]), e(short(p["url"], 60)), e(str(p.get("status"))), p.get("title_len", ""), p.get("desc_len", ""),
        p.get("h1", ""), p.get("words", ""), ("yes" if p.get("og_image") else "no") if "og_image" in p else "") for p in pages)

    return TEMPLATE.format(
        title=e("Visibility · " + (host or str(d.get("target")))),
        host=e(host or str(d.get("target"))), mode=e(d.get("mode", "")), site=e(d.get("site_url") or "unknown"),
        gen=e(d.get("generated", "")), overall=s["overall"], ocls=score_cls(s["overall"]),
        cards="".join(cards), serp=serp_html, social=social_html, tab=tab_html, sections="".join(sections),
        bots=bot_rows, pages=page_rows or '<tr><td colspan="7">No other pages sampled</td></tr>')


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--mute:#5f6672;--line:#e3e6eb;--good:#13804b;--ok:#a86500;--bad:#c4291c;--info:#3060c9;
--goodbg:#e7f6ee;--okbg:#fff4e0;--badbg:#fdecea;--infobg:#eaf0fd;--serpT:#1a0dab;--serpU:#202124;--serpD:#4d5156}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#111317;--card:#1a1d23;--ink:#e8eaee;--mute:#9aa3af;--line:#2b3038;
--good:#4cc38a;--ok:#f0b44c;--bad:#ff7a6e;--info:#7fa6ff;--goodbg:#15291f;--okbg:#2e2412;--badbg:#341a18;--infobg:#18213a;--serpT:#99c3ff;--serpU:#dadce0;--serpD:#bdc1c6}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
.wrap{{max-width:1080px;margin:0 auto;padding:28px 16px 80px}}
header{{display:flex;gap:24px;align-items:center;flex-wrap:wrap;margin-bottom:22px}}
.big{{width:96px;height:96px;border-radius:50%;display:grid;place-items:center;font-size:32px;font-weight:700;border:6px solid currentColor}}
.big.good{{color:var(--good)}}.big.ok{{color:var(--ok)}}.big.bad{{color:var(--bad)}}
h1{{margin:0;font-size:26px}}.meta{{color:var(--mute);font-size:13px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;margin-bottom:28px}}
.cat{{display:grid;grid-template-columns:auto 1fr;grid-template-rows:auto auto;column-gap:12px;padding:12px 14px;border-radius:12px;background:var(--card);border:1px solid var(--line);text-decoration:none;color:var(--ink)}}
.cat .num{{grid-row:span 2;font-size:24px;font-weight:700;align-self:center;min-width:44px}}.cat .lbl{{font-weight:600;font-size:14px}}.cat .cnt{{font-size:12px;color:var(--mute)}}
.cat.good .num{{color:var(--good)}}.cat.ok .num{{color:var(--ok)}}.cat.bad .num{{color:var(--bad)}}.cat.na .num{{color:var(--mute)}}
h2{{font-size:18px;margin:34px 0 12px}}h2 small{{color:var(--mute);font-weight:500;font-size:13px;margin-left:6px}}
.panel{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}}
.serp{{max-width:600px;font-family:Arial,sans-serif}}.serp-site{{display:flex;gap:10px;align-items:center;margin-bottom:4px}}
.serp-site img,.serp-site .globe{{width:28px;height:28px;border-radius:50%;background:#f1f3f4;padding:4px;object-fit:contain;display:grid;place-items:center;font-size:16px;border:1px solid var(--line)}}
.sn{{font-size:14px;color:var(--serpU)}}.su{{font-size:12px;color:var(--mute)}}.st{{font-size:20px;color:var(--serpT);line-height:1.3;margin:2px 0 3px}}.sd{{font-size:14px;color:var(--serpD);line-height:1.58}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px;margin-top:6px}}figure{{margin:0}}figcaption{{font-size:12px;color:var(--mute);margin-bottom:6px}}
.ogimg{{aspect-ratio:1.91/1;background:#ccd center/cover no-repeat}}.ogimg.empty{{display:grid;place-items:center;color:#666;font-size:13px;background:repeating-linear-gradient(45deg,#e4e6ea,#e4e6ea 10px,#eef0f3 10px,#eef0f3 20px)}}
.fb{{border:1px solid var(--line);border-radius:4px;overflow:hidden;background:var(--card)}}.fbt{{padding:10px 12px;background:rgba(127,127,127,.08)}}
.fbh{{font-size:12px;color:var(--mute)}}.fbtt{{font-weight:600;margin:2px 0}}.fbd{{font-size:13px;color:var(--mute)}}
.x{{position:relative;border-radius:16px;overflow:hidden;border:1px solid var(--line)}}.xh{{position:absolute;left:10px;bottom:10px;background:rgba(0,0,0,.65);color:#fff;font-size:13px;padding:2px 6px;border-radius:4px;max-width:90%}}.xt{{font-size:13px;color:var(--mute);margin-top:4px}}
.favrow{{display:flex;gap:28px;align-items:center;flex-wrap:wrap}}.tab{{display:flex;gap:8px;align-items:center;background:var(--bg);border:1px solid var(--line);border-radius:10px 10px 0 0;padding:8px 14px;font-size:13px;min-width:240px}}
.tab img{{width:16px;height:16px}}.tab .globe{{font-size:14px}}.sizes{{display:flex;gap:18px;align-items:flex-end}}.sizes div{{display:flex;flex-direction:column;align-items:center;gap:4px;font-size:11px;color:var(--mute)}}
.items{{list-style:none;margin:0;padding:0;background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}}
.items li{{display:grid;grid-template-columns:62px 1fr;gap:12px;padding:11px 14px;border-top:1px solid var(--line)}}.items li:first-child{{border-top:0}}
.badge{{font-size:10px;font-weight:700;letter-spacing:.04em;text-align:center;border-radius:6px;padding:3px 0;height:fit-content}}
.pass .badge{{background:var(--goodbg);color:var(--good)}}.warn .badge{{background:var(--okbg);color:var(--ok)}}.fail .badge{{background:var(--badbg);color:var(--bad)}}.info .badge{{background:var(--infobg);color:var(--info)}}
.tt{{font-weight:550}}.det{{font-size:13px;color:var(--mute);word-break:break-word}}.fix{{font-size:13px;margin-top:3px}}.det a{{color:var(--info)}}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;font-size:13px}}
th,td{{text-align:left;padding:8px 10px;border-top:1px solid var(--line)}}th{{background:rgba(127,127,127,.07);border-top:0}}td a{{color:var(--info)}}
td.ok{{color:var(--good);font-weight:600}}td.no{{color:var(--bad);font-weight:700}}td.meh{{color:var(--ok);font-weight:600}}
.scroll{{overflow-x:auto}}
</style></head><body><div class="wrap">
<header><div class="big {ocls}">{overall}</div><div><h1>{host}</h1>
<div class="meta">Production URL: {site} · mode: {mode} · {gen}</div></div></header>
<div class="grid">{cards}</div>
<h2>How it shows on Google</h2><div class="panel">{serp}</div>
<h2>How it shows when shared</h2><div class="panel">{social}</div>
<h2>Favicon</h2><div class="panel">{tab}</div>
{sections}
<h2 id="bots">Search &amp; AI crawler access</h2><div class="scroll"><table><tr><th>Bot</th><th>Owner</th><th>Used for</th><th>robots.txt</th><th>HTTP</th></tr>{bots}</table></div>
<h2>Sampled pages</h2><div class="scroll"><table><tr><th>URL</th><th>Status</th><th>Title</th><th>Desc</th><th>H1</th><th>Words</th><th>og:image</th></tr>{pages}</table></div>
</div></body></html>
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Audit a website's search, social and AI visibility.")
    ap.add_argument("target", help="Live URL, local dev server URL, or a static build folder")
    ap.add_argument("--site-url", help="Production origin (e.g. https://example.com) when auditing locally")
    ap.add_argument("--pages", type=int, default=12, help="How many extra pages to sample (default 12)")
    ap.add_argument("--out", default="visibility-report", help="Output folder for report files")
    ap.add_argument("--psi", action="store_true", help="Also fetch PageSpeed Insights (slow, live sites only)")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--insecure", action="store_true", help="Skip TLS certificate verification")
    ap.add_argument("--user-agent", default=DEFAULT_UA)
    ap.add_argument("--strict", action="store_true", help="Exit 1 if any check fails (for CI)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    a = Auditor(args)
    try:
        rep = a.run()
    finally:
        if a.server:
            a.server.shutdown()
    os.makedirs(args.out, exist_ok=True)
    scores = rep.scores()
    payload = {"scores": scores, "data": {k: v for k, v in rep.data.items() if k != "assets"}, "items": rep.items}
    with open(os.path.join(args.out, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(to_markdown(rep))
    with open(os.path.join(args.out, "report.html"), "w", encoding="utf-8") as fh:
        fh.write(to_html(rep))
    if not args.quiet:
        print("Site visibility audit — %s (%s mode)" % (args.target, a.mode))
        print("Production URL: %s" % (rep.data.get("site_url") or "unknown (pass --site-url)"))
        print("Overall: %s/100" % scores["overall"])
        for key, name in CATEGORIES:
            items = [i for i in rep.items if i["category"] == key]
            print("  %-32s %5s   fail %d  warn %d" % (name, "–" if scores[key] is None else scores[key],
                                                    sum(i["status"] == "fail" for i in items), sum(i["status"] == "warn" for i in items)))
        fails = [i for i in rep.items if i["status"] == "fail"]
        warns = [i for i in rep.items if i["status"] == "warn"]
        if fails:
            print("\nFailures:")
            for i in fails:
                print("  ✗ [%s] %s" % (i["category"], i["title"]))
        if warns:
            print("\nWarnings:")
            for i in warns:
                print("  ! [%s] %s" % (i["category"], i["title"]))
        print("\nReports: %s/report.html  report.md  report.json" % os.path.abspath(args.out))
    if args.strict and any(i["status"] == "fail" for i in rep.items):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
