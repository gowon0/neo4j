import { useEffect, useState } from 'react'
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
  ErrorBox,
  Spinner,
  fmt,
  shortMonth,
  useAsync,
} from '../components/common.jsx'

function Result({ result }) {
  return (
    <>
      <div className="kpi-row">
        <div className="kpi">
          <div className="kpi-label">예상 수요</div>
          <div className="kpi-value">{fmt(result.demand)}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">예상 발주량</div>
          <div className="kpi-value">{fmt(result.order)}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">예상 재고 소진일</div>
          <div className="kpi-value">
            {fmt(result.days_left)}
            <small>일</small>
          </div>
          <div className="kpi-foot muted">
            {result.days_left_material && `${result.days_left_material} 기준`}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">예상 결품 수량</div>
          <div className={`kpi-value ${result.shortage > 0 ? 'delta-up' : ''}`}>
            {fmt(result.shortage)}
          </div>
        </div>
      </div>

      <Card title="월별 수요 / 발주량">
        <div className="chart-box">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={result.months} margin={{ left: 0, right: 12 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5eaf3" />
              <XAxis
                dataKey="month"
                tickFormatter={shortMonth}
                tick={{ fontSize: 11 }}
              />
              <YAxis tick={{ fontSize: 11 }} width={48} />
              <Tooltip formatter={(v) => fmt(v)} />
              <Legend />
              <Bar name="수요" dataKey="demand" fill="#2f6bff" />
              <Bar name="발주량" dataKey="order" fill="#8fb1ff" />
              <Bar name="결품" dataKey="shortage" fill="#f0543c" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </>
  )
}

export default function Simulation() {
  const base = useAsync(() => api.materials(), [])
  const scen = useAsync(() => api.scenarios(), [])

  const [tab, setTab] = useState('forecast')
  const [materialId, setMaterialId] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [demandChange, setDemandChange] = useState(0)
  const [delayDays, setDelayDays] = useState(0)
  const [preset, setPreset] = useState('base')

  const [result, setResult] = useState(null)
  const [compare, setCompare] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const months = base.data?.months || []

  useEffect(() => {
    if (months.length && !start) {
      setStart(months[0])
      setEnd(months[months.length - 1])
    }
  }, [months, start])

  if (base.loading || scen.loading) return <Spinner />
  if (base.error) return <ErrorBox message={base.error} onRetry={base.reload} />
  if (scen.error) return <ErrorBox message={scen.error} onRetry={scen.reload} />

  const body = (extra = {}) => ({
    material_id: materialId ? Number(materialId) : null,
    start,
    end,
    demand_change: demandChange,
    delay_days: delayDays,
    ...extra,
  })

  const applyPreset = (key) => {
    setPreset(key)
    const s = scen.data.scenarios.find((x) => x.key === key)
    if (s) {
      setDemandChange(s.demand_change)
      setDelayDays(s.delay_days)
    }
  }

  const run = async () => {
    setBusy(true)
    setError('')
    try {
      setResult(await api.simulate(body()))
    } catch (e) {
      setError(e.message)
    }
    setBusy(false)
  }

  const runCompare = async () => {
    setBusy(true)
    setError('')
    try {
      const rows = await Promise.all(
        scen.data.scenarios.map(async (s) => ({
          ...s,
          result: await api.simulate(
            body({
              demand_change: s.demand_change,
              delay_days: s.delay_days,
            }),
          ),
        })),
      )
      setCompare(rows)
    } catch (e) {
      setError(e.message)
    }
    setBusy(false)
  }

  return (
    <div className="stack">
      <div className="tabs">
        <button
          className={tab === 'forecast' ? 'active' : ''}
          onClick={() => setTab('forecast')}
        >
          수요예측 시뮬레이션
        </button>
        <button
          className={tab === 'compare' ? 'active' : ''}
          onClick={() => setTab('compare')}
        >
          시나리오 비교
        </button>
      </div>

      <Card title="조건 설정">
        <div className="filters">
          <label>
            자재
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

          {tab === 'forecast' && (
            <label>
              시나리오
              <select
                value={preset}
                onChange={(e) => applyPreset(e.target.value)}
              >
                {scen.data.scenarios.map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
          )}

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
        </div>

        {tab === 'forecast' && (
          <div className="sliders">
            <label>
              수요 변동률 <b>{demandChange > 0 ? '+' : ''}{demandChange}%</b>
              <input
                type="range"
                min="-50"
                max="100"
                step="5"
                value={demandChange}
                onChange={(e) => setDemandChange(Number(e.target.value))}
              />
            </label>
            <label>
              납기 지연 <b>{delayDays}일</b>
              <input
                type="range"
                min="0"
                max="120"
                step="10"
                value={delayDays}
                onChange={(e) => setDelayDays(Number(e.target.value))}
              />
            </label>
          </div>
        )}

        <div className="filters">
          <button
            className="btn btn-primary"
            onClick={tab === 'forecast' ? run : runCompare}
            disabled={busy || start > end}
          >
            {busy ? '계산 중...' : '시뮬레이션 실행'}
          </button>
          {start > end && (
            <span className="form-error">시작월이 종료월보다 늦습니다.</span>
          )}
          {error && <span className="form-error">{error}</span>}
          <span className="spacer" />
          <ExportButtons
            build={(format) => ({
              path: '/api/export/simulation',
              options: { method: 'POST', body: { ...body(), format, compare: tab === 'compare' } },
            })}
          />
        </div>
        <p className="hint">
          월별로 (수요 + 목표 안전재고 − 현재고·입고예정)만큼 발주하고, 납기
          지연일수만큼 입고가 늦어진다고 가정해 결품을 계산합니다. 목표
          안전재고는 납기 지연 30일당 1배씩 늘어납니다.
        </p>
      </Card>

      {tab === 'forecast' && result && <Result result={result} />}
      {tab === 'forecast' && !result && (
        <p className="muted">조건을 설정하고 시뮬레이션을 실행하세요.</p>
      )}

      {tab === 'compare' && compare && (
        <Card title="시나리오별 결과">
          <table className="table">
            <thead>
              <tr>
                <th>시나리오</th>
                <th className="num">수요 변동</th>
                <th className="num">납기 지연</th>
                <th className="num">예상 수요</th>
                <th className="num">예상 발주량</th>
                <th className="num">예상 결품</th>
                <th className="num">재고 소진일</th>
              </tr>
            </thead>
            <tbody>
              {compare.map((c) => (
                <tr key={c.key}>
                  <td>{c.label}</td>
                  <td className="num">
                    {c.demand_change > 0 ? '+' : ''}
                    {c.demand_change}%
                  </td>
                  <td className="num">{c.delay_days}일</td>
                  <td className="num">{fmt(c.result.demand)}</td>
                  <td className="num">{fmt(c.result.order)}</td>
                  <td
                    className={`num ${c.result.shortage > 0 ? 'delta-up' : ''}`}
                  >
                    {fmt(c.result.shortage)}
                  </td>
                  <td className="num">{fmt(c.result.days_left)}일</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {tab === 'compare' && !compare && (
        <p className="muted">시뮬레이션을 실행하면 4개 시나리오를 비교합니다.</p>
      )}
    </div>
  )
}
