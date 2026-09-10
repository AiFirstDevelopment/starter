'use strict'

const test = require('node:test')
const assert = require('node:assert')
const { request } = require('./helper')

test('a request with no API key is rejected with 401', async () => {
  const res = await request('/widgets/w1', {})
  assert.strictEqual(res.status, 401)
  assert.strictEqual(res.body, '')
})

test('a request with an unrecognised API key is rejected with 401', async () => {
  const res = await request('/widgets/w1', { 'X-Api-Key': 'not-a-real-key' })
  assert.strictEqual(res.status, 401)
})

test('every successful response carries a unique X-Request-Id', async () => {
  const first = await request('/health', { 'X-Api-Key': 'test-key' })
  const second = await request('/health', { 'X-Api-Key': 'test-key' })
  assert.ok(first.headers['x-request-id'])
  assert.notStrictEqual(first.headers['x-request-id'], second.headers['x-request-id'])
})

test('the rate limiter answers 429 past the per-key limit', async () => {
  let last
  for (let i = 0; i < 101; i++) last = await request('/health', { 'X-Api-Key': 'burst-key' })
  assert.strictEqual(last.status, 429)
})
