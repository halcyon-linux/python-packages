# dynamic-fixes: halcyon Python port of the bazzite-dynamic-fixes
# helper from the bazzite fork (Apache-2.0); sources vendored under
# pkgs/dynamic-fixes/src, no upstream tarball exists. Submitted to
# Copr aahsnr-work/python-packages. Bumps are manual: edit Version +
# changelog, push, the cascade rebuilds.
%define debug_package %{nil}

Name:           dynamic-fixes
Version:        1.0.0
Release:        1%{?dist}
Summary:        Toggle the GSK_RENDERER=gl workaround when an Intel GPU is in use.
License:        Apache-2.0
URL:            https://github.com/halcyon-linux/python-packages
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel
Requires:       systemd

%description
User-session helper for Halcyon images: writes GSK_RENDERER=gl to the user
environment.d when the xe or i915 kernel module is loaded and in use (Intel
GPUs need it to avoid GTK4/libadwaita glitches), removes the file again when
no Intel GPU is active, and reloads the user systemd manager after either
change.

%prep
%autosetup -p1

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l dynamic_fixes
install -Dpm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE

%files -f %pyproject_files
%license %{_licensedir}/%{name}/LICENSE
%{_bindir}/dynamic-fixes

%changelog
* Sun Oct 18 2026 halcyon-autoupdate <aahsnr041@proton.me> - 1.0.0-1
- initial packaging (Python port of the bazzite-dynamic-fixes helper)
