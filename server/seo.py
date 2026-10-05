"""Small public-site metadata helpers; SITE_URL is the deployment's real origin."""
from __future__ import annotations

import html
import json
import os
import re
from urllib.parse import urlparse
from xml.sax.saxutils import escape as xml_escape

PUBLIC_PATHS = ("/", "/loc-du-lieu-mua-sam-cong")
SITE_NAME = "MuaSamCong Pro"
DESCRIPTION = ("MuaSamCong Pro hỗ trợ lọc dữ liệu mua sắm công, tra cứu TBMT, "
               "KHLCNT, kết quả lựa chọn nhà thầu và phân tích dữ liệu đấu thầu.")


def site_origin(host: str = "") -> str:
    configured = (os.environ.get("APP_BASE_URL") or os.environ.get("SITE_URL", "")).strip().rstrip("/")
    if configured:
        parsed = urlparse(configured)
        if (parsed.scheme not in {"http", "https"} or not parsed.netloc or
                parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("SITE_URL phải là origin HTTP(S) hợp lệ, không có đường dẫn.")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError("SITE_URL public phải dùng HTTPS.")
        return configured
    # Fallback is only for the desktop server. Production must set SITE_URL.
    if re.fullmatch(r"(?:localhost|127\.0\.0\.1)(?::\d{1,5})?", host, re.I):
        return "http://" + host.lower()
    if os.environ.get("PORT") not in {None, "", "0"} and (
        re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*\.run\.app", host, re.I) or
        re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*\.onrender\.com", host, re.I)
    ):
        return "https://" + host.lower()
    return ""


def absolute_url(path: str, host: str = "") -> str:
    origin = site_origin(host)
    return origin + path if origin else ""


def head_metadata(path: str, host: str = "") -> str:
    url = absolute_url(path, host)
    if not url:
        return ""
    safe_url = html.escape(url, quote=True)
    schema = {"@context": "https://schema.org", "@type": "WebSite",
              "name": SITE_NAME, "url": absolute_url("/", host), "description": DESCRIPTION}
    json_ld = json.dumps(schema, ensure_ascii=False).replace("<", "\\u003c")
    return (f'<link rel="canonical" href="{safe_url}">\n'
            f'  <meta property="og:url" content="{safe_url}">\n'
            f'  <script type="application/ld+json">{json_ld}</script>')


def render_html(source: bytes, path: str, host: str = "") -> bytes:
    return source.replace(b"<!-- SEO_URL_METADATA -->", head_metadata(path, host).encode("utf-8"))


def robots_txt(host: str = "") -> bytes:
    body = ("User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /internal/\n"
            "Disallow: /app\nDisallow: /admin\nDisallow: /login\nDisallow: /register\n"
            "Disallow: /health\n")
    url = absolute_url("/sitemap.xml", host)
    if url:
        body += "\nSitemap: " + url + "\n"
    return body.encode("utf-8")


def sitemap_xml(host: str = "") -> bytes:
    origin = site_origin(host)
    if not origin:
        raise ValueError("Cần cấu hình SITE_URL cho sitemap public.")
    items = "".join(f"<url><loc>{xml_escape(origin + path)}</loc></url>" for path in PUBLIC_PATHS)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + items + '</urlset>\n').encode("utf-8")
