# Zetaris migrations

Owner: Urvashi.

No migrations have been added yet. The first file will be `001_<short_name>.sql`.

Rules (see [../README.md](../README.md)):

- Numbered, append-only, idempotent.
- Do not edit a file after it has been merged. Add the next number.
- No passwords, tokens, or cloud keys in SQL. Use `${VAR}` placeholders.
- Put a `-- statement` line between statements so the sync tool can send them one at a time.

`python tasks.py zetaris-sync` is still a stub and will not apply these files until `scripts/zetaris_sync.py` is implemented. On Windows, `py tasks.py zetaris-sync`.
