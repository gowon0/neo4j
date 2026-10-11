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
import RiskPanel from '../components/RiskPanel.jsx'
import {
  Card,
  Chip,
  ErrorBox,
  STOCK_TONE,
  Spinner,
  fmt,
  shortMonth,
  useAsync,
} from '../components/common.jsx'

function Kpi({ k }) {
  const up = k.delta != null && k.delta > 0
  const value =
    k.unit === '%' && k.value != null ? `${k.value.toFixed(1)}` : fmt(k.value)

  return (
    <div className="kpi">
      <div className="kpi-label">{k.label}</div>
      <div className="kpi-value">
        {value}
        <small>{k.unit}</small>
      </div>
      <div className="kpi-foot">
        {k.delta != null && (
          <span className={up ? 'delta-up' : 'delta-down'}>
            {up ? '▲' : '▼'} {Math.abs(k.delta).toFixed(1)}
            {k.unit === '%' ? '%p' : '%'}
          </span>
        )}
        <span className="muted">{k.note}</span>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { data, error, loading, reload } = useAsync(() => api.dashboard(), [])

  if (loading) return <Spinner />
  if (error) return <ErrorBox message={error} onRetry={reload} />

  return (
    <div className="stack">
      <div className="kpi-row">
        {data.kpis.map((k) => (
          <Kpi key={k.key} k={k} />
        ))}
      </div>

      <div className="grid-2">
        <Card title="수요예측 추이 (전체 자재 합계)">
          <div className="chart-box">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.trend} margin={{ left: 0, right: 12 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5eaf3" />
                <XAxis
                  dataKey="month"
                  tickFormatter={shortMonth}
                  tick={{ fontSize: 11 }}
                  interval={2}
                />
                <YAxis tick={{ fontSize: 11 }} width={48} />
                <Tooltip
                  formatter={(v) => fmt(v)}
                  labelFormatter={(l) => `${l}`}
                />
                <Legend />
                <Line
                  name="실적"
                  dataKey="actual"
                  stroke="#2f6bff"
                  strokeWidth={2}
                  dot={false}
                  connectNulls={false}
                />
                <Line
                  name="예측"
                  dataKey="forecast"
                  stroke="#f0543c"
                  strokeWidth={2}
                  strokeDasharray="5 4"
                  dot={false}
                  connectNulls={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <RiskPanel />
      </div>

      <Card title="재고 주의 자재">
        {data.shortage_items.length === 0 ? (
          <p className="muted">모든 자재의 재고가 적정 수준입니다.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>자재명</th>
                <th className="num">현재 재고</th>
                <th className="num">적정 재고</th>
                <th className="num">소진 예상(일)</th>
                <th className="num">권장 발주량</th>
                <th>상태</th>
              </tr>
            </thead>
            <tbody>
              {data.shortage_items.map((i) => (
                <tr key={i.material_id}>
                  <td>{i.name}</td>
                  <td className="num">{fmt(i.current_stock)}</td>
                  <td className="num">{fmt(i.safety_stock)}</td>
                  <td className="num">{fmt(i.days_left)}</td>
                  <td className="num">{fmt(i.recommended_order)}</td>
                  <td>
                    <Chip tone={STOCK_TONE[i.status]}>{i.status}</Chip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}
