import { useState } from 'react'
import { api } from '../api.js'
import ExportButtons from '../components/ExportButtons.jsx'
import { Card, Chip, ErrorBox, Spinner, fmtDateTime, useAsync } from '../components/common.jsx'

const PAGE = 50
const TONE = {
  login_failed: 'red',
  login_locked: 'red',
  access_denied: 'orange',
  login_emergency: 'orange',
  password_reset: 'yellow',
  role_update: 'blue',
  role_create: 'blue',
  role_delete: 'blue',
}

const short = (detail) => {
  if (!detail || Object.keys(detail).length === 0) return ''
  const text = JSON.stringify(detail)
  return text.length > 80 ? text.slice(0, 80) + '…' : text
}

export default function Audit() {
  const [username, setUsername] = useState('')
  const [action, setAction] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [query, setQuery] = useState({})
  const [offset, setOffset] = useState(0)

  const { data, error, loading, reload } = useAsync(
    () => api.audit({ ...query, limit: PAGE, offset }),
    [query, offset],
  )

  const search = () => {
    setOffset(0)
    setQuery({ username, action, date_from: from, date_to: to })
  }

  const exportPath = (format) => {
    const params = new URLSearchParams({ format })
    Object.entries(query).forEach(([k, v]) => v && params.set(k, v))
    return `/api/export/audit?${params}`
  }

  return (
    <div className="stack">
      <Card>
        <div className="filters">
          <label>
            사용자
            <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="아이디" />
          </label>
          <label>
            행위
            <select value={action} onChange={(e) => setAction(e.target.value)}>
              <option value="">전체</option>
              {Object.entries(data?.actions || {}).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            기간
            <span className="range">
              <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
              ~
              <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
            </span>
          </label>
          <button className="btn btn-primary" onClick={search}>
            조회
          </button>
          <span className="spacer" />
          <ExportButtons perm="audit.view" build={(format) => ({ path: exportPath(format) })} />
        </div>
      </Card>

      <Card title="감사 로그">
        {loading && <Spinner />}
        {error && <ErrorBox message={error} onRetry={reload} />}
        {data && (
          <>
            <table className="table">
              <thead>
                <tr>
                  <th>일시</th>
                  <th>사용자</th>
                  <th>행위</th>
                  <th>대상</th>
                  <th>접속 IP</th>
                  <th>상세</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.length === 0 && (
                  <tr>
                    <td colSpan="6" className="muted center">
                      조건에 맞는 기록이 없습니다.
                    </td>
                  </tr>
                )}
                {data.rows.map((r) => (
                  <tr key={r.id}>
                    <td>{fmtDateTime(r.at)}</td>
                    <td>{r.username || '-'}</td>
                    <td>
                      <Chip tone={TONE[r.action] || 'gray'}>{data.actions[r.action] || r.action}</Chip>
                    </td>
                    <td>{r.target || '-'}</td>
                    <td>{r.ip || '-'}</td>
                    <td className="muted" title={JSON.stringify(r.detail || {})}>
                      {short(r.detail)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="pager">
              <button className="btn btn-ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                ← 이전
              </button>
              <span className="muted">
                {offset + 1} ~ {offset + data.rows.length}
              </span>
              <button className="btn btn-ghost" disabled={!data.has_more} onClick={() => setOffset(offset + PAGE)}>
                다음 →
              </button>
            </div>
          </>
        )}
        <p className="hint">최신순입니다. 내보내기는 조건에 맞는 최근 2,000건까지 포함합니다.</p>
      </Card>
    </div>
  )
}
