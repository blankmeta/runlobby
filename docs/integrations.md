# Terminal integrations

[← README](../README.md) · [Profiles](profiles.md)

```sh
runlobby status --line
```

Example output:

```text
Codex work: 5h 76% / week 62% running (snapshot)
```

The line uses the current project's bound profile, or the only profile if exactly one exists. With multiple unbound profiles, it asks you to choose instead of guessing. It omits email addresses and labels usage as a snapshot.

## tmux example

Add this to your tmux configuration, or append the command expression to your existing status format:

```tmux
set -g status-interval 30
set -g status-right '#(cd #{q:pane_current_path} && runlobby status --line)'
```

`runlobby` must be on the tmux server's PATH. The [tmux format modifier](https://man.openbsd.org/tmux#FORMATS) quotes the pane directory for the shell. This is an example configuration; automated tests cover status output, not tmux rendering.

## Codex server lifetime

Codex account launches bypass the shared background server: an existing app-server cannot
replace the selected account with its cached credentials. This applies to both
original accounts and isolated profiles, including resume. Newer Codex uses
`--no-daemon`; older versions use a file-credentials CLI config override to select
the embedded server. `--remote` is rejected
in account launches because a remote server owns its own credentials; launch
remote Codex directly instead. POSIX launches raise the local soft descriptor
limit to 4096 when allowed by the existing hard limit. System-wide limits stay unchanged.

## JSON contract, version 1

```sh
runlobby status --json
```

The command returns one JSON object on stdout. Failures go to stderr with a nonzero exit code. It reads local state by default; `--refresh` requests usage data for idle profiles. Running profiles retain their cached data.

```json
{
  "schema_version": 1,
  "project": {"path": "/projects/api", "profile": "work"},
  "profiles": [{
    "name": "work",
    "running": false,
    "state": "ready",
    "message": null,
    "account": {"name": "Work", "email": "work@example.com", "plan": "plus"},
    "usage": {
      "primary": {"remaining_percent": 76, "window_minutes": 300, "resets_at": 1789740000},
      "secondary": null,
      "updated_at": 1789732800,
      "source": "cache"
    }
  }]
}
```

`state` is `ready`, `running`, `login_required`, or `error`. `running` indicates that the profile lock is held, including during maintenance. Unknown accounts, windows, and timestamps use `null`; missing usage is never reported as 100% available. Timestamps are Unix seconds. Consumers should ignore additional fields and reject unsupported schema versions.

JSON includes account email and the current project path, but no credentials or raw auth files. Treat those identifying fields accordingly when sharing logs.
