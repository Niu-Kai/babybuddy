# Upstream review — September 23, 2026

Compared local branch `fix/local-bugs` at `089dc41` (including its existing
uncommitted work) with a fresh fetch of `babybuddy/babybuddy` master at
`573f008950ff02614c40fdf0c6c822ef50d90207`. The common ancestor is
`4839c2a69b48d98c99be78116b16fcd4221f5ebb`. Three commits are new upstream.

| Upstream commit                                                                                                                       | Local integration                                                                                                                                                                                                                                                                                                             |
| ------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [2400ccf — Corrected-age growth percentiles](https://github.com/babybuddy/babybuddy/commit/2400ccf978ec397b172774b2140b235f627723ac)  | Due date already exists in the child model, form, admin, API, and consolidated growth charts. Added optional due-date support and the early-measurement fix to the retained legacy height/weight graph functions, preserving optimized query reads. Imported upstream graph regressions.                                      |
| [3602c59 — Corrected-age labels and coverage](https://github.com/babybuddy/babybuddy/commit/3602c594a5ea56154394262b584b8be160aa9cd1) | Legacy date-axis charts label correction only with reference data. The consolidated age-axis chart correctly retains its corrected-age axis when references are hidden; its hover now explicitly says Corrected age too. Added regression coverage for both renderers. The existing translated Corrected age label is reused. |
| [573f008 — Security documentation cleanup](https://github.com/babybuddy/babybuddy/commit/573f008950ff02614c40fdf0c6c822ef50d90207)    | Removed the unused boilerplate instruction from SECURITY.md.                                                                                                                                                                                                                                                                  |

## Integration approach

These are source adaptations, not a Git merge or cherry-pick. The working tree
already contains substantial uncommitted feature work. Upstream migration
`0039_child_due_date` would conflict with our migration history: our
`0043_preferences_and_due_date` already adds the same database column. Do not
apply both migrations. No migration was added or modified during this review.

A future ancestry merge must resolve this duplicate schema operation explicitly
and preserve our redesigned reports. Git will continue to list these three
commits as unmerged until that separate history integration is performed.

## Verification

Regression checks cover due-date anchoring, unchanged actual measurement dates,
no correction for absent/equal/earlier due dates, measurements before the due
date, reference visibility, and truthful age labels. Tests use a separate test
database, not household records. See data/upstream-adaptation-tests.log for the
local test run.
