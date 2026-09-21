# UI consistency review — September 20, 2026

## Reviewed

Navigation, dashboards and preferences, timeline and child history, measurement and activity lists/forms, calendar appointments, reports, timers, child/tag/user management, deletion confirmations, login and password reset.

## Updated

- Management tables, settings, confirmations, timer details, authentication, and empty states now use the shared surfaces and button styles.
- Management pages filter real fields; nonfunctional From/To date controls are removed.
- Tag permissions and tag filtering are corrected. Tag details count each record once, include newer activity types, and only link to permitted data.
- Child detail/history uses the modern timeline and its validated period filters.
- Birth time and account expiration use minute-only entry controls with both clock formats. Existing birth/expiration timestamp precision is preserved when the displayed minute is unchanged.
- Settings link to the dedicated dashboard editor instead of duplicating its checkbox list. The existing data-age cutoff retains its original meaning.
- Empty hidden dashboard cards no longer leave invisible grid cells.
- Calculated BMI shows its source weight and height instead of unused manual-entry columns.
- Feeding and medication interval points align with the correct event, including duplicate timestamps. Interval reports gracefully handle insufficient data.
- Reports use the app theme; redundant chart titles and time-preview instructions are removed.
- Login and password-reset failures display actual validation feedback. Invalid reset links offer a new-link action.
- Necessary validation, account-role explanations, password requirements, and destructive-action confirmations remain.

## Verification

- Full regression suite: 591 passing tests.
- Isolated password-reset workflow: passing.
- Live read-only sweep: 99 rendered pages returned HTTP 200. The appointment preview requires input and correctly returns HTTP 400 when omitted.
- Styles and scripts rebuilt; style validation passed; no new migrations required.
- New regression coverage checks management filters, entry controls, tag counts and permissions, legacy child history, interval edge cases, and optional expiration inputs.

## Limits

Browser automation failed to create a usable page in this environment. Rendered HTML and live responses were checked, but visual layout and pointer/keyboard interaction still need a browser review. External calendar/provider integrations were not exercised. No changes have been pushed to GitHub.
