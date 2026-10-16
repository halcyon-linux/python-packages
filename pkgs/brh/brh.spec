# brh: halcyon-original Python helper; sources vendored under
# pkgs/brh/src (no upstream tarball exists). Submitted to Copr
# aahsnr-work/python-packages. Bumps are manual: edit Version + changelog,
# push, the cascade rebuilds.
%define debug_package %{nil}

Name:           brh
Version:        1.0.0
Release:        1%{?dist}
Summary:        Interactive rpm-ostree rollback and rebase helper.
License:        Apache-2.0
URL:            https://github.com/halcyon-linux/python-packages
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel
Requires:       rpm-ostree
Requires:       skopeo

%description
Interactive rpm-ostree rollback and rebase helper for Halcyon images. Python 3.13+, stdlib-only.

%prep
%autosetup -p1

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l brh
install -Dpm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE

%files -f %pyproject_files
%license %{_licensedir}/%{name}/LICENSE
%{_bindir}/brh

%changelog
* Sat Oct 17 2026 halcyon-autoupdate <aahsnr041@proton.me> - 1.0.0-1
- initial packaging (vendored halcyon-original sources)
