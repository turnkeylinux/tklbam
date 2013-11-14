#!/bin/bash -e
# script adds the correct apt source and installs package
# Author: Liraz Siri <liraz@turnkeylinux.org>

if [ -n "$1" ]; then
    PACKAGE="$1"
fi

set ${APT_URL:="http://archive.turnkeylinux.org/debian"}
set ${APT_KEY:=A16EB94D}

if [ -z "$PACKAGE" ]; then
    cat<<EOF
Syntax: $0 <package>
Script adds an apt source if needed and installs a package
Environment variables:

    PACKAGE      package to install
    APT_URL      apt source url (default: $APT_URL)
    APT_KEY      apt source key (default: $APT_KEY)
EOF
    exit 1
fi

error() {
    1>&2 echo "error: $1"
    exit 1
}

get_debian_dist() {
    case "$1" in 
        6.*) echo squeeze ;;
        7.*) echo wheezy ;;
        8.*) echo jessie ;;
        */*) echo $1 | sed 's|/.*||' ;;
    esac
}


if ! rgrep . /etc/apt/sources.list* | sed 's/#.*//' | grep -q $APT_URL; then
    [ -f /etc/debian_version ] || error "not a Debian derived system - no /etc/debian_version file"

    apt_name=$(echo $APT_URL | sed 's|.*//||; s|/.*||')
    apt_file="/etc/apt/sources.list.d/${apt_name}.list"

    debian_dist=$(get_debian_dist "$(cat /etc/debian_version)")
    echo "deb $APT_URL $debian_dist main" > $apt_file

    echo "+ apt-key adv --keyserver pgpkeys.mit.edu --recv-keys $APT_KEY"
    apt-key adv --keyserver pgpkeys.mit.edu --recv-keys $APT_KEY

    echo
    echo "Added $APT_URL package source to $apt_file"
fi

set -x
apt-get update

if 0>&2 tty > /dev/null; then
    0>&2 apt-get install $PACKAGE
else
    echo "To finish execute this command:"
    echo 
    echo "    apt-get install $PACKAGE"
    echo
fi
    
