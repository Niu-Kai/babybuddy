# Feeding reminders and preparation before birth

## Notes in entry lists

Notes have their own column alongside each entry. Use **Columns** to show or
hide it, like Tags or Recorded by. Existing visibility preferences still apply.
Long notes wrap within the cell and line breaks are preserved. Linked top-up
bottle details remain attached to their feeding session.

## Feeding reminders

Open **Activities → Feedings → Reminders**, or use **Feeding reminder** on a
child's dashboard card. Reminders are personal to each caregiver and are off
until enabled. Each child's plan is separate. Entries by every caregiver
contribute to that child's clock.

Choose the milk type and either **Age-based suggestion** or **Custom interval**.
The age suggestions use editable starting points within general CDC ranges:

| Age and milk                                    | App's suggested reminder interval |
| ----------------------------------------------- | --------------------------------- |
| First 7 days, any milk type                     | 150 minutes                       |
| 7–27 days, breast milk or mixed                 | 150 minutes                       |
| 28 days to under 6 months, breast milk or mixed | 180 minutes                       |
| 7 days to under 6 months, formula               | 210 minutes                       |
| 6 months or older                               | Choose a custom interval          |

These exact intervals and age boundaries are app design choices, not CDC
prescriptions. The underlying guidance describes newborn feeding about 8–12
times daily, breast-milk feeding commonly every 2–4 hours during the first
weeks and months, and formula feeding commonly every 3–4 hours after the first
days. Follow hunger cues and the child's clinician's plan. When a recorded due
date indicates birth before 37 weeks, automatic suggestions are unavailable;
use the clinician's interval. A future birth date never triggers an alarm.
If an enabled age-based plan reaches an age needing a custom interval, the app
shows **Review feeding reminder** rather than silently hiding the plan.

The next reminder is measured from the latest milk feeding's **start**, or the
start of a more recent linked top-up bottle. A solid-food-only entry does not
reset it. No first milk feeding means no invented due time. An active feeding
timer suppresses the alarm. **Remind in 10 minutes** snoozes that reminder;
a later milk feeding starts a new clock. Reminder settings affect prompts,
not the child's saved feeding history.

**Enable sound & alerts on this device** enables device sound and requests
browser notification permission. Permission is requested only after that click.
**Mute this device** turns those device alerts off while retaining in-app prompts.
The browser must remain open and the device awake; closed browsers, sleeping
devices, system volume settings, or browser restrictions can prevent an alarm.
This is not a server push, phone alarm, or medical monitoring service. Duplicate
alerts are suppressed across tabs where browser storage/locks are available.
No email, SMS, paid service, or external account is required.

Sources: [CDC breastfeeding frequency](https://www.cdc.gov/infant-toddler-nutrition/breastfeeding/how-much-and-how-often.html)
and [CDC formula feeding frequency](https://www.cdc.gov/infant-toddler-nutrition/formula-feeding/how-much-and-how-often.html).

## Before birth

The **Before birth** navigation item works before any child has been created.
It is shared household information, controlled by its own model permissions.
Caregivers can view and update it; read-only users can view it. Delete actions
require separate permission. Child selection and child restrictions do not
convert this shared page into an individual child's record.

- **Contraction timer:** Start when a contraction begins and stop when it ends.
  Duration and start-to-start spacing are shown in minutes and seconds. The
  current timer is saved on the server, resumes after refresh, and is shared
  across devices. Only one contraction can run at once. The recent-hour
  summary includes count, average completed duration, and average start-to-start
  spacing; history shows the latest 50 records. A failed connection is shown
  explicitly and no successful save is claimed. Contractions are not added to
  a baby's care timeline.
- **Hospital bag:** A starter list groups documents, supplies for the parent and
  baby, support-person items, and tasks before leaving home. Check items off,
  add your own, or remove unneeded items with permission. Progress is shared
  and saved. Confirm what your hospital provides or requires.
- **Hospital & birth notes:** Save the due date, hospital, care-team contact,
  phone number, admission instructions, and birth preferences. These notes
  remain separate from a child's birth date and care entries.

Contraction timing alone does not diagnose labor or decide when to go to the
hospital. Follow the care team's instructions. The page links to
[ACOG's labor guidance](https://www.acog.org/womens-health/faqs/how-to-tell-when-labor-begins)
and [NHS hospital-bag suggestions](https://www.nhs.uk/best-start-in-life/pregnancy/preparing-for-labour-and-birth/hospital-bag-checklist/).
