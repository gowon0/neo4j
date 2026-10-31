import { useEffect, useState } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
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

const MODEL_ORDER = ['trend_seasonal', 'holt_winters', 'seasonal_naive', 'lgbm_base', 'lgbm_exog']
const pct = (v) => (v == null ? '-' : (v * 100).toFixed(1))

function Notices({ meta }) {
  if (!meta) return null
  const [a, b] = meta.folds
  return (
    <>
      {meta.exog_linked && (
        <div className="notice notice-warn">
          외생변수(원자재 가격·프로젝트·전력 판매량)는 수요와 연관되도록 만든 <b>가상 데이터(synthetic_linked)</b>입니다.
          이 데이터로 얻은 정확도는 실데이터에서의 성능을 의미하지 않습니다.
        </div>
      )}
      {!meta.ml_available && (
        <div className="notice notice-warn">LightGBM을 사용할 수 없어 통계 모델만 비교합니다.</div>
      )}
      <div className="notice notice-info">
        검증: 학습 {meta.folds.map((f) => f.train_months).join('개월·')}개월 시점에서 각각 향후 12개월을 예측해 평균 MAPE로
        비교합니다({a?.test_from}~{a?.test_to}, {b?.test_from}~{b?.test_to}, 일부 겹침). 여러 모델 중 고르기 때문에
        선택 모델의 정확도는 다소 낙관적일 수 있습니다. 예측 범위({meta.interval})는 백테스트 오차 분포로 만든 근사이며,
        자재별 범위를 합산한 값은 실제보다 넓을 수 있습니다.
      </div>
    </>
  )
}

function ModelCompare({ selected, onSelect }) {
  const { data, error, loading, reload } = useAsync(() => api.forecastModels(), [])

  if (loading) return <Spinner />
  if (error) return <ErrorBox message={error} onRetry={reload} />

  const labels = {}
  data.materials.forEach((m) => m.candidates.forEach((c) => (labels[c.key] = c.label)))
  const keys = MODEL_ORDER.filter((k) => labels[k])
  const detail = data.materials.find((m) => String(m.material_id) === String(selected))

  return (
    <>
      <table className="table">
        <thead>
          <tr>
            <th>자재</th>
            {keys.map((k) => (
              <th key={k} className="num">{labels[k]}</th>
            ))}
            <th>선택</th>
          </tr>
        </thead>
        <tbody>
          {data.materials.map((m) => {
            const by = Object.fromEntries(m.candidates.map((c) => [c.key, c]))
            return (
              <tr
                key={m.material_id}
                className={`clickable ${String(m.material_id) === String(selected) ? 'selected' : ''}`}
                onClick={() => onSelect(String(m.material_id))}
              >
                <td>{m.name}</td>
                {keys.map((k) => (
                  <td key={k} className={`num ${by[k]?.selected ? 'best' : ''}`}>
                    {by[k] ? `${pct(by[k].mape_avg)}%${by[k].selected ? ' ✓' : ''}` : '-'}
                  </td>
                ))}
                <td><span className={`model-chip ${m.model.key.startsWith('lgbm') ? 'ml' : ''}`}>{m.model.label}</span></td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="hint">
        값은 평균 MAPE(낮을수록 좋음)입니다. ✓는 선택된 모델이며, 머신러닝(LightGBM)은 통계 모델보다 평균 MAPE가{' '}
        {data.meta.ml_min_gain_pct}% 이상 낮을 때만 채택하고, 외생변수 모델도 이력 모델보다 {data.meta.ml_min_gain_pct}% 이상
        좋을 때만 채택합니다. 행을 누르면 아래에서 시점별 오차를 볼 수 있습니다.
      </p>
      {detail && (
        <table className="table" style={{ marginTop: 10 }}>
          <thead>
            <tr>
              <th>{detail.name} — 모델</th>
              <th className="num">학습 {data.meta.folds[0]?.train_months}개월</th>
              <th className="num">학습 {data.meta.folds[1]?.train_months}개월</th>
              <th className="num">평균 MAPE</th>
            </tr>
          </thead>
          <tbody>
            {detail.candidates.map((c) => (
              <tr key={c.key}>
                <td>{c.label}{c.selected ? ' ✓' : ''}</td>
                <td className="num">{pct(c.mape_a)}%</td>
                <td className="num">{pct(c.mape_b)}%</td>
                <td className={`num ${c.selected ? 'best' : ''}`}>{pct(c.mape_avg)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}

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
          <span className="spacer" />
          <ExportButtons
            perm="forecast.export"
            build={(format) => ({
              path: `/api/export/forecast?${new URLSearchParams({
                format,
                ...(query?.material_id ? { material_id: query.material_id } : {}),
                start: query?.start || start,
                end: query?.end || end,
              })}`,
            })}
          />
        </div>
      </Card>

      <Notices meta={table.data?.meta} />

      <Card title="예측 결과">
        {table.loading && <Spinner />}
        {table.error && <ErrorBox message={table.error} onRetry={table.reload} />}
        {table.data && (
          <table className="table">
            <thead>
              <tr>
                <th>자재명</th>
                <th className="num">예측 수요량</th>
                <th className="num">예측 범위({table.data.meta.interval})</th>
                <th className="num">전년 동기 실적</th>
                <th className="num">전년 대비 증감</th>
                <th className="num">예측 정확도</th>
                <th>선택 모델</th>
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
                  <td className="num range">{fmt(r.low)} ~ {fmt(r.high)}</td>
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
                  <td>
                    <span className={`model-chip ${r.model_key.startsWith('lgbm') ? 'ml' : ''}`}>{r.model}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="hint">
          자재마다 후보 모델(추세×계절지수, 홀트-윈터스, 계절 나이브, LightGBM)을 백테스트해 가장 좋은 모델을 자동으로
          선택합니다. 정확도 = 100 − 평균 MAPE. 행을 클릭하면 아래 추이가 바뀝니다.
        </p>
      </Card>

      <Card title={`예측 추이 (${series.data?.name || '전체'})${series.data ? ` · ${series.data.model}` : ''}`}>
        {series.loading && <Spinner />}
        {series.error && <ErrorBox message={series.error} onRetry={series.reload} />}
        {series.data && (
          <div className="chart-box">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={series.data.points} margin={{ left: 0, right: 12 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5eaf3" />
                <XAxis
                  dataKey="month"
                  tickFormatter={shortMonth}
                  tick={{ fontSize: 11 }}
                  interval={1}
                />
                <YAxis tick={{ fontSize: 11 }} width={48} />
                <Tooltip
                  formatter={(v) =>
                    Array.isArray(v) ? `${fmt(v[0])} ~ ${fmt(v[1])}` : fmt(v)
                  }
                />
                <Legend />
                <Area
                  name={`예측 범위(${table.data?.meta.interval || '80%'})`}
                  dataKey="band"
                  stroke="none"
                  fill="#f5a623"
                  fillOpacity={0.2}
                  isAnimationActive={false}
                />
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
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      <Card title="모델 비교 (백테스트 평균 MAPE, %)">
        <ModelCompare selected={selected} onSelect={setSelected} />
      </Card>
    </div>
  )
}
