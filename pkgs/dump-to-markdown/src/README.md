# dump-to-markdown

Walk every file and folder under a project root and produce a single
Markdown document containing, for every file found, a heading with its
project-relative path (e.g. `myproject/src/main.py`) followed by a fenced
code block holding that file's contents. Fence language hints are chosen
from extension, exact filename, or shebang, so blocks get sensible syntax
highlighting wherever the Markdown is rendered.

Only `.git` is skipped by default; everything else — including dotfiles —
is included. Stdlib-only: no third-party runtime dependencies.

## Install

halcyon bakes this into the built image (`/usr/bin/dump-to-markdown`) via
`install_python_packages()` in `build_files/apps/install-built-apps`, which
installs every helper into the shared venv at `/usr/lib/halcyon-python`. On a
dev machine, install it from this repo:

```sh
uv tool install ./build_files/python-packages/dump-to-markdown
# or
pipx install ./build_files/python-packages/dump-to-markdown
# or
python3 -m pip install --user ./build_files/python-packages/dump-to-markdown
````

## Usage

```sh
dump-to-markdown
dump-to-markdown --root /path/to/project --output dump.md
dump-to-markdown --exclude-dir node_modules --exclude-dir .venv
dump-to-markdown --max-size 500000
dump-to-markdown --follow-symlinks
dump-to-markdown -v
python3 -m dump_to_markdown   # module form
```

## Options

| Option                  | Description                                                         |
| ----------------------- | ------------------------------------------------------------------- |
| `--root PATH`           | Root directory to scan (default: current directory)                 |
| `--output, -o PATH`     | Markdown file to write (default: `./project_dump.md`)               |
| `--exclude-dir DIRNAME` | Extra excluded dir name (repeatable; `.git` always excluded)        |
| `--max-size BYTES`      | Skip embedding files larger than this many bytes                    |
| `--follow-symlinks`     | Descend into symlinked dirs (a symlink cycle hangs, like `find -L`) |
| `-v, --verbose`         | Debug-level logging                                                 |
| `--version`             | Print version and exit                                              |

Exit codes: `0` success · `1` bad root or write failure · `130` interrupted.

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

Or from the repo root: `just test-python`.

Apache-2.0 — see the repo root `LICENSE`.

