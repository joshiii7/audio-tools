#!/usr/bin/env python3
"""
rename_files.py

Renames mp3 files in a folder from "Title Case With Spaces" to
"lowercase-with-hyphens", e.g. "Joshi Angelo.mp3" -> "joshi-angelo.mp3".
Characters that aren't letters, numbers, or hyphens are stripped. A rename
that would overwrite an existing file is skipped, not forced.

Usage:
    python rename_files.py [folder] [--dry-run]
"""

import argparse
import re
import sys
from pathlib import Path

# Anything left after lowercasing and turning whitespace into hyphens that
# isn't a letter, digit, or hyphen gets dropped.
NON_SLUG_CHARS = re.compile(r"[^a-z0-9-]")
WHITESPACE = re.compile(r"\s+")
REPEATED_HYPHENS = re.compile(r"-{2,}")


def slugify(stem: str) -> str:
    """Convert a filename stem to lowercase-with-hyphens form."""
    slug = stem.lower()
    slug = WHITESPACE.sub("-", slug)
    slug = NON_SLUG_CHARS.sub("", slug)
    slug = REPEATED_HYPHENS.sub("-", slug).strip("-")
    return slug or "untitled"


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Rename mp3 files to "lowercase-with-hyphens" form.'
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default="output",
        help="Folder containing mp3 files (default: output)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be renamed without actually renaming anything",
    )
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"Error: folder not found: {folder}", file=sys.stderr)
        sys.exit(1)

    mp3_files = sorted(
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".mp3"
    )
    if not mp3_files:
        print(f"No mp3 files found in {folder}")
        return

    renamed = 0
    skipped = 0
    unchanged = 0

    for path in mp3_files:
        new_name = f"{slugify(path.stem)}{path.suffix.lower()}"
        target = path.with_name(new_name)

        if target == path:
            unchanged += 1
            continue

        if target.exists():
            print(f"Skipping (target already exists): {path.name} -> {new_name}")
            skipped += 1
            continue

        if args.dry_run:
            print(f"[dry run] Would rename: {path.name} -> {new_name}")
        else:
            path.rename(target)
            print(f"Renamed: {path.name} -> {new_name}")
        renamed += 1

    verb = "would rename" if args.dry_run else "renamed"
    print(
        f"\nDone: {renamed} file(s) {verb}, {skipped} skipped (name conflict), "
        f"{unchanged} already correctly named."
    )


if __name__ == "__main__":
    main()
