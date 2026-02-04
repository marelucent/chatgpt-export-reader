#!/usr/bin/env python3
"""
ChatGPT Export Reader
Converts your ChatGPT data export into readable, searchable conversations.

Usage:
    1. Export your data from ChatGPT (Settings > Data Controls > Export)
    2. Unzip and find conversations.json
    3. Put this script in the same folder as conversations.json
    4. Run: python convert.py
    5. Open conversations/INDEX.html in your browser
"""

import json
import os
import re
import html
from datetime import datetime
from pathlib import Path
from collections import defaultdict


def sanitize_filename(title, max_length=50):
    """Create a safe filename from a conversation title."""
    if not title:
        title = "Untitled"
    safe = re.sub(r'[<>:"/\\|?*]', '', title)
    safe = re.sub(r'\s+', ' ', safe).strip()
    if len(safe) > max_length:
        safe = safe[:max_length].rsplit(' ', 1)[0]
    return safe or "Untitled"


def timestamp_to_datetime(ts):
    """Convert Unix timestamp to datetime."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts)
    except:
        return None


def extract_message_text(message):
    """Extract readable text from a message object."""
    if not message or 'content' not in message:
        return None

    content = message['content']
    content_type = content.get('content_type', '')

    if content_type in ('text', 'multimodal_text'):
        parts = content.get('parts', [])
        text_parts = []
        for part in parts:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                if part.get('content_type') == 'image_asset_pointer':
                    text_parts.append('[Image]')
                elif 'text' in part:
                    text_parts.append(part['text'])
        return '\n'.join(text_parts) if text_parts else None

    elif content_type == 'code':
        return f"```\n{content.get('text', '')}\n```"

    return None


def build_message_thread(mapping):
    """Build an ordered list of messages from the mapping structure."""
    if not mapping:
        return []

    children_map = defaultdict(list)
    nodes = {}

    for node_id, node in mapping.items():
        nodes[node_id] = node
        parent = node.get('parent')
        if parent:
            children_map[parent].append(node_id)

    # Find the root
    root = None
    for node_id, node in mapping.items():
        if node.get('parent') is None:
            root = node_id
            break

    if not root:
        return []

    messages = []
    visited = set()

    def traverse(node_id):
        if node_id in visited:
            return
        visited.add(node_id)

        node = nodes.get(node_id)
        if not node:
            return

        message = node.get('message')
        if message:
            author = message.get('author', {}).get('role', 'unknown')
            text = extract_message_text(message)
            create_time = message.get('create_time')

            if text and author in ('user', 'assistant', 'tool'):
                messages.append({
                    'role': author,
                    'text': text,
                    'time': create_time
                })

        children = node.get('children', [])
        for child_id in children:
            traverse(child_id)

    traverse(root)
    return messages


def conversation_to_markdown(conv):
    """Convert a conversation to Markdown format."""
    title = conv.get('title', 'Untitled Conversation')
    create_time = timestamp_to_datetime(conv.get('create_time'))
    update_time = timestamp_to_datetime(conv.get('update_time'))

    lines = []
    lines.append(f"# {title}")
    lines.append("")

    if create_time:
        lines.append(f"**Created:** {create_time.strftime('%Y-%m-%d %H:%M')}")
    if update_time:
        lines.append(f"**Last Updated:** {update_time.strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    messages = build_message_thread(conv.get('mapping', {}))

    for msg in messages:
        role = msg['role']
        text = msg['text']

        if role == 'user':
            lines.append("## You")
        elif role == 'assistant':
            lines.append("## ChatGPT")
        elif role == 'tool':
            lines.append("## Tool Output")
        else:
            lines.append(f"## {role.title()}")

        lines.append("")
        lines.append(text)
        lines.append("")
        lines.append("---")
        lines.append("")

    return '\n'.join(lines)


def get_first_user_message(mapping):
    """Get the first user message as a preview."""
    if not mapping:
        return ''
    for node_id, node in mapping.items():
        message = node.get('message')
        if message and message.get('author', {}).get('role') == 'user':
            text = extract_message_text(message)
            if text:
                return text.replace('\n', ' ').strip()[:150]
    return ''


def count_messages(mapping):
    """Count user and assistant messages."""
    count = 0
    if not mapping:
        return 0
    for node_id, node in mapping.items():
        message = node.get('message')
        if message:
            role = message.get('author', {}).get('role', '')
            if role in ('user', 'assistant'):
                count += 1
    return count


def escape_html(s):
    """Escape HTML special characters."""
    return html.escape(s) if s else ''


def escape_js_string(s):
    """Escape a string for use in JavaScript/HTML attributes."""
    if not s:
        return ''
    return s.replace('\\', '\\\\').replace('"', '&quot;').replace('\n', ' ').replace('\r', '').replace('<', '&lt;').replace('>', '&gt;')


def generate_html_index(conv_data, output_file):
    """Generate the searchable HTML index."""
    by_month = defaultdict(list)
    for c in conv_data:
        by_month[c['month']].append(c)

    for month in by_month:
        by_month[month].sort(key=lambda x: x['date'] or datetime.min, reverse=True)

    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My ChatGPT Conversations</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
            color: #333;
        }}
        h1 {{
            color: #10a37f;
            border-bottom: 3px solid #10a37f;
            padding-bottom: 10px;
        }}
        .stats {{
            background: #fff;
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .search-box {{
            width: 100%;
            padding: 12px 16px;
            font-size: 16px;
            border: 2px solid #ddd;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .search-box:focus {{
            outline: none;
            border-color: #10a37f;
        }}
        .month-section {{
            background: #fff;
            border-radius: 8px;
            margin-bottom: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .month-header {{
            background: #10a37f;
            color: white;
            padding: 12px 20px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .month-header:hover {{ background: #0d8a6a; }}
        .month-header .count {{
            background: rgba(255,255,255,0.2);
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 14px;
        }}
        .month-header .toggle {{ font-size: 14px; }}
        .month-content {{ padding: 0; }}
        .month-content.collapsed {{ display: none; }}
        .conversation {{
            padding: 15px 20px;
            border-bottom: 1px solid #eee;
            transition: background 0.2s;
        }}
        .conversation:last-child {{ border-bottom: none; }}
        .conversation:hover {{ background: #f9f9f9; }}
        .conversation a {{
            color: #10a37f;
            text-decoration: none;
            font-weight: 600;
            font-size: 16px;
        }}
        .conversation a:hover {{ text-decoration: underline; }}
        .conversation .meta {{
            color: #888;
            font-size: 13px;
            margin-top: 4px;
        }}
        .conversation .preview {{
            color: #666;
            font-size: 14px;
            margin-top: 8px;
            font-style: italic;
            line-height: 1.4;
        }}
        .hidden {{ display: none; }}
        .no-results {{
            text-align: center;
            padding: 40px;
            color: #888;
            font-size: 18px;
            background: #fff;
            border-radius: 8px;
        }}
    </style>
</head>
<body>
    <h1>My ChatGPT Conversations</h1>
    <div class="stats">
        <strong>Total Conversations:</strong> {len(conv_data)} |
        <strong>Showing:</strong> <span id="showing-count">{len(conv_data)}</span>
    </div>

    <input type="text" class="search-box" id="search" placeholder="Search conversations by title or content...">

    <div id="conversations-container">
'''

    for month in sorted(by_month.keys(), reverse=True):
        convs = by_month[month]
        if month != 'Unknown':
            try:
                month_display = datetime.strptime(month, '%Y-%m').strftime('%B %Y')
            except:
                month_display = month
        else:
            month_display = 'Unknown Date'

        html_content += f'''        <div class="month-section" data-month="{month}">
            <div class="month-header" onclick="toggleMonth(this)">
                <span>{month_display}</span>
                <span><span class="count">{len(convs)} conversations</span> <span class="toggle">▼</span></span>
            </div>
            <div class="month-content">
'''
        for c in convs:
            date_str = c['date'].strftime('%Y-%m-%d') if c['date'] else 'Unknown'
            title_escaped = escape_html(c['title'])
            preview_escaped = escape_html(c['preview'])
            title_search = escape_js_string(c['title'].lower())
            preview_search = escape_js_string(c['preview'].lower())

            html_content += f'''                <div class="conversation" data-title="{title_search}" data-preview="{preview_search}">
                    <a href="{c['filename']}">{title_escaped}</a>
                    <div class="meta">{date_str} &bull; {c['message_count']} messages</div>
'''
            if preview_escaped:
                html_content += f'''                    <div class="preview">"{preview_escaped}..."</div>
'''
            html_content += '''                </div>
'''

        html_content += '''            </div>
        </div>
'''

    html_content += '''    </div>
    <div id="no-results" class="no-results hidden">No conversations found matching your search.</div>

    <script>
        function toggleMonth(header) {
            const content = header.nextElementSibling;
            const toggle = header.querySelector('.toggle');
            content.classList.toggle('collapsed');
            toggle.textContent = content.classList.contains('collapsed') ? '►' : '▼';
        }

        const searchBox = document.getElementById('search');
        const noResults = document.getElementById('no-results');
        const showingCount = document.getElementById('showing-count');

        searchBox.addEventListener('input', function() {
            const query = this.value.toLowerCase().trim();
            let visibleCount = 0;

            document.querySelectorAll('.month-section').forEach(section => {
                let monthVisible = false;
                section.querySelectorAll('.conversation').forEach(conv => {
                    const title = conv.dataset.title || '';
                    const preview = conv.dataset.preview || '';
                    const matches = !query || title.includes(query) || preview.includes(query);
                    conv.classList.toggle('hidden', !matches);
                    if (matches) {
                        monthVisible = true;
                        visibleCount++;
                    }
                });
                section.classList.toggle('hidden', !monthVisible);

                if (query && monthVisible) {
                    section.querySelector('.month-content').classList.remove('collapsed');
                    section.querySelector('.toggle').textContent = '▼';
                }
            });

            showingCount.textContent = visibleCount;
            noResults.classList.toggle('hidden', visibleCount > 0);
        });
    </script>
</body>
</html>
'''

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)


def main():
    script_dir = Path(__file__).parent
    input_file = script_dir / 'conversations.json'
    output_dir = script_dir / 'conversations'

    if not input_file.exists():
        print("=" * 60)
        print("ERROR: conversations.json not found!")
        print("=" * 60)
        print()
        print("To use this tool:")
        print("1. Go to ChatGPT -> Settings -> Data Controls -> Export")
        print("2. Wait for the email with your download link")
        print("3. Download and unzip the export")
        print("4. Copy conversations.json to this folder")
        print("5. Run this script again")
        print()
        return

    print()
    print("=" * 60)
    print("  ChatGPT Export Reader")
    print("=" * 60)
    print()
    print(f"Reading {input_file}...")
    print("(This may take a moment for large exports)")
    print()

    with open(input_file, 'r', encoding='utf-8') as f:
        conversations = json.load(f)

    print(f"Found {len(conversations)} conversations")

    output_dir.mkdir(exist_ok=True)

    conv_data = []
    filenames_used = set()

    for i, conv in enumerate(conversations):
        title = conv.get('title', 'Untitled')
        create_time = timestamp_to_datetime(conv.get('create_time'))

        date_prefix = create_time.strftime('%Y%m%d') if create_time else '00000000'
        safe_title = sanitize_filename(title)
        filename = f"{date_prefix}_{safe_title}.md"

        # Handle duplicate filenames
        counter = 1
        while filename in filenames_used:
            filename = f"{date_prefix}_{safe_title}_{counter}.md"
            counter += 1
        filenames_used.add(filename)

        filepath = output_dir / filename

        # Convert and save
        markdown = conversation_to_markdown(conv)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(markdown)

        preview = get_first_user_message(conv.get('mapping', {}))
        message_count = count_messages(conv.get('mapping', {}))

        conv_data.append({
            'title': title,
            'date': create_time,
            'filename': filename,
            'preview': preview,
            'message_count': message_count,
            'month': create_time.strftime('%Y-%m') if create_time else 'Unknown'
        })

        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1}/{len(conversations)}...")

    print()
    print("Creating searchable index...")
    generate_html_index(conv_data, output_dir / 'INDEX.html')

    print()
    print("=" * 60)
    print("  Done!")
    print("=" * 60)
    print()
    print(f"  Conversations exported: {len(conversations)}")
    print(f"  Output folder: {output_dir}")
    print()
    print("  To view your conversations:")
    print(f"  Open: {output_dir / 'INDEX.html'}")
    print()
    print("  (Just double-click the file to open it in your browser)")
    print()


if __name__ == '__main__':
    main()
