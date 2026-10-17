# dlss-swapper: halcyon Python port of dlss-swapper and
# dlss-swapper-dll from the bazzite fork (originally from CachyOS,
# GPL-3.0-only); sources vendored under pkgs/dlss-swapper/src, no
# upstream tarball exists. Submitted to Copr aahsnr-work/python-packages.
# Bumps are manual: edit Version + changelog, push, the cascade rebuilds.
%define debug_package %{nil}

Name:           dlss-swapper
Version:        1.0.0
Release:        1%{?dist}
Summary:        Steam launch wrappers that force the latest DLSS presets via DXVK-NVAPI.
License:        GPL-3.0-only
URL:            https://github.com/halcyon-linux/python-packages
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel

%description
Two Steam launch-option wrappers for NVIDIA systems. dlss-swapper
sets PROTON_ENABLE_NGX_UPDATER and forces the latest DLSS presets for SR, RR
and frame generation, so the DLSS DLLs are refreshed from the driver and
take over future updates. dlss-swapper-dll sets the same overrides
but leaves the DLLs the game ships with in place. Prefix the game command
with either wrapper in the Steam launch options.

%prep
%autosetup -p1

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l dlss_swapper
install -Dpm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE

%files -f %pyproject_files
%license %{_licensedir}/%{name}/LICENSE
%{_bindir}/dlss-swapper
%{_bindir}/dlss-swapper-dll

%changelog
* Sun Oct 18 2026 halcyon-autoupdate <aahsnr041@proton.me> - 1.0.0-1
- initial packaging (Python port of the CachyOS DLSS preset wrappers)
