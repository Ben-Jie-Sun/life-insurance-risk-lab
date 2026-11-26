"""Portable JSON/CSV evidence and a self-contained HTML inspection report."""

import csv
from html import escape
import json
from pathlib import Path
import platform

from .money import format_inr
from .simulation import Result
from .traces import explain_month


def _dump(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _page(title: str, body: str) -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>""" + escape(title) + """</title><style>
:root{font-family:system-ui,sans-serif;color:#1c2d3b;background:#f0f4f5}
body{max-width:1200px;margin:40px auto;padding:0 24px;line-height:1.55}
h1{font-size:2rem;line-height:1.2} h2{font-size:1.3rem;margin-top:32px}
.eyebrow{color:#426671;font-weight:650;letter-spacing:.06em;font-size:.8rem}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
.card{background:white;padding:18px;border:1px solid #d5dfe2;border-radius:10px}
.value{display:block;font-size:1.35rem;font-weight:700;margin-top:8px}
.note{border-left:4px solid #19857b;background:#e0efec;padding:12px 18px}
.warning{border-left:4px solid #b06523;background:#fff0dc;padding:12px 18px}
.scroll{overflow:auto;background:white;border:1px solid #d5dfe2;border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:.85rem;white-space:nowrap}
th,td{padding:10px 12px;border-bottom:1px solid #e4eaec;text-align:right}
th{background:#173f4c;color:white}td:first-child,th:first-child{text-align:left}
tbody tr:hover{background:#eff7f5}.bad{background:#fff0dc}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#fff;padding:16px;border-radius:8px}
a{color:#146f77}footer{color:#5a6c74;font-size:.85rem;margin:32px 0}
</style></head><body>""" + body + """
<footer>Life Insurance Lab v0.2 · synthetic assumptions · virtual money · Python standard library</footer>
</body></html>"""


def write_result(result: Result, output: str | Path) -> Path:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    payload = result.as_dict()
    payload["runtime"] = {"python": platform.python_version(), "application": "0.2.0"}
    _dump(output / "result.json", payload)
    with (output / "monthly.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(result.monthly[0]))
        writer.writeheader()
        writer.writerows(result.monthly)
    s = result.summary
    cards = (
        ("Monthly premium", format_inr(result.contract["premium_paise"])),
        ("Fixed death benefit", format_inr(s["sum_assured_paise"])),
        ("Policies issued", str(s["policies_issued"])),
        ("Final net assets", format_inr(s["net_assets_paise"])),
        ("Economic surplus", format_inr(s["economic_surplus_paise"])),
        ("Unpaid claims at end", format_inr(s["unpaid_claims_paise"])),
    )
    card_html = "".join(
        f'<div class="card">{escape(label)}<span class="value">{escape(value)}</span></div>'
        for label, value in cards
    )
    status = "Payment shortfall occurred" if s["payment_shortfall_ever"] else "No payment shortfall observed in this path"
    css = "warning" if s["payment_shortfall_ever"] else "note"
    heading = (
        '<div class="eyebrow">COURSE PROJECT / INSPECTION BUILD</div>'
        f'<h1>{escape(result.config["policy"]["name"])}</h1>'
        f'<p>Experience scenario: <strong>{escape(result.scenario["name"])}</strong>. '
        'Premium, benefit and reserve valuation basis remain fixed.</p>'
        '<p>One seeded projection from acquisition through the last contract expiry.</p>'
        f'<div class="cards">{card_html}</div>'
        f'<p class="{css}"><strong>{escape(status)}</strong>. '
        'This is one synthetic path, not a guarantee or estimated failure probability.</p>'
        f'<p>Seed: {s["seed"]} · Projected months: {s["months_projected"]} · '
        f'Deaths: {s["deaths"]} · Lapses: {s["lapses"]} · Expired: {s["expired"]} · '
        f'Active at end: {s["active_at_end"]}</p>'
        f'<p>Capital-buffer breach observed: <strong>{s["capital_breach_ever"]}</strong>. '
        'This is separate from an unpaid payment. Negative surplus means a loss relative '
        'to starting capital after deducting all recorded unpaid obligations.</p>'
        '<p><a href="result.json">Full assumptions and results (JSON)</a> · '
        '<a href="monthly.csv">Monthly ledger (CSV)</a></p>'
        '<p><a href="trace.html">Explain one month step by step</a></p>'
    )
    rows = []
    for r in result.monthly:
        values = [
            r["month"], r["issued"], r["active_open"], r["deaths"], r["lapses"],
            r["expired"], format_inr(r["premiums_paise"]),
            format_inr(r["claims_incurred_paise"]), format_inr(r["claims_paid_paise"]),
            format_inr(r["closing_cash_paise"]), format_inr(r["reserve_requirement_paise"]),
            format_inr(r["capital_margin_paise"]),
        ]
        flag = ' class="bad"' if r["capital_breach"] or r["payment_shortfall"] else ""
        rows.append("<tr" + flag + ">" + "".join(f"<td>{escape(str(x))}</td>" for x in values) + "</tr>")
    columns = ("Month", "Issued", "Active opening", "Deaths", "Lapses", "Expired",
               "Premiums", "Claims incurred", "Claims paid", "Closing cash",
               "Reserve", "Capital margin")
    table = (
        '<h2>Monthly ledger</h2><p>Month 0 is the first policy month. Money is displayed in INR; '
        'machine-readable amounts are integer paise. Orange rows mark a capital breach or payment shortfall.</p>'
        '<div class="scroll"><table><thead><tr>'
        + "".join(f"<th>{x}</th>" for x in columns)
        + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )
    notes = (
        "<h2>What this build assumes</h2><ul>"
        "<li>A Yule birth creates a candidate; active customers can die, lapse or expire.</li>"
        "<li>Active customers pay at the start of a month. Lapse occurs after covered deaths.</li>"
        "<li>Expenses are settled before cash interest; claims are settled at month-end.</li>"
        "<li>Unpaid expenses and claims remain liabilities; negative cash is never used to fake a payment.</li>"
        "<li>New issues stop after the first unpaid obligation; existing policies are projected to run-off.</li>"
        "<li>Reserve floors and the capital buffer are project rules, not statutory measures.</li>"
        "<li>Experience shocks affect realized outcomes. Reserves retain the original pricing basis; they are not a stress-revalued solvency measure.</li>"
        "<li>Grace periods, real mortality calibration, AI Audit and CAPSAFE are future work.</li></ul>"
        "<h2>Pricing calculation</h2><pre>"
        + escape(json.dumps(result.pricing, indent=2)) + "</pre>"
    )
    path = output / "report.html"
    path.write_text(_page("Life Insurance Lab — inspection report", heading + table + notes), encoding="utf-8")
    month = next((row["month"] for row in result.monthly if row["deaths"]), 0)
    write_trace(explain_month(payload, month), output)
    return path


def write_comparison(data: dict, output: str | Path) -> Path:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    _dump(output / "comparison.json", data)
    rows = []
    for r in data["scenarios"]:
        interval = r["payment_shortfall_wilson_95"]
        values = [
            r["scenario"], r["paths"], f'{r["payment_shortfall_fraction"]:.1%}',
            f"{interval[0]:.1%} to {interval[1]:.1%}",
            f'{r["capital_breach_fraction"]:.1%}', format_inr(r["mean_surplus_paise"]),
            format_inr(r["mean_premiums_paise"]),
        ]
        rows.append("<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in values) + "</tr>")
    columns = ("Scenario", "Paths", "Shortfall fraction", "95% Wilson interval",
               "Capital breach fraction", "Mean surplus", "Mean premiums")
    body = (
        '<div class="eyebrow">COURSE PROJECT / SCENARIO COMPARISON</div>'
        '<h1>What changes when customers lapse?</h1>'
        f'<p>Fixed death benefit: {format_inr(data["fixed_sum_assured_paise"])}. '
        'The premium, acquisition law, costs and starting capital also remain fixed.</p>'
        '<p class="note">Small synthetic experiment. Zero observed failures does not establish zero risk. '
        'See JSON for the exact one-sided upper bound when no shortfall occurs.</p>'
        '<div class="scroll"><table><thead><tr>'
        + "".join(f"<th>{c}</th>" for c in columns) + "</tr></thead><tbody>"
        + "".join(rows) + '</tbody></table></div><p><a href="comparison.json">Full comparison JSON</a></p>'
        '<p>Scenario reserve values retain the original pricing basis. A higher lapse rate removes '
        'both future premiums and future cover; its net effect depends on costs and timing. '
        'The configured case can duplicate another case if its probabilities match.</p>'
    )
    path = output / "comparison.html"
    path.write_text(_page("Life Insurance Lab — lapse comparison", body), encoding="utf-8")
    return path


def _table(columns, rows):
    return ('<div class="scroll"><table><thead><tr>'
            + ''.join(f'<th>{escape(str(x))}</th>' for x in columns)
            + '</tr></thead><tbody>'
            + ''.join('<tr>'+''.join(f'<td>{escape(str(x))}</td>' for x in row)+'</tr>' for row in rows)
            + '</tbody></table></div>')


def write_experiment(data: dict, output: str | Path) -> Path:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    _dump(output/'experiment.json', data)
    columns = ['scenario', 'starting_capital_paise', 'paths', 'payment_shortfall_fraction',
               'mean_surplus_paise', 'median_surplus_paise', 'surplus_p05_paise',
               'worst_max_unpaid_paise', 'worst_minimum_capital_margin_paise']
    with (output/'comparison.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(data['cells'])
    rows = []
    for cell in data['cells']:
        lo, hi = cell['payment_shortfall_wilson_95']
        rows.append([cell['scenario'], format_inr(cell['starting_capital_paise']), cell['paths'],
                     f"{cell['payment_shortfall_fraction']:.1%}", f'{lo:.2%}–{hi:.2%}',
                     format_inr(cell['mean_surplus_paise']), format_inr(cell['median_surplus_paise']),
                     format_inr(cell['surplus_p05_paise']), format_inr(cell['worst_max_unpaid_paise'])])
    body = ('<div class="eyebrow">FIXED CONTRACT / SCENARIOS / CAPITAL</div><h1>Capital and experience comparison</h1>'
            f"<p>Monthly premium: {format_inr(data['fixed_premium_paise'])}. "
            f"Fixed death benefit: {format_inr(data['fixed_sum_assured_paise'])}.</p>"
            '<p class="note">These are synthetic experiments. Confidence intervals describe sampling uncertainty under the model. '
            'The capital grid is not an optimization or regulatory adequacy certificate.</p>'
            + _table(['Scenario', 'Initial capital', 'Paths', 'Shortfall fraction', '95% Wilson interval',
                      'Mean surplus', 'Median surplus', '5th percentile surplus', 'Worst unpaid obligations'], rows)
            + '<p><a href="experiment.json">Full results and seeds</a> · <a href="comparison.csv">Summary CSV</a></p>'
            + '<h2>Interpretation</h2><ul>'+''.join(f'<li>{escape(note)}</li>' for note in data['notes'])+'</ul>')
    path = output/'experiment.html'
    path.write_text(_page('Insurance Lab — capital comparison', body), encoding='utf-8')
    return path


def write_benchmark(data: dict, output: str | Path) -> Path:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    _dump(output/'benchmark.json', data)
    yule_rows = [[r['month'], f"{r['expected']:.4f}", f"{r['sample_mean']:.4f}",
                  f"{r['error']:.4f}", f"{r['standard_error']:.4f}"] for r in data['yule']]
    cohort_rows = [[r['month'], f"{r['active']['expected']:.3f}", f"{r['active']['sample_mean']:.3f}",
                   format_inr(r['premiums_paise']['expected']), format_inr(r['premiums_paise']['sample_mean']),
                   format_inr(r['claims_incurred_paise']['expected']), format_inr(r['claims_incurred_paise']['sample_mean'])]
                  for r in data['fixed_cohort']]
    margin = data['cohort_margin_epv_paise']
    body = ('<div class="eyebrow">THEORY / SIMULATION</div><h1>Analytical benchmark</h1>'
            f"<p>{data['paths']} paths, starting seed {data['seed_start']}.</p>"
            '<p class="note">Compare the empirical mean with theory and sampling uncertainty. '
            'Random deviations do not automatically imply a coding error. The normal intervals are approximate and pointwise.</p>'
            '<h2>Yule candidate population</h2>'
            + _table(['Month', 'Theoretical mean', 'Sample mean', 'Error', 'Empirical standard error'], yule_rows)
            + '<h2>Fixed initial cohort; no subsequent admissions</h2>'
            + _table(['Month', 'Expected active', 'Mean active', 'Expected premiums', 'Mean premiums',
                      'Expected incurred claims', 'Mean incurred claims'], cohort_rows)
            + f"<p>Cohort margin EPV: expected {format_inr(margin['expected'])}; sample mean "
            f"{format_inr(margin['sample_mean'])}; standard error {format_inr(margin['standard_error'])}.</p>"
            + '<p><a href="benchmark.json">Full benchmark including intervals</a></p><ul>'
            + ''.join(f'<li>{escape(x)}</li>' for x in data['notes'])+'</ul>')
    path = output/'benchmark.html'
    path.write_text(_page('Insurance Lab — analytical checks', body), encoding='utf-8')
    return path


def write_trace(data: dict, output: str | Path) -> Path:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    _dump(output/'trace.json', data)
    rows = [[step['operation'], format_inr(step['result_paise'])] for step in data['steps']]
    body = (f"<h1>Explain month {data['month']}</h1><p>Scenario: {escape(data['scenario'])}.</p>"
            f"<p class=\"note\">All arithmetic checks pass: {data['all_checks_pass']}.</p>"
            + _table(['Calculation', 'Amount'], rows)
            + '<p>Money is displayed in INR; JSON operands are in paise.</p>'
            + '<p><a href="trace.json">Exact inputs and individual checks</a></p>'
            + '<h2>Recorded month</h2><pre>'+escape(json.dumps(data['row'], indent=2))+'</pre>')
    path = output/'trace.html'
    path.write_text(_page('Insurance Lab — monthly calculation trace', body), encoding='utf-8')
    return path
