# ssh-ls

[English](README.md) · 简体中文 · [使用说明](docs/usage.md) · [版本记录](https://github.com/Moviw/ssh-ls/releases) · [参与开发](#参与开发)

[![CI](https://github.com/Moviw/ssh-ls/actions/workflows/ci.yml/badge.svg)](https://github.com/Moviw/ssh-ls/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Moviw/ssh-ls)](https://github.com/Moviw/ssh-ls/releases/latest)
[![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**别再翻历史找那条 SSH 命令了。**

我就是懒，不想每次自己打 `ssh ...`。连接信息明明已经在 `.ssh/config` 和历史记录里，我想直接选一台，不用再想该敲哪个别名、找哪条命令。

如果你每天都在几台远程机器之间切换，ssh-ls 可以把已有的连接整理成终端里的主机列表。你选中一台，系统的 `ssh` 接着完成连接。


## 已有的主机，直接选

运行 `ssh-ls`，选择器会读取 `.ssh/config` 中明确写出的主机别名，以及 bash、zsh 历史里支持的 SSH 命令。按 `/` 搜索，选中主机，再按 `Enter`。选择器退出，原生 SSH 接管终端；会话结束后，你回到原来的 shell。

Recent 把有时间记录的连接按最近使用排序。按 `Space` 收藏常用主机，下次在 Favorites 里找到它们。开始使用前，不用再手动录一份主机清单。

密钥、SSH Agent、跳板机和认证仍由现有的 OpenSSH 配置处理。ssh-ls 不替换 SSH 客户端，也不管理密码。

## 先看看，再用自己的主机

![ssh-ls 的主机列表和连接详情](docs/demo.svg)

截图使用虚构主机。安装后运行 `ssh-ls --demo` 就能试用界面，不读取你的 SSH 文件、不联系服务器，也不保存修改。

## 安装，然后连接

需要 macOS 或 Linux、curl 和 OpenSSH。

```sh
curl -fsSL https://raw.githubusercontent.com/Moviw/ssh-ls/main/install.sh | sh
ssh-ls
```

选一台主机，按回车。如果 Recent 还没有记录，切到 All 就能看到配置中的主机。不用导入向导，也不用注册账号。

安装器从 GitHub 获取最新稳定 Release，用 [uv](https://docs.astral.sh/uv/) 创建独立环境；需要时会安装 uv、下载 Python 3.11。不需要 sudo、Git 或预装 Python。SSH 文件、shell 启动文件和已有设置都不改。如果命令不在 PATH 中，安装器会提示完整启动路径。

<details>
<summary>先检查安装器，或直接用 uv / pipx 安装</summary>

```sh
curl -fsSL https://raw.githubusercontent.com/Moviw/ssh-ls/main/install.sh -o install.sh
less install.sh
sh install.sh
```

已有 Python 3.11+ 的话，也可以直接安装相同的稳定发布包：

```sh
uv tool install https://github.com/Moviw/ssh-ls/releases/latest/download/ssh-ls.tar.gz
# 或
pipx install https://github.com/Moviw/ssh-ls/releases/latest/download/ssh-ls.tar.gz
```

内置更新和卸载命令只管理官方 uv 安装。pipx 和源码安装请使用原来的安装方式。

</details>

## 最常用的几个键

| 按键 | 操作 |
| --- | --- |
| `/` | 按名称、主机、用户名或跳板机搜索 |
| `j` / `k`、`↑` / `↓` | 选择主机 |
| `Tab`、`←` / `→` | 切换 All、Recent、Favorites |
| `Enter` | 连接 |
| `Space` | 收藏或取消收藏 |
| `o` | 设置和主题画廊 |
| `?` | 查看全部快捷键 |
| `q` | 退出 |

默认打开 Recent。按 `o` 可以把启动页改为 Favorites 或 All。主机编辑、排序、远程命令和其他操作见[使用说明](docs/usage.md)。

## 选一个顺眼的主题

Settings 分为 General 和 Themes 两个标签页。选择主题卡片即可预览整个界面，Save 保存，Esc 放弃预览。强调色、行距和 ASCII 显示也可以调整。

默认主题是 Tokyo Night。另有 Dracula、Catppuccin Mocha、Nord、Gruvbox Dark、Rosé Pine、Minimal、Cyberpunk、Ocean 和 Retro。

<details>
<summary>查看十套主题的预览画廊</summary>

![Settings 中的十套主题预览](docs/themes.svg)

</details>

## 更新和卸载

```sh
ssh-ls update
ssh-ls uninstall
```

卸载需要确认，只移除应用，保留收藏、设置、SSH 文件、uv 和 Python。明确需要非交互卸载时，可以用 `ssh-ls uninstall --yes`。

正常启动时会在后台检查 GitHub 的公开版本信息；有新稳定版本时，小提示条会显示版本和 `ssh-ls update`。不会自动升级，离线时静默，不发送 SSH 配置或历史。Demo 模式不联网。

## 哪些东西不会变

**会修改 `.ssh/config` 吗？** 不会。主机编辑只作为本地覆盖项保存在 `${XDG_CONFIG_HOME:-~/.config}/ssh-ls/`。连接行为以原生 OpenSSH 为准，界面里的配置字段是估计值。

**会重放历史命令吗？** 不会。导入器提取连接字段，丢弃远程命令，跳过不支持或依赖 shell 上下文的语法。不是每条历史记录都会出现。[解析范围](docs/usage.md#config-and-history)。

**启动就会连接或探测主机吗？** 不会。你选择主机后才启动 SSH。手动标记为生产环境的主机会要求确认。`v` 提供生效配置预览，但会先提示风险：即使只是预览，OpenSSH 的 `Match exec` 也可能执行本地命令。

**会改变 SSH 会话的用法吗？** 系统 `ssh` 直接接管终端，退出码照常保留。Recent 记录的是连接尝试，不代表认证已经成功。

## 参与开发

遇到了无法识别的历史命令，或者终端宽度下的布局问题？[提交 issue](https://github.com/Moviw/ssh-ls/issues) 时，请附上操作系统、Python 版本和虚构的复现样例。不要提交私钥、真实主机清单或真实 shell 历史。

欢迎范围明确的小型 PR。[开发说明](docs/development.md)里有测试方式；版本改动记录在 [GitHub Releases](https://github.com/Moviw/ssh-ls/releases)。

---

*Dedicated to my research days in Nakayama Lab.*
