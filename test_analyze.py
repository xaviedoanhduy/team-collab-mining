"""Run: python3 -m unittest -v"""

import unittest

import analyze
import generate_sample as gen


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
        tickets, entries = gen.generate(seed=42)
        users = [{"user_id": str(gen.USER_ID[u[0]]), "login": u[0], "name": u[1], "role": u[2]} for u in gen.USERS]
        str_t = [{k: str(v) for k, v in t.items()} for t in tickets]
        cls.groups, _, _ = analyze.analyze(users, str_t, entries)
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

    def test_rare_pair_not_rated(self):
        r = self.groups[find(self.groups, "hieu.bui + lam.duong")]
        self.assertLess(r["scored_tickets"], 5)

    def test_sticky_pair_most_together_among_devs(self):
        devs = sorted((r for r in self.groups if r["role_mix"] == "Developer + Developer"), key=lambda r: -r["jaccard"])
        self.assertEqual(find(devs, "long.mai + ngoc.ha"), 0)


class TestSmall(unittest.TestCase):
    def test_user_id_hmac(self):
        u = {"login": "a", "name": "A A", "role": "dev"}
        self.assertEqual(analyze.user_id_of(u, "s1"), analyze.user_id_of(dict(u), "s1"))
        self.assertNotEqual(analyze.user_id_of(u, "s1"), analyze.user_id_of(u, "s2"))
        self.assertNotEqual(analyze.user_id_of(u, "s1"), analyze.user_id_of(dict(u, name="B B"), "s1"))
        self.assertEqual(analyze.user_id_of(dict(u, user_id="7")), 7)  # given id wins, no salt needed
        with self.assertRaises(ValueError):
            analyze.user_id_of(u)  # no id and no salt

    def test_roles_min_hours_and_labels(self):
        # users without user_id (HMAC), entries keyed by task_id / ticket_id
        users = [{"login": "a", "name": "A A", "role": "dev"}, {"login": "q", "name": "Q Q", "role": "qa"},
                 {"login": "p", "name": "P P", "role": "pm"}]
        tickets = [{"id": "1", "project": "X", "state": "closed", "development_time": "10", "qc_estimate": "2",
                    "reopening_times": "0"},
                   {"id": "2", "project": "X", "state": "closed", "development_time": "10", "qc_estimate": "2",
                    "reopening_times": "1"}]
        a, q, p = (analyze.user_id_of(u, "salt") for u in users)
        entries = [{"task_id": "1", "user_id": str(a), "duration_hour": "4"},
                   {"ticket_id": "1", "user_id": str(q), "duration_hour": "1"},
                   {"task_id": "1", "user_id": str(p), "duration_hour": "9"},     # pm not in roles
                   {"task_id": "2", "user_id": str(a), "duration_hour": "0.25"},  # below min_hours
                   {"task_id": "", "user_id": str(a), "duration_hour": "8"}]      # not linked to a ticket
        groups, users_out, _ = analyze.analyze(users, tickets, entries, salt="salt")
        self.assertEqual([(r["members"], r["role_mix"], r["shared_tickets"], r["jaccard"]) for r in groups],
                         [(f"{a} + {q}", "Developer + QC", 1, 1.0)])
        self.assertEqual(groups[0]["member_labels"], "A A (a) - Developer + Q Q (q) - QC")
        self.assertEqual(groups[0]["synergy"], 0.0)  # one ticket, one bucket: residual 0
        self.assertEqual({r["user_id"] for r in users_out}, {a, q})


if __name__ == "__main__":
    unittest.main()
