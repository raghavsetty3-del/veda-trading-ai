import os
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch


os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
sys.modules.setdefault("feedparser", SimpleNamespace(parse=lambda _url: SimpleNamespace(entries=[])))

from app import scheduler  # noqa: E402


class SchedulerImmediateExtractionTests(unittest.TestCase):
    def test_process_created_sources_limits_and_deduplicates(self):
        processed = []

        def fake_process_source(_db, source_id):
            processed.append(source_id)
            return {"source_id": source_id}

        with patch.object(scheduler.settings, "source_immediate_extraction_limit", 2), \
            patch.object(scheduler, "process_source", side_effect=fake_process_source), \
            patch.object(scheduler, "audit") as audit:
            scheduler.process_created_sources(
                object(),
                {"created_source_ids": [10, 10, 11, 12]},
                "blog",
            )

        self.assertEqual(processed, [10, 11])
        audit.assert_called_once()
        self.assertEqual(audit.call_args.kwargs["payload"]["created"], 3)
        self.assertEqual(audit.call_args.kwargs["payload"]["processed"], 2)


if __name__ == "__main__":
    unittest.main()
