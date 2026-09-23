# Import/Export

Baby Buddy uses the [django-import-export application](https://django-import-export.readthedocs.io/)
to provide import and export functionality.

## Export

Export actions are accessible from Baby Buddy's "Database Admin" area (the
Django admin interface). For example, to export all diaper change entries from
Baby Buddy as an Excel file:

1. Log in as a user with "staff" access.

1. From the user menu, click "Database Admin" under the "Site" heading.

1. Click "Diaper Changes" in the list of data types.

1. Click the "Export" button above the filters list on the right side of the
   screen.

1. Select the "xlxs" format and click "Submit"

Note: any applied filters will also filter the exported entries. Alternatively,
on the Diaper Change list screen (step 3 above), it is possible to select one
or many individual records and select "Export selected Diaper Changes" from the
"Actions" list.

## Import

Open the account menu → **Import data** in the regular app. A staff account with permission to add the selected record type is required.

1. Choose an entry type and click **Choose**.
2. Select the child for the file (pumping and tag imports are shared; child imports create children).
3. Download the CSV template. **Columns and accepted values** lists required columns, date/time formats, and exact choice values such as feeding type and method.
4. Fill a UTF-8 CSV file with up to 500 rows / 2 MB. Import one entry type and child at a time. Choose the units used by the numeric columns; Baby Buddy exports store quantities in kg, cm, mL, and °C. The file's entry_unit metadata does not override this choice. Timestamps with no offset use the timezone displayed on the import page.
5. Upload and select **Preview import**. Fix any row errors and upload again. The preview validates every row, including interactions between rows; it does not save entries or emit webhooks.
6. Review the selected child, units, and preview, then select **Confirm import**. The file is checked again and saved as one transaction. A failure saves nothing. Previews expire after one hour.

Imports create new records, never update records by file ID. File IDs, recorded-by metadata, duration, and child columns are ignored; the explicitly selected child and current caregiver are used. Unsupported columns are reported rather than silently discarded. Tags use names, not database IDs. Photos, ZIP backups, custom-activity definitions, and live timers are not accepted by this CSV workflow. BMI is calculated from imported weight and height rather than imported manually. The older Database Admin import tools remain available for their existing formats.

Repeating confirmation or uploading the same file with the same options does not create duplicates. Imported diaper history does not deduct today's inventory. Completed receipts retain only a digest, options, and count; staged CSV rows are cleared after completion. Expired private drafts are removed on the user's next valid upload. This is an entry import, not a complete backup-restore tool.
