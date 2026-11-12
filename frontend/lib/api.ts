export class ApiError extends Error {
  constructor(message:string,public status:number){super(message);this.name='ApiError'}
}
export async function api(path: string, init: RequestInit = {}) {
  const response = await fetch('/api/v1' + path, {
    ...init,
    credentials: 'same-origin',
    headers: { ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...init.headers },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '服务连接失败，请稍后重试' }));
    throw new ApiError(response.status===429?'请求过于频繁，请稍后重试':typeof error.detail === 'string' ? error.detail : '输入格式不正确，请检查填写内容',response.status);
  }
  return response.json();
}
