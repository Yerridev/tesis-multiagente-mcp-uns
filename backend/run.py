"""Arranque local del backend.

    python run.py                    # http://localhost:5051
    python run.py --puerto 8080

Equivale a ``dotnet run --urls http://localhost:5051`` del backend anterior.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# --- Windows: psycopg (async) necesita el SelectorEventLoop (no el Proactor
#     que es el default de asyncio en Windows).  Se fija antes de crear el loop.
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:                    # pragma: no cover - Python >= 3.14
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Backend MCP Industrial (Python)")
    parser.add_argument("--host", default=os.environ.get("BACKEND_HOST", "0.0.0.0"))
    parser.add_argument("--puerto", type=int, default=int(os.environ.get("BACKEND_PORT", "5051")))
    parser.add_argument("--recarga", action="store_true", help="recarga en caliente (desarrollo)")
    args = parser.parse_args()

    import uvicorn

    if args.recarga:
        uvicorn.run("app.main:app", host=args.host, port=args.puerto, reload=True)
    else:
        from app.main import app

        uvicorn.run(app, host=args.host, port=args.puerto)


if __name__ == "__main__":
    main()
