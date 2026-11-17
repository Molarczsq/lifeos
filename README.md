# 智膳 LifeOS

以饮食记录、生成式餐食规划和日常生活方式问答为核心的 Web 应用。前端使用 Next.js，后端使用 FastAPI，数据保存在受保护的服务端数据库。AI 建议用于一般生活方式参考，不提供诊断、治疗或药物处方。

## 核心功能

- **记录一餐**：手动录入或多模态图片识别，核对食材、份量和营养估算后保存。用户上传图片经过类型、尺寸与内容验证，并按用户隔离。
- **私人食物目录**：搜索、新增、编辑、删除、名称和图片去重；AI 草稿经用户确认才写入数据库。基础食物是明确的示例营养估计。
- **对话式饮食建档**：回答、跳过、返回、保存；步骤与草稿存入数据库，刷新可恢复。跳过保存为 `null`（未提供），不会转换为默认答案。版本校验和请求 ID 防止重复提交；完成后可查看和修改。
- **AI 饮食规划**：结合授权范围内的记录、预算、忌口和本次需求生成方案；确认后写入饮食记录，重复确认不会重复保存。
- **怎么做菜**：自由添加中文或英文食材，Enter、按钮及批量输入均可；支持常见别名去重、编辑、删除、数量、单位、排除食材、厨具、时间和难度。返回步骤、火候、营养估计、替代食材与需要另备的食材；可继续用自然语言修改。
- **问问智膳**：独立 `/advisor` 和快捷悬浮窗，共享后端服务；支持流式回答、Markdown、图片问答、历史会话、重命名、删除、复制、停止与重新生成。
- **推荐问题**：输入为空时自动展示，点击才发送；输入时折叠，清空后恢复。优先使用真实授权上下文，模型建议经过结构化校验，通用兜底明确标注。新会话重新请求，历史消息独立加载。
- **隐私控制**：饮食、身体数据和外部 AI 分别授权，支持数据导出、删除记录、撤回授权。前端不展示供应商密钥配置或内部模型调试标签。
- **统一视觉**：全屏随机食物背景、浅深色玻璃表面、移动导航、对话历史抽屉、减少动态效果及图片失败渐变兜底。

## 技术架构

`Next.js App Router / React / TypeScript → 同源 /api 代理 → FastAPI / Pydantic → SQLAlchemy → PostgreSQL`

开发可使用 SQLite。服务端 OpenAI 兼容适配器处理结构化生成、重试和 SSE；有界工具编排调用记录查询、营养计算、规划和知识检索。知识库使用带来源的 WHO 摘要与 BM25 词项检索，未将其描述为向量 RAG。Redis 容器仅在 `future-cache` profile 下预留，当前未使用 Redis 或 pgvector 功能；没有 LangGraph 或网页直连 HealthKit 的实现。

## 快速开始

需要 Docker Engine 和支持 `!override` 的 Docker Compose：

```bash
cp .env.example .env
# 在服务端编辑 .env，至少设置 POSTGRES_PASSWORD
# 密码若含 URL 保留字符，需要对 DATABASE_URL 正确编码
docker compose up -d --build
```

访问 `http://localhost:3000`。用用户名、密码和图案验证码注册；没有预置共享账户。后端和数据库不直接发布公网端口。

### 非 Docker 开发

需要 Python 3.12+、Node.js 22+、pnpm 11.25.0。

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.lock.txt
cd backend
uvicorn app.main:app --reload --port 8000
```

另一个终端：

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

默认开发数据库为 `backend/lifeos.db`。Python 启动进程不会自动加载根 `.env`，应通过进程环境注入配置，勿将密钥复制到前端变量。

## 环境变量

以 [.env.example](.env.example) 为准，示例文件不包含真实密钥。

|变量|用途|
|---|---|
|`POSTGRES_PASSWORD`|Docker 数据库密码|
|`DATABASE_URL`|本地后端连接；Compose 内按数据库配置构造|
|`LLM_API_KEY`|仅服务端保存的模型密钥|
|`LLM_BASE_URL`|OpenAI 兼容服务地址，包含供应商要求的路径前缀|
|`LLM_MODEL`|模型名称；视觉输入须选择支持图片的模型|
|`LLM_RESPONSE_FORMAT`|`auto`、`json_object` 或 `json_schema`；auto 对官方 DeepSeek 地址使用 JSON 模式|
|`LLM_INPUT_USD_PER_MILLION` / `LLM_OUTPUT_USD_PER_MILLION`|可选服务端成本估计；未配置时不伪造成本|
|`ALLOWED_ORIGINS`|允许的浏览器来源，逗号分隔|
|`COOKIE_SECURE`|本地 HTTP 为 false，生产 HTTPS 为 true|
|`API_INTERNAL_URL`|前端构建时的内部 API 代理目标；变更后重新构建|

## AI 能力与限制

真实模型用于识餐、餐食规划、烹饪指南、问答及问题建议。无密钥时仍可手动记录、管理食物、填写/跳过建档和检索知识；做菜与规划明确报不可用，不用固定菜谱冒充生成结果。建议问题可退回明确标注的通用问题；顾问保留明确标识的规则参考与错误提示。

图片只能提供估计，不能准确测量隐藏成分和重量。结构化结果经 Pydantic 校验；供应商失败有超时和重试。用户不满意时可以修改，而不是自动采纳。营养、份量和价格均非实测值。已知食材名称及常见别名的排除检查不能保证所有调味料或交叉接触安全。

流式输出的草稿在完成结构与安全校验前不是最终回答；失败、停止或授权变化时不会把未经校验的内容作为完成结果保存。工具调用是实际执行事件，不展示虚构思考过程。

推荐问题只读取被授权的数据；历史话题限当前授权版本的本人会话。模型建议按上下文、会话、页面、时段及授权版本缓存5分钟。客户端时区偏移仅用于时段与今日推荐，不改变原饮食统计的 UTC 日界。

本项目使用 AI 辅助开发；测试替身与真实供应商调用严格区分。没有发布未经测量的识别准确率或性能指标。

## API 文档

开发时访问后端 `http://localhost:8000/docs` 和 `/openapi.json`。生产不为此开放后端公网端口。业务 API 使用 `/api/v1`，除注册、登录、验证码和健康检查外均验证会话。

|接口|用途|
|---|---|
|`GET /ai/profile`|读取本人建档进度|
|`POST /ai/profile/turn`|`event: ANSWER/SKIP/BACK/COMPLETE`，携带 `version`、`request_id`；旧文本建档请求仍兼容|
|`GET /ai/preferences`|查看已保存的偏好|
|`GET /advisor/suggestions`|`page`、可选 `conversation_id`、`offset`；返回带 id/text/reason/type 的 suggestions，保留旧 questions 字段|
|`POST /recipes/recommend`|自由 `pantry: [{name,quantity,unit}]`；兼容旧 ingredients；支持 excluded、allergens、equipment、difficulty、adjustment、previous_id|
|`POST /food/analyze`|图片识别草稿|
|`GET/POST /food/entries`|饮食记录|
|`GET/POST/PATCH/DELETE /food/catalog…`|私人食物目录管理，具体路径见 OpenAPI|
|`POST /media`|私有图片上传；GET/DELETE `/media/{id}` 验证所有权|
|`POST /ai/plans`|模型餐食规划|
|`POST /ai/actions/{id}/confirm`|确认写入，支持幂等|
|`POST /advisor/chat/stream`|SSE 对话，支持 v2 编排及原协议|
|`GET/POST /advisor/conversations`|会话列表与新建；具体会话支持消息、重命名和删除|
|`GET /knowledge/search`|带来源的知识检索|
|`GET /data/export`、`DELETE /data`|数据导出、删除记录并撤回授权|

验证失败返回422，未授权返回403，其他用户资源返回404，版本冲突返回409，AI服务不可用返回503。前端保留输入、当前步骤与可重试提示。

## 项目结构

```text
backend/app/         API、Schema、认证、记录、模型适配与工具
backend/tests/       单元、API和模拟供应商契约测试
backend/migrations/ 历史数据库迁移说明
frontend/app/        页面、AppShell入口、公共玻璃样式
frontend/components/建档、食材表单、聊天等组件
frontend/tests/      Playwright浏览器回归
frontend/public/    公共静态资源；不包含私人上传图片
.github/workflows/  后端、前端、WebKit E2E检查
deploy/             VPS反向代理与Compose配置
docs/               架构、功能、部署与使用说明
data/               明确标记的合成导入与评测样本
```

新增建档、问题建议缓存和做菜历史复用 `records` 的 `onboarding`、`suggestions`、`cooking` 类型，按用户隔离，无需重建数据库。历史迁移由启动时的版本记录管理；升级禁止删除已有卷。

## 测试

```bash
cd backend
python -m pytest -q
# 回到项目根目录后
cd frontend
pnpm lint
pnpm typecheck
pnpm build
pnpm exec playwright install --with-deps webkit
```

E2E 使用独立测试数据库与专用验证码服务，不能用于生产：

```bash
# 终端1，项目根目录
cd backend
DATABASE_URL=sqlite:///./e2e.db python -m tests.e2e_server
# 终端2，项目根目录
cd frontend
CI=1 pnpm test:e2e
```

API 测试通过模拟模型验证请求内容、Schema、权限和异常分支，不代表真实模型成功。浏览器菜谱用例中的模拟响应只用于表单契约验证。真实供应商验收需要部署者配置密钥后另行执行，不能根据 `/healthz` 中存在配置就宣称模型可用。

## 部署

当前项目使用 VPS + Docker Compose + Caddy，规范入口为 `https://yeta-lifeos.xyz`。操作方法、域名与证书诊断见 [VPS部署记录](docs/VPS_DEPLOYMENT.md)。

```bash
sudo docker compose -p lifeos -f compose.yml -f deploy/compose.vps.yml up -d --build
sudo docker compose -p lifeos -f compose.yml -f deploy/compose.vps.yml ps
```

保留 `.env`、数据库和证书卷，更新前备份；不要执行 `down -v`。VPS 的离线 Python wheel 构建使用本机 override，见部署记录。不能仅部署静态前端并认为后端、数据库和 AI 已上线。

## 隐私与安全

- 密码用带随机盐的 scrypt；服务端存会话 token 摘要，Cookie 为 HttpOnly / SameSite=Strict，生产加 Secure。每次登录轮换会话。
- 新账户三个上下文/外部AI选项默认开启，可在隐私页撤回；后续登录不会重置用户修改。需要处理本人数据时仍逐项校验授权。
- 图片重编码后作为私有资产入库，用户上传照片不会进入公共背景池。公共背景仅使用项目明确收录的资源，来源见资源池元数据；有无图片失败均不会妨碍填写。
- 私有数据只在服务端数据库中保存；Cookie 和 sessionStorage 不保存健康记录或密码。背景 sessionStorage 仅保存装饰图片ID。
- 密钥只在服务端环境中，日志不输出密钥、模型请求正文或私人图片。前端删除内部模型状态标签，但保留授权、估算、上传失败与服务不可用信息。
- 删除数据会清理记录、图片及会话并撤回授权，账户凭据仍保留用于登录；备份保留策略由部署者管理。
- 目前单实例内存限流，生产扩容需要额外代理限流和运维监控。网页没有直接读取 HealthKit、微信运动等官方平台权限。

## 设计与扩展

公共视觉由 `app/glass.css` 和 `RandomBackground` 控制：全屏等比例cover、加载失败品牌渐变、减少动态效果、深浅色及移动阅读表面。背景资源配置和版权来源见 `lib/background-pool.json`、[图片说明](docs/FOOD_IMAGE_CREDITS.md)；不从用户图库自动收集公共背景。

MCP 使用标准 stdio：在 backend 目录执行 `python -m app.mcp_server`，提供公开知识检索与基础目录工具，不读取私人健康数据。其他说明见 [架构](docs/ARCHITECTURE.md)、[动态目录与顾问](docs/FEATURE_DYNAMIC_CATALOG_ADVISOR.md)、[做菜指南](docs/RECIPES_MODEL_ONLY.md)。

## License

当前仓库没有独立的 LICENSE 文件；本次未新增或推定项目许可证。各开源依赖的许可证与声明保留在对应软件包中。
