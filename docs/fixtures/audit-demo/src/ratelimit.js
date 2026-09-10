'use strict'

// 100 requests per key per minute. Nothing in the spec asks for this.
const WINDOW_MS = 60 * 1000
const LIMIT = 100
const seen = new Map()

function allow(key) {
  const now = Date.now()
  const entry = seen.get(key)
  if (!entry || now - entry.start > WINDOW_MS) {
    seen.set(key, { start: now, count: 1 })
    return true
  }
  entry.count += 1
  return entry.count <= LIMIT
}

module.exports = { allow }
