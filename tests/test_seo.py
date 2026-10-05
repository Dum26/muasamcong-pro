import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from unittest.mock import patch

from server.seo import PUBLIC_PATHS, head_metadata, site_origin, sitemap_xml
from web_app import WebHandler, run_web_app


class SeoTests(unittest.TestCase):
    def test_configured_origin_and_sitemap(self):
        with patch.dict(os.environ, {"SITE_URL": "https://muasamcong.test"}):
            self.assertEqual(site_origin(), "https://muasamcong.test")
            sitemap = sitemap_xml().decode()
            self.assertEqual(sitemap.count("<url>"), len(PUBLIC_PATHS))
            self.assertIn("https://muasamcong.test/loc-du-lieu-mua-sam-cong", sitemap)
            self.assertNotIn("/health", sitemap)
            self.assertIn('rel="canonical"', head_metadata("/"))

    def test_run_app_host_fallback_and_server_binding(self):
        with patch.dict(os.environ, {"PORT": "8080", "SITE_URL": ""}):
            self.assertEqual(site_origin("muasamcong-pro-abc-as.a.run.app"),
                             "https://muasamcong-pro-abc-as.a.run.app")
            with patch("web_app.ThreadingHTTPServer") as server, \
                 patch("web_app.webbrowser.open") as browser, \
                 patch("web_app.LOT_FILES.close"):
                server.return_value.server_port = 8080
                run_web_app()
                server.assert_called_once_with(("0.0.0.0", 8080), WebHandler)
                browser.assert_not_called()
        with patch.dict(os.environ, {"PORT": "0"}):
            with patch("web_app.ThreadingHTTPServer") as server, \
                 patch("web_app.LOT_FILES.close"):
                server.return_value.server_port = 12345
                run_web_app(open_browser=False)
                server.assert_called_once_with(("127.0.0.1", 0), WebHandler)

    def test_public_http_routes_and_metadata(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), WebHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        try:
            with patch.dict(os.environ, {"SITE_URL": origin}):
                for path, content_type in (("/", "text/html"),
                                           ("/loc-du-lieu-mua-sam-cong", "text/html"),
                                           ("/robots.txt", "text/plain"),
                                           ("/sitemap.xml", "application/xml"),
                                           ("/health", "application/json")):
                    with self.subTest(path=path), urlopen(origin + path) as response:
                        self.assertEqual(response.status, 200)
                        self.assertIn(content_type, response.headers["Content-Type"])
                        body = response.read().decode("utf-8")
                        if content_type == "text/html":
                            self.assertIn('rel="canonical"', body)
                            self.assertEqual(body.count("<h1>"), 1)
                        if path == "/health":
                            self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow")
                        if path == "/robots.txt":
                            self.assertIn("Disallow: /api/", body)
                for old_path, expected in (("/index.html", origin + "/"),
                                           ("/loc-du-lieu-mua-sam-cong.html", origin + "/loc-du-lieu-mua-sam-cong")):
                    with self.subTest(old_path=old_path), urlopen(origin + old_path) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.url, expected)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
