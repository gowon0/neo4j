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

  // 권한이 없는 위젯의 데이터는 서버가 아예 내려주지 않는다
  const showChart = data.trend != null
  const showRisk = !!data.widgets?.risks
  const showShortage = data.shortage_items != null
  const empty = data.kpis.length === 0 && !showChart && !showRisk && !showShortage

  return (
    <div className="stack">
      {data.kpis.length > 0 && (
        <div
          className="kpi-row"
          style={{ gridTemplateColumns: `repeat(${Math.min(4, data.kpis.length)}, 1fr)` }}
        >
          {data.kpis.map((k) => (
            <Kpi key={k.key} k={k} />
          ))}
        </div>
      )}

      {(showChart || showRisk) && (
        <div className={showChart && showRisk ? 'grid-2' : 'stack'}>
          {showChart && (
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
          )}
          {showRisk && <RiskPanel />}
        </div>
      )}

      {showShortage && (
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
      )}

      {empty && (
        <Card>
          <p className="muted">
            이 계정에는 대시보드에 표시할 항목이 없습니다. 필요한 권한은 관리자에게 요청해 주세요.
          </p>
        </Card>
      )}
    </div>
  )
}
