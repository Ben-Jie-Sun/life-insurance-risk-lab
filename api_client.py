"""A small local API client so JSON files work without shell-specific quoting."""
import argparse
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from life_insurance_lab.jsonio import dumps, load


class APIError(Exception):
    pass


def request(method, path, payload=None, url='http://127.0.0.1:8000'):
    address = urlsplit(url)
    if address.scheme != 'http' or address.hostname not in ('127.0.0.1', 'localhost') or address.username:
        raise APIError('Use an http://127.0.0.1:PORT or http://localhost:PORT URL.')
    if not path.startswith('/'):
        raise APIError('The API path must start with /.')
    data = None if payload is None else dumps(payload).encode('utf-8')
    headers = {} if data is None else {'Content-Type': 'application/json'}
    try:
        with urlopen(Request(url.rstrip('/')+path, data=data, headers=headers, method=method), timeout=120) as response:
            content = response.read()
            return json.loads(content) if 'application/json' in response.headers.get('Content-Type', '') else content
    except HTTPError as exc:
        raise APIError(f'HTTP {exc.code}: {exc.read().decode()}') from exc
    except (URLError, TimeoutError) as exc:
        raise APIError('Cannot reach the local API or the request timed out. Start run_server.py; check history if a calculation was already running.') from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('method', choices=['GET', 'POST', 'PUT', 'DELETE'])
    parser.add_argument('path')
    parser.add_argument('--file', type=Path, help='JSON request file for POST, PUT or DELETE.')
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--output', type=Path, help='Optional response file; binary exports are written unchanged.')
    args = parser.parse_args()
    try:
        payload = load(args.file) if args.file else ({} if args.method in ('POST', 'PUT', 'DELETE') else None)
        result = request(args.method, args.path, payload, args.url)
        content = result if isinstance(result, bytes) else (json.dumps(result, indent=2)+'\n').encode()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(content)
            print(f'Saved {args.output.resolve()}')
        else:
            print(content.decode('utf-8'))
        return 0
    except (APIError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
