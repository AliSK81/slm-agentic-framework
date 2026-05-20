# Aviona project rules (fixture)

- Keep edits inside this repository.
- Prefer small, focused file changes.

## v1 smoke commands

```bash
pip install -e .
cd tests/fixtures/sample_repo
aviona
> create hello.txt with "hi"
```

After a successful turn, `hello.txt` should exist in this directory and a session line is appended under `~/.aviona/projects/<hash>/`.
