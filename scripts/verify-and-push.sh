#!/usr/bin/env bash
# Run from a normal terminal. Never deploys containers or changes application data.
set -Eeuo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
repo='Molarczsq/lifeos'
stage='初始化'
log_dir="$project_dir/.verification-logs"
mkdir -p "$log_dir"
log_file="$log_dir/verify-$(date +%Y%m%d-%H%M%S)-$$.log"
exec > >(tee -a "$log_file") 2>&1
trap 'code=$?; printf "\n失败阶段：%s（退出码 %s）。未完成的步骤不会继续。\n日志：%s\n" "$stage" "$code" "$log_file" >&2; exit "$code"' ERR
printf '验证日志：%s\n' "$log_file"
cd "$project_dir"

stage='查找运行环境'
runtime_dir="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies"
if ! command -v node >/dev/null; then export PATH="$runtime_dir/node/bin:$PATH"; fi
if ! command -v pnpm >/dev/null; then export PATH="$runtime_dir/bin/fallback:$PATH"; fi
export NEXT_TELEMETRY_DISABLED=1
python_bin="${LIFEOS_PYTHON:-}"
if [[ -z "$python_bin" ]]; then
  for candidate in "$project_dir/.venv/bin/python" "$project_dir/../../work/runtime/bin/python"; do
    if [[ -x "$candidate" ]]; then python_bin="$candidate"; break; fi
  done
fi
if [[ -z "$python_bin" ]]; then python_bin="$(command -v python3)"; fi
command -v gh
command -v pnpm
"$python_bin" --version
node --version

stage='检查本地提交'
if [[ -n "$(git status --porcelain)" ]]; then
  echo '工作区有未提交改动，请先确认并提交；没有执行推送。' >&2
  exit 1
fi
if [[ "$(git branch --show-current)" != 'main' ]]; then
  echo '此脚本仅推送 main 分支，当前分支不同；没有执行推送。' >&2
  exit 1
fi
commit_sha="$(git rev-parse HEAD)"
printf '待验证提交：%s\n' "$commit_sha"

stage='GitHub 网络与认证检查'
# A failed connection is not proof that a stored token is invalid.
gh api user --jq '.login'
git ls-remote origin refs/heads/main

stage='完整后端测试'
(cd backend && timeout "${LIFEOS_TEST_TIMEOUT:-180}" "$python_bin" -m pytest -q)
stage='前端生产构建'
(cd frontend && pnpm build)

stage='推送源码'
git push origin main
remote_sha="$(git ls-remote origin refs/heads/main | cut -f1)"
if [[ "$remote_sha" != "$commit_sha" ]]; then
  echo '远程主分支与待验证提交不同，停止等待检查。' >&2
  exit 1
fi
printf '已确认远程提交与本地一致：%s\n' "$remote_sha"

stage='等待对应 GitHub Actions'
run_id=''
for attempt in {1..24}; do
  run_id="$(gh run list --repo "$repo" --workflow ci.yml --branch main --commit "$commit_sha" --limit 1 --json databaseId --jq '.[0].databaseId // empty')"
  [[ -n "$run_id" ]] && break
  sleep 5
done
if [[ -z "$run_id" ]]; then
  echo '源码已推送，但尚未发现对应 Actions；请检查仓库 Actions 页面。' >&2
  exit 1
fi
stage='云端测试（后端、前端、移动端E2E）'
gh run watch "$run_id" --repo "$repo" --interval 10 --exit-status
gh run view "$run_id" --repo "$repo" --json conclusion,url,jobs --jq '{conclusion,url,jobs:[.jobs[]|{name,conclusion}]}'
printf '\n全部检查通过。源码已推送，未执行部署。\n日志：%s\n' "$log_file"
