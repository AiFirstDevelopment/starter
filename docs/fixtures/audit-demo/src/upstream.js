'use strict'

const STORE = process.env.WIDGET_STORE_URL || 'http://widget-store.internal'

// One call. If the store fails, the failure is what the caller gets.
async function fetchWidget(id) {
  const response = await fetch(STORE + '/widgets/' + id)
  if (!response.ok) throw new Error('widget store answered ' + response.status)
  return response.json()
}

module.exports = { fetchWidget }
