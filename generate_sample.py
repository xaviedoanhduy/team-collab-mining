"""Generate a synthetic dataset (employees, tasks, timesheets) in the Odoo 17+ schema the analysis reads.

Ticket workflow:
- 1 main developer (sometimes 2) codes against the dev estimate.
- The project's TPM reviews the code (most tickets; skipped on some).
- A QC tests against a QC estimate = 20% of the dev estimate.
  `allocated_hours` = dev + QC estimate.
So a typical ticket has 3 people (dev, TPM, QC), or 2 without review.

Planted ground truth (so the analysis can be checked):
- DEV_PAIR_EFFECTS: two devs on one ticket are faster/slower than their own skill predicts.
- DEV_QC_EFFECTS: a dev + QC combination that tests faster and reopens less (or more).
- TRIO_EFFECTS: a dev + TPM + QC team that works especially well together.
- STICKY_PAIRS: devs who are usually staffed together (high Jaccard, neutral efficiency).
"""

import argparse
import csv
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path

USERS = [
    # login, name, role, speed (actual/estimate multiplier, <1 = faster)
    ("an.nguyen", "Nguyen Van An", "pm", 1.0),
    ("binh.tran", "Tran Thi Binh", "pm", 1.0),
    ("chi.le", "Le Minh Chi", "pm", 1.0),
    ("khoa.truong", "Truong Dang Khoa", "tpm", 1.0),
    ("phong.nghiem", "Nghiem Thanh Phong", "tpm", 0.9),
    ("viet.ton", "Ton That Viet", "tpm", 1.1),
    ("uyen.la", "La Thu Uyen", "tpm", 1.0),
    ("dung.pham", "Pham Quoc Dung", "dev", 0.85),
    ("giang.hoang", "Hoang Thu Giang", "dev", 1.10),
    ("hai.vu", "Vu Duc Hai", "dev", 0.95),
    ("hanh.dang", "Dang My Hanh", "dev", 1.00),
    ("hieu.bui", "Bui Trung Hieu", "dev", 1.25),
    ("hoa.do", "Do Thi Hoa", "dev", 0.90),
    ("khanh.ngo", "Ngo Gia Khanh", "dev", 1.05),
    ("lam.duong", "Duong Thanh Lam", "dev", 1.15),
    ("linh.ly", "Ly Khanh Linh", "dev", 0.80),
    ("long.mai", "Mai Hoang Long", "dev", 1.00),
    ("minh.trinh", "Trinh Cong Minh", "dev", 1.30),
    ("nam.dinh", "Dinh Phuong Nam", "dev", 0.95),
    ("ngoc.ha", "Ha Bao Ngoc", "dev", 1.10),
    ("phuc.cao", "Cao Hong Phuc", "dev", 1.00),
    ("quan.lam", "Lam Anh Quan", "dev", 0.90),
    ("son.kieu", "Kieu Truong Son", "dev", 1.20),
    ("tam.luong", "Luong Thanh Tam", "qa", 1.0),
    ("thao.phan", "Phan Thu Thao", "qa", 0.9),
    ("trang.vo", "Vo Huyen Trang", "qa", 1.1),
    ("yen.quach", "Quach Hai Yen", "qa", 1.0),
    ("tuan.ta", "Ta Minh Tuan", "consultant", 1.0),
    ("vy.chu", "Chu Tuong Vy", "consultant", 1.0),
]
USER_ID = {u[0]: i + 1 for i, u in enumerate(USERS)}

PROJECTS = [
    # name, code, pm, tpm, devs, qcs, consultants, n_tickets, review_rate
    ("ACME ERP", "acme", "an.nguyen", "khoa.truong",
     ["dung.pham", "giang.hoang", "hai.vu", "linh.ly", "minh.trinh"], ["tam.luong", "yen.quach"], ["tuan.ta"], 260, 0.85),
    ("Lotus Retail", "lotus", "binh.tran", "phong.nghiem",
     ["hanh.dang", "hieu.bui", "hoa.do", "khanh.ngo", "dung.pham", "lam.duong"], ["thao.phan"], [], 230, 0.9),
    ("Sakura Logistics", "sakura", "chi.le", "viet.ton",
     ["long.mai", "nam.dinh", "ngoc.ha", "linh.ly"], ["trang.vo"], ["vy.chu"], 170, 0.8),
    ("Mekong Pharma", "mekong", "an.nguyen", "uyen.la",
     ["phuc.cao", "quan.lam", "son.kieu", "hoa.do", "hai.vu"], ["tam.luong", "trang.vo"], ["tuan.ta"], 200, 0.85),
    ("Internal Tools", "internal", "chi.le", "khoa.truong",
     ["minh.trinh", "nam.dinh", "quan.lam", "giang.hoang"], [], [], 70, 0.5),  # no QC: dev + TPM only
]

# (hours multiplier, reopen multiplier)
DEV_PAIR_EFFECTS = {
    frozenset({"dung.pham", "linh.ly"}): (0.70, 0.5),    # great together
    frozenset({"hieu.bui", "lam.duong"}): (1.45, 2.0),   # bad together
}
DEV_QC_EFFECTS = {  # applies to QC hours and reopen
    frozenset({"hoa.do", "thao.phan"}): (0.60, 0.4),     # QC knows how this dev works
    frozenset({"son.kieu", "trang.vo"}): (1.50, 1.8),    # lots of back-and-forth
}
TRIO_EFFECTS = {  # dev + TPM + QC; applies to everyone's hours and reopen
    frozenset({"khanh.ngo", "phong.nghiem", "thao.phan"}): (0.75, 0.4),
    frozenset({"giang.hoang", "khoa.truong", "yen.quach"}): (1.35, 1.8),
}
STICKY_PAIRS = [("long.mai", "ngoc.ha"), ("quan.lam", "phuc.cao")]

ACTIVITIES = ["Feature", "Bug", "Improvement", "Support", "Migration"]
STATES_OPEN = ["01_in_progress", "02_changes_requested", "03_approved", "04_waiting_normal"]
SUMMARIES = {
    "Feature": ["Add {x} to {y}", "New report for {y}", "Allow {x} on {y}"],
    "Bug": ["Fix {x} error on {y}", "Wrong {x} computed in {y}", "Crash when saving {y}"],
    "Improvement": ["Improve {x} performance in {y}", "Refactor {y} {x}", "Better UX for {y}"],
    "Support": ["Investigate {x} issue on {y}", "Data fix for {y}", "Help user with {y}"],
    "Migration": ["Migrate {y} module to 17.0", "Port {x} from 16.0", "Upgrade {y} data"],
}
WORDS_X = ["discount", "tax", "lot number", "approval", "barcode", "currency", "invoice line", "stock move"]
WORDS_Y = ["sale order", "purchase order", "invoice", "picking", "payslip", "POS", "manufacturing order", "CRM lead"]

START = date(2025, 1, 6)
END = date(2026, 10, 30)


def workdays_from(rng, start, n_days):
    d, out = start, []
    while len(out) < n_days:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=rng.choice([1, 1, 1, 2]))
    return out


def pick_devs(rng, devs, n):
    """Pick n devs, honouring sticky pairs so some people nearly always appear together."""
    chosen = [rng.choice(devs)]
    for a, b in STICKY_PAIRS:
        if chosen[0] in (a, b) and {a, b} <= set(devs) and n >= 2 and rng.random() < 0.8:
            chosen.append(b if chosen[0] == a else a)
    pool = [d for d in devs if d not in chosen]
    rng.shuffle(pool)
    return chosen + pool[: max(0, n - len(chosen))]


def generate(seed=42):
    rng = random.Random(seed)
    speed = {u[0]: u[3] for u in USERS}
    tickets, entries = [], []
    ticket_id, entry_id = 30001, 900001

    for project_id, (proj_name, code, pm, tpm, devs, qcs, consultants, n_tickets, review_rate) in enumerate(PROJECTS, 1):
        span = (END - START).days
        for _ in range(n_tickets):
            activity = rng.choices(ACTIVITIES, weights=[40, 25, 15, 12, 8])[0]
            estimate = round(min(80, max(1, rng.lognormvariate(math.log(8), 0.8))) * 2) / 2
            if rng.random() < 0.06:
                estimate = 0.0  # PM forgot to estimate: real data has this
            qc_estimate = round(estimate * 0.2 * 4) / 4 if estimate and qcs else 0.0
            n_devs = 2 if rng.random() < (0.5 if estimate >= 16 else 0.25) else 1
            dev_team = pick_devs(rng, devs, min(n_devs, len(devs)))
            reviewer = tpm if rng.random() < review_rate else None
            qc = rng.choice(qcs) if qcs else None
            people = set(dev_team) | {p for p in (reviewer, qc) if p}

            dev_factor = sum(speed[d] for d in dev_team) / len(dev_team)
            qc_factor = speed[qc] if qc else 1.0
            reopen_mult = 1.0
            if len(dev_team) == 2:
                h, r = DEV_PAIR_EFFECTS.get(frozenset(dev_team), (1.0, 1.0))
                dev_factor *= h
                reopen_mult *= r
            for d in dev_team:
                h, r = DEV_QC_EFFECTS.get(frozenset({d, qc}), (1.0, 1.0))
                qc_factor *= h
                reopen_mult *= r
            all_factor = 1.0
            for trio, (h, r) in TRIO_EFFECTS.items():
                if trio <= people:
                    all_factor *= h
                    reopen_mult *= r
            if reviewer:
                reopen_mult *= 0.7  # review catches bugs before QC

            base = estimate or rng.uniform(2, 12)
            dev_hours = base * dev_factor * all_factor * rng.lognormvariate(0, 0.25)

            reopen_p = min(0.9, (0.25 if activity == "Bug" else 0.15) * reopen_mult)
            reopening_times = 0
            while rng.random() < reopen_p and reopening_times < 4:
                reopening_times += 1
                reopen_p *= 0.5

            created = START + timedelta(days=rng.randrange(span - 30))
            work_days = workdays_from(rng, created, max(1, int(dev_hours / 3) + rng.randint(0, 3)))
            open_ticket = created > END - timedelta(days=60) and rng.random() < 0.6 or rng.random() < 0.05
            state = rng.choice(STATES_OPEN) if open_ticket else "1_done"

            summary = rng.choice(SUMMARIES[activity]).format(x=rng.choice(WORDS_X), y=rng.choice(WORDS_Y))
            desc = f"#{ticket_id}: [{code}] {summary}"

            def log(user, hours, dev_type, day):
                nonlocal entry_id
                if hours <= 0:
                    return
                entries.append({
                    "id": entry_id, "task_id": ticket_id, "project_id": project_id,
                    "employee_id": USER_ID[user], "date": day.isoformat(), "unit_amount": round(hours * 4) / 4 or 0.25,
                    "dev_type": dev_type, "name": desc,
                })
                entry_id += 1

            # Development: split unevenly among devs, in daily chunks.
            weights = [rng.uniform(0.6, 1.4) for _ in dev_team]
            for dev, w in zip(dev_team, weights):
                share = dev_hours * w / sum(weights)
                days = rng.sample(work_days, k=min(len(work_days), max(1, int(share / 2.5))))
                for day in days:
                    log(dev, share / len(days), "new_feature", day)
            review_day = work_days[-1] + timedelta(days=1)
            if reviewer:
                review = min(4.0, max(0.5, 0.12 * base * speed[reviewer] * all_factor * rng.lognormvariate(0, 0.3)))
                log(reviewer, review, "other", review_day)
            qc_day = review_day + timedelta(days=rng.randint(0, 2))
            if qc:
                qc_base = qc_estimate or 0.2 * base
                log(qc, max(0.5, qc_base * qc_factor * all_factor * rng.lognormvariate(0, 0.25)), "qa", qc_day)

            # Each reopen: a dev fixes, the QC retests.
            for i in range(reopening_times):
                day = qc_day + timedelta(days=2 * i + rng.randint(1, 3))
                log(rng.choice(dev_team), rng.uniform(0.5, 0.3 * base) * dev_factor * all_factor, "fixing", day)
                if qc:
                    log(qc, rng.uniform(0.25, 0.4 * (qc_estimate or 1) + 0.25) * qc_factor, "qa", day)

            # Noise people: PM touches tickets briefly (below the default 0.5h member threshold).
            if rng.random() < 0.3:
                log(pm, 0.25, "other", created)
            if consultants and activity in ("Feature", "Support") and rng.random() < 0.2:
                log(rng.choice(consultants), rng.uniform(0.5, 3), "other", created)

            last_day = qc_day + timedelta(days=rng.randint(1, 5) + 2 * reopening_times)
            tickets.append({
                "id": ticket_id, "name": summary, "project_id": project_id, "state": state,
                "priority": rng.choices(["0", "1"], weights=[80, 20])[0],  # Odoo: 1 = starred
                "allocated_hours": estimate + qc_estimate, "reopen_count": reopening_times,
                "create_date": datetime.combine(created, datetime.min.time()).replace(hour=rng.randint(8, 17)).isoformat(sep=" "),
                "date_end": "" if open_ticket else datetime.combine(last_day, datetime.min.time()).replace(hour=rng.randint(9, 18)).isoformat(sep=" "),
            })
            ticket_id += 1

    return tickets, entries


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="data/sample", type=Path)
    p.add_argument("--seed", default=42, type=int)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    tickets, entries = generate(args.seed)
    # Free-text `name` (task title, timesheet description) is generated for realism but not
    # exported: the analysis doesn't need it and it is the easiest field to leak client details through.
    write_csv(args.out / "hr_employee.csv", [{"id": USER_ID[u[0]], "name": u[1], "role": u[2]} for u in USERS],
              ["id", "name", "role"])
    write_csv(args.out / "project_task.csv", tickets,
              ["id", "project_id", "state", "priority", "allocated_hours", "reopen_count", "create_date", "date_end"])
    write_csv(args.out / "account_analytic_line.csv", entries,
              ["id", "task_id", "project_id", "employee_id", "date", "unit_amount"])
    print(f"{len(tickets)} tickets, {len(entries)} work entries -> {args.out}")


if __name__ == "__main__":
    main()
