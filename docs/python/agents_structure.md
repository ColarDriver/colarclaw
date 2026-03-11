# `src/agents/` 目录结构

Python agents 模块从 TypeScript (`bk/src/agents/`) 完整迁移而来，按功能分类为 18 个子目录，共 254 个 Python 文件。

## 目录总览

| 子目录 | 文件数 | 说明 |
|---|---|---|
| `models/` | 31 | 模型定义、配置、选择、各厂商模型（Bedrock, BytePlus, Venice 等） |
| `core/` | 37 | 通用工具、上下文、缓存、错误处理、时间、PTY、序列化等 |
| `tools/` | 32 | 各工具实现（browser, discord, canvas, cron, image, memory, pdf, voice, web_search 等） |
| `pi_embedded_runner/` | 25 | 嵌入式运行器：模型解析、历史管理、压缩、扩展、执行等 |
| `subagent/` | 18 | 子代理生命周期：注册、公告、spawn、深度控制、附件等 |
| `sandbox/` | 15 | 沙箱管理：配置、Docker、安全验证、路径映射、FS 桥接等 |
| `auth_profiles/` | 15 | 认证配置：凭据存储、轮转、OAuth、外部 CLI 同步、诊断修复等 |
| `tool_system/` | 14 | 工具系统：策略、目录、展示、循环检测、合规性、管道等 |
| `skills/` | 13 | 技能系统：发现、过滤、序列化、打包、运行时刷新等 |
| `bash/` | 12 | Bash 执行：进程注册、审批请求、Host 执行、输出截断等 |
| `sessions/` | 9 | 会话管理：目录、修复、slug、工具结果守卫、写锁等 |
| `workspace_mgmt/` | 7 | 工作空间：路径解析、目录结构、运行、模板等 |
| `identity/` | 6 | 身份系统：代理身份、头像、身份文件、认证健康检查等 |
| `bootstrap/` | 5 | 项目启动：预算、缓存、文件收集、hooks 等 |
| `system_prompt/` | 4 | 系统提示词：生成、运行时参数、结构化报告等 |
| `cli/` | 4 | CLI 集成：Claude CLI runner、后端发现、凭据管理等 |
| `schema/` | 3 | Schema 构建：TypeBox 风格辅助函数、Gemini/xAI 清洗等 |
| `acp/` | 3 | ACP（Agent Communication Protocol）：spawn、父流管理等 |

## 各目录详细文件列表

### `models/` — 模型定义与配置
- `model_alias.py` — 模型别名解析
- `model_alias_lines.py` — 别名行格式化
- `model_auth.py` — 模型认证
- `model_auth_env_vars.py` — 认证环境变量
- `model_auth_label.py` — 认证标签
- `model_auth_markers.py` — Secret ref 标记
- `model_budget.py` — token 预算计算
- `model_cache_params.py` — 缓存参数
- `model_display.py` — 模型展示格式化
- `model_env_vars.py` — 环境变量解析
- `model_fallback.py` — 降级与回退策略
- `model_forward_compat.py` — 前向兼容
- `model_limits.py` — 上下文窗口与 token 限制
- `model_param_hints.py` — 参数提示
- `model_profile.py` — 模型配置文件
- `model_ref_profile.py` — 引用配置
- `model_scan.py` — 模型扫描发现
- `model_selection.py` — 模型选择与 provider 归一化
- `model_tool_support.py` — 工具支持检测
- `models_config.py` — 模型配置加载
- `models_config_merge.py` — 配置合并
- `models_config_providers.py` — provider 配置
- `bedrock_discovery.py` — AWS Bedrock 模型发现
- `byteplus_models.py` — BytePlus 模型定义
- `opencode_zen_models.py` — OpenCode Zen 模型
- `synthetic_models.py` — 合成模型定义
- `together_models.py` — Together AI 模型
- `venice_models.py` — Venice AI 模型
- `volc_models_shared.py` — 火山引擎共享模型
- `provider_capabilities.py` — provider 能力检测

### `core/` — 核心工具
- `agent_scope.py` — 代理作用域
- `announce_idempotency.py` — 公告幂等性
- `anthropic_payload_log.py` — Anthropic payload 日志
- `api_key_rotation.py` — API key 轮转
- `apply_patch.py` — 补丁应用
- `apply_patch_update.py` — 补丁更新
- `cache_trace.py` — 缓存追踪
- `channel_tools.py` — 频道工具
- `chutes_oauth.py` — Chutes OAuth
- `compaction.py` — 历史压缩
- `content_blocks.py` — 内容块
- `context.py` — 运行时上下文
- `current_time.py` — 当前时间
- `date_time.py` — 日期时间工具
- `defaults.py` — 默认值
- `failover_error.py` — 故障转移错误
- `glob_pattern.py` — Glob 模式匹配
- `image_sanitization.py` — 图片清洗
- `lanes.py` — 执行通道
- `owner_display.py` — Owner 展示
- `path_policy.py` — 路径策略
- `payload_redaction.py` — Payload 脱敏
- `pty_dsr.py` — PTY DSR 检测
- `pty_keys.py` — PTY 按键映射
- `queued_file_writer.py` — 排队文件写入
- `sanitize_for_prompt.py` — prompt 清洗
- `shell_utils.py` — Shell 工具
- `skills_manager.py` — 技能管理
- `spawned_context.py` — 派生上下文
- `stable_stringify.py` — 稳定序列化
- `stream_message_shared.py` — 流消息共享
- `timeout.py` — 超时控制
- `trace_base.py` — 追踪基础
- `transcript_policy.py` — 转录策略
- `usage.py` — 使用量追踪
- `vercel_ai_gateway.py` — Vercel AI 网关

### `tools/` — 工具实现
- `common.py` — 工具通用函数
- `agent_step.py` — 代理步进
- `agents_list_tool.py` — 代理列表
- `browser_tool.py` / `browser_tool_schema.py` / `browser_tool_actions.py` — 浏览器工具
- `canvas_tool.py` — 画布工具
- `cron_tool.py` — 定时任务
- `discord_actions.py` / `discord_actions_shared.py` / `discord_actions_guild.py` / `discord_actions_messaging.py` / `discord_actions_moderation.py` / `discord_actions_moderation_shared.py` / `discord_actions_presence.py` — Discord 工具
- `gateway_tool.py` — 网关工具
- `image_tool.py` / `image_tool_helpers.py` — 图片工具
- `media_tool_shared.py` — 媒体共享
- `memory_tool.py` — 记忆工具
- `message_tool.py` — 消息工具
- `model_config_helpers.py` — 模型配置辅助
- `nodes_tool.py` — 节点工具
- `pdf_tool.py` — PDF 工具
- `session_status_tool.py` — 会话状态
- `sessions_access.py` / `sessions_helpers.py` / `sessions_announce_target.py` / `sessions_spawn.py` — 会话工具
- `voice_tool.py` — 语音工具
- `web_search_tool.py` — 网页搜索

### `pi_embedded_runner/` — 嵌入式运行器
- `abort.py` — 中止错误检测
- `model.py` — 模型解析与 provider 回退
- `cache_ttl.py` — TTL 缓存
- `history.py` — 会话历史
- `compact.py` — 历史压缩
- `extensions.py` — 运行器扩展钩子
- `extra_params.py` — provider 额外参数
- `lanes.py` — 执行通道管理
- `google.py` — Google/Gemini 特定配置
- `sandbox_info.py` — 沙箱信息构建
- `session_manager_cache.py` / `session_manager_init.py` — 会话管理
- `run_types.py` / `run_params.py` / `run_payloads.py` / `run_attempt.py` / `run_images.py` — 运行系统
- `compaction_timeout.py` — 压缩超时保护
- `history_image_prune.py` — 历史图片修剪
- `run.py` / `runs.py` — 运行编排与并发管理
- `skills_runtime.py` — 运行时技能解析
- `sanitize_session_history.py` — 历史清洗
