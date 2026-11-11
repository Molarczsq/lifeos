# 智膳 LifeOS 架构与实施验收
定位：面向成年人的隐私优先饮食记录和生活方式教育工具，不提供诊疗。

Next.js App Router → 同源 /api 代理 → FastAPI → SQLAlchemy → SQLite（开发）/PostgreSQL（部署）。服务端环境变量选择规则或 OpenAI 兼容模型。数据库保存用户、授权及带类型的用户记录；可演进拆分为 food_entries、health_metrics、agent_messages 等表。

|阶段|文件|验收|
|---|---|---|
|1 架构|docs/ARCHITECTURE.md|边界、风险、覆盖矩阵明确|
|2 工程|backend/app、frontend/app、compose.yml|认证、用户隔离、启动、健康检查|
|3 饮食|agents.py、main.py、page.tsx|估计→人工修正→保存→推荐、盲盒|
|4 健康|schemas.py、main.py|验证、原子导入、去重、趋势、导出删除|
|5 顾问|llm.py、agents.py、mcp_server.py|授权检查、检索引用、SSE事件、历史|
|6 验证|backend/tests、frontend/tests|API测试、类型检查、生产构建|
|7 交付|README、docs/DEMO.md、CI|部署配置、实际结果和缺口|

核心风险：图片份量不可准确测定；营养种子仅演示估计，不作为实测数据库；模型提供商会收到用户主动授权的上下文；安全规则不是医学分诊；无密钥不能验证真实模型性能；网页不能直连 HealthKit 等原生平台。

MVP 选择：确定性状态机编排，避免重复模型请求；词项检索而非伪称向量 RAG；SQLAlchemy create_all 初始建表，后续采用迁移版本。Redis/pgvector 预留部署基础，未使用时明确标注。生产扩展需要 OAuth、分布式限流、备份恢复和密钥轮换。
