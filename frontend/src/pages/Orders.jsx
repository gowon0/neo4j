import { useState } from 'react'
import { api } from '../api.js'
import {
  Card,
  Chip,
  ErrorBox,
  ORDER_TONE,
  Spinner,
  fmt,
  useAsync,
} from '../components/common.jsx'

function NewOrderModal({ materials, onClose, onCreated }) {
  const tomorrow = new Date(Date.now() + 14 * 86400000)
    .toISOString()
    .slice(0, 10)
  const [materialId, setMaterialId] = useState(materials[0]?.material_id || '')
  const [quantity, setQuantity] = useState('')
  const [dueDate, setDueDate] = useState(tomorrow)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.createOrder({
        material_id: Number(materialId),
        quantity: Number(quantity),
        due_date: dueDate,
      })
      onCreated()
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form
        className="modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h3>발주 등록</h3>
        <label>
          자재
          <select
            value={materialId}
            onChange={(e) => setMaterialId(e.target.value)}
          >
            {materials.map((m) => (
              <option key={m.material_id} value={m.material_id}>
                {m.name} ({m.unit})
              </option>
            ))}
          </select>
        </label>
        <label>
          수량
          <input
            type="number"
            min="1"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            autoFocus
          />
        </label>
        <label>
          납기일
          <input
            type="date"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
          />
        </label>
        {error && <div className="form-error">{error}</div>}
        <div className="modal-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            취소
          </button>
          <button
            className="btn btn-primary"
            disabled={busy || !quantity || Number(quantity) < 1}
          >
            등록
          </button>
        </div>
      </form>
    </div>
  )
}

export default function Orders() {
  const base = useAsync(() => api.materials(), [])
  const [materialId, setMaterialId] = useState('')
  const [status, setStatus] = useState('')
  const [query, setQuery] = useState({ material_id: '', status: '' })
  const [open, setOpen] = useState(false)
  const [actionError, setActionError] = useState('')

  const list = useAsync(() => api.orders(query), [query])

  const changeStatus = async (po, next) => {
    setActionError('')
    try {
      await api.updateOrder(po, next)
      list.reload()
    } catch (err) {
      setActionError(err.message)
    }
  }

  if (base.loading) return <Spinner />
  if (base.error) return <ErrorBox message={base.error} onRetry={base.reload} />

  return (
    <div className="stack">
      <Card>
        <div className="filters">
          <label>
            자재 구분
            <select
              value={materialId}
              onChange={(e) => setMaterialId(e.target.value)}
            >
              <option value="">전체</option>
              {base.data.materials.map((m) => (
                <option key={m.material_id} value={m.material_id}>
                  {m.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            상태
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">전체</option>
              {(list.data?.statuses || []).map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <button
            className="btn btn-primary"
            onClick={() => setQuery({ material_id: materialId, status })}
          >
            조회
          </button>
          <span className="spacer" />
          <button className="btn btn-outline" onClick={() => setOpen(true)}>
            + 발주 등록
          </button>
        </div>
      </Card>

      <Card title="발주 관리">
        {actionError && <div className="form-error">{actionError}</div>}
        {list.loading && <Spinner />}
        {list.error && <ErrorBox message={list.error} onRetry={list.reload} />}
        {list.data && (
          <table className="table">
            <thead>
              <tr>
                <th>발주번호</th>
                <th>자재명</th>
                <th className="num">수량</th>
                <th>발주일</th>
                <th>납기일</th>
                <th>상태</th>
                <th>상태 변경</th>
              </tr>
            </thead>
            <tbody>
              {list.data.rows.length === 0 && (
                <tr>
                  <td colSpan="7" className="muted center">
                    조건에 맞는 발주가 없습니다.
                  </td>
                </tr>
              )}
              {list.data.rows.map((r) => (
                <tr key={r.po_no}>
                  <td>{r.po_no}</td>
                  <td>{r.name}</td>
                  <td className="num">
                    {fmt(r.quantity)} <span className="muted">{r.unit}</span>
                  </td>
                  <td>{r.order_date}</td>
                  <td>{r.due_date}</td>
                  <td>
                    <Chip tone={ORDER_TONE[r.status]}>{r.status}</Chip>
                  </td>
                  <td>
                    <select
                      className="select-sm"
                      value={r.status}
                      onChange={(e) => changeStatus(r.po_no, e.target.value)}
                    >
                      {list.data.statuses.map((s) => (
                        <option key={s}>{s}</option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {open && (
        <NewOrderModal
          materials={base.data.materials}
          onClose={() => setOpen(false)}
          onCreated={() => {
            setOpen(false)
            list.reload()
          }}
        />
      )}
    </div>
  )
}
