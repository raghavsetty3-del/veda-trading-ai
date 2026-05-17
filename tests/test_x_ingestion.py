import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch


os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

from app.services import x_ingestion  # noqa: E402


class XIngestionBackfillTests(unittest.TestCase):
    def test_ingest_username_walks_pagination_and_deduplicates_posts(self):
        pages = [
            {
                "data": [
                    {"id": "1", "text": "first", "entities": {"urls": []}},
                ],
                "meta": {"next_token": "next-page"},
            },
            {
                "data": [
                    {"id": "2", "text": "second", "entities": {"urls": []}},
                    {"id": "1", "text": "duplicate", "entities": {"urls": []}},
                ],
                "meta": {},
            },
        ]
        fetch_calls = []
        archived = []

        def fake_fetch(_client, user_id, limit, pagination_token=None):
            fetch_calls.append((user_id, limit, pagination_token))
            return pages[len(fetch_calls) - 1]

        def fake_archive(_db, payload):
            archived.append(payload)
            row = SimpleNamespace(id=len(archived), title=payload["title"])
            return row, True, {}

        with patch.object(x_ingestion, "_headers", return_value={}), \
            patch.object(x_ingestion, "_lookup_user", return_value={"id": "u1", "username": "JustNifty"}), \
            patch.object(x_ingestion, "_fetch_user_posts", side_effect=fake_fetch), \
            patch.object(x_ingestion, "_linked_page_media_urls", return_value=[]), \
            patch.object(x_ingestion, "archive_source_document", side_effect=fake_archive), \
            patch.object(x_ingestion, "audit"):
            result = x_ingestion.ingest_x_username(object(), "JustNifty", limit=100, pages=3)

        self.assertEqual(result["seen"], 2)
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["existing"], 0)
        self.assertEqual(result["created_source_ids"], [1, 2])
        self.assertEqual(result["pages_fetched"], 2)
        self.assertFalse(result["has_more"])
        self.assertEqual(fetch_calls, [("u1", 100, None), ("u1", 100, "next-page")])
        self.assertEqual([item["source_external_id"] for item in archived], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
