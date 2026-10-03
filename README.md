# ssh-ls

**Stop digging through shell history for that SSH command.**

English · [简体中文](README.zh-CN.md) · [Usage](docs/usage.md) · [Releases](https://github.com/Moviw/ssh-ls/releases)

[![CI](https://github.com/Moviw/ssh-ls/actions/workflows/ci.yml/badge.svg)](https://github.com/Moviw/ssh-ls/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Moviw/ssh-ls)](https://github.com/Moviw/ssh-ls/releases/latest)
[![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

I didn't want to keep typing `ssh ...`. My SSH config and shell history already held the destinations—I wanted to pick one instead of remembering which alias or command to type.

ssh-ls is a terminal host picker for people who move between remote machines throughout the day. It turns the connections you already have into a searchable list, then hands the selected host to your system's `ssh`.

## Your existing hosts, one list

Run `ssh-ls`. The picker reads literal host aliases from `.ssh/config` and supported SSH commands from your bash or zsh history. Press `/` to search, select a host, and press `Enter`. The picker closes, native SSH takes over your terminal, and the session ends back at your shell.

Recent puts known, timestamped connections first. Press `Space` to star the hosts you return to, and find them under Favorites next time. There's no second host inventory you have to fill in before getting started.

Your existing OpenSSH setup still handles keys, agents, jump hosts, and authentication. ssh-ls doesn't replace the SSH client or manage passwords.

## See it before using your own hosts

![ssh-ls showing a searchable host list and connection details](docs/demo.svg)

The screenshot uses fictional hosts. Run `ssh-ls --demo` after installing to try the picker without reading your SSH files, contacting servers, or saving changes.

## Install and connect

Requires macOS or Linux, curl, and OpenSSH.

```sh
curl -fsSL https://raw.githubusercontent.com/Moviw/ssh-ls/main/install.sh | sh
ssh-ls
```

Choose a host and press `Enter`. If Recent is empty, switch to All to see your configured hosts. No import wizard or account to create.

The installer gets the latest stable GitHub Release in an isolated [uv](https://docs.astral.sh/uv/) environment. It installs uv and downloads Python 3.11 if needed; no sudo, Git, or preinstalled Python is required. Your SSH files, shell profiles, and saved settings stay unchanged. If the command isn't on PATH, the installer prints its full path.

<details>
<summary>Inspect the installer or use uv / pipx directly</summary>

```sh
curl -fsSL https://raw.githubusercontent.com/Moviw/ssh-ls/main/install.sh -o install.sh
less install.sh
sh install.sh
```

With Python 3.11+, you can install the same stable asset directly:

```sh
uv tool install https://github.com/Moviw/ssh-ls/releases/latest/download/ssh-ls.tar.gz
# or
pipx install https://github.com/Moviw/ssh-ls/releases/latest/download/ssh-ls.tar.gz
```

Built-in update and uninstall support official uv installations. For pipx or source installs, use the original installation method instead.

</details>

## The keys you'll use

| Key | Action |
| --- | --- |
| `/` | Search by name, host, user, or jump host |
| `j` / `k`, `↑` / `↓` | Select a host |
| `Tab`, `←` / `→` | All · Recent · Favorites |
| `Enter` | Connect |
| `Space` | Toggle favorite |
| `o` | Settings and theme gallery |
| `?` | Show all shortcuts |
| `q` | Quit |

The picker opens on Recent. Press `o` to choose Favorites or All as your start page. Host edits, sorting, remote commands, and the remaining controls are in the [usage guide](docs/usage.md).

## Make it yours

Settings has separate General and Themes tabs. Choose a theme card to preview it across the app; Save keeps it, and Esc discards the preview. You can also adjust accent color, row spacing, and ASCII display.

Tokyo Night is the default. The gallery includes Dracula, Catppuccin Mocha, Nord, Gruvbox Dark, Rosé Pine, Minimal, Cyberpunk, Ocean, and Retro.

<details>
<summary>See the ten-theme gallery</summary>

![Ten selectable theme previews in ssh-ls Settings](docs/themes.svg)

</details>

## Update or uninstall

```sh
ssh-ls update
ssh-ls uninstall
```

Uninstall asks for confirmation and removes only the app. Favorites, settings, SSH files, uv, and Python are kept. `ssh-ls uninstall --yes` is available for explicit noninteractive removal.

Interactive launches check public GitHub release metadata in the background. A newer stable version appears in a small banner with `ssh-ls update`; nothing upgrades automatically. Offline failures are silent, and no SSH config or history is sent. Demo mode stays offline.

## What stays unchanged

**Will it edit `.ssh/config`?** No. Host edits are local overrides under `${XDG_CONFIG_HOME:-~/.config}/ssh-ls/`. Native OpenSSH remains the source of truth for connections; displayed config fields are estimates.

**Will it replay shell history commands?** No. The importer extracts connection fields, discards remote commands, and skips unsupported or shell-dependent syntax. Not every history entry will appear. [Parsing limits](docs/usage.md#config-and-history).

**Does it connect or probe hosts on startup?** No. SSH starts when you choose a host. Hosts you manually mark as production require confirmation. The `v` shortcut offers an explicit effective-config preview after a warning: OpenSSH's `Match exec` can execute local commands even during that preview.

**Does it change how SSH sessions work?** Native `ssh` inherits your terminal, and ssh-ls preserves its exit status. Recent records connection attempts, not proof that authentication succeeded.

## Contributing

Found a missing history format or a terminal layout that doesn't fit? [Open an issue](https://github.com/Moviw/ssh-ls/issues) with your OS, Python version, and a fictional example. Never include private keys, real host inventories, or real shell history.

Small, focused pull requests are welcome. See the [development guide](docs/development.md). Version changes are listed in [GitHub Releases](https://github.com/Moviw/ssh-ls/releases).

---

*Dedicated to my research days in Nakayama Lab.*
