import { useState } from 'react'
import { api, auth } from '../api.js'

export default function Login({ onLogin }) {
  const [id, setId] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const res = await api.login(id.trim(), password)
      auth.set(res.token)
      onLogin(res.name)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <div className="login-hero">
        <h2>기자재 AI 수요예측 시스템</h2>
        <p>
          더 스마트한 전력 인프라를 위한
          <br />
          AI 기반 기자재 관리 플랫폼
        </p>
        <svg viewBox="0 0 200 260" className="login-tower" aria-hidden="true">
          <g stroke="#9db4e8" strokeWidth="2" fill="none" strokeLinecap="round">
            <path d="M100 10 L70 250 M100 10 L130 250" />
            <path d="M60 70 H140 M50 110 H150 M42 150 H158 M34 190 H166" />
            <path d="M85 70 L115 110 M115 70 L85 110 M80 110 L120 150 M120 110 L80 150 M72 150 L128 190 M128 150 L72 190" />
            <path d="M20 60 H180 M10 100 H190" />
          </g>
        </svg>
      </div>

      <form className="login-form" onSubmit={submit}>
        <h3>로그인</h3>
        <label>
          아이디
          <input
            value={id}
            onChange={(e) => setId(e.target.value)}
            placeholder="아이디를 입력하세요"
            autoComplete="username"
            autoFocus
          />
        </label>
        <label>
          비밀번호
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="비밀번호를 입력하세요"
            autoComplete="current-password"
          />
        </label>
        {error && <div className="form-error">{error}</div>}
        <button
          className="btn btn-primary btn-block"
          disabled={busy || !id || !password}
        >
          {busy ? '확인 중...' : '로그인'}
        </button>
      </form>
    </div>
  )
}
