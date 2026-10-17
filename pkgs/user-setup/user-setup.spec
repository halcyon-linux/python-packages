# user-setup: halcyon Python port of bazzite-user-setup and
# bazzite-privileged-user-setup from the bazzite fork (Apache-2.0); sources
# vendored under pkgs/user-setup/src, no upstream tarball exists.
# Submitted to Copr aahsnr-work/python-packages. Bumps are manual: edit
# Version + changelog, push, the cascade rebuilds.
%define debug_package %{nil}

Name:           user-setup
Version:        1.0.0
Release:        1%{?dist}
Summary:        Per-user setup: privileged one-time tweaks plus default template files.
License:        Apache-2.0
URL:            https://github.com/halcyon-linux/python-packages
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel
Requires:       polkit
Requires:       shadow-utils
Requires:       systemd
Requires:       xdg-user-dirs

%description
Per-user setup for Halcyon images. user-setup runs from
user-setup.service as the desktop user, keeps its version state
under $XDG_DATA_HOME/bazzite, and calls privileged-user-setup
through polkit for the root-only steps (NTP, tailscale operator, libvirt
group). It then symlinks the shipped mangohud/vkBasalt/dxvk template configs
into the user's Templates directory.

%prep
%autosetup -p1

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l user_setup
install -Dpm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE

%files -f %pyproject_files
%license %{_licensedir}/%{name}/LICENSE
%{_bindir}/user-setup
%{_bindir}/privileged-user-setup

%changelog
* Sun Oct 18 2026 halcyon-autoupdate <aahsnr041@proton.me> - 1.0.0-1
- initial packaging (Python port of the bazzite user setup helpers)
