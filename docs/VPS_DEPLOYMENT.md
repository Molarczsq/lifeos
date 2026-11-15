# VPS 部署记录

正式入口：https://yeta-lifeos.xyz 。应用运行在 VPS，开发机只用于 SSH、构建资源传输和验证。

## 目录与服务

- 发布目录：`/home/ubuntu/lifeos/releases/<commit>`，`/home/ubuntu/lifeos/current` 指向当前发布。
- 在当前发布目录执行：`sudo docker compose -p lifeos -f compose.yml -f compose.vps.yml ps`。
- Caddy 负责 80/443 入口、HTTP 跳转 HTTPS 及自动证书；frontend、backend、PostgreSQL 不直接发布端口。
- VPS override 设置 `ALLOWED_ORIGINS=https://yeta-lifeos.xyz`、`COOKIE_SECURE=true`，三个应用服务及 Caddy 均设置 `restart: unless-stopped`。
- `.env` 从开发机加密复制，权限600，不进入镜像、Git或日志；域名配置放在 VPS override，不覆盖原始 `.env`。
- 数据库使用已有 `lifeos_pgdata`；升级不可使用 `down -v`。首次更新前已将停止状态的数据卷备份至 `/home/ubuntu/lifeos/backups/predeploy-20261115.tgz`，权限600。

## 构建与验证

VPS 到 PyPI 下载曾超时，使用按 `backend/requirements.lock.txt` 下载的 Linux x86_64 / CPython 3.12 官方 wheel 离线构建。仅 VPS 的 `Dockerfile.vps` 改为从本地 wheels 安装；应用源码来自 Git 发布提交。

验证应通过正式 HTTPS 域名进行：注册登录、真实模型餐食规划、确认前不写饮食、确认幂等、顾问SSE与会话持久化。测试使用合成数据，结束后清理临时账户。健康检查的 `configured-unverified` 仅表示服务端存在密钥，不能代替实际模型请求结果。

## 2026-11-15 聊天回归修复

真实模型返回“我不做疾病诊断、不开处方”时，否定表达曾被误判为医疗建议。补充了否定谓词识别，仍拦截同句后续的停药、胰岛素调整等危险建议。

流式内容校验失败时清空未验证草稿、显示真实重试步骤，再请求结构化回答；只有 Schema 和安全审查通过的结果才作为模型回答保存，失败仍明确显示不可用。
