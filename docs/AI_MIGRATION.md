# 生成式饮食智能体审计与移植

分支：feature/generative-diet-agent；基线98814f6（72项后端、11项E2E已通过）。

## 真实审计与依赖决策

|原功能|当前方式|分类|决策|涉及文件/风险|
|---|---|---|---|---|
|拍照识餐、名称营养草稿|服务端多模态/文本LLM，Schema校验|A|保留并接入聊天与事件建议|catalog/llm；不破坏图片权限|
|问问智膳|SSE、多轮、无参工具规划|A|保留，增加有参数的工具注册表、确认动作|main/advisor；旧会话兼容|
|食物目录/营养计算/饮食历史|数据库与确定性计算|B|保留|旧记录快照不改|
|注册登录/授权/数据导出删除|服务端Cookie与数据库|B|保留|不迁移到localStorage|
|静态三食谱推荐/盲盒|固定规则|C（界面）/兼容层|移除旧界面，改用真实生成接口；旧API标记兼容|新接口明确模型不可用|
|身体运动独立仪表盘|手动指标/规则趋势|C（界面）/B（已授权上下文）|删除独立UI；保留历史指标读写与AI工具依赖|不删除历史数据|
|平台连接目录|仅说明import-only，无真实连接|C|删除无调用连接API|不影响历史指标|
|七日图表/静态健康驾驶舱|确定性统计|C（独立页面）|替换为AI摘要及引导；必要统计作为工具|无健康评分伪装AI|
|历史/隐私入口|必要账户管理|B|收拢到账户入口|保持可访问|
|MCP知识工具|只读stdio|B|保留并复用BM25检索|不泄漏用户数据|

## 食憩附件审计

已直接读取用户提供ZIP中的README、index.html、js/app.js、js/data.js、css/style.css，未执行附件脚本。附件是前端localStorage应用；README明确BM25+模板、意图分派，不是完整向量RAG或自主Function Calling。

- Guide（app.js1254起）：参考“一轮一问”，不移植强制年龄/性别/身高/体重及疾病目标估算。改为可跳过、逐项确认的饮食偏好。
- SYSTEM_PROMPT（data.js1095起）：移植结论优先、已有数据优先、一次必要追问；剔除“食品疗愈”角色及固定数值疗效暗示。
- tok/retrieve（data.js1050起）：重写中文双字词BM25服务；无向量模型时明确BM25，不称混合向量RAG。
- TOOLS/runTool：重写为服务端真实LLM Function Calling；add_meal只提议，确认接口才写入。
- Brain.proactive：只移植事件触发模式，重写为有授权、冷却和缓存的LLM建议，不移植固定营养缺口评分。
- SpeechRecognition：重写React控件，主动授权、开始/停止、可编辑文本，不自动发送。
- Safety：保留输入分流/输出审查思想，不复制把危险词换成“有助于改善”的scrub，也不复制未经地域核验的热线号码。
- 附件食物表缺少逐项可追溯版本及URL，暂不批量搬入营养数据库；生活方式知识按WHO公开原文重新核验摘要并记录来源、版本、适用范围。
- 不移植情绪打卡、声景、音乐处方、社交功能、浏览器API Key存储和旧UI。

## 交付架构与文件

新增后端：`ai_schemas.py`（请求/生成Schema）、`ai_services.py`（建档、餐食、确认事务、主动建议与用量）、`agent_tools.py`（七个Function Calling工具）、`ai_advisor.py`（有界工作流）、`knowledge.py`（BM25）。

调整后端：`main.py` 注册新服务及权限检查，`advisor.py` 共享快捷会话与动态建议，`catalog.py` 支持同一确认事务内创建食物，`llm.py` 统一Prompt和用量统计，`agents.py` 复用知识服务，`schemas.py` 保持旧聊天契约并扩展v2。

新增前端：`components/ai-workspace.tsx`（摘要/建档/规划/确认/知识查询/上下文卡片）、`voice-input.tsx`（语音）。调整 `app/page.tsx`、`app/advisor/page.tsx`、`components/app-shell.tsx`、`app/globals.css`，保留原Token与Dialog。

配置与验证：`.env.example`、`compose.yml`、`README.md`、本文件；新增 `test_generative.py`、`test_tool_registry.py`，更新 `frontend/tests/flow.spec.ts`。没有复制附件前端，也没有添加新的运行时依赖。

## 兼容与行为边界

新增数据复用 `records`，无需DDL或删库。确认动作有1小时有效期、用户归属、授权版本和幂等状态；PostgreSQL下用用户/动作行锁，创建目录和保存一餐同事务提交。授权变化后旧方案不继续传入模型。用户点击确认之前，仅保存方案/动作草稿，不增加饮食记录。

识图预览→用户确认目录→核对克数→保存餐食→生成摘要→生成下一餐→携带meal_id/plan_id进入聊天。`plan_recipe` 也可以在聊天中生成待确认菜谱；“聊菜谱”弹窗支持previous_id自然语言调整。营养总量由代码计算，不让模型自行累加。

删除的是传统独立UI和无调用的平台连接API；保留的身体指标API用于授权上下文、历史兼容。旧规则食谱API标记deprecated，旧聊天v1仍兼容；前端所有新聊天都使用v2，不把旧规则回复标为模型生成。

不迁移附件中缺少来源的营养数值。原六种食物照片与许可记录保持不变，本次没有新增远程图片服务。没有实拍或可验证单项裁切时使用明确标注的分类插画。

## 实际验证（2026-11-14）

- `python -m pytest -q`：84项通过，包含图片输入/权限/异常模型输出、两轮工具查询到待确认记餐、v2 SSE、餐食生成与追问、预算/忌口、用户隔离和授权变化。供应商单元/集成测试使用明确测试替身；不是在线视觉准确率评测。
- `node node_modules/typescript/bin/tsc --noEmit`、`node node_modules/eslint/bin/eslint.js .`：通过。
- `NEXT_TELEMETRY_DISABLED=1 node node_modules/next/dist/bin/next build`：通过。Next.js提示尚未接入其专用ESLint插件，现有ESLint和编译类型检查仍执行。
- 生产构建 + WebKit E2E：12项主流程加1项语音接口模拟测试已通过，375/768/1024/1440px图鉴与顾问均检查无页面横向溢出、输入栏在底部导航之上；包含注册/登录/恢复Cookie/跨账户记录/目录/会话/隐私/知识查询。
- 真实DeepSeek通用请求：1份菜谱通过Recipe Schema；1次Function Calling选择retrieve_knowledge；两次请求均有供应商Token用量。请求不含私人健康记录。未测在线多模态识别精度、真实硬件语音或负载性能，不虚构这些指标。
- 本地首次E2E因未等待构建完成、缺少浏览器及运行库未启动；等待构建并补齐临时测试依赖后重跑通过。构建曾因遥测配置目录只读退出，禁用遥测后通过。这些是环境问题，没有跳过失败断言。

语音模拟验证识别文字可编辑且不会自动发送，未验证实机麦克风。最终GitHub CI结果以本次提交的检查结果为准；生产部署需配置支持所用能力的模型。BM25只有六条WHO摘要，不宣称医学级知识库或向量RAG；过敏检查是有限别名与模型约束，不能保证隐藏成分和交叉接触安全。
