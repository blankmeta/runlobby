# Changelog

## 1.5.2

- Launch Codex without the shared background daemon for both original accounts and isolated profiles. Use `--no-daemon` when supported, and a file-credentials config override for older Codex versions that embed their server when CLI overrides are supplied. Reject remote-server overrides that would bypass account selection.
- Raise the POSIX soft file-descriptor limit to 4096 when the existing hard limit allows it, without changing system-wide settings.
- Reap PTY children after cancellation, escalating from hangup to terminate and kill when necessary. Make PTY cleanup idempotent so a second close cannot close a reused descriptor.

## 1.5.1

- Add `rlb monitor on|off|status` and a persistent side-panel toggle in Settings. Turning it off bypasses the terminal renderer; toggling from the menu keeps keyboard focus on the setting.
- Fix standalone builds recursively launching RunLobby when a configured tool is a Python script. Executable scripts use their shebang; other scripts require an external Python interpreter.
- Exercise script overrides inside every packaged native build, in addition to source-level tests.

## 1.5.0

- Show a live local activity panel beside Codex and Claude by default, using built-in PTY/ConPTY support across macOS, Linux and Windows. F8 toggles the panel; F9 selects the monitored session; F10 changes ranking.
- Analyze recorded actions and token usage without model calls, including linked subagent histories. Deduplicate provider usage records and show mixed requests separately.
- Add session history with top action categories, recorded commands, durations, errors and repeated results. Document classification sources and accounting limits.

## 1.4.2

- Match usage columns to the reported window duration. Weekly-only accounts show a dash under 5h and their actual weekly balance under Week, including saved profiles and reset times.

## 1.4.1

- Install the standalone macOS build through Homebrew, without upgrading global Node, Python or Xray packages. This avoids compiler dependencies on macOS 14.
- Include the original `codex-proxy` entry point in standalone builds and verify it after installation.
- Bundle the usage guide and changelog with the application.

## 1.4.0

Continues the 1.x release series after 1.3.0 and supersedes the release numbered 2.0.1.

- Rename to RunLobby, with `rlb` as the short command. Preserve `codex-lobby`, `cxl`, `codex-switch`, `codex-vpn`, existing account paths and project preferences.
- Add isolated Claude subscription accounts beside Codex accounts. Select a provider only when adding an account; launch and resume from the common menu.
- Preserve Claude credential paths and session history during verified reauthentication. Read usage from the documented status-line interface; never copy refresh tokens.
- Add platform ports and native Windows, macOS and Linux implementations for console input, inherited process locks, paths and proxy lifecycle.
- Ship standalone installers and verify native dependencies against pinned checksums. Install missing tools from the account flow.
- Verify Windows installer checksum downloads from a file, independent of the HTTP content type, and test installation with Windows PowerShell 5.1 and 7.
- Simplify the English and Russian READMEs around installation, browser sign-in and account selection. Enlarge the menu preview text.
- Exercise the same account scenarios on Python 3.11/3.13 across Windows, macOS and Linux, with native CLI compatibility, Win32 console events, POSIX PTYs and a local VLESS tunnel.

Browser OAuth is still performed by the provider CLI. Automated tests use synthetic credentials and do not send model requests.

## 1.3.0

- One terminal menu for ChatGPT accounts, remaining limits, session continuation, and settings. Arrow keys and Enter; numbered choices on non-interactive terminals.
- Add an account without inventing a profile ID. Email names by default, editable labels with spaces and Unicode, and a saved language preference.
- Keep original accounts and their history visible alongside added accounts.
- Show quota freshness and reset countdowns. Unknown or expired snapshots never imply fresh allowance. Exhausted accounts offer refresh or another selection.
- Repair sign-in and choose project defaults inside the menu. Busy accounts and missing project preferences return to a choice without changing identity.
- Paste a VLESS link with hidden input, validate and test the connection, and restore the previous preference if the check fails. Confirm changes to a running proxy.
- Add explicit account removal with confirmation, including its local history. Active accounts cannot be removed or renamed.
- Preserve CLI commands, JSON schema version 1, per-account isolation, and concurrent use of different accounts.

One running Codex process per added account remains the supported limit. Browser OAuth is still handled by Codex; automated login tests use synthetic credentials.

## 1.2.0

- Add isolated ChatGPT account profiles with `login <name>` and `run <name>`.
- Remember the default profile for a project with `bind`; remove the preference with `unbind`.
- Run different profiles concurrently with separate Codex homes and history. A process-lifetime lock permits one Codex process per profile.
- Keep live profiles on cached usage; serialize sign-in and refresh with launches.
- Stage reauthentication before replacing credentials. Reject a different account or a duplicate managed identity.
- Add versioned JSON status and an email-free status line for terminal integrations.
- Preserve original accounts and history through `runlobby legacy`.

New managed profiles require their own sign-in and start with separate history/configuration. Existing profiles are not migrated automatically. Desktop/IDE integration, same-profile parallel processes, and cross-account history merging are not included.

## 1.1.0

Account picker, usage snapshots, guided VLESS setup, Homebrew packaging, and domain/application/infrastructure architecture.

## 1.0.0

Original codex-vpn wrapper.
