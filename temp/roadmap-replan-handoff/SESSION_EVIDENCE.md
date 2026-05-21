# Session Evidence — User-Reported REPL Runs

Summarized from Cursor chat transcripts and debug logs (`~/.aviona/debug/*.txt`).

---

## Session A — Early debug (df52fe66, 93e8af4, etc.)

**Workspace:** `D:\thesis\aviona-test`  
**Issues drove fixes:**

| Prompt | Result | Root cause found |
|--------|--------|------------------|
| `just say "ali ali"` | ok 1 step | — |
| `tell me what is your llm model?` | ok | — |
| `are you gpt?` | ok | — |
| `hi` | FAIL harness (`Hi there!` vs `hi`) | Strict must_contain |
| `what is content of hello file?` | budget / missing message | list_dir loop |
| `list files in this dir` | listing but 3 steps | no terminate |
| `read main.py and explain…` | missing main in raw dump | synthesis dumped file not summary |
| `create bar.txt…` | missing message | code_edit without terminate |

---

## Session B — User "you stuck" continuation

After constraint + interactive loop fixes, debug_session **8/8 then 9/9** with hardcoded shortcuts (later removed).

---

## Session C — Manual REPL (`418ec76b…`)

```
aviona> what is you model?          → ok 1 step
aviona> try to fastly reply "salam"  → ok 1 step
aviona> list files in current dir    → ok 3 steps (listing)
aviona> list files in current dir    → ok 3 steps again (~13s)
aviona> what is content of main file? → ok 3 steps BUT listing not main.py
aviona> i asked for content…         → ok 2 steps (main.py content) — user correction turn
aviona> run this code with input…    → ok 3 steps BUT listing
```

---

## Session D — Extended manual (`a28c4fad…`)

```
aviona> what is content of main file?  → ok 0 steps (hardcoded — removed in 10c80eb)
aviona> read notes.txt                 → ok 0 steps (hardcoded — removed)
aviona> explore md files               → ok 3 steps, listing (wrong)
aviona> read first 3 lines of bar.txt  → ok 1 step, full file "debug-smoke"
aviona> edit bar.txt random sentence   → ok 6 steps, "Updated bar.txt."
aviona> read its content now           → ok 2 steps, correct sentence
aviona> write unit test, run, show     → ok 3 steps, listing (wrong)
```

---

## Log patterns (framework)

### list_dir loop (explore, main file, unit test)

```
[INTERACTIVE] attempt=1 billable=0 → tool_call list_dir
[INTERACTIVE] attempt=2 billable=1 → tool_call list_dir (repeat)
[INTERACTIVE] attempt=3 billable=2 → tool_call list_dir
[INTERACTIVE] done outcome=solved user_message_len=<listing>  # BEFORE fix
[INTERACTIVE] done outcome=unresolvable                       # AFTER fix
```

### read without terminate

```
tool_call read_file → ok
(no terminate)
→ synthesis: "solution.py is empty." IF snapshot kept
```

### edit without terminate

```
code_edit × N → ok
→ synthesis: "Updated bar.txt."
```

### shell permission (earlier logs)

```
[EXECUTOR] tool_dispatch_start tool=shell
Permission denied: shell type hello.txt
```

---

## User preferences (explicit)

1. **No hardcode** — removed python_complete, aliases, greet run
2. **Fix framework first**, Aviona thin
3. **Replanned roadmap** for all issues — not incremental patches
4. Debug mode valued — keep `--debug` logs

---

## Suggested live matrix rows (for replan, not implementation here)

| ID | Prompt | Expected turn_type | Notes |
|----|--------|-------------------|-------|
| inspect-main-file | what is content of main file? | inspect | Must not be listing |
| inspect-explore-md | explore md files | inspect | Must read .md files |
| inspect-partial | first 3 lines of X | inspect | Substring or honest limit |
| run-input | run this code with input "…" | inspect | shell/pytest output |
| edit-test-run | write unit test, run, show | edit | Multi-step |
| anaphora-read | read its content now | inspect | After prior edit turn |
