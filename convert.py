#!/usr/bin/env python3
"""
ChatGPT Export Reader + Project Recovery

Fork-compatible extension of marelucent/chatgpt-export-reader.
Converts ChatGPT exports into readable Markdown/HTML and, for supported
2026-era exports, reconstructs Project membership and restores Project
Library file payloads from the export manifest.

Default usage:
    1. Unzip your ChatGPT data export.
    2. Put this script in the export folder (or pass the folder path).
    3. Run: python convert.py
    4. Open conversations/INDEX.html

No third-party packages are required.
"""

import argparse
import html
import json
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


TOOL_VERSION = "1.0.0"
REPOSITORY_URL = "https://github.com/rschaer/chatgpt-export-reader"
REPOSITORY_LABEL = "github.com/rschaer/chatgpt-export-reader"

PROJECT_ID_RE = re.compile(r"^g-p-[A-Za-z0-9_-]+$")
CONVERSATION_CHUNK_RE = re.compile(r"^conversations-(\d+)\.json$")
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def sanitize_filename(title, max_length=80):
    """Create a filesystem-safe filename component."""
    if not title:
        title = "Untitled"
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', str(title))
    safe = re.sub(r'\s+', ' ', safe).strip().rstrip('. ')
    if len(safe) > max_length:
        safe = safe[:max_length].rsplit(' ', 1)[0].rstrip('. ')
    if not safe:
        safe = "Untitled"
    if safe.upper() in WINDOWS_RESERVED_NAMES:
        safe = "_" + safe
    return safe


def safe_original_filename(record):
    """Return a safe basename while preserving the original extension/case when possible."""
    name = record.get('file_name') or record.get('normalized_name')
    if not name:
        ext = record.get('file_extension') or 'dat'
        name = f"{record.get('file_id', 'unknown_file')}.{ext}"
    # Keep only the final component to prevent path traversal from metadata.
    name = str(name).replace('\\', '/').split('/')[-1]
    stem, ext = os.path.splitext(name)
    stem = sanitize_filename(stem, max_length=140)
    ext = re.sub(r'[^A-Za-z0-9._-]', '', ext)[:30]
    return stem + ext


def timestamp_to_datetime(ts):
    """Convert Unix timestamp to local datetime."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts))
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def iso_to_datetime(value):
    if not value:
        return None
    text = str(value)
    parser = getattr(datetime, 'fromisoformat', None)
    if parser is not None:
        try:
            return parser(text.replace('Z', '+00:00'))
        except (TypeError, ValueError):
            pass
    # Python 3.6 fallback: sufficient for sorting export timestamps.
    try:
        return datetime.strptime(text[:19], '%Y-%m-%dT%H:%M:%S')
    except (TypeError, ValueError):
        return None


def extract_message_text(message):
    """Extract readable text from a ChatGPT message object."""
    if not message or 'content' not in message:
        return None

    content = message['content'] or {}
    content_type = content.get('content_type', '')

    if content_type in ('text', 'multimodal_text'):
        parts = content.get('parts', []) or []
        text_parts = []
        for part in parts:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                if part.get('content_type') == 'image_asset_pointer':
                    text_parts.append('[Image]')
                elif 'text' in part and isinstance(part.get('text'), str):
                    text_parts.append(part['text'])
        return '\n'.join(text_parts) if text_parts else None

    if content_type == 'code':
        return f"```\n{content.get('text', '')}\n```"

    # Preserve useful textual fallbacks found in some export variants.
    if isinstance(content.get('text'), str) and content.get('text'):
        return content['text']

    return None


def build_message_thread(mapping):
    """Build ordered messages from ChatGPT's conversation tree.

    Newer exports may omit each node's ``children`` list, so parent pointers
    are treated as authoritative and children are reconstructed from them.
    """
    if not mapping:
        return []

    children_map = defaultdict(list)
    nodes = {}

    for node_id, node in mapping.items():
        nodes[node_id] = node
        parent = node.get('parent')
        if parent:
            children_map[parent].append(node_id)

    # Older exports carried children explicitly. Merge any extra edges.
    for node_id, node in mapping.items():
        for child_id in node.get('children', []) or []:
            if child_id in mapping and child_id not in children_map[node_id]:
                children_map[node_id].append(child_id)

    def node_time(node_id):
        message = nodes.get(node_id, {}).get('message') or {}
        return message.get('create_time') or 0

    for node_id in children_map:
        children_map[node_id].sort(key=node_time)

    roots = []
    for node_id, node in mapping.items():
        parent = node.get('parent')
        if parent is None or parent not in nodes:
            roots.append(node_id)

    messages = []
    visited = set()

    if not roots:
        timed = []
        for node in mapping.values():
            message = node.get('message')
            if not message:
                continue
            author = message.get('author', {}).get('role', 'unknown')
            text = extract_message_text(message)
            if text and author in ('user', 'assistant', 'tool'):
                timed.append({
                    'role': author,
                    'text': text,
                    'time': message.get('create_time'),
                })
        timed.sort(key=lambda m: m['time'] or 0)
        return timed

    stack = list(reversed(roots))
    while stack:
        node_id = stack.pop()
        if node_id in visited:
            continue
        visited.add(node_id)

        node = nodes.get(node_id)
        if not node:
            continue

        message = node.get('message')
        if message:
            author = message.get('author', {}).get('role', 'unknown')
            text = extract_message_text(message)
            if text and author in ('user', 'assistant', 'tool'):
                messages.append({
                    'role': author,
                    'text': text,
                    'time': message.get('create_time'),
                })

        for child_id in reversed(children_map.get(node_id, [])):
            if child_id not in visited:
                stack.append(child_id)

    return messages


def get_project_id_from_conversation(conv):
    value = conv.get('conversation_template_id')
    if isinstance(value, str) and PROJECT_ID_RE.match(value):
        return value
    return None


def get_project_id_from_library_record(record):
    value = record.get('gizmo_id')
    if isinstance(value, str) and PROJECT_ID_RE.match(value):
        return value
    return None


def conversation_to_markdown(conv):
    """Convert a conversation to Markdown."""
    title = conv.get('title', 'Untitled Conversation')
    create_time = timestamp_to_datetime(conv.get('create_time'))
    update_time = timestamp_to_datetime(conv.get('update_time'))
    project_id = get_project_id_from_conversation(conv)

    lines = [f"# {title}", ""]
    if create_time:
        lines.append(f"**Created:** {create_time.strftime('%Y-%m-%d %H:%M')}")
    if update_time:
        lines.append(f"**Last Updated:** {update_time.strftime('%Y-%m-%d %H:%M')}")
    if project_id:
        lines.append(f"**Project ID:** `{project_id}`")
    lines.extend(["", "---", ""])

    messages = build_message_thread(conv.get('mapping', {}))
    for msg in messages:
        role = msg['role']
        if role == 'user':
            lines.append("## You")
        elif role == 'assistant':
            lines.append("## ChatGPT")
        elif role == 'tool':
            lines.append("## Tool Output")
        else:
            lines.append(f"## {role.title()}")
        lines.extend(["", msg['text'], "", "---", ""])

    return '\n'.join(lines), len(messages)


def get_first_user_message(mapping):
    if not mapping:
        return ''
    for node in mapping.values():
        message = node.get('message')
        if message and message.get('author', {}).get('role') == 'user':
            text = extract_message_text(message)
            if text:
                return text.replace('\n', ' ').strip()[:180]
    return ''


def count_messages(mapping):
    count = 0
    if not mapping:
        return count
    for node in mapping.values():
        message = node.get('message')
        if message and message.get('author', {}).get('role') in ('user', 'assistant'):
            count += 1
    return count


def load_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def find_conversation_files(export_dir):
    single = export_dir / 'conversations.json'
    if single.exists():
        return [single]

    chunks = []
    for path in export_dir.glob('conversations-*.json'):
        match = CONVERSATION_CHUNK_RE.match(path.name)
        if match:
            chunks.append((int(match.group(1)), path))
    chunks.sort(key=lambda item: item[0])
    return [path for _, path in chunks]


def load_conversations(export_dir):
    input_files = find_conversation_files(export_dir)
    conversations = []
    for input_file in input_files:
        data = load_json(input_file, default=[])
        if isinstance(data, list):
            conversations.extend(data)
        else:
            print(f"Warning: skipping unexpected conversation JSON shape: {input_file.name}")
    return conversations, input_files


def load_project_name_overrides(path):
    if not path or not path.exists():
        return {}
    data = load_json(path, default={})
    if not isinstance(data, dict):
        raise ValueError("project names file must contain a JSON object")
    result = {}
    for key, value in data.items():
        if PROJECT_ID_RE.match(str(key)) and isinstance(value, str) and value.strip():
            result[str(key)] = value.strip()
    return result


def discover_projects(conversations, library_records):
    """Discover Project IDs and gather their conversations/library records."""
    projects = {}

    def ensure(project_id):
        if project_id not in projects:
            projects[project_id] = {
                'id': project_id,
                'conversations': [],
                'library_records': [],
            }
        return projects[project_id]

    for conv in conversations:
        project_id = get_project_id_from_conversation(conv)
        if project_id:
            ensure(project_id)['conversations'].append(conv)

    for record in library_records or []:
        project_id = get_project_id_from_library_record(record)
        if project_id:
            ensure(project_id)['library_records'].append(record)

    def project_sort_key(item):
        project_id, data = item
        times = [c.get('create_time') for c in data['conversations'] if c.get('create_time') is not None]
        first = min(times) if times else float('inf')
        if first == float('inf'):
            dates = [iso_to_datetime(r.get('created_at')) for r in data['library_records']]
            dates = [d.timestamp() for d in dates if d]
            first = min(dates) if dates else float('inf')
        return (first, project_id)

    return dict(sorted(projects.items(), key=project_sort_key))


def choose_project_labels(projects, overrides):
    labels = {}
    used = set()
    for index, project_id in enumerate(projects.keys(), start=1):
        requested = overrides.get(project_id)
        if requested:
            base = sanitize_filename(requested, max_length=100)
        else:
            short_id = project_id[:14]
            base = f"Project_{index:02d}_{short_id}"
        candidate = base
        n = 2
        while candidate.lower() in used:
            candidate = f"{base}_{n}"
            n += 1
        used.add(candidate.lower())
        labels[project_id] = candidate
    return labels


def manifest_logical_map(manifest):
    if not isinstance(manifest, dict):
        return {}
    logical = manifest.get('logical_files')
    if isinstance(logical, dict):
        return logical
    # Some JSON parsers/export variants could encode a single dictionary in a list.
    if isinstance(logical, list) and len(logical) == 1 and isinstance(logical[0], dict):
        return logical[0]
    return {}


def resolve_payload_parts(export_dir, manifest, file_id):
    """Resolve physical export file(s) backing a Library file ID."""
    if not file_id:
        return [], False
    logical_name = f"{file_id}.dat"
    logical = manifest_logical_map(manifest)
    entry = logical.get(logical_name)
    if isinstance(entry, dict):
        names = entry.get('files') or []
        parts = [export_dir / str(name) for name in names]
        return parts, bool(entry.get('sharded'))

    fallback = export_dir / logical_name
    if fallback.exists():
        return [fallback], False
    return [], False


def unique_destination(directory, original_name, file_id, used_names):
    name = original_name
    key = name.lower()
    if key not in used_names and not (directory / name).exists():
        used_names.add(key)
        return directory / name

    stem, ext = os.path.splitext(name)
    suffix = (file_id or 'duplicate').replace('file_', '')[-12:]
    candidate = f"{stem}__{suffix}{ext}"
    n = 2
    while candidate.lower() in used_names or (directory / candidate).exists():
        candidate = f"{stem}__{suffix}_{n}{ext}"
        n += 1
    used_names.add(candidate.lower())
    return directory / candidate


def copy_or_reassemble(parts, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if len(parts) == 1:
        shutil.copyfile(parts[0], destination)
        return 'copied'
    with open(destination, 'wb') as out:
        for part in parts:
            with open(part, 'rb') as src:
                shutil.copyfileobj(src, out, length=1024 * 1024)
    return f'reassembled_{len(parts)}_parts'


def selected_library_metadata(record):
    keys = [
        'file_name', 'normalized_name', 'file_id', 'gizmo_id', 'directory_id',
        'state', 'is_visible', 'deleted_at', 'deletion_origin', 'deletion_reason',
        'mime_type', 'file_extension', 'file_size_bytes', 'created_at', 'record_creation_time',
        'file_upload_time', 'modified_at',
        'current_version_number', 'source_version_number', 'origination_thread_id',
        'origination_message_id', 'library_artifact_type', 'library_file_category',
        'version_created_at', 'version_provenance',
    ]
    return {key: record.get(key) for key in keys if key in record}


def restore_library_records(export_dir, files_dir, records, manifest, conversation_lookup=None, enabled=True):
    """Restore arbitrary Library records into ``files_dir`` and return metadata rows."""
    files_dir.mkdir(parents=True, exist_ok=True)
    used_names = set()
    results = []
    conversation_lookup = conversation_lookup or {}

    for record in records:
        meta = selected_library_metadata(record)
        file_id = record.get('file_id')
        original_name = safe_original_filename(record)
        parts, sharded = resolve_payload_parts(export_dir, manifest, file_id)
        existing_parts = [p for p in parts if p.exists() and p.is_file()]

        result = dict(meta)
        result['original_name'] = original_name
        result['manifest_sharded'] = sharded
        result['physical_parts'] = [p.name for p in parts]
        result['restored_name'] = None
        result['origin_conversation_filename'] = conversation_lookup.get(record.get('origination_thread_id'))
        result['restore_status'] = 'not_requested' if not enabled else 'missing_payload'
        result['size_matches_metadata'] = None

        if enabled and parts and len(existing_parts) == len(parts):
            destination = unique_destination(files_dir, original_name, file_id, used_names)
            try:
                result['restore_status'] = copy_or_reassemble(parts, destination)
                result['restored_name'] = destination.name
                expected = record.get('file_size_bytes')
                if isinstance(expected, int):
                    result['size_matches_metadata'] = destination.stat().st_size == expected
                    if not result['size_matches_metadata']:
                        result['restore_status'] += '_SIZE_MISMATCH'
            except OSError as exc:
                result['restore_status'] = f'error: {exc}'
        elif enabled and parts:
            missing = [p.name for p in parts if not p.exists()]
            result['restore_status'] = 'missing_parts: ' + ', '.join(missing)

        results.append(result)

    return results


def restore_project_files(export_dir, project_dir, records, manifest, conversation_lookup=None, enabled=True):
    results = restore_library_records(
        export_dir, project_dir / 'Files', records, manifest,
        conversation_lookup=conversation_lookup, enabled=enabled,
    )
    with open(project_dir / 'library_index.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return results


def normalized_datetime(value):
    '''Return a timezone-naive datetime for display/range comparisons.'''
    if value is None:
        return None
    dt = value if isinstance(value, datetime) else iso_to_datetime(value)
    if not dt:
        return None
    if getattr(dt, 'tzinfo', None) is not None:
        # Artifact ranges are displayed as dates only. Removing tzinfo preserves
        # the exported wall-clock date without introducing host-timezone drift.
        dt = dt.replace(tzinfo=None)
    return dt


def datetime_sort_value(value):
    '''Portable numeric sort key for static HTML data attributes; 0 means unknown.'''
    dt = normalized_datetime(value)
    if not dt:
        return 0
    # Use a calendar-form key rather than datetime.timestamp(). On Windows,
    # pre-epoch datetimes can raise OSError; mixing a timestamp fallback with
    # YYYYMMDDHHMMSS values would put otherwise valid dates in the wrong order.
    # This representation is timezone-independent and remains exactly sortable
    # as a JavaScript Number for normal four-digit calendar years.
    return int(dt.strftime('%Y%m%d%H%M%S'))


def library_display_name(item):
    return str(item.get('file_name') or item.get('normalized_name') or item.get('original_name') or 'Unnamed')


def library_file_type(item):
    ext = str(item.get('file_extension') or '').strip().lower().lstrip('.')
    if not ext:
        ext = Path(library_display_name(item)).suffix.lower().lstrip('.')
    return ('.' + ext) if ext else ''


def library_created_datetime(item):
    for key in ('created_at', 'record_creation_time', 'file_upload_time', 'version_created_at', 'modified_at'):
        dt = normalized_datetime(item.get(key))
        if dt:
            return dt
    return None


def sort_controls(select_id, container_id, item_selector, include_file_type=False):
    options = [
        ('date-desc', 'Newest first'),
        ('date-asc', 'Oldest first'),
        ('name-asc', 'Name A → Z'),
        ('name-desc', 'Name Z → A'),
    ]
    if include_file_type:
        options.append(('type-asc', 'File type A → Z'))
    option_html = ''.join(
        f'<option value="{value}"{" selected" if value == "date-desc" else ""}>{html.escape(label)}</option>'
        for value, label in options
    )
    return (
        '<div class="inline-controls sort-controls"><label><strong>Sort:</strong> '
        f'<select id="{html.escape(select_id, quote=True)}" '
        f'onchange="sortGeneratedList(\'{html.escape(select_id, quote=True)}\',\'{html.escape(container_id, quote=True)}\',\'{html.escape(item_selector, quote=True)}\')">'
        f'{option_html}</select></label></div>'
    )


def sorting_script():
    return r'''
function lexicalCompare(a,b){a=(a||'').toLowerCase();b=(b||'').toLowerCase();return a<b?-1:(a>b?1:0);}
function sortGeneratedList(selectId,containerId,itemSelector){
  const select=document.getElementById(selectId), container=document.getElementById(containerId);
  if(!select||!container)return;
  const mode=select.value;
  const items=Array.from(container.children).filter(x=>x.matches(itemSelector));
  items.sort((a,b)=>{
    let cmp=0;
    if(mode==='date-desc'||mode==='date-asc'){
      const ad=Number(a.dataset.sortDate||0), bd=Number(b.dataset.sortDate||0);
      if(!ad&&!bd)cmp=0; else if(!ad)cmp=1; else if(!bd)cmp=-1; else cmp=ad-bd;
      if(mode==='date-desc')cmp=-cmp;
    } else if(mode==='name-desc') {
      cmp=-lexicalCompare(a.dataset.sortName,b.dataset.sortName);
    } else if(mode==='type-asc') {
      cmp=lexicalCompare(a.dataset.sortType,b.dataset.sortType);
    } else {
      cmp=lexicalCompare(a.dataset.sortName,b.dataset.sortName);
    }
    if(cmp===0)cmp=lexicalCompare(a.dataset.sortName,b.dataset.sortName);
    return cmp;
  });
  items.forEach(x=>container.appendChild(x));
}
'''


def html_page(title, body, extra_script=''):
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)} · v{TOOL_VERSION}</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Ubuntu,sans-serif; max-width: 1180px; margin: 0 auto; padding: 24px; background: #f5f5f5; color: #2d3338; }}
.tool-banner {{ display:flex; flex-wrap:wrap; justify-content:space-between; align-items:baseline; gap:8px 18px; margin-bottom:14px; color:#59636a; font-size:13px; }}
.tool-banner strong {{ color:#2d3338; }}
a {{ color: #087f6a; }}
h1 {{ border-bottom: 3px solid #10a37f; padding-bottom: 10px; }}
h2 {{ margin-top: 32px; }}
.card, .section {{ background: white; border-radius: 9px; padding: 16px 18px; margin: 12px 0; box-shadow: 0 1px 4px rgba(0,0,0,.09); }}
.meta {{ color: #667; font-size: 13px; margin-top: 5px; }}
.preview {{ color: #555; font-size: 14px; margin-top: 7px; }}
.search {{ width: 100%; padding: 11px 14px; border: 1px solid #bbb; border-radius: 7px; font-size: 16px; margin: 10px 0 16px; }}
table {{ width: 100%; border-collapse: collapse; background: white; }}
th, td {{ text-align: left; padding: 9px; border-bottom: 1px solid #e6e6e6; vertical-align: top; }}
th {{ position: sticky; top: 0; background: #eef8f5; z-index: 1; }}
code {{ word-break: break-all; }}
.badge {{ display: inline-block; font-size: 12px; padding: 2px 7px; border-radius: 10px; background: #e8f3f0; margin-left: 5px; }}
.warn {{ background: #fff6dd; padding: 10px 12px; border-radius: 7px; }}
.hidden {{ display:none !important; }}
.small {{ font-size: 12px; color: #666; }}
.tabs {{ display:flex; flex-wrap:wrap; gap:8px; margin:18px 0; }}
.button, button, select {{ font: inherit; border:1px solid #9aa8a4; border-radius:7px; background:white; padding:7px 11px; cursor:pointer; color:#2d3338; }}
.button:hover, button:hover {{ background:#eef8f5; }}
select {{ padding:7px 10px; border-radius:7px; background:white; color:#2d3338; }}
.tab-button.active {{ background:#10a37f; color:white; border-color:#10a37f; }}
.inline-controls {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:8px 0 14px; }}
.project-name-row {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px; }}
.project-name-row a {{ font-size:18px; }}
.filter-chips {{ display:flex; flex-wrap:wrap; gap:7px 13px; margin:10px 0; }}
.filter-chips label {{ display:inline-flex; align-items:center; gap:5px; background:#f7faf9; border:1px solid #dce6e3; border-radius:14px; padding:5px 9px; }}
.stat-grid {{ display:flex; flex-wrap:wrap; gap:14px; }}
.stat-grid > span {{ white-space:nowrap; }}
</style>
</head><body>
<div class="tool-banner"><span><strong>ChatGPT Export Reader + Project Recovery</strong> · v{TOOL_VERSION}</span><a href="{REPOSITORY_URL}" target="_blank" rel="noopener">{REPOSITORY_LABEL}</a></div>
{body}
{extra_script}
</body></html>'''


def conversation_card(c, href):
    title_raw = str(c['title'])
    title = html.escape(title_raw)
    preview = html.escape(c['preview'])
    date = c['date'].strftime('%Y-%m-%d') if c['date'] else 'Unknown date'
    search = html.escape((title_raw + ' ' + c['preview']).lower(), quote=True)
    preview_html = f'<div class="preview">{preview}</div>' if preview else ''
    sort_date = datetime_sort_value(c.get('date'))
    return (f'<div class="card searchable sortable-item" data-search="{search}" '
            f'data-sort-date="{sort_date}" data-sort-name="{html.escape(title_raw.lower(), quote=True)}">'
            f'<a href="{href}"><strong>{title}</strong></a>'
            f'<div class="meta">{date} · {c["message_count"]} messages</div>'
            f'{preview_html}</div>')


def library_row_html(item, root_relative=False):
    restored_href = item.get('root_restored_href') if root_relative else item.get('library_restored_href')
    origin_href = item.get('root_origin_href') if root_relative else item.get('library_origin_href')
    raw_name = library_display_name(item)
    name = html.escape(raw_name)
    name_cell = f'<a href="{restored_href}">{name}</a>' if restored_href else name
    file_id_raw = str(item.get('file_id') or '')
    file_id = html.escape(file_id_raw)
    state_raw = str(item.get('state') or '')
    state = html.escape(state_raw)
    status_raw = str(item.get('restore_status') or '')
    status = html.escape(status_raw)
    size = item.get('file_size_bytes')
    size_text = f"{size:,}" if isinstance(size, int) else ''
    created_raw = str(item.get('created_at') or '')
    created = html.escape(created_raw)
    project_id = item.get('project_id') or ''
    project_label = item.get('project_label') or 'Unassigned'
    file_type = library_file_type(item)
    if project_id:
        project_cell = f'<span class="project-name" data-project-id="{html.escape(project_id, quote=True)}">{html.escape(project_label)}</span>'
    else:
        project_cell = '<span class="small">Unassigned</span>'
    origin_cell = f'<a href="{origin_href}">origin chat</a>' if origin_href else ''
    search_text = f'{raw_name} {file_id_raw} {state_raw} {status_raw} {project_label} {project_id} {file_type}'.lower()
    return (
        f'<tr class="library-row sortable-item" data-project-id="{html.escape(project_id, quote=True)}" '
        f'data-search="{html.escape(search_text, quote=True)}" '
        f'data-sort-date="{datetime_sort_value(library_created_datetime(item))}" '
        f'data-sort-name="{html.escape(raw_name.lower(), quote=True)}" '
        f'data-sort-type="{html.escape(file_type, quote=True)}">'
        f'<td>{name_cell}<div class="small"><code>{file_id}</code></div></td>'
        f'<td>{html.escape(file_type)}</td><td>{project_cell}</td><td>{state}</td><td>{status}</td><td>{size_text}</td><td>{created}</td><td>{origin_cell}</td></tr>'
    )


def project_filter_html(project_summaries):
    items = []
    for p in project_summaries:
        pid = html.escape(p['id'], quote=True)
        label = html.escape(p['label'])
        items.append(
            f'<label><input class="library-project-check" type="checkbox" value="{pid}" checked> '
            f'<span class="project-name" data-project-id="{pid}">{label}</span></label>'
        )
    items.append('<label><input id="library-unassigned-check" type="checkbox" checked> Unassigned</label>')
    return ''.join(items)


def project_name_script(project_summaries, link_prefix='Projects/'):
    defaults = {p['id']: p['label'] for p in project_summaries}
    folders = {p['id']: p['folder'] for p in project_summaries}
    return f'''
const PROJECT_NAME_DEFAULTS={json.dumps(defaults, ensure_ascii=False)};
const PROJECT_FOLDERS={json.dumps(folders, ensure_ascii=False)};
const PROJECT_NAME_KEY='chatgpt-export-reader-project-names-v2';
let PROJECT_NAME_MEMORY={{}};
function readProjectNames(){{
  try {{ const x=JSON.parse(localStorage.getItem(PROJECT_NAME_KEY)||'{{}}'); if(x && typeof x==='object')PROJECT_NAME_MEMORY=Object.assign({{}},PROJECT_NAME_MEMORY,x); }} catch(e) {{}}
  return PROJECT_NAME_MEMORY;
}}
function projectName(id){{ const n=readProjectNames(); return (n[id]||PROJECT_NAME_DEFAULTS[id]||id); }}
function applyProjectNames(){{
  document.querySelectorAll('.project-name[data-project-id]').forEach(el=>{{const name=projectName(el.dataset.projectId);el.textContent=name;const card=el.closest('.project-card');if(card)card.dataset.sortName=name.toLowerCase();}});
  document.querySelectorAll('a[data-project-link]').forEach(a=>{{
    const id=a.dataset.projectId; const base=a.dataset.baseHref;
    a.href=base+'?project_name='+encodeURIComponent(projectName(id));
  }});
}}
function renameProject(id){{
  const current=projectName(id); const next=prompt('Display name for this recovered Project:', current);
  if(next===null) return;
  const clean=next.trim(); if(!clean) return;
  const names=readProjectNames(); names[id]=clean; PROJECT_NAME_MEMORY=names;
  try {{ localStorage.setItem(PROJECT_NAME_KEY,JSON.stringify(names)); }} catch(e) {{}}
  applyProjectNames();
}}
function resetProjectNames(){{
  if(!confirm('Reset browser-local Project display names to the names generated by the recovery tool?')) return;
  PROJECT_NAME_MEMORY={{}}; try {{ localStorage.removeItem(PROJECT_NAME_KEY); }} catch(e) {{}}
  applyProjectNames();
}}
function exportProjectNames(){{
  const names=readProjectNames(); const out={{}};
  Object.keys(PROJECT_NAME_DEFAULTS).forEach(id=>{{out[id]=names[id]||PROJECT_NAME_DEFAULTS[id];}});
  const blob=new Blob([JSON.stringify(out,null,2)+'\\n'],{{type:'application/json'}});
  const url=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url; a.download='project_names.json'; a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}}
applyProjectNames();
'''


def format_display_date(value):
    """Format an ISO YYYY-MM-DD date as an unambiguous human-readable date."""
    if not value:
        return None
    try:
        dt = datetime.strptime(str(value), '%Y-%m-%d')
    except (TypeError, ValueError):
        return str(value)
    return f'{dt.day} {dt.strftime("%B %Y")}'


def generate_root_index(conv_data, project_summaries, library_catalog, output_file):
    project_cards = []
    for p in sorted(project_summaries, key=lambda x: x.get('last_date_sort') or 0, reverse=True):
        pid = html.escape(p['id'], quote=True)
        base_href = f'Projects/{quote(p["folder"])}/INDEX.html'
        date_range = 'date unavailable'
        if p.get('first_date') and p.get('last_date'):
            date_range = f'{format_display_date(p["first_date"])} to {format_display_date(p["last_date"])}'
        project_cards.append(
            f'<div class="card project-card sortable-item" data-sort-date="{p.get("last_date_sort") or 0}" '
            f'data-sort-name="{html.escape(p["label"].lower(), quote=True)}">'
            '<div class="project-name-row">'
            f'<a data-project-link data-project-id="{pid}" data-base-href="{html.escape(base_href, quote=True)}" href="{base_href}">'
            f'<strong class="project-name" data-project-id="{pid}">{html.escape(p["label"])}</strong></a>'
            f'<button type="button" onclick="renameProject(\'{pid}\')">Rename</button>'
            '</div>'
            f'<span class="badge">{p["conversation_count"]} chats</span>'
            f'<span class="badge">{p["library_count"]} library records</span>'
            f'<div class="meta"><strong>Date range:</strong> {html.escape(date_range)}</div>'
            f'<div class="meta"><code>{pid}</code></div>'
            '</div>'
        )

    chat_cards = [conversation_card(c, quote(c['filename'])) for c in sorted(conv_data, key=lambda x: x['date'] or datetime.min, reverse=True)]
    library_sorted = sorted(library_catalog, key=lambda x: datetime_sort_value(library_created_datetime(x)), reverse=True)
    library_rows = [library_row_html(item, root_relative=True) for item in library_sorted]
    project_library_count = sum(1 for x in library_catalog if x.get('project_id'))
    unassigned_count = len(library_catalog) - project_library_count

    body = f'''<h1>ChatGPT Export Archive</h1>
<div class="section stat-grid"><span><strong>Conversations:</strong> {len(conv_data)}</span><span><strong>Projects:</strong> {len(project_summaries)}</span><span><strong>Library records:</strong> {len(library_catalog)}</span></div>
<div class="tabs">
<button class="tab-button active" data-tab="chats" onclick="showTab('chats')">All chats</button>
<button class="tab-button" data-tab="projects" onclick="showTab('projects')">Projects</button>
<button class="tab-button" data-tab="library" onclick="showTab('library')">Library</button>
</div>
<section id="tab-chats" class="tab-panel">
<h2>All conversations</h2>
<input id="chat-search" class="search" placeholder="Search titles and previews...">
{sort_controls('chat-sort', 'chat-list', '.sortable-item')}
<div id="chat-list">{''.join(chat_cards)}</div>
</section>
<section id="tab-projects" class="tab-panel hidden">
<h2>Projects</h2>
<div class="section">
<p>Project names are not always included in ChatGPT exports. Rename changes the display name in this browser without renaming recovered folders.</p>
<div class="inline-controls"><button type="button" onclick="exportProjectNames()">Export project_names.json</button><button type="button" onclick="resetProjectNames()">Reset display names</button></div>
<p class="small">Exporting names creates a mapping that can be saved beside the ChatGPT export and used on the next recovery run for permanent generated labels/folders.</p>
</div>
{sort_controls('project-sort', 'project-list', '.sortable-item')}
<div id="project-list">{''.join(project_cards) if project_cards else '<div class="warn">No Project IDs were detected.</div>'}</div>
</section>
<section id="tab-library" class="tab-panel hidden">
<h2>Library</h2>
<div class="section stat-grid"><span><strong>All:</strong> {len(library_catalog)}</span><span><strong>Project-associated:</strong> {project_library_count}</span><span><strong>Unassigned:</strong> {unassigned_count}</span></div>
<input id="library-search" class="search" placeholder="Search file names, file IDs, Project names, states, or recovery status...">
<div class="section">
<div class="inline-controls"><strong>Selection:</strong><button type="button" onclick="setLibraryScope('all')">All</button><button type="button" onclick="setLibraryScope('projects')">All Projects</button><button type="button" onclick="setLibraryScope('unassigned')">Unassigned</button><button type="button" onclick="setLibraryScope('none')">Clear</button><span id="library-visible-count" class="small"></span></div>
<div class="filter-chips">{project_filter_html(project_summaries)}</div>
</div>
{sort_controls('library-sort', 'library-list', '.sortable-item', include_file_type=True)}
<p class="small">Project-associated files link to their recovered Project folders. Files without a Project association are restored under <a href="Library/INDEX.html">Library/Files</a> where payloads are available. Full metadata is in <a href="Library/library_index.json">Library/library_index.json</a>.</p>
<div style="overflow:auto"><table><thead><tr><th>File</th><th>Type</th><th>Project</th><th>State</th><th>Recovery</th><th>Bytes</th><th>Created</th><th>Origin</th></tr></thead><tbody id="library-list">{''.join(library_rows)}</tbody></table></div>
</section>
'''
    script = '''<script>
''' + sorting_script() + '''
function showTab(name){
  document.querySelectorAll('.tab-panel').forEach(x=>x.classList.toggle('hidden',x.id!=='tab-'+name));
  document.querySelectorAll('.tab-button').forEach(x=>x.classList.toggle('active',x.dataset.tab===name));
  location.hash=name;
}
const initial=(location.hash||'#chats').slice(1); if(['chats','projects','library'].includes(initial)) showTab(initial);
const chatBox=document.getElementById('chat-search');
chatBox.addEventListener('input',()=>{const q=chatBox.value.toLowerCase().trim(); document.querySelectorAll('#tab-chats .searchable').forEach(x=>x.classList.toggle('hidden',q&&!x.dataset.search.includes(q)));});
function selectedLibraryIds(){return new Set(Array.from(document.querySelectorAll('.library-project-check:checked')).map(x=>x.value));}
function applyLibraryFilters(){
  const q=document.getElementById('library-search').value.toLowerCase().trim(); const ids=selectedLibraryIds();
  const unassigned=document.getElementById('library-unassigned-check').checked; let visible=0;
  document.querySelectorAll('.library-row').forEach(row=>{
    const pid=row.dataset.projectId||''; const scope=pid ? ids.has(pid) : unassigned; const search=!q||(row.dataset.search||'').includes(q);
    const show=scope&&search; row.classList.toggle('hidden',!show); if(show)visible++;
  });
  document.getElementById('library-visible-count').textContent=visible+' shown';
}
function setLibraryScope(mode){
  document.querySelectorAll('.library-project-check').forEach(x=>x.checked=(mode==='all'||mode==='projects'));
  document.getElementById('library-unassigned-check').checked=(mode==='all'||mode==='unassigned');
  if(mode==='none'){document.querySelectorAll('.library-project-check').forEach(x=>x.checked=false);document.getElementById('library-unassigned-check').checked=false;}
  applyLibraryFilters();
}
document.getElementById('library-search').addEventListener('input',applyLibraryFilters);
document.querySelectorAll('.library-project-check,#library-unassigned-check').forEach(x=>x.addEventListener('change',applyLibraryFilters));
''' + project_name_script(project_summaries) + '''
sortGeneratedList('chat-sort','chat-list','.sortable-item');
sortGeneratedList('project-sort','project-list','.sortable-item');
sortGeneratedList('library-sort','library-list','.sortable-item');
applyLibraryFilters();
</script>'''
    output_file.write_text(html_page('ChatGPT Export Archive', body, script), encoding='utf-8')


def generate_project_index(project, label, conv_entries, library_results, project_dir):
    conv_cards = [conversation_card(c, '../../' + quote(c['filename'])) for c in sorted(conv_entries, key=lambda x: x['date'] or datetime.min, reverse=True)]
    rows = []
    for item in sorted(library_results, key=lambda x: datetime_sort_value(library_created_datetime(x)), reverse=True):
        restored = item.get('restored_name')
        raw_name = library_display_name(item)
        name = html.escape(raw_name)
        name_cell = f'<a href="Files/{quote(restored)}">{name}</a>' if restored else name
        status = html.escape(str(item.get('restore_status') or ''))
        state = html.escape(str(item.get('state') or ''))
        size = item.get('file_size_bytes'); size_text = f"{size:,}" if isinstance(size, int) else ''
        created = html.escape(str(item.get('created_at') or ''))
        file_id = html.escape(str(item.get('file_id') or ''))
        file_type = library_file_type(item)
        origin_file = item.get('origin_conversation_filename')
        origin_cell = f'<a href="../../{quote(origin_file)}">origin chat</a>' if origin_file else ''
        search = html.escape(f'{raw_name} {file_id} {state} {status} {file_type}'.lower(), quote=True)
        rows.append(
            f'<tr class="file-row sortable-item" data-search="{search}" '
            f'data-sort-date="{datetime_sort_value(library_created_datetime(item))}" '
            f'data-sort-name="{html.escape(raw_name.lower(), quote=True)}" '
            f'data-sort-type="{html.escape(file_type, quote=True)}">'
            f'<td>{name_cell}<div class="small"><code>{file_id}</code></div></td><td>{html.escape(file_type)}</td>'
            f'<td>{state}</td><td>{status}</td><td>{size_text}</td><td>{created}</td><td>{origin_cell}</td></tr>'
        )

    pid = html.escape(project['id'], quote=True)
    first_date, last_date = project_date_range(project)
    if first_date and last_date:
        date_range = f'{first_date.day} {first_date.strftime("%B %Y")} to {last_date.day} {last_date.strftime("%B %Y")}'
    else:
        date_range = 'date unavailable'
    body = f'''<p><a href="../../INDEX.html#projects">← Projects</a> · <a href="../../INDEX.html#library">Library</a> · <a href="../../INDEX.html#chats">All chats</a></p>
<h1 id="project-title" class="project-name" data-project-id="{pid}">{html.escape(label)}</h1>
<div class="section"><div><strong>Project ID:</strong> <code>{pid}</code></div>
<div><strong>Date range:</strong> {html.escape(date_range)}</div>
<div><strong>Conversations:</strong> {len(conv_entries)} · <strong>Library records:</strong> {len(library_results)}</div></div>
<h2>Conversations</h2>
<input id="conv-search" class="search" placeholder="Search project conversation titles and previews...">
{sort_controls('conv-sort', 'conv-list', '.sortable-item')}
<div id="conv-list">{''.join(conv_cards) if conv_cards else '<div class="warn">No conversation objects for this Project ID were present in the export.</div>'}</div>
<h2>Project Library</h2>
<p class="small">Files are restored from exported <code>.dat</code> payloads where available. Metadata is preserved in <a href="library_index.json">library_index.json</a>.</p>
<input id="file-search" class="search" placeholder="Search project file names, IDs, or state...">
{sort_controls('file-sort', 'file-list', '.sortable-item', include_file_type=True)}
<div style="overflow:auto"><table><thead><tr><th>File</th><th>Type</th><th>State</th><th>Recovery</th><th>Bytes</th><th>Created</th><th>Origin</th></tr></thead><tbody id="file-list">{''.join(rows)}</tbody></table></div>
'''
    script = '''<script>
''' + sorting_script() + '''
function wire(id, selector){const box=document.getElementById(id);if(!box)return;box.addEventListener('input',()=>{const q=box.value.toLowerCase().trim();document.querySelectorAll(selector).forEach(x=>x.classList.toggle('hidden',q&&!(x.dataset.search||'').includes(q)));});}
wire('conv-search','.searchable'); wire('file-search','.file-row');
sortGeneratedList('conv-sort','conv-list','.sortable-item'); sortGeneratedList('file-sort','file-list','.sortable-item');
const qn=new URLSearchParams(location.search).get('project_name'); if(qn)document.getElementById('project-title').textContent=qn;
</script>'''
    (project_dir / 'INDEX.html').write_text(html_page(label, body, script), encoding='utf-8')


def generate_projects_index(project_summaries, projects_dir):
    cards=[]
    for p in sorted(project_summaries, key=lambda x: x.get('last_date_sort') or 0, reverse=True):
        date_text = 'date unavailable'
        if p.get('first_date') and p.get('last_date'):
            date_text = f'{format_display_date(p["first_date"])} to {format_display_date(p["last_date"])}'
        pid=html.escape(p['id'],quote=True); base=f'{quote(p["folder"])}/INDEX.html'
        cards.append(
            f'<div class="card project-card sortable-item" data-sort-date="{p.get("last_date_sort") or 0}" data-sort-name="{html.escape(p["label"].lower(), quote=True)}">'
            '<div class="project-name-row">'
            f'<a data-project-link data-project-id="{pid}" data-base-href="{html.escape(base,quote=True)}" href="{base}"><strong class="project-name" data-project-id="{pid}">{html.escape(p["label"])}</strong></a>'
            f'<button type="button" onclick="renameProject(\'{pid}\')">Rename</button></div>'
            f'<div class="meta"><code>{pid}</code></div>'
            f'<div>{p["conversation_count"]} conversations · {p["library_count"]} library records · {p["recovered_count"]} payloads restored</div>'
            f'<div class="meta"><strong>Date range:</strong> {html.escape(date_text)}</div></div>'
        )
    body=f'''<p><a href="../INDEX.html#projects">← Main archive</a></p><h1>Recovered Projects</h1>
<div class="section"><div class="inline-controls"><button type="button" onclick="exportProjectNames()">Export project_names.json</button><button type="button" onclick="resetProjectNames()">Reset display names</button></div><p class="small">Renames here are browser-local display names. Export the mapping and rerun the converter to make them part of the generated archive.</p></div>
{sort_controls('projects-sort', 'projects-list', '.sortable-item')}
<div id="projects-list">{''.join(cards) if cards else '<div class="warn">No Project IDs were detected.</div>'}</div>'''
    script='<script>'+sorting_script()+project_name_script(project_summaries, link_prefix='')+"sortGeneratedList('projects-sort','projects-list','.sortable-item');</script>"
    (projects_dir/'INDEX.html').write_text(html_page('Recovered Projects',body,script),encoding='utf-8')


def generate_library_index(library_catalog, project_summaries, library_dir):
    rows=[library_row_html(item,root_relative=False) for item in sorted(library_catalog,key=lambda x:datetime_sort_value(library_created_datetime(x)), reverse=True)]
    project_count=sum(1 for x in library_catalog if x.get('project_id')); unassigned=len(library_catalog)-project_count
    body=f'''<p><a href="../INDEX.html#library">← Main archive</a></p><h1>Recovered Library</h1>
<div class="section stat-grid"><span><strong>All:</strong> {len(library_catalog)}</span><span><strong>Project-associated:</strong> {project_count}</span><span><strong>Unassigned:</strong> {unassigned}</span></div>
<input id="library-search" class="search" placeholder="Search file names, IDs, Project names, states, or recovery status...">
<div class="section"><div class="inline-controls"><strong>Selection:</strong><button onclick="setLibraryScope('all')">All</button><button onclick="setLibraryScope('projects')">All Projects</button><button onclick="setLibraryScope('unassigned')">Unassigned</button><button onclick="setLibraryScope('none')">Clear</button><span id="library-visible-count" class="small"></span></div><div class="filter-chips">{project_filter_html(project_summaries)}</div></div>
{sort_controls('library-sort', 'library-list', '.sortable-item', include_file_type=True)}
<div style="overflow:auto"><table><thead><tr><th>File</th><th>Type</th><th>Project</th><th>State</th><th>Recovery</th><th>Bytes</th><th>Created</th><th>Origin</th></tr></thead><tbody id="library-list">{''.join(rows)}</tbody></table></div>'''
    script='''<script>
''' + sorting_script() + '''
function selectedLibraryIds(){return new Set(Array.from(document.querySelectorAll('.library-project-check:checked')).map(x=>x.value));}
function applyLibraryFilters(){const q=document.getElementById('library-search').value.toLowerCase().trim();const ids=selectedLibraryIds();const unassigned=document.getElementById('library-unassigned-check').checked;let visible=0;document.querySelectorAll('.library-row').forEach(row=>{const pid=row.dataset.projectId||'';const scope=pid?ids.has(pid):unassigned;const search=!q||(row.dataset.search||'').includes(q);const show=scope&&search;row.classList.toggle('hidden',!show);if(show)visible++;});document.getElementById('library-visible-count').textContent=visible+' shown';}
function setLibraryScope(mode){document.querySelectorAll('.library-project-check').forEach(x=>x.checked=(mode==='all'||mode==='projects'));document.getElementById('library-unassigned-check').checked=(mode==='all'||mode==='unassigned');if(mode==='none'){document.querySelectorAll('.library-project-check').forEach(x=>x.checked=false);document.getElementById('library-unassigned-check').checked=false;}applyLibraryFilters();}
document.getElementById('library-search').addEventListener('input',applyLibraryFilters);document.querySelectorAll('.library-project-check,#library-unassigned-check').forEach(x=>x.addEventListener('change',applyLibraryFilters));
''' + project_name_script(project_summaries) + '''sortGeneratedList('library-sort','library-list','.sortable-item');applyLibraryFilters();</script>'''
    (library_dir/'INDEX.html').write_text(html_page('Recovered Library',body,script),encoding='utf-8')


def build_conversation_entries(conversations, output_dir):
    entries = []
    filenames_used = set()
    empty_count = 0

    for i, conv in enumerate(conversations):
        title = conv.get('title', 'Untitled')
        create_time = timestamp_to_datetime(conv.get('create_time'))
        date_prefix = create_time.strftime('%Y%m%d') if create_time else '00000000'
        safe_title = sanitize_filename(title, max_length=60)
        filename = f"{date_prefix}_{safe_title}.md"
        counter = 1
        while filename.lower() in filenames_used:
            filename = f"{date_prefix}_{safe_title}_{counter}.md"
            counter += 1
        filenames_used.add(filename.lower())

        markdown, rendered_count = conversation_to_markdown(conv)
        if rendered_count == 0 and conv.get('mapping'):
            empty_count += 1
        (output_dir / filename).write_text(markdown, encoding='utf-8')

        entries.append({
            'conversation': conv,
            'conversation_id': conv.get('id') or conv.get('conversation_id'),
            'project_id': get_project_id_from_conversation(conv),
            'title': title,
            'date': create_time,
            'filename': filename,
            'preview': get_first_user_message(conv.get('mapping', {})),
            'message_count': count_messages(conv.get('mapping', {})),
        })

        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1}/{len(conversations)} conversations...")

    return entries, empty_count


def write_project_name_template(projects, output_dir):
    template = {project_id: "" for project_id in projects.keys()}
    path = output_dir / 'project_names.example.json'
    path.write_text(json.dumps(template, indent=2), encoding='utf-8')


def project_date_range(project):
    """Oldest-to-newest creation dates across chats and Library artifacts."""
    dates = [normalized_datetime(timestamp_to_datetime(c.get('create_time'))) for c in project['conversations']]
    dates.extend(library_created_datetime(r) for r in project['library_records'])
    dates = [d for d in dates if d]
    if not dates:
        return None, None
    return min(dates), max(dates)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Convert ChatGPT exports to readable Markdown/HTML and recover Projects.')
    parser.add_argument('export_dir', nargs='?', default='.', help='Unzipped ChatGPT export directory (default: current directory)')
    parser.add_argument('--output', help='Output directory (default: <export_dir>/conversations)')
    parser.add_argument('--project-names', help='Optional JSON mapping of g-p-* Project IDs to display names')
    parser.add_argument('--no-project-files', '--no-library-files', dest='no_project_files', action='store_true', help='Build indexes but do not copy/reassemble Library payloads')
    return parser.parse_args(argv)


def run(export_dir, output_dir, project_names_path=None, restore_files=True):
    export_dir = Path(export_dir).resolve()
    output_dir = Path(output_dir).resolve()

    conversations, input_files = load_conversations(export_dir)
    if not input_files:
        raise FileNotFoundError('No conversations.json or conversations-*.json files found')

    library_path = export_dir / 'library_files.json'
    manifest_path = export_dir / 'export_manifest.json'
    library_records = load_json(library_path, default=[])
    if not isinstance(library_records, list):
        library_records = []
    manifest = load_json(manifest_path, default={})
    if not isinstance(manifest, dict):
        manifest = {}

    if project_names_path:
        overrides_path = Path(project_names_path)
        if not overrides_path.is_absolute():
            overrides_path = Path.cwd() / overrides_path
    else:
        candidate = export_dir / 'project_names.json'
        overrides_path = candidate if candidate.exists() else None
    overrides = load_project_name_overrides(overrides_path) if overrides_path else {}

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Found {len(conversations)} conversations in {len(input_files)} conversation file(s)")
    if library_records:
        print(f"Found {len(library_records)} Library metadata records")

    print("\nConverting conversations...")
    conv_entries, empty_count = build_conversation_entries(conversations, output_dir)

    projects = discover_projects(conversations, library_records)
    labels = choose_project_labels(projects, overrides)
    projects_dir = output_dir / 'Projects'
    projects_dir.mkdir(exist_ok=True)
    write_project_name_template(projects, output_dir)

    entries_by_project = defaultdict(list)
    for entry in conv_entries:
        if entry['project_id']:
            entries_by_project[entry['project_id']].append(entry)

    conversation_lookup = {entry['conversation_id']: entry['filename'] for entry in conv_entries if entry.get('conversation_id')}

    project_summaries = []
    project_results_by_id = {}
    print(f"\nDiscovered {len(projects)} Project ID(s)")
    for project_id, project in projects.items():
        label = labels[project_id]
        project_dir = projects_dir / label
        project_dir.mkdir(parents=True, exist_ok=True)

        library_results = restore_project_files(
            export_dir, project_dir, project['library_records'], manifest, conversation_lookup=conversation_lookup, enabled=restore_files
        )
        project_results_by_id[project_id] = library_results
        generate_project_index(project, label, entries_by_project[project_id], library_results, project_dir)

        first_date, last_date = project_date_range(project)
        recovered_count = sum(1 for r in library_results if str(r.get('restore_status', '')).startswith(('copied', 'reassembled')))
        missing_count = sum(1 for r in library_results if str(r.get('restore_status', '')).startswith(('missing', 'error')))
        project_summaries.append({
            'id': project_id,
            'label': label,
            'folder': label,
            'conversation_count': len(entries_by_project[project_id]),
            'library_count': len(library_results),
            'recovered_count': recovered_count,
            'missing_count': missing_count,
            'first_date': first_date.strftime('%Y-%m-%d') if first_date else None,
            'last_date': last_date.strftime('%Y-%m-%d') if last_date else None,
            'first_date_sort': datetime_sort_value(first_date),
            'last_date_sort': datetime_sort_value(last_date),
        })
        print(f"  {label}: {len(entries_by_project[project_id])} chats, {len(library_results)} Library records, {recovered_count} payloads restored")

    generate_projects_index(project_summaries, projects_dir)

    # Recover Library records that are not associated with a g-p-* Project,
    # then build one catalog spanning Project and non-Project Library files.
    library_dir = output_dir / 'Library'
    library_dir.mkdir(exist_ok=True)
    unassigned_records = [r for r in library_records if not get_project_id_from_library_record(r)]
    unassigned_results = restore_library_records(
        export_dir, library_dir / 'Files', unassigned_records, manifest,
        conversation_lookup=conversation_lookup, enabled=restore_files,
    )

    summaries_by_id = {p['id']: p for p in project_summaries}
    library_catalog = []
    for project_id, rows in project_results_by_id.items():
        summary = summaries_by_id[project_id]
        for row in rows:
            item = dict(row)
            item['project_id'] = project_id
            item['project_label'] = summary['label']
            restored = item.get('restored_name')
            if restored:
                item['root_restored_href'] = f"Projects/{quote(summary['folder'])}/Files/{quote(restored)}"
                item['library_restored_href'] = f"../Projects/{quote(summary['folder'])}/Files/{quote(restored)}"
            else:
                item['root_restored_href'] = None
                item['library_restored_href'] = None
            origin = item.get('origin_conversation_filename')
            item['root_origin_href'] = quote(origin) if origin else None
            item['library_origin_href'] = f"../{quote(origin)}" if origin else None
            library_catalog.append(item)

    for row in unassigned_results:
        item = dict(row)
        item['project_id'] = None
        item['project_label'] = None
        restored = item.get('restored_name')
        if restored:
            item['root_restored_href'] = f"Library/Files/{quote(restored)}"
            item['library_restored_href'] = f"Files/{quote(restored)}"
        else:
            item['root_restored_href'] = None
            item['library_restored_href'] = None
        origin = item.get('origin_conversation_filename')
        item['root_origin_href'] = quote(origin) if origin else None
        item['library_origin_href'] = f"../{quote(origin)}" if origin else None
        library_catalog.append(item)

    (library_dir / 'library_index.json').write_text(
        json.dumps(library_catalog, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    generate_library_index(library_catalog, project_summaries, library_dir)
    generate_root_index(conv_entries, project_summaries, library_catalog, output_dir / 'INDEX.html')

    report = {
        'format': 'chatgpt-export-reader-project-recovery-report-v3',
        'conversation_files': [p.name for p in input_files],
        'conversation_count': len(conversations),
        'library_files_present': library_path.exists(),
        'library_record_count': len(library_records),
        'export_manifest_present': manifest_path.exists(),
        'library_recovery': {
            'project_associated_records': sum(1 for x in library_catalog if x.get('project_id')),
            'unassigned_records': sum(1 for x in library_catalog if not x.get('project_id')),
            'recovered_payloads': sum(1 for x in library_catalog if str(x.get('restore_status', '')).startswith(('copied', 'reassembled'))),
        },
        'project_detection': {
            'conversation_field': 'conversation_template_id',
            'library_field': 'gizmo_id',
            'project_id_pattern': 'g-p-*',
            'project_count': len(projects),
        },
        'projects': project_summaries,
        'warnings': [],
    }
    conversation_project_ids = {get_project_id_from_conversation(c) for c in conversations}
    conversation_project_ids.discard(None)
    library_project_ids = {get_project_id_from_library_record(r) for r in library_records}
    library_project_ids.discard(None)
    only_conversations = sorted(conversation_project_ids - library_project_ids)
    only_library = sorted(library_project_ids - conversation_project_ids)
    if only_conversations:
        report['warnings'].append({'project_ids_with_conversations_but_no_library_records': only_conversations})
    if only_library:
        report['warnings'].append({'project_ids_with_library_records_but_no_conversations': only_library})
    if empty_count:
        report['warnings'].append({'conversations_with_mapping_but_no_rendered_messages': empty_count})

    (output_dir / 'recovery_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main(argv=None):
    args = parse_args(argv)
    export_dir = Path(args.export_dir)
    output_dir = Path(args.output) if args.output else export_dir / 'conversations'

    print()
    print('=' * 68)
    print(f'  ChatGPT Export Reader + Project Recovery v{TOOL_VERSION}')
    print('=' * 68)
    print(f"  Export: {export_dir.resolve()}")
    print(f"  Output: {output_dir.resolve()}")
    print()

    try:
        report = run(
            export_dir=export_dir,
            output_dir=output_dir,
            project_names_path=args.project_names,
            restore_files=not args.no_project_files,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print()
    print('=' * 68)
    print('  Done')
    print('=' * 68)
    print(f"  Conversations exported: {report['conversation_count']}")
    print(f"  Projects discovered: {report['project_detection']['project_count']}")
    index_path = output_dir / 'INDEX.html'
    print(f"  Web interface: {index_path}")
    print('  Open INDEX.html in your browser to browse chats, Projects, and Library files.')
    print(f'  Tool repository: {REPOSITORY_URL}')
    print(f"  Recovered Library directory: {output_dir / 'Library'}")
    print()
    if report['project_detection']['project_count']:
        print('  Project names are not always present in ChatGPT exports.')
        print('  You can rename Projects directly in the INDEX.html web interface.')
        print('  Use "Export project_names.json" there to save those names for a future rerun,')
        print('  or copy/edit project_names.example.json as project_names.json beside the export.')
        print()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
