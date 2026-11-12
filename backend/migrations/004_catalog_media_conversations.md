# 004 动态目录、图片与会话迁移

生产入口仍是 `app.db.initialize_schema(engine)`，由 FastAPI lifespan 在启动时自动执行；SQLite 和 PostgreSQL 共用 SQLAlchemy 模型，不要求手工运行 SQL。

新增表：
- `catalog_foods`：用户 ID、规范化名称（用户内唯一）、营养和来源 JSON、创建时间。
- `media_assets`：用户 ID、压缩 JPEG 字节、SHA256（用户内唯一）、创建时间。
- `conversations`：用户 ID、标题、创建时间。

`schema_migrations` 记录 `004_catalog_media_conversations`。旧 `records.kind=chat` 按用户归到“历史快捷对话”，保留原记录 ID、文本、引用和授权版本，仅新增 `conversation_id`。迁移执行一次且事务化；PostgreSQL 使用现有启动迁移事务锁。新记录仍复用 records，不删除原有饮食、健康或账户数据。

图片存入数据库并通过认证 API 读取，不挂载公开静态目录。无需新增 Docker volume，数据库备份同时包含压缩图片。已有基础六种食物为只读演示种子；自建目录可以编辑删除。新饮食记录保存名称、营养快照，删除目录项不会改写历史；旧记录使用原基础食品 ID 显示名称。

升级前备份数据库，再执行 `sudo docker compose up -d --build`。不要使用 `down -v`。回退代码不会删除新增表；不要把默认授权迁移标记删除后重跑。
