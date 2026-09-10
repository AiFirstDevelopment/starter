'use strict'

const MAX_LENGTH = 60

// Turn a title into a URL slug: lowercase, words joined by single hyphens,
// trimmed to MAX_LENGTH without splitting a word.
function slugify(title) {
  if (typeof title !== 'string') {
    throw new TypeError('slugify expects a string')
  }

  const words = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .split(' ')
    .filter(Boolean)

  if (words.length === 0) {
    return ''
  }

  let slug = words[0].slice(0, MAX_LENGTH)
  for (const word of words.slice(1)) {
    if (slug.length + 1 + word.length > MAX_LENGTH) {
      break
    }
    slug += '-' + word
  }
  return slug
}

module.exports = { slugify, MAX_LENGTH }
