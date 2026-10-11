import { useEffect, useState } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api.js'
import {
  Card,
  ErrorBox,
  Spinner,
  fmt,
  shortMonth,
  useAsync,
} from '../components/common.jsx'

export default function Forecast() {
  const base = useAsync(() => api.materials(), [])
  const [materialId, setMaterialId] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [query, setQuery] = useState(null)
  const [selected, setSelected] = useState('')

  const months = base.data?.months || []

  useEffect(() => {
    if (months.length && !query) {
      setStart(months[0])
      setEnd(months[months.length - 1])
      setQuery({ material_id: '', start: months[0], end: months[months.length - 1] })
    }
  }, [months, query])

  const table = useAsync(
    () => (query ? api.forecast(query) : Promise.resolve(null)),
    [query],
  )
  const series = useAsync(
    () => api.forecastSeries(selected || null),
    [selected],
  )

  if (base.loading) return <Spinner />
  if (base.error) return <ErrorBox message={base.error} onRetry={base.reload} />

  const search = () => {
    if (start > end) return
    setQuery({ material_id: materialId, start, end })
    setSelected(materialId)
  }

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
            기간
            <span className="range">
              <select value={start} onChange={(e) => setStart(e.target.value)}>
                {months.map((m) => (
                  <option key={m}>{m}</option>
                ))}
              </select>
              ~
              <select value={end} onChange={(e) => setEnd(e.target.value)}>
                {months.map((m) => (
                  <option key={m}>{m}</option>
                ))}
              </select>
            </span>
          </label>
          <button
            className="btn btn-primary"
            onClick={search}
            disabled={start > end}
          >
            조회
          </button>
          {start > end && (
            <span className="form-error">시작월이 종료월보다 늦습니다.</span>
          )}
        </div>
      </Card>

      <Card title="예측 결과">
        {table.loading && <Spinner />}
        {table.error && <ErrorBox message={table.error} onRetry={table.reload} />}
        {table.data && (
          <table className="table">
            <thead>
              <tr>
                <th>자재명</th>
                <th className="num">예측 수요량</th>
                <th className="num">전년 동기 실적</th>
                <th className="num">전년 대비 증감</th>
                <th className="num">예측 정확도</th>
              </tr>
            </thead>
            <tbody>
              {table.data.rows.map((r) => (
                <tr
                  key={r.material_id}
                  className={`clickable ${
                    String(r.material_id) === String(selected) ? 'selected' : ''
                  }`}
                  onClick={() => setSelected(String(r.material_id))}
                >
                  <td>
                    {r.name} <span className="muted">({r.unit})</span>
                  </td>
                  <td className="num">{fmt(r.demand)}</td>
                  <td className="num">{fmt(r.previous)}</td>
                  <td
                    className={`num ${
                      r.change > 0 ? 'delta-up' : r.change < 0 ? 'delta-down' : ''
                    }`}
                  >
                    {r.change == null
                      ? '-'
                      : `${r.change > 0 ? '▲' : r.change < 0 ? '▼' : ''} ${Math.abs(
                          r.change,
                        ).toFixed(1)}%`}
                  </td>
                  <td className="num">
                    {r.accuracy == null ? '-' : `${r.accuracy.toFixed(1)}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="hint">
          예측 모델: 선형 추세 + 월별 계절지수 (Supabase 수요이력 2022~2025).
          예측 정확도는 최근 12개월을 숨기고 예측한 백테스트 결과입니다.
          행을 클릭하면 아래 추이가 바뀝니다.
        </p>
      </Card>

      <Card title={`예측 추이 (${series.data?.name || '전체'})`}>
        {series.loading && <Spinner />}
        {series.error && <ErrorBox message={series.error} onRetry={series.reload} />}
        {series.data && (
          <div className="chart-box">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series.data.points} margin={{ left: 0, right: 12 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5eaf3" />
                <XAxis
                  dataKey="month"
                  tickFormatter={shortMonth}
                  tick={{ fontSize: 11 }}
                  interval={1}
                />
                <YAxis tick={{ fontSize: 11 }} width={48} />
                <Tooltip formatter={(v) => fmt(v)} />
                <Legend />
                <Line
                  name="실적"
                  dataKey="actual"
                  stroke="#2f6bff"
                  strokeWidth={2}
                  dot={{ r: 2 }}
                  connectNulls={false}
                />
                <Line
                  name="예측"
                  dataKey="forecast"
                  stroke="#f0543c"
                  strokeWidth={2}
                  strokeDasharray="5 4"
                  dot={{ r: 2 }}
                  connectNulls={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
    </div>
  )
}
