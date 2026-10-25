# Release and Deployment Operations

## Version 2.1.0 release procedure

Version 2.1.0 is an additive interface-only release. After independent
acceptance: merge the accepted PR, wait for exact-main CI, verify dependency and
security state, verify the predecessor tags, tag the exact verified main SHA as
`v2.1.0`, and create the GitHub Release using
`release/RELEASE_NOTES_2.1.0.md`. There is no `web/**` change and no production
Vercel redeploy is required.

## Historical v2.0.0 release

Version 2.0.0 is immutable at `77574ee445e97fe282a62c2528b2c250e6998ddb`. It
established the core/adapters/demo boundary. Never move its tag.

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

Never move any published SemVer tag. Corrective changes become a new version.
If publication or deployment fails, leave the prior immutable state intact and
investigate through a new release commit.
