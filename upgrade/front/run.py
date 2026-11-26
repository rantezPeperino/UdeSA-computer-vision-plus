"""Starts the monitor: python upgrade/front/run.py [--host 127.0.0.1] [--port 8000]

Then open http://127.0.0.1:8000. The script reads the same environment variables
as in the terminal (upgrade/MERCHANT_SETUP.md): GOOGLE_SERVICE_ACCOUNT_PATH,
MERCHANT_ID, MERCHANT_DATA_SOURCE_ID, MERCHANT_ENV and OPENAI_API_KEY or
ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

FRONT = Path(__file__).resolve().parent
sys.path.insert(0, str(FRONT))

import uvicorn  # noqa: E402

from api.server import app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
