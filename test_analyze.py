"""Run: python3 -m unittest -v"""

import argparse
import unittest

import analyze
import report
import generate_sample as gen


def sample():
    tickets, entries = gen.generate(seed=42)
    employees = [{"id": str(gen.USER_ID[u[0]]), "name": u[1], "role": u[2]} for u in gen.USERS]
    str_rows = [[{k: str(v) for k, v in r.items()} for r in rows] for rows in (tickets, entries)]
    return employees, *str_rows


def ids(members):
    """'a.login + b.login' -> {user_id, ...}"""
    return {str(gen.USER_ID[m]) for m in members.split(" + ")}


def find(rows, members):
    return next(i for i, r in enumerate(rows) if set(r["members"].split(" + ")) == ids(members))


rank = find


class TestPlantedTruth(unittest.TestCase):
    """The generator plants known effects; the analysis must find them."""

    @classmethod
    def setUpClass(cls):
        cls.groups, _, _ = analyze.analyze(*sample())
        rated = [r for r in cls.groups if r["scored_tickets"] >= 5]
        cls.pairs = sorted((r for r in rated if r["size"] == 2), key=lambda r: r["hours_vs_expected_pct"])
        cls.trios = sorted((r for r in rated if r["size"] == 3), key=lambda r: r["hours_vs_expected_pct"])
        cls.quality = sorted(rated, key=lambda r: r["reopen_vs_expected"])

    def test_good_dev_pair_on_top(self):
        self.assertEqual(rank(self.pairs, "dung.pham + linh.ly"), 0)

    def test_dream_team_trio_near_top(self):
        self.assertLess(rank(self.trios, "khanh.ngo + phong.nghiem + thao.phan"), 3)

    def test_bad_trio_at_bottom(self):
        self.assertEqual(rank(self.trios, "giang.hoang + khoa.truong + yen.quach"), len(self.trios) - 1)

    def test_bad_dev_qc_pair_slow_and_reopens(self):
        self.assertGreaterEqual(rank(self.pairs, "son.kieu + trang.vo"), len(self.pairs) - 3)
        self.assertGreaterEqual(rank(self.quality, "son.kieu + trang.vo"), len(self.quality) - 10)

    def test_planted_groups_are_clear(self):
        for members in ("dung.pham + linh.ly", "giang.hoang + khoa.truong + yen.quach", "son.kieu + trang.vo"):
            r = self.groups[find(self.groups, members)]
            self.assertTrue(r["hours_significant"], members)
            self.assertLessEqual(r["hours_ci_low_pct"], r["hours_vs_expected_pct"])
            self.assertLessEqual(r["hours_vs_expected_pct"], r["hours_ci_high_pct"])

    def test_uniform_small_sample_not_overconfident(self):
        # ~7 tickets with 0 reopens is common at a 0.14 base rate; must not read as a clear effect.
        zero = [r for r in self.groups if r["scored_tickets"] >= 5 and r["reopen_avg"] == 0.0]
        self.assertTrue(zero)
        self.assertFalse([r["members"] for r in zero if r["reopen_significant"]])

    def test_individuals_hidden_by_default(self):
        groups, users_out, ctx = analyze.analyze(*sample())
        args = argparse.Namespace(data="x", roles="dev,tpm,qa", min_hours=0.5, min_shared=5, shrink=5.0, top=8,
                                  min_edge=3, show_individuals=False)
        html = report.render(groups, users_out, ctx, args)
        self.assertNotIn("Individual baseline", html)
        self.assertNotIn("Individual:", html)
        args.show_individuals = True
        self.assertIn("Individual baseline", report.render(groups, users_out, ctx, args))

    def test_rare_pair_not_rated(self):
        r = self.groups[find(self.groups, "hieu.bui + lam.duong")]
        self.assertLess(r["scored_tickets"], 5)

    def test_sticky_pair_most_together_among_devs(self):
        devs = sorted((r for r in self.groups if r["role_mix"] == "Developer + Developer"), key=lambda r: -r["jaccard"])
        self.assertEqual(find(devs, "long.mai + ngoc.ha"), 0)


class TestSmall(unittest.TestCase):
    def test_roles_min_hours_and_labels(self):
        employees = [{"id": "1", "name": "A A", "role": "dev"}, {"id": "2", "name": "", "role": "qa"},
                     {"id": "3", "name": "P P", "role": "pm"}]
        tasks = [{"id": "10", "project_id": "7", "state": "1_done", "allocated_hours": "12", "reopen_count": "0"},
                 {"id": "11", "project_id": "7", "state": "1_done", "allocated_hours": "12"}]  # no reopen_count
        lines = [{"task_id": "10", "employee_id": "1", "unit_amount": "4"},
                 {"task_id": "10", "employee_id": "2", "unit_amount": "1"},
                 {"task_id": "10", "employee_id": "3", "unit_amount": "9"},     # pm not in roles
                 {"task_id": "11", "employee_id": "1", "unit_amount": "0.25"},  # below min_hours
                 {"task_id": "", "employee_id": "1", "unit_amount": "8"}]       # timesheet without task
        groups, users_out, _ = analyze.analyze(employees, tasks, lines)
        self.assertEqual([(r["members"], r["role_mix"], r["shared_tickets"], r["jaccard"]) for r in groups],
                         [("1 + 2", "Developer + QC", 1, 1.0)])
        self.assertEqual(groups[0]["member_labels"], "A A - Developer + #2 - QC")
        self.assertEqual(groups[0]["synergy"], 0.0)  # one ticket, one bucket: residual 0
        self.assertEqual({r["employee_id"] for r in users_out}, {1, 2})


if __name__ == "__main__":
    unittest.main()
