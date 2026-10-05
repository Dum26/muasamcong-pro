import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import ResultRow
from server.auth import register
from server.database import get_db, reset_db, user_notifications, user_document_state
from server.database_adapters import user_stores
from sqlalchemy import select, update
from server.document_center import catalog, compare_uploaded, detail
from server.document_service import delete_document, process_document, upload_document
from server.intelligence import _sync_documents, ingest_row
from server.source_documents import (fetch_source_document, extract_source_document,
    cached_source_file, import_source_for_ai, compare_source_versions)
from server.document_storage import LocalStorageProvider
from server.source.request_manager import SourceRequestManager
from server.source.errors import SourceError
from unittest.mock import Mock


class DocumentCenterTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "DATABASE_URL": "sqlite:///" + (Path(self.folder.name) / "center.db").as_posix(),
            "ENV": "development", "STORAGE_BACKEND": "local"})
        self.env.start()
        reset_db()
        self.first = register("center-a@example.test", "safe-long-password-123")["id"]
        self.second = register("center-b@example.test", "safe-long-password-123")["id"]
        self.uploaded = []

    def tearDown(self):
        for item in self.uploaded:
            delete_document(self.first, item)
        reset_db()
        self.env.stop()
        self.folder.cleanup()

    def upload(self, name, text):
        item = upload_document(self.first, {"filename": name,
            "data": base64.b64encode(text.encode()).decode()})
        self.uploaded.append(item["id"])
        process_document(self.first, item["id"])
        return item["id"]

    def test_private_search_pagination_and_compare_isolation(self):
        first = self.upload("one.txt", "Giá gói thầu 100")
        second = self.upload("two.txt", "Giá gói thầu 200")
        result = catalog(self.first, source="upload", page_size=1)
        self.assertEqual(result["total"], 2)
        self.assertTrue(result["has_more"])
        self.assertEqual(catalog(self.first, query="200")["items"][0]["id"], second)
        self.assertEqual(catalog(self.second, source="upload")["total"], 0)
        self.assertIsNone(detail(self.second, "upload", first))
        self.assertTrue(compare_uploaded(self.first, first, second)["lines"])
        with self.assertRaises(LookupError):
            compare_uploaded(self.second, first, second)

    def test_source_metadata_revisions_without_download(self):
        code = "IB2600123456"
        ingest_row(ResultRow(notify_no=code, package_name="Gói kiểm thử"))
        url = "https://muasamcong.mpi.gov.vn/example/document.pdf"
        item = {"document_name": "Hồ sơ mời thầu", "document_type": "HSMT",
                "source_url": url, "file_size": 100}
        with get_db().engine.begin() as conn:
            _sync_documents(conn, code, [item], "2026-09-29T01:00:00+00:00")
            _sync_documents(conn, code, [item], "2026-09-29T02:00:00+00:00")
        found = catalog(self.first, source="egp")
        self.assertEqual(found["total"], 1)
        self.assertEqual(found["items"][0]["version"], 1)
        self.assertTrue(found["items"][0]["is_new"])
        detail(self.first, "egp", found["items"][0]["id"])
        self.assertFalse(catalog(self.first, source="egp")["items"][0]["is_new"])
        with get_db().engine.begin() as conn:
            conn.execute(update(user_document_state).where(
                user_document_state.c.user_id == self.first,
                user_document_state.c.document_id == found["items"][0]["id"])
                .values(last_viewed_at="2026-09-29T02:30:00+00:00"))
        item["file_size"] = 200
        with get_db().engine.begin() as conn:
            _sync_documents(conn, code, [item], "2026-09-29T03:00:00+00:00")
        self.assertTrue(catalog(self.first, source="egp")["items"][0]["is_new"])
        result = detail(self.first, "egp", found["items"][0]["id"])
        self.assertEqual(result["document"]["version"], 2)
        self.assertEqual(len(result["versions"]), 2)
        self.assertEqual(result["versions"][0]["version"], 2)
        self.assertFalse(catalog(self.first, source="egp")["items"][0]["is_new"])

    def test_same_type_files_have_independent_version_history(self):
        code = "IB2600123477"
        ingest_row(ResultRow(notify_no=code, package_name="Hai file cùng loại"))
        files = [{"document_name": "HSMT.txt", "document_type": "HSMT",
                  "source_url": f"https://muasamcong.mpi.gov.vn/files/{name}.txt"}
                 for name in ("first", "second")]
        with get_db().engine.begin() as conn:
            _sync_documents(conn, code, files, "2026-09-29T01:00:00+00:00")
        rows = catalog(self.first, source="egp")["items"]
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["version"] for row in rows}, {1})
        self.assertNotEqual(rows[0]["document_group_id"], rows[1]["document_group_id"])
        files[0]["document_name"] = "HSMT revised.txt"
        with get_db().engine.begin() as conn:
            _sync_documents(conn, code, files, "2026-09-29T02:00:00+00:00")
        history = {row["source_url"]: detail(self.first, "egp", row["id"])["versions"]
                   for row in rows}
        self.assertEqual(len(history[files[0]["source_url"]]), 2)
        self.assertEqual(len(history[files[1]["source_url"]]), 1)

    def test_followed_tender_document_notifications_are_deduplicated(self):
        code = "IB2600123499"
        ingest_row(ResultRow(notify_no=code, package_name="Gói theo dõi"))
        user_stores(self.first).watchlist.update({"action": "add", "code": code, "name": "Gói theo dõi"})
        item = {"document_name": "HSMT.txt", "document_type": "HSMT",
                "source_url": "https://muasamcong.mpi.gov.vn/files/watch.txt", "file_size": 10}
        with get_db().engine.begin() as conn:
            _sync_documents(conn, code, [item], "2026-09-29T01:00:00+00:00")
            _sync_documents(conn, code, [item], "2026-09-29T02:00:00+00:00")
        with get_db().engine.connect() as conn:
            alerts = conn.execute(select(user_notifications)).mappings().all()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["user_id"], self.first)
        item["file_size"] = 20
        with get_db().engine.begin() as conn:
            _sync_documents(conn, code, [item], "2026-09-29T03:00:00+00:00")
        with get_db().engine.connect() as conn:
            alerts = conn.execute(select(user_notifications)).mappings().all()
        self.assertEqual([row["type"] for row in alerts], ["new_document", "document_changed"])

    def test_complete_source_list_marks_removed_without_deleting_history(self):
        code = "IB2600123498"
        ingest_row(ResultRow(notify_no=code, package_name="Gói tài liệu"))
        item = {"document_name": "HSMT.txt", "source_url":
                "https://muasamcong.mpi.gov.vn/files/removed.txt"}
        with get_db().engine.begin() as conn:
            _sync_documents(conn, code, [item], "2026-09-29T01:00:00+00:00")
            _sync_documents(conn, code, [], "2026-09-29T02:00:00+00:00")
        self.assertEqual(catalog(self.first, source="egp")["items"][0]["status"], "metadata_only")
        with get_db().engine.begin() as conn:
            _sync_documents(conn, code, [], "2026-09-29T03:00:00+00:00", complete=True)
        self.assertEqual(catalog(self.first, source="egp")["items"][0]["status"], "deleted_at_source")
        with get_db().engine.begin() as conn:
            _sync_documents(conn, code, [item], "2026-09-29T04:00:00+00:00", complete=True)
        self.assertEqual(catalog(self.first, source="egp")["items"][0]["status"], "metadata_only")

    def test_explicit_fetch_hash_dedup_extraction_and_file_validation(self):
        code = "IB2600123458"
        ingest_row(ResultRow(notify_no=code, package_name="Gói hồ sơ"))
        user_stores(self.first).watchlist.update({"action": "add", "code": code, "name": "Gói hồ sơ"})
        item = {"document_name": "HSMT.txt", "document_type": "HSMT",
                "source_url": "https://muasamcong.mpi.gov.vn/files/one.txt",
                "file_size": 12}
        with get_db().engine.begin() as conn:
            _sync_documents(conn, code, [item], "2026-09-29T01:00:00+00:00")
        document_id = catalog(self.first, source="egp")["items"][0]["id"]
        manager = Mock()
        manager.request_binary.return_value = (b"gia goi thau 100", "text/plain")
        storage = LocalStorageProvider(Path(self.folder.name) / "objects")
        with patch("server.source_documents.get_request_manager", return_value=manager), \
             patch("server.source_documents.get_storage", return_value=storage):
            self.assertEqual(fetch_source_document(self.first, document_id)["version"], 1)
            self.assertTrue(fetch_source_document(self.first, document_id)["cached"])
            self.assertEqual(manager.request_binary.call_count, 1)
            self.assertEqual(cached_source_file(document_id)[0], b"gia goi thau 100")
            self.assertEqual(extract_source_document(self.first, document_id)["status"], "ready")
            self.assertTrue(extract_source_document(self.first, document_id)["cached"])
            self.assertEqual(catalog(self.first, query="thau 100")["total"], 1)
            self.assertEqual(fetch_source_document(self.first, document_id, force=True)["version"], 1)
            manager.request_binary.return_value = (b"gia goi thau 200", "text/plain")
            self.assertEqual(fetch_source_document(self.first, document_id, force=True)["version"], 2)
            self.assertEqual(len(detail(self.first, "egp", document_id)["versions"]), 2)
            comparison = compare_source_versions(self.first, document_id, 1, 2)
            self.assertTrue(comparison["metadata_changes"])
            with get_db().engine.connect() as conn:
                self.assertEqual(len(conn.execute(select(user_notifications)).all()), 2)
            manager.request_binary.return_value = (b"gia goi thau 100", "text/plain")
            self.assertEqual(fetch_source_document(self.first, document_id, force=True)["version"], 1)
            self.assertEqual(len(detail(self.first, "egp", document_id)["versions"]), 2)
            manager.request_binary.return_value = (b"<html>bad</html>", "text/html")
            with self.assertRaises(ValueError):
                fetch_source_document(self.first, document_id, force=True)

    def test_ai_import_requires_explicit_action_and_is_user_scoped(self):
        code = "IB2600123466"
        ingest_row(ResultRow(notify_no=code, package_name="Gói AI"))
        with get_db().engine.begin() as conn:
            _sync_documents(conn, code, [{"document_name": "AI.txt",
                "source_url": "https://muasamcong.mpi.gov.vn/files/ai.txt"}],
                "2026-09-29T01:00:00+00:00")
        document_id = catalog(self.first, source="egp")["items"][0]["id"]
        storage = LocalStorageProvider(Path(self.folder.name) / "objects")
        manager = Mock()
        manager.request_binary.return_value = (b"Thong tin goi thau", "text/plain")
        with patch("server.source_documents.get_request_manager", return_value=manager), \
             patch("server.source_documents.get_storage", return_value=storage), \
             patch("server.document_service.get_storage", return_value=storage):
            self.assertEqual(catalog(self.first, source="upload")["total"], 0)
            with self.assertRaises(ValueError):
                import_source_for_ai(self.first, document_id)
            fetch_source_document(self.first, document_id)
            first = import_source_for_ai(self.first, document_id)
            self.assertFalse(first["cached"])
            self.assertEqual(import_source_for_ai(self.first, document_id)["document_id"],
                             first["document_id"])
            second = import_source_for_ai(self.second, document_id)
            self.assertNotEqual(second["document_id"], first["document_id"])
            self.assertIsNone(detail(self.second, "upload", first["document_id"]))
            delete_document(self.first, first["document_id"])
            delete_document(self.second, second["document_id"])


class SourceBinaryTests(unittest.TestCase):
    def test_bounded_binary_request_rejects_redirects_and_foreign_hosts(self):
        response = Mock(status_code=200, headers={"Content-Type": "text/plain", "Content-Length": "4"})
        response.iter_content.return_value = [b"test"]
        session = Mock()
        session.request.return_value = response
        manager = SourceRequestManager(session=session, sleeper=lambda _: None)
        self.assertEqual(manager.request_binary(
            "https://muasamcong.mpi.gov.vn/file.txt", max_bytes=4)[0], b"test")
        session.request.assert_called_with("GET", "https://muasamcong.mpi.gov.vn/file.txt",
            stream=True, allow_redirects=False, timeout=(10, 30))
        with self.assertRaises(ValueError):
            manager.request_binary("https://evil.example/file.txt", max_bytes=4)
        response.headers = {"Content-Type": "text/plain", "Content-Length": "100"}
        with self.assertRaises(ValueError):
            manager.request_binary("https://muasamcong.mpi.gov.vn/file.txt", max_bytes=4)
        response.status_code = 302
        with self.assertRaises(SourceError):
            manager.request_binary("https://muasamcong.mpi.gov.vn/file.txt", max_bytes=4)


if __name__ == "__main__":
    unittest.main()
