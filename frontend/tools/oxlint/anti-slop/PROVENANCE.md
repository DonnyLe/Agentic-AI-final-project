# anti-slop (vendored)

Source: https://github.com/dmmulroy/anti-slop
Commit: 13909c9e07590f5a85d93c62712259fe14a883f7
Copied: 2026-11-15

Copied `src/` without the `*.test.ts` files and without the opt-in Effect rules (`src/effect/`), since this project doesn't use Effect. Upstream pins `oxlint` and `@oxlint/plugins` at 1.78.0; this project runs them at 1.93.0.

These files are ours to maintain now. Record local changes here.
