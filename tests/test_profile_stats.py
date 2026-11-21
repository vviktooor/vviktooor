"""Testy generatora statystyk profilu. Autor: WR"""
import datetime as dt
import os
import sys
import tempfile
import unittest
import xml.dom.minidom

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import profile_stats as ps  # noqa: E402

D = dt.date


def days(spec):
    """spec: {'2026-11-01': 3, ...}"""
    return sorted(spec.items())


class Streaks(unittest.TestCase):
    def test_current_streak_counts_today(self):
        s = ps.streaks(days({"2026-11-19": 1, "2026-11-20": 2, "2026-11-21": 1}), D(2026, 11, 21))
        self.assertEqual((s["total"], s["current"], s["longest"]), (4, 3, 3))
        self.assertEqual(s["current_range"], (D(2026, 11, 19), D(2026, 11, 21)))

    def test_empty_today_does_not_break_streak(self):
        s = ps.streaks(days({"2026-11-19": 1, "2026-11-20": 2, "2026-11-21": 0}), D(2026, 11, 21))
        self.assertEqual(s["current"], 2)

    def test_gap_breaks_streak_and_longest_kept(self):
        spec = {"2026-01-01": 1, "2026-01-02": 1, "2026-01-03": 1, "2026-01-04": 0,
                "2026-11-20": 0, "2026-11-21": 5}
        s = ps.streaks(days(spec), D(2026, 11, 21))
        self.assertEqual((s["current"], s["longest"]), (1, 3))
        self.assertEqual(s["longest_range"], (D(2026, 1, 1), D(2026, 1, 3)))

    def test_future_days_ignored(self):
        s = ps.streaks(days({"2026-11-21": 1, "2026-11-22": 9}), D(2026, 11, 21))
        self.assertEqual(s["total"], 1)

    def test_no_contributions(self):
        s = ps.streaks(days({"2026-11-21": 0}), D(2026, 11, 21))
        self.assertEqual((s["total"], s["current"], s["longest"]), (0, 0, 0))
        self.assertEqual(ps.fmt_range(s["current_range"]), "No active streak")


class Aggregates(unittest.TestCase):
    def test_weekly_has_52_buckets_and_sums(self):
        w = ps.weekly(days({"2026-11-16": 2, "2026-11-21": 3, "2020-01-01": 99}), D(2026, 11, 21))
        self.assertEqual(len(w), 52)
        self.assertEqual(w[-1], (D(2026, 11, 16), 5))
        self.assertEqual(sum(c for _, c in w), 5)

    def test_language_shares_top4_plus_other(self):
        sh = ps.language_shares({"A": 50, "B": 20, "C": 10, "D": 10, "E": 5, "F": 5, "X": 100}, {"X"})
        self.assertEqual([n for n, _ in sh], ["A", "B", "C", "D", "Other"])
        self.assertAlmostEqual(sum(s for _, s in sh), 1.0)

    def test_language_shares_empty(self):
        self.assertEqual(ps.language_shares({}, set()), [])


class Render(unittest.TestCase):
    def test_fixture_renders_valid_svgs(self):
        fixture = os.path.join(os.path.dirname(__file__), "fixture.json")
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(ps.main(["--fixture", fixture, "--out", out, "--today", "2026-11-21"]), 0)
            names = sorted(os.listdir(out))
            self.assertEqual(names, ["activity-dark.svg", "activity-light.svg",
                                     "languages-dark.svg", "languages-light.svg"])
            for name in names:
                xml.dom.minidom.parse(os.path.join(out, name))

    def test_empty_data_renders(self):
        svg = ps.languages_svg([], ps.THEMES["dark"])
        xml.dom.minidom.parseString(svg)
        self.assertIn("No language data yet", svg)

    def test_only_wr_colors(self):
        allowed = {ps.INK, ps.SIGNAL, ps.BLUE, ps.SLATE, ps.PAPER, ps.LINE, ps.WHITE, "#283346"}
        import re
        fixture = os.path.join(os.path.dirname(__file__), "fixture.json")
        with tempfile.TemporaryDirectory() as out:
            ps.main(["--fixture", fixture, "--out", out, "--today", "2026-11-21"])
            for name in os.listdir(out):
                with open(os.path.join(out, name), encoding="utf-8") as fh:
                    used = set(re.findall(r"#[0-9A-Fa-f]{6}", fh.read()))
                self.assertLessEqual(used, allowed, name)


class Fetch(unittest.TestCase):
    def test_each_repo_weighs_the_same(self):
        def fake(token, query, variables):
            if "createdAt" in query:
                return {"user": {"createdAt": "2026-01-01T00:00:00Z"}}
            if "contributionCalendar" in query:
                return {"user": {"contributionsCollection": {"contributionCalendar": {"weeks": [
                    {"contributionDays": [{"date": "2026-11-21", "contributionCount": 2}]}]}}}}
            return {"user": {"repositories": {"pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [
                        {"languages": {"edges": [{"size": 1_000_000, "node": {"name": "HTML"}}]}},
                        {"languages": {"edges": [{"size": 300, "node": {"name": "Python"}},
                                                 {"size": 100, "node": {"name": "Shell"}}]}},
                        {"languages": {"edges": []}}]}}}
        original = ps.graphql
        ps.graphql = fake
        try:
            data = ps.fetch("t", "u", D(2026, 11, 21))
        finally:
            ps.graphql = original
        self.assertEqual(data["languages"], {"HTML": 1.0, "Python": 0.75, "Shell": 0.25})
        self.assertEqual(data["days"], [("2026-11-21", 2)])
        self.assertEqual(data["since"], 2026)


if __name__ == "__main__":
    unittest.main()
