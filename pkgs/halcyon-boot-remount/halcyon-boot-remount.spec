# halcyon-boot-remount: halcyon Python port of the bazzite-boot-remount shell
# helper from the bazzite fork (Apache-2.0); sources vendored under
# pkgs/halcyon-boot-remount/src, no upstream tarball exists. Submitted to Copr
# aahsnr-work/python-packages. Bumps are manual: edit Version + changelog,
# push, the cascade rebuilds.
%define debug_package %{nil}

Name:           halcyon-boot-remount
Version:        1.0.0
Release:        1%{?dist}
Summary:        Remount /boot read-write for an operation and restore the prior state.
License:        Apache-2.0
URL:            https://github.com/halcyon-linux/python-packages
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel
Requires:       util-linux-core

%description
CLI replacement for the sourced bazzite-boot-remount shell function. `rw`
remounts /boot read-write when it is read-only and prints 1 (or 0 when no
remount was needed); `ro 1` restores the read-only mount. Used by the ujust
grub recipes, which need /boot writable on bootc images.

%prep
%autosetup -p1

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l halcyon_boot_remount
install -Dpm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE

%files -f %pyproject_files
%license %{_licensedir}/%{name}/LICENSE
%{_bindir}/halcyon-boot-remount

%changelog
* Sun Oct 18 2026 halcyon-autoupdate <aahsnr041@proton.me> - 1.0.0-1
- initial packaging (Python port of the bazzite-boot-remount helper)
