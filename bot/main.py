"""clawbot 主入口"""
import logging
import sys
import os
from loguru import logger
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from config.settings import settings
from security import is_user_allowed
from executor import (
    run_command,
    pull_file,
    push_file,
    list_sessions,
    run_tui_command,
    capture_tui_output,
    start_tui_session,
    stop_tui_session,
)

SESSION_BINDINGS_FILE = os.path.join(settings.LOG_DIR, "session_bindings.json")

def _load_session_bindings() -> dict:
    if not os.path.exists(SESSION_BINDINGS_FILE):
        return {}
    try:
        import json
        with open(SESSION_BINDINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_session_bindings(data: dict) -> None:
    import json
    with open(SESSION_BINDINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# 配置日志
logger.remove()
logger.add(sys.stdout, level=settings.LOG_LEVEL)
logger.add(
    os.path.join(settings.LOG_DIR, "clawbot.log"),
    rotation="1 day",
    retention="30 days",
    level=settings.LOG_LEVEL,
)

# 配置代理
import os

# 根据配置决定是否使用代理
if settings.proxy_url:
    # 使用代理
    print(f"使用代理: {settings.proxy_url}")
    os.environ['http_proxy'] = settings.proxy_url
    os.environ['https_proxy'] = settings.proxy_url
    os.environ['all_proxy'] = settings.proxy_url

    # 使用 aiogram 内置的代理支持
    from aiogram.client.session.aiohttp import AiohttpSession
    session = AiohttpSession(proxy=settings.proxy_url)
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, session=session)
else:
    # 不使用代理
    print("未配置代理，直接连接")
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)

# 初始化 Dispatcher
dp = Dispatcher()
TELEGRAM_MAX_LEN = 4000

async def _send_long_message(message: types.Message, text: str) -> None:
    if len(text) <= TELEGRAM_MAX_LEN:
        await message.answer(text)
        return
    for i in range(0, len(text), TELEGRAM_MAX_LEN):
        await message.answer(text[i:i + TELEGRAM_MAX_LEN])

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    """
    处理 /start 命令
    """
    user_id = message.from_user.id
    logger.info(f"用户 {user_id} 发送 /start 命令")

    if not is_user_allowed(user_id):
        logger.warning(f"禁止用户 {user_id} 访问")
        await message.answer("你没有访问权限，请联系管理员")
        return

    await message.answer(
        "欢迎使用 clawbot！\n\n"
        "我可以帮助你在 macOS 上执行命令。\n\n"
        "可用命令：\n"
        "/run <command> - 在 Claude CLI 中执行命令\n"
        "/run --session <id> <command> - 指定会话执行\n"
        "/run --continue <command> - 继续最近会话执行\n"
        "/sessions [n] - 列出最近 n 个 Claude 会话\n"
        "/session set <id> - 固定会话\n"
        "/tui <command> - 在 Claude Code TUI 中执行命令\n"
        "/tui-capture [n] - 获取 TUI 最近输出（也支持 /tui_capture）\n"
        "/tui-start - 启动 TUI 会话\n"
        "/tui-stop - 停止 TUI 会话\n"
        "/pull <file_path> - 拉取文件到 Telegram\n"
        "/push <file> - 推送文件到 macOS\n"
        "/help - 显示帮助信息"
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """
    处理 /help 命令
    """
    user_id = message.from_user.id
    logger.info(f"用户 {user_id} 发送 /help 命令")

    if not is_user_allowed(user_id):
        logger.warning(f"禁止用户 {user_id} 访问")
        await message.answer("你没有访问权限，请联系管理员")
        return

    await message.answer(
        "clawbot 帮助信息\n\n"
        "可用命令：\n"
        "/start - 欢迎信息\n"
        "/run <command> - 在 Claude CLI 中执行命令\n"
        "  示例：/run ls -la\n"
        "/run --session <id> <command> - 指定会话执行\n"
        "  示例：/run --session 1234-... 你好\n"
        "/run --continue <command> - 继续最近会话执行\n"
        "  示例：/run --continue 你好\n"
        "/sessions [n] - 列出最近 n 个 Claude 会话\n"
        "  示例：/sessions 10\n"
        "/session set <id> - 固定会话\n"
        "  示例：/session set 1234-...\n"
        "/tui <command> - 在 Claude Code TUI 中执行命令\n"
        "  示例：/tui 帮我总结这个项目结构\n"
        "/tui-capture [n] - 获取 TUI 最近输出（也支持 /tui_capture）\n"
        "  示例：/tui-capture 80\n"
        "/tui-start - 启动 TUI 会话\n"
        "/tui-stop - 停止 TUI 会话\n"
        "/pull <file_path> - 拉取文件到 Telegram\n"
        "  示例：/pull ~/Documents/report.txt\n"
        "/push <file> - 推送文件到 macOS\n"
        "  使用方法：回复文件并发送 /push 命令\n"
        "/help - 显示此帮助信息"
    )

@dp.message(Command("sessions"))
async def cmd_sessions(message: types.Message):
    """
    处理 /sessions 命令
    """
    user_id = message.from_user.id
    logger.info(f"用户 {user_id} 发送 /sessions 命令")

    if not is_user_allowed(user_id):
        logger.warning(f"禁止用户 {user_id} 访问")
        await message.answer("你没有访问权限，请联系管理员")
        return

    # 提取可选参数：数量与活跃分钟数
    parts = message.text.split(maxsplit=2)
    limit = 10
    active_minutes = 60
    if len(parts) >= 2:
        try:
            limit = int(parts[1].strip())
        except ValueError:
            await message.answer("参数必须是数字，例如：/sessions 10 或 /sessions 10 60")
            return
    if len(parts) == 3:
        try:
            active_minutes = int(parts[2].strip())
        except ValueError:
            await message.answer("活跃分钟数必须是数字，例如：/sessions 10 60")
            return

    result = list_sessions(limit=limit, active_minutes=active_minutes)

    if result["success"]:
        await message.answer(result["message"])
    else:
        await message.answer(f"❌ 获取会话失败\n\n{result['message']}")

@dp.message(Command("session"))
async def cmd_session(message: types.Message):
    """
    处理 /session set 命令
    """
    user_id = message.from_user.id
    logger.info(f"用户 {user_id} 发送 /session 命令")

    if not is_user_allowed(user_id):
        logger.warning(f"禁止用户 {user_id} 访问")
        await message.answer("你没有访问权限，请联系管理员")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3 or parts[1] != "set":
        await message.answer("用法：/session set <id>")
        return

    session_id = parts[2].strip()
    if not session_id:
        await message.answer("请提供 session id\n\n示例：/session set 1234-...")
        return

    bindings = _load_session_bindings()
    bindings[str(user_id)] = session_id
    _save_session_bindings(bindings)
    await message.answer(f"✅ 已固定会话: {session_id}\n之后 /run 将默认使用该会话")

@dp.message(Command("run"))
async def cmd_run(message: types.Message):
    """
    处理 /run 命令
    """
    user_id = message.from_user.id
    logger.info(f"用户 {user_id} 发送 /run 命令")

    if not is_user_allowed(user_id):
        logger.warning(f"禁止用户 {user_id} 访问")
        await message.answer("你没有访问权限，请联系管理员")
        return

    # 提取命令参数
    # 使用 split 方法更可靠地提取命令参数
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("请提供要执行的命令\n\n示例：/run ls -la")
        return

    raw = parts[1].strip()
    command = raw
    session_id = None
    use_continue = False

    if raw.startswith("--session "):
        rest = raw[len("--session "):].strip()
        if " " not in rest:
            await message.answer("请提供 session id 和命令\n\n示例：/run --session <id> 你好")
            return
        session_id, command = rest.split(" ", 1)
        command = command.strip()
    elif raw.startswith("--continue "):
        use_continue = True
        command = raw[len("--continue "):].strip()
    else:
        bindings = _load_session_bindings()
        session_id = bindings.get(str(user_id))
    logger.info(f"用户 {user_id} 执行命令：{command}")

    # 在执行前先记录命令参数的详细信息，用于调试
    logger.info(f"命令参数长度: {len(command)}")
    logger.info(f"命令参数内容: '{command}'")

    # 执行命令
    result = run_command(user_id, command, session_id=session_id, use_continue=use_continue)

    # 记录命令执行结果的详细信息
    logger.info(f"命令执行结果: {result}")

    # 格式化回复
    if result["success"]:
        await _send_long_message(message, f"✅ 执行成功\n\n{result['message']}")
    else:
        await message.answer(f"❌ 执行失败\n\n{result['message']}")

@dp.message(Command("tui"))
async def cmd_tui(message: types.Message):
    """
    处理 /tui 命令
    """
    user_id = message.from_user.id
    logger.info(f"用户 {user_id} 发送 /tui 命令")

    if not is_user_allowed(user_id):
        logger.warning(f"禁止用户 {user_id} 访问")
        await message.answer("你没有访问权限，请联系管理员")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("请提供要执行的命令\n\n示例：/tui 你好")
        return

    command = parts[1].strip()
    result = run_tui_command(user_id, command)

    if result["success"]:
        await _send_long_message(message, f"✅ 已发送到 TUI\n\n{result['message']}")
    else:
        await message.answer(f"❌ 执行失败\n\n{result['message']}")

@dp.message(Command("tui-capture"))
@dp.message(Command("tui_capture"))
@dp.message(Command("tuicapture"))
async def cmd_tui_capture(message: types.Message):
    """
    处理 /tui-capture 命令
    """
    user_id = message.from_user.id
    logger.info(f"用户 {user_id} 发送 /tui-capture 命令")

    if not is_user_allowed(user_id):
        logger.warning(f"禁止用户 {user_id} 访问")
        await message.answer("你没有访问权限，请联系管理员")
        return

    parts = message.text.split(maxsplit=1)
    lines = None
    if len(parts) == 2:
        try:
            lines = int(parts[1].strip())
        except ValueError:
            await message.answer("参数必须是数字，例如：/tui-capture 80")
            return

    result = capture_tui_output(user_id, lines=lines)
    if result["success"]:
        await _send_long_message(message, f"✅ TUI 输出\n\n{result['message']}")
    else:
        await message.answer(f"❌ 获取失败\n\n{result['message']}")

@dp.message(Command("tui-start"))
async def cmd_tui_start(message: types.Message):
    """
    处理 /tui-start 命令
    """
    user_id = message.from_user.id
    logger.info(f"用户 {user_id} 发送 /tui-start 命令")

    if not is_user_allowed(user_id):
        logger.warning(f"禁止用户 {user_id} 访问")
        await message.answer("你没有访问权限，请联系管理员")
        return

    result = start_tui_session(user_id)
    if result["success"]:
        await message.answer(f"✅ {result['message']}")
    else:
        await message.answer(f"❌ {result['message']}")

@dp.message(Command("tui-stop"))
async def cmd_tui_stop(message: types.Message):
    """
    处理 /tui-stop 命令
    """
    user_id = message.from_user.id
    logger.info(f"用户 {user_id} 发送 /tui-stop 命令")

    if not is_user_allowed(user_id):
        logger.warning(f"禁止用户 {user_id} 访问")
        await message.answer("你没有访问权限，请联系管理员")
        return

    result = stop_tui_session(user_id)
    if result["success"]:
        await message.answer(f"✅ {result['message']}")
    else:
        await message.answer(f"❌ {result['message']}")

@dp.message(Command("pull"))
async def cmd_pull(message: types.Message):
    """
    处理 /pull 命令
    """
    user_id = message.from_user.id
    logger.info(f"用户 {user_id} 发送 /pull 命令")

    if not is_user_allowed(user_id):
        logger.warning(f"禁止用户 {user_id} 访问")
        await message.answer("你没有访问权限，请联系管理员")
        return

    # 提取文件路径
    file_path = message.text[len("/pull "):].strip()
    if not file_path:
        await message.answer("请提供要拉取的文件路径\n\n示例：/pull ~/Documents/report.txt")
        return

    logger.debug(f"用户 {user_id} 尝试拉取文件：{file_path}")

    # 验证和处理文件
    result = pull_file(user_id, file_path)

    if result["success"]:
        try:
            await message.answer_document(
                document=types.FSInputFile(result["file_path"])
            )
        except Exception as e:
            logger.exception(f"文件发送失败：{result['file_path']}")
            await message.answer(f"❌ 文件发送失败：{str(e)}")
    else:
        await message.answer(f"❌ 拉取失败\n\n{result['message']}")

@dp.message(Command("push"))
async def cmd_push(message: types.Message):
    """
    处理 /push 命令
    """
    user_id = message.from_user.id
    logger.info(f"用户 {user_id} 发送 /push 命令")

    if not is_user_allowed(user_id):
        logger.warning(f"禁止用户 {user_id} 访问")
        await message.answer("你没有访问权限，请联系管理员")
        return

    # 检查是否回复了文件
    if not message.reply_to_message or not (
        message.reply_to_message.document or message.reply_to_message.photo
    ):
        await message.answer(
            "请回复要推送的文件并发送 /push 命令\n\n"
            "使用方法：\n"
            "1. 发送文件\n"
            "2. 回复该文件并发送 /push"
        )
        return

    logger.debug(f"用户 {user_id} 尝试推送文件")

    # 处理推送的文件
    try:
        if message.reply_to_message.document:
            # 处理文档
            file = await bot.get_file(message.reply_to_message.document.file_id)
            file_data = await bot.download_file(file.file_path)
            filename = message.reply_to_message.document.file_name
        else:
            # 处理照片（获取最高分辨率）
            photo = message.reply_to_message.photo[-1]
            file = await bot.get_file(photo.file_id)
            file_data = await bot.download_file(file.file_path)
            filename = f"photo_{photo.file_unique_id}.jpg"

        # aiogram 返回 BytesIO，需要转换为 bytes
        if hasattr(file_data, "read"):
            file_bytes = file_data.read()
        else:
            file_bytes = file_data

        logger.debug(f"收到文件：{filename}，大小：{len(file_bytes)} 字节")

        # 保存文件
        result = push_file(user_id, file_bytes, filename)

        if result["success"]:
            await message.answer(f"✅ 推送成功\n\n{result['message']}")
        else:
            await message.answer(f"❌ 推送失败\n\n{result['message']}")

    except Exception as e:
        logger.exception("文件推送过程中发生错误")
        await message.answer(f"❌ 推送失败\n\n{str(e)}")

async def main():
    """
    主函数
    """
    logger.info("clawbot 正在启动...")

    # 检查配置是否完整
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("未配置 TELEGRAM_BOT_TOKEN，请在 .env 文件中设置")
        return

    logger.info("clawbot 启动成功！")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("clawbot 已停止")
    except Exception as e:
        logger.exception("clawbot 启动失败")
