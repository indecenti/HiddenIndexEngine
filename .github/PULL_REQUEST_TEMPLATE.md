## What changes

<!-- One sentence. What this PR does. -->

## Why

<!-- The problem it solves. For a fix, how the bug was reproduced. -->

## Checklist

- [ ] `pytest` passes locally
- [ ] Type hints on new or changed signatures
- [ ] No `print()`, no magic numbers, no emoji
- [ ] Resource paths via `get_resource_path` / `get_writable_path`
- [ ] JSON writes via `safe_write_json`
- [ ] No new dependency (or discussed first in an issue)
- [ ] Docs, comments and commit messages in English

### If it touches engine/ (binding rule)

- [ ] It does not touch the modules replicated in the web runtime
- [ ] Or: `docs/web/WEB_EXPORT_SYNC.md` updated, JS runtime propagated and
      `pytest tests/test_web_sync.py` green

### If it touches scenes or catalogs

- [ ] `python tools/audit_catalog.py` executed
- [ ] New strings go through the i18n system

## Screenshots

<!-- Required if anything on screen changes. -->
