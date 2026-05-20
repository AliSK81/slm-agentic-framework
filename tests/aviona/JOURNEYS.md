# Aviona user journey matrix

Locked by `tests/unit/test_aviona_journeys.py`. Every user-reported REPL bug adds a row here first, then a failing test.

## Journeys

| ID | User prompt | Goal kind | Required tools | REPL must show | Must NOT |
|----|-------------|-----------|----------------|----------------|----------|
| J1 | `hi` | local chat | none | greeting | API call, file edits |
| J9 | `ok` | local chat | none | acknowledgment | API call, file edits |
| J2 | `list files in this dir` | read | `list_dir` | file names | file edits |
| J3 | `what is content of hello file?` | read_content | `read_file` | file body (`hi`) | directory listing only |
| J4 | `read hello.txt` | read_content | `read_file` | file body | listing only |
| J5 | `explain the codebase` | explain | read tools + `terminate` | prose answer | file edits |
| J8 | `what is this project` | explain | read tools or fallback | project summary from README | vacuous meta answer, file edits |
| J6 | `create foo.txt with "x"` | write | `write_file` / `code_edit` | `edited foo.txt` | — |
| J7 | chat-like line + agent edits | general | none | failure / no false ok | unsolicited edits |

## QA layers

| Layer | Command | API key |
|-------|---------|---------|
| L1 | `pytest tests/unit/test_aviona_effects.py tests/unit/test_aviona_intent.py` | No |
| L2 | `pytest tests/unit/test_aviona_journeys.py` | No |
| L2 gate | `scripts/test-aviona.ps1` | No |
| L3 | `scripts/test-aviona.ps1 -Live` | Yes |

## Fix loop

1. Add row to this table.
2. Write failing L2 test.
3. Fix intent / verification / hints.
4. Run `scripts/test-aviona.ps1`.
5. Bump version (see below).
6. Optional L3 manual check in `D:\thesis\aviona-test`.

## Version policy

Versions are manual in `src/aviona/__init__.py` and `pyproject.toml` (not auto from git).

| Bump | When | Example |
|------|------|---------|
| Patch | Bugfix, intent, verification | `0.2.0` → `0.2.1` |
| Minor | New REPL capability | `0.2.x` → `0.3.0` |

After every bump: `pip install -e .` then `aviona --version`.
