"""Render analysis results as one self-contained HTML page (inline SVG, no deps)."""

import math
from collections import Counter
from html import escape

CSS = """
:root { --surface:#fcfcfb; --card:#ffffff; --border:#e4e3df; --text:#0b0b0b; --text2:#52514e;
  --muted:#8a8984; --good:#2a78d6; --bad:#e34948; --neutral:#c9c8c2; --grid:#e4e3df; }
@media (prefers-color-scheme: dark) { :root:where(:not([data-theme="light"])) {
  --surface:#1a1a19; --card:#232322; --border:#383835; --text:#f0efec; --text2:#c3c2b7;
  --muted:#8f8e86; --good:#3987e5; --bad:#e66767; --neutral:#4a4a46; --grid:#383835; } }
:root[data-theme="dark"] { --surface:#1a1a19; --card:#232322; --border:#383835; --text:#f0efec;
  --text2:#c3c2b7; --muted:#8f8e86; --good:#3987e5; --bad:#e66767; --neutral:#4a4a46; --grid:#383835; }
* { box-sizing:border-box; }
body { margin:0; background:var(--surface); color:var(--text);
  font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width:1080px; margin:0 auto; padding:24px 16px 64px; }
h1 { font-size:22px; margin:0 0 4px; } h2 { font-size:17px; margin:0 0 4px; }
h3 { font-size:12px; font-weight:600; color:var(--text2); text-transform:uppercase; letter-spacing:.04em; margin:16px 0 4px; }
.sub { color:var(--text2); margin:0 0 16px; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:16px 0 24px; }
.tile, .card { background:var(--card); border:1px solid var(--border); border-radius:10px; }
.tile { padding:12px 14px; } .tile b { display:block; font-size:24px; font-variant-numeric:tabular-nums; }
.tile span { color:var(--text2); font-size:12px; }
.card { padding:18px; margin-bottom:20px; }
.legend { display:flex; flex-wrap:wrap; gap:14px; color:var(--text2); font-size:12px; margin:8px 0 12px; }
.sw { display:inline-block; width:12px; height:12px; border-radius:3px; vertical-align:-2px; margin-right:5px; }
.row { display:grid; grid-template-columns:minmax(150px,340px) 1fr 64px; align-items:center; gap:8px; min-height:28px; padding:7px 0; cursor:default; }
.row { border-bottom:1px solid var(--border); }
.row:hover { background:color-mix(in srgb, var(--text) 5%, transparent); border-radius:4px; }
.row .name { font-size:13px; line-height:1.35; overflow-wrap:anywhere; }
.row .val { text-align:right; font-variant-numeric:tabular-nums; color:var(--text2); font-size:13px; }
.track { position:relative; height:16px; }
.track:not(.plain)::before { content:""; position:absolute; left:50%; top:-6px; bottom:-6px; border-left:1px solid var(--muted); }
.bar { position:absolute; top:0; height:16px; }
.bar.neg { right:50%; border-radius:4px 0 0 4px; background:var(--good); }
.bar.pos { left:50%; border-radius:0 4px 4px 0; background:var(--bad); }
.bar.noise { background:var(--neutral); }
.ci { position:absolute; top:7px; height:2px; background:var(--text2); }
.ci::before, .ci::after { content:""; position:absolute; top:-4px; height:10px; border-left:2px solid var(--text2); }
.ci::before { left:0; } .ci::after { right:0; }
.axis { display:grid; grid-template-columns:minmax(150px,340px) 1fr 64px; gap:8px; color:var(--muted); font-size:11px; }
.axis div:nth-child(2) { display:flex; justify-content:space-between; }
@media (max-width:600px) {
  .row, .axis { grid-template-columns:1fr 56px; }
  .row .name { grid-column:1 / -1; }
  .axis div:first-child { display:none; }
}
.members { list-style:none; margin:0; padding:0; }
.members li { padding:1px 0; }
.role { display:inline-block; font-size:11px; color:var(--text2); border:1px solid var(--border);
  border-radius:4px; padding:0 5px; margin-left:4px; white-space:nowrap; }
.split { font-size:11px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:.04em;
  border-top:1px dashed var(--border); margin:8px 0 2px; padding-top:6px; }
.split:first-child { border-top:0; margin-top:0; padding-top:0; }
dl.glossary { display:grid; grid-template-columns:max-content 1fr; margin:8px 0 0; font-size:13px; border-top:1px solid var(--border); }
dl.glossary dt, dl.glossary dd { padding:8px 16px 8px 0; border-bottom:1px solid var(--border); }
dl.glossary dt { font-weight:600; } dl.glossary dd { margin:0; color:var(--text2); }
dl.glossary code { font-size:12px; color:var(--text); }
@media (max-width:600px) { dl.glossary { grid-template-columns:1fr; } dl.glossary dt { border-bottom:0; padding-bottom:0; } }
svg text { fill:var(--text); }
.edge { cursor:default; transition:opacity .15s; }
.net.focus .edge:not(.on) { opacity:.08; } .net.focus .node:not(.on) { opacity:.3; }
.node circle { fill:var(--card); stroke:var(--text2); stroke-width:2; }
.node { cursor:default; }
.arc { fill:none; stroke:var(--muted); stroke-width:4; stroke-linecap:round; opacity:.5; }
.arclabel { fill:var(--text2) !important; font-size:13px; font-weight:600; paint-order:stroke;
  stroke:var(--card); stroke-width:5px; stroke-linejoin:round; pointer-events:none; }
#tip { position:fixed; pointer-events:none; background:var(--card); color:var(--text); border:1px solid var(--border);
  border-radius:8px; padding:8px 10px; font-size:12px; box-shadow:0 4px 16px rgba(0,0,0,.15); display:none; max-width:280px; z-index:9; }
#tip b { display:block; margin-bottom:2px; }
.note { color:var(--text2); font-size:13px; }
details { margin-top:12px; } summary { cursor:pointer; color:var(--text2); }
table { border-collapse:collapse; width:100%; font-size:12px; margin-top:8px; font-variant-numeric:tabular-nums; }
th, td { padding:5px 8px; border-bottom:1px solid var(--border); text-align:right; }
th:first-child, td:first-child { text-align:left; }
.tablewrap { overflow-x:auto; }
"""

JS = """
const tip = document.getElementById('tip');
document.addEventListener('mousemove', e => {
  const t = e.target.closest('[data-tip]');
  if (!t) { tip.style.display = 'none'; return; }
  tip.innerHTML = t.dataset.tip; tip.style.display = 'block';
  const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8);
  const y = Math.min(e.clientY + 14, innerHeight - tip.offsetHeight - 8);
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
});
const net = document.querySelector('.net');
net && net.querySelectorAll('.node').forEach(n => {
  n.addEventListener('mouseenter', () => {
    net.classList.add('focus'); n.classList.add('on');
    net.querySelectorAll(`.edge[data-u~="${n.dataset.u}"]`).forEach(e => {
      e.classList.add('on');
      e.dataset.u.split(' ').forEach(u => net.querySelector(`.node[data-u="${u}"]`).classList.add('on'));
    });
  });
  n.addEventListener('mouseleave', () => {
    net.classList.remove('focus'); net.querySelectorAll('.on').forEach(x => x.classList.remove('on'));
  });
});
"""


HOURS_CI = ("hours_ci_low_pct", "hours_ci_high_pct")
REOPEN_CI = ("reopen_ci_low", "reopen_ci_high")


def pct(v):
    return f"{v:+.1f}%"


def member_list(labels):
    """'Name (login) - Role' labels -> one list item per person with a role tag."""
    items = []
    for lab in labels:
        name, _, role = lab.rpartition(" - ")
        items.append(f'<li>{escape(name)}<span class="role">{escape(role)}</span></li>')
    return f'<ul class="members">{"".join(items)}</ul>'


def diverging_rows(items, limit=None, fmt=None, split=("Best", "Worst")):
    """items: (name_html, value, tooltip_html[, (ci_low, ci_high)]). Negative = fewer hours = good (blue).
    A row whose interval crosses 0 is drawn gray (could be noise), with the interval as a whisker.
    With limit, rows before it go under split[0], the rest under split[1]."""
    if not items:
        return '<p class="note">Not enough data.</p>'
    scale = max(max(abs(x) for x in (it[1], *(it[3] if len(it) > 3 else ()))) for it in items) or 1
    fmt = fmt or pct
    scale = math.ceil(scale / 5) * 5 if scale >= 1 else math.ceil(scale * 10) / 10
    out = []
    for i, (label, v, tip, *ci) in enumerate(items):
        if limit and i in (0, limit):
            out.append(f'<div class="split">{escape(split[i > 0])}</div>')
        side = "neg" if v < 0 else "pos"
        whisker = ""
        if ci:
            lo, hi = ci[0]
            side += " noise" if lo <= 0 <= hi else ""
            whisker = f'<div class="ci" style="left:{50 + lo / scale * 50:.2f}%;width:{(hi - lo) / scale * 50:.2f}%"></div>'
        out.append(
            f'<div class="row" data-tip="{escape(tip)}"><div class="name">{label}</div>'
            f'<div class="track"><div class="bar {side}" style="width:{abs(v) / scale * 50:.2f}%"></div>{whisker}</div>'
            f'<div class="val">{fmt(v)}</div></div>')
    out.append(f'<div class="axis"><div></div><div><span>{fmt(-scale)}</span><span>0</span>'
               f'<span>{fmt(scale)}</span></div><div></div></div>')
    return "\n".join(out)


def network_svg(pairs, users, label, team, ticket_by_id, min_edge, min_shared):
    # Group nodes on a circle by each user's main project, so project teams sit together.
    main_proj = {}
    for u in {u for m in team.values() for u in m}:
        c = Counter(ticket_by_id[t]["project"] for t, m in team.items() if u in m)
        main_proj[u] = c.most_common(1)[0][0]
    order = sorted(main_proj, key=lambda u: (main_proj[u], u))
    r = 210
    cx = cy = r + 300  # room for radial labels like "Nguyen Van An (an.nguyen) - Developer"
    size = 2 * cx
    gap = 0.35  # radians between project groups
    projects = list(dict.fromkeys(main_proj[u] for u in order))
    step = (2 * math.pi - gap * len(projects)) / max(1, len(order))
    pos, angle, arcs = {}, -math.pi / 2, []
    for p in projects:
        members = [u for u in order if main_proj[u] == p]
        start = angle
        for u in members:
            pos[u] = angle
            angle += step
        arcs.append((p, start, angle - step))
        angle += gap

    def xy(a, rad=r):
        return cx + rad * math.cos(a), cy + rad * math.sin(a)

    parts = [f'<svg class="net" viewBox="0 0 {size} {size}" width="100%" style="max-width:860px;display:block;margin:auto" role="img" '
             f'aria-label="Collaboration network">']
    # Project groups: an arc just outside the nodes, name inside the circle (haloed over links).
    arc_r, labels = r + 20, []
    for p, a0, a1 in arcs:
        (x0, y0), (x1, y1) = xy(a0 - 0.06, arc_r), xy(a1 + 0.06, arc_r)
        large = 1 if a1 - a0 + 0.12 > math.pi else 0
        parts.append(f'<path class="arc" d="M{x0:.1f},{y0:.1f} A{arc_r},{arc_r} 0 {large} 1 {x1:.1f},{y1:.1f}"/>')
        lx, ly = xy((a0 + a1) / 2, r - 52)
        labels.append(f'<text class="arclabel" x="{lx:.1f}" y="{ly + 4:.1f}" text-anchor="middle">{escape(p)}</text>')

    # Neutral edges first so coloured ones draw on top.
    edges = sorted((p for p in pairs if p["shared_tickets"] >= min_edge and p["user_a"] in pos and p["user_b"] in pos),
                   key=lambda p: (p["scored_tickets"] >= min_shared and p["hours_significant"], p["jaccard"]))
    for p in edges:
        (x1, y1), (x2, y2) = xy(pos[p["user_a"]]), xy(pos[p["user_b"]])
        scored = p["scored_tickets"] >= min_shared
        v = p["hours_vs_expected_pct"]
        strong = scored and p["hours_significant"]
        color = ("var(--good)" if v < 0 else "var(--bad)") if strong else "var(--neutral)"
        opacity = min(1.0, 0.45 + abs(v) / 25) if strong else 0.7
        width = 1.5 + 14 * p["jaccard"]
        eff = (f"{pct(v)} hours, {p['reopen_vs_expected']:+.2f} reopens/ticket vs apart" if scored
               else f"fewer than {min_shared} scored tickets, efficiency not rated")
        tip = (f"<b>{escape(p['user_a_label'])}<br>{escape(p['user_b_label'])}</b>{p['shared_tickets']} shared tickets, "
               f"Jaccard {p['jaccard']}<br>{eff}")
        # Curve slightly toward the centre so edges between neighbours stay visible.
        mx, my = (x1 + x2) / 2 * 0.75 + cx * 0.25, (y1 + y2) / 2 * 0.75 + cy * 0.25
        parts.append(f'<path class="edge" data-u="{p["user_a"]} {p["user_b"]}" '
                     f'data-tip="{escape(tip)}" d="M{x1:.1f},{y1:.1f} Q{mx:.1f},{my:.1f} {x2:.1f},{y2:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="{width:.1f}" stroke-linecap="round" opacity="{opacity:.2f}"/>')

    for u, a in pos.items():
        x, y = xy(a)
        n = sum(u in m for m in team.values())
        lx, ly = xy(a, arc_r + 10)
        # Radial label, flipped on the left half so it never reads upside down.
        left = math.cos(a) < 0
        deg = math.degrees(a) + (180 if left else 0)
        anchor = "end" if left else "start"
        tip = f"<b>{escape(label[u])}</b>{escape(main_proj[u])}, {n} tickets"
        if u in users:
            tip += f"<br>Individual: {pct(users[u]['hours_vs_expected_pct'])} hours vs expected"
        parts.append(f'<g class="node" data-u="{u}" data-tip="{escape(tip)}">'
                     f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{5 + math.sqrt(n) * 0.9:.1f}"/>'
                     f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" dominant-baseline="middle" font-size="12" '
                     f'transform="rotate({deg:.1f} {lx:.1f} {ly:.1f})">{escape(label[u])}</text></g>')
    parts.extend(labels)  # last, so project names sit above the links
    parts.append("</svg>")
    return "\n".join(parts)


def render(groups, users, ctx, args):
    team, ticket_by_id, label = ctx["team"], ctx["ticket_by_id"], ctx["label"]
    user_map = {u["user_id"]: u for u in users} if args.show_individuals else {}
    rated = [g for g in groups if g["scored_tickets"] >= args.min_shared]
    pairs = []
    for g in groups:
        if g["size"] == 2:
            a, b = map(int, g["members"].split(" + "))
            pairs.append(dict(g, user_a=a, user_b=b, user_a_label=label[a], user_b_label=label[b]))

    def g_label(g):
        return member_list(g["member_labels"].split(" + "))

    def g_tip(g):
        names = "<br>".join(escape(x) for x in g["member_labels"].split(" + "))
        return (f"<b>{names}</b>{g['scored_tickets']} closed estimated tickets, {g['shared_tickets']} shared tickets<br>"
                f"Hours vs apart: {pct(g['hours_vs_expected_pct'])} "
                f"(95% CI {pct(g['hours_ci_low_pct'])} to {pct(g['hours_ci_high_pct'])})<br>"
                f"Reopens vs apart: {g['reopen_vs_expected']:+.2f}/ticket "
                f"(95% CI {g['reopen_ci_low']:+.2f} to {g['reopen_ci_high']:+.2f})<br>"
                f"Avg reopen: {g['reopen_avg']} (overall: {ctx['reopen_avg']:.2f})")

    def best_worst(rows, key, ci, fmt=None, split=("Faster together", "Slower together")):
        n = args.top // 2 or 1
        rows = sorted(rows, key=lambda g: g[key])
        best, worst = rows[:n], [g for g in rows[-n:] if g not in rows[:n]]
        items = [(g_label(g), g[key], g_tip(g), (g[ci[0]], g[ci[1]])) for g in best + worst]
        return diverging_rows(items, limit=len(best) if worst else None, fmt=fmt, split=split)

    def together(mix_size):
        out = []
        for mix in sorted({g["role_mix"] for g in groups if g["size"] == mix_size}):
            top = sorted((g for g in groups if g["role_mix"] == mix), key=lambda g: -g["jaccard"])[:3]
            out.append(f'<h3>{escape(mix)}</h3>')
            out.extend(
                f'<div class="row" data-tip="{escape(g_tip(g))}"><div class="name">{g_label(g)}</div>'
                f'<div class="track plain"><div class="bar" style="left:0;width:{g["jaccard"] * 100:.1f}%;'
                f'background:var(--text2);border-radius:0 4px 4px 0"></div></div>'
                f'<div class="val">{g["jaccard"]:.2f}</div></div>' for g in top)
        out.append('<div class="axis"><div></div><div><span>0</span><span>0.5</span><span>1.0</span></div><div></div></div>')
        return "\n".join(out)

    user_items = [(member_list([u["label"]]), u["hours_vs_expected_pct"],
                   f"<b>{escape(u['label'])}</b>{u['scored_tickets']} closed estimated tickets, "
                   f"{u['tickets']} tickets total<br>Avg reopen: {u['reopen_avg']}") for u in users if u["scored_tickets"]]

    cols = ["size", "member_labels", "role_mix", "shared_tickets", "jaccard", "lift", "scored_tickets",
            "hours_vs_expected_pct", "hours_ci_low_pct", "hours_ci_high_pct",
            "reopen_vs_expected", "reopen_ci_low", "reopen_ci_high", "reopen_avg"]
    heads = ["Size", "Members", "Roles", "Shared tickets", "Jaccard", "Lift", "Scored tickets",
             "Hours vs apart %", "95% low", "95% high", "Reopens vs apart", "95% low", "95% high", "Avg reopen"]
    clear = sum(g["hours_significant"] for g in rated)
    individuals = f"""<div class="card">
  <h2>Individual baseline</h2>
  <p class="note">Hours compared with tickets of the same project and team size, across all of a person's tickets.
  Shown because <code>--show-individuals</code> was passed. Not a performance rating.</p>
  {diverging_rows(user_items, limit=sum(v < 0 for _, v, _ in user_items) or None,
                  split=("Faster than comparable tickets", "Slower than comparable tickets"))}
</div>
""" if args.show_individuals else ""
    def cell(g, c):
        return member_list(g[c].split(" + ")) if c == "member_labels" else escape(str(g[c]))

    table = "".join("<tr>" + "".join(f"<td>{cell(g, c)}</td>" for c in cols) + "</tr>"
                    for g in sorted(groups, key=lambda g: (g["size"], g["synergy"])))
    sizes = Counter(min(len(m), 4) for m in team.values())

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Team Collaboration Report</title><style>{CSS}</style></head>
<body><main>
<h1>Who works with whom, and which teams are most efficient?</h1>
<p class="sub">Source: <code>{escape(str(args.data))}</code>, roles: {escape(args.roles)},
at least {args.min_hours}h logged on a ticket to count as a member</p>

<div class="tiles">
  <div class="tile"><b>{len(ticket_by_id)}</b><span>tickets</span></div>
  <div class="tile"><b>{ctx["scored"]}</b><span>closed tickets with estimate</span></div>
  <div class="tile"><b>{sizes[3]}</b><span>tickets with 3 people</span></div>
  <div class="tile"><b>{sizes[2]} / {sizes[4]}</b><span>tickets with 2 / 4+ people</span></div>
  <div class="tile"><b>{len(rated)}</b><span>pairs &amp; trios with enough data</span></div>
  <div class="tile"><b>{clear}</b><span>of them clearly faster or slower (95%)</span></div>
</div>

<div class="card">
  <h2>What the numbers mean</h2>
  <p class="note">A <b>member</b> of a ticket is a {escape(args.roles)} user who logged at least {args.min_hours}h on it.
  A <b>group</b> is any pair or trio of members on the same ticket.</p>
  <dl class="glossary">
    <dt>Shared tickets</dt><dd>Tickets where every member of the group is a member.</dd>
    <dt>Jaccard</dt><dd><code>shared tickets / tickets with at least one of them</code> (multi-person tickets only).
      0 = never together, 1.0 = always together. A and B on 20 tickets, together on 5: 5 / 20 = 0.25.</dd>
    <dt>Lift</dt><dd><code>shared tickets / expected</code>, expected = in each project
      <code>n<sub>A</sub> * n<sub>B</sub> / n<sub>project</sub></code> (trio: <code>n<sub>A</sub>n<sub>B</sub>n<sub>C</sub> / n<sub>project</sub><sup>2</sup></code>),
      i.e. how often they would meet if staffed at random. &gt; 1 = together more than chance. With only 2 or 3 people per
      ticket it stays near 1, so Jaccard is used for ranking.</dd>
    <dt>Closed &amp; estimated</dt><dd>Shared tickets that are closed and have a dev estimate. Only these count for hours and
      reopens; groups need {args.min_shared}+ to be rated.</dd>
    <dt>Hours vs apart</dt><dd>Per ticket: <code>ln(team hours / (dev estimate + QC estimate))</code>, minus the average of
      tickets in the same project and team size. Group value = average on shared tickets minus each member's average on
      tickets <i>without</i> the others, shown as %. -15% means about 15% fewer hours together than apart.</dd>
    <dt>Reopens vs apart</dt><dd>Same, using <code>reopening_times</code>. -0.20 = 0.2 fewer reopens per ticket together.</dd>
    <dt>95% interval</dt><dd>Range the true value likely falls in, from the spread of the tickets behind it
      (shown as a whisker on each bar). If it crosses 0 the bar is <b>gray</b>: the difference could be noise.
      With {len(rated)} groups rated, about {round(len(rated) * 0.05)} will still look clear by chance.</dd>
    <dt>Avg reopen</dt><dd>Plain average of <code>reopening_times</code> on the group's scored tickets
      (overall: {ctx['reopen_avg']:.2f}).</dd>
    <dt>Shrinkage</dt><dd>Averages are <code>sum / (n + {args.shrink:g})</code> instead of <code>sum / n</code>, so a group with
      few tickets is pulled toward 0 and can't top a list by luck.</dd>
  </dl>
</div>

<div class="card">
  <h2>Collaboration network</h2>
  <p class="note">Each dot is a person, grouped by main project. Thicker links mean the two work on the same
  tickets more often. Colour shows whether they are faster together than apart. Hover a person to see only their links.</p>
  <div class="legend">
    <span><i class="sw" style="background:var(--good)"></i>Faster together than apart</span>
    <span><i class="sw" style="background:var(--bad)"></i>Slower together than apart</span>
    <span><i class="sw" style="background:var(--neutral)"></i>Could be noise (95% interval crosses 0) or fewer than {args.min_shared} tickets</span>
    <span>Only pairs with {args.min_edge}+ shared tickets are drawn</span>
  </div>
  {network_svg(pairs, user_map, label, team, ticket_by_id, args.min_edge, args.min_shared)}
</div>

<div class="card">
  <h2>Best and worst trios: hours</h2>
  <p class="note">A typical ticket is Developer + TPM (code review) + QC. Hours the trio spends together compared with
  each member working without the other two, on comparable tickets (same project and team size).
  <b style="color:var(--good)">Negative</b> = faster together. <b style="color:var(--bad)">Positive</b> = slower.
  Only trios with {args.min_shared}+ closed, estimated shared tickets.</p>
  {best_worst([g for g in rated if g["size"] == 3], "hours_vs_expected_pct", HOURS_CI)}
</div>

<div class="card">
  <h2>Best and worst pairs: hours</h2>
  <p class="note">Same measure for any two people: Developer + Developer, Developer + QC, Developer + TPM, TPM + QC.</p>
  {best_worst([g for g in rated if g["size"] == 2], "hours_vs_expected_pct", HOURS_CI)}
</div>

<div class="card">
  <h2>Quality: fewest and most reopens</h2>
  <p class="note">Fewer hours only counts if the ticket doesn't come back. Reopens per ticket compared with the members
  working apart. <b style="color:var(--good)">Negative</b> = fewer reopens together. Pairs and trios combined.</p>
  {best_worst(rated, "reopen_vs_expected", REOPEN_CI, fmt=lambda v: f"{v:+.2f}", split=("Fewer reopens", "More reopens"))}
</div>

<div class="card">
  <h2>Most often together</h2>
  <p class="note">Ranked by Jaccard (1.0 = always together). Compare within one role mix only: a project's TPM reviews most of its tickets, so Developer + TPM is naturally high.</p>
  {together(2)}
  {together(3)}
</div>

{individuals}
<div class="card">
  <h2>How to read this</h2>
  <p class="note">Treat these as hints to look into, not verdicts. Gray bars may be noise. A colored bar
  means the difference is stable, not that the pair causes it: who gets staffed on which tickets matters too.
  Effects that only touch one part of the work (e.g. QC time, ~15% of a ticket) are hard to see in total hours. Estimates are set by PMs and carry their own bias. Do not use this to rank or evaluate individuals.</p>
  <details><summary>Full table of all pairs and trios ({len(groups)})</summary>
  <div class="tablewrap"><table><thead><tr>{"".join(f"<th>{h}</th>" for h in heads)}</tr></thead>
  <tbody>{table}</tbody></table></div></details>
</div>
</main><div id="tip"></div><script>{JS}</script></body></html>
"""
