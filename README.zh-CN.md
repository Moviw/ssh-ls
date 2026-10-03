# ssh-ls

**别再翻历史找那条 SSH 命令了。**

[English](README.md) · [使用说明](docs/usage.md) · [参与开发](docs/development.md)

[![CI](https://github.com/Moviw/ssh-ls/actions/workflows/ci.yml/badge.svg)](https://github.com/Moviw/ssh-ls/actions/workflows/ci.yml)
[![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

我就是懒，不想每次自己打 `ssh ...`。连接信息明明已经在 `.ssh/config` 和历史记录里，我想直接选一台，不用再想该敲哪个别名、找哪条命令。

## 选一台，按回车

运行 `ssh-ls`，你会看到 SSH 配置里的主机，以及从 bash、zsh 历史记录中识别出的连接。按 `/` 搜索，用 `j` / `k` 或方向键选中主机，再按 `Enter`。选择器退出，系统的 `ssh` 接管终端；连接结束后，你回到原来的 shell。

常用的主机按空格收藏。**Recent** 合并 ssh-ls 中的连接尝试和 shell 历史里发现的连接，已知时间的记录按最近使用排序。原来的配置和历史文件都不改，ssh-ls 单独保存收藏和连接记录。

密钥、SSH Agent、跳板机和认证仍然由 OpenSSH 处理。ssh-ls 只负责帮你选主机，不另造一个 SSH 客户端，也不管理密码。

![ssh-ls 展示配置与历史中的主机](docs/demo.svg)

*截图使用虚构数据。运行 `ssh-ls --demo` 即可体验，不读取你的 SSH 文件。*

## 安装

需要 macOS 或 Linux、curl 和 OpenSSH。

```sh
curl -fsSL https://raw.githubusercontent.com/Moviw/ssh-ls/main/install.sh | sh
ssh-ls
```

脚本用 [uv](https://docs.astral.sh/uv/) 创建独立环境；没装 uv 或 Python 时，会自动安装 uv 和下载 Python 3.11。不需要 sudo、Git，也不用提前装 Python。不会修改 shell 启动文件、SSH 配置或 ssh-ls 设置。如果命令目录不在 PATH 里，安装后会提示完整启动路径。

安装来源是最新稳定 GitHub Release。更新用 `ssh-ls update`，卸载用 `ssh-ls uninstall`。想先检查脚本，可以下载后再执行：

```sh
curl -fsSL https://raw.githubusercontent.com/Moviw/ssh-ls/main/install.sh -o install.sh
less install.sh
sh install.sh
```

已经使用 uv 或 pipx 的话，也可以安装相同的稳定发布包，需要 Python 3.11+：

```sh
uv tool install https://github.com/Moviw/ssh-ls/releases/latest/download/ssh-ls.tar.gz
# 或
pipx install https://github.com/Moviw/ssh-ls/releases/latest/download/ssh-ls.tar.gz
```

## 最常用的几个键

| 按键 | 操作 |
| --- | --- |
| `/` | 按名称、主机、用户名或跳板机搜索 |
| `j` / `k`、`↑` / `↓` | 选择主机 |
| `Tab`、`←` / `→` | 切换全部、最近、收藏 |
| `Enter` | 连接 |
| `Space` | 收藏或取消收藏 |
| `?` | 查看全部快捷键 |
| `q` | 退出 |

默认打开 **Recent**。点击 **Settings** 或按 `o` 进入配置页，可以选择 Recent、Favorites 或 All 作为启动页，也能选择主题、调整强调色、行距和 ASCII 显示。

主题默认是 Tokyo Night。也预置了 Dracula、Catppuccin Mocha、Nord、Gruvbox Dark、Rosé Pine、Minimal、Cyberpunk、Ocean 和 Retro。在 Settings 的 **Themes** 标签页选择卡片即可预览，Save 保存，Esc 放弃预览。

![主题画廊](docs/themes.svg)

你也可以新增、编辑、复制、隐藏和手动排列主机，调整排序，明确输入一条远程命令，或更换强调色与行距。[完整快捷键与命令行选项 →](docs/usage.md)

## 你可能想问

**会改我的 SSH 配置吗？** 不会。编辑结果作为本地覆盖项，保存在 `${XDG_CONFIG_HOME:-~/.config}/ssh-ls/`。实际连接行为仍以 OpenSSH 为准；界面显示的是配置估计值，按 `v` 可以主动预览生效配置。

**会重放历史命令吗？** 不会。导入器只从支持的 SSH 命令中提取连接字段，丢弃远程命令；遇到 shell 替换、环境变量赋值，或无法还原原工作目录的相对密钥、配置路径，就跳过。这意味着部分历史记录不会出现。

**打开界面就会偷偷连接吗？** 不会。选择器不在后台探测服务器，也不自动运行 `ssh -G`。你选择主机后才开始连接；手动标记为生产环境的主机还需要确认。

**会改变我现在的终端用法吗？** 不会。系统 `ssh` 直接接管终端，退出码照常保留。不需要云端账号、同步服务或另一套凭据存储。

## 更新和卸载

```sh
ssh-ls update
ssh-ls uninstall
```

卸载需要确认，只移除应用，保留收藏、设置、SSH 文件、uv 和 Python。`--yes` 可跳过交互确认。内置命令只管理官方 uv 安装；pipx 和源码安装请使用原来的安装方式。

正常启动时会在后台检查 GitHub 稳定版本；发现更新时显示版本和更新命令，不自动升级，离线静默，Demo 不联网。不发送 SSH 配置或历史。Settings 分为 General 和 Themes 两个标签页，主题画廊提供十套可预览的主题卡片，默认仍是 Tokyo Night。底栏新增 `o Settings`。

## 参与开发

欢迎报告问题和提交范围明确的 PR。请附上操作系统、Python 版本，以及可以复现问题的虚构配置或历史样例，不要提交私钥或真实 shell 历史。[开发说明 →](docs/development.md)

---

*Dedicated to my research days in Nakayama Lab.*
