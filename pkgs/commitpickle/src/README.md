# commitpickle

Generate Conventional Commit suggestions for your staged changes with Claude Haiku,
pick one, then commit. It works like `lazycommit` / `aicommit2`: several one-line
candidates, a numbered picker, and a lazygit custom command. It uses your Claude
subscription through the logged-in `claude` CLI (Claude Code), so no API key is needed.
Standard library only.

## Setup

1. Install Claude Code and log in with your subscription (`claude`, then `/login`).
2. `commitpickle init` writes `~/.config/commitpickle/config.toml` and prints a lazygit snippet.

## Use

```
git add -p
commitpickle                 # suggestions -> pick -> commit
commitpickle "fixes #12"     # extra context for the "why"
commitpickle -g 3            # three suggestions
commitpickle --print         # print suggestions, one per line, do not commit
commitpickle -o json         # {"messages": [...]} for scripts and lazygit
commitpickle --yes           # commit with the first suggestion
commitpickle -- --no-verify  # arguments after -- go to `git commit`
```

At the prompt: a number picks that suggestion (Enter picks 1), `e2` picks 2 and opens your editor,
`r` regenerates, `q` quits.

## Config

`commitpickle config` shows settings; `commitpickle config set <key> <value>` changes them.

| key | default | meaning |
| --- | --- | --- |
| `model` | `haiku` | any `claude --model` alias or full name (`COMMITPICKLE_MODEL` overrides) |
| `effort` | `low` | `low`, `medium`, `high`, `xhigh`, `max` |
| `count` | `6` | suggestions per run (1-10) |
| `timeout` | `120` | seconds per attempt |
| `max_diff` | `60000` | max bytes of staged diff sent |

## Privacy and safety

The staged diff, branch name and last 10 commit subjects are sent to Anthropic through your
Claude subscription. Lock files and likely-secret files (`.env`, `*.pem`, ...) are left out of the
diff text. The prompt goes in on stdin. `claude` runs with every tool disabled, no MCP servers, no
slash commands and no saved session, from `~/.cache/commitpickle/run` so the repository's own
CLAUDE.md, settings and hooks are not loaded.
