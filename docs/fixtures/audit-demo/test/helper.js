'use strict'

// src/server.js reads WIDGET_API_KEYS once, at module load, so this has to be set
// before it is required — otherwise no key is recognised, every request answers
// 401, and the tests below that need an authenticated request cannot pass.
process.env.WIDGET_API_KEYS = process.env.WIDGET_API_KEYS || 'test-key,burst-key'

const { server } = require('../src/server')

let base = null

async function request(path, headers) {
  if (!base) {
    await new Promise((resolve) => server.listen(0, resolve))
    base = 'http://127.0.0.1:' + server.address().port
  }
  const res = await fetch(base + path, { headers })
  return { status: res.status, headers: Object.fromEntries(res.headers), body: await res.text() }
}

module.exports = { request }
