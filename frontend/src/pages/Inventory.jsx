import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api.js'
import ExportButtons from '../components/ExportButtons.jsx'
import {
  Card,
  Chip,
  ErrorBox,
  STOCK_TONE,
  Spinner,
  fmt,
  useAsync,
} from '../components/common.jsx'

export default function Inventory() {
  const base = useAsync(() => api.materials(), [])
  const [materialId, setMaterialId] = useState('')
  const [status, setStatus] = useState('')
  const [query, setQuery] = useState({ material_id: '', status: '' })

  const list = useAsync(() => api.inventory(query), [query])

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
              <option>여유</option>
              <option>부족</option>
              <option>위험</option>
            </select>
          </label>
          <button
            className="btn btn-primary"
            onClick={() => setQuery({ material_id: materialId, status })}
          >
            조회
          </button>
          <span className="spacer" />
          <ExportButtons
            build={(format) => ({
              path: `/api/export/inventory?${new URLSearchParams({ format, ...Object.fromEntries(Object.entries(query).filter(([, v]) => v)) })}`,
            })}
          />
        </div>
      </Card>

      <Card title="재고 현황">
        {list.loading && <Spinner />}
        {list.error && <ErrorBox message={list.error} onRetry={list.reload} />}
        {list.data && (
          <table className="table">
            <thead>
              <tr>
                <th>자재명</th>
                <th className="num">현재 재고</th>
                <th className="num">적정 재고</th>
                <th className="num">부족 수량</th>
                <th className="num">입고 예정(발주 중)</th>
                <th className="num">소진 예상(일)</th>
                <th className="num">권장 발주량</th>
                <th>상태</th>
              </tr>
            </thead>
            <tbody>
              {list.data.rows.length === 0 && (
                <tr>
                  <td colSpan="8" className="muted center">
                    조건에 맞는 재고가 없습니다.
                  </td>
                </tr>
              )}
              {list.data.rows.map((r) => (
                <tr key={r.material_id}>
                  <td>
                    {r.name} <span className="muted">({r.unit})</span>
                  </td>
                  <td className="num">{fmt(r.current_stock)}</td>
                  <td className="num">{fmt(r.safety_stock)}</td>
                  <td className={`num ${r.gap > 0 ? 'delta-up' : ''}`}>
                    {fmt(r.gap)}
                  </td>
                  <td className="num">{fmt(r.pending_order)}</td>
                  <td className="num">{fmt(r.days_left)}</td>
                  <td className="num">{fmt(r.recommended_order)}</td>
                  <td>
                    <Chip tone={STOCK_TONE[r.status]}>{r.status}</Chip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="hint">
          부족 수량이 음수(-)이면 적정 재고를 초과한 상태입니다. 권장 발주량 =
          적정 재고 + 다음 달 예측 수요 − 현재 재고 − 발주 중 수량.
        </p>
      </Card>

      {list.data && list.data.rows.length > 0 && (
        <Card title="재고 현황 추이 (현재 vs 적정)">
          <div className="chart-box">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={list.data.rows} margin={{ left: 0, right: 12 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5eaf3" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} width={48} />
                <Tooltip formatter={(v) => fmt(v)} />
                <Legend />
                <Bar name="현재 재고" dataKey="current_stock" fill="#2f6bff" />
                <Bar name="적정 재고" dataKey="safety_stock" fill="#a9c1ff" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}
    </div>
  )
}
