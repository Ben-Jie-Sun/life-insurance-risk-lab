"""Run the local backend; data is stored beside this script by default."""
import argparse
from pathlib import Path
from life_insurance_lab.backend.server import serve

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, default=Path(__file__).resolve().parent/'data/lab.sqlite3')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    serve(args.db, port=args.port)
