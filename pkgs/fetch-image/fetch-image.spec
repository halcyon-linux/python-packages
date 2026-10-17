# fetch-image: halcyon Python port of the bazzite-fetch-image shell
# helper from the bazzite fork (Apache-2.0); sources vendored under
# pkgs/fetch-image/src, no upstream tarball exists. Submitted to Copr
# aahsnr-work/python-packages. Bumps are manual: edit Version + changelog,
# push, the cascade rebuilds.
%define debug_package %{nil}

Name:           fetch-image
Version:        1.0.0
Release:        1%{?dist}
Summary:        Print image name:branch plus a signed/unsigned marker for fastfetch.
License:        Apache-2.0
URL:            https://github.com/halcyon-linux/python-packages
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-devel
Requires:       rpm-ostree

%description
fastfetch command helper: prints the image name and branch from
image-info.json, followed by a signature marker. Signed rpm-ostree
deployments get a plain glyph; unsigned ones get a blinking red glyph.

%prep
%autosetup -p1

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l fetch_image
install -Dpm644 LICENSE %{buildroot}%{_licensedir}/%{name}/LICENSE

%files -f %pyproject_files
%license %{_licensedir}/%{name}/LICENSE
%{_bindir}/fetch-image

%changelog
* Sun Oct 18 2026 halcyon-autoupdate <aahsnr041@proton.me> - 1.0.0-1
- initial packaging (Python port of the bazzite-fetch-image helper)
