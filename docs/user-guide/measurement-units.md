# Measurement units and household views

Use the child button next to the account menu to choose one child, all children
in a combined view, or separate side-by-side panels. This selection follows you
between pages. Manage profiles under **My account → Manage children**.

Each caregiver can set **Preferred units** in **My profile & preferences**.
Choose liquid (mL or US fl oz), length (cm or in), weight (kg, lbs, or oz), and
temperature (°C or °F) independently. For example, use mL, cm, lbs, and °F together.
Changing a category resets its history-page display overrides for this session;
other categories keep their selections. Existing entries keep their original units.
An entry's **Entry unit** selector can override that preference. Changing an
explicit entry unit converts the value already in the field. **Convert display**
on a history page changes presentation only; it does not edit measurements.
Liquid ounces are US **fl oz**, while weight ounces are **oz**.

New entries with explicit units are stored in cm, kg, mL, or °C. The `entry_unit`
field remembers the original input unit; editing converts back to that unit.
Existing API numeric fields keep representing stored values. Clients that omit
unit metadata continue to produce legacy unitless records.

Older records have an empty `entry_unit`. Their values are never automatically
relabeled or converted by migrations. Edit a record and choose the unit that was
originally used to confirm it. A local demo-data normalization was performed only
for this workspace after its owner confirmed the entries are sample data; that
normalization is intentionally not part of a deployment migration.

Previous feeding is the start-to-start interval for the same child, including
across pagination and in combined household views.

The timeline shows all history by default. Choose **Day**, **Week**, **Month**,
or **Year**. The picker offers calendar days, Sunday–Saturday week ranges,
months with a year, or years to match. Its **Today** shortcut uses the current
date in your selected time zone; choose **Apply filters** to update the history.
The exact range appears above the history. **Previous period** and **Next period**
retain the activity filter and child view, and comparison panels use the same
range for every child. **Clear filters** restores all dates and all activities.
