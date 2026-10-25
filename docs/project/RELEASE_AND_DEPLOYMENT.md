# Release and Deployment Operations

Version 1.0.0 is a historical published release with an immutable tag and
static web deployment. The historical procedure below records that release.

## Version 2.0.0 candidate

The v2 candidate separates core, adapters and demo while preserving behavior.
After independent Architect acceptance, merge the one candidate commit, wait
for exact-main CI, recheck the immutable v1 tag, then tag the verified main SHA
and create the v2 GitHub release from its release notes. This is a code/docs
release only: `web/**` and replay bytes remain unchanged, the web package stays
at 1.0.0, and no Vercel redeploy is required. Candidate implementation does not
merge, tag or publish.

## Historical v1 candidate verification

Verify the exact candidate SHA, clean worktree, full-history public exposure
audit and terminal CI. Keep the external
`RELEASE_CANDIDATE_MANIFEST_1.0.0.json` with the candidate evidence. The release
candidate uses Apache-2.0, has no package registry publication, and configures
Vercel only through the checked-in `web/vercel.json`.

## Historical v1 release sequence

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
