# Release and Deployment Operations

This document describes the authorized sequence for the 1.0.0 release. The
release candidate itself does not merge, change repository visibility, create a
tag or release, create a Vercel project, or deploy.

## Candidate verification

Verify the exact candidate SHA, clean worktree, full-history public exposure
audit and terminal CI. Keep the external
`RELEASE_CANDIDATE_MANIFEST_1.0.0.json` with the candidate evidence. The release
candidate uses Apache-2.0, has no package registry publication, and configures
Vercel only through the checked-in `web/vercel.json`.

## Authorized release sequence

After independent Architect review and separate explicit user authorization:

1. Merge only the cumulative candidate PR into `main`.
2. Wait for all `main` verification jobs and record the resulting SHA.
3. Re-run the full-history exposure audit on that exact `main` SHA.
4. Change repository visibility to public and immediately inspect README,
   LICENSE, SECURITY and public Actions exposure.
5. Enable available security controls and restore branch protection as needed.
6. Create/link the Vercel project with root `web`, Node 24 and no environment
   variables, then deploy the exact verified `main` SHA.
7. Run the public static-evidence smoke and verify replay digests and zero
   backend/inference requests.
8. Enable immutable releases if available, create the draft `v1.0.0` tag/release
   at the verified `main` SHA, cross-check the tag, deployment URL and SHA, then
   publish.
9. Close superseded historical PRs only after the final PR is merged.

## Rollback boundary

Never move an immutable `v1.0.0` tag. Corrective changes become a new version.
If publication or deployment fails, leave the prior immutable state intact and
investigate through a new candidate.
