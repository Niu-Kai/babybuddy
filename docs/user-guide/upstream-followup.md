# Upstream issue follow-up

## Care entry validation

Feeding forms, the API, offline replay, and imports reject formula or fortified milk recorded as direct breastfeeding, and solid food recorded as a bottle. Mixed breast milk/formula bottles remain supported. Direct nursing followed by a bottle should be recorded as two entries because the delivery methods differ. Historical records are not rewritten.

Interval columns use “earlier” for gaps between historical records. Sleep labels the gap as “Awake between sleep sessions.” Sleep, diaper changes, and tummy time calculate the preceding entry for the same child, even across pagination and date filters.

## Equipment (#1004)

Open Inventory → Equipment & limits. Add the equipment manually, select children, and enter the manufacturer's maximum weight and/or height in the units printed on the product. Optional instructions cover other restrictions; “Needs review” can flag a developmental milestone. There is no automatic product lookup.

The list and dashboard compare each child's latest measurements with recorded units against the entered limits. Measurements without known units are not guessed. Reaching a limit produces an in-app review alert; archiving an item stops its alerts. “Below entered limits” does not evaluate unentered restrictions or developmental milestones. No scheduled email or push notifications are sent.

## Access to selected children (#187)

When managing a caregiver or read-only user, enable “Restrict to selected children” and select the children they may access. Selecting none grants access to no child records. Staff/administrator accounts retain administrative scope; use a nonstaff caregiver or read-only account for restrictions.

The rules cover data queries, forms, APIs, reports, timelines, protected images, and calendar subscriptions. Pumping and household inventory retain role-based access. Equipment assignments that an editor cannot view are preserved when the shared item is edited. A saved child selector is never an access grant.

## Offline care logging (#1095)

The core request to log care without a server connection is implemented and automated/browser-tested. Physical-phone verification of offline entry, reopening, and reconnection/sync remains; see the current remaining-issues list. Broader full-offline functionality is tracked under #128.

While connected, open Settings → Offline access → Enable on this device on a private device. Supported regular Add entry forms can save to the local queue; disconnected navigation opens the cached basic entry form for the selected activity and child. Timers and custom activities are supported. Pending entries survive reloading and sync on reconnection, reopening/focus, or the five-minute interval while the app is open. A closed app cannot guarantee background sync. Recent history is cached for the last seven days, up to 200 entries.

A service worker caches only the public entry shell and static assets, not authenticated pages. Local setup stores child names and allowed entry choices; pending entries remain on the device. API keys, session cookies, and CSRF tokens are not written into the offline database. Settings provides Sync now and Clear this device; clearing removes local setup and pending entries after confirmation.

Sync requires the original account, rechecks current permissions and child access, and validates units and timestamps. Each entry has a unique identifier recorded transactionally with its creation. A retry after a lost response cannot create another record or deduct stock again. Validation errors remain in the queue and can be corrected or discarded. Offline appointments, attachments, the complete dashboard/history, and edits to existing server records remain outside the implemented scope.

## Custom activities (#217)

Activities → Custom activities → Activity types lets an administrator define a name, optional duration, number/unit, dropdown choices, yes/no field, and text field. Children, date/time, and notes are standard fields. Archive an unused type to stop new entries; history remains available. Entries appear in their list and the timeline and can be exported. Caregivers may log entries but cannot redefine activity types.

## Display preferences (#836)

User Settings → Entry preferences can hide activities from navigation and hide optional notes, tags, feeding amounts/mixed bottle fields, or diaper details. Hiding fields preserves existing values during edits; required fields remain available. These are presentation preferences, not permissions. Dashboard panels retain their separate customization controls.

## API additions (#161, #575)

`GET /api/dashboard` returns permitted children with their latest feeding, sleep, and diaper change, plus visible timers. Missing model permissions omit those data categories. No GraphQL dependency is needed for this common aggregate request.

Timers accept a `context` object, for example `{"activity":"feeding","type":"breast milk","method":"left breast"}`. Supported activities are feeding, sleep, pumping, tummytime, and bathtime. The browser timer form chooses the intended activity; API clients can additionally provide feeding defaults. Defaults prefill the matching entry form/API and can be overridden. Unrecognized context keys and invalid combinations are rejected.

## Deferred

The guided import interface (#123) remains deferred as requested. Existing exports remain available. Deployment-specific Home Assistant/proxy reports and broader mobile/localization issues still require their respective environments; this work does not claim to resolve all upstream tickets.

## Solid foods within Feeding (#929)

Choose Solid food in Feeding. Pick a previously recorded food or type a new name; Add food adds another row, with an optional reaction for each food. These are linked Food entries, not copies: editing a reaction in Food is reflected in Feeding. Changing a meal's date/time or child updates its linked foods. Edit those shared fields from Feeding. Removing a food row removes that exposure and requires food-delete permission. Deleting the feeding itself preserves its food history as independent entries. Older feeding entries are not guessed or backfilled. The full timeline groups foods with their meal; the Food filter still lists each exposure.

## Integration settings (#878)

Authenticated `GET /api/settings` returns the server time, effective request time zone, and permitted nap hours, dashboard day start, and feeding interval setting. It never returns webhook URLs, secrets, or other users' preferences. This endpoint is read-only. It makes information available to integrations; it does not install or connect Home Assistant automatically.

## Flexible read queries (#926)

Authenticated `GET /api/query` describes the resources, output fields, filters, sort fields, and supported sum metrics available to the current account. `POST /api/query` reads several resources in one request. It performs no writes. Existing role and child permissions apply, including to counts and totals. Household inventory and pumping remain shared by role.

```json
{
  "queries": [
    {
      "key": "last_bottle",
      "resource": "feedings",
      "filters": { "child": 1, "method": "bottle" },
      "fields": ["id", "start", "amount"],
      "order_by": "-start",
      "limit": 1
    },
    {
      "key": "sleep_total",
      "resource": "sleep",
      "filters": {
        "child": 1,
        "start_min": "2026-09-22T00:00:00-10:00",
        "start_max": "2026-09-22T23:59:59-10:00"
      },
      "operation": "sum",
      "metric": "duration"
    },
    {
      "key": "diapers",
      "resource": "inventory",
      "filters": { "category": "diapers", "archived": false },
      "fields": ["id", "name", "size", "quantity", "unit"]
    }
  ]
}
```

Each result is keyed by the caller's unique `key`. Lists return `items` and `next_offset`; pass `offset` to request another page. Operations are `list`, `count`, and `sum`. Duration sums are in seconds and count the full duration of matching sessions (the example matches sessions that start that day, rather than clipping overnight sessions at midnight). Other sums are intentionally unavailable where legacy units could make the result ambiguous. Existing measurement endpoints retain their existing storage-unit semantics.

Limits: 10 queries per request, 50 rows per query, offset up to 10,000, 20 KB query JSON, and 60 requests per minute per account. Unknown filters/fields/orderings are rejected; arbitrary database paths and write operations are not supported. A denied or invalid query fails the request. This is a bounded JSON query API, not a GraphQL endpoint. API-token and authenticated-session access use existing authentication.

## Home Assistant timestamps (#1121)

Direct API tests cover Home Assistant-style form-encoded timestamps with UTC, negative offsets, fractional-hour offsets, and positive offsets crossing dates. Equal instants are preserved; current timestamps are accepted and future clock values remain rejected. Completed feeding end times are now checked as well as start times. The API settings response includes `server_time` for clock diagnostics.

The integration source examined uses aware timestamps and has its own future-time check. Its generic error log mentions an old upgrade/fallback for multiple errors; that message alone does not identify the cause. No live Home Assistant instance was used, and the upstream report is not claimed resolved. Check the actual sent timestamp and clock synchronization when testing the future installation.

References: [upstream issue](https://github.com/babybuddy/babybuddy/issues/1121), [integration services](https://github.com/jcgoette/baby_buddy_homeassistant/blob/master/custom_components/babybuddy/services.py), [integration client](https://github.com/jcgoette/baby_buddy_homeassistant/blob/master/custom_components/babybuddy/client.py).

## Form refresh protection (#1019)

The app's pull-to-refresh gesture is disabled on pages containing entry/POST forms and while zoomed in. Form pages also suppress native vertical overscroll refresh. The check follows the current DOM after page navigation; dashboard refresh remains available. This does not block an explicit browser reload. Behavior still needs confirmation on a physical Firefox Android device.

Native single sign-on (#907) remains deferred by choice; separate Baby Buddy accounts are retained.

## Empty household, pumping, and medication history

Child-specific Add Entry pages send an authorized user to Add Child when no accessible child exists, then return to the intended entry. Users without permission to create children receive administrator guidance. Shared household pumping and inventory remain available according to their role.

Pumping supports optional `left_amount` and `right_amount` alongside the existing `amount`. When either side is supplied, the total and side are derived automatically. Browser entries use the selected entry unit; API quantities retain their existing canonical storage units. Editing a side through PATCH recalculates the total. For older API clients, an amount-only PATCH intentionally clears the side breakdown. Existing total-only records are unchanged.

New medication entries offer a searchable history list for the selected child. Selecting a name fills the most recently recorded dosage, unit, and interval for review; it never administers or saves a dose automatically. Switching children clears details selected from history. Suggestions require medication-view permission and respect child restrictions.

The visible feeding label is now “Caregiver fed.” Its stored/API value remains `parent fed`. No separate assistance field was added.

## Translation maintenance

American English remains the source language. Interface messages use Django catalogs, including the newer inventory, equipment, custom activity, offline, and browser controls. User-entered names, notes, and activity definitions are not translated. Chinese catalog folders use Django's case-sensitive names (`zh_Hans` and `zh_Hant`). Language activation is scoped to each request, and JavaScript catalogs have explicit language URLs. Only public interface catalogs and static assets may be cached for offline use.

Portable catalog tooling (no platform gettext executable required):

```sh
python -m pip install -r scripts/requirements-i18n.txt
python scripts/localization.py update
python scripts/localization.py check
python scripts/localization.py compile
```

`check` validates interpolation placeholders and writes missing-message coverage to `data/localization-coverage.json`. It does not claim that untranslated or fuzzy entries are complete. Compilation validates every catalog before writing any `.mo` files. Review translations in context, including plural forms and medical terminology; preserve existing human translations when filling gaps. No external translation service is part of the app runtime.

### Optional one-time translation drafts

After explicit approval to send fixed interface text to Google, a developer can run:

```sh
python scripts/draft_translations.py es --google-interface-text
# Or use `all` in place of `es` for the existing language catalog directories.
python scripts/localization.py check
python scripts/localization.py compile
```

This is a development-only step, never a runtime integration. It reads extracted English UI messages rather than the application database. Existing active translations are retained. Inactive fuzzy wording is preserved in translator comments and a local backup when replaced with a new draft. Generated translations carry a review comment; plural forms and care-related terminology need fluent-speaker review. The English (UK) catalog uses source fallback text where reviewed wording is missing.

Requests are throttled. A provider denial or rate limit stops additional requests; it does not switch providers, enable billing, or retry indefinitely. Successful draft responses are cached under the ignored `data` directory so a later explicitly started run can resume. Placeholder, count, and markup checks must pass before a locale's catalogs are written. Compiled catalogs remain entirely inside the app; Google is contacted again only when this development command is deliberately run for new or changed interface text.

### Offline interface catalogs

All active extracted interface messages now have catalog entries in the existing language choices. American English remains the source; saved catalogs supply the other languages. No translation request occurs when a page is viewed. Names, notes, medication names entered by users, and other household records are never translated or submitted to a provider.

The one-time draft pass used a local NLLB model after Google rate-limited the approved attempt. Google produced no saved translations. The development model was `OpenNMT/nllb-200-3.3B-ct2-int8`, pinned to revision `28d998cc8548ad62f4f98cf8860928c3af99b97b`; its model SHA-256 was verified as `b7540c4e19aa2a5079c89241ffccb49711705ca8b1d255cea00c3216dc7d5165`. The model's CC-BY-NC-4.0 license applies to those development weights. Neither weights nor model dependencies are included in the application or repository.

Contextual corrections are recorded in `scripts/translation_overrides.json`. Review covered care terminology, calendar appointments, stock units, plural forms, destructive actions, selected permission explanations, Chinese script variants, and reverse-translation diagnostics. Existing active app translations and established Django translations for shared controls were preserved. Draft comments intentionally do not claim professional translation: fluent speakers should still review tone, regional wording, and less common messages before a public multilingual release. Reverse translation is a diagnostic, not proof of linguistic accuracy.

For future local drafting, use an isolated Python 3.12 development environment with `polib==1.2.0`, `ctranslate2==4.6.2`, and `tokenizers==0.22.2`, plus a compatible local CUDA runtime for this GPU-based tool. A model directory must contain `model.bin`, `config.json`, `shared_vocabulary.json`, and `tokenizer.json`. No model downloads are performed by the script.

```sh
python scripts/localization.py update
python scripts/localization.py export
# Run with the separate development environment, never the app runtime:
python scripts/local_translation.py draft es --model /path/to/local/model
python scripts/local_translation.py check es
# Review the drafts and add contextual corrections before applying:
python scripts/local_translation.py apply es
python scripts/localization.py compile
python scripts/test_local_translation.py
```

Use `all` in place of `es` to process existing non-English locales. Draft caches, diagnostic reports, and original catalogs are kept in the ignored `data` directory. `check` does not change catalogs; `apply` validates a complete locale before saving it. It preserves active translations, including earlier reviewed drafts, so later wording corrections should edit the catalog directly. The independent `localization.py check` reports extraction coverage and validates both named-percent and brace placeholders. Restart a long-running server after recompiling catalogs to clear its translation cache.

## Approved partial-issue follow-up

- Offline logging now includes custom activities and persistent device timers. Enable offline logging while connected, refresh activities after changing activity types, then start/pause/resume/stop and review entries before syncing. Timers remain on that device; they are not live shared timers. Pending entries are bound to their original account and permissions are checked again on sync. Offline appointments, attachments, and edits to server history remain outside this scope.
- Current timestamps retain their exact instant. A manually entered time that occurs twice during a daylight-saving transition asks for the first or second occurrence, showing the timezone offsets. A skipped time produces a validation error. Durations use elapsed time across transitions.
- Growth reports keep the WHO median by default. Show percentiles adds the 3rd, 15th, 85th, and 97th curves, controlled by the existing boys/girls checkboxes and display units. BMI uses WHO daily expanded reference tables; source links are in `reports/data/README.md`.
- Feeding includes Tube. Children born before their due date show gestational age at birth alongside actual/corrected age. No medical interpretation or treatment recommendation is inferred from these values.
- Activity types offers an editable Potty attempt preset with pee/poop and success fields. It uses custom-activity date/time and notes, and never consumes diaper inventory.
- Supported admin entry lists delete selected records in confirmed batches of 100, with progress, interruption/resume, repeat-request protection, and fresh permission checks. Child/type deletion retains Django's original confirmation. Jobs expire after one day.
- New child photos are validated, oriented, resized to a maximum 1600 pixels, and re-encoded as JPEG without embedded metadata. Limits are 20 MB and 40 megapixels. Convert HEIC to JPEG before uploading; existing stored files are not rewritten automatically.
- See [Updating this installation](../setup/updating.md) for the manually invoked preflight/apply helper, verified SQLite/media/source backups, asset building, migrations, and recovery instructions. It never schedules updates or changes Git branches.

Validation: the full application suite passed (767 tests), followed by targeted checks for permission revocation and CSRF. Eleven JavaScript tests passed. Isolated browser checks covered offline reload/pause/resume/custom-activity synchronization, batch deletion, repeated-time selection, and percentile visibility. These checks do not replace testing physical mobile devices or external storage providers.

## Nursing with a supplemental bottle

Edit the nursing entry and turn on **Add a top-up bottle**. Choose the bottle's date and time, milk type, and amount. A mixed bottle can include a second milk type and amount. The bottle cannot precede the end of nursing. Amounts use the entry unit selected on the form.

This remains one feeding. The original nursing start/end, duration, interval, and last-feeding clock do not change. The bottle appears separately at its actual time on the timeline, with an edit link to the same feeding. Its measured volume contributes to that day's totals, including when the bottle is after midnight. The app does not estimate unmeasured breast milk. To remove the linked bottle, turn off the option and save. Existing separate entries are not automatically linked or merged.

The API exposes optional `top_up_at`, `top_up_type`, `top_up_amount`, `top_up_secondary_type`, and `top_up_secondary_amount` fields on a feeding. API quantities follow the existing canonical mL convention. Older clients that omit these fields preserve an existing linked bottle. Explicitly clear all five fields to remove one through the API.

## Feeding Amounts grouping

In **Reports → Feeding Amounts**, **Group by** offers **Milk type** (default) and **Feeding session**. Milk type compares daily milk totals. Feeding session divides each day's bar into the feedings recorded that day; hover over a segment for its milk components, times, and combined volume. A mixed bottle remains one session segment. Switching grouping does not change the total volume. A linked bottle across midnight contributes to its actual day without incrementing the nursing-session count.

## Installation and integration follow-up

- Runtime Python versions are locked with hashes; see [Updating Baby Buddy](../setup/updating.md).
- Device developers can use the documented [connection QR format](../development/device-qr.md).
- Apps mounted under a path such as `/babybuddy/` now use that path for installation, shortcuts, and offline logging; see [subdirectory hosting](../setup/subdirectory.md). Reinstall an older app icon after changing its address, after syncing any pending offline entries.

## Verified open-issue follow-up completion record

These four fixes are completed locally and are excluded from the remaining-issues list. This does not change upstream GitHub ticket status.

| Issue                                                                                   | Local resolution                                                                                                                                               |
| --------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [#1013 — Supplemental feeding](https://github.com/babybuddy/babybuddy/issues/1013)      | Optional linked top-up bottle within one nursing entry, with its own time, milk types, and amounts. Nursing timing and feeding count remain unchanged.         |
| [#827 — Feeding Amounts by session](https://github.com/babybuddy/babybuddy/issues/827)  | Group by milk type or feeding session; each session's hover shows its components and total. Daily bars have explicit widths, including a single-day selection. |
| [#807 — Dependency locking](https://github.com/babybuddy/babybuddy/issues/807)          | Exact runtime versions and SHA-256 hashes in requirements.lock, checked by CI and the update script. The lock is included with this feature batch.             |
| [#674 — Connection QR documentation](https://github.com/babybuddy/babybuddy/issues/674) | Documents payload, token authentication, ingress cookies, permissions, and revocation in development/device-qr.md.                                             |

## Automatic offline synchronization and recent history

Enable **Settings → Offline access → Enable on this device** once while connected on each private device. This requires HTTPS (localhost also works for development); a phone opening an ordinary HTTP LAN address cannot install the offline service worker.

Entries entered through the offline log are first saved in the device's browser database. The app attempts synchronization immediately after saving, every five minutes while a page is visible, and when connectivity returns or the app is reopened or brought to the foreground. These checks also run on normal authenticated pages after the device is enabled. If the browser still considers itself online while the server is down, the periodic check retries without needing a new connection event. There is also a **Sync now** button in Settings.

The same check refreshes the child/activity choices and a read-only snapshot of the most recent 200 entries from the past seven days. The offline log shows the snapshot's update time. Automatic refresh does not reset an entry being typed; reopen the screen or use **Refresh activities** to load changed form choices. Only records allowed by the current account's view permissions and child restrictions are cached. Shared pumping records follow the account's pumping permission.

A pending entry stays on the device until the server acknowledges it. Retries retain the same identifier, so an interrupted response does not create a second entry or deduct inventory twice. Rejected entries remain available for correction. Login must be renewed if the session expires, and the original account must be used. Browser/device storage is not a backup: clearing it before synchronization discards pending entries. **Clear this device** removes the cached data and queue.

Phones may suspend background or closed apps, so there is no promise of scheduled sync while the app is closed. Reopening it checks again. Supported normal new-entry forms now save their submitted fields to the device queue before synchronizing when offline access is enabled. If a regular entry page cannot load, navigation opens the saved Add entry screen with the matching activity and child. Full authenticated pages are not cached. The saved screen offers the existing basic activity fields; advanced fields remain available when the regular form was opened while connected. Offline appointments, attachments, editing server records, and the complete dashboard remain separate work.

Validation: 781 application tests and 18 JavaScript tests passed. Phone-sized Chrome checks covered disconnected saves, a five-minute retry without an online event, refreshed history, and synchronization from the regular dashboard after closing the offline screen. Physical-device testing remains outstanding.

## One Add entry flow and device controls

The separate Offline log navigation item has been removed. **Settings → Offline access** contains **Enable on this device**, **Sync now**, and **Clear this device**. A small pending-entry count appears in the normal navigation when the current account has unsynced entries; clicking it opens the queue on **Add entry**. The older `/offline/` bookmark still opens this same Add entry screen.

With device access enabled, regular supported new-entry forms save their fields locally before sending them to the server. Without device setup, normal connected form submissions continue to work. This preserves tags, mixed feeding and top-up amounts, multi-food meals, units, dates, and timer context. Form replay uses the same Django forms and permission checks as regular entry creation, with an idempotency receipt around the save. Existing-record edits, appointments, attachments, and account/settings changes are not intercepted.

Server validation errors stay with the pending entry. Correct them on the current form or follow **Correct entry** from the queue after reconnecting. Original values are restored, and overlap confirmation remains available. CSRF tokens are fetched fresh for synchronization and excluded from stored form data. The original timezone accompanies an entry so later profile or device timezone changes cannot shift its time silently.

Validation: 787 application tests passed. Browser checks cover Settings setup, saving a regular form after disconnecting, matching activity/child selection on offline navigation, the pending indicator, synchronization exactly once, and reopening/correcting an overlapping queued entry. Physical-device testing remains outstanding.

## Birth-time precision and guided imports (#924, #123)

Birth time now accepts and displays seconds in both 12-hour and 24-hour preferences. Explicit `:00` can replace existing seconds; minute-only submissions from older clients preserve stored precision. Other care-entry clocks remain minute-only.

The account menu's **Import data** opens a regular-app CSV workflow for staff with the appropriate add permissions. It provides per-type templates and accepted values, explicit child/unit selection, row validation, preview, and confirmation. All rows are revalidated and saved atomically; retries and repeat uploads of the same file/options do not duplicate records. Permission and child access are checked again at confirmation. Historical diaper imports do not charge current stock. See [Import/Export](../import-export.md) for supported scope and limits.

These two tickets are implemented locally and removed from the deferred list. Validation: 805 application tests and 19 JavaScript tests passed, with isolated Chrome upload/preview/confirm and birth-time save/reload checks. Upstream GitHub tickets were not changed.

## Twins feedback follow-up (#952), September 23

See the [detailed assessment](feedback-952.md). Timer restarts now require
confirmation bound to the account and the timer's current state. Repeated,
stale, or expired confirmations do not reset it. Missing timer pages/actions
return a friendly message. Dashboard/list timers show elapsed time, activity
labels replace unnamed IDs, and child context stays visible.

Validation summaries focus on load, preserve entered values, link to invalid
fields, and reveal collapsed optional sections. Child choices wrap their
avatar/name together, card headings look clickable, and a diaper icon replaces
the trash-can glyph for logging care. German diaper/save/elapsed-time wording
was corrected, including an erroneous years suffix.

Timer names on entry forms (#862/#854) are now verified for feeding, sleep,
pumping, tummy time, and bath time. Pumping needed a fieldset fix after child
selection was removed. These two tickets leave the remaining list. Physical
mobile checks remain separate. New installations can use the
[first-run guide](../setup/first-run.md) and the guided Windows launchers described below.

## Easy Windows setup and #952 verification tracking

New installations can extract this fork's ZIP and double-click **Setup Baby Buddy.cmd**,
then **Start Baby Buddy.cmd**. Setup detects Python 3.14 and offers Windows Package
Manager installation if needed, creates a private environment, installs hash-verified
runtime dependencies, migrates an empty database, and asks for a personal administrator
account. It bypasses the legacy default-account migration hook. Shipped assets avoid a
Node.js build for end users. Interrupted setup can resume; completed setup is unchanged
on repeat runs. Existing unrelated databases and custom configuration are refused.

Start verifies migrations and an active administrator before starting a loopback-only
server. It chooses a free port, waits for readiness, then opens the browser. No paid
hosting, public network exposure, or background Windows service is configured.

Device checks, native-speaker German review, and a clean-machine prerequisite bootstrap
check are under **Untested**. All four design decisions are settled: one-card timeline
sessions were implemented; manual overlap correction, confirmation-only timer restarts,
and the Baby Buddy name/logo were retained by user choice. #952 moves from partial
to awaiting verification: 0 partial tickets and 22 awaiting verification, with 25
remaining tickets in total.

Validation: 13 installer safety tests passed, including existing-data refusal,
interrupted setup, repeat runs, missing-database protection, simultaneous setup,
and occupied ports. An isolated Windows installation in a folder containing
spaces created a fresh virtual environment, installed locked dependencies,
applied migrations, created exactly one administrator with no default account,
and passed login, empty-household dashboard, startup, and CSS/JavaScript/chart
asset checks (including gzip). The test server was stopped afterward; the
existing household server and database were not changed. Windows launcher
prerequisite checks passed. Automatic Python installation still requires a
clean-machine test.

## One timeline card per session

Feeding, sleep, tummy time, bath time, pumping, and custom activities now show
one card with their start/end range and duration, ordered by start time. Notes,
tags, food details, feeding intervals, and linked top-up bottle details remain
on that card. An overnight session appears once in an all-dates or multi-day
view and also matches either day's filter; long sessions match intervening days.
The complete original range stays visible, with an end date when it crosses midnight
and timezone abbreviations when the clocks change.

Active timers show **In progress** or **Paused**, with elapsed time excluding
pauses. They require permission to view both timers and the activity, and respect
child access. Saving a timer-backed entry replaces the timer with the completed
entry. An entry recorded without duration is not labeled as ongoing.

Validation: 85 focused timeline/integration/permission/query tests passed; all
20 timeline tests passed again after the final elapsed-time formatting change.
Browser checks verified a single overnight card, its range and duration, active
status, comparison panels, and a 390px layout without horizontal overflow.
Translation compilation reports zero missing active messages and valid placeholders.
