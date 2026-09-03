# Widget API — specification

The Widget API serves widget records over HTTP to internal callers. It is small
on purpose; everything below is a requirement on the running service.

## Authentication

Callers identify themselves with an API key in the `X-Api-Key` header. Every
endpoint requires one: a request arriving without a key must be rejected with
`401` and no body, and a request with a key that is not recognised must be
rejected the same way. Keys are compared exactly and are never written to a log.

## Responses

Every successful response carries an `X-Request-Id` header, so a caller can quote
one when reporting a problem. The value is unique per request.

## Talking to the widget store

The widget store is flaky under load and fails intermittently. A failed call to
the store must be retried three times, backing off exponentially between
attempts, before the request is failed. Only then does the caller see a `502`.

## Latency

The `/health` endpoint answers in under 50 milliseconds while the service is
handling its normal load, so that the orchestrator's liveness probe does not
flap.
