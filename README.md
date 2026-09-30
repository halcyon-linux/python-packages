# python-packages

halcyon Python helper tools — Fedora 44 (+45) RPMs built on
[Copr](https://copr.fedorainfracloud.org/coprs/aahsnr-work/python-packages/).

```
dnf copr enable aahsnr-work/python-packages fedora-44
```

One of the seven halcyon group repositories: base-pkgs · cli-tools ·
applications · fonts · texlive-packages · linux-p03 · python-packages.

Unlike the six source-build siblings, these are halcyon-original tools with
no upstream tarball: each package's sources are vendored under
`pkgs/<pkg>/src/`, and the copr-build submit job packs `Source0` from there.

| Package            | Binary             | Purpose                                              |
| ------------------ | ------------------ | ---------------------------------------------------- |
| `dump-to-markdown` | `dump-to-markdown` | Dump a project tree into one Markdown document.      |
| `fconf`            | `fconf`            | Fuzzy configuration finder/editor.                   |
| `fe`               | `fe`               | Fuzzy edit — pick a file, open in `$EDITOR`.         |
| `ff`               | `ff`               | Fast file finder wrapping `fd`.                      |
| `fkill`            | `fkill`            | Fuzzy process killer.                                |
| `fp`               | `fp`               | Fuzzy file/directory previewer.                      |
| `fssh`             | `fssh`             | Fuzzy SSH launcher.                                  |
| `rmi`              | `rmi`              | Safe removal to the XDG trash.                       |
| `rmtmp`            | `rmtmp`            | Root-only secure cleanup of `/tmp` and `/var/tmp`.   |
| `screenshot`       | `screenshot`       | Wayland screenshot helper.                           |
| `se`               | `se`               | Search & edit with ripgrep and fzf.                  |

Runtime tool dependencies (`fd`, `fzf`, `bat`, `rg`, `grim`, `swappy`,
`slurp`) come from the image's RPM layer; each tool checks for its own
dependencies at startup and exits with a clear message if missing.

## CI

- `copr-build.yml` — a push to `main` rebuilds changed packages (all batch
  0, one wave). Gated on the `CASCADE_ENABLED` repository variable
  (kill-switch; `workflow_dispatch` bypasses it). PRs validate only.
- `repoclosure.yml` — nightly + post-cascade closure check of the published
  Copr repo against Fedora 44/45.
- `builder-docker.yml` — builds this repo's own CI job image and pushes it
  to `ghcr.io/halcyon-linux/python-packages-builder:f44`.

There is no version sweeper: halcyon-authored tools have no upstream feed.
Bumps are manual — edit the spec's `Version` + `%changelog` and push.

## Layout

```
ci/packages.toml    the registry: build selection (a package without an
                    entry is never built). All batch 0, no sweep feeds.
ci/matrix.py        batch/wave build plan (validate job runs it)
pkgs/<pkg>/         spec + vendored sources under src/
repo/               this project's consumer .repo drop-in
templates/          starting point for new specs (vendored-source pattern)
```

See [AGENTS.md](AGENTS.md) for the conventions before touching specs.
