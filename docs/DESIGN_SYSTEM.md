# LifeOS 统一界面与图片工作流

## 改造前审查

- 首页内嵌品牌侧栏、顶栏和标题，`/advisor` 使用独立 Emoji 品牌、独立导航与始终展开的历史栏。
- 目录使用统一碗 Emoji；卡片显示食材、来源、操作，底部常驻完整表单。
- 视觉识别将餐盘原图绑定每项食物，无法证明图片对应单品。
- 没有图片来源/状态元数据及历史图片修复任务。

## 设计系统与组件

`frontend/components/app-shell.tsx` 是首页所有模块和 `/advisor` 的公共布局。Sidebar 与 Header 共用品牌、Lucide 图标和登录状态；主站以 `/?tab=scan` 等链接恢复指定页面。聊天页主导航高亮，历史记录按需打开，不再存在第二套品牌导航。

全局 Token 位于 `frontend/app/globals.css`：brand/page/surface/accent/text/muted/border/radius/sidebar/shadow。深色主题覆盖 Token，主题选择保存在本地，不包含健康资料。原有 `.card`、输入、按钮作为共用样式原语。`Dialog` 基于原生 `<dialog>`，提供焦点限制、Escape 关闭和关闭后焦点恢复。

聊天内容最大宽度840px，输入区留在聊天容器底部；移动端采用100dvh、safe-area和原主站底部导航。会话CRUD、SSE、停止、重试、重新生成、复制、图片上传均复用旧API。空状态优先显示已授权上下文问题，再补通用问题，固定4张建议卡。

目录采用4/3/2列响应网格、4:3图片、懒加载、骨架屏和详情弹窗。营养、来源、食材、编辑和删除移至详情；新增通过“添加食物”弹窗选择图片识别、名称AI草稿、手动录入。

## 图片规则

每条用户食物JSON新增 `image_url/image_source/image_status/image_updated_at/image_attribution`；旧JSON可直接读取，无破坏性SQL迁移。原图字节仍在已有MediaAsset中，权限校验和上传压缩机制不变。

- 用户明确上传对应照片优先，保存为受保护 `/api/v1/media/{id}`。
- 不自动把整盘照片分配给每种食物；未实现可靠裁切，因此不伪称自动分割。
- 已核验6张Wikimedia Commons开放许可参考照片（糙米饭、西兰花、鸡胸肉、豆腐、鸡蛋、燕麦），压缩后打包在public/food-photos，仅精确名称/少量明确别名匹配。许可与署名见 [图片授权记录](FOOD_IMAGE_CREDITS.md)，详情中提供原图和许可链接。运行时不发起外部图片URL请求。尚未接入开放式图库搜索或图片生成服务。
- 无对应实拍时，按名称/类别匹配6类原创SVG（谷物、蔬菜、蛋白质、豆类、水果、餐食），卡片明确“分类插画 · 非实拍”。基础6种食物优先使用已核验参考照片；新增未知食物才使用分类插画。
- `POST /food/images/repair` 检查历史缺元数据项和重复AI照片，每批最多20项，每用户至少间隔5秒。修复关联和来源，不删除原始私有图片或历史餐食。
- 任务存入现有Record（kind=image-job），记录状态、处理数、剩余数和失败ID。`GET /food/images/jobs` 仅返回当前用户最近10次任务；失败可重新运行。同步小批次无后台队列，进程中断后可再次发起任务。
- 旧AI重复餐盘图片即使尚未运行修复，在目录读取时也不会显示为对应单品照片。删除照片会同时回退插画元数据。

图片任务实际测试只使用合成测试图片与测试账户，未修改真实用户目录。无法报告生产账户的补图数量。

## AI 草稿与API兼容

- `POST /food/catalog/suggest {name}`：外部AI授权校验、LLM Schema校验、返回草稿；不写食物目录。
- `POST /food/analyze?preview=true`：校验并保存私有上传图片，返回结构化候选，不写食物目录；无足够信息返回自然追问。
- 新版记录一餐和目录使用preview流程。用户确认后才POST现有catalog接口，同名仍去重，再确认餐食份量。
- 旧 `/food/analyze` 默认调用方式保持返回结构兼容，但新增食物不再自动绑定餐盘图。
- AI模型/密钥仍通过服务端原环境变量配置，无新增客户端密钥。

## 本地运行和测试

按README原步骤启动后端和前端，或 `sudo docker compose up -d --build --wait`。Docker增加复制public目录，保证分类SVG随镜像发布。

```
cd backend
python -m pytest -q
cd ../frontend
pnpm lint
pnpm typecheck
pnpm build
pnpm test:e2e
```

E2E使用CI-only固定验证码服务 `python -m tests.e2e_server`，生产环境不使用。CI模式用构建后的standalone。新增375/768/1024/1440宽度检查：目录图片可加载、草稿取消不入库、Dialog焦点/Escape、导航高亮、返回记录一餐、输入框位置和无横向溢出。名称AI前端测试使用明确的模拟响应，后端另有真实接口隔离测试；未宣称视觉模型识别精度或开放式在线图库接入。

## 本次实际验收记录（2026-11-12）

基线为已通过GitHub CI的 `cc28b70`。本次回归使用隔离SQLite及测试账户，不修改生产健康数据。

- `python -m pytest -q`：71项通过，1项现有Starlette/httpx弃用警告。
- `node node_modules/typescript/bin/tsc --noEmit`：通过。
- `node node_modules/eslint/bin/eslint.js .`：通过。
- `node node_modules/next/dist/bin/next build`：通过，包含 `/` 与 `/advisor`；Next ESLint插件提示仍存在，不影响构建。
- `CI=1 ... node node_modules/@playwright/test/cli.js test`：10项通过，覆盖旧注册/登录/隐私/目录/聊天流程和375/768/1024/1440宽度。实际本机使用E2E_PORT=3201、API_INTERNAL_URL=http://127.0.0.1:8201，避免占用运行服务。
- 已查看手机与平板目录、聊天截图，核验图片内容、导航高亮、间距和输入区位置；生产构建与E2E均使用standalone。
- 真实DeepSeek名称草稿调用成功，CatalogInput Schema校验通过，未写入数据库。视觉识别仍以受控契约测试验证，不宣称真实视觉能力已验证。
- 6张授权照片均验证文件内容、唯一SHA256、来源/许可和前端可加载性。照片共约356KiB（WebP），不含用户照片。

尚未接入自动食物区域分割、在线图库搜索或AI图片生成；不确定的图像保持分类插画或由用户上传对应照片。生产数据库批量修复须登录后点击“补全 / 修复图片”；本次不更改真实用户照片。Dockerfile已包含静态素材，但本次未更新正在运行的Docker服务。

## 实际修改文件清单

- `README.md`
- `backend/app/catalog.py`
- `backend/app/food_photos.json`
- `backend/app/media.py`
- `backend/app/schemas.py`
- `backend/tests/test_image_workflow.py`
- `docs/DESIGN_SYSTEM.md`
- `docs/FOOD_IMAGE_CREDITS.md`
- `frontend/Dockerfile`
- `frontend/app/advisor/advisor.css`
- `frontend/app/advisor/page.tsx`
- `frontend/app/globals.css`
- `frontend/app/page.tsx`
- `frontend/components/app-shell.tsx`
- `frontend/components/dialog.tsx`
- `frontend/components/food-catalog.tsx`
- `frontend/lib/api.ts`
- `frontend/public/food-art/fruit.svg`
- `frontend/public/food-art/grain.svg`
- `frontend/public/food-art/meal.svg`
- `frontend/public/food-art/protein.svg`
- `frontend/public/food-art/soy.svg`
- `frontend/public/food-art/vegetable.svg`
- `frontend/public/food-photos/broccoli.webp`
- `frontend/public/food-photos/chicken.webp`
- `frontend/public/food-photos/egg.webp`
- `frontend/public/food-photos/oats.webp`
- `frontend/public/food-photos/rice.webp`
- `frontend/public/food-photos/tofu.webp`
- `frontend/tests/flow.spec.ts`
