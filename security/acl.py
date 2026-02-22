"""访问控制和审计模块"""
import os
import logging
from datetime import datetime
from config.settings import settings
from loguru import logger

logger = logging.getLogger(__name__)

def is_user_allowed(user_id: int) -> bool:
    """
    检查用户是否被允许使用 Bot

    Args:
        user_id: Telegram 用户 ID

    Returns:
        是否被允许
    """
    if not settings.admin_ids:
        # 如果没有配置管理员列表，允许所有用户（生产环境不推荐）
        logger.warning("未配置管理员白名单，允许所有用户访问")
        return True

    return user_id in settings.admin_ids

def is_command_allowed(command: str) -> bool:
    """
    检查命令是否被允许执行

    Args:
        command: 要检查的命令

    Returns:
        是否被允许
    """
    # 检查是否在禁止命令列表中
    for blocked in settings.blocked_commands:
        if blocked in command.lower():
            logger.warning(f"命令包含禁止关键词: {blocked}")
            return False

    return True

def is_path_allowed(file_path: str) -> bool:
    """
    检查文件路径是否被允许访问

    Args:
        file_path: 要检查的文件路径

    Returns:
        是否被允许
    """
    if not settings.SANDBOX_ENABLED:
        return True

    # 规范化路径
    normalized_path = os.path.abspath(file_path)
    workspace = os.path.abspath(settings.WORKSPACE_DIR)

    # 检查是否在工作目录内
    if normalized_path.startswith(workspace):
        return True

    # 检查是否在禁止访问的路径中
    for prohibited in settings.PROHIBITED_PATHS:
        # 处理通配符路径（如 /Users/*/Library）
        if "*" in prohibited:
            import fnmatch
            if fnmatch.fnmatch(normalized_path, prohibited):
                logger.warning(f"路径禁止访问: {normalized_path}")
                return False
        elif normalized_path.startswith(prohibited):
            logger.warning(f"路径禁止访问: {normalized_path}")
            return False

    return True

def log_command_execution(user_id: int, command: str, success: bool, result: str = ""):
    """
    记录命令执行审计日志

    Args:
        user_id: 用户 ID
        command: 执行的命令
        success: 是否成功
        result: 执行结果（可选）
    """
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "command": command,
        "success": success,
        "result": result
    }

    # 写入 JSONL 格式的日志文件
    log_file = os.path.join(settings.LOG_DIR, f"audit_{datetime.now().strftime('%Y%m%d')}.jsonl")
    import json
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    logger.info(f"命令执行记录: 用户 {user_id} 执行 '{command}' {'成功' if success else '失败'}")
