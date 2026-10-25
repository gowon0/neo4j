const TOKEN_KEY = 'matai.token'

export const auth = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (t) => sessionStorage.setItem(TOKEN_KEY, t),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
}

async function request(method, path, body) {
  const headers = { 'Content-Type': 'application/json' }
  const token = auth.get()
  if (token) headers.Authorization = `Bearer ${token}`

  let res
  try {
    res = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new Error('서버에 연결할 수 없습니다.')
  }

  if (res.status === 401 && path !== '/api/auth/login') {
    auth.clear()
    window.dispatchEvent(new Event('matai:logout'))
  }

  const data = await res.json().catch(() => ({}))

  if (!res.ok) {
    const detail = Array.isArray(data.detail)
      ? '입력값을 확인해 주세요.'
      : data.detail
    throw new Error(detail || `요청 실패 (${res.status})`)
  }

  return data
}

const qs = (params) => {
  const p = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== '' && v != null) p.set(k, v)
  })
  const s = p.toString()
  return s ? `?${s}` : ''
}

function filenameFrom(res, fallback) {
  const cd = res.headers.get('Content-Disposition') || ''
  const star = /filename\*=UTF-8''([^;]+)/i.exec(cd)
  if (star) {
    try {
      return decodeURIComponent(star[1])
    } catch {
      /* 아래 기본값 사용 */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(cd)
  return plain ? plain[1] : fallback
}

/** 인증 토큰을 붙여 파일을 받아 브라우저 다운로드로 저장한다. */
export async function download(path, { method = 'GET', body } = {}) {
  const headers = {}
  const token = auth.get()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let res
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  } catch {
    throw new Error('서버에 연결할 수 없습니다.')
  }

  if (res.status === 401) {
    auth.clear()
    window.dispatchEvent(new Event('matai:logout'))
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error((typeof data.detail === 'string' && data.detail) || `내보내기 실패 (${res.status})`)
  }

  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filenameFrom(res, 'export')
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export const api = {
  login: (id, password) => request('POST', '/api/auth/login', { id, password }),
  materials: () => request('GET', '/api/materials'),
  dashboard: () => request('GET', '/api/dashboard'),
  risks: (refresh = false) => request('GET', `/api/risks${refresh ? '?refresh=true' : ''}`),
  forecast: (p) => request('GET', `/api/forecast${qs(p)}`),
  forecastModels: () => request('GET', '/api/forecast/models'),
  forecastSeries: (materialId) =>
    request('GET', `/api/forecast/series${qs({ material_id: materialId })}`),
  orders: (p) => request('GET', `/api/orders${qs(p)}`),
  createOrder: (body) => request('POST', '/api/orders', body),
  updateOrder: (po, status) => request('PATCH', `/api/orders/${po}`, { status }),
  inventory: (p) => request('GET', `/api/inventory${qs(p)}`),
  scenarios: () => request('GET', '/api/simulation/scenarios'),
  simulate: (body) => request('POST', '/api/simulation', body),
  dataStatus: () => request('GET', '/api/data/status'),
  dataRefresh: () => request('POST', '/api/data/refresh'),
  settings: () => request('GET', '/api/settings'),
}
