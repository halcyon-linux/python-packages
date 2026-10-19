# commitpickle

Generate a two-part Conventional Commit message (subject + body) for your **staged**
changes using OpenCode's free models. Review it, then commit. Works in a plain terminal
and as a lazygit custom command. Standard library only.

## Setup

```bash
pip install --user .      # or install the RPM
commitpickle init            # writes the tool-less agent + config, prints the lazygit snippet
```

Requires `git` and a logged-in `opencode` on `PATH`.

## Use

```bash
git add -p
commitpickle                          # generate -> [C]ommit / [e]dit / [r]egenerate / [q]uit
commitpickle "fixes the race in #412" # give the model the "why"
commitpickle --print                  # print only
commitpickle --yes                    # commit without asking
commitpickle -- --no-verify -S        # extra args go to `git commit`
```

## Configure

```bash
commitpickle models                                  # list current free models
commitpickle config set models opencode/space-bunny-free,opencode/longcat-2.5-preview-free
commitpickle config set timeout 60
```

Config lives in `~/.config/commitpickle/config.toml`. `COMMITPICKLE_MODEL` overrides `models`.
Models are tried in order; the first valid message wins. `config set` rewrites the file,
so comments written by `init` are not preserved.

Free models come and go. If the first one stops working, `commitpickle models` shows what is
listed right now.

## Privacy

The staged diff is sent to the model. The default models are free models that the Zen docs
describe as zero-retention and not used for training. Other free models may train on your
prompts or keep them for a while (see <https://opencode.ai/docs/zen/#privacy>), so check
before switching.

What commitpickle does to limit exposure:

- Lock files, generated files and likely secrets (`.env`, `.env.local`, `.env.*.local`,
  `*.pem`, `*.p12`, `*.pfx`, `id_rsa`, `id_ed25519`, at any depth) are left out of the diff
  text. Their names still appear in the file list. This is a filename filter, not a secret
  scanner: a token pasted into a source file is still sent.
- The prompt is piped to OpenCode on stdin, so the diff never appears in `ps` output.
- OpenCode runs from a private empty directory (`~/.cache/commitpickle/run`), not from your
  repository, so a repository cannot change which agent, plugins or MCP servers are used.
  With `attach` set, OpenCode is pointed at the repository instead, because the server
  needs the path.

OpenCode keeps a local session record of every run (titled `commitpickle`), including the
prompt. Delete them with `opencode session delete` if that matters to you.

## Safety

The diff is untrusted input: a commit can contain text written to hijack the model. The
`commitpickle` OpenCode agent therefore denies every tool (`"*": deny`), including any MCP
tools you have configured. commitpickle refuses to run if it cannot install that agent, and
aborts if OpenCode falls back to its default agent or reports that a tool actually ran.

An agent file written by an older commitpickle is upgraded automatically. If you edited the
file yourself it is left alone, with a warning if it does not deny tools by default;
`commitpickle init --force` resets it.

## Develop

```bash
pip install -e '.[test]' && pytest
```
