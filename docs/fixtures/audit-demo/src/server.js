'use strict'

const http = require('http')
const crypto = require('crypto')
const { fetchWidget } = require('./upstream')
const { allow } = require('./ratelimit')

const KEYS = new Set((process.env.WIDGET_API_KEYS || '').split(',').filter(Boolean))

function unauthorized(res) {
  res.writeHead(401)
  res.end()
}

const server = http.createServer(async (req, res) => {
  const requestId = crypto.randomUUID()

  const key = req.headers['x-api-key']
  if (!key || !KEYS.has(key)) return unauthorized(res)

  if (!allow(key)) {
    res.writeHead(429, { 'X-Request-Id': requestId })
    return res.end()
  }

  if (req.url === '/health') {
    res.writeHead(200, { 'X-Request-Id': requestId, 'Content-Type': 'application/json' })
    return res.end(JSON.stringify({ status: 'ok' }))
  }

  if (req.url === '/metrics') {
    res.writeHead(200, { 'X-Request-Id': requestId, 'Content-Type': 'text/plain' })
    return res.end(report())
  }

  const match = /^\/widgets\/(\w+)$/.exec(req.url || '')
  if (!match) {
    res.writeHead(404, { 'X-Request-Id': requestId })
    return res.end()
  }

  try {
    const widget = await fetchWidget(match[1])
    res.writeHead(200, { 'X-Request-Id': requestId, 'Content-Type': 'application/json' })
    res.end(JSON.stringify(widget))
  } catch (err) {
    res.writeHead(502, { 'X-Request-Id': requestId })
    res.end()
  }
})

let served = 0
function report() {
  return 'widget_requests_total ' + served + '\n'
}

server.on('request', () => { served += 1 })

module.exports = { server }
