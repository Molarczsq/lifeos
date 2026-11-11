export async function api(path: string, init: RequestInit = {}) {
  const response = await fetch('/api/v1' + path, {
    ...init,
    credentials: 'same-origin',
    headers: { ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...init.headers },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '服务连接失败，请稍后重试' }));
    throw new Error(typeof error.detail === 'string' ? error.detail : '输入格式不正确，请检查用户名、密码与验证码');
  }
  return response.json();
}
