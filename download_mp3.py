#!/usr/bin/env python3
"""
download_mp3.py

Reads a list of YouTube URLs from a text file (one per line; blank lines and
lines starting with '#' are ignored) and downloads each as a 192kbps mp3 into
an output folder, named after the video title. A URL that fails to download
is logged and skipped rather than stopping the whole batch.

Usage:
    python download_mp3.py [links_file] [-o OUTPUT_DIR]
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

# Characters illegal in Windows filenames (also unwise on macOS/Linux):
# < > : " / \ | ? * and ASCII control characters.
ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class _SilentLogger:
    """
    Swallows yt-dlp's own console output entirely. We catch and print our
    own single, clean error line per URL (see main()); without this, a
    failed download logs twice — once from yt-dlp's internal reporting,
    once from our own handler.
    """

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


def check_dependencies() -> None:
    """Fail fast with a clear message if a required tool is missing."""
    missing = []
    if yt_dlp is None:
        missing.append("yt-dlp (run: pip install -r requirements.txt)")
    if shutil.which("ffmpeg") is None:
        missing.append(
            "ffmpeg (required by yt-dlp to extract audio as mp3 — "
            "install it and make sure it's on PATH; see README.md)"
        )
    if missing:
        print("Error: missing required dependencies:", file=sys.stderr)
        for item in missing:
            print(f"  - {item}", file=sys.stderr)
        sys.exit(1)


def sanitize_filename(title: str) -> str:
    """Strip characters that are illegal in filenames and tidy whitespace."""
    name = ILLEGAL_FILENAME_CHARS.sub("", title)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name or "untitled"


def build_filename(index: int, total: int, title: str, numbered: bool) -> str:
    """
    Build the (extension-less) output filename for one download.

    When numbered, prefixes the sanitized title with the URL's 1-based
    position in links.txt (zero-padded to the width needed for the full
    list, e.g. "01-", "002-"), so files sort in download order without
    manual sorting. rename_files.py preserves this prefix as-is, since
    digits and hyphens are already valid slug characters.
    """
    sanitized = sanitize_filename(title)
    if not numbered:
        return sanitized
    width = max(2, len(str(total)))
    return f"{index:0{width}d}-{sanitized}"


def read_links(path: Path) -> list:
    """Read URLs from a links file, skipping blank lines and '#' comments."""
    links = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        links.append(line)
    return links


def fetch_title(url: str) -> str:
    """Look up a video's title without downloading it."""
    probe_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,  # a URL like watch?v=X&list=RD...&start_radio=1 is a
                             # single video with a radio-mix queue attached; without
                             # this, yt-dlp treats it as a playlist request and pulls
                             # every entry in that auto-generated queue.
        "logger": _SilentLogger(),
    }
    with yt_dlp.YoutubeDL(probe_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info.get("title", "untitled")


def download_as_mp3(url: str, output_dir: Path, filename: str) -> None:
    """Download a single URL as a 192kbps mp3 saved as `filename` (no extension)."""
    outtmpl = str(output_dir / f"{filename}.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,  # see fetch_title(): download only the linked video,
                             # not an attached radio-mix queue
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _SilentLogger(),
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download a list of YouTube URLs as 192kbps mp3s."
    )
    parser.add_argument(
        "links_file",
        nargs="?",
        default="links.txt",
        help="Text file of URLs, one per line (default: links.txt)",
    )
    parser.add_argument(
        "-o", "--output",
        default="output",
        help="Folder to save downloaded mp3s into (default: output)",
    )
    parser.add_argument(
        "--number",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Prefix filenames with their download order, e.g. '01-title.mp3' "
             "(default: enabled). Pass --no-number to save plain titles instead.",
    )
    args = parser.parse_args()

    check_dependencies()

    links_path = Path(args.links_file)
    if not links_path.is_file():
        print(f"Error: links file not found: {links_path}", file=sys.stderr)
        sys.exit(1)

    urls = read_links(links_path)
    if not urls:
        print(f"No URLs found in {links_path}")
        return

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    total = len(urls)
    succeeded = 0
    failed = 0

    for index, url in enumerate(urls, start=1):
        # Look up the title first so the progress line and the eventual
        # filename are consistent, and so a bad URL fails here (cheaply)
        # rather than partway through a download.
        try:
            title = fetch_title(url)
        except Exception as exc:
            print(f"Error {index}/{total}: could not read info for {url}: {exc}", file=sys.stderr)
            failed += 1
            continue

        print(f"Downloading {index}/{total}: {title}")
        try:
            filename = build_filename(index, total, title, args.number)
            download_as_mp3(url, output_dir, filename)
            succeeded += 1
        except Exception as exc:
            print(f"Error {index}/{total}: failed to download '{title}': {exc}", file=sys.stderr)
            failed += 1

    print(f"\nDone: {succeeded} succeeded, {failed} failed.")


if __name__ == "__main__":
    main()
