# clawbot

A lightweight, extensible open-source robot framework that supports remote execution of Claude CLI commands via Telegram.

## Features

- **Remote Command Execution**: Execute commands on macOS via `/run` command
- **File Transfer**: Support `/pull` (download files) and `/push` (upload files)
- **Security Sandbox**: All operations are executed in a restricted workspace
- **Access Control**: Whitelist-based user access control
- **Audit Logs**: Complete operation audit records in JSONL format
- **Structured Logging**: Detailed logging with loguru
- **Configuration Management**: Type-safe configuration with pydantic v2

## Installation

### 1. Clone Repository or Create Directory

```bash
cd /Users/demo/python/
mkdir clawbot && cd clawbot
```

### 2. Install Dependencies

Using Python virtual environment (recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuration

Copy and modify the configuration file:

```bash
cp .env.example .env
```

Edit the `.env` file and configure the following required fields:

```env
# Telegram Bot Token (obtain from @BotFather)
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Admin user IDs (obtain from @userinfobot), support multiple users separated by commas
TELEGRAM_ADMIN_IDS=your_user_id_here

# Optional configurations
# CLAUDE_CLI_PATH=claude  # Path to Claude CLI executable
# EXECUTION_TIMEOUT=300  # Command execution timeout (seconds)
# WORKSPACE_DIR=~/clawbot_workspace  # Working directory
```

### 4. Install Claude CLI

Ensure the system has Claude CLI installed:

```bash
# Install official CLI via npm
npm install -g @anthropic-ai/claude-code

# Run and follow the prompts to complete OAuth authorization
claude
```

If you use `/tui`, install tmux:

```bash
brew install tmux
```

## Usage

### Start the Bot

Using the provided startup script (recommended):

```bash
# Start service
./start.sh start

# Check running status
./start.sh status

# View logs
./start.sh logs

# View real-time logs
./start.sh logstail

# Restart service
./start.sh restart

# Stop service
./start.sh stop
```

Or run directly (not recommended for production environments):

```bash
source .venv/bin/activate
python3 -m bot.main
```

### Available Commands

1. **/start** - Display welcome information and help
2. **/help** - Display detailed help information
3. **/run <command>** - Execute commands in Claude CLI
   - Example: `/run ls -la`
   - Description: Execute natural language instructions or commands
4. **/tui <command>** - Execute commands in Claude Code TUI
   - Example: `/tui hello`
   - Description: Send commands to Claude Code via tmux session
5. **/tui-capture [n]** - Get recent TUI output
   - Example: `/tui-capture 80`
6. **/tui-start** - Start the TUI session
7. **/tui-stop** - Stop the TUI session
8. **/pull <path>** - Pull files from macOS to Telegram
   - Example: `/pull ~/Documents/report.txt`
9. **/push <file>** - Push files from Telegram to macOS
   - Usage: Reply to the file you want to push and send `/push` command
10. **/sessions [n]** - List recent n Claude sessions
   - Example: `/sessions 10`
   - Description: Defaults to listing 10 recent sessions
11. **/session set <id>** - Set fixed session
   - Example: `/session set 1234-abcde`
   - Description: After setting a fixed session, /run commands will use this session by default

## Security Mechanisms

### 1. Access Control

- **User Whitelist**: Only users configured in `TELEGRAM_ADMIN_IDS` can access
- **Default Behavior**: If no whitelist is configured, all users are allowed (not recommended for production)

### 2. Command Restrictions

**Prohibited commands list** (default):
- `rm -rf`: Dangerous file deletion command
- `sudo`: Privilege escalation command
- `nc` or `ncat`: Network tools

### 3. Security Sandbox

- **Workspace Restriction**: All commands are executed in `~/clawbot_workspace/` directory
- **Prohibited Paths**:
  - `/System`: System directory
  - `/Users/*/Library`: User library directory
  - `/private`: Private directory
  - `/etc`: System configuration directory

### 4. Audit Logs

- All operations are recorded in `logs/audit_YYYYMMDD.jsonl` files
- Logs contain timestamp, user ID, command, execution result, etc.
- Logs are retained for 30 days (configurable)

## Architecture

```
Telegram → Bot Interface → Security Check → Executor → Claude CLI → Result
```

### Core Components

- **bot/**: Telegram communication module (aiogram v3)
  - `main.py`: Bot entry point and message handlers
- **executor/**: Command execution module
  - `runner.py`: Calls Claude CLI to execute commands
- **security/**: Security and audit module
  - `acl.py`: Access control and audit logs
- **config/**: Configuration management
  - `settings.py`: pydantic configuration class
- **logs/**: Log storage
  - `clawbot.log`: System logs
  - `audit_YYYYMMDD.jsonl`: Audit logs

## Configuration Options

For detailed configuration options, please refer to `config/settings.py`. Main configuration items:

| Configuration Item | Description | Default Value |
|-------------------|-------------|---------------|
| TELEGRAM_BOT_TOKEN | Telegram Bot token | Required |
| TELEGRAM_ADMIN_IDS | List of admin user IDs (comma-separated) | Empty |
| CLAUDE_CLI_PATH | Path to Claude CLI executable | `claude` |
| EXECUTION_TIMEOUT | Command execution timeout (seconds) | 300 |
| CLAUDE_TUI_CMD | Claude Code TUI launch command | `claude` |
| TUI_SESSION_NAME | tmux session name | `clawbot-claude` |
| TUI_CAPTURE_LINES | Default TUI capture lines | 80 |
| TUI_CAPTURE_DELAY | Delay after send (seconds) | 0.8 |
| TUI_LOG_FILE | TUI output log filename | `tui_output.log` |
| TUI_REPLY_MAX_LINES | Max TUI reply lines | 40 |
| TUI_REPLY_MAX_CHARS | Max TUI reply chars | 2000 |
| WORKSPACE_DIR | Working directory | `~/clawbot_workspace` |
| LOG_LEVEL | Log level | DEBUG |
| SANDBOX_ENABLED | Whether to enable sandbox | True |
| BLOCKED_COMMANDS | List of prohibited commands | ["rm -rf", "sudo", "nc", "ncat"] |
| PROHIBITED_PATHS | List of prohibited paths | ["/System", "/Users/*/Library", "/private", "/etc"] |

## SOP (Standard Operating Procedure)

### 1. Deployment Process

```bash
# 1. Clone repository
cd /Users/demo/python/
mkdir clawbot && cd clawbot

# 2. Install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env file, fill in TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_IDS

# 4. Install Claude CLI
npm install -g @anthropic-ai/claude-code
claude  # Complete authorization

# 5. Start service
python3 -m bot.main
```

### 2. Daily Use Process

#### Remote Execution Command
```
/run list all files in workspace
```

#### Pull File
```
/pull ~/Documents/report.txt
```

#### Push File
1. Send the file in Telegram
2. Reply to the file and send `/push` command

### 3. Monitoring and Maintenance

#### Check Running Status
- Check the log information output to the console

#### View Log Files
```bash
# System logs
tail -f logs/clawbot.log

# Audit logs
cat logs/audit_$(date +%Y%m%d).jsonl
```

#### Restart Service
```bash
# Stop current running service (press Ctrl+C)
python3 -m bot.main  # Restart
```

### 4. Troubleshooting

#### Common Issues

1. **Claude CLI Not Found**
   - Make sure Claude CLI is correctly installed: `npm install -g @anthropic-ai/claude-code`
   - Check `CLAUDE_CLI_PATH` configuration

2. **No Access Permission**
   - Make sure your user ID is in `TELEGRAM_ADMIN_IDS` configuration
   - Check the configuration in `.env` file

3. **Command Execution Timeout**
   - Check if the command needs more time
   - Adjust `EXECUTION_TIMEOUT` configuration

4. **Path Access Denied**
   - Make sure the file path is within allowed scope
   - Check `PROHIBITED_PATHS` configuration

## Deployment Recommendations

### Production Environment Deployment

1. Use `launchd` or other process management tools to keep the Bot running permanently
2. Backup configuration and logs regularly
3. Monitor Bot running status

### Local Development

Use Python's `watchdog` library to automatically reload code:

```bash
pip install watchdog
watchmedo auto-restart --patterns="*.py" --recursive -- python3 -m bot.main
```

## Development

The project adopts a modular design, supporting easy expansion:

1. **Add New Commands**: Add new command handler functions in `bot/main.py`
2. **Modify Execution Logic**: Modify `executor/runner.py`
3. **Adjust Security Policies**: Modify `security/acl.py` and `config/settings.py`

## Disclaimer

This tool has system-level operation capabilities. Please ensure:
- Only use on your own devices
- Keep Bot Token strictly confidential
- Do not expose to public network incoming connections

## License

[MIT License](LICENSE)
