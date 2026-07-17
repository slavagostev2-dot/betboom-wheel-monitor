from pathlib import Path

agents = Path('AGENTS.md')
text = agents.read_text(encoding='utf-8')
anchor = '- уведомление о наступлении времени отправляется до автоматической очистки завершившегося колеса.\n'
block = Path('.github/ch3-agents-block.txt').read_text(encoding='utf-8').replace('__GET_UPDATES__', 'getUpdates')
if '### Достоверный health и inventory источников' not in text:
    if anchor not in text:
        raise SystemExit('AGENTS chapter 3 anchor is missing')
    agents.write_text(text.replace(anchor, anchor + block, 1), encoding='utf-8')

changelog = Path('docs/PROJECT_CHANGELOG_RU.md')
text = changelog.read_text(encoding='utf-8')
entry = Path('.github/ch3-changelog-block.txt').read_text(encoding='utf-8').replace('__GET_UPDATES__', 'getUpdates')
if '## 2026-07-17 — Глава 3: функциональные контракты' not in text:
    marker = '---\n\n'
    if marker not in text:
        raise SystemExit('Changelog marker is missing')
    changelog.write_text(text.replace(marker, marker + entry, 1), encoding='utf-8')
