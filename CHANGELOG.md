# 变更日志

所有重要的 clawbot 变更都将记录在此文件中。

---

## [1.1.0] - 2026-02-22

### 新增功能
- 添加启动脚本 `start.sh`，支持 start/stop/restart/status/logs 命令
- 新增 `/session set` 命令，支持固定会话
- 新增 `/sessions` 命令，支持列出最近的会话

### 改进
- 更新 `requirements.txt`，添加缺少的依赖包（pydantic-settings、aiohttp-socks）
- 优化文档（README.md 和 SOP.md），添加启动脚本使用说明
- 改进了故障排除流程，添加虚拟环境问题的解决方案

### 修复
- 修复了虚拟环境路径错误导致的依赖无法找到的问题
- 修复了代理配置相关的依赖缺失问题

---

## [1.0.0] - 2024-02-21

### 新增功能
- 实现了 Telegram Bot 基础框架
- 添加了 /run 命令，支持执行自然语言指令
- 添加了 /start 和 /help 命令
- 实现了基本的安全检查
- 实现了基本的日志记录功能

### 架构
- 使用 aiogram v3 作为 Telegram Bot 框架
- 使用 loguru 进行日志记录
- 项目采用模块化结构设计
- 支持配置管理

---

## 版本控制说明

本项目遵循 [语义化版本控制](https://semver.org/)，格式为：
- MAJOR（主版本）：不兼容的 API 变更
- MINOR（次版本）：向后兼容的功能新增
- PATCH（补丁版本）：向后兼容的 bug 修复

---

## 变更类型说明

- **Added**：新增功能
- **Changed**：功能变更
- **Deprecated**：即将废弃的功能
- **Removed**：已删除的功能
- **Fixed**：修复的 bug
- **Security**：安全相关的修复

---

## 贡献者

感谢所有为 clawbot 做出贡献的人！

- [Your Name](https://github.com/TaylorChen) - 项目创始人
