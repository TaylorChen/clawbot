"""clawbot 配置文件"""
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """项目配置类"""
    # Telegram Bot 配置
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ADMIN_IDS: str = ""

    # 计算属性，用于将字符串转换为列表
    @property
    def admin_ids(self) -> list[int]:
        if not self.TELEGRAM_ADMIN_IDS:
            return []
        return [int(x.strip()) for x in self.TELEGRAM_ADMIN_IDS.split(",") if x.strip()]

    # 安全配置
    ALLOWED_COMMANDS: list[str] = ["/run", "/pull", "/push"]
    BLOCKED_COMMANDS: str = "rm -rf,sudo,nc,ncat"
    WORKSPACE_DIR: str = os.path.expanduser("~/clawbot_workspace")

    # 计算属性，用于将字符串转换为列表
    @property
    def blocked_commands(self) -> list[str]:
        if not self.BLOCKED_COMMANDS:
            return []
        return [x.strip() for x in self.BLOCKED_COMMANDS.split(",") if x.strip()]

    # 执行配置
    CLAUDE_CLI_PATH: str = "claude"
    EXECUTION_TIMEOUT: int = 300  # 执行超时时间（秒）
    CLAUDE_TUI_CMD: str = "claude"  # Claude Code TUI 启动命令
    TUI_SESSION_NAME: str = "clawbot-claude"
    TUI_CAPTURE_LINES: int = 200
    TUI_CAPTURE_DELAY: float = 3.0  # 发送指令后等待输出（秒）
    TUI_LOG_FILE: str = "tui_output.log"
    TUI_REPLY_MAX_LINES: int = 40
    TUI_REPLY_MAX_CHARS: int = 4000
    TUI_WAIT_ATTEMPTS: int = 0
    TUI_MAX_WAIT_SECONDS: float = 120.0

    # 日志配置
    LOG_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
    LOG_LEVEL: str = "DEBUG"

    # Redis 配置（用于任务队列）
    REDIS_URL: str = "redis://localhost:6379/0"

    # 安全沙盒配置
    SANDBOX_ENABLED: bool = True
    PROHIBITED_PATHS: list[str] = [
        "/System",
        "/Users/*/Library",
        "/private",
        "/etc"
    ]

    # 代理配置
    # 如果配置了代理地址，就使用代理功能
    PROXY_TYPE: str = ""  # 支持 http、https、socks5
    PROXY_ADDRESS: str = ""
    PROXY_PORT: int = 0
    PROXY_USERNAME: str = ""
    PROXY_PASSWORD: str = ""

    @property
    def proxy_url(self):
        """获取完整的代理 URL"""
        if self.PROXY_TYPE and self.PROXY_ADDRESS and self.PROXY_PORT:
            if self.PROXY_USERNAME and self.PROXY_PASSWORD:
                return f"{self.PROXY_TYPE}://{self.PROXY_USERNAME}:{self.PROXY_PASSWORD}@{self.PROXY_ADDRESS}:{self.PROXY_PORT}"
            else:
                return f"{self.PROXY_TYPE}://{self.PROXY_ADDRESS}:{self.PROXY_PORT}"
        return None

    class Config:
        """配置加载方式"""
        env_file = ".env"
        case_sensitive = True

settings = Settings()

# 确保工作目录和日志目录存在
settings.WORKSPACE_DIR = os.path.expanduser(settings.WORKSPACE_DIR)
settings.LOG_DIR = os.path.abspath(settings.LOG_DIR)

os.makedirs(settings.WORKSPACE_DIR, exist_ok=True)
os.makedirs(settings.LOG_DIR, exist_ok=True)
