# ublue-motd: halcyon-original Python helper; sources vendored under
# pkgs/ublue-motd/src (no upstream tarball exists). Submitted to Copr
# aahsnr-work/python-packages. Bumps are manual: edit Version + changelog,
# push, the cascade rebuilds.
%define debug_package %{nil}

Name:           ublue-motd
Version:        1.0.1
Release:        1%{?dist}
Summary:        Login banner for bootc images: image info, boot health, staged updates, tips.
License:        Apache-2.0
URL:            https://github.com/halcyon-linux/python-packages
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel
Requires:       glow
Requires:       rpm-ostree

%description
Renders the login MOTD banner for ublue-based bootc images. Reads
image-info.json, greenboot boot status, staged rpm-ostree deployments, disk
pressure and rotating tips; renders a markdown template through glow, falling
back to plain markdown when glow or a terminal is unavailable.

%prep
%autosetup -p1

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l ublue_motd
install -Dpm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE

%files -f %pyproject_files
%license %{_licensedir}/%{name}/LICENSE
%{_bindir}/ublue-motd

%changelog
* Sun Oct 18 2026 halcyon-autoupdate <aahsnr041@proton.me> - 1.0.1-1
- Read disk pressure from /sysroot on composefs-booted systems (the
  overlay at "/" always reads 100% full); pin rpm-ostree failure modes
  and the glow fallback in tests
* Sat Oct 17 2026 halcyon-autoupdate <aahsnr041@proton.me> - 1.0.0-1
- initial packaging (vendored halcyon-original sources)
