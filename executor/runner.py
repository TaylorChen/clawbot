"""执行器模块 - 负责调用 Claude CLI 执行命令"""
import subprocess
import os
import json
from datetime import datetime
from loguru import logger
from config.settings import settings
from security import (
    is_command_allowed,
    is_path_allowed,
    log_command_execution,
)


def _parse_iso_ts(value: str | None):
    if not value:
        return None
    try:
        # Handle Zulu time
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except Exception:
        return None

def run_command(user_id: int, command: str, *, session_id: str | None = None, use_continue: bool = False) -> dict:
    """
    在 Claude CLI 中执行命令

    Args:
        user_id: 执行命令的用户 ID
        command: 要执行的命令

    Returns:
        包含执行结果的字典
    """
    logger.info(f"用户 {user_id} 尝试执行命令: {command}")

    # 安全检查
    if not is_command_allowed(command):
        logger.warning(f"用户 {user_id} 尝试执行禁止的命令: {command}")
        log_command_execution(user_id, command, False, "禁止的命令")
        return {
            "success": False,
            "message": "命令包含禁止关键词，请检查后重试"
        }

    try:
        # 在工作目录中执行命令（避免全局 chdir 带来的并发问题）
        logger.debug(f"在工作目录 {settings.WORKSPACE_DIR} 中执行命令")

        # Claude CLI 使用 prompt 模式执行自然语言指令（-p 会直接输出并退出）
        # 注意：Telegram 代理环境会影响 Claude CLI 请求，需移除代理变量
        clean_env = os.environ.copy()
        for key in (
            "http_proxy", "https_proxy", "all_proxy",
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
        ):
            clean_env.pop(key, None)
        cli_args = [settings.CLAUDE_CLI_PATH]
        if use_continue:
            cli_args.append("--continue")
        if session_id:
            cli_args.extend(["--session-id", session_id])
        cli_args.extend(["-p", command])

        result = subprocess.run(
            cli_args,
            capture_output=True,
            text=True,
            timeout=settings.EXECUTION_TIMEOUT,
            cwd=settings.WORKSPACE_DIR,
            env=clean_env,
        )

        # 添加详细的调试信息
        logger.info(f"subprocess.run() 完整输出信息:")
        logger.info(f"返回码: {result.returncode}")
        logger.info(f"标准输出长度: {len(result.stdout)}")
        logger.info(f"标准输出内容: '{result.stdout}'")
        logger.info(f"标准错误长度: {len(result.stderr)}")
        logger.info(f"标准错误内容: '{result.stderr}'")

        # 记录审计日志
        output_text = (result.stdout or result.stderr or "").strip()
        log_command_execution(
            user_id,
            command,
            result.returncode == 0,
            output_text
        )

        if result.returncode == 0:
            logger.info(f"命令执行成功: {command}")
            message = output_text
            # 处理命令没有输出的情况
            if not message:
                message = "命令已成功执行，但没有输出内容"
            return {
                "success": True,
                "message": message
            }
        else:
            logger.error(f"命令执行失败: {command} - {result.stderr.strip()}")
            return {
                "success": False,
                "message": f"执行失败: {result.stderr.strip()}"
            }

    except subprocess.TimeoutExpired:
        logger.error(f"命令执行超时: {command}")
        log_command_execution(user_id, command, False, "执行超时")
        return {
            "success": False,
            "message": "命令执行超时"
        }
    except FileNotFoundError:
        logger.error("Claude CLI 未找到")
        log_command_execution(user_id, command, False, "Claude CLI 未找到")
        return {
            "success": False,
            "message": "Claude CLI 未找到，请确保已正确安装"
        }
    except Exception as e:
        logger.exception(f"命令执行过程中发生错误: {command}")
        log_command_execution(user_id, command, False, str(e))
        return {
            "success": False,
            "message": f"执行过程中发生错误: {str(e)}"
        }


def list_sessions(limit: int = 10, active_minutes: int = 60) -> dict:
    """
    列出本机 Claude CLI 已有会话

    Args:
        limit: 返回数量上限

    Returns:
        包含执行结果的字典
    """
    sessions_dir = os.path.expanduser("~/.claude/sessions")
    session_env_dir = os.path.expanduser("~/.claude/session-env")
    if not os.path.isdir(sessions_dir):
        return {
            "success": False,
            "message": "未找到本机 Claude 会话目录 (~/.claude/sessions)"
        }

    try:
        history_path = os.path.expanduser("~/.claude/history.jsonl")
        history_map = {}
        if os.path.isfile(history_path):
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                        except Exception:
                            continue
                        sid = item.get("sessionId")
                        if not sid:
                            continue
                        raw_title = (item.get("display") or "").strip()
                        history_map[sid] = {
                            "title": raw_title or "(no title)",
                            "ts_ms": item.get("timestamp"),
                        }
            except Exception:
                history_map = {}

        active_ids = set()
        if os.path.isdir(session_env_dir):
            for name in os.listdir(session_env_dir):
                if name and os.path.isdir(os.path.join(session_env_dir, name)):
                    active_ids.add(name)

        if not active_ids:
            return {
                "success": True,
                "message": "暂无正在运行的会话"
            }

        def normalize_title(value: str) -> str:
            text = (value or "").replace("\n", " ").replace("\r", " ").strip()
            text = " ".join(text.split())
            if text.startswith("[Pasted text"):
                return "(pasted text)"
            max_len = 80
            return text[:max_len] + ("…" if len(text) > max_len else "")

        sessions = []
        for sid in active_ids:
            env_dir = os.path.join(session_env_dir, sid)
            session_path = os.path.join(sessions_dir, f"{sid}.json")
            mtime = os.path.getmtime(env_dir)
            if os.path.isfile(session_path):
                try:
                    with open(session_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    updated_at = _parse_iso_ts(data.get("updatedAt"))
                    created_at = _parse_iso_ts(data.get("createdAt"))
                    sessions.append({
                        "id": data.get("id") or sid,
                        "title": data.get("title") or "(no title)",
                        "updated_at": updated_at,
                        "created_at": created_at,
                        "mtime": mtime,
                    })
                except Exception:
                    sessions.append({
                        "id": sid,
                        "title": "(unreadable)",
                        "updated_at": None,
                        "created_at": None,
                        "mtime": mtime,
                    })
            else:
                hist = history_map.get(sid)
                hist_ts = None
                if hist and isinstance(hist.get("ts_ms"), (int, float)):
                    hist_ts = datetime.fromtimestamp(hist["ts_ms"] / 1000)
                sessions.append({
                    "id": sid,
                    "title": normalize_title((hist.get("title") if hist else None) or "(no session file)"),
                    "updated_at": hist_ts or datetime.fromtimestamp(mtime),
                    "created_at": None,
                    "mtime": mtime,
                })

        def sort_key(item):
            return (
                item["updated_at"] or item["created_at"] or datetime.fromtimestamp(item["mtime"])
            )

        sessions.sort(key=sort_key, reverse=True)

        # 仅保留真正活跃的会话（最近 active_minutes 内有更新）
        now = datetime.now()
        cutoff = now.timestamp() - max(1, active_minutes) * 60
        def is_active(item):
            ts = item["updated_at"] or item["created_at"] or datetime.fromtimestamp(item["mtime"])
            return ts.timestamp() >= cutoff
        sessions = [s for s in sessions if is_active(s)]

        if not sessions:
            return {
                "success": True,
                "message": f"暂无最近 {active_minutes} 分钟内活跃的会话"
            }

        limit = max(1, min(limit, 20))
        lines = []
        for s in sessions[:limit]:
            ts = s["updated_at"] or s["created_at"] or datetime.fromtimestamp(s["mtime"])
            ts_str = ts.strftime("%Y-%m-%dT%H")
            title = normalize_title(s["title"])
            lines.append(f"{s['id']} | {title} | updated: {ts_str}")

        return {
            "success": True,
            "message": "\n".join(lines)
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"读取会话失败: {str(e)}"
        }

def pull_file(user_id: int, file_path: str) -> dict:
    """
    拉取文件（从 macOS 到 Telegram）

    Args:
        user_id: 用户 ID
        file_path: 要拉取的文件路径

    Returns:
        包含执行结果的字典
    """
    logger.info(f"用户 {user_id} 尝试拉取文件: {file_path}")

    # 安全检查
    if not is_path_allowed(file_path):
        logger.warning(f"用户 {user_id} 尝试访问禁止的路径: {file_path}")
        log_command_execution(user_id, f"pull {file_path}", False, "禁止访问的路径")
        return {
            "success": False,
            "message": "路径禁止访问，请检查后重试"
        }

    # 规范化路径
    normalized_path = os.path.abspath(file_path)

    # 检查文件是否存在
    if not os.path.exists(normalized_path):
        logger.warning(f"用户 {user_id} 尝试访问不存在的文件: {file_path}")
        log_command_execution(user_id, f"pull {file_path}", False, "文件不存在")
        return {
            "success": False,
            "message": "文件不存在"
        }

    # 检查是否是文件（不是目录）
    if os.path.isdir(normalized_path):
        logger.warning(f"用户 {user_id} 尝试拉取目录: {file_path}")
        log_command_execution(user_id, f"pull {file_path}", False, "不能拉取目录")
        return {
            "success": False,
            "message": "只能拉取文件，不能拉取目录"
        }

    log_command_execution(user_id, f"pull {file_path}", True, f"文件大小: {os.path.getsize(normalized_path)} 字节")
    return {
        "success": True,
        "file_path": normalized_path
    }

def push_file(user_id: int, file_data: bytes, filename: str) -> dict:
    """
    推送文件（从 Telegram 到 macOS）

    Args:
        user_id: 用户 ID
        file_data: 文件二进制数据
        filename: 文件名

    Returns:
        包含执行结果的字典
    """
    logger.info(f"用户 {user_id} 尝试推送文件: {filename}")

    # 构造目标文件路径
    target_path = os.path.join(settings.WORKSPACE_DIR, filename)

    # 确保路径安全
    if not is_path_allowed(target_path):
        logger.warning(f"用户 {user_id} 尝试写入禁止的路径: {target_path}")
        log_command_execution(user_id, f"push {filename}", False, "禁止访问的路径")
        return {
            "success": False,
            "message": "目标路径禁止访问"
        }

    try:
        # 写入文件
        with open(target_path, "wb") as f:
            f.write(file_data)

        log_command_execution(user_id, f"push {filename}", True, f"文件大小: {len(file_data)} 字节")
        return {
            "success": True,
            "message": f"文件已保存到: {target_path}"
        }
    except Exception as e:
        logger.exception(f"文件写入失败: {filename}")
        log_command_execution(user_id, f"push {filename}", False, str(e))
        return {
            "success": False,
            "message": f"文件写入失败: {str(e)}"
        }
