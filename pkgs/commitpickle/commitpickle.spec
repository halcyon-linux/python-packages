# commitpickle: halcyon-original Python helper; sources vendored under
# pkgs/commitpickle/src (no upstream tarball exists). Submitted to Copr
# aahsnr-work/python-packages. Bumps are manual: edit Version + changelog,
# push, the cascade rebuilds.
# Vendored 0.1.0 with opencode v2 CLI fixes; see the changelog.
%define debug_package %{nil}

Name:           commitpickle
Version:        0.1.0
Release:        1%{?dist}
Summary:        Generate two-part Conventional Commit messages with OpenCode.
License:        Apache-2.0
URL:            https://github.com/halcyon-linux/python-packages
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel
BuildRequires:  git-core
Requires:       git-core
Requires:       opencode

%description
Generate a two-part Conventional Commit message (subject plus body) for staged
changes using OpenCode's free models, review it, then commit. Works in a plain
terminal and as a lazygit custom command. Standard library only.

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
* Tue Oct 20 2026 halcyon-autoupdate <aahsnr041@proton.me> - 0.1.0-1
- initial packaging (vendored halcyon-original sources)
- opencode v2 CLI compatibility: model listing, attach via --server, error parsing
