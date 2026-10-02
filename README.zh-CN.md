# ssh-ls

面向键盘操作的 SSH 主机选择器，支持 macOS 和 Linux。`ssh-ls` 使用 Textual 展示 OpenSSH 配置中的主机，以及按有限规则从本地 shell 历史提取的候选目标；连接由系统自带的 OpenSSH 客户端接管。它是受 [akinoiro/ssh-list](https://github.com/akinoiro/ssh-list) 启发的独立 MIT 许可重写，不复用原项目源代码。

![ssh-ls 演示](docs/demo.svg)

## 功能

- 读取 OpenSSH 配置中的字面 Host 别名及支持的 `Include` 文件；不修改原始 SSH 配置。界面展示的是估算值，可在确认后用 `ssh -G` 查看 OpenSSH 实际解析结果。
- 支持搜索/筛选、排序/重排、收藏、添加、编辑、克隆和隐藏主机；提供「全部」「最近」「收藏」「历史」视图，不引入分组或标签。自定义主机和应用覆盖项保存在 ssh-ls 自己的状态文件中。
- 从 zsh/bash 历史中只解析保守子集，提取主机字段供界面查看；收藏、编辑、隐藏或尝试连接等用户操作才会保存元数据。绝不执行或重放历史命令。
- `r` 允许用户为所选主机明确输入远程命令。退出选择器后才启动原生 `ssh`，会话结束后回到 shell。
- `--demo` 使用虚构主机，不读取真实 SSH 配置或历史，也不发起网络连接。

## 安装

需要 Python 3.11 或更高版本，以及 `PATH` 中可用的 OpenSSH 客户端。

使用 [uv](https://docs.astral.sh/uv/)：

```sh
uv tool install git+https://github.com/Moviw/ssh-ls.git
ssh-ls
```

也可使用 pipx：

```sh
pipx install git+https://github.com/Moviw/ssh-ls.git
ssh-ls
```

本地开发：

```sh
git clone https://github.com/Moviw/ssh-ls.git
cd ssh-ls
uv sync
uv run ssh-ls --demo
```

## 快捷键

| 按键 | 操作 |
| --- | --- |
| `j` / `k`、`↑` / `↓` | 移动主机选择 |
| `Tab` / `←` / `→` | 切换标签页 |
| `Space` | 切换收藏状态 |
| `/` | 搜索 |
| `s` | 打开排序菜单 |
| `Enter` | 连接所选主机 |
| `a` / `e` / `c` / `Delete` | 添加 / 编辑 / 克隆 / 删除主机 |
| `m` | 进入重排模式（用 `j`/`k` 或方向键移动，`Esc` 完成） |
| `r` | 输入要执行的远程命令 |
| `i` | 从配置重新加载主机 |
| `o` | 打开设置 |
| `v` | 确认后查看 OpenSSH 实际解析结果（`ssh -G`） |
| `U` / `H` | 重置主机覆盖项 / 恢复已隐藏主机 |
| `g` | 执行本机 doctor 检查 |
| `?` | 显示帮助 |
| `q` / `Esc` | 退出或关闭当前视图 |

界面底部会显示当前可用快捷键。删除等破坏性操作会要求确认。

## 命令行

```text
ssh-ls [--config PATH] [--history PATH ...] [--no-history] [--demo]
       [--doctor] [--ascii] [--version]
```

- `--config PATH` 指定另一份 OpenSSH 配置文件。
- `--history PATH` 可重复传入，自选 shell 历史文件。
- `--no-history` 本次运行不扫描历史。
- `--demo` 使用虚构数据，不读取真实 SSH 配置/历史，也不连接网络。
- `--doctor` 检查本地环境，不连接主机。
- `--ascii` 使用 ASCII 边框和指示符，适用于字形支持有限的终端。

安装后使用 `ssh-ls --help` 查看实际 CLI 帮助。使用 uv 安装后，可运行 `uv tool uninstall ssh-ls` 卸载。

## 隐私与本地状态

历史发现只接受保守的直接 `ssh` 命令子集。不求值 shell 展开；`NAME=value ssh host` 这类赋值前缀命令会被跳过。无法根据历史上下文解析的相对 `-i` 私钥路径和 `-F` 配置路径会被拒绝。程序丢弃解析出的命令文本：绝不执行或重放历史命令，包括其中的远程命令文本。`r` 只会执行用户在界面中明确输入的远程命令。示例和演示数据使用保留的 `.test` 域名，不包含真实主机名或凭据。

用户界面状态保存在 `${XDG_CONFIG_HOME:-~/.config}/ssh-ls/state.json`。POSIX 系统上状态目录/文件使用私有权限（0700/0600），更新时保留 `state.json.bak` 备份。SSH 凭据和私钥仍由 OpenSSH 的常规机制管理；ssh-ls 不要求把私钥粘贴进状态文件。

在现有 OpenSSH 别名上添加的 ssh-ls 身份路径会作为额外的 `-i` 参数传入。清除 ssh-ls 覆盖项只会移除应用添加的参数，不会删除或改写 OpenSSH 配置中的 `IdentityFile`。

## 开发与检查

```sh
uv sync
uv run python -m unittest discover -s tests -v
uv build
```

CI 会在 Linux、macOS 和 Python 3.11、3.14 组合上运行单元测试与包构建，并在 Ubuntu 上执行隔离的原生 OpenSSH 集成检查。`docs/verification.md` 记录烟雾检查命令及安全边界；它是检查清单，不代表这些命令已全部通过。

## 恢复状态或卸载

`ROLLBACK.sh` 只会使用同目录的 `.bak` 文件恢复一份应用状态副本，不会删除项目，也不会检查或修改 SSH 配置、密钥或其他 `~/.ssh` 数据。例如，`./ROLLBACK.sh "$STATE_COPY"` 要求存在对应的 `"$STATE_COPY.bak"` 基线文件。恢复任何状态副本前先退出 ssh-ls，避免运行中的应用随后用旧状态覆盖恢复结果。除非确实要用备份覆盖实时状态，否则不要把实时状态文件作为参数。

uv 安装的版本可用 `uv tool uninstall ssh-ls` 卸载。

## 设计参考与致谢

视觉方向参考了 [awesome-tui-design](https://github.com/cola-runner/awesome-tui-design) 中的 Tokyo Night、Catppuccin 和 Nord 设计说明，交互模式参考 [Truffle Glyph](https://truffleagent.com/glyph/)。Glyph 目前提供 Go/Bubble Tea 组件；ssh-ls 使用 Python/Textual，仅重新实现适用的交互模式，不导入 Glyph 代码。主题文档是设计参考，不是打包的代码。

## 许可证

MIT，详见 [LICENSE](LICENSE)。
