# Backend and UI security review

## Context

Review the current local and hosted app for exploitable dependency and
application issues. The 2026-10-08 audits found a vulnerable locked PyJWT
version and several UI build-tool advisories. Completion means upgrading
reachable vulnerable packages, adding targeted protections for confirmed
application gaps, and recording advisories that cannot affect this app's
trusted build workflow or lack a patched release.

## Design

Keep account and Origin checks at the server boundary, as described in
`docs/SECURITY.md`. Preserve the core/adapters split in `ARCHITECTURE.md`.
Use the smallest compatible dependency upgrades. Check browser security
headers and development-server exposure without changing coaching behavior.
Treat dev-only parsers as lower risk when they never parse rider input.

## Steps

1. Audit locked Python and pnpm dependencies against current advisories.
2. Review auth, request limits, response headers, UI rendering, and dev
   server configuration for concrete vulnerabilities.
3. Upgrade vulnerable dependencies and fix confirmed application gaps.
4. Add regression tests for security boundaries that changed.
5. Run audits and `make check`; document any residual advisory and its reachability.

## Verification

- `pip-audit` against the workspace environment and `pnpm audit` against the
  lockfile.
- Backend tests for any new request/header behavior.
- `make check` and `git diff --check`.

## Build status

Completed on 2026-10-08. PyJWT now resolves to 2.15.1, Vite to 6.4.4,
esbuild to 0.25.12 and source-map-js to 1.2.2. Backend private responses
disable caching and sniffing; secret settings stay out of diagnostic reprs;
CloudFront adds UI security headers and a CSP.
`pip-audit` found no known third-party Python vulnerabilities. `pnpm audit`
fell from seven advisories to two Tailwind build-chain advisories, recorded
in `docs/SECURITY.md` and the tech-debt tracker. `make check` passed (299
Python tests, web lint and typecheck); the production UI build and Pulumi
module syntax check passed. The CloudFront policy still needs verification
after a real deployment.

Quality self-score: correctness passes local checks but live CloudFront
verification is deferred; one source of truth for auth and account scoping
remains in core; no sensor behavior changed; security headers have an API
regression test; docs match the implementation; the change stayed inside
this plan; local binding and account isolation remain intact.
