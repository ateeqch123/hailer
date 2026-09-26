"""Command line: hailer auth add, hailer auth list, hailer check."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from hailer.auth import add_account, list_accounts
from hailer.config import load_config
from hailer.errors import HailerError
from hailer.gmail_api import GmailApiClient
from hailer.paths import state_db, token_dir
from hailer.poll import format_action, run_check
from hailer.store import DedupStore


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    _configure_logging()
    try:
        if args.command == "auth" and args.auth_command == "add":
            return _cmd_add(args.client_secret)
        if args.command == "auth" and args.auth_command == "list":
            return _cmd_list()
        if args.command == "check":
            return _cmd_check(args.dry_run, args.concurrency)
    except HailerError as exc:
        print(f"hailer: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"hailer: {exc}", file=sys.stderr)
        return 2
    parser.error(f"unknown command {args.command}")
    return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hailer",
        description=(
            "Watch OAuth-authorized Gmail accounts and email one address when "
            "a message looks like recruiter outreach or an automatic reply."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    auth = sub.add_parser("auth", help="Connect or list Gmail accounts")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    add = auth_sub.add_parser(
        "add",
        help="Run Google's consent screen for one account and save its token",
    )
    add.add_argument(
        "--client-secret",
        default="client_secret.json",
        help="Desktop OAuth client JSON (default: ./client_secret.json)",
    )
    auth_sub.add_parser("list", help="List connected account emails")

    check = sub.add_parser("check", help="Poll connected accounts and notify")
    check.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify and print actions without sending or recording dedup",
    )
    check.add_argument(
        "--concurrency",
        type=_positive_int,
        default=None,
        help="Accounts to poll at once (default: the concurrency field in config, or 10)",
    )
    return parser


def _cmd_add(client_secret: str) -> int:
    email = add_account(Path(client_secret), token_dir())
    print(f"Connected {email}.")
    print(
        "Repeat `hailer auth add` for each Gmail account (at most 100). "
        "Each account owner completes Google's consent screen."
    )
    return 0


def _cmd_list() -> int:
    accounts = list_accounts(token_dir())
    if not accounts:
        print("No connected accounts.", file=sys.stderr)
        return 0
    for account in accounts:
        print(account)
    return 0


def _cmd_check(dry_run: bool, concurrency: int | None) -> int:
    config = load_config()
    accounts = list_accounts(token_dir())
    if not accounts:
        print(
            "No connected accounts. Run `hailer auth add` for each Gmail account.",
            file=sys.stderr,
        )
        return 0
    workers = config.concurrency if concurrency is None else concurrency
    store = DedupStore(state_db())
    try:
        report = run_check(
            accounts,
            GmailApiClient(token_dir()),
            store,
            notify_to=config.notify_to,
            notify_from=config.notify_from,
            concurrency=workers,
            dry_run=dry_run,
        )
    finally:
        store.close()
    for action in report.actions:
        print(format_action(action))
    for error in report.errors:
        message_id = error.message_id or "-"
        print(
            f"account={error.account} message_id={message_id} error={error.error}",
            file=sys.stderr,
        )
    return 1 if report.errors else 0


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    for name in ("googleapiclient", "google.auth", "urllib3", "httplib2"):
        logging.getLogger(name).setLevel(logging.WARNING)

