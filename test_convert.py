"""Quick checks for build_message_thread. Run: python test_convert.py"""
import convert


def msg(role, text, t):
    return {'author': {'role': role}, 'create_time': t,
            'content': {'content_type': 'text', 'parts': [text]}}


def node(nid, parent, message=None, children=None):
    n = {'id': nid, 'parent': parent, 'message': message}
    if children is not None:
        n['children'] = children
    return n


# October 2026 shape (issue #3): no `children` key anywhere, one regenerated
# reply (two children on node 3), and an interrupted empty final message.
new_style = {
    'n1': node('n1', None),
    'n2': node('n2', 'n1', msg('system', '', 1)),
    'n3': node('n3', 'n2', msg('user', 'Hello', 2)),
    'n5': node('n5', 'n3', msg('assistant', 'Second reply (regenerated)', 4)),
    'n4': node('n4', 'n3', msg('assistant', 'First reply', 3)),
    'n6': node('n6', 'n5', msg('user', 'Thanks', 5)),
    'n7': node('n7', 'n6', msg('assistant', '', 6)),
}
got = [(m['role'], m['text']) for m in convert.build_message_thread(new_style)]
assert got == [('user', 'Hello'), ('assistant', 'First reply'),
               ('assistant', 'Second reply (regenerated)'), ('user', 'Thanks')], got

# Pre-October shape: `children` lists present. Must give the same answer.
old_style = {
    'n1': node('n1', None, None, ['n2']),
    'n2': node('n2', 'n1', msg('system', '', 1), ['n3']),
    'n3': node('n3', 'n2', msg('user', 'Hello', 2), ['n4', 'n5']),
    'n4': node('n4', 'n3', msg('assistant', 'First reply', 3), []),
    'n5': node('n5', 'n3', msg('assistant', 'Second reply (regenerated)', 4), ['n6']),
    'n6': node('n6', 'n5', msg('user', 'Thanks', 5), ['n7']),
    'n7': node('n7', 'n6', msg('assistant', '', 6), []),
}
assert [(m['role'], m['text']) for m in convert.build_message_thread(old_style)] == got

print('ok: new-style and old-style trees both render', len(got), 'messages')
