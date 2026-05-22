# Aviona contract matrix (L2)

Locked by `tests/unit/test_aviona_contract_matrix.py`. Add a matrix row first, then a failing test — not phrasing-regex journeys.

## Turn types

| Type | LLM cycle cap | Read-only | Required invariants |
|------|---------------|-----------|---------------------|
| `local` | 0 | yes | canned `user_message`; no file writes |
| `answer` | 1 | yes | non-empty `user_message`; no file writes |
| `inspect` | 3 | yes | non-empty `user_message`; no file writes |
| `edit` | 6 | no | `user_message` + at least one write + verify passed |
| `build` | 15 | no | `user_message` + verify passed (after `needs_plan`) |

## Contract matrix rows

| ID | turn_type | user_message | writes | verify | contract | budget |
|----|-----------|--------------|--------|--------|----------|--------|
| local-greeting | local | yes | none | — | pass | ≤0 cycles |
| local-empty | local | empty | none | — | fail | ≤0 cycles |
| local-no-write | local | yes | unsolicited | — | fail | ≤0 cycles |
| answer-ok | answer | yes | none | — | pass | ≤1 cycle |
| answer-missing-message | answer | empty | none | — | fail | ≤1 cycle |
| answer-no-unsolicited-edit | answer | yes | unsolicited | — | fail | ≤1 cycle |
| answer-budget-exceeded | answer | yes | none | — | fail (budget) | >1 cycle |
| inspect-read-only | inspect | yes | none | — | pass | ≤3 cycles |
| inspect-no-write | inspect | yes | unsolicited | — | fail | ≤3 cycles |
| inspect-budget-exceeded | inspect | yes | none | — | fail (budget) | >3 cycles |
| edit-write-and-verify | edit | yes | required | pass | pass | ≤6 cycles |
| edit-missing-write | edit | yes | none | pass | fail | ≤6 cycles |
| edit-verify-failed | edit | yes | required | fail | fail | ≤6 cycles |
| build-planned | build | yes | optional | pass | pass | ≤15 cycles |
| build-missing-message | build | empty | optional | pass | fail | ≤15 cycles |
| build-verify-failed | build | yes | optional | fail | fail | ≤15 cycles |

## Declared turn_type (from decisions)

| Case | Signal | Expected type |
|------|--------|---------------|
| terminate-answer | `terminate{turn_type: answer}` | `answer` |
| terminate-edit | write + `terminate{turn_type: edit}` | `edit` |
| needs-plan-handoff | `handoff{reason: needs_plan}` | `build` |
| infer-edit-from-writes | terminate without type + file changes | `edit` |

## L3 live gate (release-blocking)

Locked by `scripts/live_gate.py` via `scripts/test-aviona.ps1 -Live`. Requires API key.

| ID | Prompt | Turn type | Must contain | Must NOT | Budget |
|----|--------|-----------|--------------|----------|--------|
| answer-hi | `hi` | answer | greeting | edits | ≤1 step |
| answer-ok | `ok` | answer | acknowledgment | edit `notes.txt` | ≤1 step |
| answer-model | `what is your model?` | answer | provider + model from anchor | edits | ≤1 step |
| answer-language-model | `what language model?` | answer | model id | project overview | ≤1 step |
| answer-salam | `try to fastly reply with "salam"` | answer | `salam` | vacuous ok | ≤1 step |
| inspect-hello-content | `what is content of hello file?` | inspect | `hi` | edits | ≤3 steps |
| inspect-project | `what is this project` | inspect | README summary | vacuous meta | ≤3 steps |
| inspect-list-files | `list files in this dir` | inspect | file names | edits | ≤4 steps |
| inspect-main-file | `read main.py and briefly explain…` | inspect | `greet` | edit `notes.txt` | ≤4 steps |
| inspect-explore-md | `explore md files in this project` | inspect | `.md` | vacuous ok | ≤4 steps |
| inspect-partial | `read README.md… first section` | inspect | project title | full install block | ≤4 steps |
| inspect-empty | `what is the content of solution.py?` | inspect | `empty` | edits | ≤4 steps |
| repeat-list | `list files in this directory` | inspect | `hello.txt` | edits | ≤4 steps |
| run-input | `python -c … add(2,3)` | inspect | `5` | edits | ≤4 steps |
| anaphora-read | create + read `anaphora_probe.txt` | edit | `probe-data` | — | ≤6 steps |
| edit-create-foo | `create foo.txt with "x"` | edit | confirmation + file | — | ≤6 steps |
| edit-test-run | write test + pytest | edit | `pytest`, `pass` | — | ≤10 steps |

## QA layers

| Layer | Command | API key |
|-------|---------|---------|
| L2 matrix | `pytest tests/unit/test_aviona_contract_matrix.py` | No |
| L2 gate | `scripts/test-aviona.ps1` | No |
| L3 live | `scripts/test-aviona.ps1 -Live` | Yes |

## Fix loop

1. Add row to the contract matrix table above.
2. Extend `CONTRACT_MATRIX` or `DECLARED_TYPE_CASES` in the test file.
3. Fix contract / budget / write-guard — not regex intent routing.
4. Run `scripts/test-aviona.ps1`.
5. Bump version when releasing (see `CHANGELOG.md`).
