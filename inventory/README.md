# Inventory

All supplies belong to the household. Each item represents one product, size, stock unit, and expiration batch. Children can share the same diaper stock.

Logging a diaper change deducts exactly one diaper. Selection priority is the child's designated supply, then their selected diaper size, then an optional household-entered age range if no size is set. Set overrides under Manage children → Diaper supply & sizes. Selecting a supply also updates the child's diaper size; it overrides age ranges. Automatic deduction can be disabled per child.

Manufacturer diaper sizes use package weight ranges, not standard ages. Age bounds are inclusive in completed months and are only used when entered by the household. If several supplies match, no stock is deducted until a caregiver chooses a supply. Unavailable or empty designated supplies never silently switch to another item.

Editing an entry does not deduct twice. Reassigning it to another child returns the original diaper and charges the new matching supply. Deleting a single entry restores its original stock; deleting a child's entire history does not replenish used diapers. Historical entries without linked stock usage are not charged on edit.

Counts change only through logged diaper usage or explicit Use stock, Restock, and Correct count actions. Age changes and estimated daily usage never change quantity. Other activity entries do not yet deduct supplies automatically.

Restock reminders are automatic when the estimated supply reaches 14 days (two weeks) or less. There are no manual threshold, usage-rate, or notice-period settings. Diaper forecasts use each currently assigned child's recent diaper entries, including entries logged before inventory was set up, and combine the rates for children sharing stock. Rates follow the child when their supply/size changes. Each entry counts as one diaper even when both wet and solid.

The averaging window is the last 14 completed local calendar days. Today and future entries are excluded; when logging started more recently, the denominator runs from the first logged day to yesterday, including intervening zero-use days. Each assigned child needs at least one completed day with logs; incomplete shared-child history yields no estimate rather than understating use. Estimates reflect recorded data, so missing logs can understate actual usage. Non-diaper supplies use explicit Use stock history; restocks and count corrections do not count as usage. Diaper packs need individual-diaper units before usage can be forecast. Forecasts are computed once per request, not persisted or used to change quantities.

Cards show estimated days left and average daily use. Shopping suggestions show a 30-day supply at that rate. Without recent usage, the app reports that it cannot estimate; out-of-stock and expiration reminders still work. Expiration reminders also start 14 days beforehand. Reminders appear automatically in the app's navigation, dashboard, and shopping list; they are not background push/email notifications. Supplies marked Next size / later, Outgrown, or Archived do not trigger restock reminders. Batches with different expiration dates should be separate items; expired batches cannot be restocked. Stock units cannot be changed after creation.

Stock access requires inventory permissions. Editing child supply preferences also requires child-management and size-profile permissions. Removing a child leaves household inventory intact.

Apply `python manage.py migrate` after updating. Run `python manage.py test inventory --settings=babybuddy.settings.test`.
