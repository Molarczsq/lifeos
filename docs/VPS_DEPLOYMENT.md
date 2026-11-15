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

## 双域名配置与排查

版本库提供 `deploy/Caddyfile` 和 `deploy/compose.vps.yml`：保留既有规范地址 `https://yeta-lifeos.xyz`，www 在证书有效后永久重定向到根域名并保留路径和查询参数。不要在证书尚未取得时宣称 www 已可用。

DNS 当前权威服务为 DNSPod；2026-11-15 查询根域名与 www 的 A 均为实际 VPS 地址43.143.86.172，无AAAA。迁移时必须改为新环境的真实地址，勿照抄历史IP。检查所有解析线路的A/CNAME、冲突记录和停放/转发设置；没有可用IPv6时不要添加AAAA。

```bash
dig yeta-lifeos.xyz A
dig www.yeta-lifeos.xyz A
dig www.yeta-lifeos.xyz AAAA
curl -I https://yeta-lifeos.xyz
curl -I https://www.yeta-lifeos.xyz
sudo docker compose -p lifeos -f compose.yml -f deploy/compose.vps.yml up -d --build
```

VPS 的离线 wheel 构建可再叠加仅指定 `backend.build.dockerfile: Dockerfile.vps` 的本机 override。保留 `.env` 权限600以及 `lifeos_pgdata`、`lifeos_caddy_data`、`lifeos_caddy_config`；Caddy 自动管理证书和续期，不删除证书卷。若使用已有发布目录的 `compose.vps.yml`，检查其 Caddyfile 挂载路径，避免修改未被容器读取的文件。

API 使用同源 `/api/v1` 反代；浏览器不需要公开供应商密钥或跨域后端地址。Cookie 保持 Secure、HttpOnly 和原 SameSite 策略；www 先跳转到根域名，故无需放宽 Cookie Domain 或 CORS。当前没有 OAuth 回调集成。

本次 www 证书申请的真实阻塞：Caddy 已加载 www 配置，部分 ACME HTTP 验证请求到达服务器，但另一些请求报43.174.225.201（曾出现43.174.224.202）响应体错误；TLS-ALPN验证报连接重置。常规公开/权威A查询虽指向VPS，也不能证明所有验证路径正常。需要核查DNSPod线路/上游访问策略；尚不能把问题归因为应用代码或直接宣称DNS已修复。必要时使用DNS-01验证，但必须具备DNS管理权限及可续期方案，不能只手工绕过一次证书验证。
