#!/usr/bin/env python3
"""
normalize_audio.py

For every mp3 in a folder: trims leading/trailing silence (below -50dB, with
a small buffer left so cuts don't feel abrupt), then normalizes loudness to
a uniform target using ffmpeg's loudnorm filter (EBU R128, two-pass for
accuracy). Originals are left untouched; results go into a normalized/
subfolder.

Default target: -16 LUFS integrated loudness, -1.5 dBTP true peak, 11 LU
loudness range — a safe, comfortable level for headphones/earbuds.

Usage:
    python normalize_audio.py [folder] [--target LUFS]
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_TARGET_I = -16.0    # LUFS integrated loudness
DEFAULT_TARGET_TP = -1.5    # dBTP true peak
DEFAULT_TARGET_LRA = 11.0   # LU loudness range

SILENCE_NOISE_DB = -50      # quieter than this counts as silence
SILENCE_MIN_DURATION = 0.1  # seconds; minimum run length to register as silence
TRIM_BUFFER = 0.3           # seconds of silence left in place at each cut

# Only silence touching t=0 or the very end of the file is ever trimmed;
# a gap this large from the boundary means it's silence in the middle of
# the track, which is left alone.
BOUNDARY_EPSILON = 0.05

SILENCE_START_RE = re.compile(r"silence_start:\s*(-?[\d.]+)")
SILENCE_END_RE = re.compile(r"silence_end:\s*(-?[\d.]+)")


def check_dependencies() -> None:
    """Fail fast with a clear message if ffmpeg/ffprobe aren't available."""
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        print(f"Error: required tool(s) not found on PATH: {', '.join(missing)}", file=sys.stderr)
        print("Install ffmpeg (it provides both ffmpeg and ffprobe):", file=sys.stderr)
        print("  Windows: choco install ffmpeg   (or download from https://ffmpeg.org/download.html)", file=sys.stderr)
        print("  macOS:   brew install ffmpeg", file=sys.stderr)
        print("  Linux:   sudo apt install ffmpeg", file=sys.stderr)
        sys.exit(1)


def run(cmd: list) -> subprocess.CompletedProcess:
    """Run an ffmpeg/ffprobe command, decoding output leniently (titles can be non-ASCII)."""
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def get_duration(path: Path) -> float:
    result = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    return float(result.stdout.strip())


def detect_trim_bounds(path: Path, duration: float) -> tuple:
    """
    Return (start_cut, end_cut): the timestamps, in seconds, where the
    trimmed output should begin and end. Only silence at the very start or
    very end of the file is considered.
    """
    cmd = [
        "ffmpeg", "-i", str(path), "-af",
        f"silencedetect=noise={SILENCE_NOISE_DB}dB:d={SILENCE_MIN_DURATION}",
        "-f", "null", "-",
    ]
    stderr = run(cmd).stderr

    starts = [float(m) for m in SILENCE_START_RE.findall(stderr)]
    ends = [float(m) for m in SILENCE_END_RE.findall(stderr)]
    # ffmpeg doesn't print silence_end when the silence runs straight to EOF.
    if len(ends) < len(starts):
        ends.append(duration)

    start_cut = 0.0
    end_cut = duration

    if starts and starts[0] <= BOUNDARY_EPSILON:
        start_cut = max(0.0, ends[0] - TRIM_BUFFER)

    if ends and ends[-1] >= duration - BOUNDARY_EPSILON:
        end_cut = min(duration, starts[-1] + TRIM_BUFFER)

    if end_cut <= start_cut:
        # The whole file is effectively silence (or the bounds overlap) —
        # don't trim rather than produce an empty/invalid clip.
        return 0.0, duration

    return start_cut, end_cut


def trim_silence(path: Path, start_cut: float, end_cut: float, tmp_path: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-i", str(path),
        "-ss", f"{start_cut:.3f}", "-to", f"{end_cut:.3f}",
        "-c:a", "libmp3lame", "-q:a", "0",
        str(tmp_path),
    ]
    result = run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg trim failed: {result.stderr.strip()[-500:]}")


def extract_loudnorm_json(stderr: str) -> dict:
    """loudnorm prints one JSON object at the end of stderr; pull it out."""
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise RuntimeError("Could not parse loudnorm measurements from ffmpeg output")
    return json.loads(stderr[start:end + 1])


def measure_loudness(path: Path, target_i: float, target_tp: float, target_lra: float) -> dict:
    """Pass 1: analyze only (output discarded) to get the file's current loudness stats."""
    cmd = [
        "ffmpeg", "-i", str(path), "-af",
        f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
        "-f", "null", "-",
    ]
    return extract_loudnorm_json(run(cmd).stderr)


def apply_loudnorm(path: Path, measured: dict, target_i: float, target_tp: float,
                    target_lra: float, output_path: Path) -> dict:
    """Pass 2: apply the correction computed from pass 1's measurements and write the file."""
    loudnorm_filter = (
        f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:"
        f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true:print_format=json"
    )
    cmd = [
        "ffmpeg", "-y", "-i", str(path), "-af", loudnorm_filter,
        "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "192k",
        str(output_path),
    ]
    result = run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg normalize failed: {result.stderr.strip()[-500:]}")
    return extract_loudnorm_json(result.stderr)


def process_file(path: Path, normalized_dir: Path, target_i: float, target_tp: float,
                  target_lra: float, tmp_dir: Path) -> None:
    print(f"\n{path.name}")

    duration = get_duration(path)
    start_cut, end_cut = detect_trim_bounds(path, duration)
    trimmed_start = start_cut
    trimmed_end = duration - end_cut
    print(f"  Trimmed {trimmed_start:.1f}s start, {trimmed_end:.1f}s end")

    tmp_path = tmp_dir / f"__trim_{path.stem}.mp3"
    trim_silence(path, start_cut, end_cut, tmp_path)

    try:
        measured = measure_loudness(tmp_path, target_i, target_tp, target_lra)
        print(f"  Before: {measured['input_i']} LUFS, {measured['input_tp']} dBTP, "
              f"{measured['input_lra']} LU range")

        output_path = normalized_dir / path.name
        result = apply_loudnorm(tmp_path, measured, target_i, target_tp, target_lra, output_path)
        print(f"  After:  {result['output_i']} LUFS, {result['output_tp']} dBTP, "
              f"{result['output_lra']} LU range")
        print(f"  Saved to {output_path}")
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trim silence and normalize loudness for a folder of mp3s."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default="output",
        help="Folder containing mp3 files (default: output)",
    )
    parser.add_argument(
        "--target",
        type=float,
        default=DEFAULT_TARGET_I,
        help=f"Target integrated loudness in LUFS (default: {DEFAULT_TARGET_I})",
    )
    args = parser.parse_args()

    check_dependencies()

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

    normalized_dir = folder / "normalized"
    normalized_dir.mkdir(exist_ok=True)

    errors = 0
    with tempfile.TemporaryDirectory(prefix="normalize_audio_") as tmp:
        tmp_dir = Path(tmp)
        for path in mp3_files:
            try:
                process_file(path, normalized_dir, args.target, DEFAULT_TARGET_TP, DEFAULT_TARGET_LRA, tmp_dir)
            except Exception as exc:
                print(f"  Error processing {path.name}: {exc}", file=sys.stderr)
                errors += 1

    print(f"\nDone: {len(mp3_files) - errors}/{len(mp3_files)} file(s) normalized.")


if __name__ == "__main__":
    main()
