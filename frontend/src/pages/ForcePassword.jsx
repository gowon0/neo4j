import { useState } from 'react'
import { api, auth } from '../api.js'

/** 임시 비밀번호로 처음 로그인한 사용자가 비밀번호를 바꾸는 화면 */
export default function ForcePassword({ user, onDone, onLogout }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    if (next !== confirm) {
      setError('새 비밀번호와 확인이 일치하지 않습니다.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const res = await api.changePassword({ current_password: current, new_password: next })
      auth.set(res.token)
      onDone(res.user)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <div className="login-hero">
        <h2>기자재 AI 수요예측 시스템</h2>
        <p>
          처음 로그인하셨습니다.
          <br />
          사용하기 전에 비밀번호를 변경해 주세요.
        </p>
      </div>
      <form className="login-form" onSubmit={submit}>
        <h3>비밀번호 변경</h3>
        <p className="muted">
          {user.name}({user.username}) 님, 관리자가 발급한 임시 비밀번호는 보안을 위해 한 번만 쓸 수 있습니다.
        </p>
        <label>
          현재(임시) 비밀번호
          <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" autoFocus />
        </label>
        <label>
          새 비밀번호
          <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
        </label>
        <label>
          새 비밀번호 확인
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
        </label>
        <p className="hint">10자 이상, 영문과 숫자를 모두 포함해야 합니다.</p>
        {error && <div className="form-error">{error}</div>}
        <button className="btn btn-primary btn-block" disabled={busy || !current || !next || !confirm}>
          {busy ? '변경 중...' : '비밀번호 변경'}
        </button>
        <button type="button" className="btn btn-ghost btn-block" onClick={onLogout}>
          로그아웃
        </button>
      </form>
    </div>
  )
}
