# Release and Deployment Operations

## Version 2.0.0 release procedure

Version 2.0.0 separates core, adapters and demo while preserving behavior. After
independent acceptance: merge the accepted PR, wait for exact-main CI, verify the
historical v1 tag, verify the reviewed dependency state/security closure, tag the
exact verified main SHA as `v2.0.0`, and create the GitHub Release using
`release/RELEASE_NOTES_2.0.0.md`. This is a code/docs release only: generated
static output and replay bytes remain unchanged, the web package stays at 1.0.0,
and no production Vercel redeploy is required because the Vite delta is build/dev
tooling.

## Historical v1.0.0 release

Version 1.0.0 is preserved by immutable tag `v1.0.0` at
`e9fd3d29a969d66ad907ff5f7d0ea0055ed7ae2a`. Its static recorded-replay
deployment remains the historical production evidence viewer. Pre-release
acceptance artifacts remain in repository history/internal acceptance history;
current release procedures do not treat them as current instructions.

## Historical release boundary

The v1 release checklist is retained under internal acceptance history. Current
operations use exact release commits and the current v2 verification gates.

## Rollback boundary

Never move an immutable `v1.0.0` tag. Corrective changes become a new version.
If publication or deployment fails, leave the prior immutable state intact and
investigate through a new release commit.
