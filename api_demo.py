"""Exercise actual HTTP storage, pricing, simulation, export and revision behavior."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import uuid

from api_client import request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent/'outputs/api_demo')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    call = lambda method, path, body=None: request(method, path, body, args.url)
    examples = call('GET', '/api/examples')
    suffix = uuid.uuid4().hex[:8]
    config = call('POST', '/api/configs', {'name': 'Demo model '+suffix, 'kind': 'model',
                                        'document': examples['models']['baseline']})
    scenario = call('POST', '/api/configs', {'name': 'Demo mortality shock '+suffix, 'kind': 'scenario',
                                         'document': examples['scenarios']['mortality_shock']})
    quote = call('POST', '/api/quote', {'config_id': config['id']})
    run = call('POST', '/api/simulations', {'config_id': config['id'], 'scenario_id': scenario['id']})
    trace = call('GET', f"/api/runs/{run['id']}/trace?month=8")
    ledger = call('GET', f"/api/runs/{run['id']}/ledger.csv")
    revised = deepcopy(config['document'])
    revised['policy']['monthly_premium'] = '1200.00'
    updated = call('PUT', '/api/configs/'+config['id'], {'expected_revision': config['revision'], 'document': revised})
    saved = call('GET', '/api/runs/'+run['id'])
    if saved['result']['contract']['premium_paise'] != 100000 or not trace['all_checks_pass']:
        raise RuntimeError('Snapshot/trace validation failed.')
    for filename, value in [('quote.json', quote), ('run.json', saved), ('trace.json', trace), ('updated_config.json', updated)]:
        (args.output/filename).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    (args.output/'ledger.csv').write_bytes(ledger)
    print(f"Saved model: {config['id']} (now revision {updated['revision']}, premium INR 1,200)")
    print(f"Saved simulation: {run['id']} (original premium INR 1,000 preserved)")
    print(f"Monthly trace checks passed: {trace['all_checks_pass']}")
    print(f"Downloaded results: {args.output.resolve()}")
    print('Restart the server and retrieve the same run ID to inspect persistence.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
