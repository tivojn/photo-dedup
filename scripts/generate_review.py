#!/usr/bin/env python3
"""
Photo Dedup — Static Review Page Generator
Generates a self-contained HTML file for reviewing duplicate groups.
No server needed. User selects photos, clicks Save, gets a shell script to run.
"""

import argparse
import base64
import io
import json
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("ERROR: pip3 install Pillow pillow-heif")
    sys.exit(1)

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass


def make_thumbnail_b64(filepath, max_size=600):
    try:
        img = Image.open(filepath)
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        buf = io.BytesIO()
        img.convert('RGB').save(buf, format='JPEG', quality=85)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"  Warning: couldn't thumbnail {filepath.name}: {e}")
        return ""


def main():
    parser = argparse.ArgumentParser(description="Generate static dedup review HTML")
    parser.add_argument("report", help="Path to dedup_report.json")
    parser.add_argument("--source", help="Source photos directory (overrides report)")
    parser.add_argument("--output-dir", help="Default output dir for the save script",
                        default="~/Desktop/selected_photos")
    parser.add_argument("-o", "--out", help="Output HTML path", default=None)
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        print(f"ERROR: Report not found: {report_path}")
        sys.exit(1)

    data = json.load(open(report_path))
    source_dir = Path(args.source) if args.source else Path(data['source'])

    if not source_dir.is_dir():
        print(f"ERROR: Source directory not found: {source_dir}")
        sys.exit(1)

    clusters = [c for c in data['clusters'] if c['count'] > 1]
    if not clusters:
        print("No duplicate groups found. Nothing to review.")
        sys.exit(0)

    total = data['total_scanned']
    groups = len(clusters)
    dupes = data['duplicate_count']
    output_dir = args.output_dir

    print(f"Source:  {source_dir}")
    print(f"Groups:  {groups} ({dupes} duplicates)")
    print("Generating thumbnails...")

    # Build photo data
    photo_entries = []  # list of (group_idx, fname, path_str, size_str, is_best, thumb_b64)
    for gi, c in enumerate(clusters):
        all_names = [c['selected']] + c['duplicates']
        for fname in all_names:
            matches = list(source_dir.rglob(fname))
            if not matches:
                continue
            fpath = matches[0]
            size_kb = fpath.stat().st_size / 1024
            is_best = (fname == c['selected'])
            thumb = make_thumbnail_b64(fpath)
            if not thumb:
                continue
            size_str = f"{size_kb:.0f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
            photo_entries.append((gi, fname, str(fpath), size_str, is_best, thumb))

    print(f"Thumbnailed {len(photo_entries)} photos across {groups} groups.")

    # Build HTML
    check_svg = '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z"/></svg>'

    groups_html = ""
    for gi, c in enumerate(clusters):
        group_photos = [e for e in photo_entries if e[0] == gi]
        if not group_photos:
            continue

        photos_html = ""
        for _, fname, fpath_str, size_str, is_best, thumb in group_photos:
            badge = '<span class="badge badge-best">Best</span>' if is_best else '<span class="badge badge-dupe">Dupe</span>'
            escaped = fpath_str.replace('"', '&quot;')
            photos_html += f'''<div class="photo" data-path="{escaped}" onclick="toggle(this)">
  <div class="cb">{check_svg}</div>
  <img src="data:image/jpeg;base64,{thumb}" loading="lazy">
  <div class="meta">
    <div class="meta-row"><span class="size">{size_str}</span>{badge}</div>
    <div class="name" title="{fname}">{fname[:28]}</div>
  </div>
</div>'''

        groups_html += f'''<div class="group">
  <div class="gh"><span class="gt">Group {gi+1}</span><span class="gc">{c["count"]} photos</span></div>
  <div class="photos">{photos_html}</div>
</div>'''

    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Photo Dedup Review</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root {{
  --bg:#fff; --bg2:#f7f6f3; --bgH:#f1f1ef; --bgA:#e8e7e4;
  --tx:#37352f; --tx2:#787774; --tx3:#b4b4b0; --bd:#e9e9e7;
  --bl:#2383e2; --blBg:#e7f3ff; --gn:#0f7b6c; --gnBg:#dbeddb;
  --rd:#eb5757; --rdBg:#fbe4e4; --or:#d9730d; --orBg:#fbecdd;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',ui-sans-serif,-apple-system,sans-serif;color:var(--tx);background:var(--bg);-webkit-font-smoothing:antialiased}}
.page{{max-width:900px;margin:0 auto;padding:0 96px 80px}}
.cover{{height:180px;background:linear-gradient(135deg,#f7f6f3,#e8e7e4 50%,#d3e5ef);position:relative}}
.cover-icon{{position:absolute;bottom:-36px;left:96px;font-size:64px;line-height:1}}
.header{{padding-top:52px;margin-bottom:4px}}
.header h1{{font-size:40px;font-weight:700;letter-spacing:-0.02em;line-height:1.2}}
.header .desc{{color:var(--tx2);font-size:16px;margin-top:4px}}
.props{{display:flex;flex-direction:column;margin:24px 0 32px;font-size:14px}}
.pr{{display:flex;align-items:center;padding:6px 0;border-top:1px solid var(--bd)}}
.pr:last-child{{border-bottom:1px solid var(--bd)}}
.pl{{width:160px;flex-shrink:0;color:var(--tx2);font-size:14px}}
.tag{{display:inline-flex;padding:2px 8px;border-radius:3px;font-size:12px;font-weight:500}}
.tag-bl{{background:var(--blBg);color:var(--bl)}} .tag-gn{{background:var(--gnBg);color:var(--gn)}}
.tag-or{{background:var(--orBg);color:var(--or)}}
.callout{{display:flex;gap:10px;padding:16px;border-radius:6px;background:var(--bg2);margin-bottom:28px;font-size:14px;color:var(--tx2);line-height:1.5}}
.callout b{{color:var(--tx)}}
.toolbar{{position:sticky;top:0;z-index:100;background:rgba(255,255,255,.95);backdrop-filter:blur(16px);padding:12px 0;margin-bottom:8px;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--bd)}}
.sel{{font-size:14px;color:var(--tx2);margin-right:auto}} .sel strong{{color:var(--tx);font-weight:600}}
.btn{{display:inline-flex;align-items:center;gap:6px;border:none;border-radius:6px;padding:6px 12px;font-size:14px;font-weight:500;font-family:inherit;cursor:pointer;transition:background 80ms;white-space:nowrap}}
.btn-g{{background:transparent;color:var(--tx2)}} .btn-g:hover{{background:var(--bgH);color:var(--tx)}}
.btn-a{{background:var(--bl);color:#fff}} .btn-a:hover{{background:#1b6ec2}}
.btn-a:disabled{{background:var(--bgA);color:var(--tx3);cursor:default}}
.group{{margin-bottom:36px}}
.gh{{display:flex;align-items:baseline;gap:10px;margin-bottom:12px}}
.gt{{font-size:18px;font-weight:600}} .gc{{font-size:13px;color:var(--tx3)}}
.photos{{display:flex;gap:16px;flex-wrap:wrap}}
.photo{{position:relative;border-radius:8px;overflow:hidden;cursor:pointer;background:var(--bg2);box-shadow:0 1px 2px rgba(0,0,0,.04);transition:box-shadow 150ms,transform 150ms}}
.photo:hover{{box-shadow:0 2px 8px rgba(0,0,0,.08);transform:translateY(-1px)}}
.photo.sel{{outline:2.5px solid var(--bl);outline-offset:-2.5px}}
.cb{{position:absolute;top:10px;left:10px;width:22px;height:22px;border-radius:4px;border:2px solid rgba(255,255,255,.8);background:rgba(255,255,255,.5);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;transition:all 120ms}}
.photo:hover .cb{{border-color:var(--bl);background:rgba(255,255,255,.9)}}
.photo.sel .cb{{background:var(--bl);border-color:var(--bl)}}
.photo.sel .cb svg{{opacity:1}} .cb svg{{width:14px;height:14px;color:#fff;opacity:0;transition:opacity 80ms}}
.photo img{{display:block;height:220px;width:auto;min-width:160px;max-width:320px;object-fit:cover}}
.meta{{padding:10px 12px;background:var(--bg)}}
.meta-row{{display:flex;align-items:center;justify-content:space-between;gap:8px}}
.size{{font-size:13px;font-weight:600}}
.name{{font-size:11px;color:var(--tx3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px;margin-top:2px}}
.badge{{font-size:11px;font-weight:500;padding:1px 6px;border-radius:3px}}
.badge-best{{background:var(--gnBg);color:var(--gn)}} .badge-dupe{{background:var(--rdBg);color:var(--rd)}}
.overlay{{display:none;position:fixed;inset:0;background:rgba(15,15,15,.6);z-index:999;justify-content:center;align-items:center}}
.overlay.show{{display:flex}}
.modal{{background:var(--bg);border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.12);padding:32px;max-width:540px;width:90%;text-align:center}}
.modal-icon{{font-size:48px;margin-bottom:12px}}
.modal h2{{font-size:20px;font-weight:600;margin-bottom:8px}}
.modal p{{color:var(--tx2);font-size:14px;line-height:1.6}}
.modal .script-box{{background:var(--bg2);border:1px solid var(--bd);border-radius:6px;padding:14px;margin:16px 0;font-family:'SF Mono','Fira Code',monospace;font-size:12px;color:var(--tx);text-align:left;max-height:200px;overflow-y:auto;white-space:pre-wrap;word-break:break-all}}
.modal .btn{{margin-top:8px}}
.modal .btn-row{{display:flex;gap:8px;justify-content:center;margin-top:16px}}
</style></head>
<body>

<div class="cover"><div class="cover-icon">📸</div></div>
<div class="page">
  <div class="header">
    <h1>Photo Dedup Review</h1>
    <p class="desc">Select which photos to keep from each duplicate group</p>
  </div>

  <div class="props">
    <div class="pr"><div class="pl">Status</div><span class="tag tag-bl">In Review</span></div>
    <div class="pr"><div class="pl">Total Scanned</div><span class="tag tag-gn">{total} photos</span></div>
    <div class="pr"><div class="pl">Duplicate Groups</div><span class="tag tag-or">{groups} groups</span></div>
    <div class="pr"><div class="pl">Duplicates</div>{dupes} photos</div>
  </div>

  <div class="callout">
    <span style="font-size:20px">💡</span>
    <span>Click any photo to select it. The <b>best quality</b> photo in each group is pre-selected. Hit <b>Save</b> to download a script that copies your picks to a folder. Originals are never touched.</span>
  </div>

  <div class="toolbar">
    <span class="sel">Selected: <strong id="cnt">0</strong></span>
    <button class="btn btn-g" onclick="best()">Auto-select best</button>
    <button class="btn btn-g" onclick="clear_()">Clear all</button>
    <button class="btn btn-a" id="save-btn" onclick="save()" disabled>Save selected</button>
  </div>

  {groups_html}

  <div class="overlay" id="ov">
    <div class="modal">
      <div class="modal-icon" id="m-icon">📋</div>
      <h2 id="m-title">Your save script</h2>
      <p id="m-msg">Copy and run this in Terminal, or click Download to save it as a file.</p>
      <div class="script-box" id="m-script"></div>
      <div class="btn-row">
        <button class="btn btn-g" onclick="copyScript()">Copy to clipboard</button>
        <button class="btn btn-a" onclick="dlScript()">Download .sh</button>
        <button class="btn btn-g" onclick="document.getElementById('ov').classList.remove('show')">Close</button>
      </div>
    </div>
  </div>
</div>

<script>
const S = new Set();
const OUT = "{output_dir}";

function toggle(el) {{
  const p = el.dataset.path;
  if (S.has(p)) {{ S.delete(p); el.classList.remove('sel'); }}
  else {{ S.add(p); el.classList.add('sel'); }}
  upd();
}}
function upd() {{
  document.getElementById('cnt').textContent = S.size + ' photos';
  document.getElementById('save-btn').disabled = S.size === 0;
}}
function best() {{
  document.querySelectorAll('.group').forEach(g => {{
    g.querySelectorAll('.photo.sel').forEach(p => {{ S.delete(p.dataset.path); p.classList.remove('sel'); }});
    const b = g.querySelector('.photo');
    if (b) {{ S.add(b.dataset.path); b.classList.add('sel'); }}
  }});
  upd();
}}
function clear_() {{
  S.clear();
  document.querySelectorAll('.photo.sel').forEach(p => p.classList.remove('sel'));
  upd();
}}

function buildScript() {{
  const dir = OUT.replace('~', '$HOME');
  let sh = '#!/bin/bash\\n# Photo Dedup — copy selected photos\\n';
  sh += '# Generated by photo-dedup skill\\n\\n';
  sh += 'OUT="' + dir + '"\\n';
  sh += 'mkdir -p "$OUT"\\n\\n';
  sh += 'echo "Copying ' + S.size + ' selected photos..."\\n\\n';
  Array.from(S).forEach(p => {{
    const escaped = p.replace(/'/g, "'\\\\''");
    const name = p.split('/').pop();
    sh += "cp -n '" + escaped + "' \\"$OUT/" + name + "\\"\\n";
  }});
  sh += '\\necho "Done! ' + S.size + ' photos saved to $OUT"\\n';
  return sh;
}}

function save() {{
  if (S.size === 0) return;
  const script = buildScript();
  document.getElementById('m-script').textContent = script;
  document.getElementById('ov').classList.add('show');
}}

function copyScript() {{
  const text = document.getElementById('m-script').textContent;
  navigator.clipboard.writeText(text).then(() => {{
    document.getElementById('m-msg').textContent = 'Copied! Paste into Terminal and press Enter.';
  }});
}}

function dlScript() {{
  const text = document.getElementById('m-script').textContent;
  const blob = new Blob([text], {{type: 'text/x-shellscript'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'copy_selected_photos.sh';
  a.click();
  document.getElementById('m-msg').textContent = 'Downloaded! Run: bash copy_selected_photos.sh';
}}

best();
</script>
</body></html>'''

    # Write output
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = source_dir / "dedup_review.html"
    out_path.write_text(html)
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"\nReview page saved to: {out_path} ({size_mb:.1f} MB)")
    print("Open it in any browser — no server needed.")


if __name__ == "__main__":
    main()
