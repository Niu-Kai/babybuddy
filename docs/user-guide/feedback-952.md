# Review of twins feedback (#952)

Source: [upstream issue #952](https://github.com/babybuddy/babybuddy/issues/952).
The user supplied the original post and detailed discussion comments on September
23, 2026. The earlier audit looked only at the opening post and incorrectly
left the details unavailable. No additional document is needed to assess these
supplied comments. This review uses that supplied discussion and local source;
it is not a fresh check of the live issue.

Status: **untested / awaiting verification**. Approved implementation is complete
and all four design decisions are settled. The implementation findings below do not claim
that every original scenario has been reproduced on a physical device.

| Area                          | Current coverage                                                                                                                              | Remaining work or verification                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Installation                  | Installation documentation and an update/backup script exist.                                                                                 | Double-click Windows Setup/Start launchers now handle Python detection/bootstrap, verified dependencies, migrations, personal account creation, and local browser launch. Uses included assets without Git or Node.js. Hosted deployment is separate; no paid service was introduced.                                                                                                                                                                          |
| Desktop design and navigation | Modern cards, dark mode, centered headings, rounded avatars, Reports navigation, child selector, and management under the account menu exist. | Card links are underlined, diaper icons are distinct from delete icons, and avatar/name choices wrap together. Browser checks at 390, 768, and 844 pixels found no page-level overflow in dashboard, feeding, and sleep reports. Physical landscape verification remains. Activity colors identify activities; they are not clinical status indicators. Settled by user choice: retain the Baby Buddy name and logo.                                           |
| Units and temperatures        | Explicit units, independent length/weight/liquid/temperature preferences, conversions, and decimal temperatures are implemented.              | Do not treat the unit system as an outstanding implementation gap in this ticket.                                                                                                                                                                                                                                                                                                                                                                              |
| Feeding                       | A unified Feeding workflow replaces the separate bottle menu; milk components, totals, and optional top-ups exist.                            | No further separate bottle workflow is implied.                                                                                                                                                                                                                                                                                                                                                                                                                |
| Dashboard                     | Child-specific care links pass child scope. Comparison layouts, adjustable panels, and rounded photos are implemented.                        | Verify link discoverability and scaling on the reporter's tablet/split-screen setup.                                                                                                                                                                                                                                                                                                                                                                           |
| Timeline and pumping          | Multi-day timelines and date/activity filters exist. Pumping is household-level.                                                              | One card per saved session now shows its time range and duration, with linked top-up details inside Feeding. Active/paused timers are visible with child and activity permissions. Household pumping remains separate from child comparison panels.                                                                                                                                                                                                            |
| Validation and errors         | Inline/form-level validation and overlap handling exist; pending offline errors can be corrected.                                             | Focused error summaries and links to invalid fields now preserve entered values and open collapsed field sections. Narrow-browser validation and draft retention passed. Deleted/stopped timer pages and stale actions return a friendly message. Physical browser-Back behavior still needs device testing. Settled by user choice: retain manual overlap correction, existing validation, and explicit confirmation. Automatic time changes are not planned. |
| Timers                        | Timers support child association, pause/resume, and elapsed-time displays.                                                                    | Restart requires signed confirmation and rejects stale, expired, cross-user, and repeated confirmations. Elapsed time and child context are visible; unnamed timers use activity labels instead of IDs. All five supported timed entry forms show the disabled timer name, including the repaired household pumping fieldset (#862/#854). Settled by user choice: keep restart confirmation without post-restart Undo.                                         |
| Export                        | User-facing exports and guided CSV imports are implemented.                                                                                   | No new export feature is required for this feedback.                                                                                                                                                                                                                                                                                                                                                                                                           |
| German wording                | Translated catalogs exist; Previous feeding is explicit.                                                                                      | Corrected Wet/Solid to Urin/Stuhlgang, Save to Speichern, and time/diaper interval wording. Fixed an elapsed-time translation that incorrectly appended years. Native-speaker review remains useful.                                                                                                                                                                                                                                                           |
| Mobile charts and timezones   | Charts were redesigned and user timezone preferences exist.                                                                                   | Physical Firefox Android, Safari iOS, and iPad split-screen readability need testing. Confirm newborn age and times across timezone/daylight-saving boundaries.                                                                                                                                                                                                                                                                                                |

## Validation and remaining work

The application suite passed 827 tests before the final pumping-fieldset fix;
110 timer/form tests then passed, including all five supported timed entry forms.
All 19 JavaScript tests passed. Browser checks covered restart/cancel, the named
feeding timer, linked and focused errors with preserved notes at 390px, selection
of a tag beyond the five recent choices, and dashboard/feeding/sleep-report
layout at 390px, 768px, and 844px. Chromium occasionally reported a skipped
cross-document view transition during rapid automated navigation; these checks
do not establish physical mobile browser behavior. Translation compilation
reported zero missing active messages and no placeholder errors.

## Settled design decision: overlap correction

The user chose to retain manual correction on September 23, 2026. Existing overlap
validation and explicit confirmation remain; caregivers edit incorrect times themselves.
No automatic time adjustment or suggested-correction workflow is planned.

## Settled design decision: timer restart

The user chose confirmation only on September 23, 2026. The existing confirmation
and stale/repeated-request protection remain. A post-restart Undo action is not planned.

## Settled design decision: branding

The user chose to retain the Baby Buddy name and logo on September 23, 2026.
No replacement branding is planned. All four design decisions are now settled;
the remaining work is verification listed below.

## Untested / awaiting review

Moved out of implementation work at the user's request:

- Physical Firefox Android, Safari iPhone, and iPad split-screen testing,
  including landscape, browser Back, touch tags, chart usability, and offline sync.
- Native-speaker review of German terminology and relative times.
- Python bootstrap on a clean Windows computer without Python installed.
  Fresh Python-environment installation on the development computer is a separate check.

## Easy local installation

The [Windows setup guide](../setup/first-run.md) now uses double-click Setup and
Start launchers. Setup resumes interruptions, refuses unrelated existing databases
and custom configurations, requires a personal administrator password, and never
creates the legacy default account. Startup checks the database and opens the
browser only after the local server responds. Shipped interface assets remove the
need for Node.js or Git. Public hosting and automatic Windows service installation
are outside this local-install workflow.

No paid hosting was introduced. The logo is unchanged. The original submitted
feedback is not reproduced in this repository; the table records the local
assessment and implementation outcomes.

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
