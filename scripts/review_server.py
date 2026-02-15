#!/usr/bin/env python3
"""
Photo Dedup Review Server
Interactive web UI for reviewing duplicate groups and selecting which photos to keep.
Copies selected photos to a dedicated output folder. Never deletes anything.
"""

import argparse
import base64
import io
import json
import mimetypes
import shutil
import sys
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

try:
    from PIL import Image
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

# Globals set at startup
SOURCE_DIR = None
REPORT_DATA = None
OUTPUT_DIR = None
TRASH_DIR = None  # .dedup_trash inside source — for undo support
TRASH_MANIFEST = {}  # {original_path: trash_path} for undo


def find_file(filename):
    """Find a file by name in the source directory."""
    matches = list(SOURCE_DIR.rglob(filename))
    return matches[0] if matches else None


def make_thumbnail_b64(filepath, max_size=600):
    """Create a base64-encoded JPEG thumbnail for browser display."""
    try:
        img = Image.open(filepath)
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        buf = io.BytesIO()
        img.convert('RGB').save(buf, format='JPEG', quality=85)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"  Warning: couldn't thumbnail {filepath.name}: {e}")
        return ""


def build_html():
    """Build the interactive review page — Notion-style design."""
    clusters = [c for c in REPORT_DATA['clusters'] if c['count'] > 1]
    total = REPORT_DATA['total_scanned']
    groups = len(clusters)
    dupes = REPORT_DATA['duplicate_count']

    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Photo Dedup</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {{
  --bg: #ffffff;
  --bg-secondary: #f7f6f3;
  --bg-hover: #f1f1ef;
  --bg-active: #e8e7e4;
  --text: #37352f;
  --text-secondary: #787774;
  --text-tertiary: #b4b4b0;
  --border: #e9e9e7;
  --blue: #2383e2;
  --blue-bg: #e7f3ff;
  --blue-light: #d3e5ef;
  --green: #0f7b6c;
  --green-bg: #dbeddb;
  --red: #eb5757;
  --red-bg: #fbe4e4;
  --orange: #d9730d;
  --orange-bg: #fbecdd;
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.04);
  --shadow-md: 0 2px 8px rgba(0,0,0,0.08);
  --shadow-lg: 0 8px 30px rgba(0,0,0,0.12);
  --radius: 6px;
}}

* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ scroll-behavior: smooth; }}
body {{
  font-family: 'Inter', ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif;
  color: var(--text);
  background: var(--bg);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}}

.page {{
  max-width: 900px;
  margin: 0 auto;
  padding: 0 96px 80px;
}}

/* Cover */
.cover {{
  height: 180px;
  background: linear-gradient(135deg, #f7f6f3 0%, #e8e7e4 50%, #d3e5ef 100%);
  position: relative;
}}
.cover-icon {{
  position: absolute;
  bottom: -36px;
  left: 96px;
  font-size: 64px;
  line-height: 1;
}}

/* Header */
.header {{
  padding-top: 52px;
  margin-bottom: 4px;
}}
.header h1 {{
  font-size: 40px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.02em;
  line-height: 1.2;
}}
.header .desc {{
  color: var(--text-secondary);
  font-size: 16px;
  margin-top: 4px;
}}

/* Properties */
.properties {{
  display: flex;
  flex-direction: column;
  gap: 0;
  margin: 24px 0 32px;
  font-size: 14px;
}}
.prop-row {{
  display: flex;
  align-items: center;
  padding: 6px 0;
  border-top: 1px solid var(--border);
}}
.prop-row:last-child {{ border-bottom: 1px solid var(--border); }}
.prop-label {{
  width: 160px;
  flex-shrink: 0;
  color: var(--text-secondary);
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 6px;
}}
.prop-label svg {{ width: 14px; height: 14px; color: var(--text-tertiary); }}
.prop-value {{ font-size: 14px; }}
.prop-tag {{
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 12px;
  font-weight: 500;
}}
.prop-tag.blue {{ background: var(--blue-bg); color: var(--blue); }}
.prop-tag.orange {{ background: var(--orange-bg); color: var(--orange); }}
.prop-tag.green {{ background: var(--green-bg); color: var(--green); }}

/* Toolbar */
.toolbar {{
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(255,255,255,0.95);
  backdrop-filter: blur(16px);
  padding: 12px 0;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid var(--border);
}}
.toolbar .sel-info {{
  font-size: 14px;
  color: var(--text-secondary);
  margin-right: auto;
}}
.toolbar .sel-info strong {{
  color: var(--text);
  font-weight: 600;
}}
.btn {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  border-radius: var(--radius);
  padding: 6px 12px;
  font-size: 14px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: background 80ms ease-in;
  white-space: nowrap;
}}
.btn-ghost {{
  background: transparent;
  color: var(--text-secondary);
}}
.btn-ghost:hover {{ background: var(--bg-hover); color: var(--text); }}
.btn-action {{
  background: var(--blue);
  color: #fff;
}}
.btn-action:hover {{ background: #1b6ec2; }}
.btn-action:disabled {{
  background: var(--bg-active);
  color: var(--text-tertiary);
  cursor: default;
}}
.btn-danger {{
  background: var(--red-bg);
  color: var(--red);
}}
.btn-danger:hover {{ background: #f5c6c6; }}
.btn-undo {{
  background: var(--orange-bg);
  color: var(--orange);
}}
.btn-undo:hover {{ background: #f5d9b8; }}
.photo.removed {{
  opacity: 0.25;
  pointer-events: none;
  filter: grayscale(1);
}}

/* Divider */
.divider {{
  height: 1px;
  background: var(--border);
  margin: 28px 0 20px;
}}

/* Group */
.group {{
  margin-bottom: 36px;
}}
.group-header {{
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
}}
.group-title {{
  font-size: 18px;
  font-weight: 600;
  color: var(--text);
}}
.group-count {{
  font-size: 13px;
  color: var(--text-tertiary);
}}

/* Photo grid */
.photos {{
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}}
.photo {{
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  background: var(--bg-secondary);
  box-shadow: var(--shadow-sm);
  transition: box-shadow 150ms ease, transform 150ms ease;
  flex: 0 0 auto;
}}
.photo:hover {{
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}}
.photo.selected {{
  outline: 2.5px solid var(--blue);
  outline-offset: -2.5px;
}}

/* Checkbox overlay */
.photo .checkbox {{
  position: absolute;
  top: 10px;
  left: 10px;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  border: 2px solid rgba(255,255,255,0.8);
  background: rgba(255,255,255,0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 120ms ease;
}}
.photo:hover .checkbox {{
  border-color: var(--blue);
  background: rgba(255,255,255,0.9);
}}
.photo.selected .checkbox {{
  background: var(--blue);
  border-color: var(--blue);
}}
.photo.selected .checkbox svg {{
  opacity: 1;
}}
.photo .checkbox svg {{
  width: 14px;
  height: 14px;
  color: #fff;
  opacity: 0;
  transition: opacity 80ms ease;
}}

.photo img {{
  display: block;
  height: 220px;
  width: auto;
  min-width: 160px;
  max-width: 320px;
  object-fit: cover;
}}
.photo-meta {{
  padding: 10px 12px;
  background: var(--bg);
}}
.photo-meta-row {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}}
.photo-size {{
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}}
.photo-name {{
  font-size: 11px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
  margin-top: 2px;
}}
.badge {{
  font-size: 11px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 3px;
}}
.badge-best {{
  background: var(--green-bg);
  color: var(--green);
}}
.badge-dupe {{
  background: var(--red-bg);
  color: var(--red);
}}

/* Result overlay */
.overlay {{
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(15,15,15,0.6);
  z-index: 999;
  justify-content: center;
  align-items: center;
}}
.overlay.show {{ display: flex; }}
.modal {{
  background: var(--bg);
  border-radius: 12px;
  box-shadow: var(--shadow-lg);
  padding: 32px;
  max-width: 440px;
  width: 90%;
  text-align: center;
}}
.modal-icon {{
  font-size: 48px;
  margin-bottom: 12px;
}}
.modal h2 {{
  font-size: 20px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 8px;
}}
.modal p {{
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.6;
}}
.modal .path-display {{
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 14px;
  margin: 16px 0;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 13px;
  color: var(--text);
  word-break: break-all;
  text-align: left;
}}
.modal .btn {{ margin-top: 12px; }}

/* Callout */
.callout {{
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 16px;
  border-radius: var(--radius);
  background: var(--bg-secondary);
  margin-bottom: 28px;
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.5;
}}
.callout-icon {{ font-size: 20px; flex-shrink: 0; margin-top: -1px; }}
</style></head>
<body>

<div class="cover">
  <div class="cover-icon">📸</div>
</div>

<div class="page">
  <div class="header">
    <h1>Photo Dedup Review</h1>
    <p class="desc">Select which photos to keep from each duplicate group</p>
  </div>

  <div class="properties">
    <div class="prop-row">
      <div class="prop-label">
        <svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM0 8a8 8 0 1116 0A8 8 0 010 8z"/><path d="M8 3.5a.75.75 0 01.75.75v3.5h2.5a.75.75 0 010 1.5h-3.25a.75.75 0 01-.75-.75v-4.25A.75.75 0 018 3.5z"/></svg>
        Status
      </div>
      <div class="prop-value"><span class="prop-tag blue">In Review</span></div>
    </div>
    <div class="prop-row">
      <div class="prop-label">
        <svg viewBox="0 0 16 16" fill="currentColor"><path d="M2.5 3.5v9h11v-9h-11zM2 2h12a1 1 0 011 1v10a1 1 0 01-1 1H2a1 1 0 01-1-1V3a1 1 0 011-1z"/></svg>
        Total Scanned
      </div>
      <div class="prop-value"><span class="prop-tag green">{total} photos</span></div>
    </div>
    <div class="prop-row">
      <div class="prop-label">
        <svg viewBox="0 0 16 16" fill="currentColor"><path d="M5.5 3.5h5v1h-5v-1zm0 3h5v1h-5v-1zm0 3h3v1h-3v-1z"/><path d="M2 1h12a1 1 0 011 1v12a1 1 0 01-1 1H2a1 1 0 01-1-1V2a1 1 0 011-1zm.5 1.5v11h11v-11h-11z"/></svg>
        Duplicate Groups
      </div>
      <div class="prop-value"><span class="prop-tag orange">{groups} groups</span></div>
    </div>
    <div class="prop-row">
      <div class="prop-label">
        <svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 1C4.1 1 1 4.1 1 8s3.1 7 7 7 7-3.1 7-7-3.1-7-7-7zm3.7 10.7L7 9.5V4h1.5v4.8l4 1.9-.8 1z"/></svg>
        Duplicates
      </div>
      <div class="prop-value">{dupes} photos</div>
    </div>
  </div>

  <div class="callout">
    <span class="callout-icon">💡</span>
    <span>Click any photo to select it. The <strong>best quality</strong> photo in each group is pre-selected. Your originals are never modified — selected photos are copied to a new folder.</span>
  </div>

  <div class="toolbar">
    <span class="sel-info">Selected: <strong id="sel-count">0</strong></span>
    <button class="btn btn-ghost" onclick="autoSelectBest()">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z"/></svg>
      Auto-select best
    </button>
    <button class="btn btn-ghost" onclick="deselectAll()">Deselect all</button>
    <button class="btn btn-action" id="save-btn" onclick="saveSelected()" disabled>Save selected</button>
    <div style="width:1px;height:24px;background:var(--border);margin:0 4px"></div>
    <button class="btn btn-danger" id="remove-btn" onclick="confirmRemove()">Remove unselected duplicates</button>
    <button class="btn btn-undo" id="undo-btn" onclick="undoRemove()" style="display:none">Undo</button>
  </div>
'''

    # Build groups
    checkSvg = '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z"/></svg>'

    for gi, c in enumerate(clusters):
        all_names = [c['selected']] + c['duplicates']
        html += f'<div class="group" id="group-{gi}">'
        html += f'<div class="group-header"><span class="group-title">Group {gi+1}</span>'
        html += f'<span class="group-count">{c["count"]} photos</span></div>'
        html += '<div class="photos">'

        for fname in all_names:
            fpath = find_file(fname)
            if not fpath:
                continue
            size_kb = fpath.stat().st_size / 1024
            is_best = (fname == c['selected'])
            thumb = make_thumbnail_b64(fpath)
            if not thumb:
                continue
            badge = '<span class="badge badge-best">Best</span>' if is_best else '<span class="badge badge-dupe">Dupe</span>'
            size_str = f"{size_kb:.0f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
            escaped_path = str(fpath).replace('"', '&quot;')

            html += f'''<div class="photo" data-path="{escaped_path}" data-group="{gi}" onclick="togglePhoto(this)">
  <div class="checkbox">{checkSvg}</div>
  <img src="data:image/jpeg;base64,{thumb}" loading="lazy">
  <div class="photo-meta">
    <div class="photo-meta-row">
      <span class="photo-size">{size_str}</span>
      {badge}
    </div>
    <div class="photo-name" title="{fname}">{fname[:28]}</div>
  </div>
</div>'''

        html += '</div></div>'

    html += '''
  <div class="overlay" id="result-overlay">
    <div class="modal">
      <div class="modal-icon" id="modal-icon">⏳</div>
      <h2 id="result-title">Saving...</h2>
      <p id="result-msg"></p>
      <div class="path-display" id="result-path" style="display:none"></div>
      <div id="modal-buttons" style="display:flex;gap:8px;justify-content:center;margin-top:16px"></div>
    </div>
  </div>
</div>

<script>
const selected = new Set();

function togglePhoto(el) {
  if (el.classList.contains('removed')) return;
  const path = el.dataset.path;
  if (selected.has(path)) {
    selected.delete(path);
    el.classList.remove('selected');
  } else {
    selected.add(path);
    el.classList.add('selected');
  }
  updateCount();
}

function updateCount() {
  const allPhotos = document.querySelectorAll('.photo:not(.removed)');
  const unselected = allPhotos.length - selected.size;
  document.getElementById('sel-count').textContent = selected.size + ' photos';
  document.getElementById('save-btn').disabled = selected.size === 0;
  document.getElementById('remove-btn').disabled = selected.size === 0;
}

function autoSelectBest() {
  document.querySelectorAll('.group').forEach(group => {
    group.querySelectorAll('.photo.selected').forEach(p => {
      selected.delete(p.dataset.path);
      p.classList.remove('selected');
    });
    const best = group.querySelector('.photo:not(.removed)');
    if (best) {
      selected.add(best.dataset.path);
      best.classList.add('selected');
    }
  });
  updateCount();
}

function deselectAll() {
  selected.clear();
  document.querySelectorAll('.photo.selected').forEach(p => p.classList.remove('selected'));
  updateCount();
}

// — Save selected (copies to output folder) —
async function saveSelected() {
  if (selected.size === 0) return;
  showModal('⏳', 'Saving...', 'Copying ' + selected.size + ' photos...');
  try {
    const resp = await fetch('/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({files: Array.from(selected)})
    });
    const data = await resp.json();
    if (data.ok) {
      showModal('✅', 'Photos saved', data.count + ' photos copied. Originals untouched.', data.output_dir);
    } else { showModal('❌', 'Something went wrong', data.error); }
  } catch(e) { showModal('❌', 'Something went wrong', e.message); }
}

// — Remove unselected duplicates (moves to trash, supports undo) —
function confirmRemove() {
  if (selected.size === 0) {
    showModal('⚠️', 'Select photos first', 'You need to select which photos to KEEP before removing the rest.');
    return;
  }
  // Gather unselected paths
  const allPaths = new Set();
  document.querySelectorAll('.photo:not(.removed)').forEach(p => allPaths.add(p.dataset.path));
  const toRemove = [...allPaths].filter(p => !selected.has(p));
  if (toRemove.length === 0) {
    showModal('👍', 'Nothing to remove', 'All photos in duplicate groups are selected.');
    return;
  }
  // Show confirmation
  showModal(
    '🗑️',
    'Remove ' + toRemove.length + ' unselected duplicates?',
    'These files will be moved to a .dedup_trash folder (not permanently deleted). You can Undo anytime.',
    null,
    [{label: 'Remove them', cls: 'btn-danger', action: () => doRemove(toRemove)},
     {label: 'Cancel', cls: 'btn-ghost', action: closeModal}]
  );
}

async function doRemove(paths) {
  showModal('⏳', 'Moving to trash...', 'Moving ' + paths.length + ' files...');
  try {
    const resp = await fetch('/remove', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({files: paths})
    });
    const data = await resp.json();
    if (data.ok) {
      // Grey out removed photos in UI
      paths.forEach(p => {
        const el = document.querySelector('.photo[data-path="' + CSS.escape(p) + '"]');
        if (el) {
          selected.delete(p);
          el.classList.remove('selected');
          el.classList.add('removed');
        }
      });
      updateCount();
      document.getElementById('undo-btn').style.display = 'inline-flex';
      showModal('🗑️', 'Removed ' + data.count + ' duplicates',
        'Files moved to .dedup_trash folder. Click <b>Undo</b> in the toolbar to restore them.',
        data.trash_dir);
    } else { showModal('❌', 'Something went wrong', data.error); }
  } catch(e) { showModal('❌', 'Something went wrong', e.message); }
}

// — Undo (restores from trash) —
async function undoRemove() {
  showModal('⏳', 'Restoring...', 'Moving files back from trash...');
  try {
    const resp = await fetch('/undo', {method: 'POST'});
    const data = await resp.json();
    if (data.ok) {
      // Un-grey all removed photos
      document.querySelectorAll('.photo.removed').forEach(el => el.classList.remove('removed'));
      document.getElementById('undo-btn').style.display = 'none';
      autoSelectBest();
      showModal('↩️', 'Restored ' + data.count + ' photos', 'All files moved back to their original location.');
    } else { showModal('❌', 'Something went wrong', data.error); }
  } catch(e) { showModal('❌', 'Something went wrong', e.message); }
}

// — Modal helper —
function showModal(icon, title, msg, path, buttons) {
  document.getElementById('modal-icon').textContent = icon;
  document.getElementById('result-title').textContent = title;
  document.getElementById('result-msg').innerHTML = msg;
  const pathEl = document.getElementById('result-path');
  if (path) { pathEl.textContent = path; pathEl.style.display = 'block'; }
  else { pathEl.style.display = 'none'; }
  // Custom buttons or default close
  const btnArea = document.getElementById('modal-buttons');
  btnArea.innerHTML = '';
  if (buttons) {
    buttons.forEach(b => {
      const btn = document.createElement('button');
      btn.className = 'btn ' + b.cls;
      btn.textContent = b.label;
      btn.onclick = b.action;
      btnArea.appendChild(btn);
    });
  } else {
    const btn = document.createElement('button');
    btn.className = 'btn btn-action';
    btn.textContent = 'Done';
    btn.onclick = closeModal;
    btnArea.appendChild(btn);
  }
  document.getElementById('result-overlay').classList.add('show');
}
function closeModal() {
  document.getElementById('result-overlay').classList.remove('show');
}

autoSelectBest();
</script>
</body></html>'''
    return html


class ReviewHandler(BaseHTTPRequestHandler):
    html_cache = None

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            if ReviewHandler.html_cache is None:
                print("Building review page (thumbnailing photos)...")
                ReviewHandler.html_cache = build_html()
                print("Ready!")
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(ReviewHandler.html_cache.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global TRASH_MANIFEST

        if self.path == '/save':
            length = int(self.headers['Content-Length'])
            body = json.loads(self.rfile.read(length))
            files = body.get('files', [])

            try:
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                copied = 0
                for fpath_str in files:
                    fpath = Path(fpath_str)
                    if fpath.exists():
                        dest = OUTPUT_DIR / fpath.name
                        if dest.exists():
                            stem, suffix = fpath.stem, fpath.suffix
                            counter = 1
                            while dest.exists():
                                dest = OUTPUT_DIR / f"{stem}_{counter}{suffix}"
                                counter += 1
                        shutil.copy2(fpath, dest)
                        copied += 1

                result = {'ok': True, 'count': copied, 'output_dir': str(OUTPUT_DIR)}
            except Exception as e:
                result = {'ok': False, 'error': str(e)}

            self._json_response(result)

        elif self.path == '/remove':
            length = int(self.headers['Content-Length'])
            body = json.loads(self.rfile.read(length))
            files = body.get('files', [])

            try:
                TRASH_DIR.mkdir(parents=True, exist_ok=True)
                moved = 0
                for fpath_str in files:
                    fpath = Path(fpath_str)
                    if fpath.exists():
                        trash_dest = TRASH_DIR / fpath.name
                        # Handle name collision in trash
                        if trash_dest.exists():
                            stem, suffix = fpath.stem, fpath.suffix
                            counter = 1
                            while trash_dest.exists():
                                trash_dest = TRASH_DIR / f"{stem}_{counter}{suffix}"
                                counter += 1
                        shutil.move(str(fpath), str(trash_dest))
                        TRASH_MANIFEST[str(fpath)] = str(trash_dest)
                        moved += 1

                # Persist manifest so undo survives server restart
                manifest_path = TRASH_DIR / 'manifest.json'
                with open(manifest_path, 'w') as f:
                    json.dump(TRASH_MANIFEST, f, indent=2)

                result = {'ok': True, 'count': moved, 'trash_dir': str(TRASH_DIR)}
            except Exception as e:
                result = {'ok': False, 'error': str(e)}

            self._json_response(result)

        elif self.path == '/undo':
            try:
                restored = 0
                for original_str, trash_str in list(TRASH_MANIFEST.items()):
                    trash_path = Path(trash_str)
                    original_path = Path(original_str)
                    if trash_path.exists():
                        original_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(trash_path), str(original_path))
                        restored += 1

                TRASH_MANIFEST.clear()
                # Clean up manifest file and trash dir if empty
                manifest_path = TRASH_DIR / 'manifest.json'
                if manifest_path.exists():
                    manifest_path.unlink()
                if TRASH_DIR.exists() and not any(TRASH_DIR.iterdir()):
                    TRASH_DIR.rmdir()

                result = {'ok': True, 'count': restored}
            except Exception as e:
                result = {'ok': False, 'error': str(e)}

            self._json_response(result)

        else:
            self.send_response(404)
            self.end_headers()

    def _json_response(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        # Quieter logging
        pass


def main():
    global SOURCE_DIR, REPORT_DATA, OUTPUT_DIR, TRASH_DIR, TRASH_MANIFEST

    parser = argparse.ArgumentParser(description="Photo Dedup Review Server")
    parser.add_argument("report", help="Path to dedup_report.json")
    parser.add_argument("--source", help="Source photos directory (overrides report)")
    parser.add_argument("--output", help="Output directory for selected photos")
    parser.add_argument("--port", type=int, default=8765, help="Server port (default: 8765)")
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        print(f"ERROR: Report not found: {report_path}")
        sys.exit(1)

    REPORT_DATA = json.load(open(report_path))
    SOURCE_DIR = Path(args.source) if args.source else Path(REPORT_DATA['source'])

    if not SOURCE_DIR.is_dir():
        print(f"ERROR: Source directory not found: {SOURCE_DIR}")
        sys.exit(1)

    if args.output:
        OUTPUT_DIR = Path(args.output)
    else:
        OUTPUT_DIR = SOURCE_DIR.parent / "selected_photos"

    TRASH_DIR = SOURCE_DIR / '.dedup_trash'

    # Load existing trash manifest if resuming
    manifest_path = TRASH_DIR / 'manifest.json'
    if manifest_path.exists():
        with open(manifest_path) as f:
            TRASH_MANIFEST = json.load(f)
        print(f"Loaded existing trash manifest ({len(TRASH_MANIFEST)} files)")

    print(f"Source:  {SOURCE_DIR}")
    print(f"Output:  {OUTPUT_DIR}")
    print(f"Report:  {report_path}")
    print(f"\nStarting review server on http://localhost:{args.port}")
    print("Opening browser...")

    import webbrowser
    webbrowser.open(f"http://localhost:{args.port}")

    server = HTTPServer(('localhost', args.port), ReviewHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
