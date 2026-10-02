#!/bin/sh
# Restore an application state COPY from its sibling .bak. Does not touch SSH config.
set -eu
if [ "$#" -ne 1 ]; then
    printf 'Usage: %s STATE_COPY\nRestore STATE_COPY from STATE_COPY.bak.\n' "$0" >&2
    exit 2
fi
case "$1" in
    /*) target=$1 ;;
    *) target=$PWD/$1 ;;
esac
baseline=$target.bak
if [ ! -f "$baseline" ] || [ -L "$target" ] || [ -L "$baseline" ]; then
    printf 'Refusing restore: missing regular sibling backup or symbolic link.\n' >&2
    exit 1
fi
umask 077
temporary=$target.restore.$$
trap 'rm -f "$temporary"' EXIT HUP INT TERM
cp "$baseline" "$temporary"
chmod 600 "$temporary"
mv "$temporary" "$target"
printf 'Restored pristine bytes from sibling backup.\n'
