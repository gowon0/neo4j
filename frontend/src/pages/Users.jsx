import { useState } from 'react'
import { api } from '../api.js'
import { useAuth } from '../auth.jsx'
import { Card, Chip, ErrorBox, Modal, Spinner, fmtDateTime, useAsync } from '../components/common.jsx'

function StatusChips({ u }) {
  if (!u.is_active) return <Chip tone="red">비활성</Chip>
  return (
    <>
      {u.locked && <Chip tone="orange">잠김</Chip>}
      {u.must_change_password && <Chip tone="yellow">비밀번호 변경 대기</Chip>}
      {!u.locked && !u.must_change_password && <Chip tone="green">정상</Chip>}
    </>
  )
}

function TempPassword({ info, onClose }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(info.password)
      setCopied(true)
    } catch {
      /* 복사가 막힌 브라우저에서는 직접 선택해서 복사 */
    }
  }
  return (
    <Modal title={info.title} onClose={onClose}>
      <p className="muted">
        <b>{info.username}</b> 님의 임시 비밀번호입니다. <b>지금 한 번만</b> 표시되며, 첫 로그인에서 변경해야 합니다.
      </p>
      <div className="secret-box">{info.password}</div>
      <div className="modal-actions">
        <button className="btn btn-outline" onClick={copy}>
          {copied ? '복사됨' : '복사'}
        </button>
        <button className="btn btn-primary" onClick={onClose}>
          확인
        </button>
      </div>
    </Modal>
  )
}

function CreateModal({ roles, onClose, onCreated }) {
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [roleId, setRoleId] = useState(roles[0]?.id || '')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const res = await api.createUser({
        username,
        display_name: displayName,
        role_id: Number(roleId),
        password: password || null,
      })
      onCreated(res)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <Modal title="사용자 추가" onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <label>
          아이디 (영문 소문자·숫자·._-, 3~30자)
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        </label>
        <label>
          이름
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </label>
        <label>
          역할
          <select value={roleId} onChange={(e) => setRoleId(e.target.value)}>
            {roles.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          임시 비밀번호 (비워 두면 자동 생성)
          <input type="text" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="off" />
        </label>
        {error && <div className="form-error">{error}</div>}
        <div className="modal-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            취소
          </button>
          <button className="btn btn-primary" disabled={busy || !username || !displayName}>
            추가
          </button>
        </div>
      </form>
    </Modal>
  )
}

export default function Users() {
  const { user: me } = useAuth()
  const { data, error, loading, reload } = useAsync(() => api.adminUsers(), [])
  const [creating, setCreating] = useState(false)
  const [temp, setTemp] = useState(null)
  const [actionError, setActionError] = useState('')

  const run = async (fn, after) => {
    setActionError('')
    try {
      const res = await fn()
      if (after) after(res)
      reload()
    } catch (err) {
      setActionError(err.message)
    }
  }

  if (loading) return <Spinner />
  if (error) return <ErrorBox message={error} onRetry={reload} />

  return (
    <div className="stack">
      <Card
        title={`사용자 (${data.users.length}명)`}
        extra={
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            + 사용자 추가
          </button>
        }
      >
        {actionError && <div className="form-error">{actionError}</div>}
        <table className="table">
          <thead>
            <tr>
              <th>이름</th>
              <th>아이디</th>
              <th>역할</th>
              <th>상태</th>
              <th>최근 로그인</th>
              <th>관리</th>
            </tr>
          </thead>
          <tbody>
            {data.users.map((u) => {
              const self = String(u.id) === String(me.id)
              return (
                <tr key={u.id}>
                  <td>
                    {u.display_name} {self && <span className="muted">(나)</span>}
                  </td>
                  <td>{u.username}</td>
                  <td>
                    <select
                      className="select-sm"
                      value={u.role_id}
                      disabled={self}
                      title={self ? '본인의 역할은 바꿀 수 없습니다' : ''}
                      onChange={(e) => run(() => api.updateUser(u.id, { role_id: Number(e.target.value) }))}
                    >
                      {data.roles.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <StatusChips u={u} />
                  </td>
                  <td>{fmtDateTime(u.last_login_at)}</td>
                  <td className="row-actions">
                    {u.locked && (
                      <button className="btn btn-ghost" onClick={() => run(() => api.unlockUser(u.id))}>
                        잠금 해제
                      </button>
                    )}
                    <button
                      className="btn btn-ghost"
                      onClick={() => {
                        if (window.confirm(`${u.display_name}(${u.username})의 비밀번호를 초기화할까요?\n기존 로그인은 모두 해제됩니다.`))
                          run(
                            () => api.resetPassword(u.id),
                            (res) => setTemp({ title: '비밀번호 초기화', username: u.username, password: res.temp_password }),
                          )
                      }}
                    >
                      비밀번호 초기화
                    </button>
                    <button
                      className="btn btn-ghost"
                      disabled={self}
                      title={self ? '본인 계정은 비활성화할 수 없습니다' : ''}
                      onClick={() => {
                        const verb = u.is_active ? '비활성화' : '활성화'
                        if (window.confirm(`${u.display_name}(${u.username})을(를) ${verb}할까요?`))
                          run(() => api.updateUser(u.id, { is_active: !u.is_active }))
                      }}
                    >
                      {u.is_active ? '비활성화' : '활성화'}
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <p className="hint">
          역할을 바꾸면 해당 사용자의 권한이 바로 바뀝니다. 비활성화하면 로그인 중인 사용자도 즉시 차단됩니다.
          사용자·역할 관리 권한을 가진 활성 사용자가 한 명도 남지 않게 하는 변경은 막습니다.
        </p>
      </Card>

      {creating && (
        <CreateModal
          roles={data.roles}
          onClose={() => setCreating(false)}
          onCreated={(res) => {
            setCreating(false)
            setTemp({ title: '사용자를 추가했습니다', username: res.user.username, password: res.temp_password })
            reload()
          }}
        />
      )}
      {temp && <TempPassword info={temp} onClose={() => setTemp(null)} />}
    </div>
  )
}
