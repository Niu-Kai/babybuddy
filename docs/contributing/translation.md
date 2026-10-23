# Translation

## POEditor

Baby Buddy uses [POEditor](https://poeditor.com/) for translation contributions.
Interested contributors can [join translation of Baby Buddy](https://poeditor.com/join/project/QwQqrpTIzn)
for access to a simple, web-based frontend for adding/editing translation files
to the project.

## Manual

Baby Buddy has support for translation/localization. A manual translation
process will look something like this:

1. Set up a development environment (see [Development environment](development-environment.md)).

2. Run `gulp makemessages -l xx` where `xx` is a specific locale code in the
   [ISO 639-1 format](https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes) (e.g.,
   "it" for Italian or "es" for Spanish). This creates a new translation file at
   `locale/xx/LC_MESSAGES/django.po`, or updates one if it exists.

3. Open the created/updated `django.po` file and update the header template
   with license and contact info.

4. Start translating! Each translatable string will have a `msgid` value with
   the string in English and a corresponding (empty) `msgstr` value where a
   translated string can be filled in. Pluralized messages have several
   `msgstr[n]` entries; see [Plural forms](#plural-forms) below.

5. Once all strings have been translated, run `gulp compilemessages -l xx` to
   compile an optimized translation file (`locale/xx/LC_MESSAGES/django.mo`).

6. To expose the new translation as a user setting, add the locale code to the
   `LANGUAGES` array in the base settings file (`babybuddy/settings/base.py`).

7. Check if Plotly offers a translation (in `node_modules/plotly.js/dist/`) for
   the language. If it does:
   1. Add the Plotly translation file path to [`gulpfile.config.js`](https://github.com/babybuddy/babybuddy/tree/master/gulpfile.config.js)
      in `scriptsConfig.graph`.

   2. Build, collect, and commit the `/static` folder (see [`gulp updatestatic`](gulp-command-reference.md#updatestatic)).

8. Run the development server, log in, and update the user language to test the
   newly translated strings.

Once the translation is complete, commit the new files and changes to a fork
and [create a pull request](pull-requests.md) for review.

For more information on the Django translation process, see Django's
documentation section: [Translation](https://docs.djangoproject.com/en/5.0/topics/i18n/translation/).

## Plural forms

A pluralized message has `msgid` and `msgid_plural` source strings, followed by
numbered translations (`msgstr[0]`, `msgstr[1]`, and so on). Fill every numbered
form declared by the catalog's `Plural-Forms: nplurals=N; ...` header. The count
depends on the target language; it does not have to match English's two forms.

Keep named placeholders such as `%(count)s` in each translated form. Translate
the complete phrase rather than appending a suffix such as `%(plural)s`, which
cannot express the plural rules of many languages. Empty forms fall back to
English for the counts that use those forms. Review examples with different
counts in the interface after compiling the catalog.
