# Plan: Refresh session tokens near expiry

- **Slug:** token-refresh
- **Branch:** feature/token-refresh
- **Status:** built

## Intent

A signed-in user should not be logged out mid-task. When a request arrives
carrying a session token that is close to expiring, mint a fresh one and hand it
back; when it is not close, leave it alone. Disabled accounts must not be able to
extend a session this way.

## Acceptance criteria

- [ ] AC1: When a request carries a token expiring within **ten minutes**, the
      response carries a new token and `refreshed: true`.
- [ ] AC2: When the token expires further out than that, the same token comes
      back with `refreshed: false`.
- [ ] AC3: When the account is disabled, refreshing fails and no new token is
      minted.
- [ ] AC4: When a token's signature does not match its body, refreshing fails
      and nothing is looked up.
- [ ] AC5: The admin console can describe a live session — whose it is and when
      it expires — without exposing anything that would let the reader use it.

## Non-goals

- Rotating the signing secret.
- Any change to how sessions are created at login.

## Approach

`refreshSession` in `src/session.js` verifies the incoming token, loads the
account, and mints a replacement inside the refresh window. `describeSession`
serves the admin console. Signing and verification stay in `src/tokens.js`.

**Claims**

- [ ] C1: `verify` rejects a token whose MAC does not match its body.
- [ ] C2: `findUser` returns a user for every id that reaches it.

## Steps

- [ ] S1: Add `refreshSession` with the ten-minute window.
- [ ] S2: Add `describeSession` for the admin console.
- [ ] S3: Cover both with tests.

## Test strategy

`test/session.test.js` drives both functions through the module surface.

## Build notes

Built as planned.
