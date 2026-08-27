'use strict'

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
