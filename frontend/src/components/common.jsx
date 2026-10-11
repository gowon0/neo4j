import { useEffect, useState } from 'react'

export const fmt = (n) =>
  n == null ? '-' : Number(n).toLocaleString('ko-KR')

export const shortMonth = (m) => m.slice(2).replace('-', '.')

export function Chip({ tone = 'gray', children }) {
  return <span className={`chip chip-${tone}`}>{children}</span>
}

export const LEVEL_TONE = {
  매우위험: 'red',
  위험: 'orange',
  경고: 'yellow',
}

export const STOCK_TONE = { 여유: 'green', 부족: 'red', 위험: 'red' }

export const ORDER_TONE = {
  발주완료: 'green',
  진행중: 'blue',
  발주대기: 'orange',
  지연: 'red',
}

export function Spinner({ label = '불러오는 중...' }) {
  return (
    <div className="spinner">
      <span className="spinner-dot" />
      {label}
    </div>
  )
}

export function ErrorBox({ message, onRetry }) {
  return (
    <div className="error-box">
      <span>{message}</span>
      {onRetry && (
        <button className="btn btn-ghost" onClick={onRetry}>
          다시 시도
        </button>
      )}
    </div>
  )
}

/** 비동기 데이터 로딩 훅: { data, error, loading, reload } */
export function useAsync(fn, deps = []) {
  const [state, setState] = useState({
    data: null,
    error: null,
    loading: true,
  })
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    fn()
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch(
        (e) =>
          alive && setState({ data: null, error: e.message, loading: false }),
      )
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  return { ...state, reload: () => setTick((t) => t + 1) }
}

export function Card({ title, extra, children, className = '' }) {
  return (
    <section className={`card ${className}`}>
      {(title || extra) && (
        <header className="card-head">
          <h3>{title}</h3>
          {extra}
        </header>
      )}
      {children}
    </section>
  )
}
