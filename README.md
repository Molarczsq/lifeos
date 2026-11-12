# 智膳 LifeOS
可运行的中文健康管理 MVP：Next.js + FastAPI + SQLAlchemy。**当前不是全部挑战赛需求的最终版本。** 无密钥使用透明规则模式，真实 DeepSeek 文本 SSE 已用不含个人数据的问题验证；视觉能力需使用支持图片的模型另行验证。

## 快速启动
需要 Docker Engine / Docker Compose：
```bash
cp .env.example .env
# 修改 POSTGRES_PASSWORD；本地默认不启用模型
# 密码避免 URL 保留字符，或自行对 DATABASE_URL 做百分号编码
docker compose up --build
```
访问 http://localhost:3000。使用用户名、密码和图案验证码注册独立账户，无需邮箱，无预置共享用户。未登录时桌面侧栏和移动导航均隐藏。
后端不对公网暴露端口；API 经 Next.js 同源代理。
OpenAPI：http://localhost:3000/api/v1/openapi.json（见下述本地文档入口）。

### 非 Docker 开发
Python 3.12+、Node.js 22+、pnpm 11.25.0：
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload --port 8000
# 另一个终端
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```
开发数据库是 backend/lifeos.db；指定 DATABASE_URL 切换 PostgreSQL。API 文档 http://localhost:8000/docs ，OpenAPI http://localhost:8000/openapi.json。
本地 Python 进程不会自动加载根 .env；先通过启动环境注入 LLM_*，勿把密钥放进前端变量。

## 本次增量功能
- 动态私人食物目录：可搜索、新增、编辑、删除；名称规范化去重；上传图片经校验和压缩后存入数据库，按内容去重。六种原基础食物继续作为只读演示种子。
- AI 食物识别：支持目录外的新名称、类别、主要食材、每100g营养估计、估计份量。Schema 验证后写入用户目录，前端立即刷新；重复图片复用识别记录。信息不足时询问补充，不编造必然识别结果。
- `/advisor` 独立对话中心：会话搜索、创建、重命名、删除、Markdown/代码块、复制消息、多轮历史、图片问答、停止生成、失败重试和重新生成；移动端历史抽屉及安全区域输入栏。
- 模型原生 SSE：向兼容模型发送 stream=true，逐步展示 JSON text 字段的草稿；草稿是待校验内容，完整 Schema 和安全检查后才保存最终回答。连接失败会清除草稿并明确降级；停止请求不保存未完成回答。快捷悬浮窗保留原事件流，并可携带会话 ID 打开完整中心。
- 问题建议根据页面、已授权的当天饮食、运动记录及会话是否有历史，通过透明规则生成，不宣称预测用户意图。
- 前端隐私页已删除数据源连接与 AI 供应商配置区块，保留三个隐私开关、导出和删除数据。

### 能力边界
AI 适配器、Function Calling、图片输入和 SSE 已实现；未将模拟测试称为真实模型成功。部署时仍须用自己的供应商和支持对应功能的模型验证。文字模型不一定支持图片。营养、份量均为估计；基础食物与三款推荐餐仍是演示种子。RAG 仍为两个 WHO 摘要的词项检索，不是向量数据库。多智能体使用确定性编排，未引入 LangGraph。设备健康连接仍只支持文件导入和手动录入。规则安全检查不是医学诊断或完备风险检测。

## 目录
```text
backend/app/         API、数据库、Schema、Agent、供应商适配、MCP
backend/tests/       单元与API集成测试、模拟供应商契约测试
backend/migrations/  PostgreSQL初始SQL
frontend/app/        中文响应式界面
frontend/tests/      Playwright移动端测试脚本
.github/workflows/   后端测试与前端生产构建
data/                合成健康导入样本与AI评测案例清单
docs/                架构、验收结果、答辩大纲与演示脚本
```

## 模型配置
服务端设置 LLM_API_KEY、LLM_BASE_URL（需包含 /v1 或供应商对应前缀）、LLM_MODEL。LLM_RESPONSE_FORMAT 默认 auto：官方 DeepSeek 地址使用 json_object，其他地址使用 json_schema；也可显式设置 json_object 或 json_schema。JSON 模式会将 Schema 写入提示词，所有输出仍经过服务端 Pydantic 校验，不合格时重试后降级。图片识别另需模型支持图像输入，文本模型接入成功不代表能识图。密钥从不返回浏览器，不接受客户端传入模型服务器地址。
三个隐私选项对新账户默认开启；本版本首次启动会将现有账户的三个选项统一开启，迁移记录在 schema_migrations 中，只执行一次。用户之后手动关闭的选择会保留，不会在登录或重启时重新开启。关闭外部AI后不会发起外部请求。模型只获得已授权的上下文；仅发送同一授权版本内最近6轮聊天，变更授权后旧聊天不再进入上下文。工具名称与参数先校验再执行；不在白名单的模型工具调用被拒绝。输出结构通过 Pydantic 验证；失败重试一次后降级。快捷顾问输出步骤和最终回答；独立对话中心支持模型原生流式草稿，最终回答校验后保存。
协议参考：https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
知识来源：https://www.who.int/news-room/fact-sheets/detail/healthy-diet （摘要改写，非诊疗依据）。

## 数据与安全
- 账户密码采用带随机盐的 scrypt；数据库只存会话 token 的 SHA256，24小时有效，每次登录替换旧会话。
- 饮食、健康上下文及外部 AI 默认开启，可在隐私页关闭；手动存储操作不等于允许将记录发给AI。
- 所有用户数据查询限定 user_id；删除全部记录同时撤回授权。账户用户名和密码哈希保留用于登录；备份清理由部署者另行管理。
- 当前模型：users、records 和 captcha_challenges。records.kind 区分 food/metric/chat/feedback/consent/mystery；不是声称已建齐需求中的全部规范化实体。
- PostgreSQL 可先执行 migrations/001_initial.sql；应用首次启动也能建表。此次升级会在启动时幂等执行邮箱列到用户名列的迁移，并新增验证码表；对应 SQL 为 migrations/002_username_captcha.sql。旧用户 ID、密码哈希及记录保留，旧用户仍用原邮箱字符串作为登录名。禁止删库升级。
- 单实例内存限流180次/分钟/IP。生产需代理按真实来源限流、HTTPS、COOKIE_SECURE=true、ALLOWED_ORIGINS设置准确域名、数据库备份、容量限制及合规审查。
- 图像只在内存中转换，原图不入库；导入最多1000行/1MB；未来日期、单位错误、越界值拒绝，导入先整体验证再写入。
- Redis容器仅在 future-cache profile 启用，当前没有使用Redis或pgvector功能。

## 测试
```bash
cd backend && python -m pytest -q
cd frontend && pnpm build
# E2E 使用独立测试数据库与测试专用验证码服务，不可用于生产
# 终端1，在仓库根目录：
cd backend && DATABASE_URL=sqlite:///./e2e.db python -m tests.e2e_server
# 终端2，在仓库根目录：
cd frontend && pnpm exec playwright install webkit && CI=1 pnpm test:e2e
```
真实结果见 docs/TEST_REPORT.md。测试中的模型响应为隔离的契约模拟，不是实际AI验证。评测案例 data/eval-cases.json；图像准确率、误差、真实延迟均待测，不提供虚构指标。

## MCP
安装后从 backend 目录运行：
```bash
python -m app.mcp_server
```
这是标准 stdio MCP 服务。客户端配置 command 为当前虚拟环境 python，args 为 ["-m","app.mcp_server"]，cwd 为 backend。提供 search_knowledge 和 food_catalog，不读取任何私人用户数据。

## GitHub与部署
本地环境没有 Docker，尚未验证容器或远程部署。工程包含 GitHub Actions 与容器配置。创建自己的私有仓库可执行：
```bash
gh auth login
gh repo create lifeos --private --source=. --remote=origin --push
```
Sites托管使用Cloudflare Workers，不直接支持本项目的FastAPI进程与PostgreSQL容器。请部署到支持Docker Compose的主机；不能仅部署前端静态文件并声称全栈上线。

## 常见问题
- AI识别503：未配置密钥、模型不支持图像/json_schema，或供应商超时；手动录入仍可使用。
- 403：检查授权开关以及ALLOWED_ORIGINS是否匹配浏览器域名。
- 推荐为空：预算不足、未知过敏原或所有候选被不喜欢排除；当前目录有限，不降低过敏原约束。
- Cookie登录失败：本地HTTP使用COOKIE_SECURE=false；生产HTTPS使用true。
- 导入失败：使用样本列名；recorded_at含时区；单位为steps/hours/bpm/minutes。

## 用户名注册与 Cookie 会话
- 新注册用户名：3–32位中文、英文字母、数字或下划线，去除首尾空白，英文统一小写；密码仍需10–128字符。
- GET /api/v1/auth/captcha 返回 PNG 数据URL、随机挑战ID和300秒有效期；答案摘要与浏览器绑定摘要保存在数据库，答案不会返回前端。
- POST /api/v1/auth/register 接收 username、password、captcha_id、captcha_answer；验证码一次性消费，过期/错误/跨浏览器使用均拒绝。刷新使同浏览器旧验证码失效。
- POST /api/v1/auth/login 只接收 username、password，并使用数据库中的加盐密码哈希比对。
- 注册成功自动登录；登录会轮换24小时有效的 HttpOnly / SameSite=Strict 会话Cookie。GET /api/v1/me 恢复用户名和授权，饮食/健康数据仍由受保护API读取。
- Cookie不保存用户名密码、健康数据或客户端可篡改的身份资料；退出使数据库中的会话立即失效，前端清除私有缓存。
- 验证码仅为基础防自动化措施，不是强抗机器人服务；当前支持换图，尚无音频验证码。
- Docker只打包 backend/app，绝不导入测试专用验证码服务。E2E服务器使用已知测试图片字符，仅用于自动化测试。

## 一键验证并推送
在系统终端、项目根目录执行 `bash scripts/verify-and-push.sh`。需要已配置Python依赖、Node/pnpm和GitHub CLI登录。脚本要求干净的main分支，通过完整后端测试和前端构建后才推送，并等待本提交的云端检查。日志保存在被Git忽略的 `.verification-logs/`，失败时显示具体阶段。不会部署容器或删除数据库。

## 页面与 API

页面：`/` 健康驾驶舱（含动态食物目录、记录、趋势和隐私），`/advisor` 独立对话中心。所有私人 API 均要求现有 HttpOnly 会话 Cookie；未登录进入中心显示注册/登录面板。

|API|用途|
|---|---|
|GET/POST `/api/v1/food/catalog`|搜索（q）、新增目录；创建返回 created，重名复用|
|PUT/DELETE `/api/v1/food/catalog/{id}`|编辑或删除用户自建条目；冲突409、无权限或不存在404|
|POST `/api/v1/food/analyze`|图片识别、验证并自动入库；需要 external_ai|
|POST `/api/v1/media`|上传 JPEG/PNG/WebP，最多5MB及2000万像素；解码、去EXIF、压缩至1200px|
|GET/DELETE `/api/v1/media/{id}`|私有图片读取/删除；删除后目录回到占位图|
|GET/POST `/api/v1/advisor/conversations`|搜索标题、新建会话|
|PATCH/DELETE `/api/v1/advisor/conversations/{id}`|重命名、删除会话及消息|
|GET `/api/v1/advisor/conversations/{id}/messages`|按会话读取历史|
|GET `/api/v1/advisor/suggestions`|传 page/conversation_id 获取上下文建议|
|POST `/api/v1/advisor/chat/stream`|message、conversation_id、image_id、stream、regenerate_id；返回 SSE|

SSE 事件：session、step、draft（临时完整文本快照）、answer（最终结果）、done。客户端终止用 AbortController；断线不盲目重发，应先读取历史再重试，避免已保存回答重复生成。重新生成原子替换所选回答；后续历史应通过新会话分支处理，目前 UI 仅允许重新生成最后一轮。

图片不接受外部 URL，不进行服务端 URL 抓取。图片权限与目录、会话相同，按用户隔离。创建食物必须填写每100g的营养数据；AI 给出的内部置信度、模型来源和验证状态留在数据库，不作为用户可见的准确率承诺。占位图为本地 emoji/CSS，明确标识，不使用未经授权网络图片。

数据库迁移见 [004说明](backend/migrations/004_catalog_media_conversations.md)。账户和历史数据保留；`/data/export` 包含目录、会话和记录，原始图片二进制可通过私有媒体API读取；`DELETE /data` 同时清除新目录、会话与压缩图片。

## 增量开发验证
```bash
cd backend
python -m pytest -q
cd ../frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
NEXT_TELEMETRY_DISABLED=1 pnpm build
pnpm exec playwright install --with-deps webkit
# 单独测试数据库与固定验证码，仅用于测试，绝不用于生产
# 另一个终端：cd backend && DATABASE_URL=sqlite:////tmp/lifeos-e2e.db python -m tests.e2e_server
CI=1 pnpm test:e2e
```
`tests/e2e_server.py` 仅固定测试验证码，不模拟供应商。后端供应商契约测试使用明确的 MockTransport / monkeypatch，无需真实密钥。E2E 不设置模型密钥，验证规则路径、UI、Cookie、目录和会话数据链路。真实供应商、视觉准确率、真实调用延迟不在这些测试结论内。

## 统一设计系统与图鉴更新

首页各模块与 `/advisor` 共用 `AppShell`、主导航、顶栏、品牌和设计Token。聊天历史改为按需打开，保留流式对话和所有会话操作。食物目录采用响应网格与详情弹窗，“添加食物”支持AI图片草稿、名称AI补充和手动录入，确认后保存。

图片优先采用用户上传的对应照片；不再将整盘照片自动绑定多项食物。没有可靠单品照片时显示带“非实拍”标识的原创分类SVG。基础6种食物已配备核验过的开放许可照片，详情展示作者和许可，见 [图片授权记录](docs/FOOD_IMAGE_CREDITS.md)。开放式在线图库搜索和生成服务尚未接入。图片修复按钮以每批20项处理历史关联，任务状态按用户持久化。

新增接口：`POST /api/v1/food/catalog/suggest`、`POST /api/v1/food/analyze?preview=true`、`POST /api/v1/food/images/repair`、`GET /api/v1/food/images/jobs`。使用既有Cookie认证。图片字段扩展已有JSON，不需要删除数据库或重建数据卷。环境变量沿用现有LLM配置。

组件结构、图片来源规则、兼容说明和测试方式见 [统一设计说明](docs/DESIGN_SYSTEM.md)。
