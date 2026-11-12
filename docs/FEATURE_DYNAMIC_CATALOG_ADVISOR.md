# 动态目录与问问智膳验收记录

分支：`feature/dynamic-food-catalog-ai-advisor`。

## 实现范围

后端增量模块：`catalog.py`（目录与识别）、`media.py`（私有压缩图片）、`advisor.py`（会话管理）；复用现有登录 Cookie、User、Record、Schema 校验、模型适配器和工具白名单。新模型和迁移入口位于 `db.py`，迁移说明见 `backend/migrations/004_catalog_media_conversations.md`。

前端：可搜索/创建的 FoodPicker、FoodCatalogPanel；首页增加食物目录导航；新增 `/advisor`，桌面历史侧栏与移动抽屉，支持多轮消息、原生模型 SSE、图片上传、停止、重试、重新生成、Markdown/代码、复制、历史搜索、改名、删除；悬浮顾问保留并新增携带会话链接。AI 供应商配置区块与置信度机械文案从前端移除。

## 核验记录（2026-11-12）

- `cd backend && python -m pytest -q`：65 passed，1 项现有 Starlette/httpx 弃用警告。
- `cd frontend && node node_modules/eslint/bin/eslint.js .`：通过（与 pnpm lint 相同入口）。
- `node node_modules/typescript/bin/tsc --noEmit`：通过。
- `NEXT_TELEMETRY_DISABLED=1 node node_modules/next/dist/bin/next build`：通过；包含 `/` 与 `/advisor`。
- `CI=1 node node_modules/@playwright/test/cli.js test`：6 项端到端测试全部通过。已用 WebKit/iPhone 13 测试注册登录、数据恢复、验证码、隐私关闭/失败恢复；新增目录创建/编辑/记录/刷新、悬浮跳转、重新生成、会话切换/刷新；桌面改名、搜索、删除与布局。
- 真实 DeepSeek 文本 SSE：使用已配置服务端密钥发送不含个人健康数据的自我介绍问题，收到32个草稿更新、1个最终Schema有效结果。未在文档保存密钥或原始模型响应。
- 视觉识别使用模拟供应商契约测试，验证新食物入库、模糊图片询问、错误Schema不写库、私有图片及用户隔离；不宣称已验证当前所配置模型的视觉能力。

## 发现并修复的问题

1. 表单编辑携带只读字段：改为明确构建请求字段，符合严格后端Schema。
2. WebKit/Next开发热更新干扰跨路由导航：CI使用构建后的standalone生产服务，与Docker运行形态一致。
3. 对话历史抽屉继承首页移动底栏高度：重设抽屉高度、导航最小宽度及滚动区域，恢复按钮点击。
4. 旧输出安全规则把“不提供诊断”误当危险请求：分离输入分流和回答审查，增加边界声明及危险建议回归测试。

本机 WebKit 缺失运行库最初导致浏览器启动失败；官方 Ubuntu 包下载到 `/tmp/lifeos-webkit-libs`，只为临时测试浏览器补齐依赖，未修改系统安装。pnpm 本地默认存储目录受沙箱限制，测试使用同一包的 Node CLI 入口；CI仍使用锁文件和pnpm。

## 未宣称实现的能力

- 六种基础种子保持只读；用户自建食物可增删改，营养数据仍为估计。
- 图片按压缩后内容SHA256去重，不是视觉语义去重。
- 问题建议由上下文规则产生，不是模型意图预测；RAG仍为词项检索。
- 内部安全审查为规则系统，不能代表医学级安全评估。
- 未在本次任务中升级生产Docker，也未合并到main。
