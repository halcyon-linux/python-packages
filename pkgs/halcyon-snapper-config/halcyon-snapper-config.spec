# halcyon-snapper-config: halcyon Python port of the bazzite-snapper-config
# helper from the bazzite fork (Apache-2.0); sources vendored under
# pkgs/halcyon-snapper-config/src, no upstream tarball exists. Submitted to
# Copr aahsnr-work/python-packages. Bumps are manual: edit Version +
# changelog, push, the cascade rebuilds.
%define debug_package %{nil}

Name:           halcyon-snapper-config
Version:        1.0.0
Release:        1%{?dist}
Summary:        Manage the root snapper config: enable, clean, wipe, or disable it.
License:        Apache-2.0
URL:            https://github.com/halcyon-linux/python-packages
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel
Requires:       btrfs-assistant
Requires:       snapper
Requires:       sudo
Requires:       systemd
Requires:       zenity

%description
Front-end for snapper on Halcyon images, used by the ujust snapshot
recipes: enable (default) creates the /var/home config with zero retention
and opens btrfs-assistant so the user can pick real values; clean runs the
number and timeline cleanups; wipe resets the defaults, cleans and disables
snapshots; any other value deletes the root config and stops the timeline
and boot timers.

%prep
%autosetup -p1

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l halcyon_snapper_config
install -Dpm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE

%files -f %pyproject_files
%license %{_licensedir}/%{name}/LICENSE
%{_bindir}/halcyon-snapper-config

%changelog
* Sun Oct 18 2026 halcyon-autoupdate <aahsnr041@proton.me> - 1.0.0-1
- initial packaging (Python port of the bazzite-snapper-config helper)
