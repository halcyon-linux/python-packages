# AGENTS.md

RPM package repo for **halcyon Python helper tools** — the seventh halcyon
group repository (base-pkgs, cli-tools, applications, fonts,
texlive-packages, linux-p03, python-packages; each has its own GitHub repo
under [halcyon-linux](https://github.com/orgs/halcyon-linux/repositories)
and its own Copr project under `aahsnr-work`). Built on Fedora Copr
([aahsnr-work/python-packages](https://copr.fedorainfracloud.org/coprs/aahsnr-work/python-packages/),
chroots fedora-44-x86_64 + fedora-45-x86_64) in CI. The repo carries only
specs, vendored sources, the registry and the workflows; Copr owns the
build farm, the GPG signing and the repo hosting. Consumers:

```
dnf copr enable aahsnr-work/python-packages fedora-44
```

Fedora 44 is the target; the fc45 chroot exists so closure and build
breakage surfaces one release early.

Cloned from the cli-tools group repo: same `ci/matrix.py` wave planner,
same three workflows (builder image → copr-build waves → repoclosure), same
`repo/` consumer drop-ins. Differences from cli-tools are all consequences
of halcyon-original sources: no `update.yml`, no `ci/sweep/` (nothing
upstream to sweep — bumps are manual spec edits), and the submit job packs
`Source0` from `pkgs/<pkg>/src/` instead of `spectool -g`.

## Commands

There is no test suite; verification = the Copr build going green.

```bash
# registry consistency + build plan (what CI's validate job runs)
python3 ci/matrix.py --list

# submit ONE package to Copr (what copr-build.yml's submit job does;
# rpmbuild: run inside the CI image or a fedora:44 container)
ver=$(sed -n 's/^Version:[[:space:]]*//' pkgs/<pkg>/<pkg>.spec)
mkdir -p _srpms/<pkg>/<pkg>-$ver
cp -a pkgs/<pkg>/src/. _srpms/<pkg>/<pkg>-$ver/
tar czf _srpms/<pkg>/<pkg>-$ver.tar.gz -C _srpms/<pkg> <pkg>-$ver
rpmbuild -bs --define "_sourcedir $PWD/_srpms/<pkg>" \
         --define "_srcrpmdir $PWD/_srpms" \
         --define "_specdir $PWD/pkgs/<pkg>" pkgs/<pkg>/<pkg>.spec
copr-cli build --nowait python-packages _srpms/<pkg>-*.src.rpm

# a mock buildroot identical to Copr's, for debugging a failed build locally
copr-cli mock-config aahsnr-work/python-packages fedora-44-x86_64 > /tmp/copr.cfg
mock -r /tmp/copr.cfg <srpm>
```

## Non-obvious rules

- **A package without a `ci/packages.toml` entry is never built** — the
  registry is the build selection. Adding a package = 3 items:
  `pkgs/<pkg>/<pkg>.spec` (start from
  `templates/python-vendored.spec.tmpl`), the vendored tree under
  `pkgs/<pkg>/src/` (`pyproject.toml` + `src/` + `tests/` if present +
  `LICENSE`), and the registry entry (`batch = 0`). Never commit
  `__pycache__/`, `*.pyc` or `*.egg-info` (the `.gitignore` already excludes
  them).
- **All packages are batch 0** — stdlib-only leaf tools with no
  inter-dependencies. If a future tool gains a dependency on another repo
  package, it moves to a higher batch and copr-build.yml gains a
  submitN/waitN pair (copy the batch-0 pair, renumber, chain after that
  wave).
- **Bumps are manual** (no sweeper): edit the spec's `Version` + `%changelog`
  and push — the registry carries no version field, so nothing else needs
  syncing. Push cascades are gated on the CASCADE_ENABLED repository
  variable (kill-switch — set it to `false` to stop automatic cascades;
  `workflow_dispatch` bypasses it). PRs run validation only.
- **Spec conventions** (terra-style, differ from Fedora defaults):
  - `Source0` is packed from `pkgs/<pkg>/src/` with a top-level
    `<name>-<version>` dir (the submit job does this); keep downloads out
    of `%prep` — use plain `%autosetup -p1`.
  - explicit `Release: N%{?dist}` + a written `%changelog` — no
    rpmautospec/`%autorelease`.
  - **never mention macros textually in comments** — rpm expands macros
    inside comments too.
  - stdlib-only keeps runtime Requires to the automatic python ABI dep;
    runtime helpers (`fd`, `fzf`, `bat`, `rg`) are checked by each tool at
    startup, not by RPM deps.
  - the `%pyproject_save_files -l <module>` argument is the import name,
    not the package name, when they differ (`dump_to_markdown`).
  - console scripts land in `%{_bindir}` and are claimed explicitly in
    `%files` next to `-f %pyproject_files` (the pyprland pattern).
  - _no debug packages_ — every spec carries the debug_package nil define;
    nothing in the halcyon image consumes debug packages.
  - validate a new spec with `rpmbuild -bs` locally before pushing (see
    Commands) — a failed Copr build leaves the published repo on the last
    good version, so main-line failures self-heal, but a green SRPM saves
    a cascade round-trip.
- `repo/` carries this project's consumer drop-in (`python-packages.repo`)
  — repoclosure installs it and checks the project's closure against
  Fedora (+ Terra), exactly what a halcyon-image consumer sees. Sibling
  group repos are intentionally absent: these packages depend on nothing
  outside Fedora, so the union adds no coverage.
- **CI authentication**: the `COPR_CLICONF` GitHub secret drives every
  copr-cli step. The Copr API token expires — a wave of 401s in
  copr-build.yml means: regenerate at
  <https://copr.fedorainfracloud.org/api/>, re-set the secret, re-run.
