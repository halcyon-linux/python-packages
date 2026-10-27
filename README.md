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
| `bbrew-helper`     | `bbrew-helper`     | Bootstrap Homebrew and launch the bbrew TUI.         |
| `boot-remount`     | `boot-remount`     | Remount `/boot` read-write around grub recipes, then restore. |
| `brh`              | `brh`              | Interactive rpm-ostree rollback and rebase helper.   |
| `bruh`             | `bruh`             | Short alias wrapper; `bruh moment` forwards to rollback. |
| `commitpickle`     | `commitpickle`     | Claude Haiku Conventional Commit suggestions (lazycommit/aicommit2 style); pick, then commit. |
| `crh`              | `crh`              | Custom resolution and EDID helper.                   |
| `dlss-swapper`     | `dlss-swapper`, `dlss-swapper-dll` | Steam launch wrappers forcing the latest DLSS presets. |
| `dump-to-markdown` | `dump-to-markdown` | Dump a project tree into one Markdown document.      |
| `dynamic-fixes`    | `dynamic-fixes`    | Toggle the Intel GTK renderer workaround per session. |
| `fconf`            | `fconf`            | Fuzzy configuration finder/editor.                   |
| `fe`               | `fe`               | Fuzzy edit — pick a file, open in `$EDITOR`.         |
| `fetch-image`      | `fetch-image`      | fastfetch helper: image name and signature marker.   |
| `ff`               | `ff`               | Fast file finder wrapping `fd`.                      |
| `fkill`            | `fkill`            | Fuzzy process killer.                                |
| `fp`               | `fp`               | Fuzzy file/directory previewer.                      |
| `fssh`             | `fssh`             | Fuzzy SSH launcher.                                  |
| `gameclass`        | `gameclass`        | Set WM_CLASS for a wrapped game command.             |
| `hardware-setup`   | `hardware-setup`   | One-shot host setup: kargs, hostname, image state.   |
| `nvidia-flatpak-runtime` | `nvidia-flatpak-runtime-sync`, `-notify` | Keep NVIDIA flatpak runtimes in step with the driver. |
| `powersave`        | `powersave`        | Switch the power-profiles-daemon active profile.     |
| `rmi`              | `rmi`              | Safe removal to the XDG trash.                       |
| `rmtmp`            | `rmtmp`            | Root-only secure cleanup of `/tmp` and `/var/tmp`.   |
| `screenshot`       | `screenshot`       | Wayland screenshot helper.                           |
| `se`               | `se`               | Search & edit with ripgrep and fzf.                  |
| `snapper-config`   | `snapper-config`   | Enable, clean, wipe, or disable the root snapper config. |
| `ublue-motd`       | `ublue-motd`       | Login banner: image info, staged updates, tips.      |
| `user-setup`       | `user-setup`, `privileged-user-setup` | Per-user setup, polkit helper, template symlinks.    |
| `uupd-update`      | `uupd-update`      | Front-end for `ujust update`: attach to or start the uupd service, stream its journal. |

Runtime tool dependencies (`fd`, `fzf`, `bat`, `rg`, `glow`, `grim`, `swappy`,
`slurp`, `rpm-ostree`, `skopeo`, `sudo`, `systemd`, `wmctrl`, `xdotool`) come from RPM dependencies; tools report
failures when a required command cannot run. These ports replace former
image-owned shell helpers and additionally require `flatpak`,
`snapper`, `zenity`, `btrfs-assistant`, `polkit`, `libnotify`, `xdg-utils`,
`xdg-user-dirs`, and `util-linux-core`.

`commitpickle` additionally requires `claude-code` (the `claude` CLI, logged in
with a Claude subscription). Fedora does not package it; it must come from
another repo on the image.

## CI

- `copr-build.yml` — a push to `main` rebuilds changed packages in dependency
  waves (batch 0 before batch 1). Gated on the `CASCADE_ENABLED` repository variable
  (kill-switch; `workflow_dispatch` bypasses it). PRs validate only.
- `repoclosure.yml` — nightly + post-cascade closure check of the published
  Copr repo against Fedora 44/45.
- `builder-docker.yml` — builds this repo's own CI job image and pushes it
  to `ghcr.io/halcyon-linux/python-packages-builder:f44`.

There is no version sweeper: halcyon-authored tools have no upstream feed.
Bumps are manual — edit the spec's `Version` + `%changelog` and push.

## Running and cancelling workflows

### Run a workflow manually

In the GitHub UI: **Actions** → the workflow → **Run workflow** → branch `main` →
fill the inputs → **Run workflow**. From the CLI:

```bash
gh workflow run <file> -R halcyon-linux/python-packages --ref main -f <input>=<value>
```

Inputs (leave empty for the default):

- `copr-build.yml` — `only`: space-separated packages to build (empty = all), e.g. `-f only="<pkg> <pkg>"`. Bypasses the `CASCADE_ENABLED` gate.
- `repoclosure.yml`, `builder-docker.yml` — no inputs.

### Force-cancel a workflow run

1. Find the run ID: `gh run list -R halcyon-linux/python-packages --workflow <file>`.
2. Cancel it: `gh run cancel <run-id> -R halcyon-linux/python-packages`, or **Cancel workflow**
   on the run page.
3. If it stays in *Cancelling* because a job or runner is hung, use **Force cancel**
   on the run page, or:

   ```bash
   gh api -X POST repos/halcyon-linux/python-packages/actions/runs/<run-id>/force-cancel
   ```

A force cancel ends the run without waiting for its jobs. It does not stop Copr
builds that were already submitted; cancel those on the Copr project page.

## Layout

```
ci/packages.toml    the registry: build selection (a package without an
                    entry is never built). All batch 0, no sweep feeds.
ci/matrix.py        batch/wave build plan (validate job runs it)
pkgs/<pkg>/         spec + vendored sources under src/
repo/               this project's consumer .repo drop-in
templates/          starting point for new specs (vendored-source pattern)
```

See [CLAUDE.md](CLAUDE.md) for the conventions before touching specs.
