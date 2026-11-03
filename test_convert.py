"""Synthetic regression tests. Run: python test_convert.py"""

import json
import tempfile
from pathlib import Path

import convert


def msg(role, text, t):
    return {
        'author': {'role': role},
        'create_time': t,
        'content': {'content_type': 'text', 'parts': [text]},
    }


def node(nid, parent, message=None, children=None):
    n = {'id': nid, 'parent': parent, 'message': message}
    if children is not None:
        n['children'] = children
    return n


def conversation(cid, title, t, project_id=None):
    data = {
        'id': cid,
        'conversation_id': cid,
        'title': title,
        'create_time': t,
        'update_time': t + 10,
        'mapping': {
            'n1': node('n1', None),
            'n2': node('n2', 'n1', msg('user', f'hello from {title}', t)),
            'n3': node('n3', 'n2', msg('assistant', 'reply', t + 1)),
        },
    }
    if project_id:
        data['conversation_template_id'] = project_id
    return data


def test_message_tree_compatibility():
    new_style = {
        'n1': node('n1', None),
        'n2': node('n2', 'n1', msg('system', '', 1)),
        'n3': node('n3', 'n2', msg('user', 'Hello', 2)),
        'n5': node('n5', 'n3', msg('assistant', 'Second reply (regenerated)', 4)),
        'n4': node('n4', 'n3', msg('assistant', 'First reply', 3)),
        'n6': node('n6', 'n5', msg('user', 'Thanks', 5)),
    }
    got = [(m['role'], m['text']) for m in convert.build_message_thread(new_style)]
    assert got == [
        ('user', 'Hello'),
        ('assistant', 'First reply'),
        ('assistant', 'Second reply (regenerated)'),
        ('user', 'Thanks'),
    ], got

    old_style = {
        'n1': node('n1', None, None, ['n2']),
        'n2': node('n2', 'n1', msg('system', '', 1), ['n3']),
        'n3': node('n3', 'n2', msg('user', 'Hello', 2), ['n4', 'n5']),
        'n4': node('n4', 'n3', msg('assistant', 'First reply', 3), []),
        'n5': node('n5', 'n3', msg('assistant', 'Second reply (regenerated)', 4), ['n6']),
        'n6': node('n6', 'n5', msg('user', 'Thanks', 5), []),
    }
    assert [(m['role'], m['text']) for m in convert.build_message_thread(old_style)] == got


def test_end_to_end_project_recovery():
    project_a = 'g-p-alpha123'
    project_b = 'g-p-beta456'

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        out = root / 'archive'

        (root / 'conversations-000.json').write_text(json.dumps([
            conversation('c1', 'Project A chat', 1000, project_a),
            conversation('c2', 'Ordinary chat', 1100),
        ]), encoding='utf-8')
        (root / 'conversations-001.json').write_text(json.dumps([
            conversation('c3', 'Project B chat', 1200, project_b),
        ]), encoding='utf-8')

        payload1 = b'# original markdown\nhello\n'
        payload2 = b'second version\n'
        payload3_parts = [b'PK-part-one-', b'part-two']
        payload4 = b'unassigned library payload\n'

        (root / 'file_aaa.dat').write_bytes(payload1)
        (root / 'file_bbb.dat').write_bytes(payload2)
        (root / 'file_ccc.part1').write_bytes(payload3_parts[0])
        (root / 'file_ccc.part2').write_bytes(payload3_parts[1])
        (root / 'file_ddd.dat').write_bytes(payload4)

        library = [
            {
                'file_id': 'file_aaa', 'gizmo_id': project_a, 'is_project': True,
                'file_name': 'notes.md', 'normalized_name': 'notes.md',
                'file_extension': 'md', 'mime_type': 'text/markdown',
                'file_size_bytes': len(payload1), 'state': 'ready',
                'created_at': '2026-01-01T00:00:00+00:00',
                'origination_thread_id': 'c1',
            },
            {
                'file_id': 'file_bbb', 'gizmo_id': project_a, 'is_project': True,
                'file_name': 'notes.md', 'normalized_name': 'notes.md',
                'file_extension': 'md', 'mime_type': 'text/markdown',
                'file_size_bytes': len(payload2), 'state': 'ready',
                'created_at': '2026-01-02T00:00:00+00:00',
            },
            {
                'file_id': 'file_ccc', 'gizmo_id': project_b, 'is_project': True,
                'file_name': 'bundle.zip', 'normalized_name': 'bundle.zip',
                'file_extension': 'zip', 'mime_type': 'application/zip',
                'file_size_bytes': sum(map(len, payload3_parts)), 'state': 'ready',
                'created_at': '2026-01-03T00:00:00+00:00',
            },
            {
                'file_id': 'file_ddd', 'is_project': False,
                'file_name': 'global-note.txt', 'normalized_name': 'global-note.txt',
                'file_extension': 'txt', 'mime_type': 'text/plain',
                'file_size_bytes': len(payload4), 'state': 'ready',
                'created_at': '2026-01-04T00:00:00+00:00',
                'origination_thread_id': 'c2',
            },
        ]
        (root / 'library_files.json').write_text(json.dumps(library), encoding='utf-8')

        manifest = {
            'version': 1,
            'export_files': [
                {'path': 'file_aaa.dat', 'size_bytes': len(payload1)},
                {'path': 'file_bbb.dat', 'size_bytes': len(payload2)},
                {'path': 'file_ccc.part1', 'size_bytes': len(payload3_parts[0])},
                {'path': 'file_ccc.part2', 'size_bytes': len(payload3_parts[1])},
                {'path': 'file_ddd.dat', 'size_bytes': len(payload4)},
            ],
            'logical_files': {
                'file_aaa.dat': {'files': ['file_aaa.dat'], 'sharded': False},
                'file_bbb.dat': {'files': ['file_bbb.dat'], 'sharded': False},
                'file_ccc.dat': {'files': ['file_ccc.part1', 'file_ccc.part2'], 'sharded': True},
                'file_ddd.dat': {'files': ['file_ddd.dat'], 'sharded': False},
            },
            'manifest_file': 'export_manifest.json',
        }
        (root / 'export_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        (root / 'project_names.json').write_text(json.dumps({project_a: 'Alpha Project'}), encoding='utf-8')

        report = convert.run(root, out, restore_files=True)
        assert report['conversation_count'] == 3
        assert report['project_detection']['project_count'] == 2

        alpha = out / 'Projects' / 'Alpha Project'
        assert alpha.exists()
        alpha_files = sorted((alpha / 'Files').iterdir())
        assert len(alpha_files) == 2
        assert {p.read_bytes() for p in alpha_files} == {payload1, payload2}
        assert len({p.name.lower() for p in alpha_files}) == 2, 'duplicate original names must not overwrite'

        beta_dirs = [p for p in (out / 'Projects').iterdir() if p.is_dir() and p.name != 'Alpha Project']
        assert len(beta_dirs) == 1
        beta_files = list((beta_dirs[0] / 'Files').iterdir())
        assert len(beta_files) == 1
        assert beta_files[0].read_bytes() == b''.join(payload3_parts)

        alpha_index = json.loads((alpha / 'library_index.json').read_text(encoding='utf-8'))
        assert all(item['size_matches_metadata'] is True for item in alpha_index)
        assert any(item.get('origin_conversation_filename') for item in alpha_index)
        library_files = list((out / 'Library' / 'Files').iterdir())
        assert len(library_files) == 1
        assert library_files[0].read_bytes() == payload4
        global_library = json.loads((out / 'Library' / 'library_index.json').read_text(encoding='utf-8'))
        assert len(global_library) == 4
        assert sum(1 for x in global_library if not x.get('project_id')) == 1

        root_html = (out / 'INDEX.html').read_text(encoding='utf-8')
        assert 'data-tab="library"' in root_html
        assert 'renameProject' in root_html
        assert 'Export project_names.json' in root_html
        assert 'Unassigned' in root_html
        assert project_a in root_html and project_b in root_html
        assert 'Date range:' in root_html
        assert 'Newest first' in root_html and 'Oldest first' in root_html
        assert 'Name A → Z' in root_html and 'Name Z → A' in root_html
        assert 'File type A → Z' in root_html
        assert '<th>Type</th>' in root_html
        assert 'data-sort-date=' in root_html and 'data-sort-name=' in root_html
        assert 'ChatGPT Export Reader + Project Recovery' in root_html
        assert 'v1.0.0' in root_html
        assert 'https://github.com/rschaer/chatgpt-export-reader' in root_html

        # Project date range combines conversation creation dates and Library creation dates.
        alpha_summary = next(x for x in report['projects'] if x['id'] == project_a)
        assert alpha_summary['first_date'] == '1970-01-01'
        assert alpha_summary['last_date'] == '2026-01-02'
        assert alpha_summary['last_date_sort'] > alpha_summary['first_date_sort']

        alpha_html = (alpha / 'INDEX.html').read_text(encoding='utf-8')
        assert 'Date range:</strong> 1 January 1970 to 2 January 2026' in alpha_html
        assert 'File type A → Z' in alpha_html
        assert '<th>Type</th>' in alpha_html

        library_html = (out / 'Library' / 'INDEX.html').read_text(encoding='utf-8')
        assert 'File type A → Z' in library_html
        assert 'data-sort-type=".txt"' in library_html or 'data-sort-type=".md"' in library_html

        assert (out / 'INDEX.html').exists()
        assert (out / 'Projects' / 'INDEX.html').exists()
        assert (out / 'Library' / 'INDEX.html').exists()
        assert (out / 'recovery_report.json').exists()
        assert (out / 'project_names.example.json').exists()
        assert report['library_recovery']['unassigned_records'] == 1
        assert report['library_recovery']['project_associated_records'] == 3


def main():
    test_message_tree_compatibility()
    test_end_to_end_project_recovery()
    print('ok: message-tree compatibility and synthetic Project recovery passed')


if __name__ == '__main__':
    main()
