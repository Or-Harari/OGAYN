export type JwtPayload = Record<string, any>

function base64UrlToBase64(s: string): string {
  s = s.replace(/-/g, '+').replace(/_/g, '/')
  const pad = s.length % 4
  if (pad === 2) s += '=='
  else if (pad === 3) s += '='
  else if (pad !== 0) s += '==='
  return s
}

export function decodeJwtPayload(token: string | null): JwtPayload | null {
  if (!token) return null
  try {
    const parts = token.split('.')
    if (parts.length < 2) return null
    const payload = parts[1]
    const b64 = base64UrlToBase64(payload)
    // Frontend-only: use atob for base64 decoding; avoid Node Buffer to keep build clean
    const jsonStr = (typeof atob === 'function' ? atob(b64) : (globalThis as any).atob?.(b64)) as string
    const obj = JSON.parse(jsonStr)
    return obj || null
  } catch {
    return null
  }
}

export function isJwtExpired(token: string | null): boolean {
  const p = decodeJwtPayload(token)
  if (!p) return true
  const exp = p.exp
  if (!exp) return false
  const nowSec = Math.floor(Date.now() / 1000)
  const expNum = typeof exp === 'number' ? exp : Number(exp)
  return isFinite(expNum) ? expNum <= nowSec : true
}
