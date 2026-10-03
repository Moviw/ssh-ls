#!/bin/sh
# Install or update ssh-ls in a user-owned, isolated uv environment.
set -eu

fail() { printf 'ssh-ls: %s\n' "$*" >&2; exit 1; }

case "$(uname -s)" in
    Darwin|Linux) ;;
    *) fail 'Only macOS and Linux are supported.' ;;
esac
command -v curl >/dev/null 2>&1 || fail 'curl is required.'
command -v ssh >/dev/null 2>&1 || fail 'OpenSSH is required. Install it using your system package manager.'
: "${HOME:?HOME must be set}"

if command -v uv >/dev/null 2>&1; then
    uv_bin=$(command -v uv)
elif [ -x "$HOME/.local/bin/uv" ]; then
    uv_bin=$HOME/.local/bin/uv
else
    printf 'Installing uv from astral.sh (without changing shell profiles)...\n'
    temporary=$(mktemp -d "${TMPDIR:-/tmp}/ssh-ls-install.XXXXXX")
    trap 'rm -rf "$temporary"' 0
    trap 'exit 1' HUP INT TERM
    curl --proto '=https' --tlsv1.2 -fsSL https://astral.sh/uv/install.sh -o "$temporary/uv-install.sh"
    UV_INSTALL_DIR="$HOME/.local/bin" UV_NO_MODIFY_PATH=1 sh "$temporary/uv-install.sh"
    uv_bin=$HOME/.local/bin/uv
    [ -x "$uv_bin" ] || fail 'uv installation did not produce an executable.'
fi

printf 'Installing ssh-ls from github.com/Moviw/ssh-ls...\n'
# The source archive avoids requiring Git or developer tools on a fresh Mac.
"$uv_bin" tool install --upgrade --refresh --python 3.11 \
    https://github.com/Moviw/ssh-ls/archive/refs/heads/main.tar.gz
bin_dir=$("$uv_bin" tool dir --bin)
"$bin_dir/ssh-ls" --version
printf '\nInstalled: %s/ssh-ls\n' "$bin_dir"

case ":${PATH:-}:" in
    *":$bin_dir:"*) printf 'Run: ssh-ls\n' ;;
    *) printf 'Run directly: "%s/ssh-ls"\nAdd "%s" to your shell PATH to use ssh-ls by name.\n' "$bin_dir" "$bin_dir" ;;
esac
printf 'To update, run this installer again. Your SSH files and ssh-ls settings are unchanged.\n'
