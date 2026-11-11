'use client';
import { useState, FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';

export type UserProfile = { username: string; consents: { diet?: boolean; health?: boolean; external_ai?: boolean } };
type Challenge = { id: string; image: string; expires_in: number };

export function AuthPanel({ disabled, onAuthenticated }: { disabled: boolean; onAuthenticated: (profile: UserProfile) => Promise<void> }) {
  const [mode, setMode] = useState<'register' | 'login'>('register');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [answer, setAnswer] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const challenge = useQuery<Challenge>({
    queryKey: ['captcha'], queryFn: () => api('/auth/captcha'),
    enabled: !disabled && mode === 'register',
    staleTime: 0, gcTime: 0, retry: false, refetchOnWindowFocus: false,
  });
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending || disabled || (mode === 'register' && (!challenge.data || challenge.isFetching))) return;
    setPending(true); setError('');
    try {
      const body = mode === 'register'
        ? { username, password, captcha_id: challenge.data!.id, captcha_answer: answer }
        : { username, password };
      const profile = await api('/auth/' + mode, { method: 'POST', body: JSON.stringify(body) });
      setPassword(''); setAnswer('');
      await onAuthenticated(profile);
    } catch (failure) {
      setError((failure as Error).message);
      if (mode === 'register') { setAnswer(''); await challenge.refetch(); }
    } finally { setPending(false); }
  }
  return <section className="welcome card">
    <div><span className="badge">你好，欢迎来到智膳</span><h2>照顾自己，<br/>从好好吃饭开始。</h2><p>记录每一餐，发现身体的节奏。<br/>让更健康的选择，变得简单一点。</p><div className="leaf-art">🌱</div></div>
    <form onSubmit={submit} aria-label={mode === 'register' ? '账户注册' : '账户登录'}>
      <h3>{mode === 'register' ? '创建你的私人空间' : '欢迎回来'}</h3>
      <label>用户名<input name="username" autoComplete="username" required disabled={disabled || pending}
        minLength={3} maxLength={mode === 'register' ? 32 : 160}
        pattern={mode === 'register' ? '[a-zA-Z0-9_\u4e00-\u9fff]{3,32}' : undefined}
        value={username} onChange={e => setUsername(e.target.value)} aria-describedby="username-help"/></label>
      <p id="username-help" className="muted">{mode === 'register' ? '3–32位中文、英文字母、数字或下划线，英文不区分大小写。无需邮箱。' : '旧账户可继续使用原邮箱作为用户名。'}</p>
      <label>密码 · 至少10个字符<input name="password" type="password" autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
        required minLength={10} maxLength={128} disabled={disabled || pending} value={password} onChange={e => setPassword(e.target.value)}/></label>
      {mode === 'register' && <div className="captcha-block">
        <div className="captcha-image-row">
          {challenge.data && !challenge.isFetching ? <img src={challenge.data.image} alt="注册图案验证码，请输入图片中的5位字符" width="240" height="86"/> : <span role="status">{challenge.isError ? '验证码加载失败' : '正在加载图案验证码…'}</span>}
          <button type="button" className="ghost" disabled={disabled || pending || challenge.isFetching} onClick={() => { setAnswer(''); void challenge.refetch(); }}>换一张验证码</button>
        </div>
        {challenge.isError && <p role="alert">无法加载验证码，请检查连接并点击“换一张验证码”。</p>}
        <label>图案验证码<input name="captcha" required autoComplete="off" autoCapitalize="characters" spellCheck={false}
          minLength={5} maxLength={5} value={answer} disabled={disabled || pending || challenge.isFetching || !challenge.data}
          onChange={e => setAnswer(e.target.value)} aria-describedby="captcha-help"/></label>
        <small id="captcha-help">输入图中5位字母或数字，不区分大小写。5分钟内有效，每次提交后需换新图。</small>
      </div>}
      {error && <p className="auth-error" role="alert">{error}</p>}
      <p className="muted">仅使用必要的 HttpOnly 会话 Cookie 保持登录。密码加盐哈希存储；登录后自动加载该账户的数据库记录，Cookie 不保存密码或健康数据。</p>
      <button disabled={disabled || pending || (mode === 'register' && (!challenge.data || challenge.isFetching || challenge.isError))}>
        {pending ? '正在连接…' : mode === 'register' ? '创建账户，开启日常' : '登录'}
      </button>
      <button type="button" className="ghost" disabled={pending} onClick={() => { setMode(mode === 'register' ? 'login' : 'register'); setError(''); setAnswer(''); setPassword(''); }}>
        {mode === 'register' ? '已有账户？登录' : '创建新账户'}
      </button>
      {disabled && <p role="status">正在恢复会话…</p>}
    </form>
  </section>;
}
