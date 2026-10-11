import { api } from '../api.js'
import { Card, ErrorBox, Spinner, useAsync } from '../components/common.jsx'

export default function Settings() {
  const { data, error, loading, reload } = useAsync(() => api.settings(), [])

  if (loading) return <Spinner />
  if (error) return <ErrorBox message={error} onRetry={reload} />

  return (
    <div className="stack">
      <Card title="계정">
        <table className="table kv">
          <tbody>
            <tr>
              <th>로그인 사용자</th>
              <td>{data.user}</td>
            </tr>
          </tbody>
        </table>
      </Card>

      <Card title="위험도 기준 (원자재 가격 상승률)">
        <table className="table kv">
          <tbody>
            <tr>
              <th>경고</th>
              <td>기준가 대비 {data.thresholds.warning}% 이상</td>
            </tr>
            <tr>
              <th>위험</th>
              <td>기준가 대비 {data.thresholds.danger}% 이상</td>
            </tr>
            <tr>
              <th>매우위험</th>
              <td>기준가 대비 {data.thresholds.very_danger}% 이상</td>
            </tr>
          </tbody>
        </table>
        <p className="hint">
          기준값은 서버 설정(config/settings.py)에서 변경합니다. 외부 리스크와
          자연재해의 위험 등급은 지식그래프의 심각도(매우높음 → 매우위험, 높음 →
          위험)를 따릅니다.
        </p>
      </Card>

      <Card title="캐시">
        <table className="table kv">
          <tbody>
            <tr>
              <th>AI 위험 분석</th>
              <td>{data.risk_cache_minutes}분 (대시보드의 '새로 분석'으로 즉시 갱신)</td>
            </tr>
            <tr>
              <th>Supabase 데이터</th>
              <td>{data.data_cache_minutes}분 (데이터 관리에서 새로고침)</td>
            </tr>
          </tbody>
        </table>
      </Card>
    </div>
  )
}
