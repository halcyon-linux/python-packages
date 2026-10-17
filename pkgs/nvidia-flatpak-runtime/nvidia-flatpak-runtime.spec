# nvidia-flatpak-runtime: halcyon Python port of
# ublue-nvidia-flatpak-runtime-sync and -notify from the bazzite fork
# (Apache-2.0); sources vendored under pkgs/nvidia-flatpak-runtime/src,
# no upstream tarball exists. Submitted to Copr aahsnr-work/python-packages.
# Bumps are manual: edit Version + changelog, push, the cascade rebuilds.
%define debug_package %{nil}

Name:           nvidia-flatpak-runtime
Version:        1.0.0
Release:        1%{?dist}
Summary:        Check, install, and notify about NVIDIA Flatpak runtimes matching the driver.
License:        Apache-2.0
URL:            https://github.com/halcyon-linux/python-packages
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel
Requires:       flatpak
Requires:       libnotify
Requires:       xdg-utils

%description
Workaround for flatpak/flatpak#3907: nvidia-flatpak-runtime-sync
exits 0 when the org.freedesktop.Platform.GL(.GL32).nvidia-<driver> runtimes
are missing (so the sync service runs) and 1 when they are in place, and
installs both runtimes from flathub when asked to sync.
nvidia-flatpak-runtime-notify shows a notification offering the docs
link, the bazaar flatpak updater, or the yafti runtime update.

%prep
%autosetup -p1

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l nvidia_flatpak_runtime
install -Dpm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE

%files -f %pyproject_files
%license %{_licensedir}/%{name}/LICENSE
%{_bindir}/nvidia-flatpak-runtime-sync
%{_bindir}/nvidia-flatpak-runtime-notify

%changelog
* Sun Oct 18 2026 halcyon-autoupdate <aahsnr041@proton.me> - 1.0.0-1
- initial packaging (Python port of the nvidia flatpak runtime helpers)
