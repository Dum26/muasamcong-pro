import base64
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server.database import reset_db
from web_app import WebHandler


class DocumentHttpTests(unittest.TestCase):
    def test_private_document_routes_and_unconfigured_ai(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {"DATABASE_URL": "sqlite:///" + (Path(folder) / "docs.db").as_posix(),
                   "ENV": "development", "STORAGE_BACKEND": "local", "AI_ENABLED": "false",
                   "JOB_SECRET": "test-job-secret-longer-than-32-characters"}
            with patch.dict(os.environ, env):
                reset_db()
                server = ThreadingHTTPServer(("127.0.0.1", 0), WebHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                root = f"http://127.0.0.1:{server.server_port}"

                def call(path, cookie="", body=None):
                    request = Request(root + path, data=json.dumps(body).encode() if body is not None else None,
                                      headers={"Cookie": cookie, "Content-Type": "application/json"})
                    return urlopen(request)

                def signup(email):
                    with call("/api/auth/register", body={"email": email,
                                      "password": "safe-long-password-123"}) as response:
                        return next(value.split(";", 1)[0] for value in response.headers.get_all("Set-Cookie")
                                    if value.startswith("msc_auth="))

                try:
                    with self.assertRaises(HTTPError) as unauthenticated:
                        call("/api/documents")
                    self.assertEqual(unauthenticated.exception.code, 401)
                    unauthenticated.exception.close()
                    a, b = signup("doc-http-a@example.test"), signup("doc-http-b@example.test")
                    with call("/app/ai", a) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.headers.get("X-Robots-Tag"), "noindex, nofollow")
                    with call("/ai-workspace.css") as response:
                        self.assertEqual(response.status, 200)
                    with call("/api/ai/config", a) as response:
                        self.assertFalse(json.load(response)["configured"])
                    body = {"filename": "HSMT.txt", "mime_type": "text/plain", "tender_code": "IB2600123456",
                            "data": base64.b64encode("Bảo đảm dự thầu 500 triệu đồng".encode()).decode()}
                    with call("/api/documents/upload", a, body) as response:
                        self.assertEqual(response.status, 201)
                        document_id = json.load(response)["document"]["id"]
                    with call(f"/api/documents/{document_id}/process", a, {}) as response:
                        self.assertEqual(json.load(response)["document"]["status"], "ready")
                    with call(f"/api/documents/{document_id}/content", a) as response:
                        self.assertIn("500 triệu", json.load(response)["chunks"][0]["text"])
                    with call(f"/api/documents/{document_id}/download", a) as response:
                        self.assertIn(b"500", response.read())
                    with call("/api/documents?tender_code=IB2600123456", a) as response:
                        self.assertEqual(len(json.load(response)["items"]), 1)
                    with call("/app/documents", a) as response:
                        self.assertEqual(response.status, 200)
                    with call("/api/document-center?source=upload", a) as response:
                        center = json.load(response)
                        self.assertEqual(center["total"], 1)
                        self.assertEqual(center["items"][0]["id"], document_id)
                    with call(f"/api/document-center/upload/{document_id}", a) as response:
                        self.assertEqual(json.load(response)["document"]["filename"], "HSMT.txt")
                    with call("/api/document-center/export?source=upload", a) as response:
                        self.assertEqual(response.status, 200)
                        self.assertTrue(response.read().startswith(b"PK"))
                    with call("/api/documents", b) as response:
                        self.assertEqual(json.load(response)["items"], [])
                    with call("/api/document-center?source=upload", b) as response:
                        self.assertEqual(json.load(response)["total"], 0)
                    with self.assertRaises(HTTPError) as denied_center:
                        call(f"/api/document-center/upload/{document_id}", b)
                    self.assertEqual(denied_center.exception.code, 404)
                    denied_center.exception.close()
                    for path in (f"/api/documents/{document_id}", f"/api/documents/{document_id}/content",
                                 f"/api/documents/{document_id}/download"):
                        with self.assertRaises(HTTPError) as denied:
                            call(path, b)
                        self.assertEqual(denied.exception.code, 404)
                        denied.exception.close()
                    with self.assertRaises(HTTPError) as denied_delete:
                        call(f"/api/documents/{document_id}/delete", b, {})
                    self.assertEqual(denied_delete.exception.code, 404)
                    denied_delete.exception.close()
                    with self.assertRaises(HTTPError) as unconfigured:
                        call("/api/ai/analyze", a, {"document_id": document_id, "operation": "summary"})
                    self.assertEqual(unconfigured.exception.code, 503)
                    unconfigured.exception.close()
                    with patch.dict(os.environ, {"AI_REQUESTS_PER_MINUTE": "1"}), patch(
                            "server.document_http.analyze", return_value={"id": "test", "result": {}}):
                        # A separate account gets its own AI quota.
                        with call("/api/ai/analyze", b, {"document_id": document_id,
                                                         "operation": "summary"}) as response:
                            self.assertEqual(response.status, 200)
                        with self.assertRaises(HTTPError) as limited:
                            call("/api/ai/analyze", b, {"document_id": document_id,
                                                        "operation": "summary"})
                        self.assertEqual(limited.exception.code, 429)
                        limited.exception.close()
                    with call(f"/api/documents/{document_id}/delete", a, {}) as response:
                        self.assertTrue(json.load(response)["ok"])
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
                    reset_db()


if __name__ == "__main__":
    unittest.main()
