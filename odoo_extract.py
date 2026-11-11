"""Export Odoo 17+ tasks and timesheets to the CSV files analyze.py reads.

Reads project.task, account.analytic.line and hr.employee over XML-RPC and writes
hr_employee.csv, project_task.csv, account_analytic_line.csv. Free-text fields
(task titles, timesheet descriptions) are never read.

    export ODOO_PASSWORD=...   # password or API key (asked if unset)
    python3 odoo_extract.py --url https://odoo.example.com --db prod --user me@example.com \\
        --role-map "Developer=dev,Technical Lead=tpm,Tester=qa" --since 2025-01-01

With TEAM_MINING_SALT set, every id is replaced by HMAC-SHA256(salt, "kind:id") and names are left out.
"""

import argparse
import csv
import getpass
import hashlib
import hmac
import os
import xmlrpc.client
from collections import Counter
from pathlib import Path

SALT_ENV = "TEAM_MINING_SALT"
CHUNK = 1000
ALL = {"context": {"active_test": False}}  # archived tasks and employees still count


def pseudonym(salt, kind, rid):
    """HMAC-SHA256(salt, 'kind:id') cut to 48 bits. Same salt -> same id across exports;
    without the salt nobody can map it back to the Odoo record."""
    return int(hmac.new(salt.encode(), f"{kind}:{rid}".encode(), hashlib.sha256).hexdigest()[:12], 16)


def reopen_counts(changes, folded):
    """Times each task left a folded (closed) stage. changes: (task_id, old_stage_id, new_stage_id)."""
    return Counter(t for t, old, new in changes if old in folded and new not in folded)


def parse_role_map(text):
    """'Developer=dev,Tester=qa' -> {'developer': 'dev', 'tester': 'qa'} (job titles match case-insensitively)."""
    pairs = (item.split("=", 1) for item in text.split(",") if item.strip())
    return {title.strip().lower(): role.strip() for title, role in pairs}


def m2o(value):
    return value[0] if value else None


class Odoo:
    def __init__(self, url, db, user, password):
        self.db, self.password = db, password
        self.uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(db, user, password, {})
        if not self.uid:
            raise SystemExit("Odoo login failed")
        self.models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)

    def call(self, model, method, args, kwargs=None):
        return self.models.execute_kw(self.db, self.uid, self.password, model, method, args, kwargs or {})

    def read(self, model, domain, fields):
        ids = self.call(model, "search", [domain], ALL)
        return [r for i in range(0, len(ids), CHUNK)
                for r in self.call(model, "read", [ids[i:i + CHUNK]], {"fields": fields, **ALL})]

    def read_in(self, model, field, values, fields, domain=()):
        """read() with `field in values`, split so the domain stays small."""
        values = list(values)
        return [r for i in range(0, len(values), CHUNK)
                for r in self.read(model, [*domain, (field, "in", values[i:i + CHUNK])], fields)]


def stage_changes(odoo, task_ids):
    """(task_id, old_stage_id, new_stage_id) from the chatter's tracking values. Needs admin rights."""
    tracks = odoo.read_in("mail.tracking.value", "mail_message_id.res_id", task_ids,
                          ["mail_message_id", "old_value_integer", "new_value_integer"],
                          domain=[("field_id.model", "=", "project.task"), ("field_id.name", "=", "stage_id"),
                                  ("mail_message_id.model", "=", "project.task")])
    task_of = {m["id"]: m["res_id"] for m in
               odoo.read_in("mail.message", "id", {m2o(t["mail_message_id"]) for t in tracks}, ["res_id"])}
    return [(task_of[m2o(t["mail_message_id"])], t["old_value_integer"], t["new_value_integer"]) for t in tracks]


def write_csv(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(fields)
        w.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--url", required=True, help="Odoo base URL, e.g. https://odoo.example.com")
    p.add_argument("--db", required=True, help="database name")
    p.add_argument("--user", required=True, help="login; the password or API key comes from ODOO_PASSWORD")
    p.add_argument("--out", default="data/odoo", type=Path, help="output folder (default: data/odoo)")
    p.add_argument("--since", help="only timesheets on or after this date (YYYY-MM-DD)")
    p.add_argument("--project", action="append", type=int, default=[], help="project id to include (repeatable)")
    p.add_argument("--role-map", default="", help="job title=role pairs, e.g. 'Developer=dev,Tester=qa'")
    args = p.parse_args()

    salt = os.environ.get(SALT_ENV)
    odoo = Odoo(args.url.rstrip("/"), args.db, args.user,
                os.environ.get("ODOO_PASSWORD") or getpass.getpass("Odoo password or API key: "))

    def pid(kind, rid):
        return pseudonym(salt, kind, rid) if salt and rid else rid

    domain = [("task_id", "!=", False)]
    domain += [("date", ">=", args.since)] if args.since else []
    domain += [("project_id", "in", args.project)] if args.project else []
    lines = odoo.read("account.analytic.line", domain, ["task_id", "employee_id", "unit_amount", "date"])
    task_ids = {m2o(line["task_id"]) for line in lines}
    tasks = odoo.read_in("project.task", "id", task_ids, ["project_id", "state", "priority", "allocated_hours",
                                                          "stage_id", "create_date", "date_end"])
    try:
        folded = {s["id"] for s in odoo.read("project.task.type", [("fold", "=", True)], ["id"])}
        reopens = reopen_counts(stage_changes(odoo, task_ids), folded)
    except xmlrpc.client.Fault as e:  # usually: no access to mail.tracking.value
        print(f"warning: reopen_count left empty, could not read stage history ({e.faultString.splitlines()[-1]})")
        reopens = None
    employees = odoo.read_in("hr.employee", "id", {m2o(line["employee_id"]) for line in lines},
                             ["name", "job_id", "job_title"])

    role_map = parse_role_map(args.role_map)
    unmapped = Counter()
    rows = []
    for e in employees:
        title = (e["job_title"] or (e["job_id"] and e["job_id"][1]) or "").strip()
        role = role_map.get(title.lower(), "") if role_map else title.lower()
        if not role:
            unmapped[title or "(no job title)"] += 1
        rows.append((pid("employee", e["id"]), "" if salt else e["name"], role))

    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "hr_employee.csv", ["id", "name", "role"], rows)
    write_csv(args.out / "project_task.csv",
              ["id", "project_id", "state", "priority", "allocated_hours", "reopen_count", "create_date", "date_end"],
              ((pid("task", t["id"]), pid("project", m2o(t["project_id"])), t["state"], t["priority"],
                t["allocated_hours"], "" if reopens is None else reopens.get(t["id"], 0),
                t["create_date"], t["date_end"] or "") for t in tasks))
    write_csv(args.out / "account_analytic_line.csv", ["task_id", "employee_id", "unit_amount", "date"],
              ((pid("task", m2o(line["task_id"])), pid("employee", m2o(line["employee_id"])),
                line["unit_amount"], line["date"]) for line in lines if line["employee_id"]))

    print(f"{len(employees)} employees, {len(tasks)} tasks, {len(lines)} timesheets -> {args.out}/"
          + (" (ids pseudonymized)" if salt else ""))
    if unmapped:
        print("No role for these job titles (add them to --role-map):",
              ", ".join(f"{t} ({n})" for t, n in unmapped.most_common()))


if __name__ == "__main__":
    main()
