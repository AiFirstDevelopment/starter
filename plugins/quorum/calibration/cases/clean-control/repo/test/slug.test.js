'use strict'

const assert = require('node:assert')
const { test } = require('node:test')
const { slugify, MAX_LENGTH } = require('../src/slug')

test('joins words with single hyphens', () => {
  assert.strictEqual(slugify('Hello   Brave New World'), 'hello-brave-new-world')
})

test('drops punctuation rather than encoding it', () => {
  assert.strictEqual(slugify("Ada's Notes: Vol. 2"), 'ada-s-notes-vol-2')
})

test('an empty or punctuation-only title yields an empty slug', () => {
  assert.strictEqual(slugify(''), '')
  assert.strictEqual(slugify('!!! ???'), '')
})

test('trims to MAX_LENGTH without splitting a word', () => {
  const slug = slugify('supercalifragilistic ' + 'expialidocious '.repeat(6))
  assert.ok(slug.length <= MAX_LENGTH, `${slug.length} > ${MAX_LENGTH}`)
  assert.ok(!slug.endsWith('-'), 'must not end mid-join')
  assert.strictEqual(slug, 'supercalifragilistic-expialidocious-expialidocious')
})

test('a single word longer than MAX_LENGTH is cut to it', () => {
  const slug = slugify('z'.repeat(100))
  assert.strictEqual(slug.length, MAX_LENGTH)
})

test('rejects a non-string', () => {
  assert.throws(() => slugify(null), TypeError)
})
