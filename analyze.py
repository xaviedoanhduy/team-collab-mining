"""Find who works together and which teams (pairs, trios) deliver tickets more efficiently.

Input (CSVs, see README): users.csv, tickets.csv, work_entries.csv.
Output: reports/groups.csv, reports/users.csv, report.html and an SPMF-format HUIM dataset.

Method:
- Transaction = one ticket, items = users (dev, TPM, QC by default) who
  logged >= --min-hours on it. A typical ticket: dev + TPM review + QC.
- Groups = every pair and trio inside a ticket's team.
- Co-work strength = Jaccard over multi-person tickets (tickets with all members /
  tickets with any member). Compare within one role mix: a project's TPM sits on
  most of its tickets, so "dev + TPM" is naturally higher than "dev + dev".
- Efficiency = ln(team hours / (dev estimate + QC estimate)) on closed, estimated
  tickets, minus the mean of tickets in the same project and team size (the
  residual). Negative = faster than comparable tickets.
- Quality = reopening_times, residual the same way. Fewer hours with more
  reopens is not efficient, so both are reported.
- Group synergy = group residual - average of its members' residual on tickets
  where they work WITHOUT the other members, i.e. "are they better together than apart". Means are shrunk toward 0
  (sum / (n + shrink)) so groups with few shared tickets don't top the list.
"""

import argparse
import csv
import hashlib
import hmac
import math
import os
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import report


ROLE_LABELS = {"pm": "PM", "tpm": "TPM", "dev": "Developer", "qa": "QC", "consultant": "Consultant"}
ROLE_ORDER = {"dev": 0, "tpm": 1, "qa": 2}
TICKET_KEYS = ("ticket_id", "task_id")  # first non-empty wins


SALT_ENV = "TEAM_MINING_SALT"


def user_label(user, uid):
    """'Nguyen Van An (an.nguyen) - PM'"""
    role = ROLE_LABELS.get(user["role"], user["role"].title())
    login = user.get("login") or f"#{uid}"
    return f"{user.get('name') or login} ({login}) - {role}"


def user_id_of(user, salt=None):
    """`user_id` from the file, else HMAC-SHA256(salt, name|login) cut to 48 bits.

    Same salt -> same id across exports; without the salt the id can't be recomputed from a user list.
    """
    if user.get("user_id"):
        return int(user["user_id"])
    if not salt:
        raise ValueError(f"user {user.get('login')!r} has no user_id: set {SALT_ENV} (a secret) to derive one")
    digest = hmac.new(salt.encode(), f"{user.get('name', '')}|{user['login']}".encode(), hashlib.sha256)
    return int(digest.hexdigest()[:12], 16)


def ticket_of(entry):
    """Ticket id of a work entry (`ticket_id` or `task_id`), None if unlinked."""
    return next((int(entry[k]) for k in TICKET_KEYS if entry.get(k)), None)


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load(data_dir):
    data_dir = Path(data_dir)
    return (read_csv(data_dir / "users.csv"), read_csv(data_dir / "tickets.csv"),
            read_csv(data_dir / "work_entries.csv"))


def analyze(users, tickets, entries, roles=("dev", "tpm", "qa"), min_hours=0.5, shrink=5.0, max_size=3, salt=None):
    ids = [user_id_of(u, salt) for u in users]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate user_id in users")
    role_of = {i: u["role"] for i, u in zip(ids, users)}
    label = {i: user_label(u, i) for i, u in zip(ids, users)}
    ticket_by_id = {int(t["id"]): t for t in tickets}

    hours = defaultdict(lambda: defaultdict(float))  # ticket -> user id -> hours
    for e in entries:
        uid = int(e["user_id"])
        tid = ticket_of(e)
        if tid is not None and role_of.get(uid) in roles:
            hours[tid][uid] += float(e["duration_hour"])
    team = {tid: {u: h for u, h in uh.items() if h >= min_hours} for tid, uh in hours.items()}
    team = {tid: t for tid, t in team.items() if t and tid in ticket_by_id}

    def sort_members(members):
        return tuple(sorted(members, key=lambda u: (ROLE_ORDER.get(role_of[u], 9), u)))

    def subgroups(members):
        for k in range(2, max_size + 1):
            yield from combinations(sort_members(members), k)

    # --- Co-occurrence over multi-person tickets, with per-project expectation ---
    n_proj = defaultdict(int)
    n_user = defaultdict(lambda: defaultdict(int))   # project -> user -> tickets
    n_group = defaultdict(lambda: defaultdict(int))  # project -> group -> tickets
    user_tickets = defaultdict(set)                  # user -> multi-person tickets
    for tid, members in team.items():
        if len(members) < 2:  # solo tickets say nothing about who one works with
            continue
        p = ticket_by_id[tid]["project"]
        n_proj[p] += 1
        for u in members:
            n_user[p][u] += 1
            user_tickets[u].add(tid)
        for g in subgroups(members):
            n_group[p][g] += 1

    # --- Efficiency residual per ticket ---
    overrun = {}
    for tid, members in team.items():
        t = ticket_by_id[tid]
        est = float(t["development_time"] or 0) + float(t.get("qc_estimate") or 0)
        if t["state"] == "closed" and est > 0:
            overrun[tid] = math.log(sum(members.values()) / est)

    def bucket(tid):
        return ticket_by_id[tid]["project"], min(len(team[tid]), 4)

    buckets = defaultdict(list)
    for tid, o in overrun.items():
        buckets[bucket(tid)].append(o)
    bucket_mean = {k: sum(v) / len(v) for k, v in buckets.items()}
    resid = {tid: o - bucket_mean[bucket(tid)] for tid, o in overrun.items()}

    # Quality: reopens vs comparable tickets. Fewer hours only counts as "efficient" if quality holds.
    reopens = {tid: int(ticket_by_id[tid]["reopening_times"]) for tid in resid}
    rq = defaultdict(list)
    for tid in resid:
        rq[bucket(tid)].append(reopens[tid])
    rq_mean = {k: sum(v) / len(v) for k, v in rq.items()}
    q_resid = {tid: reopens[tid] - rq_mean[bucket(tid)] for tid in resid}

    reopen_avg = sum(reopens.values()) / max(1, len(reopens))

    user_r, group_r = defaultdict(list), defaultdict(list)
    for tid in resid:
        for u in team[tid]:
            user_r[u].append(tid)
        for g in subgroups(team[tid]):
            group_r[g].append(tid)

    def shrunk(tids, values=resid):
        return sum(values[t] for t in tids) / (len(tids) + shrink)

    def reopen(tids):
        return round(sum(int(ticket_by_id[t]["reopening_times"]) for t in tids) / len(tids), 2) if tids else ""

    user_eff = {u: shrunk(t) for u, t in user_r.items()}
    user_q = {u: shrunk(t, q_resid) for u, t in user_r.items()}
    user_rows = sorted(({
        "user_id": u, "label": label[u], "role": role_of[u],
        "tickets": sum(u in m for m in team.values()),
        "scored_tickets": len(user_r.get(u, [])),
        "efficiency": round(user_eff.get(u, 0.0), 3),
        "hours_vs_expected_pct": round((math.exp(user_eff.get(u, 0.0)) - 1) * 100, 1),
        "reopen_avg": reopen(user_r.get(u, [])),
        "reopen_vs_expected": round(user_q.get(u, 0.0), 2),
    } for u in {u for m in team.values() for u in m}), key=lambda r: r["efficiency"])

    group_rows = []
    for g in {g for p in n_group for g in n_group[p]}:
        observed = sum(n_group[p].get(g, 0) for p in n_proj)
        either = len(set().union(*(user_tickets[u] for u in g)))
        expected = sum(math.prod(n_user[p][u] for u in g) / n_proj[p] ** (len(g) - 1)
                       for p in n_proj if all(n_user[p].get(u) for u in g))
        tids = group_r.get(g, [])
        eff = shrunk(tids) if tids else 0.0
        # Baseline = each member on tickets WITHOUT the other members, so the group's own
        # tickets don't leak into it (a pair that's always together would cancel itself out).
        apart = [[t for t in user_r.get(u, []) if not any(o in team[t] for o in g if o != u)] for u in g]
        synergy = eff - sum(shrunk(a) if a else 0.0 for a in apart) / len(g)
        q_synergy = ((shrunk(tids, q_resid) if tids else 0.0)
                     - sum(shrunk(a, q_resid) if a else 0.0 for a in apart) / len(g))
        group_rows.append({
            "size": len(g),
            "members": " + ".join(map(str, g)),
            "member_labels": " + ".join(label[u] for u in g),
            "role_mix": " + ".join(ROLE_LABELS.get(role_of[u], role_of[u]) for u in g),
            "shared_tickets": observed,
            "any_tickets": either,
            "jaccard": round(observed / either, 2),
            "lift": round(observed / expected, 2) if expected else 0.0,
            "scored_tickets": len(tids),
            "group_efficiency": round(eff, 3),
            "synergy": round(synergy, 3),
            "hours_vs_expected_pct": round((math.exp(synergy) - 1) * 100, 1),
            "reopen_avg": reopen(tids),
            "reopen_vs_expected": round(q_synergy, 2),
        })
    group_rows.sort(key=lambda r: r["synergy"])
    return group_rows, user_rows, {"reopen_avg": reopen_avg, "team": team, "ticket_by_id": ticket_by_id,
                                   "scored": len(resid), "label": label, "role_of": role_of}


def write_spmf(path_txt, path_items, team, ticket_by_id):
    """HUIM input in SPMF format: `items:TU:utilities` per ticket.

    Utility of a user on a ticket = their share of the ticket's value, where
    value = estimate * min(2, estimate / team_hours), estimate = dev + QC estimate, / (1 + reopening_times):
    delivering the estimated scope faster and without reopen is worth more.
    Scaled x10 to integers.
    """
    item_id = {u: i + 1 for i, u in enumerate(sorted({u for m in team.values() for u in m}))}
    lines = []
    for tid, members in sorted(team.items()):
        t = ticket_by_id[tid]
        est = float(t["development_time"] or 0) + float(t.get("qc_estimate") or 0)
        if t["state"] != "closed" or est <= 0:
            continue
        total = sum(members.values())
        value = est * min(2.0, est / total) / (1 + int(t["reopening_times"]))
        utils = sorted((item_id[u], max(1, round(10 * value * h / total))) for u, h in members.items())
        lines.append(f"{' '.join(str(i) for i, _ in utils)}:{sum(x for _, x in utils)}:"
                     f"{' '.join(str(x) for _, x in utils)}")
    Path(path_txt).write_text("\n".join(lines) + "\n")
    with open(path_items, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["item", "user_id"])
        w.writerows((i, u) for u, i in item_id.items())
    return len(lines)


def write_rows(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data", default="data/sample", type=Path)
    p.add_argument("--out", default="reports", type=Path)
    p.add_argument("--roles", default="dev,tpm,qa", help="comma-separated roles to include (default: dev,tpm,qa)")
    p.add_argument("--min-hours", default=0.5, type=float, help="min hours on a ticket to count as member")
    p.add_argument("--min-shared", default=5, type=int, help="min scored shared tickets to rate a group")
    p.add_argument("--shrink", default=5.0, type=float, help="pseudo-count pulling small samples toward 0")
    p.add_argument("--top", default=8, type=int, help="rows per ranking")
    p.add_argument("--min-edge", default=3, type=int, help="min shared tickets to draw a link in the network")
    args = p.parse_args()

    groups, users_, ctx = analyze(*load(args.data), roles=tuple(args.roles.split(",")),
                                  min_hours=args.min_hours, shrink=args.shrink, salt=os.environ.get(SALT_ENV))
    args.out.mkdir(parents=True, exist_ok=True)
    write_rows(args.out / "groups.csv", groups)
    write_rows(args.out / "users.csv", users_)
    n = write_spmf(args.out / "huim_spmf.txt", args.out / "huim_items.csv", ctx["team"], ctx["ticket_by_id"])
    html_path = args.out / "report.html"
    html_path.write_text(report.render(groups, users_, ctx, args), encoding="utf-8")

    k = args.top // 2 or 1

    rule = "  " + "─" * 76

    def line(r, value, bar, scored=False):
        first, *rest = r["member_labels"].split(" + ")
        count = f"({r['shared_tickets']} tickets / {r['any_tickets']} tickets)"
        if scored:
            count += f", {r['scored_tickets']} closed & estimated"
        return "\n".join([f"{'':35}{count}", f"  {value:>7}  {bar:<22}  - {first}"]
                          + [f"{'':33}  - {m}" for m in rest])

    def section(title):
        print(f"\n{'=' * 78}\n {title}\n{'=' * 78}")

    def items(rows, show):
        """One itemset per block, a rule under each."""
        for r in rows:
            print(show(r))
            print(rule)

    def halves(rows, labels, show):
        for lab, part in zip(labels, (rows[:k], [r for r in rows[-k:] if r not in rows[:k]])):
            print(f"\n  [{lab}]\n{rule}")
            items(part, show)

    def hours(r):
        v = r["hours_vs_expected_pct"]
        return line(r, f"{v:+.1f}%", "█" * round(abs(v) / 2), scored=True)

    def reopens(r):
        v = r["reopen_vs_expected"]
        return line(r, f"{v:+.2f}", "█" * round(abs(v) * 40), scored=True)

    print("(A tickets / B tickets) = tickets with all members / multi-person tickets with any of them;"
          " A / B = Jaccard.\nClosed & estimated = shared tickets used for hours and reopens.")
    section("Most often together, per role mix (Jaccard: 1.0 = always together)")
    for mix in sorted({r["role_mix"] for r in groups}, key=lambda m: (m.count("+"), m)):
        top = sorted((r for r in groups if r["role_mix"] == mix), key=lambda r: -r["jaccard"])[:2]
        print(f"\n  [{mix}]\n{rule}")
        items(top, lambda r: line(r, f"{r['jaccard']:.2f}", "█" * round(r["jaccard"] * 20)))
    for size, name in ((2, "pairs"), (3, "trios")):
        shown = [r for r in groups if r["size"] == size and r["scored_tickets"] >= args.min_shared]
        section(f"Best / worst {name}: % hours vs apart (>= {args.min_shared} tickets; negative = faster)")
        halves(shown, ("Faster together", "Slower together"), hours)
    rated = [r for r in groups if r["scored_tickets"] >= args.min_shared]
    section(f"Fewest / most reopens vs apart, per ticket (>= {args.min_shared} tickets)")
    halves(sorted(rated, key=lambda r: r["reopen_vs_expected"]), ("Fewer reopens", "More reopens"), reopens)
    print(f"\nFull report: {html_path.resolve().as_uri()}")
    print(f"CSV + HUIM dataset ({n} transactions): {args.out}/")


if __name__ == "__main__":
    main()
