"""执行器模块 - 负责调用 Claude CLI 执行命令"""
import subprocess
import os
import json
import shlex
import re
import time
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
        logger.exception("列出会话过程中发生错误")
        return {
            "success": False,
            "message": f"列出会话失败: {str(e)}"
        }


def _tmux_run(args: list[str], *, timeout: float = 5.0) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["tmux", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=["tmux", *args],
            returncode=124,
            stdout="",
            stderr="tmux command timed out",
        )


def _ensure_tui_session() -> dict:
    session_name = settings.TUI_SESSION_NAME
    log_path = os.path.join(settings.LOG_DIR, settings.TUI_LOG_FILE)
    os.makedirs(settings.LOG_DIR, exist_ok=True)
    has = _tmux_run(["has-session", "-t", session_name])
    if has.returncode == 0:
        _tmux_run(["pipe-pane", "-o", "-t", session_name, f"cat >> {log_path}"])
        return {"success": True, "message": "TUI 会话已存在"}

    cmd = ["new-session", "-d", "-s", session_name, "-c", settings.WORKSPACE_DIR]
    cmd.extend(shlex.split(settings.CLAUDE_TUI_CMD))
    created = _tmux_run(cmd)
    if created.returncode != 0:
        return {
            "success": False,
            "message": f"启动 TUI 会话失败: {created.stderr.strip()}"
        }
    _tmux_run(["pipe-pane", "-o", "-t", session_name, f"cat >> {log_path}"])
    return {"success": True, "message": "TUI 会话已启动"}


def _capture_tui_raw(lines: int | None = None) -> dict:
    session_name = settings.TUI_SESSION_NAME
    capture_lines = lines or settings.TUI_CAPTURE_LINES
    logger.info(f"TUI capture 请求: session={session_name}, lines={capture_lines}")
    result = _tmux_run([
        "capture-pane",
        "-p",
        "-e",
        "-J",
        "-a",
        "-t",
        session_name,
        "-S",
        f"-{int(capture_lines)}",
    ])
    if result.returncode != 0 and "no alternate screen" in (result.stderr or ""):
        result = _tmux_run([
            "capture-pane",
            "-p",
            "-e",
            "-J",
            "-t",
            session_name,
            "-S",
            f"-{int(capture_lines)}",
        ])
    if result.returncode == 124:
        return {
            "success": False,
            "message": "获取 TUI 输出超时，请重试"
        }
    logger.info(
        f"TUI capture 结果: code={result.returncode}, stdout_len={len(result.stdout)}, stderr='{result.stderr.strip()}'"
    )
    if result.returncode != 0:
        return {
            "success": False,
            "message": f"获取 TUI 输出失败: {result.stderr.strip()}"
        }
    output = result.stdout
    if output:
        # Strip ANSI escape sequences and non-printable chars (keep newlines/tabs)
        output = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", output)
        output = re.sub(r"\x1b\][^\x07]*\x07", "", output)
        output = "".join(ch for ch in output if ch == "\n" or ch == "\t" or ch >= " ")
        output = output.strip()
    if output:
        return {
            "success": True,
            "message": output
        }

    log_path = os.path.join(settings.LOG_DIR, settings.TUI_LOG_FILE)
    if os.path.isfile(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                data = f.readlines()
            tail = "".join(data[-max(1, int(capture_lines)):]).strip()
            if tail:
                return {
                    "success": True,
                    "message": tail
                }
        except Exception:
            pass
    return {
        "success": True,
        "message": "(no output)"
    }


def _capture_tui(lines: int | None = None) -> dict:
    raw = _capture_tui_raw(lines=lines)
    if not raw.get("success"):
        return raw
    message = raw.get("message", "")
    if message and message != "(no output)":
        message = _limit_tui_output(message)
    return {
        "success": True,
        "message": message
    }


def _limit_tui_output(text: str) -> str:
    reply = _extract_tui_reply(text)
    if not reply:
        # Fallback: keep only the tail
        lines = [ln.rstrip() for ln in text.splitlines()]
        tail = lines
        if settings.TUI_REPLY_MAX_LINES > 0:
            tail = tail[-settings.TUI_REPLY_MAX_LINES:]
        reply = "\n".join(tail).strip()

    if settings.TUI_REPLY_MAX_CHARS > 0 and len(reply) > settings.TUI_REPLY_MAX_CHARS:
        reply = reply[-settings.TUI_REPLY_MAX_CHARS:]
    return reply.strip() or "(no output)"


def _extract_tui_reply(text: str) -> str:
    lines = [ln.rstrip() for ln in text.splitlines()]
    reply_lines: list[str] = []
    latest_reply: list[str] = []
    for ln in lines:
        if ln.strip().startswith(("⏺", "●")):
            # Start a new reply block
            reply_lines = [ln.strip()]
            continue
        if reply_lines:
            if ln.strip().startswith(("❯", ">", "esc to interrupt", "✗", "✢", "─")):
                latest_reply = reply_lines
                reply_lines = []
                continue
            if ln.strip():
                reply_lines.append(ln.strip())
    if reply_lines:
        latest_reply = reply_lines
    return "\n".join(latest_reply).strip()


def _extract_reply_after_prompt(text: str, command: str) -> str:
    lines = [ln.rstrip() for ln in text.splitlines()]
    needle = command.strip()
    if len(needle) > 32:
        needle = needle[-32:]
    last_idx = -1
    for i, ln in enumerate(lines):
        if needle and needle in ln:
            last_idx = i
    if last_idx == -1:
        return ""
    reply_lines: list[str] = []
    for ln in lines[last_idx + 1:]:
        if ln.strip().startswith(("⏺", "●")):
            reply_lines = [ln.strip()]
            continue
        if reply_lines:
            if ln.strip().startswith(("❯", ">", "esc to interrupt", "✗", "✢", "─")):
                break
            if ln.strip():
                reply_lines.append(ln.strip())
    return "\n".join(reply_lines).strip()


def run_tui_command(user_id: int, command: str, *, capture_lines: int | None = None) -> dict:
    """
    在 Claude Code TUI 中执行命令（tmux 会话）
    """
    logger.info(f"用户 {user_id} 尝试执行 TUI 命令: {command}")

    if not is_command_allowed(command):
        logger.warning(f"用户 {user_id} 尝试执行禁止的命令: {command}")
        log_command_execution(user_id, f"tui:{command}", False, "禁止的命令")
        return {
            "success": False,
            "message": "命令包含禁止关键词，请检查后重试"
        }

    try:
        ensure = _ensure_tui_session()
        if not ensure["success"]:
            log_command_execution(user_id, f"tui:{command}", False, ensure["message"])
            return ensure

        session_name = settings.TUI_SESSION_NAME
        before = _capture_tui_raw(lines=capture_lines)
        before_reply = _extract_tui_reply(before.get("message", ""))

        # Ensure not stuck in copy-mode and send a real Enter key
        _tmux_run(["send-keys", "-t", session_name, "-X", "cancel"])
        _tmux_run(["send-keys", "-t", session_name, "C-u"])
        _tmux_run(["send-keys", "-t", session_name, "-l", command])
        send = _tmux_run(["send-keys", "-t", session_name, "Enter"])
        if send.returncode != 0:
            msg = send.stderr.strip() or "发送指令失败"
            log_command_execution(user_id, f"tui:{command}", False, msg)
            return {"success": False, "message": msg}

        # 多次抓取，给 TUI 留出渲染时间
        output = None
        for _ in range(6):
            time.sleep(settings.TUI_CAPTURE_DELAY)
            current = _capture_tui_raw(lines=capture_lines)
            if current["success"]:
                current_reply = _extract_reply_after_prompt(current.get("message", ""), command)
                if not current_reply:
                    current_reply = _extract_tui_reply(current.get("message", ""))
                if current_reply and current_reply != before_reply:
                    output = {
                        "success": True,
                        "message": _limit_tui_output(current_reply)
                    }
                    break
            output = current

        if output is None:
            output = {
                "success": True,
                "message": "(no output)"
            }

        log_command_execution(
            user_id,
            f"tui:{command}",
            output["success"],
            output["message"] if output["success"] else output["message"],
        )
        return output
    except FileNotFoundError:
        log_command_execution(user_id, f"tui:{command}", False, "tmux 未找到")
        return {
            "success": False,
            "message": "tmux 未找到，请先安装 tmux"
        }
    except Exception as e:
        logger.exception(f"TUI 命令执行过程中发生错误: {command}")
        log_command_execution(user_id, f"tui:{command}", False, str(e))
        return {
            "success": False,
            "message": f"执行过程中发生错误: {str(e)}"
        }


def start_tui_session(user_id: int) -> dict:
    try:
        ensure = _ensure_tui_session()
        log_command_execution(user_id, "tui:start", ensure["success"], ensure["message"])
        return ensure
    except FileNotFoundError:
        log_command_execution(user_id, "tui:start", False, "tmux 未找到")
        return {
            "success": False,
            "message": "tmux 未找到，请先安装 tmux"
        }
    except Exception as e:
        logger.exception("TUI 会话启动过程中发生错误")
        log_command_execution(user_id, "tui:start", False, str(e))
        return {
            "success": False,
            "message": f"执行过程中发生错误: {str(e)}"
        }


def capture_tui_output(user_id: int, *, lines: int | None = None) -> dict:
    try:
        output = _capture_tui(lines=lines)
        log_command_execution(
            user_id,
            "tui:capture",
            output["success"],
            output["message"] if output["success"] else output["message"],
        )
        return output
    except FileNotFoundError:
        log_command_execution(user_id, "tui:capture", False, "tmux 未找到")
        return {
            "success": False,
            "message": "tmux 未找到，请先安装 tmux"
        }
    except Exception as e:
        logger.exception("TUI 输出获取过程中发生错误")
        log_command_execution(user_id, "tui:capture", False, str(e))
        return {
            "success": False,
            "message": f"执行过程中发生错误: {str(e)}"
        }


def stop_tui_session(user_id: int) -> dict:
    try:
        session_name = settings.TUI_SESSION_NAME
        killed = _tmux_run(["kill-session", "-t", session_name])
        if killed.returncode != 0:
            msg = killed.stderr.strip() or "停止失败"
            log_command_execution(user_id, "tui:stop", False, msg)
            return {"success": False, "message": msg}
        log_command_execution(user_id, "tui:stop", True, "已停止")
        return {"success": True, "message": "TUI 会话已停止"}
    except FileNotFoundError:
        log_command_execution(user_id, "tui:stop", False, "tmux 未找到")
        return {
            "success": False,
            "message": "tmux 未找到，请先安装 tmux"
        }
    except Exception as e:
        logger.exception("TUI 会话停止过程中发生错误")
        log_command_execution(user_id, "tui:stop", False, str(e))
        return {
            "success": False,
            "message": f"执行过程中发生错误: {str(e)}"
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
