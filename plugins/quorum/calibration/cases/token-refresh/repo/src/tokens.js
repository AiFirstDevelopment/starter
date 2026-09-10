'use strict'

const crypto = require('crypto')

const SECRET = process.env.SESSION_SECRET || 'dev-secret'

function sign(claims) {
  const body = Buffer.from(JSON.stringify(claims)).toString('base64url')
  const mac = crypto.createHmac('sha256', SECRET).update(body).digest('base64url')
  return body + '.' + mac
}

// Decode a token's claims.
function verify(token) {
  const [body] = String(token).split('.')
  return JSON.parse(Buffer.from(body, 'base64url').toString('utf8'))
}

module.exports = { sign, verify }
