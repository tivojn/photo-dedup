# Photo Dedup

Find and select unique photos from hundreds of duplicates. Built for workflows like school photography where ~500 photos come in but only ~100 are truly unique.

## How It Works

1. **Perceptual Hashing** - Each image is converted to a perceptual hash (pHash). Similar-looking images produce similar hashes, even if they differ in resolution, compression, or minor edits.

2. **Clustering** - Images are grouped by hash similarity. Each cluster represents one "scene" or "shot". The best image (largest file = highest quality) is auto-selected.

3. **Interactive Review** - A local web UI lets you see all duplicate groups side by side, select which to keep, and save or remove with one click.

## Quick Start

### Requirements

```bash
pip3 install Pillow imagehash pillow-heif
```

Python 3.10+ required. No other dependencies.

### 1. Scan for duplicates

```bash
python3 scripts/dedup.py ~/Photos/event-folder/ --preview
```

This scans the folder, finds duplicates, and saves a report to `/tmp/dedup_report_<folder>.json`.

Options:
- `--preview` - Scan only, don't copy files
- `--threshold N` - Similarity sensitivity (default: 6, range 0-20). Lower = stricter, higher = more aggressive grouping
- `--output DIR` - Custom output folder for unique photos

### 2. Review & select

```bash
python3 scripts/review_server.py /tmp/dedup_report_<folder>.json --output ~/Desktop/selected_photos
```

Opens a browser with the review UI where you can:
- See all duplicate groups side by side
- Click to select which photos to keep
- **Auto-select best** - one-click pick of highest quality from each group
- **Save selected** - copies chosen photos to the output folder
- **Remove unselected duplicates** - moves dupes to `.dedup_trash/` (with Undo support)

### Supported Formats

JPG, JPEG, PNG, HEIC, WEBP, TIFF, BMP

### Safety

- Originals are **never** modified or deleted
- "Remove" moves files to a `.dedup_trash/` folder with full undo support
- "Save" copies files to a new folder, leaving originals in place

## Claude Code Skill

This is also a [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skill. Install it and use natural language:

```
> dedup my photos in ~/Photos/school-event/
```

See `skill.md` for the skill definition.

## License

MIT
