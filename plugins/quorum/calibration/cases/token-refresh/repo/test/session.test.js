'use strict'

const assert = require('node:assert')
const { test } = require('node:test')
const { refreshSession, describeSession } = require('../src/session')
const { sign } = require('../src/tokens')

test('refreshSession returns a token', async () => {
  const now = Date.now()
  const token = sign({ sub: 'u1', exp: now + 1000 })
  const result = await refreshSession(token, now)
  assert.ok(result.token)
})

test('describeSession returns something', async () => {
  const now = Date.now()
  const token = sign({ sub: 'u1', exp: now + 1000 })
  const result = await describeSession(token)
  assert.ok(result)
})
