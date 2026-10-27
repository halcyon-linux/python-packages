# CLAUDE.md

RPM packaging repo for **halcyon Python helper tools**: 28 small, halcyon-original,
mostly stdlib-only CLI scripts vendored under `pkgs/<pkg>/src/`. There is no upstream
for any of them. Built on Fedora Copr (`aahsnr-work/python-packages`, chroots
fedora-44 + fedora-45) by GitHub Actions; Copr does the building, signing and hosting.
Fedora 44 is the target, the fc45 chroot only surfaces breakage early. Owner: halcyon-linux
(one of seven group repos: base-pkgs, cli-tools, applications, fonts, texlive-packages,
linux-p03, python-packages). This repo was cloned from cli-tools, so some CI text still
talks about sweepers and upstream feeds that do not exist here.

## Decisions that are not visible in the code

- **No automatic updates, ever.** These are custom scripts with no upstream. Versions are
  bumped by hand (edit `Version` + `%changelog`, push). Do not add update sweepers,
  `spectool -g`, `[pkg.updates]` tables, autoupdate bots, or rpmautospec. Renovate may
  only touch pinned GitHub Actions. Do not "fix" the absence of an update workflow.
- **External CLI tools are out of scope for audits.** The `cli-tools` Copr is installed on
  the image before this repo's RPMs, so `fd`, `fzf`, `bat`, `rg`, `grim`, `claude-code`
  and friends are always present. Do not flag, package, or vendor them. A helper the
  script shells out to still gets a `Requires:` line, but its availability is not a
  finding.
- **`claude-code` is the RPM name, `claude` is the binary.** `commitpickle` requires the
  RPM and execs the binary. Never run `claude` with `--bare`: it skips OAuth and needs an
  API key, which defeats the point (it must use the user's subscription).
- **commitpickle** is a lazycommit/aicommit2-style tool: Haiku, low effort, several
  one-line Conventional Commit subjects, picker, `--print`, `-o json`, lazygit command.
  There is no `lazycommit` package in this repo; that name only refers to the upstream
  tool whose UX is copied.
- The owner runs an immutable Fedora-based image (ublue-style), so helpers target
  `rpm-ostree`, `bootc`, `flatpak`, `snapper`/btrfs and Hyprland, not a mutable
  workstation. Do not suggest `dnf install` or writing to `/usr` at runtime.

## Local environment gotchas

- System Python is 3.14 with no pytest and no ruff. Run checks with:
  `cd pkgs/<pkg>/src && uv run --no-project --with pytest --with ruff sh -c 'ruff check . && python -m pytest -q -p no:cacheprovider'`
- `rpmspec`/`rpmbuild` are not installed on the host; CI uses the builder image
  (`ghcr.io/halcyon-linux/python-packages-builder:f44`). Use a fedora:44 container to
  validate specs locally.
- Most packages test with `unittest`; commitpickle, dump-to-markdown and rmi use pytest
  (a separate loop in the CI validate job). No spec has `%check`; CI is the test gate.
- `references/` holds the original shell helpers. Read-only history, never packaged.

## Rules that bite

- **A package with no entry in `ci/packages.toml` is never built.** New package = spec
  (from `templates/python-vendored.spec.tmpl`) + vendored `src/` tree (`pyproject.toml`,
  `README.md`, `LICENSE`, `src/<module>/`, `tests/`) + registry entry `batch = 0`. A
  package depending on another repo package goes in a higher batch and needs a new
  submitN/waitN pair in `copr-build.yml` (only `bruh`, which needs `brh`, is batch 1).
- CI runs unit tests from **hard-coded package lists** (unittest loop and pytest loop) in
  `copr-build.yml`'s validate job. A new package with tests must be added there by hand.
- Spec conventions (terra-style, not Fedora defaults): `%define debug_package %{nil}`;
  explicit `Release: N%{?dist}` and a written `%changelog` authored
  `halcyon-autoupdate <aahsnr041@proton.me>`; `Source0` is `%{name}-%{version}.tar.gz`
  packed by CI from `src/` with a top-level `<name>-<version>` dir; plain
  `%autosetup -p1`, no downloads in `%prep`; `noarch`; Apache-2.0; LICENSE installed to
  `%{_licensedir}/%{name}/`; console scripts claimed explicitly in `%files`.
- **Never write a macro textually in a spec comment**; rpm expands macros inside comments.
- `%pyproject_save_files -l` takes the import name, not the package name
  (`dump_to_markdown`).
- Binary to RPM map for `Requires:`: `fd` -> `fd-find`, `rg` -> `ripgrep`,
  `ps` -> `procps-ng`, `ssh` -> `openssh-clients`.
- Push cascades are gated on the `CASCADE_ENABLED` repo variable (set `false` to stop
  them; `workflow_dispatch` bypasses it). PRs only validate.
- CI auth is the `COPR_CLICONF` secret; a wave of 401s means the Copr API token expired
  (regenerate at copr.fedorainfracloud.org/api, re-set the secret, re-run).
- A failed Copr build leaves the published repo on the last good version, so main-line
  failures self-heal.
- Never commit `__pycache__/`, `*.pyc`, `*.egg-info`, `_srpms/`.

## Commands

```bash
python3 ci/matrix.py --list     # registry consistency + build plan (CI validate job)
```

Submit one package by hand: pack `pkgs/<pkg>/src/` into
`_srpms/<pkg>/<pkg>-<ver>.tar.gz` (top-level `<pkg>-<ver>/`), `rpmbuild -bs` with
`_sourcedir`/`_srpmdir`/`_specdir` pointed at it, then
`copr-cli build --nowait python-packages <srpm>`.
