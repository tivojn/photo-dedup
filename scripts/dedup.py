#!/usr/bin/env python3
"""
Photo Deduplication Tool
Finds unique photos from a set of duplicates/near-duplicates using perceptual hashing.
"""

import argparse
import json
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path

try:
    from PIL import Image
    import imagehash
except ImportError:
    print("ERROR: Required packages not installed. Run:")
    print("  pip3 install Pillow imagehash pillow-heif")

# Register HEIC/HEIF support if available
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass  # HEIC files will be skipped
    sys.exit(1)

SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic', '.webp', '.tiff', '.tif', '.bmp'}


def get_image_files(folder: Path) -> list[Path]:
    """Get all supported image files from folder."""
    files = []
    for f in sorted(folder.rglob('*')):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(f)
    return files


def compute_hash(filepath: Path) -> imagehash.ImageHash | None:
    """Compute perceptual hash for an image."""
    try:
        with Image.open(filepath) as img:
            return imagehash.phash(img)
    except Exception as e:
        print(f"  WARNING: Could not process {filepath.name}: {e}")
        return None


def cluster_images(image_hashes: dict[Path, imagehash.ImageHash], threshold: int) -> list[list[Path]]:
    """Group images into clusters based on hash similarity."""
    files = list(image_hashes.keys())
    visited = set()
    clusters = []

    for i, file_a in enumerate(files):
        if file_a in visited:
            continue
        cluster = [file_a]
        visited.add(file_a)

        for j in range(i + 1, len(files)):
            file_b = files[j]
            if file_b in visited:
                continue
            distance = image_hashes[file_a] - image_hashes[file_b]
            if distance <= threshold:
                cluster.append(file_b)
                visited.add(file_b)

        clusters.append(cluster)

    return clusters


def pick_best(cluster: list[Path]) -> Path:
    """Pick the best image from a cluster (largest file = highest quality)."""
    return max(cluster, key=lambda f: f.stat().st_size)


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def main():
    parser = argparse.ArgumentParser(description="Find unique photos from duplicates")
    parser.add_argument("source", help="Source folder containing photos")
    parser.add_argument("--threshold", type=int, default=6,
                        help="Similarity threshold (0-20, default: 6). Lower = stricter.")
    parser.add_argument("--preview", action="store_true",
                        help="Preview mode — show results without copying files")
    parser.add_argument("--output", help="Custom output folder (default: source/unique/)")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    if not source.is_dir():
        print(f"ERROR: '{source}' is not a directory")
        sys.exit(1)

    output = Path(args.output) if args.output else source / "unique"

    # Find images
    print(f"Scanning: {source}")
    images = get_image_files(source)
    if not images:
        print("No supported image files found.")
        sys.exit(0)

    print(f"Found {len(images)} images. Computing hashes...")

    # Compute hashes
    hashes = {}
    for i, img in enumerate(images, 1):
        h = compute_hash(img)
        if h is not None:
            hashes[img] = h
        if i % 50 == 0 or i == len(images):
            print(f"  Processed {i}/{len(images)}")

    # Cluster
    print(f"\nClustering with threshold={args.threshold}...")
    clusters = cluster_images(hashes, args.threshold)

    # Pick best from each cluster
    unique_picks = []
    duplicate_count = 0
    report_clusters = []

    for cluster in clusters:
        best = pick_best(cluster)
        unique_picks.append(best)
        dupes = [f for f in cluster if f != best]
        duplicate_count += len(dupes)

        report_clusters.append({
            "selected": best.name,
            "selected_size": format_size(best.stat().st_size),
            "duplicates": [f.name for f in dupes],
            "count": len(cluster)
        })

    # Sort clusters by size (most duplicates first)
    report_clusters.sort(key=lambda c: c["count"], reverse=True)

    # Print summary
    print(f"\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    print(f"  Total photos scanned:  {len(hashes)}")
    print(f"  Unique photos found:   {len(unique_picks)}")
    print(f"  Duplicates identified: {duplicate_count}")
    print(f"  Dedup ratio:           {len(hashes)}:{len(unique_picks)} ({100*len(unique_picks)/len(hashes):.0f}% unique)")

    # Show top clusters with most duplicates
    multi_clusters = [c for c in report_clusters if c["count"] > 1]
    if multi_clusters:
        print(f"\n  Top duplicate groups:")
        for c in multi_clusters[:10]:
            print(f"    - {c['selected']} ({c['selected_size']}) + {len(c['duplicates'])} duplicate(s)")

    if args.preview:
        print(f"\n  PREVIEW MODE — no files were copied.")
        print(f"  Run without --preview to copy unique photos to output folder.")
    else:
        # Copy unique photos
        output.mkdir(parents=True, exist_ok=True)
        print(f"\n  Copying {len(unique_picks)} unique photos to: {output}")
        for img in unique_picks:
            dest = output / img.name
            if dest.exists():
                # Handle name collision
                stem = img.stem
                suffix = img.suffix
                counter = 1
                while dest.exists():
                    dest = output / f"{stem}_{counter}{suffix}"
                    counter += 1
            shutil.copy2(img, dest)
        print(f"  Done! Unique photos saved to: {output}")

    # Save report
    report = {
        "source": str(source),
        "total_scanned": len(hashes),
        "unique_count": len(unique_picks),
        "duplicate_count": duplicate_count,
        "threshold": args.threshold,
        "clusters": report_clusters
    }
    if args.preview:
        report_path = Path("/tmp") / f"dedup_report_{source.name}.json"
    else:
        report_path = output / "dedup_report.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"  Report saved to: {report_path}")


if __name__ == "__main__":
    main()
