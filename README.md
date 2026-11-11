# team-collab-mining

Find out, from per-ticket working hours:

- **who works together** most often, and
- **which pairs and trios finish tickets faster** (or slower, or with more reopens) than the same
  people do apart.

Python 3.10+, standard library only, nothing to install. Ships with a synthetic dataset so you can
try it in one minute.

![Report: metric glossary and collaboration network](docs/report.png)

## Quick start

```bash
git clone git@github.com:xaviedoanhduy/team-collab-mining.git
cd team-collab-mining
python3 analyze.py              # analyze data/sample/, print a summary, write reports/
xdg-open reports/report.html    # macOS: open reports/report.html
```

The terminal shows the strongest results; the HTML report has everything, with charts and hover
details. Other commands:

```bash
python3 generate_sample.py      # rebuild data/sample/ (same seed, same data)
python3 -m unittest -v          # check the analysis still finds the effects planted in the sample
```

## Use your own data

Put three CSV files in a folder and run `python3 analyze.py --data path/to/folder`.
Only the **bold** columns are required; extra columns are ignored.

**users.csv** (one row per person)

| column | meaning |
|---|---|
| **user_id** | numeric id (see [User ids](#user-ids) if you don't have one) |
| **role** | `dev`, `tpm`, `qa`, `pm` or `consultant` (`qa` is shown as QC) |
| login, name | only used for labels in the report: `Name (login) - Role` |

**tickets.csv** (one row per ticket)

| column | meaning |
|---|---|
| **id** | ticket id |
| **project** | tickets are only compared within the same project |
| **state** | only `closed` tickets count for hours and reopens |
| **development_time** | dev estimate in hours; `0` or empty = not estimated (skipped) |
| **reopening_times** | how many times the ticket was reopened |
| qc_estimate | QC estimate in hours, added to the dev estimate |

**work_entries.csv** (one row per time entry)

| column | meaning |
|---|---|
| **ticket_id** or **task_id** | ticket the time was logged on; empty = skipped |
| **user_id** | who logged it |
| **duration_hour** | hours |

Do not export free-text fields (ticket titles, entry descriptions): the analysis doesn't need them
and they are the easiest way to leak client details.

### User ids

If `users.csv` has no `user_id`, one is derived from `HMAC-SHA256(salt, name|login)`. The salt is
a secret you keep outside the repo and outside the exported files:

```bash
export TEAM_MINING_SALT="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"  # once, store it safely
```

The same salt always gives the same id, and without it nobody can map ids back to people.
Without `user_id` and without the salt, the run stops with an error.

## Reading the results

| metric | meaning |
|---|---|
| shared tickets | tickets where every member of the group logged at least `--min-hours` |
| Jaccard | shared tickets / tickets with any of them. 0 = never together, 1 = always together. Compare within one role mix only: a TPM reviews most of a project, so Developer + TPM is naturally high. |
| hours vs apart | e.g. `-15%`: the group needs about 15% fewer hours together than its members need apart, on comparable tickets |
| reopens vs apart | e.g. `-0.16`: 0.16 fewer reopens per ticket together than apart |
| 95% CI | range the true value likely falls in. If it crosses 0 the result is marked **could be noise** (gray in the report). |
| closed & estimated | shared tickets used for hours and reopens; a group needs `--min-shared` (5) of them to be rated |

A colored (clear) result means the difference is stable, not that the pair causes it: who gets
staffed on which tickets matters too. Treat results as hints to look into, not verdicts.

### Outputs in `reports/`

| file | content |
|---|---|
| `report.html` | single page, no dependencies, light and dark: glossary, network, best/worst trios and pairs, reopens, most-together, full table |
| `groups.csv` | one row per pair or trio with every metric above, including `*_ci_low`, `*_ci_high`, `*_significant` |
| `huim_spmf.txt`, `huim_items.csv` | the same tickets in SPMF format (`items:TU:utilities`) for high-utility itemset mining tools |
| `users.csv` | only with `--show-individuals` |

## Options

| option | default | meaning |
|---|---|---|
| `--data` | `data/sample` | folder with the three CSV files |
| `--out` | `reports` | output folder |
| `--roles` | `dev,tpm,qa` | roles that count as team members (PMs only touch tickets briefly) |
| `--min-hours` | `0.5` | hours on a ticket to count as a member |
| `--min-shared` | `5` | closed & estimated shared tickets needed to rate a group |
| `--shrink` | `5` | pulls small groups toward 0 so luck doesn't top the list |
| `--top` | `8` | rows per best/worst list |
| `--min-edge` | `3` | shared tickets needed to draw a link in the network |
| `--show-individuals` | off | also rank individuals; off because this is a team tool, not a rating |

## How it works

1. **Team of a ticket**: users of the chosen roles who logged at least `--min-hours` on it.
   A typical ticket: 1 or 2 developers, the project's TPM (code review) and a QC.
2. **Groups**: every pair and trio inside a team.
3. **Hours per ticket**: `ln(team hours / (dev estimate + QC estimate))`, minus the average of
   tickets in the same project with the same team size. This residual is negative when the
   ticket went faster than comparable work.
4. **Reopens per ticket**: `reopening_times`, residual computed the same way.
5. **Together vs apart**: the group's average residual on shared tickets, minus each member's
   average on tickets **without the other members**. Using all of a member's tickets would mix
   the group's own effect into its baseline. Averages are `sum / (n + shrink)`.
6. **95% interval**: shared and apart tickets are separate sets, so their variances add. Each set
   uses at least the variance of all scored tickets, so a small uniform set (7 tickets, 0 reopens)
   doesn't get a falsely narrow interval. With ~150 groups rated, about 5% look clear by chance.

## Does it work? The sample dataset

`data/sample/` is synthetic: 930 tickets, 5 projects, 29 people, Jan 2025 to Oct 2026, with
realistic noise (individual speed, unestimated and open tickets, 2-dev tickets, one project without
QC). A few groups have effects planted on purpose; the tests check the analysis finds them.

| planted group | planted effect | analysis finds |
|---|---|---|
| dung.pham + linh.ly (Dev + Dev) | 0.7x dev hours, 0.5x reopens | best of 78 pairs, -15% (CI -24% to -5%) |
| khanh.ngo + phong.nghiem + thao.phan (Dev + TPM + QC) | 0.75x hours, 0.4x reopens | 3rd of 67 trios, -14%; fewest-reopens pair inside it |
| giang.hoang + khoa.truong + yen.quach (Dev + TPM + QC) | 1.35x hours, 1.8x reopens | worst trio, +26% (CI +15% to +38%) |
| son.kieu + trang.vo (Dev + QC) | 1.5x QC hours, 1.8x reopens | 2nd worst pair, +19%; reopens +0.19 but could be noise |
| long.mai + ngoc.ha (Dev + Dev) | usually staffed together | highest Jaccard among Dev + Dev |
| hieu.bui + lam.duong (Dev + Dev) | 1.45x hours, 2x reopens | **not rated**: only 1 closed & estimated shared ticket |
| hoa.do + thao.phan (Dev + QC) | 0.6x QC hours, 0.4x reopens | **missed**: QC is ~15% of a ticket's hours |

Known limits, all visible above:

- Rare combinations can't be judged.
- Reopens are a weak signal (0.14 per ticket on average); most planted reopen effects stay "could be noise".
- An effect on one part of the work (QC time only) drowns in total hours.
- Some unplanted groups look clear because they share a member with a planted group.

## Before using real data

- Working hours are personal data. Agree on the purpose with the people concerned first, and
  present results as team-composition hints, never as individual ratings.
- Once people know the metric, the way they log time changes.
- Estimates are set by people and carry their own bias.

## Project layout

| file | purpose |
|---|---|
| `analyze.py` | loading, analysis, terminal summary, CSV and SPMF output |
| `report.py` | the HTML report |
| `generate_sample.py` | synthetic dataset with planted effects |
| `test_analyze.py` | tests against the planted effects |

## License

MIT, see [LICENSE](LICENSE).
