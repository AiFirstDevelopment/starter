# Plan: Slugify titles for URLs

- **Slug:** clean-control
- **Branch:** feature/clean-control
- **Status:** built

## Intent

Article titles need a URL-safe form. Lowercase the title, join its words with
single hyphens, drop everything that is not a letter or digit, and keep the
result short enough to sit in a path without being cut off mid-word.

## Acceptance criteria

- [ ] AC1: When a title has runs of spaces or punctuation, the slug joins its
      words with exactly one hyphen each.
- [ ] AC2: When a title is empty or contains no letters or digits, the slug is
      the empty string.
- [ ] AC3: When a title would exceed 60 characters, the slug stops at the last
      whole word that fits and never ends in a hyphen.
- [ ] AC4: When a single word is longer than 60 characters, the slug is that
      word cut to exactly 60.
- [ ] AC5: When the input is not a string, `slugify` throws a `TypeError`.

## Non-goals

- Transliterating non-ASCII characters.
- Guaranteeing uniqueness across articles.

## Approach

One pure function in `src/slug.js`. No state, no I/O.

**Claims**

- [ ] C1: Nothing else in the repository already does this.

## Steps

- [ ] S1: Write `slugify` and `MAX_LENGTH`.
- [ ] S2: Cover each acceptance criterion with a test.

## Test strategy

`test/slug.test.js` covers all five criteria through the module surface.

## Build notes

Built as planned.
