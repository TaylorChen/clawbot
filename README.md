# clawbot

轻量级、可扩展的开源机器人框架，支持通过 Telegram 远程调用 Claude CLI 执行指令。

## 功能特性

- **远程指令执行**：通过 `/run` 命令在 macOS 上的 Claude CLI 中执行命令
- **文件传输**：支持 `/pull`（拉取文件）和 `/push`（推送文件）
- **安全沙盒**：所有操作都在受限的工作目录中执行
- **访问控制**：基于用户白名单的访问控制
- **审计日志**：完整的操作审计记录（JSONL格式）
- **结构化日志**：使用 loguru 进行详细的日志记录
- **配置管理**：使用 pydantic v2 进行类型安全的配置管理

## 安装

### 1. 克隆仓库或创建目录

```bash
cd /Users/demo/python/
mkdir clawbot && cd clawbot
```

### 2. 安装依赖

使用 Python 虚拟环境（推荐）：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置

复制并修改配置文件：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置以下必填项：

```env
# Telegram Bot Token（在 @BotFather 处获取）
TELEGRAM_BOT_TOKEN=your_bot_token_here

# 管理员用户 ID（从 @userinfobot 获取），支持多个用户用逗号分隔
TELEGRAM_ADMIN_IDS=your_user_id_here

# 可选配置
# CLAUDE_CLI_PATH=claude  # Claude CLI 可执行文件路径
# EXECUTION_TIMEOUT=300  # 命令执行超时时间（秒）
# WORKSPACE_DIR=~/clawbot_workspace  # 工作目录
```

### 4. 安装 Claude CLI

确保系统已安装 Claude CLI：

```bash
# 通过 npm 安装官方 CLI
npm install -g @anthropic-ai/claude-code

# 运行并按照提示完成 OAuth 授权
claude
```

如果使用 /tui，需要安装 tmux：

```bash
brew install tmux
```

## 使用

### 启动 Bot

使用提供的启动脚本（推荐）：

```bash
# 启动服务
./start.sh start

# 检查运行状态
./start.sh status

# 查看日志
./start.sh logs

# 实时查看日志
./start.sh logstail

# 重启服务
./start.sh restart

# 停止服务
./start.sh stop
```

或者直接运行（不推荐用于生产环境）：

```bash
source .venv/bin/activate
python3 -m bot.main
```

### 可用命令

1. **/start** - 显示欢迎信息和帮助
2. **/help** - 显示详细帮助信息
3. **/run <command>** - 在 Claude CLI 中执行命令
   - 示例：`/run ls -la`
   - 说明：执行自然语言指令或命令
4. **/tui <command>** - 在 Claude Code TUI 中执行命令
   - 示例：`/tui 你好`
   - 说明：通过 tmux 会话发送指令到 Claude Code
5. **/tui-capture [n]** - 获取 TUI 最近输出
   - 示例：`/tui-capture 80`
6. **/tui-start** - 启动 TUI 会话
7. **/tui-stop** - 停止 TUI 会话
8. **/pull <path>** - 拉取文件到 Telegram
   - 示例：`/pull ~/Documents/report.txt`
9. **/push <file>** - 推送文件到 macOS
   - 使用方法：回复要推送的文件并发送 `/push` 命令
10. **/sessions [n]** - 列出最近 n 个 Claude 会话
   - 示例：`/sessions 10`
   - 说明：默认列出最近 10 个会话
11. **/session set <id>** - 固定会话
   - 示例：`/session set 1234-abcde`
   - 说明：设置固定会话后，/run 命令默认使用该会话

## 安全机制

### 1. 访问控制

- **用户白名单**：只有配置在 `TELEGRAM_ADMIN_IDS` 中的用户可以访问
- **默认行为**：如果未配置白名单，允许所有用户访问（生产环境不推荐）

### 2. 命令限制

**禁止的命令列表**（默认）：
- `rm -rf`：危险的文件删除命令
- `sudo`：提权命令
- `nc` 或 `ncat`：网络工具

### 3. 安全沙盒

- **工作目录限制**：所有命令在 `~/clawbot_workspace/` 目录中执行
- **禁止访问的路径**：
  - `/System`：系统目录
  - `/Users/*/Library`：用户库目录
  - `/private`：私有目录
  - `/etc`：系统配置目录

### 4. 审计日志

- 所有操作都记录在 `logs/audit_YYYYMMDD.jsonl` 文件中
- 日志包含时间戳、用户ID、命令、执行结果等信息
- 日志保留 30 天（可通过配置修改）

## 架构

```
Telegram → Bot 接口 → 安全检查 → 执行器 → Claude CLI → 结果
```

### 核心组件

- **bot/**：Telegram 通信模块（aiogram v3）
  - `main.py`：Bot 入口和消息处理器
- **executor/**：命令执行模块
  - `runner.py`：调用 Claude CLI 执行命令
- **security/**：安全与审计模块
  - `acl.py`：访问控制和审计日志
- **config/**：配置管理
  - `settings.py`：pydantic 配置类
- **logs/**：日志存储
  - `clawbot.log`：系统日志
  - `audit_YYYYMMDD.jsonl`：审计日志

## 配置选项

详细的配置选项请参考 `config/settings.py` 文件。主要配置项：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| TELEGRAM_BOT_TOKEN | Telegram Bot 令牌 | 必填 |
| TELEGRAM_ADMIN_IDS | 管理员用户 ID 列表（逗号分隔） | 空 |
| CLAUDE_CLI_PATH | Claude CLI 路径 | `claude` |
| EXECUTION_TIMEOUT | 命令执行超时时间（秒） | 300 |
| CLAUDE_TUI_CMD | Claude Code TUI 启动命令 | `claude` |
| TUI_SESSION_NAME | tmux 会话名 | `clawbot-claude` |
| TUI_CAPTURE_LINES | TUI 默认抓取行数 | 80 |
| TUI_CAPTURE_DELAY | 发送指令后等待输出（秒） | 0.8 |
| TUI_LOG_FILE | TUI 输出日志文件名 | `tui_output.log` |
| TUI_REPLY_MAX_LINES | TUI 回传最大行数 | 40 |
| TUI_REPLY_MAX_CHARS | TUI 回传最大字符数 | 2000 |
| WORKSPACE_DIR | 工作目录 | `~/clawbot_workspace` |
| LOG_LEVEL | 日志级别 | DEBUG |
| SANDBOX_ENABLED | 是否启用沙盒 | True |
| BLOCKED_COMMANDS | 禁止的命令列表 | ["rm -rf", "sudo", "nc", "ncat"] |
| PROHIBITED_PATHS | 禁止访问的路径 | ["/System", "/Users/*/Library", "/private", "/etc"] |

## SOP（标准操作流程）

### 1. 部署流程

```bash
# 1. 克隆仓库
cd /Users/demo/python/
mkdir clawbot && cd clawbot

# 2. 安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. 配置
cp .env.example .env
# 编辑 .env 文件，填入 TELEGRAM_BOT_TOKEN 和 TELEGRAM_ADMIN_IDS

# 4. 安装 Claude CLI
npm install -g @anthropic-ai/claude-code
claude  # 完成授权

# 5. 启动服务
python3 -m bot.main
```

### 2. 日常使用流程

#### 远程执行命令
```
/run list all files in workspace
```

#### 拉取文件
```
/pull ~/Documents/report.txt
```

#### 推送文件
1. 在 Telegram 中发送文件
2. 回复该文件并发送 `/push` 命令

### 3. 监控与维护

#### 查看运行状态
- 检查控制台输出的日志信息

#### 查看日志文件
```bash
# 系统日志
tail -f logs/clawbot.log

# 审计日志
cat logs/audit_$(date +%Y%m%d).jsonl
```

#### 重启服务
```bash
# 停止当前运行的服务（按 Ctrl+C）
python3 -m bot.main  # 重新启动
```

### 4. 故障排除

#### 常见问题

1. **Claude CLI 未找到**
   - 确保已正确安装 Claude CLI：`npm install -g @anthropic-ai/claude-code`
   - 检查 `CLAUDE_CLI_PATH` 配置

2. **无访问权限**
   - 确保你的用户 ID 在 `TELEGRAM_ADMIN_IDS` 配置中
   - 检查 `.env` 文件中的配置

3. **命令执行超时**
   - 检查命令是否需要更长时间
   - 调整 `EXECUTION_TIMEOUT` 配置

4. **路径访问被拒绝**
   - 确保文件路径在允许的范围内
   - 检查 `PROHIBITED_PATHS` 配置

## 部署建议

### 生产环境部署

1. 使用 `launchd` 或其他守护进程管理工具保持 Bot 常驻
2. 定期备份配置和日志
3. 监控 Bot 运行状态

### 本地开发

可以使用 Python 的 `watchdog` 库自动重载代码：

```bash
pip install watchdog
watchmedo auto-restart --patterns="*.py" --recursive -- python3 -m bot.main
```

## 开发

项目采用模块化设计，支持轻松扩展：

1. **新增指令**：在 `bot/main.py` 中添加新的命令处理函数
2. **修改执行逻辑**：修改 `executor/runner.py`
3. **调整安全策略**：修改 `security/acl.py` 和 `config/settings.py`

## 免责声明

本工具具备系统级操作能力。请确保：
- 仅在本人设备使用
- Bot Token 严格保密
- 不开放公网入站

## 许可证

[MIT License](LICENSE)
