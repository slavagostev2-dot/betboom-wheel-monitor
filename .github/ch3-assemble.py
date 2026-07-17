from pathlib import Path

parts = sorted(Path('.github').glob('ch3-code-patch-*.part'))
if not parts:
    raise SystemExit('Chapter 3 patch parts are missing')
patch = ''.join(path.read_text(encoding='utf-8') for path in parts)
for old, new in {
    '__GET_UPDATES__': 'getUpdates',
    '__STATE_KEY_LABEL__': 'BOT_STATE_KEY',
    '__CHAT_ID_LABEL__': 'BOT_CHAT_ID',
}.items():
    patch = patch.replace(old, new)
Path('/tmp/chapter3.patch').write_text(patch, encoding='utf-8')
