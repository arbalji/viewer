#!/usr/bin/env python3
"""Inject email/password from a users CSV into generated userscript files.

Row 1 of the CSV is written into ``log1.user.js``, row 2 into ``log2.user.js``
and so on. The CSV header must contain ``email`` and ``password`` columns.

Because userscripts store credentials in different ways, two modes are
supported:

* ``placeholder`` (default) - replace literal tokens such as ``{{EMAIL}}`` and
  ``{{PASSWORD}}`` wherever they appear in the file.
* ``assign`` - update existing JavaScript assignments, e.g. turn
  ``const email = "";`` into ``const email = "user@example.com";`` (also handles
  ``let``/``var`` and ``email: "..."`` object properties).

Example::

    python inject_credentials.py \
        --csv "C:\\Users\\DELL\\ab2gents\\original_users.csv" \
        --scripts-dir "C:\\Users\\DELL\\ab2gents\\generated" \
        --mode placeholder

Files are edited in place. A ``<name>.bak`` backup is written next to each
file first (disable with ``--no-backup``); use ``--dry-run`` to preview without
touching anything.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

READ_ENCODINGS = ["utf-8-sig", "cp1252"]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inject CSV email/password values into log<N>.user.js files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--csv", default="original_users.csv", type=Path,
                        help="Input CSV with email and password columns.")
    parser.add_argument("--scripts-dir", default="generated", type=Path,
                        help="Directory that contains the log<N>.user.js files.")
    parser.add_argument("--prefix", default="log", help="Filename prefix before the row number.")
    parser.add_argument("--suffix", default=".user.js", help="Filename suffix after the row number.")
    parser.add_argument("--mode", choices=["placeholder", "assign"], default="placeholder",
                        help="How to inject credentials into each file.")
    parser.add_argument("--email-column", default="email", help="CSV column holding the email.")
    parser.add_argument("--password-column", default="password", help="CSV column holding the password.")
    parser.add_argument("--email-token", default="{{EMAIL}}",
                        help="[placeholder mode] token replaced by the email.")
    parser.add_argument("--password-token", default="{{PASSWORD}}",
                        help="[placeholder mode] token replaced by the password.")
    parser.add_argument("--email-var", default="email",
                        help="[assign mode] JS variable/property name for the email.")
    parser.add_argument("--password-var", default="password",
                        help="[assign mode] JS variable/property name for the password.")
    parser.add_argument("--encoding", default=None,
                        help="Force input encoding for the CSV and scripts (default: utf-8 then cp1252).")
    parser.add_argument("--allow-missing", action="store_true",
                        help="Skip missing log<N>.user.js files instead of erroring.")
    parser.add_argument("--no-backup", action="store_true",
                        help="Do not write a .bak copy before editing each file.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change without writing any files.")
    return parser


def read_text(path: Path, encoding: str | None) -> str:
    encodings = [encoding] if encoding else READ_ENCODINGS
    last_error: UnicodeDecodeError | None = None
    for enc in encodings:
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"could not decode {path} as {' or '.join(encodings)} ({last_error})")


def read_rows(csv_path: Path, encoding: str | None) -> tuple[list[str], list[dict[str, str]]]:
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    text = read_text(csv_path, encoding)
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        raise ValueError(f"CSV has no header row: {csv_path}")
    return list(reader.fieldnames), [dict(row) for row in reader]


def js_escape(value: str) -> str:
    """Escape a value so it is safe inside a single- or double-quoted JS string."""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("'", "\\'")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def inject_placeholder(content: str, token: str, value: str) -> tuple[str, int]:
    if not token:
        return content, 0
    count = content.count(token)
    if count:
        content = content.replace(token, js_escape(value))
    return content, count


def inject_assignment(content: str, var: str, value: str) -> tuple[str, int]:
    escaped = js_escape(value)
    # Matches: const/let/var NAME = "..."  |  NAME = "..."  |  NAME: "..."
    pattern = re.compile(
        r"((?:\b(?:const|let|var)\s+)?\b" + re.escape(var) + r"\b\s*[:=]\s*)"
        r"(['\"])(?:\\.|(?!\2).)*?\2",
        re.IGNORECASE,
    )

    def repl(match: re.Match[str]) -> str:
        quote = match.group(2)
        return f"{match.group(1)}{quote}{escaped}{quote}"

    return pattern.subn(repl, content)


def target_files(rows: list[dict[str, str]], args: argparse.Namespace) -> list[tuple[int, Path]]:
    return [
        (i, args.scripts_dir / f"{args.prefix}{i}{args.suffix}")
        for i in range(1, len(rows) + 1)
    ]


def count_unmatched_scripts(args: argparse.Namespace, row_count: int) -> int:
    """Count log<N> files whose index is greater than the number of CSV rows."""
    if not args.scripts_dir.is_dir():
        return 0
    pattern = re.compile(
        r"^" + re.escape(args.prefix) + r"(\d+)" + re.escape(args.suffix) + r"$"
    )
    unmatched = 0
    for entry in args.scripts_dir.iterdir():
        match = pattern.match(entry.name)
        if match and int(match.group(1)) > row_count:
            unmatched += 1
    return unmatched


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    try:
        fieldnames, rows = read_rows(args.csv, args.encoding)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not rows:
        print("error: the CSV has a header but no data rows.", file=sys.stderr)
        return 1

    for column in (args.email_column, args.password_column):
        if column not in fieldnames:
            print(f"error: column '{column}' not found in CSV header {fieldnames}.", file=sys.stderr)
            return 1

    targets = target_files(rows, args)
    missing = [path.name for _, path in targets if not path.is_file()]
    if missing and not args.allow_missing:
        preview = ", ".join(missing[:10])
        more = "" if len(missing) <= 10 else f" (+{len(missing) - 10} more)"
        print(f"error: {len(missing)} script file(s) not found in {args.scripts_dir}: "
              f"{preview}{more}\nPass --allow-missing to skip them.", file=sys.stderr)
        return 1

    edited = 0
    skipped = 0
    warnings: list[str] = []

    for index, path in targets:
        if not path.is_file():
            skipped += 1
            continue

        row = rows[index - 1]
        email = row.get(args.email_column, "") or ""
        password = row.get(args.password_column, "") or ""

        try:
            content = read_text(path, args.encoding)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        if args.mode == "placeholder":
            content, n_email = inject_placeholder(content, args.email_token, email)
            content, n_pass = inject_placeholder(content, args.password_token, password)
        else:
            content, n_email = inject_assignment(content, args.email_var, email)
            content, n_pass = inject_assignment(content, args.password_var, password)

        if n_email == 0:
            warnings.append(f"{path.name}: no email target matched")
        if n_pass == 0:
            warnings.append(f"{path.name}: no password target matched")

        if n_email == 0 and n_pass == 0:
            skipped += 1
            continue

        if args.dry_run:
            print(f"[dry-run] {path.name}: email x{n_email}, password x{n_pass}")
            edited += 1
            continue

        if not args.no_backup:
            path.with_suffix(path.suffix + ".bak").write_text(
                read_text(path, args.encoding), encoding="utf-8"
            )
        path.write_text(content, encoding="utf-8")
        edited += 1

    action = "Would edit" if args.dry_run else "Edited"
    print(f"{action} {edited} file(s); skipped {skipped}.")

    unmatched = count_unmatched_scripts(args, len(rows))
    if unmatched:
        print(
            f"warning: {unmatched} script file(s) have an index higher than the "
            f"{len(rows)} CSV row(s) and were left unchanged (no matching row)."
        )

    for warning in warnings:
        print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
