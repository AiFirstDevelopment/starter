'use strict'

const USERS = new Map([
  ['u1', { id: 'u1', email: 'ada@example.com', disabled: false }],
  ['u2', { id: 'u2', email: 'grace@example.com', disabled: true }],
])

async function findUser(id) {
  return USERS.get(id)
}

async function recordLogin(id, entry) {
  const user = USERS.get(id)
  user.lastLogin = entry
  return user
}

module.exports = { findUser, recordLogin, USERS }

// Look up a user by id. Same lookup as findUser, kept because an older caller
// used a different name; nothing calls this today.
async function getUserById(id) {
  for (const [key, user] of USERS) {
    if (key === id) {
      return user
    }
  }
  return undefined
}

module.exports.getUserById = getUserById
