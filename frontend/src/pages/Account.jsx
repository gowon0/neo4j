import { useState } from 'react'
import { api, auth } from '../api.js'
import { useAuth } from '../auth.jsx'
import { Card, Chip, ErrorBox, Spinner, fmtDateTime, useAsync } from '../components/common.jsx'

const ACTION_LABEL = { login: '로그인 성공', login_failed: '로그인 실패', login_emergency: '비상 관리자 로그인' }

export default function Account() {
  const { user, setUser } = useAuth()
  const catalog = useAsync(() => api.permissions(), [])
  const logins = useAsync(() => api.myLogins(), [])
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const change = async (e) => {
    e.preventDefault()
    setMessage('')
    setError('')
    if (next !== confirm) {
      setError('새 비밀번호와 확인이 일치하지 않습니다.')
      return
    }
    setBusy(true)
    try {
      const res = await api.changePassword({ current_password: current, new_password: next })
      auth.set(res.token)
      setUser(res.user)
      setCurrent('')
      setNext('')
      setConfirm('')
      setMessage('비밀번호를 변경했습니다. 다른 기기의 로그인은 모두 해제되었습니다.')
    } catch (err) {
      setError(err.message)
    }
    setBusy(false)
  }

  const groups = {}
  ;(catalog.data?.permissions || []).forEach((p) => {
    ;(groups[p.group] = groups[p.group] || []).push(p)
  })

  return (
    <div className="stack">
      <div className="grid-2">
        <Card title="내 정보">
          <table className="table kv">
            <tbody>
              <tr>
                <th>이름</th>
                <td>{user.name}</td>
              </tr>
              <tr>
                <th>아이디</th>
                <td>{user.username}</td>
              </tr>
              <tr>
                <th>역할</th>
                <td>
                  <Chip tone="blue">{user.role}</Chip>
                  {user.emergency && <span className="muted"> (.env 비상 계정)</span>}
                </td>
              </tr>
            </tbody>
          </table>
        </Card>

        <Card title="비밀번호 변경">
          {user.emergency ? (
            <p className="muted">비상 관리자 비밀번호는 서버 설정(.env)에서 바꿉니다.</p>
          ) : (
            <form className="stack" onSubmit={change}>
              <div className="filters">
                <label>
                  현재 비밀번호
                  <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" />
                </label>
                <label>
                  새 비밀번호
                  <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
                </label>
                <label>
                  새 비밀번호 확인
                  <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
                </label>
              </div>
              <p className="hint">10자 이상, 영문과 숫자를 모두 포함해야 합니다.</p>
              {error && <div className="form-error">{error}</div>}
              {message && <div className="notice notice-info">{message}</div>}
              <div>
                <button className="btn btn-primary" disabled={busy || !current || !next || !confirm}>
                  {busy ? '변경 중...' : '비밀번호 변경'}
                </button>
              </div>
            </form>
          )}
        </Card>
      </div>

      <Card title="내 권한">
        {catalog.loading && <Spinner />}
        {catalog.error && <ErrorBox message={catalog.error} onRetry={catalog.reload} />}
        {catalog.data && (
          <div className="perm-grid">
            {Object.entries(groups).map(([group, items]) => (
              <div key={group} className="perm-group">
                <div className="perm-group-title">{group}</div>
                {items.map((p) => {
                  const has = user.permissions.includes(p.code)
                  return (
                    <div key={p.code} className={`perm-item ${has ? 'on' : 'off'}`}>
                      <span>{has ? '✔' : '–'}</span> {p.label}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        )}
        <p className="hint">권한이 필요하면 관리자에게 역할 변경을 요청하세요.</p>
      </Card>

      <Card title="최근 로그인 이력">
        {logins.loading && <Spinner />}
        {logins.error && <ErrorBox message={logins.error} onRetry={logins.reload} />}
        {logins.data && (
          <table className="table">
            <thead>
              <tr>
                <th>일시</th>
                <th>결과</th>
                <th>접속 IP</th>
              </tr>
            </thead>
            <tbody>
              {logins.data.rows.length === 0 && (
                <tr>
                  <td colSpan="3" className="muted center">
                    이력이 없습니다.
                  </td>
                </tr>
              )}
              {logins.data.rows.map((r, i) => (
                <tr key={i}>
                  <td>{fmtDateTime(r.at)}</td>
                  <td>
                    <Chip tone={r.action === 'login_failed' ? 'red' : 'green'}>{ACTION_LABEL[r.action] || r.action}</Chip>
                  </td>
                  <td>{r.ip || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}
