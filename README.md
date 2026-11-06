# team-collab-mining

From per-ticket working hours, find **who works together** and **which pairs and
trios deliver tickets more efficiently**. Ships with a synthetic dataset; any
time-tracking export mapped to the CSV format below works.

Stdlib only, Python 3.10+. No install.

```bash
python3 generate_sample.py      # (re)build data/sample/ (seeded, deterministic)
python3 analyze.py              # prints top pairs, writes reports/ (open reports/report.html)
python3 -m unittest -v          # checks the analysis recovers the planted pairs
```

Options: `python3 analyze.py --help` (`--roles dev,tpm,qa`, `--min-hours`, `--min-shared`, `--min-edge`, `--shrink`, `--top`, `--data`).

## Input format (`data/sample/`)

**users.csv**: `user_id, login, name, role` (role: `pm | tpm | dev | qa | consultant`; `qa` is shown as QC)

`user_id` is a numeric user id; all processing is keyed on it. If the column is missing or empty,
a 48-bit id is derived as `HMAC-SHA256(salt, name|login)`, with the secret salt from `TEAM_MINING_SALT`
(required in that case, the run stops otherwise). The same salt gives the same id across exports; without the salt the
id can't be recomputed from a user list. Keep the salt out of git and away from the exported files.

```bash
export TEAM_MINING_SALT="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"  # once, store it safely
```

**tickets.csv** (one row per ticket)

| column | note |
|---|---|
| id | |
| project, activity, state, priority | `state = closed` is required to score efficiency |
| owner_id, developer_id | numeric user ids |
| development_time | dev estimate (h), `0` = not estimated (skipped) |
| qc_estimate | QC estimate (h), 20 % of dev estimate in the sample |
| time_spent, sum_qc_time, fixing_time_spent | hours of all / `qa` / `fixing` entries |
| reopening_times | |
| create_date, closing_datetime | empty closing = still open |

**work_entries.csv** (one row per time entry)

`id, ticket_id, project, user_id, date, duration_hour, dev_type`

Free-text `name` (ticket title, work entry description) is not exported: not needed, and the easiest field
to leak client details through.

- Ticket column: `ticket_id` or `task_id`; the first non-empty one is used. Entries linked to no ticket are skipped.
- User column: `user_id` only (required). Logins never appear in work entries.

`dev_type`: `new_feature` (coding), `fixing` (after reopen), `qa` (QC), `other` (review, PM, consulting).

## Method

1. **Team of a ticket** = users of the chosen roles (default `dev,tpm,qa`) who logged at least `--min-hours`.
   Typical team: 1 or 2 developers, the project's TPM (code review) and a QC: 3 people, 2 without review.
   PMs are excluded by default (short touches on many tickets).
2. **Groups** = every pair and trio inside a ticket's team.
3. **Together**: Jaccard over multi-person tickets. Compare within one role mix only: a TPM reviews
   most of a project's tickets, so Developer + TPM is naturally higher than Developer + Developer.
4. **Hours**: `ln(team hours / (dev estimate + QC estimate))` on closed, estimated tickets, minus the
   mean of tickets in the same project and team size, giving the residual. Negative = faster than comparable work.
5. **Quality**: `reopening_times`, residual the same way. Fewer hours with more reopens isn't efficient.
6. **Synergy** of a group = its shared-ticket residual minus the average residual of each member on
   tickets **without the other members**: "are they better together than apart?". Using all of a
   member's tickets instead would leak the group's own effect into the baseline.
   Means are shrunk (`sum / (n + shrink)`) so groups with few shared tickets don't top the list.

`hours_vs_expected_pct = -15` means about 15 % fewer hours together than apart. `reopen_vs_expected = -0.16` means
0.16 fewer reopens per ticket.

## Outputs (`reports/`)

- `report.html`: self-contained page (no deps, light/dark): metric glossary, collaboration network grouped by
  project, best/worst trios and pairs (hours), fewest/most reopens, most-together per role mix,
  individual baseline, full table. Hover for details.
- `groups.csv`: size, members (user ids), `Name (login) - Role` labels, role_mix, shared_tickets, any_tickets (Jaccard denominator), jaccard, lift,
  scored_tickets, synergy, hours_vs_expected_pct, reopen_vs_expected, reopen_avg
- `users.csv`: user_id, label, role, individual hours and reopen
- `huim_spmf.txt` + `huim_items.csv` (`item, user_id`): HUIM input in SPMF format (`items:TU:utilities`).
  Utility of a user on a ticket = their hour share of
  `estimate * min(2, estimate / team_hours) / (1 + reopening_times)` times 10 (estimate = dev + QC),
  so faster delivery without reopen is worth more.

## Sample dataset: planted truth

930 tickets, ~5.9k entries, 5 projects, 29 users (3 PM, 4 TPM, 16 dev, 4 QC, 2 consultants),
Jan 2025 to Oct 2026. Team sizes: 573 tickets with 3 people, 232 with 4, 93 with 2. Realistic noise: individual speed
varies, ~6 % tickets unestimated, ~10 % still open, big tickets more often get 2 devs, review lowers
reopens, PM touches of 0.25 h (below the member threshold), one project without QC.

| group | planted | analysis finds |
|---|---|---|
| dung.pham + linh.ly (Dev + Dev) | 0.7x dev hours, 0.5x reopen | best pair (-15 %) |
| khanh.ngo + phong.nghiem + thao.phan (Dev + TPM + QC) | 0.75x all hours, 0.4x reopen | 3rd best trio (-14 %), its pairs top-3 |
| giang.hoang + khoa.truong + yen.quach (Dev + TPM + QC) | 1.35x all hours, 1.8x reopen | worst trio (+26 %) |
| son.kieu + trang.vo (Dev + QC) | 1.5x QC hours, 1.8x reopen | 2nd worst pair (+19 %), near-worst reopens |
| long.mai + ngoc.ha (Dev + Dev) | often staffed together | top Jaccard among Dev + Dev |
| hieu.bui + lam.duong (Dev + Dev) | 1.45x hours, 2x reopen | **not rated**: only 2 shared tickets |
| hoa.do + thao.phan (Dev + QC) | 0.6x QC hours, 0.4x reopen | **missed** (-2 %): QC is ~15 % of ticket hours |

The last two rows are the method's real limits: rare combinations can't be judged, and effects on
only one part of the work drown in total-hours noise. A per-role metric (`sum_qc_time / qc_estimate`
for Dev + QC) would catch the latter; not built yet. Some unplanted groups also show +/-10 %: noise at
~10 shared tickets. Treat results as hints to look into, not verdicts.

## Caveats before real data

- Working hours are personal data; present results as team-composition hints, not individual rankings.
- If people learn the metric, logging behaviour changes. Estimates are made by PMs and are biased too.

## License

MIT, see [LICENSE](LICENSE).
