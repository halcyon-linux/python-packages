# rmi: halcyon-original Python helper; sources vendored under
# pkgs/rmi/src (no upstream tarball exists). Submitted to Copr
# aahsnr-work/python-packages. Bumps are manual: edit Version + changelog,
# push, the cascade rebuilds.
%define debug_package %{nil}

Name:           rmi
Version:        2.0.1
Release:        1%{?dist}
Summary:        Safe removal to the XDG trash with collision handling.
License:        Apache-2.0
URL:            https://github.com/halcyon-linux/python-packages
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel

%description
Safe removal to the XDG trash with collision handling. Halcyon helper tool; stdlib-only.

%prep
%autosetup -p1

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l rmi
install -Dpm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE

%files -f %pyproject_files
%license %{_licensedir}/%{name}/LICENSE
%{_bindir}/rmi

%changelog
* Wed Sep 30 2026 halcyon-autoupdate <aahsnr041@proton.me> - 2.0.1-1
- initial packaging (vendored halcyon-original sources)
