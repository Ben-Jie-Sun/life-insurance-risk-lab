"""Offline calculations and the optional local persistence/API entry points."""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from .backend.service import ExecutionError, Service
from .backend.storage import Store
from .errors import ModelError
from .jsonio import load
from .money import format_inr
from .monte_carlo import write_monte_carlo
from .reporting import _dump, write_benchmark, write_experiment, write_result, write_trace
from .simulation import Result
from .traces import explain_month


def export_result(kind: str, result: dict, output: Path) -> Path:
    if kind == 'monte_carlo':
        return write_monte_carlo(result, output)
    if kind == 'simulation':
        return write_result(Result.from_dict(result), output)
    if kind == 'experiment':
        return write_experiment(result, output)
    if kind == 'benchmark':
        return write_benchmark(result, output)
    output.mkdir(parents=True, exist_ok=True)
    path = output/'quote.json'
    _dump(path, result)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='life_insurance_lab', description='Yule acquisition, insurance pricing and risk experiments.')
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('quote', 'run', 'compare', 'experiment', 'benchmark', 'monte-carlo'):
        sub = commands.add_parser(command)
        sub.add_argument('--config', type=Path, default=Path('examples/baseline.json'))
        sub.add_argument('--seed', type=int)
        sub.add_argument('--db', type=Path, help='Optional SQLite file: persist this run and its exact inputs.')
        sub.add_argument('--output', type=Path, default=Path('outputs')/command)
        if command in ('run', 'monte-carlo'):
            sub.add_argument('--scenario', type=Path)
        if command in ('compare', 'experiment', 'benchmark', 'monte-carlo'):
            sub.add_argument('--paths', type=int, default=200 if command in ('benchmark', 'monte-carlo') else 100)
        if command == 'experiment':
            sub.add_argument('--scenarios', type=Path, nargs='+')
            sub.add_argument('--capitals', nargs='+', default=['1000000', '2500000', '5000000', '7500000'], help='Starting capital values in INR.')
    server = commands.add_parser('serve', help='Start the loopback-only HTTP JSON API.')
    server.add_argument('--db', type=Path, default=Path('data/lab.sqlite3'))
    server.add_argument('--host', default='127.0.0.1', choices=['127.0.0.1', 'localhost'])
    server.add_argument('--port', type=int, default=8000)
    trace = commands.add_parser('trace')
    trace.add_argument('--input', type=Path, required=True, help='A generated simulation result.json.')
    trace.add_argument('--month', type=int, default=0)
    trace.add_argument('--output', type=Path, default=Path('outputs/trace'))
    history = commands.add_parser('history')
    history.add_argument('--db', type=Path, default=Path('data/lab.sqlite3'))
    export = commands.add_parser('export')
    export.add_argument('--db', type=Path, default=Path('data/lab.sqlite3'))
    export.add_argument('--run-id', required=True)
    export.add_argument('--output', type=Path, default=Path('outputs/export'))
    args = parser.parse_args(argv)
    try:
        if args.command == 'serve':
            from .backend.server import serve
            serve(args.db, args.host, args.port)
            return 0
        if args.command == 'trace':
            result = json.loads(args.input.read_text(encoding='utf-8'))
            if not isinstance(result, dict) or not {'monthly', 'contract', 'scenario', 'config'} <= result.keys():
                raise ModelError('Input must be a generated v0.2 simulation result.json.')
            path = write_trace(explain_month(result, args.month), args.output)
            print(f'Trace: {path.resolve()}')
            return 0
        if args.command in ('history', 'export'):
            store = Store(args.db)
            if args.command == 'history':
                print(json.dumps(store.list_runs(), indent=2))
                return 0
            saved = store.get_run(args.run_id)
            if saved['status'] != 'completed':
                raise ModelError(f"Run status is {saved['status']}: {saved['error']}")
            path = export_result(saved['kind'], saved['result'], args.output)
            print(f'Export: {path.resolve()}')
            return 0
        body = {'config': load(args.config), 'persist': args.db is not None}
        if args.seed is not None:
            body['seed'] = args.seed
        kind = {'run': 'simulation', 'compare': 'experiment', 'monte-carlo': 'monte_carlo'}.get(args.command, args.command)
        if args.command in ('run', 'monte-carlo') and args.scenario:
            body['scenario'] = load(args.scenario)
        if args.command in ('compare', 'experiment', 'benchmark', 'monte-carlo'):
            body['paths'] = args.paths
        if args.command == 'experiment':
            body['scenarios'] = [load(p) for p in args.scenarios] if args.scenarios else [{'name': 'baseline'}]
            body['capitals'] = args.capitals
        if args.command == 'compare':
            body['scenarios'] = [{'name': 'no_lapse', 'lapse_monthly': 0},
                                 {'name': 'configured_lapse'},
                                 {'name': 'synthetic_2_percent_lapse', 'lapse_monthly': .02}]
        outcome = Service(Store(args.db) if args.db else None).execute(kind, body)
        result = outcome['result']
        path = export_result(kind, result, args.output)
        print('SYNTHETIC TEACHING MODEL — virtual money')
        if kind in ('quote', 'simulation'):
            pricing = result['pricing']
            print(f"Monthly premium: {format_inr(pricing['selected_premium_paise'])}")
            print(f"Death benefit:   {format_inr(pricing['selected_benefit_paise'])}")
            print(f"Pricing-basis expected margin: {format_inr(pricing['expected_margin_paise'])}")
            if not pricing['meets_target_margin']:
                print('The fixed contract does not meet the expected-margin target.')
        if kind == 'simulation':
            summary = result['summary']
            print(f"Scenario: {summary['scenario_name']} | Issued {summary['policies_issued']} | "
                  f"Deaths {summary['deaths']} | Lapses {summary['lapses']} | Expired {summary['expired']}")
            print(f"Economic surplus: {format_inr(summary['economic_surplus_paise'])}")
            print(f"Payment shortfall ever: {summary['payment_shortfall_ever']}")
        if kind == 'monte_carlo':
            risk = result['summary']['payment_shortfall']
            print(f"Monte Carlo: {result['paths']} paths, shortfall {risk['estimate']:.2%}, 95% Wilson {risk['wilson_95']}")
        if kind == 'experiment':
            print(f"Completed {len(result['cells'])} scenario/capital cells, {result['paths_per_scenario']} paths each.")
        if kind == 'benchmark':
            print(f"Completed {result['paths']} paths for each analytical benchmark.")
        if outcome['id']:
            print(f"Saved run: {outcome['id']}")
        print(f'Result: {path.resolve()}')
        return 0
    except (ModelError, OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f'Could not complete: {exc}', file=sys.stderr)
        if isinstance(exc, ExecutionError) and exc.run_id:
            print(f'Recorded {exc.status} run: {exc.run_id}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
