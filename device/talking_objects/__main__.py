"""`python -m talking_objects [--config config.env]`"""

from __future__ import annotations

import argparse
import asyncio
import logging

from . import config
from .app import App
from .status import serve


async def _main(env_file: str) -> None:
    app = App(config.load(env_file))
    await serve(app, app.settings.status_port)
    await app.run()


def main() -> None:
    parser = argparse.ArgumentParser(prog="talking_objects")
    parser.add_argument("--config", default="config.env", help="path to config.env")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    try:
        asyncio.run(_main(args.config))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
