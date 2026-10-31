import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, auth } from './api.js'
import { AuthContext } from './auth.jsx'
import Login from './pages/Login.jsx'
import ForcePassword from './pages/ForcePassword.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Forecast from './pages/Forecast.jsx'
import Orders from './pages/Orders.jsx'
import Inventory from './pages/Inventory.jsx'
import Simulation from './pages/Simulation.jsx'
import DataManagement from './pages/DataManagement.jsx'
import Settings from './pages/Settings.jsx'
import Users from './pages/Users.jsx'
import Roles from './pages/Roles.jsx'
import Audit from './pages/Audit.jsx'
import Account from './pages/Account.jsx'
import { Forbidden } from './components/common.jsx'

// perm: 이 화면을 볼 수 있는 권한 (any: 여러 개 중 하나만 있어도 됨)
const MENU = [
  { key: 'dashboard', label: '대시보드', icon: '▦', view: Dashboard, perm: 'dashboard.view', group: '업무' },
  { key: 'forecast', label: '수요예측', icon: '◔', view: Forecast, perm: 'forecast.view', group: '업무' },
  { key: 'orders', label: '발주관리', icon: '☰', view: Orders, perm: 'orders.view', group: '업무' },
  { key: 'inventory', label: '재고관리', icon: '▤', view: Inventory, perm: 'inventory.view', group: '업무' },
  { key: 'simulation', label: '시뮬레이션', icon: '⚙', view: Simulation, perm: 'simulation.run', group: '업무' },
  { key: 'data', label: '데이터 관리', icon: '◫', view: DataManagement, perm: 'data.view', group: '업무' },
  { key: 'settings', label: '설정', icon: '✲', view: Settings, perm: 'settings.view', group: '업무' },
  { key: 'users', label: '사용자 관리', icon: '☺', view: Users, perm: 'users.manage', group: '관리' },
  { key: 'roles', label: '역할·권한', icon: '✔', view: Roles, perm: 'roles.manage', group: '관리' },
  { key: 'audit', label: '감사 로그', icon: '☷', view: Audit, perm: 'audit.view', group: '관리' },
]

const ACCOUNT = { key: 'account', label: '내 계정', view: Account }

export default function App() {
  const [user, setUser] = useState(null)
  const [booting, setBooting] = useState(!!auth.get())
  const [page, setPage] = useState(null)

  const can = useCallback((perm) => !!user && user.permissions.includes(perm), [user])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } catch {
      /* 서버 호출이 실패해도 이 브라우저에서는 로그아웃 */
    }
    auth.clear()
    setUser(null)
    setPage(null)
  }, [])

  // 새로고침 시 토큰으로 내 정보와 권한을 다시 불러온다
  useEffect(() => {
    if (!auth.get()) return
    api
      .me()
      .then(setUser)
      .catch(() => auth.clear())
      .finally(() => setBooting(false))
  }, [])

  useEffect(() => {
    const onLogout = () => {
      setUser(null)
      setPage(null)
    }
    window.addEventListener('matai:logout', onLogout)
    return () => window.removeEventListener('matai:logout', onLogout)
  }, [])

  const visible = useMemo(() => MENU.filter((m) => can(m.perm)), [can])
  const ctx = useMemo(() => ({ user, can, setUser }), [user, can])

  if (booting) return <div className="boot">불러오는 중...</div>

  if (!user) {
    return (
      <Login
        onLogin={(u) => {
          setUser(u)
          setPage(null)
        }}
      />
    )
  }

  if (user.must_change_password) {
    return (
      <AuthContext.Provider value={ctx}>
        <ForcePassword user={user} onDone={setUser} onLogout={logout} />
      </AuthContext.Provider>
    )
  }

  const pageKey = page || (visible[0] ? visible[0].key : 'account')
  const current = pageKey === 'account' ? ACCOUNT : MENU.find((m) => m.key === pageKey)
  const allowed = pageKey === 'account' || (current && can(current.perm))
  const View = current?.view
  const groups = ['업무', '관리'].map((g) => [g, visible.filter((m) => m.group === g)]).filter(([, items]) => items.length)

  const today = new Date().toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    weekday: 'short',
  })

  return (
    <AuthContext.Provider value={ctx}>
      <div className="shell">
        <aside className="sidebar">
          <div className="brand">기자재 AI 수요예측 시스템</div>
          <nav>
            {groups.map(([group, items]) => (
              <div key={group}>
                {groups.length > 1 && <div className="nav-group">{group}</div>}
                {items.map((m) => (
                  <button
                    key={m.key}
                    className={`nav-item ${m.key === pageKey ? 'active' : ''}`}
                    onClick={() => setPage(m.key)}
                  >
                    <span className="nav-icon">{m.icon}</span>
                    {m.label}
                  </button>
                ))}
              </div>
            ))}
          </nav>
        </aside>

        <div className="main">
          <header className="topbar">
            <h1>{current ? current.label : '접근 권한 없음'}</h1>
            <div className="topbar-right">
              <span className="muted">{today}</span>
              <button className="user-badge" onClick={() => setPage('account')} title="내 계정">
                {user.name} · {user.role}
              </button>
              <button className="btn btn-ghost" onClick={logout}>
                로그아웃
              </button>
            </div>
          </header>
          <main className="content">
            {allowed && View ? <View key={pageKey} /> : <Forbidden />}
          </main>
        </div>
      </div>
    </AuthContext.Provider>
  )
}
