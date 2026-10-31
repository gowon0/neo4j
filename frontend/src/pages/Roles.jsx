import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Card, Chip, ErrorBox, Modal, Spinner, useAsync } from '../components/common.jsx'

function NewRoleModal({ onClose, onCreated }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const res = await api.createRole({ name, description, permissions: ['dashboard.view'] })
      onCreated(res.role)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <Modal title="새 역할" onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <label>
          역할 이름
          <input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </label>
        <label>
          설명
          <input value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <p className="hint">처음에는 대시보드 조회 권한만 있습니다. 만든 뒤 권한을 체크해 주세요.</p>
        {error && <div className="form-error">{error}</div>}
        <div className="modal-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            취소
          </button>
          <button className="btn btn-primary" disabled={busy || !name}>
            만들기
          </button>
        </div>
      </form>
    </Modal>
  )
}

export default function Roles() {
  const { data, error, loading, reload } = useAsync(() => api.adminRoles(), [])
  const [selectedId, setSelectedId] = useState(null)
  const [perms, setPerms] = useState(new Set())
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [creating, setCreating] = useState(false)
  const [message, setMessage] = useState('')
  const [actionError, setActionError] = useState('')
  const [busy, setBusy] = useState(false)

  const role = data?.roles.find((r) => r.id === selectedId) || data?.roles[0]

  // 선택한 역할이 바뀌거나 서버에서 다시 불러오면 편집 상태를 맞춘다
  useEffect(() => {
    if (!role) return
    setPerms(new Set(role.permissions))
    setName(role.name)
    setDescription(role.description)
    setMessage('')
    setActionError('')
  }, [role?.id, data]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <Spinner />
  if (error) return <ErrorBox message={error} onRetry={reload} />

  const isAdminRole = role.is_system && role.name === '관리자'
  const dirty =
    name !== role.name ||
    description !== role.description ||
    [...perms].sort().join() !== [...role.permissions].sort().join()

  const groups = {}
  data.permissions.forEach((p) => {
    ;(groups[p.group] = groups[p.group] || []).push(p)
  })

  const toggle = (code) => {
    const next = new Set(perms)
    if (next.has(code)) next.delete(code)
    else next.add(code)
    setPerms(next)
  }

  const save = async () => {
    setBusy(true)
    setMessage('')
    setActionError('')
    try {
      await api.updateRole(role.id, {
        name: role.is_system ? undefined : name,
        description,
        permissions: isAdminRole ? undefined : [...perms],
      })
      setMessage('저장했습니다. 해당 역할의 사용자에게 바로 적용됩니다.')
      reload()
    } catch (err) {
      setActionError(err.message)
    }
    setBusy(false)
  }

  const remove = async () => {
    if (!window.confirm(`'${role.name}' 역할을 삭제할까요?`)) return
    setActionError('')
    try {
      await api.deleteRole(role.id)
      setSelectedId(null)
      reload()
    } catch (err) {
      setActionError(err.message)
    }
  }

  return (
    <div className="roles-layout">
      <Card
        title="역할"
        extra={
          <button className="btn btn-outline" onClick={() => setCreating(true)}>
            + 새 역할
          </button>
        }
      >
        <ul className="role-list">
          {data.roles.map((r) => (
            <li key={r.id}>
              <button className={r.id === role.id ? 'active' : ''} onClick={() => setSelectedId(r.id)}>
                <span>
                  {r.name} {r.is_system && <Chip tone="gray">기본</Chip>}
                </span>
                <span className="muted">{r.user_count}명</span>
              </button>
            </li>
          ))}
        </ul>
      </Card>

      <Card title={`'${role.name}' 권한`}>
        <div className="filters">
          <label>
            이름
            <input value={name} disabled={role.is_system} onChange={(e) => setName(e.target.value)} />
          </label>
          <label style={{ flex: 1 }}>
            설명
            <input style={{ width: '100%' }} value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
        </div>

        {isAdminRole && (
          <div className="notice notice-info">관리자 역할은 항상 모든 권한을 가지며 줄일 수 없습니다.</div>
        )}

        <div className="perm-grid editable">
          {Object.entries(groups).map(([group, items]) => (
            <div key={group} className="perm-group">
              <div className="perm-group-title">{group}</div>
              {items.map((p) => (
                <label key={p.code} className="perm-check">
                  <input
                    type="checkbox"
                    checked={isAdminRole || perms.has(p.code)}
                    disabled={isAdminRole}
                    onChange={() => toggle(p.code)}
                  />
                  {p.label}
                </label>
              ))}
            </div>
          ))}
        </div>

        {actionError && <div className="form-error">{actionError}</div>}
        {message && <div className="notice notice-info">{message}</div>}

        <div className="filters">
          <button className="btn btn-primary" onClick={save} disabled={busy || !dirty}>
            {busy ? '저장 중...' : '저장'}
          </button>
          {!role.is_system && (
            <button className="btn btn-ghost" onClick={remove}>
              역할 삭제
            </button>
          )}
          <span className="hint">
            내보내기는 해당 화면의 조회 권한과 내보내기 권한이 모두 있어야 사용할 수 있습니다.
          </span>
        </div>
      </Card>

      {creating && (
        <NewRoleModal
          onClose={() => setCreating(false)}
          onCreated={(created) => {
            setCreating(false)
            setSelectedId(created.id)
            reload()
          }}
        />
      )}
    </div>
  )
}
