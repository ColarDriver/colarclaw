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

---

# `src/auto_reply/` 目录结构

从 TypeScript (`bk/src/auto-reply/`) 完整迁移而来，共 32 个 Python 文件。

## 目录总览

| 子目录/文件 | 文件数 | 说明 |
|---|---|---|
| 顶层模块 | 17 | 类型、分块、信封、命令、心跳、调度等 |
| `reply/` | 15 | 回复管道：agent runner、ACP、命令处理、分发器等 |

## 顶层模块（17 个文件）

- `types.py` — 所有类型定义（CommandScope, ChatCommandDefinition, ReplyPayload 等）
- `chunk.py` — 文本分块：按长度、换行、段落、Markdown 感知拆分
- `envelope.py` — 消息信封格式化：频道、发送者、时间戳
- `model.py` — `/model` 指令提取
- `model_runtime.py` — provider/model ref 格式化与解析
- `command_detection.py` — 控制命令检测、中止触发词
- `command_auth.py` — 命令授权解析
- `commands_args.py` — 命令参数格式化器（config, debug, queue, exec）
- `commands_registry.py` — 命令注册系统与默认命令定义
- `heartbeat.py` — 心跳提示词、内容检查、token 剥离
- `heartbeat_reply_payload.py` — 心跳回复 payload 解析
- `inbound_debounce.py` — 入站消息防抖缓冲
- `media_note.py` — `[media attached: ...]` 媒体注解构建
- `fallback_state.py` — 模型降级状态管理与通知
- `group_activation.py` — 群组激活模式（mention/always）
- `dispatch.py` — 消息调度管道

## `reply/` 子目录（15 个文件）

- `abort.py` — 中止触发检测与回复截断
- `agent_runner.py` — Agent 运行器：配置、payload 构建、memory、执行
- `acp_projector.py` — ACP 事件投影、流设置、重置目标
- `block_reply_pipeline.py` — 流式文本块合并与管道处理
- `reply_dispatcher.py` — 回复分发器生命周期管理
- `commands.py` — 所有命令处理器（status, help, compact, model, config 等 20+）
- `commands_acp.py` — ACP 命令：诊断、生命周期、安装提示、运行时选项
- `channel_context.py` — 频道回复上下文解析
- `body.py` — 回复正文构建与格式化
- `command_gates.py` — 命令门控（授权检查）
- `dispatch_from_config.py` — 基于配置的回复分发
- `inbound_context.py` — 入站上下文最终化
- `audio_tags.py` — 音频标签提取与剥离
- `bash_command.py` — Bash 命令执行

---

# `src/acp/` 目录结构

从 TypeScript (`bk/src/acp/`) 完整迁移而来，共 27 个 Python 文件。

## 目录总览

| 子目录/文件 | 文件数 | 说明 |
|---|---|---|
| 顶层模块 | 14 | 类型、会话存储、策略、客户端/服务端、翻译器等 |
| `runtime/` | 7 | 运行时类型、错误、后端注册、会话标识/元数据 |
| `control_plane/` | 6 | 控制面：会话管理器、生成、缓存、运行时选项、队列 |

## 顶层模块（14 个文件）

- `types.py` — AcpSession, AcpServerOptions, ACP_AGENT_INFO
- `meta.py` — read_string/read_bool/read_number 元数据读取
- `session.py` — InMemorySessionStore：TTL 驱逐、容量限制、运行追踪
- `policy.py` — ACP 策略检查：启用状态、dispatch 策略、agent 白名单
- `commands.py` — ACP 可用命令注册（27 个命令定义）
- `secret_file.py` — 安全文件读取（符号链接检查、大小限制）
- `conversation_id.py` — Telegram topic 会话 ID 解析与格式化
- `event_mapper.py` — prompt 文本/附件提取、工具标题格式化、工具类型推断
- `session_mapper.py` — 会话 key 解析、session meta 解析、会话重置
- `client.py` — ACP 客户端：工具权限解析、自动批准、子进程 spawn
- `server.py` — ACP 网关服务器：参数解析、stdio 服务
- `translator.py` — AcpGatewayAgent 翻译桥：ACP 协议 ↔ 网关 WebSocket
- `persistent_bindings.py` — 频道绑定配置、会话 key 构建、binding 解析、路由

## `runtime/` 子目录（7 个文件）

- `types.py` — AcpRuntimeSessionMode, AcpRuntimeSession, AcpRuntimeSessionOptions
- `errors.py` — AcpRuntimeError 异常、错误文本格式化
- `registry.py` — ACP 后端注册表
- `session_identifiers.py` — 会话标识符构建与解析
- `session_identity.py` — 会话身份解析
- `session_meta.py` — 会话元数据读写

## `control_plane/` 子目录（6 个文件）

- `manager.py` — AcpSessionManager：init/close/resolve 会话生命周期
- `spawn.py` — ACP 会话生成
- `runtime_cache.py` — TTL 运行时状态缓存
- `runtime_options.py` — 运行时选项解析
- `session_actor_queue.py` — 按会话串行化异步操作队列

---

# `src/browser/` 目录结构

从 TypeScript (`bk/src/browser/`) 完整迁移而来，共 25 个 Python 文件。

## 目录总览

| 子目录/文件 | 文件数 | 说明 |
|---|---|---|
| 顶层模块 | 18 | CDP、Chrome、Playwright、客户端/服务端、认证等 |
| `routes/` | 7 | HTTP 路由：agent 操作、标签页、状态、快照 |

## 顶层模块（18 个文件）

- `constants.py` — 默认常量（颜色、端口、快照字符上限）
- `config.py` — 浏览器配置解析：端口、profiles、CDP URL、SSRF 策略
- `cdp.py` — Chrome DevTools Protocol：WebSocket 连接、截图、JS 评估、DOM/ARIA 快照、querySelector
- `chrome.py` — Chrome 可执行文件发现、启动参数、用户数据目录、profile 装饰
- `client.py` — 浏览器控制 HTTP 客户端：状态、标签页、快照、profiles
- `client_actions.py` — 浏览器操作：click、type、scroll、hover、navigate、evaluate
- `server.py` — 浏览器控制 HTTP 服务器：生命周期、context、中间件
- `profiles.py` — Profile 管理：创建、删除、端口分配
- `pw_session.py` — Playwright 会话管理：连接、页面状态跟踪、console/error/network 监控
- `pw_tools.py` — Playwright 工具实现：click、type、navigate、screenshot、download 等
- `pw_ai.py` — AI 模块：snapshot-for-AI、角色快照、AI 模块加载
- `auth.py` — 认证：token/password 验证、CSRF 保护、bridge 认证注册
- `navigation_guard.py` — 导航 SSRF 保护：URL 策略验证
- `bridge_server.py` — WebSocket bridge 服务器
- `extension_relay.py` — Chrome 扩展 relay：消息路由、CDP 桥接
- `screenshot.py` — 截图捕获与处理
- `paths.py` — 文件路径、安全文件名、原子写入、target ID、tab 注册表、控制服务

## `routes/` 子目录（7 个文件）

- `types.py` — 路由类型：BrowserRouteContext、BrowserRouteRegistrar
- `utils.py` — 路由工具：JSON 响应、错误响应、输出路径
- `dispatcher.py` — 路由注册调度器
- `basic.py` — 基本路由：status、start、stop、reset-profile
- `tabs.py` — 标签页路由：list、open、close、focus、action
- `agent.py` — Agent 路由：act、snapshot、storage、debug、download

---

# `src/media/` 目录结构

从 TypeScript (`bk/src/media/`) 完整迁移而来，共 6 个 Python 文件。

| 文件 | 说明 |
|---|---|
| `constants.py` | 媒体类型（image/audio/video/document）、大小限制（6/16/16/100MB） |
| `mime.py` | MIME 检测与扩展名映射（EXT↔MIME 双向映射、file-type sniffing、音频文件识别） |
| `store.py` | 媒体存储：URL 下载/本地读取/Buffer 保存、TTL 清理、安全文件名、原始文件名嵌入 |
| `parse.py` | MEDIA 令牌提取：从文本输出中解析 MEDIA: URL/路径、audio_as_voice 标签 |
| `utils.py` | 综合工具：audio 转换、Base64 编解码、ffmpeg、图片操作、PDF 提取、内容安全路径策略、临时文件 |

---

# `src/media_understanding/` 目录结构

从 TypeScript (`bk/src/media-understanding/`) 完整迁移而来，共 6 个 Python 文件。

## 目录总览

| 子目录/文件 | 文件数 | 说明 |
|---|---|---|
| 顶层模块 | 5 | 类型、Runner、附件、工具 |
| `providers/` | 1 | 9 个 Provider 实现 + 注册表 |

## 顶层模块

- `types.py` — 类型定义：MediaAttachment、AudioTranscriptionRequest/Result、VideoDescriptionRequest/Result、ImageDescriptionRequest/Result、MediaUnderstandingProvider Protocol
- `runner.py` — 主入口：Provider 注册、capability 运行、自动模型解析、决策摘要
- `attachments.py` — 附件处理：规范化、按能力选择、MediaAttachmentCache（带缓冲读取）
- `utils.py` — 综合工具：默认 Provider 列表、scope 决策、模型解析、并发限制、格式化、音频预检、Gemini 输出提取

## `providers/` 子目录

- `__init__.py` — 9 个 Provider 实现（OpenAI、Anthropic、Google、Deepgram、Groq、Minimax、Mistral、Moonshot、Zai）+ 注册表 + ID 别名映射

---

# `src/plugin_sdk/` 目录结构

从 TypeScript (`bk/src/plugin-sdk/`) 完整迁移而来，共 11 个 Python 文件。
原始 85 个 TS 文件是一个巨大的 re-export barrel + 工具集，专为第三方插件开发者提供统一 API。

| 文件 | 说明 |
|---|---|
| `core.py` | 核心类型：OpenClawPluginApi Protocol、OpenClawPluginService Protocol、ProviderAuthResult/Context |
| `webhooks.py` | Webhook 管理：target 注册/匹配、request guards、body 读取、rate limiter、in-flight 控制 |
| `group_access.py` | 群组访问控制：SenderGroupAccessDecision、GroupRouteAccessDecision、MatchedGroupAccessDecision + 完整评估逻辑 |
| `reply_payload.py` | 出站回复：OutboundReplyPayload 规范化、chunked text + media 发送、attachment 链接格式化 |
| `inbound_envelope.py` | 入站信封构建器：route 解析、session 时间戳查找、可配置格式化器 |
| `inbound_reply_dispatch.py` | 入站回复调度：session 记录 + dispatch 管线、settled dispatcher 模式 |
| `status_helpers.py` | 状态快照：channel runtime state、account status、probe summary、token summary、issue 收集 |
| `channel_config.py` | 频道配置：scoped account accessors、WhatsApp/iMessage allowFrom + defaultTo 解析 |
| `command_auth.py` | 命令授权：DM/群组授权决策、sender command auth（store allowFrom + access groups） |
| `utils.py` | 综合工具（70+ 函数）：account-id、allow-from、file-lock、json-store（原子写入）、keyed-async-queue、OAuth PKCE、text-chunking、SSRF 检测、run-command、temp-path、channel-send-result、agent-media-payload |

---

# `src/plugins/` 目录结构

从 TypeScript (`bk/src/plugins/`) 完整迁移而来，共 7 个 Python 文件。
原始 50 个 TS 文件（含 runtime/ 子目录 15 个文件）组成插件运行时系统，负责插件的完整生命周期。

| 文件 | 说明 |
|---|---|
| `types.py` | 类型定义：PluginHookName（24 种 hook）、PluginDefinition、PluginCommandDefinition、ProviderPlugin、所有 hook event/result 类型 |
| `registry.py` | 注册表：PluginRegistry（tools/hooks/channels/providers/commands/services/http-routes/gateway）、PluginRecord、create_api |
| `manifest.py` | Manifest 加载：openclaw.plugin.json 解析、PackageManifest、extension entries |
| `loader.py` | 加载器：discover_plugins（工作区扫描）、load_openclaw_plugins（动态 import + 注册） |
| `runtime.py` | 运行时（含 15 个 TS runtime/ 子文件）：PluginRuntime（config/system/media/TTS/STT/tools/events/logging/state/subagent/channel）、GatewayRequestScope、SubagentRun/Wait/GetSessionMessages/DeleteSession 参数与结果 |
| `utils.py` | 综合工具：commands 注册/清理、config-state 规范化、discovery、enable 决策、HTTP path/registry、hook runner、path-safety、schema validator、services 启停、slots 决策、status、install/uninstall |

---

# `src/infra/` 目录结构

从 TypeScript (`bk/src/infra/`) 完整迁移而来，共 13 个 Python 文件。
原始 196 个 TS 文件是系统核心基础设施层，覆盖事件总线、进程管理、网络、文件系统、安全等。

| 文件 | 覆盖 TS 文件 | 说明 |
|---|---|---|
| `events.py` | 6 个 | AgentEventPayload + emit/listen、SystemEvent 队列（session-scoped）、DiagnosticEvent、HeartbeatEvent |
| `errors.py` | 1 个 | 错误提取（code/name/errno）、格式化、error graph 遍历、uncaught 处理 |
| `env.py` | 2 个 | 环境变量日志/规范化、.env 加载（dotenv）、truthy 判断 |
| `heartbeat.py` | 5 个 | HeartbeatWakeController（coalesced dispatch + reason priority）、active hours、visibility |
| `exec_safety.py` | 16 个 | 命令 allowlist/approvals、obfuscation 检测、safe-bin policy profiles、exec host（async subprocess）、wrapper 解析 |
| `networking.py` | 15 个 | HTTP fetch（aiohttp）、FixedWindowRateLimiter、端口扫描、SSRF guard、URL 处理（sanitize/allowlist/metadata）、TLS、WebSocket |
| `file_ops.py` | 15 个 | 文件锁（fcntl）、safe FS 操作、SHA256 identity、tar 归档、原子 JSON 写入、LockedJsonStore、流式行读取、临时文件 |
| `process.py` | 12 个 | abort signal、BackoffPolicy、DedupeCache（TTL + max-size）、PID 文件、shutdown handler、signal 安装、Singleton/Lazy/Once、retry（sync+async） |
| `device.py` | 9 个 | DeviceIdentity + UUID 持久化、DeviceAuthStore、pairing（code 生成/验证）、BonjourDiscovery（mDNS）、clipboard、home dir |
| `platform.py` | 15 个 | 二进制查找、package manager 检测、Git ops（root/commit/branch/dirty）、Gemini/MiniMax auth、UI assets、CliRootOptions、ChannelActivity/Summary |
| `formatting.py` | 12 个 | 时间格式化（datetime/duration/relative）、path 脱敏、API key 脱敏/redact、string 规范化、token 估算、logging setup |
| `gateway.py` | 9 个 | GatewayLock（PID+port 锁文件）、auth（bearer token）、CORS headers、health check、GatewayRouter（路由匹配）、GatewaySession、WebSocket manager |
