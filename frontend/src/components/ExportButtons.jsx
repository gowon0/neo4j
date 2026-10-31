import { useState } from 'react'
import { download } from '../api.js'
import { useAuth } from '../auth.jsx'

/**
 * CSV / 엑셀 내려받기 버튼 한 쌍.
 * build(format) → { path, options? }  (options: { method, body })
 * perm: 이 권한이 없으면 버튼을 보여주지 않는다 (서버도 같은 권한을 검사한다)
 */
export default function ExportButtons({ build, label = '내보내기', perm }) {
  const { can } = useAuth()
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  if (perm && !can(perm)) return null

  const run = async (format) => {
    setBusy(format)
    setError('')
    try {
      const { path, options } = build(format)
      await download(path, options)
    } catch (e) {
      setError(e.message)
    }
    setBusy('')
  }

  return (
    <span className="export-buttons">
      {label && <span className="muted">{label}</span>}
      <button className="btn btn-ghost" onClick={() => run('csv')} disabled={!!busy}>
        {busy === 'csv' ? '받는 중...' : '⬇ CSV'}
      </button>
      <button className="btn btn-ghost" onClick={() => run('xlsx')} disabled={!!busy}>
        {busy === 'xlsx' ? '받는 중...' : '⬇ 엑셀'}
      </button>
      {error && <span className="form-error">{error}</span>}
    </span>
  )
}
