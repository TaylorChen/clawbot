#!/bin/bash
# clawbot 启动脚本
# 支持启动、停止、重启和查看状态

# 获取脚本所在目录
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$SCRIPT_DIR"

# 配置变量
PID_FILE="$SCRIPT_DIR/.clawbot.pid"
LOG_FILE="$SCRIPT_DIR/logs/clawbot.log"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 错误处理函数
error() {
    echo -e "${RED}错误: $1${NC}" >&2
    exit 1
}

# 检查权限
check_permissions() {
    if [ ! -w "$SCRIPT_DIR" ]; then
        error "脚本所在目录不可写"
    fi

    if [ ! -w "$SCRIPT_DIR/logs" ]; then
        mkdir -p "$SCRIPT_DIR/logs" || error "无法创建日志目录"
    fi
}

# 检查虚拟环境
activate_venv() {
    if [ -d ".venv" ]; then
        source ".venv/bin/activate" || error "无法激活虚拟环境"
    else
        echo -e "${YELLOW}警告: 未找到虚拟环境，将使用系统 Python${NC}"
    fi
}

# 检查依赖
check_dependencies() {
    if ! python3 -c "import aiogram; import loguru; import pydantic" 2>/dev/null; then
        echo -e "${YELLOW}依赖未安装，正在安装...${NC}"
        pip3 install -r requirements.txt || error "依赖安装失败"
    fi
}

# 检查配置文件
check_config() {
    if [ ! -f ".env" ]; then
        echo -e "${YELLOW}未找到 .env 文件，正在创建...${NC}"
        cp .env.example .env || error "无法创建 .env 文件"
        echo "已创建 .env 文件，请编辑该文件配置 Bot Token"
        exit 1
    fi
}

# 获取 PID
get_pid() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$pid" ] && ps -p "$pid" >/dev/null 2>&1; then
            echo "$pid"
        else
            rm -f "$PID_FILE"
            echo ""
        fi
    else
        echo ""
    fi
}

# 启动函数
start() {
    local pid=$(get_pid)

    if [ -n "$pid" ]; then
        echo -e "${YELLOW}clawbot 已在运行中 (PID: $pid)${NC}"
        return 0
    fi

    echo -e "${GREEN}正在启动 clawbot...${NC}"

    check_permissions
    activate_venv
    check_dependencies
    check_config

    # 后台运行
    nohup python3 -m bot.main >"$LOG_FILE" 2>&1 < /dev/null &
    local pid=$!

    if [ -n "$pid" ]; then
        echo "$pid" >"$PID_FILE"
        echo -e "${GREEN}clawbot 启动成功 (PID: $pid)${NC}"
    else
        error "clawbot 启动失败"
    fi
}

# 停止函数
stop() {
    local pid=$(get_pid)

    if [ -z "$pid" ]; then
        echo -e "${YELLOW}clawbot 未在运行中${NC}"
        return 0
    fi

    echo -e "${RED}正在停止 clawbot (PID: $pid)...${NC}"

    kill "$pid" 2>/dev/null

    local count=0
    while [ $count -lt 30 ]; do
        if ! ps -p "$pid" >/dev/null 2>&1; then
            echo -e "${GREEN}clawbot 已停止${NC}"
            rm -f "$PID_FILE"
            return 0
        fi
        count=$((count + 1))
        sleep 1
    done

    echo -e "${RED}强制停止 clawbot...${NC}"
    kill -9 "$pid" 2>/dev/null

    sleep 2
    if ! ps -p "$pid" >/dev/null 2>&1; then
        echo -e "${GREEN}clawbot 已停止${NC}"
        rm -f "$PID_FILE"
        return 0
    else
        error "clawbot 无法停止"
    fi
}

# 重启函数
restart() {
    echo -e "${YELLOW}正在重启 clawbot...${NC}"
    stop
    start
}

# 状态检查函数
status() {
    local pid=$(get_pid)

    if [ -n "$pid" ]; then
        echo -e "${GREEN}clawbot 正在运行中 (PID: $pid)${NC}"
        if [ -f "$LOG_FILE" ]; then
            local start_time=$(stat "$LOG_FILE" 2>/dev/null | grep 'Modify:' | awk '{print $2" "$3}')
            echo "启动时间: $start_time"
            echo "日志文件: $LOG_FILE"
        fi
    else
        echo -e "${RED}clawbot 未在运行中${NC}"
    fi
}

# 查看日志函数
logs() {
    if [ ! -f "$LOG_FILE" ]; then
        error "日志文件不存在"
    fi

    if [ "$1" = "tail" ]; then
        tail -f "$LOG_FILE"
    else
        cat "$LOG_FILE"
    fi
}

# 帮助信息
show_help() {
    cat <<EOL
clawbot 管理脚本

用法: $0 <命令>

命令:
  start    启动 clawbot
  stop     停止 clawbot
  restart  重启 clawbot
  status   检查 clawbot 状态
  logs     查看 clawbot 日志
  logstail 实时查看 clawbot 日志
  help     显示此帮助信息

示例:
  $0 start        # 启动服务
  $0 status       # 检查状态
  $0 logstail     # 实时查看日志
  $0 restart      # 重启服务

EOL
}

# 主函数
main() {
    case "$1" in
        start)
            start
            ;;
        stop)
            stop
            ;;
        restart)
            restart
            ;;
        status)
            status
            ;;
        logs)
            logs
            ;;
        logstail|tail)
            logs tail
            ;;
        help|-h|--help)
            show_help
            ;;
        *)
            echo -e "${RED}未知命令: $1${NC}"
            show_help
            exit 1
            ;;
    esac
}

# 检查是否有其他实例正在运行
if [ "$1" = "start" ]; then
    if [ -f "$PID_FILE" ]; then
        old_pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$old_pid" ] && ps -p "$old_pid" >/dev/null 2>&1; then
            echo -e "${RED}clawbot 已在运行中 (PID: $old_pid)${NC}"
            exit 1
        fi
    fi
fi

main "$@"

