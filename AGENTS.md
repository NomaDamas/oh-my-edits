# oh-my-edits

Plugin for Claude Code and Codex that wraps Meta's Edits app (Mac MCP server and iPhone app through ipb).

## Layout

| Path | Owns |
|---|---|
| `skills/<name>/SKILL.md` | One skill each. Shared by both harnesses. |
| `scripts/phone.py` | The iPhone helper: ipb screenshot, Apple Vision OCR, screen-checked taps and text entry. Skills run it with `uv run`. |
| `tests/` | Unit tests for the helper. They need no device, no ipb, and no Vision. |
| `.claude-plugin/` | Claude Code plugin and marketplace manifests |
| `.codex-plugin/`, `.agents/plugins/` | Codex plugin and marketplace manifests |
| `research/` | Local notes on references and external services. Git ignores it. |

## Rules

- Skills are written in English. Keep the two manifests' name, version, and description in sync.
- Write in a skill only behavior you observed on a real device or app version, and name the version. Mark anything else as unverified.
- This repository is public. Do not commit device IDs, account names, tokens, screenshots of real feeds, or other creators' content. Research notes on external services stay in `research/`.
- Every skill that acts inside the Edits iPhone app follows the Safety section in `skills/edits-setup/SKILL.md`.
- Validate manifests before a PR: `claude plugin validate .`
- Run the helper tests before a PR: `uv run --with pyobjc-framework-Vision python -m unittest discover -s tests`
- Work on a branch, open a PR, and track follow-ups as GitHub issues.
