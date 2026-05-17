import os
import unittest
from datetime import datetime


os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

from app.services.source_archive import _parse_datetime  # noqa: E402


class SourceArchiveDateTests(unittest.TestCase):
    def test_parse_iso_datetime(self):
        self.assertEqual(
            _parse_datetime("2026-05-17T09:15:00.000Z"),
            datetime(2026, 5, 17, 9, 15, 0),
        )

    def test_parse_rss_datetime(self):
        self.assertEqual(
            _parse_datetime("Sun, 17 May 2026 09:15:00 +0000"),
            datetime(2026, 5, 17, 9, 15, 0),
        )


if __name__ == "__main__":
    unittest.main()
