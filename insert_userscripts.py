#!/usr/bin/env python3
"""Map each row of a users CSV to a generated userscript file.

Given a CSV whose header is ``email,password`` and a directory that holds the
generated userscript files ``log1.user.js`` .. ``logN.user.js``, this program
adds a ``script`` column to the CSV so that row 1 points to ``log1.user.js``,
row 2 to ``log2.user.js`` and so on.

Example (matching the paths from the original request)::

    python insert_userscripts.py \
        --csv "C:\\Users\\DELL\\ab2gents\\original_users.csv" \
        --scripts-dir "C:\\Users\\DELL\\ab2gents\\generated"

By default the result is written next to the input as
``<name>_with_scripts.csv`` so the original file is never overwritten. Pass
``--in-place`` to overwrite the input, or ``--output PATH`` to choose the
destination.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Insert generated userscript filenames into a users CSV.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--csv",
        default="original_users.csv",
        type=Path,
        help="Path to the input CSV (header: email,password).",
    )
    parser.add_argument(
        "--scripts-dir",
        default="generated",
        type=Path,
        help="Directory that contains the log<N>.user.js files.",
    )
    parser.add_argument(
        "--prefix",
        default="log",
        help="Filename prefix before the row number.",
    )
    parser.add_argument(
        "--suffix",
        default=".user.js",
        help="Filename suffix after the row number.",
    )
    parser.add_argument(
        "--column",
        default="script",
        help="Name of the new column added to the CSV.",
    )
    parser.add_argument(
        "--encoding",
        default=None,
        help="Force a specific input encoding (e.g. cp1252, latin-1). "
        "By default utf-8 is tried first, then cp1252.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Where to write the result. Defaults to <name>_with_scripts.csv.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite the input CSV instead of writing a new file.",
    )
    parser.add_argument(
        "--full-path",
        action="store_true",
        help="Store the full path to each script instead of just the filename.",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Continue even if some script files are absent (they are still mapped).",
    )
    return parser


def read_rows(
    csv_path: Path, encoding: str | None = None
) -> tuple[list[str], list[dict[str, str]]]:
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    # utf-8-sig transparently strips a BOM when present. If the file is not
    # UTF-8 (Excel on Windows often saves cp1252), fall back so a stray byte
    # like 0xa0 (non-breaking space) does not abort the run.
    encodings = [encoding] if encoding else ["utf-8-sig", "cp1252"]
    last_error: UnicodeDecodeError | None = None
    for enc in encodings:
        try:
            with csv_path.open("r", newline="", encoding=enc) as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None:
                    raise ValueError(f"CSV has no header row: {csv_path}")
                fieldnames = list(reader.fieldnames)
                rows = [dict(row) for row in reader]
            return fieldnames, rows
        except UnicodeDecodeError as exc:
            last_error = exc

    raise ValueError(
        f"could not decode {csv_path} as {' or '.join(encodings)}. "
        f"Re-run with --encoding to specify the correct one. ({last_error})"
    )


def resolve_output(args: argparse.Namespace) -> Path:
    if args.in_place:
        return args.csv
    if args.output is not None:
        return args.output
    return args.csv.with_name(f"{args.csv.stem}_with_scripts{args.csv.suffix}")


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

    if args.column not in fieldnames:
        fieldnames.append(args.column)

    missing: list[str] = []
    for index, row in enumerate(rows, start=1):
        filename = f"{args.prefix}{index}{args.suffix}"
        script_path = args.scripts_dir / filename
        if not script_path.is_file():
            missing.append(filename)
        row[args.column] = str(script_path) if args.full_path else filename

    if missing and not args.allow_missing:
        preview = ", ".join(missing[:10])
        more = "" if len(missing) <= 10 else f" (+{len(missing) - 10} more)"
        print(
            f"error: {len(missing)} script file(s) not found in {args.scripts_dir}: "
            f"{preview}{more}\n"
            "Pass --allow-missing to map them anyway.",
            file=sys.stderr,
        )
        return 1

    output_path = resolve_output(args)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Mapped {len(rows)} row(s) to '{args.column}' -> {output_path}")
    if missing:
        print(f"warning: {len(missing)} script file(s) were missing but mapped anyway.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
