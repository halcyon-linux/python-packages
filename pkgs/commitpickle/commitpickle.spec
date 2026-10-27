# commitpickle: halcyon-original Python helper; sources vendored under
# pkgs/commitpickle/src (no upstream tarball exists). Submitted to Copr
# aahsnr-work/python-packages. Bumps are manual: edit Version + changelog,
# push, the cascade rebuilds.
%define debug_package %{nil}

Name:           commitpickle
Version:        0.2.0
Release:        1%{?dist}
Summary:        Generate Conventional Commit suggestions with Claude Haiku.
License:        Apache-2.0
URL:            https://github.com/halcyon-linux/python-packages
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel
BuildRequires:  git-core
Requires:       git-core
Requires:       claude-code

%description
Generate several Conventional Commit subjects for staged changes with Claude
Haiku at low effort, pick one, then commit. Like lazycommit and aicommit2, but
it uses the Claude subscription through the logged-in claude CLI instead of an
API key. Works in a plain terminal and as a lazygit custom command. Standard
library only.

%prep
%autosetup -p1

%generate_buildrequires
%pyproject_buildrequires -x test

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l commitpickle
install -Dpm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE

%check
%pytest

%files -f %pyproject_files
%license %{_licensedir}/%{name}/LICENSE
%{_bindir}/commitpickle

%changelog
* Tue Oct 27 2026 halcyon-autoupdate <aahsnr041@proton.me> - 0.2.0-1
- rewrite: Claude Haiku (low effort) via the claude CLI and subscription, no API key
- lazycommit/aicommit2 style: several suggestions, picker, --print, -o json
- drop opencode, its agent file, and the models subcommand

* Tue Oct 20 2026 halcyon-autoupdate <aahsnr041@proton.me> - 0.1.0-1
- initial packaging (vendored halcyon-original sources)
- opencode v2 CLI compatibility: model listing, attach via --server, error parsing
