import { useState } from 'react'
import { api } from '../api.js'
import { Card, Chip, ErrorBox, LEVEL_TONE, Spinner, useAsync } from './common.jsx'

const KIND_ICON = { material: '▲', external: '◆', disaster: '●' }

function RiskItem({ item }) {
  return (
    <li className={`risk-item risk-${LEVEL_TONE[item.level]}`}>
      <div className="risk-item-head">
        <span className="risk-kind">
          {KIND_ICON[item.kind]} {item.kind_label}
        </span>
        <strong>{item.title}</strong>
        <Chip tone={LEVEL_TONE[item.level]}>{item.level}</Chip>
      </div>
      <dl className="risk-lines">
        {item.lines.map((l) => (
          <div key={l.label}>
            <dt>{l.label}</dt>
            <dd>{l.text}</dd>
          </div>
        ))}
      </dl>
    </li>
  )
}

function ProjectRisk({ project, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen)
  const [all, setAll] = useState(false)

  const LIMIT = 2
  const shown = all ? project.items : project.items.slice(0, LIMIT)
  const hidden = project.items.length - shown.length

  return (
    <div className={`risk-project risk-${LEVEL_TONE[project.level]}`}>
      <button
        className="risk-project-head"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <div className="risk-project-title">
          <Chip tone={LEVEL_TONE[project.level]}>{project.level}</Chip>
          <strong>{project.project}</strong>
          <span className="muted">{project.status}</span>
        </div>
        <div className="risk-headline">{project.headline}</div>
        <span className="risk-caret">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <>
          <ul className="risk-items">
            {shown.map((it) => (
              <RiskItem key={it.id} item={it} />
            ))}
          </ul>
          {(hidden > 0 || all) && project.items.length > LIMIT && (
            <button className="risk-more" onClick={() => setAll((a) => !a)}>
              {all ? '접기' : `나머지 ${hidden}건 더보기`}
            </button>
          )}
        </>
      )}
    </div>
  )
}

export default function RiskPanel() {
  const { data, error, loading, reload } = useAsync(() => api.risks(), [])
  const [refreshing, setRefreshing] = useState(false)

  const refresh = async () => {
    setRefreshing(true)
    try {
      await api.risks(true)
    } catch {
      /* 아래 reload에서 오류 표시 */
    }
    setRefreshing(false)
    reload()
  }

  const extra = (
    <button
      className="btn btn-ghost"
      onClick={refresh}
      disabled={refreshing || loading}
    >
      {refreshing ? '분석 중...' : '새로 분석'}
    </button>
  )

  return (
    <Card title="AI 위험 알림" extra={extra} className="risk-panel">
      {loading && <Spinner label="지식그래프 위험을 분석하는 중..." />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && (
        <>
          <div className="risk-summary">
            <span>
              {data.summary.projects}개 프로젝트 · {data.summary.total}건
            </span>
            <Chip tone="red">매우위험 {data.summary.very_danger}</Chip>
            <Chip tone="orange">위험 {data.summary.danger}</Chip>
            <Chip tone="yellow">경고 {data.summary.warning}</Chip>
            <span className="muted risk-time">{data.generated_at} 기준</span>
          </div>
          {data.projects.length === 0 ? (
            <p className="muted">현재 감지된 수급 위험이 없습니다.</p>
          ) : (
            data.projects.map((p, i) => (
              <ProjectRisk key={p.project} project={p} defaultOpen={i === 0} />
            ))
          )}
        </>
      )}
    </Card>
  )
}
