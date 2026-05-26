"""``worklogicly-agent`` console-script entry point.

A single subcommand today (``login``); the dispatcher is structured to
grow (``status``, ``logout``) without breaking the entry point.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="worklogicly-agent",
        description="WorkLogicly lead-scraper agent control surface.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    login_parser = subparsers.add_parser(
        "login",
        help="Authenticate against the CRM and write tokens to ~/.worklogicly/agent.env.",
    )
    login_parser.add_argument(
        "--email",
        help="CRM login email. If omitted, prompts interactively.",
    )

    args = parser.parse_args(argv)

    if args.command == "login":
        # Import lazily so ``--help`` doesn't pay for httpx at startup.
        from .login import run_login

        return run_login(email=args.email)

    parser.error(f"unknown command: {args.command}")
    return 2  # unreachable; argparse exits


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
