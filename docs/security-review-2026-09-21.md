# Security review — September 21, 2026

Reviewed the local Django application, access controls, calendar subscriptions,
exports, upload delivery, authentication settings, and Python/JavaScript dependencies.
This is a source and regression-test review, not an exhaustive penetration test.

## Fixed

- Calendar subscription links exposed the user's general API key. New credentials
  are read-only, scoped to one child, checked against current account permissions
  and expiration, and revoked when the API key is regenerated. Old API-key feed URLs
  are rejected; existing subscribers need new links from Appointments.
- Full-data export checked staff status without checking access to the exported
  record types. Export now requires view permission for every included model.
- User text beginning with spreadsheet formula characters was exported directly.
  CSV/TSV downloads now escape that text, including exports through Django admin.
- Local uploaded child pictures, note images, and thumbnails could be requested
  anonymously. Local media now requires the matching record permission, accepts
  session or API authentication, rejects unsafe paths and executable formats,
  and sends no-store and nosniff headers.
- API HEAD requests did not require the corresponding view permission. They now
  enforce the same permission as GET.
- Development used a shared, predictable signing key. A per-installation random key
  is now stored in the Git-ignored `.development-secret-key` file.
- Replaced outdated JavaScript minification/icon tooling and the full Plotly
  dependency tree with maintained minification and the Cartesian distribution
  actually used by the app. Browser locales and icon-update functionality remain.
- Calendar text escaping now rejects carriage-return property injection.

## Verification

- 661 Python tests passed, plus the isolated password-reset test: 662 total.
- 9 JavaScript tests passed.
- Formatting checks and static asset build passed; no pending model migrations.
- Actual Chrome rendering verified the rebuilt growth chart and its SVG output.
- Authenticated dashboard, inventory, appointments, and growth pages returned 200.
- Final npm audit: zero known vulnerabilities, down from eight dependency findings.
  The findings included transitive packages; this did not establish that each was
  exploitable in the app's served assets.
- Python audit: 69 installed packages checked, none skipped, no known vulnerabilities.
- Server restarted on 127.0.0.1:8000.

## Remaining account and deployment items

An active administrator account still uses a default password. Replacement is pending
the user's choice between generating a strong password in a private local file and
changing it in the app. No account password was changed during this review.

The server remains a local HTTP development instance with DEBUG enabled. Django's
five remaining deployment warnings concern HTTPS/HSTS, secure-only cookies, and
DEBUG. Before making it internet-facing, configure production settings and TLS.
Reverse proxies must route media requests through Django. External object storage
must remain private and use signed URLs; direct public storage bypasses these checks.
See [security configuration](configuration/security.md).

## Advisory references

- [MapLibre sanitizer advisory](https://github.com/advisories/GHSA-jrc7-96c5-q579)
- [Terser regular-expression advisory](https://github.com/advisories/GHSA-4wf5-vphf-c2xc)
- [Lodash template advisory](https://github.com/advisories/GHSA-35jh-r3h4-6jhm)
- [Django security guidance](https://docs.djangoproject.com/en/6.0/topics/security/)

## Follow-up review: security and performance

Reviewed the newer inventory/reminder code plus API list handling, HTML fragments,
request-local timezone state, and outgoing webhook delivery.

- API responses cap `limit` at 1,000 entries (the default stays 100), with normal
  offset pagination for larger exports. This bounds response generation work.
- Eager loading authors and tags reduced a measured 20-entry diaper API request
  from 43 database queries to 4. Returned records and permissions are unchanged.
- Reminder navigation no longer loads archived supplies or long notes. Added
  `(child, time)` and `(item, action, created_at)` indexes for usage lookups.
- Webhooks only dispatch after transaction commit, so rolled-back entries do not
  leave the app. Redirects are rejected, non-HTTP(S) destinations and embedded
  URL credentials are rejected, and failures no longer log URLs or exception
  messages that could contain webhook tokens.
- Webhooks use four workers and at most 64 pending/running jobs, replacing an
  unbounded thread per event. Saturated delivery logs a warning and drops the event;
  this remains best-effort delivery, not a durable queue. Private-network endpoints
  remain supported for Home Assistant. Admin-configured destinations remain trusted;
  this is not a general-purpose SSRF sandbox.
- Timezone settings are confined to a request and restored on success or failure.
- Replaced unsafe HTML construction with escaping in overlap errors and the 404
  template. Current overlap labels are fixed model names and Django quotes the
  default 404 path, so no active stored/reflected XSS exploit was established for
  these paths; these changes harden them against future dynamic content.

Fresh dependency audits found zero known vulnerabilities: npm audited 398
packages and pip-audit checked all 68 installed Python packages with none skipped.
Dependency audits cannot prove the application is free of vulnerabilities.

The active default administrator password still needs replacement; user approval
was requested because changing it signs that account out. Local HTTP development
still produces the five deployment warnings listed above. Neither finding is
silently treated as resolved.

Guidance used: [Django HTML safety](https://docs.djangoproject.com/en/6.0/topics/security/)
and [OWASP redirect handling for outbound requests](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).

Follow-up verification: 711 Python tests and 9 JavaScript tests passed, repository
formatting passed, and no model migrations are missing. Authenticated dashboard,
timeline, inventory, add-supply, and reports pages returned 200. SQLite query plans
confirmed use of both new indexes. The database was backed up before applying the
index migrations and the local server was restarted successfully.
