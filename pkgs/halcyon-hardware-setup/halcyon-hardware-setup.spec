# halcyon-hardware-setup: halcyon Python port of the bazzite-hardware-setup
# helper from the bazzite fork (Apache-2.0); sources vendored under
# pkgs/halcyon-hardware-setup/src, no upstream tarball exists. Submitted to
# Copr aahsnr-work/python-packages. Bumps are manual: edit Version +
# changelog, push, the cascade rebuilds.
%define debug_package %{nil}

Name:           halcyon-hardware-setup
Version:        1.0.0
Release:        1%{?dist}
Summary:        One-shot host setup: kernel args, hostname, and image identity state.
License:        Apache-2.0
URL:            https://github.com/halcyon-linux/python-packages
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel
Requires:       rpm-ostree
Requires:       systemd

%description
One-shot hardware setup for the current machine. Runs from
halcyon-hardware-setup.service and re-runs whenever the image identity
(name/branch/Fedora version) or HWS_VER changes: applies the bluetooth and
virtualization kernel arguments, removes nomodeset, replaces over-long
hostnames, records the identity under /etc/bazzite, and reboots when the
kernel arguments changed.

%prep
%autosetup -p1

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l halcyon_hardware_setup
install -Dpm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE

%files -f %pyproject_files
%license %{_licensedir}/%{name}/LICENSE
%{_bindir}/halcyon-hardware-setup

%changelog
* Sun Oct 18 2026 halcyon-autoupdate <aahsnr041@proton.me> - 1.0.0-1
- initial packaging (Python port of the bazzite-hardware-setup helper)
