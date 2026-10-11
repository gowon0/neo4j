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

export const api = {
  login: (id, password) => request('POST', '/api/auth/login', { id, password }),
  materials: () => request('GET', '/api/materials'),
  dashboard: () => request('GET', '/api/dashboard'),
  risks: (refresh = false) => request('GET', `/api/risks${refresh ? '?refresh=true' : ''}`),
  forecast: (p) => request('GET', `/api/forecast${qs(p)}`),
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
