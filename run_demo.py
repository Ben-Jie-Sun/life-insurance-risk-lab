"""Generate the complete offline professor demonstration with one command."""
import argparse
from html import escape
from pathlib import Path

from life_insurance_lab.backend.service import Service
from life_insurance_lab.backend.storage import Store
from life_insurance_lab.cli import export_result
from life_insurance_lab.jsonio import load
from life_insurance_lab.reporting import _page

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paths', type=int, default=100, help='Paths per capital/scenario cell.')
    parser.add_argument('--benchmark-paths', type=int, default=200)
    parser.add_argument('--output', type=Path, default=ROOT/'outputs/demo')
    parser.add_argument('--db', type=Path, help='Optionally save every computation in SQLite.')
    args = parser.parse_args()
    service = Service(Store(args.db) if args.db else None)
    base = load(ROOT/'examples/baseline.json')
    jobs = [
        ('quote', 'premium_quote', 'Premium to benefit', {'config': base}),
        ('quote', 'cover_quote', 'Benefit to premium', {'config': load(ROOT/'examples/cover_based.json')}),
    ]
    for name in ('baseline', 'mortality_shock', 'lapse_shock', 'poor_returns', 'combined_stress', 'volatile_returns'):
        jobs.append(('simulation', name, name.replace('_', ' ').title(),
                     {'config': base, 'scenario': load(ROOT/f'examples/scenarios/{name}.json')}))
    jobs += [
        ('simulation', 'increasing_mortality', 'Increasing policy-duration mortality', {'config': load(ROOT/'examples/increasing_mortality.json')}),
        ('simulation', 'shortfall', 'Guaranteed shortfall boundary', {'config': load(ROOT/'examples/certain_claim_shortfall.json')}),
        ('experiment', 'capital_comparison', 'Capital and scenario experiment', {'config': base, 'paths': args.paths,
             'capitals': [1000000, 2500000, 5000000, 7500000],
             'scenarios': [load(ROOT/f'examples/scenarios/{name}.json') for name in ('baseline', 'mortality_shock', 'combined_stress')]}),
        ('benchmark', 'benchmark', 'Theory versus simulation', {'config': base, 'paths': args.benchmark_paths}),
    ]
    links = []
    for kind, folder, title, body in jobs:
        print(f'Calculating: {title}', flush=True)
        body['persist'] = args.db is not None
        outcome = service.execute(kind, body)
        output = export_result(kind, outcome['result'], args.output/folder)
        relative = output.relative_to(args.output).as_posix()
        identifier = '' if outcome['id'] is None else ' — '+outcome['id']
        links.append(f'<li><a href="{escape(relative)}">{escape(title)}</a>{escape(identifier)}</li>')
    index = args.output/'index.html'
    index.write_text(_page('Insurance Lab — professor demonstration',
        '<div class="eyebrow">YULE–FURRY / ACTUARIAL PRICING / LOCAL BACKEND</div>'
        '<h1>Professor demonstration</h1><p>Start with the quote, inspect a monthly trace, '
        'apply an experience shock, then compare capital levels and analytical expectations.</p>'
        '<p class="note">All examples use synthetic assumptions and virtual money. Fixed contract promises and '
        'the original reserve valuation basis remain unchanged by experience shocks.</p><ol>'
        + ''.join(links)+'</ol><p>Each simulation includes its CSV ledger, exact JSON results, and an explained month.</p>'),
        encoding='utf-8')
    print(f'Open this file in your browser: {index.resolve()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
