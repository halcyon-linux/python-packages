# halcyon-powersave: halcyon Python port of the bazzite-powersave helper from
# the bazzite fork (Apache-2.0); sources vendored under
# pkgs/halcyon-powersave/src, no upstream tarball exists. Submitted to Copr
# aahsnr-work/python-packages. Bumps are manual: edit Version + changelog,
# push, the cascade rebuilds.
%define debug_package %{nil}

Name:           halcyon-powersave
Version:        1.0.0
Release:        1%{?dist}
Summary:        Switch the power-profiles-daemon active profile from the command line.
License:        Apache-2.0
URL:            https://github.com/halcyon-linux/python-packages
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel
Requires:       glib2

%description
Sets the power-profiles-daemon ActiveProfile through gdbus: no argument (or
anything but 0) selects power-saver; 0 selects balanced. Used by ujust
recipes and desktop keybindings.

%prep
%autosetup -p1

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l halcyon_powersave
install -Dpm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE

%files -f %pyproject_files
%license %{_licensedir}/%{name}/LICENSE
%{_bindir}/halcyon-powersave

%changelog
* Sun Oct 18 2026 halcyon-autoupdate <aahsnr041@proton.me> - 1.0.0-1
- initial packaging (Python port of the bazzite-powersave helper)
