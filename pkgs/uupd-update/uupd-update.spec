# uupd-update: halcyon-original Python helper; sources vendored under
# pkgs/uupd-update/src (no upstream tarball exists). Submitted to Copr
# aahsnr-work/python-packages. Bumps are manual: edit Version + changelog,
# push, the cascade rebuilds.
%define debug_package %{nil}

Name:           uupd-update
Version:        1.0.0
Release:        1%{?dist}
Summary:        Front-end for uupd: attach to or start the update service, stream its journal.
License:        Apache-2.0
URL:            https://github.com/halcyon-linux/python-packages
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel
Requires:       systemd
Requires:       uupd

%description
Front-end for uupd on bootc images: attaches to a running uupd.service or
uupd-manual.service and streams its journal, or starts uupd-manual.service
and waits; exits with the service's exit code.

%prep
%autosetup -p1

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l uupd_update
install -Dpm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE

%files -f %pyproject_files
%license %{_licensedir}/%{name}/LICENSE
%{_bindir}/uupd-update

%changelog
* Sat Oct 17 2026 halcyon-autoupdate <aahsnr041@proton.me> - 1.0.0-1
- initial packaging (vendored halcyon-original sources)
