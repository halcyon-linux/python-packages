# Template for halcyon-original Python helpers (vendored sources, no upstream).
#
# Copy to pkgs/<name>/<name>.spec and fill the five @FIELDS@. Convention notes:
# - Source0 is packed by the copr-build submit job from pkgs/<name>/src/ with
#   a top-level <name>-<version> dir; plain autosetup unpacks it (no -c).
# - stdlib-only: no runtime Requires beyond the automatic python ABI dep.
#   Runtime helpers (fd, fzf, bat, rg) are checked by the tool at startup.
# - Written Release + changelog (no rpmautospec — terra-style conventions).
# - Never mention macros textually in comments (rpm expands them anywhere).
# - Bumps are manual: edit Version + changelog, push, the cascade rebuilds.
%define debug_package %{nil}

Name:           rmtmp
Version:        1.0.0
Release:        1%{?dist}
Summary:        Root-only secure cleanup of old files in /tmp and /var/tmp.
License:        Apache-2.0
URL:            https://github.com/halcyon-linux/python-packages
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel

%description
Root-only secure cleanup of old files in /tmp and /var/tmp. Halcyon helper tool; stdlib-only.

%prep
%autosetup -p1

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l rmtmp
install -Dpm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE

%files -f %pyproject_files
%license %{_licensedir}/%{name}/LICENSE
%{_bindir}/rmtmp

%changelog
* Wed Sep 30 2026 halcyon-autoupdate <aahsnr041@proton.me> - 1.0.0-1
- initial packaging (vendored halcyon-original sources)
