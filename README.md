# 智膳 LifeOS
可运行的中文健康管理 MVP：Next.js + FastAPI + SQLAlchemy。**当前不是全部挑战赛需求的最终版本。** 无密钥使用透明规则模式，真实模型适配器已实现但本次没有真实密钥验证。

## 快速启动
需要 Docker Engine / Docker Compose：
```bash
cp .env.example .env
# 修改 POSTGRES_PASSWORD；本地默认不启用模型
# 密码避免 URL 保留字符，或自行对 DATABASE_URL 做百分号编码
docker compose up --build
```
访问 http://localhost:3000。注册独立账户，无预置共享用户。
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

## 真实接入状态与评分覆盖矩阵
|维度|已交付|限制 / 下一阶段|
|---|---|---|
|LLM 8%|服务端 OpenAI 兼容 Chat Completions、Schema 校验、2次尝试、超时降级|无真实模型调用验证；只有兼容供应商适配器|
|Agent 8%|4个具名 Agent/编排类、权限检查、实际工具事件|确定性编排；支持受白名单约束的标准 Function Calling；无 LangGraph 和长期记忆|
|RAG 6%|WHO 文本片段词项检索、引用、模型上下文注入|仅2个片段；无向量索引、入库流水线或检索基准|
|多模态 5%|图片压缩、真实视觉API请求、置信度、修正、保存|无密钥返回503手动录入；未测识别准确率|
|安全 4%|用户隔离、HttpOnly Cookie、Origin校验、授权、删除/导出、危险关键词、结构校验|安全规则不是完整医学风险检测；无OAuth/审计日志/分布式限流|
|MCP/工具 4%|官方 MCP SDK stdio 知识查询与食品目录工具|无用户健康数据工具，无部署远程MCP|
|创新 25%|预算/忌口盲盒、不喜欢过滤、透明执行步骤、隐私模式、基于最近食物重复度排序|已实现反事实营养加法模拟；未实现医学数字孪生或长期偏好学习|
|前端 10%|Next.js App Router、TS、TanStack Query、响应式、暗色、语义表单|CSS实现视觉系统，未引入Tailwind/shadcn；单页组件待进一步拆分|
|实用性/UX|饮食CRUD、7日趋势、健康手动/CSV/JSON导入、聊天历史、资料导出删除|模型模式支持同一授权版本内最近6轮上下文；当前只有6种食品及3款演示食谱|
|社会/商业|不出售敏感健康数据的产品设想、清晰非医疗边界|商业模式尚未验证|

**数据标签**：营养数值/餐食价格是演示估计，不是经过核验的 USDA 数据；链接只是参考数据库入口，不宣称具体数值来自该来源。食物克数是用户输入或模型估计。步数等指标是用户录入或文件导入，不伪称设备同步。HealthKit、Health Connect、微信运动、小米健康目前均为 import-only。

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
服务端设置 LLM_API_KEY、LLM_BASE_URL（需包含 /v1 或供应商对应前缀）、LLM_MODEL。选择支持图像输入与 json_schema 的兼容模型。密钥从不返回浏览器，不接受客户端传入模型服务器地址。
管理员配置后，用户仍须在隐私页单独授权外部AI。未经授权不会发起外部请求。模型只获得已授权的上下文；仅发送同一授权版本内最近6轮聊天，变更授权后旧聊天不再进入上下文。工具名称与参数先校验再执行；不在白名单的模型工具调用被拒绝。输出结构通过 Pydantic 验证；失败重试一次后降级。顾问事件流输出步骤和完整最终回答，**并非逐token模型流**。
协议参考：https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
知识来源：https://www.who.int/news-room/fact-sheets/detail/healthy-diet （摘要改写，非诊疗依据）。

## 数据与安全
- 账户密码采用带随机盐的 scrypt；数据库只存会话 token 的 SHA256，24小时有效，每次登录替换旧会话。
- 默认无健康上下文授权；手动存储操作不等于允许将记录发给AI。
- 所有用户数据查询限定 user_id；删除全部记录同时撤回授权。账户邮箱和密码保留用于登录；备份清理由部署者另行管理。
- 初始模型：users 和 records。records.kind 区分 food/metric/chat/feedback/consent/mystery；不是声称已建齐需求中的全部规范化实体。
- PostgreSQL 可先执行 migrations/001_initial.sql；应用首次启动也能建表。后续结构变更必须新增迁移，禁止直接删库升级。
- 单实例内存限流180次/分钟/IP。生产需代理按真实来源限流、HTTPS、COOKIE_SECURE=true、ALLOWED_ORIGINS设置准确域名、数据库备份、容量限制及合规审查。
- 图像只在内存中转换，原图不入库；导入最多1000行/1MB；未来日期、单位错误、越界值拒绝，导入先整体验证再写入。
- Redis容器仅在 future-cache profile 启用，当前没有使用Redis或pgvector功能。

## 测试
```bash
cd backend && python -m pytest -q
cd frontend && pnpm build
# 后端另行启动后
cd frontend && pnpm exec playwright install webkit && pnpm test:e2e
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
