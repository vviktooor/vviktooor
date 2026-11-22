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
            if "viewer{login}" in query:
                return {"viewer": {"login": "u"}}
            if "createdAt" in query:
                return {"user": {"createdAt": "2026-01-01T00:00:00Z"}}
            if "contributionCalendar" in query:
                return {"user": {"contributionsCollection": {"contributionCalendar": {"weeks": [
                    {"contributionDays": [{"date": "2026-11-21", "contributionCount": 2}]}]}}}}
            return {"viewer": {"repositories": {"pageInfo": {"hasNextPage": False, "endCursor": None},
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


    def test_falls_back_to_user_query_without_own_token(self):
        seen = []

        def fake(token, query, variables):
            seen.append(query)
            if "viewer{login}" in query:
                raise RuntimeError("GraphQL: not accessible")
            if "createdAt" in query:
                return {"user": {"createdAt": "2026-01-01T00:00:00Z"}}
            if "contributionCalendar" in query:
                return {"user": {"contributionsCollection": {"contributionCalendar": {"weeks": []}}}}
            return {"user": {"repositories": {"pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [{"isPrivate": False, "languages": {"edges": [{"size": 5, "node": {"name": "C"}}]}}]}}}
        original = ps.graphql
        ps.graphql = fake
        try:
            data = ps.fetch("t", "u", D(2026, 11, 21))
        finally:
            ps.graphql = original
        self.assertEqual(data["languages"], {"C": 1.0})
        self.assertTrue(any("user(login:$l)" in q for q in seen))


class Snake(unittest.TestCase):
    RAW = ('<svg viewBox="-16 -32 880 192" width="880" height="192" xmlns="http://www.w3.org/2000/svg">'
           '<style>.c{fill:red}</style><rect class="c" width="12" height="12"/></svg>')

    def test_snake_wrapped_in_wr_card(self):
        svg = ps.snake_svg(self.RAW, ps.THEMES["dark"])
        xml.dom.minidom.parseString(svg)
        self.assertIn("CONTRIBUTION GRAPH", svg)
        self.assertIn('viewBox="-16 -32 880 192"', svg)
        self.assertEqual(svg.count("<svg"), 2)

    def test_main_wraps_raw_snake_and_removes_it(self):
        fixture = os.path.join(os.path.dirname(__file__), "fixture.json")
        with tempfile.TemporaryDirectory() as out:
            for mode in ("light", "dark"):
                with open(os.path.join(out, f"snake-raw-{mode}.svg"), "w") as fh:
                    fh.write(self.RAW)
            ps.main(["--fixture", fixture, "--out", out, "--today", "2026-11-21"])
            names = set(os.listdir(out))
            self.assertIn("snake-dark.svg", names)
            self.assertNotIn("snake-raw-dark.svg", names)

    def test_bad_snake_raises(self):
        with self.assertRaises(ValueError):
            ps.snake_svg("<svg></svg>", ps.THEMES["dark"])


class CountUp(unittest.TestCase):
    def test_final_value_visible_without_animation(self):
        svg = ps.count_up(0, 0, 356, "", 'fill="#fff"')
        self.assertIn(">356<animate", svg)
        self.assertNotIn('opacity="0">356', svg)

    def test_zero_is_static(self):
        self.assertEqual(ps.count_up(0, 10, 0, " d", "a=\"b\""), '<text x="0" y="10" a="b">0 d</text>')


if __name__ == "__main__":
    unittest.main()
