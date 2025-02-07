Name:           ssh-commander
Version:        %{version}
Release:        1%{?dist}
Summary:        Execute commands on multiple servers via SSH

License:        MIT
URL:            https://github.com/AthenaNetworks/ssh_commander
Source0:        %{name}-%{version}.tar.gz

BuildArch:      x86_64
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-pip

Requires:       python3
Requires:       python3-paramiko
Requires:       python3-yaml
Requires:       python3-colorama

%description
SSH Commander is a command-line tool that allows you to execute commands on multiple servers via SSH.
It supports server tags for grouping, key-based authentication, and configuration management.

%prep
%autosetup

%build
python3 -m pip install --no-deps -r requirements.txt
pyinstaller --onefile --noupx --name %{name} \
  --exclude-module _bootlocale \
  --exclude-module PIL \
  --exclude-module numpy \
  --exclude-module pandas \
  --exclude-module matplotlib \
  --exclude-module tkinter \
  --exclude-module unittest \
  --exclude-module email \
  --exclude-module http \
  --exclude-module html \
  --exclude-module xml \
  --exclude-module pydoc \
  ssh_commander.py

%install
rm -rf $RPM_BUILD_ROOT
mkdir -p %{buildroot}%{_bindir}
mkdir -p %{buildroot}%{_sysconfdir}/ssh-commander
install -m 755 dist/%{name} %{buildroot}%{_bindir}/%{name}
install -m 644 servers.yaml.example %{buildroot}%{_sysconfdir}/ssh-commander/servers.yaml.example

%files
%{_bindir}/%{name}
%{_sysconfdir}/ssh-commander/servers.yaml.example
%doc README.md

%changelog
* Thu Feb 07 2025 Josh Finlay <josh@athenanetworks.com.au> - %{version}-1
- Initial RPM release
