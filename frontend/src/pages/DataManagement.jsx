import { useState } from 'react'
import { api } from '../api.js'
import {
  Card,
  Chip,
  ErrorBox,
  Spinner,
  fmt,
  useAsync,
} from '../components/common.jsx'

const TABLE_LABEL = {
  materials: '자재 마스터',
  demand_history: '월별 수요 이력',
  raw_material_prices: '원자재 가격',
  construction_projects: '공사 프로젝트',
  project_monthly_stats: '프로젝트 월별 통계',
  electricity_usage: '전력 사용량',
  inventory: '재고 현황',
  purchase_orders: '발주 내역',
}

export default function DataManagement() {
  const { data, error, loading, reload } = useAsync(
    () => api.dataStatus(),
    [],
  )
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const refresh = async () => {
    setBusy(true)
    setMessage('')
    try {
      await api.dataRefresh()
      setMessage('Supabase 데이터를 다시 불러왔습니다.')
      reload()
    } catch (e) {
      setMessage(e.message)
    }
    setBusy(false)
  }

  return (
    <div className="stack">
      <Card
        title="데이터 소스 (Supabase)"
        extra={
          <button className="btn btn-outline" onClick={refresh} disabled={busy}>
            {busy ? '불러오는 중...' : '데이터 새로고침'}
          </button>
        }
      >
        {message && <p className="hint">{message}</p>}
        {loading && <Spinner />}
        {error && <ErrorBox message={error} onRetry={reload} />}
        {data && (
          <table className="table">
            <thead>
              <tr>
                <th>테이블</th>
                <th>설명</th>
                <th className="num">행 수</th>
                <th>기간</th>
                <th>데이터 구분</th>
              </tr>
            </thead>
            <tbody>
              {data.tables.map((t) => (
                <tr key={t.table}>
                  <td>
                    <code>{t.table}</code>
                  </td>
                  <td>{TABLE_LABEL[t.table] || ''}</td>
                  <td className="num">{t.error ? '-' : fmt(t.rows)}</td>
                  <td>
                    {t.error
                      ? t.error
                      : t.first_month
                        ? `${t.first_month.slice(0, 7)} ~ ${t.last_month.slice(0, 7)}`
                        : '-'}
                  </td>
                  <td>
                    {(t.data_status || []).map((s) => (
                      <Chip key={s} tone="gray">
                        {s.startsWith('synthetic') ? 'synthetic' : s}
                      </Chip>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title="연동 구성">
        <ul className="plain-list">
          <li>수요·가격·프로젝트 이력: Supabase (읽기 전용, 서버에서만 접근)</li>
          <li>위험 관계 그래프: Neo4j 지식그래프 (원자재 → 기자재 → 수급 → 프로젝트)</li>
          <li>발주·재고: Supabase (서버에서 읽기/쓰기, 현재 샘플 데이터)</li>
        </ul>
      </Card>
    </div>
  )
}
