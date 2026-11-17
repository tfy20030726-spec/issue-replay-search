import json
from pathlib import Path
import subprocess
import sys
import unittest

from issue_replay import METHODS, metrics, rank, read_data, replay_rows, utc_cutoff

ROOT = Path(__file__).resolve().parent
NOW = "2026-10-10T10:00:00Z"


def item(number, title, day):
    return {"number": number, "title": title, "created_at": f"2026-10-{day:02d}T10:00:00Z"}


class RankingsTest(unittest.TestCase):
    def test_same_instant_and_future_excluded_from_scores(self):
        before = [item(1, "blink cursor", 7), item(2, "blink screen", 8), item(3, "cursor", 9)]
        after = [item(n, "cursor cursor", 11) for n in range(4, 30)]
        same = item(30, "blink cursor", 10)
        expected = rank(before, "blink cursor", NOW)
        self.assertEqual(rank(before + after + [same], "blink cursor", NOW), expected)
        self.assertEqual(expected[0], 3)

    def test_multi_term_or_and_consistent_ties(self):
        docs = [item(3, "cursor", 4), item(4, "toolbar", 4), item(2, "cursor", 5)]
        _, ranked = rank(docs, "cursor toolbar", NOW)
        for ids in ranked.values():
            self.assertEqual(set(ids), {2, 3, 4})
            self.assertLess(ids.index(2), ids.index(3))

    def test_blank_unmatched_and_punctuation(self):
        docs = [item(1, "Text editor", 9)]
        for query in ('the  ', 'xylophone', '"?!!()'):
            self.assertEqual(rank(docs, query, NOW), (1, {"bm25": [], "overlap": []}))

    def test_utc_cutoffs_and_required_offset(self):
        self.assertEqual(utc_cutoff("2026-11-17T09:00:00+10:00"), "2026-11-16T23:00:00Z")
        self.assertEqual(utc_cutoff("2026-11-17"), "2026-11-17T00:00:00Z")
        with self.assertRaises(ValueError):
            utc_cutoff("2026-11-17T09:00:00")

    def test_mrr_at_five_counts_misses_in_denominator(self):
        rows = [{"ranks": {"bm25": pos, "overlap": None}} for pos in (1, 2, 6, None)]
        summary = metrics(rows)
        self.assertEqual(summary["bm25"], {"queries": 4, "hits_at_1": 1, "hits_at_5": 2, "mrr_at_5": .375})
        self.assertEqual(summary["overlap"]["hits_at_5"], 0)

    def test_rejects_a_future_reference(self):
        docs = [item(1, "small font", 3), item(2, "font size", 8)]
        with self.assertRaises(ValueError):
            replay_rows(docs, [{"query": 1, "canonical": 2, "confirmed_at": NOW}])

    def test_committed_snapshot_and_report(self):
        docs = read_data("issues.json")
        labels = read_data("duplicates.json")
        rows = replay_rows(docs, labels)
        for doc in docs:
            self.assertEqual(set(doc), {"number", "title", "created_at"})
            self.assertEqual(doc["created_at"], utc_cutoff(doc["created_at"]))
        for row in rows:
            self.assertTrue(row["evidence_url"].startswith(
                f"https://github.com/microsoft/vscode/issues/{row['query']}#issuecomment-"))
            for method in METHODS:
                pos = row["ranks"][method]
                if pos is not None and pos <= 5:
                    self.assertEqual(row["results"][method][pos - 1], row["canonical"])
        report = json.loads((ROOT / "reports" / "replay.json").read_text(encoding="utf-8"))
        self.assertEqual(report, {"rows": rows, "metrics": metrics(rows)})

    def test_cli_search(self):
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "issue_replay.py"), "search", "terminal",
             "--before", "2026-11-16"],
            check=True, capture_output=True, encoding="utf-8", errors="replace")
        self.assertIn("candidate titles", result.stdout)
        self.assertIn("https://github.com/microsoft/vscode/issues/", result.stdout)


if __name__ == "__main__":
    unittest.main()
