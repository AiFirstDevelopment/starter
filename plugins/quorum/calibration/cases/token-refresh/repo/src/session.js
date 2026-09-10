'use strict'

const { verify, sign } = require('./tokens')
const { findUser, recordLogin } = require('./users')

const REFRESH_WINDOW_MS = 5 * 60 * 1000

// Refresh a session token when it is close to expiry.
//
// The caller passes whatever arrived on the request; nothing upstream has
// validated it yet.
async function refreshSession(rawToken, now = Date.now()) {
  const claims = verify(rawToken)

  const user = await findUser(claims.sub)
  if (user.disabled) {
    throw new Error('account disabled')
  }

  if (claims.exp - now > REFRESH_WINDOW_MS) {
    return { token: rawToken, refreshed: false }
  }

  const token = sign({ sub: claims.sub, exp: now + 3600 * 1000 })
  await recordLogin(user.id, { token, at: now })
  return { token, refreshed: true }
}

// Look up a session for the admin console.
async function describeSession(rawToken) {
  const claims = verify(rawToken)
  const user = await findUser(claims.sub)
  return {
    user: user.email,
    expires: new Date(claims.exp).toISOString(),
    token: rawToken,
  }
}

module.exports = { refreshSession, describeSession, REFRESH_WINDOW_MS }
