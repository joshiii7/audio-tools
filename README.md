# audio-tools

Three standalone command-line scripts for downloading YouTube audio as mp3,
cleaning up filenames, and normalizing loudness.

| Script | Purpose |
|---|---|
| `download_mp3.py` | Download a list of YouTube URLs as 192kbps mp3s |
| `rename_files.py` | Rename mp3s to `lowercase-with-hyphens` form |
| `normalize_audio.py` | Trim silence and normalize loudness across a batch of mp3s |

They're independent — run whichever one you need, in whatever order fits
your workflow (typically download → rename → normalize).

## Prerequisites

- **Python 3.9+**
- **ffmpeg**, installed and available on your `PATH` (used directly by
  `normalize_audio.py`, and by `yt-dlp` under the hood in `download_mp3.py`
  to extract/convert audio to mp3):
  - Windows: `choco install ffmpeg`, or download a build from
    [ffmpeg.org](https://ffmpeg.org/download.html) and add its `bin/`
    folder to `PATH`.
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg` (or your distro's equivalent)

  Each script checks for `ffmpeg`/`yt-dlp` on startup and prints an install
  message instead of crashing if something's missing.

- **Python dependencies** — install with:

  ```bash
  pip install -r requirements.txt
  ```

## 1. `download_mp3.py`

Downloads every URL listed in a text file as a 192kbps mp3, named after the
video's title (sanitized — illegal filename characters stripped). By default,
each filename is also prefixed with its position in `links.txt` (e.g.
`01-some-title.mp3`, `02-another-title.mp3`), so the files stay in download
order without manual sorting — a failed URL still keeps its number, so a gap
in the sequence means a skipped download, not a renumbering.

1. List URLs in `links.txt`, one per line. Blank lines and lines starting
   with `#` are ignored:

   ```
   # my playlist
   https://www.youtube.com/watch?v=dQw4w9WgXcQ
   https://www.youtube.com/watch?v=xxxxxxxxxxx
   ```

2. Run it:

   ```bash
   python download_mp3.py
   ```

   Files are saved to `output/`. A URL that fails to download is logged to
   stderr and skipped — it won't stop the rest of the batch.

**Options:**

```bash
python download_mp3.py [links_file] [-o OUTPUT_DIR] [--no-number]
```

- `links_file` — defaults to `links.txt`
- `-o, --output` — defaults to `output`
- `--number` / `--no-number` — numbered filename prefix (default: `--number`,
  i.e. enabled). Pass `--no-number` to save plain sanitized titles instead,
  e.g. `some-title.mp3` instead of `01-some-title.mp3`.

## 2. `rename_files.py`

Renames mp3s in a folder from `Title Case With Spaces.mp3` to
`lowercase-with-hyphens.mp3`. Characters that aren't letters, numbers, or
hyphens are stripped. If a rename would overwrite an existing file, that one
file is skipped (logged, not forced) and everything else still runs.

```bash
python rename_files.py [folder] [--dry-run]
```

- `folder` — defaults to `output`
- `--dry-run` — print what would be renamed without changing anything

Example:

```bash
python rename_files.py --dry-run       # preview
python rename_files.py                 # actually rename
```

## 3. `normalize_audio.py`

For every mp3 in a folder: trims leading/trailing silence (below -50dB,
leaving a ~300ms buffer so cuts don't feel abrupt — silence in the middle of
a track is never touched), then normalizes loudness with ffmpeg's
`loudnorm` filter, run twice (once to measure, once to apply) for accuracy.

Default target: **-16 LUFS** integrated loudness, **-1.5 dBTP** true peak,
**11 LU** loudness range — a comfortable, consistent level for
headphones/earbuds without pushing into loud, risky-for-sustained-listening
territory.

Originals are never modified. Results are written to a `normalized/`
subfolder alongside the source files.

```bash
python normalize_audio.py [folder] [--target LUFS]
```

- `folder` — defaults to `output`
- `--target` — override the target integrated loudness in LUFS (default: `-16`)

For each file it prints how much silence was trimmed, plus before/after
loudness stats:

```
some-track.mp3
  Trimmed 1.2s start, 0.8s end
  Before: -22.4 LUFS, -8.1 dBTP, 14.3 LU range
  After:  -16.0 LUFS, -1.5 dBTP, 9.7 LU range
  Saved to output/normalized/some-track.mp3
```

## Typical workflow

```bash
pip install -r requirements.txt

# 1. fill in links.txt, then:
python download_mp3.py

# 2. clean up filenames:
python rename_files.py --dry-run
python rename_files.py

# 3. trim silence and normalize loudness:
python normalize_audio.py
```

## License

[MIT](LICENSE)
