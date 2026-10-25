# Public Release Checklist

Complete this checklist only after the candidate PR is independently accepted
and explicitly authorized for release.

- [ ] Candidate SHA and terminal CI are unchanged and all required jobs pass.
- [ ] Full-history exposure audit has no hard secret/private-key blocker.
- [ ] Any non-noreply commit metadata warning has explicit human disposition.
- [ ] Repository visibility change consequences, including public Actions logs,
      have been reviewed.
- [ ] Apache-2.0, SECURITY.md and contribution guidance are visible and current.
- [ ] Dependabot, secret scanning, push protection and code scanning are enabled
      where available; main protection is restored after visibility changes.
- [ ] Vercel project root is `web`, framework is Vite, Node is 24.x, and no
      application secrets are configured.
- [ ] Public smoke checks landing/gallery/detail routes, replay digests, the
      recorded-replay badge and zero backend/inference requests.
- [ ] Immutable releases are enabled where available; draft `v1.0.0` targets the
      exact verified main SHA.
- [ ] Tag, release and production URL are cross-checked before publication.
- [ ] Superseded historical PRs are closed only after the final PR is merged.
