import { useEffect, useState } from 'react'
import { auth } from './api.js'
import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Forecast from './pages/Forecast.jsx'
import Orders from './pages/Orders.jsx'
import Inventory from './pages/Inventory.jsx'
import Simulation from './pages/Simulation.jsx'
import DataManagement from './pages/DataManagement.jsx'
import Settings from './pages/Settings.jsx'

const MENU = [
  { key: 'dashboard', label: '대시보드', icon: '▦', view: Dashboard },
  { key: 'forecast', label: '수요예측', icon: '◔', view: Forecast },
  { key: 'orders', label: '발주관리', icon: '☰', view: Orders },
  { key: 'inventory', label: '재고관리', icon: '▤', view: Inventory },
  { key: 'simulation', label: '시뮬레이션', icon: '⚙', view: Simulation },
  { key: 'data', label: '데이터 관리', icon: '◫', view: DataManagement },
  { key: 'settings', label: '설정', icon: '✲', view: Settings },
]

export default function App() {
  const [user, setUser] = useState(() =>
    auth.get() ? sessionStorage.getItem('matai.user') || '관리자' : null,
  )
  const [page, setPage] = useState('dashboard')

  useEffect(() => {
    const onLogout = () => setUser(null)
    window.addEventListener('matai:logout', onLogout)
    return () => window.removeEventListener('matai:logout', onLogout)
  }, [])

  if (!user) {
    return (
      <Login
        onLogin={(name) => {
          sessionStorage.setItem('matai.user', name)
          setUser(name)
        }}
      />
    )
  }

  const current = MENU.find((m) => m.key === page) || MENU[0]
  const View = current.view

  const today = new Date().toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    weekday: 'short',
  })

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">기자재 AI 수요예측 시스템</div>
        <nav>
          {MENU.map((m) => (
            <button
              key={m.key}
              className={`nav-item ${m.key === page ? 'active' : ''}`}
              onClick={() => setPage(m.key)}
            >
              <span className="nav-icon">{m.icon}</span>
              {m.label}
            </button>
          ))}
        </nav>
      </aside>

      <div className="main">
        <header className="topbar">
          <h1>{current.label}</h1>
          <div className="topbar-right">
            <span className="muted">{today}</span>
            <span className="user-badge">{user}</span>
            <button
              className="btn btn-ghost"
              onClick={() => {
                auth.clear()
                setUser(null)
              }}
            >
              로그아웃
            </button>
          </div>
        </header>
        <main className="content">
          <View key={current.key} />
        </main>
      </div>
    </div>
  )
}
