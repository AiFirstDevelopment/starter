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
  // Assert the guard's own message, not just the class: null.toLowerCase()
  // throws a native TypeError as well, so matching on TypeError alone passed
  // identically with the guard deleted.
  assert.throws(() => slugify(null), {
    name: 'TypeError',
    message: 'slugify expects a string',
  })
  assert.throws(() => slugify(42), { message: 'slugify expects a string' })
})

test('a word that fits MAX_LENGTH exactly is kept', () => {
  // 50 + 1 + 9 === 60. This is the only shape that distinguishes `>` from
  // `>=` at the length comparison; without it an off-by-one there passes.
  const slug = slugify('a'.repeat(50) + ' ' + 'b'.repeat(9))
  assert.strictEqual(slug.length, MAX_LENGTH)
  assert.strictEqual(slug, 'a'.repeat(50) + '-' + 'b'.repeat(9))
})

test('a word one character too long is dropped', () => {
  const slug = slugify('a'.repeat(50) + ' ' + 'b'.repeat(10))
  assert.strictEqual(slug, 'a'.repeat(50))
})
