"""Bounded CSV imports using the same validation as care-entry forms."""

import csv
import hashlib
import io
import json
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, IntegrityError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View

from babybuddy.mixins import LoginRequiredMixin, StaffOnlyMixin
from babybuddy.models import ImportBatch
from core import forms as entry_forms, models
from core.access import scoped, restricted
from core.units import SPECS

MAX_ROWS = 500
MAX_BYTES = 2 * 1024 * 1024
FORM_CLASSES = (
    entry_forms.ChildForm,
    entry_forms.FeedingForm,
    entry_forms.PumpingForm,
    entry_forms.DiaperChangeForm,
    entry_forms.SleepForm,
    entry_forms.TummyTimeForm,
    entry_forms.BathTimeForm,
    entry_forms.FoodForm,
    entry_forms.MedicationForm,
    entry_forms.RefluxForm,
    entry_forms.NoteForm,
    entry_forms.WeightForm,
    entry_forms.HeightForm,
    entry_forms.HeadCircumferenceForm,
    entry_forms.TemperatureForm,
    entry_forms.TagAdminForm,
)
REGISTRY = {form._meta.model._meta.model_name: form for form in FORM_CLASSES}
# Export metadata is never used to overwrite IDs, ownership, or relationships.
IGNORED = {
    "id",
    "child",
    "child_id",
    "child_first_name",
    "child_last_name",
    "created_by",
    "created_by_id",
    "duration",
    "entry_unit",
}
EXCLUDED = {"child", "picture", "timer", "allow_overlap", "entry_unit"}


def allowed_types(user):
    return {
        key: cls
        for key, cls in REGISTRY.items()
        if user.has_perm("core.add_" + key)
        and not (key == "child" and restricted(user))
    }


def entry_form(kind, user, data=None):
    # Binding an empty mapping retains legacy start/end fields instead of the
    # interactive split date/time controls. Import fields do not follow hide prefs.
    return REGISTRY[kind](user=user, data={} if data is None else data)


def columns(kind, user):
    form = entry_form(kind, user)
    return {
        name: form.fields[name]
        for name in form._meta.fields
        if name in form.fields and name not in EXCLUDED
    }


class UploadForm(forms.Form):
    kind = forms.ChoiceField(label=_("Entry type"))
    child = forms.ModelChoiceField(
        queryset=models.Child.objects.none(), required=False, label=_("Child")
    )
    unit = forms.ChoiceField(required=False, label=_("Units in file"))
    file = forms.FileField(
        label=_("CSV file"),
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,text/csv"}),
    )

    def __init__(self, user, *args, kind=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        choices = allowed_types(user)
        self.fields["kind"].choices = [
            (key, cls._meta.model._meta.verbose_name) for key, cls in choices.items()
        ]
        self.selected_kind = kind if kind in choices else next(iter(choices), None)
        self.initial["kind"] = self.selected_kind
        self.fields["child"].queryset = scoped(models.Child.objects.all(), user)
        needs_child = (
            self.selected_kind and "child" in REGISTRY[self.selected_kind]._meta.fields
        )
        if not needs_child:
            self.fields["child"].widget = forms.HiddenInput()
        else:
            self.fields["child"].required = True
        spec = SPECS.get(self.selected_kind)
        self.fields["unit"].choices = list(spec[3]) if spec else [("", "")]
        if spec:
            self.fields["unit"].required = True
            self.initial["unit"] = spec[1]
        else:
            self.fields["unit"].widget = forms.HiddenInput()

    def clean_file(self):
        file = self.cleaned_data["file"]
        if file.size > MAX_BYTES or not file.name.lower().endswith(".csv"):
            raise forms.ValidationError(_("Choose a CSV file up to 2 MB."))
        return file


def read_rows(file, names):
    try:
        text = file.read(MAX_BYTES + 1).decode("utf-8-sig")
        if len(text.encode("utf-8")) > MAX_BYTES or "\x00" in text:
            raise ValueError()
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = reader.fieldnames or []
        if not headers or len(headers) > 80 or len(set(headers)) != len(headers):
            raise forms.ValidationError(
                _("Use unique column names from the CSV template.")
            )
        unknown = set(headers) - set(names) - IGNORED
        if unknown:
            raise forms.ValidationError(
                _("Unknown columns: %(columns)s")
                % {"columns": ", ".join(sorted(unknown))}
            )
        rows = []
        seen = set()
        for number, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise forms.ValidationError(
                    _("Row %(row)s has the wrong number of columns.") % {"row": number}
                )
            if not any(value.strip() for value in row.values()):
                continue
            row = {key: value for key, value in row.items() if key in names}
            fingerprint = json.dumps(row, sort_keys=True)
            if fingerprint in seen:
                raise forms.ValidationError(
                    _("Row %(row)s repeats an earlier row.") % {"row": number}
                )
            seen.add(fingerprint)
            rows.append({"number": number, "values": row})
            if len(rows) > MAX_ROWS:
                raise forms.ValidationError(_("Import up to 500 rows at a time."))
        if not rows:
            raise forms.ValidationError(_("The file has no entries."))
        return rows
    except (UnicodeError, csv.Error, ValueError) as error:
        raise forms.ValidationError(
            _("Use a UTF-8 CSV file with a header row.")
        ) from error


def validate_options(user, options):
    kind = options["kind"]
    if kind not in allowed_types(user):
        raise PermissionDenied()
    if "child" in REGISTRY[kind]._meta.fields:
        get_object_or_404(scoped(models.Child.objects.all(), user), pk=options["child"])


def process_rows(user, options, rows, commit=False):
    validate_options(user, options)
    errors = []
    with transaction.atomic(), timezone.override(options["timezone"]):
        for row in rows:
            data = dict(row["values"])
            kind = options["kind"]
            fields = columns(kind, user)
            if "child" in REGISTRY[kind]._meta.fields:
                data["child"] = options["child"]
            if kind in SPECS:
                data["entry_unit"] = options["unit"]
            for name, field in fields.items():
                if isinstance(field, forms.BooleanField) and name in data:
                    value = data[name].strip().lower()
                    if value not in {"", "true", "false", "1", "0", "yes", "no"}:
                        errors.append(
                            {
                                "row": row["number"],
                                "field": name,
                                "message": str(_("Use true or false.")),
                            }
                        )
                    data[name] = value in {"true", "1", "yes"}
            form = entry_form(kind, user, data)
            if not form.is_valid():
                for name, problems in form.errors.items():
                    errors.append(
                        {
                            "row": row["number"],
                            "field": name,
                            "message": " ".join(problems),
                        }
                    )
                continue
            try:
                with transaction.atomic():
                    form.instance._historical_import = True
                    form.save()
            except ValidationError as error:
                errors.append(
                    {
                        "row": row["number"],
                        "field": "",
                        "message": "; ".join(error.messages),
                    }
                )
            except IntegrityError:
                errors.append(
                    {
                        "row": row["number"],
                        "field": "",
                        "message": str(
                            _("This entry conflicts with an existing record.")
                        ),
                    }
                )
        if errors or not commit:
            transaction.set_rollback(True)
    return errors


def guide(kind, user):
    result = []
    for name, field in columns(kind, user).items():
        if isinstance(field, forms.ChoiceField):
            fmt = "; ".join(
                f"{key} = {label}" for key, label in field.choices if key != ""
            )
        elif isinstance(field, forms.DateTimeField):
            fmt = "YYYY-MM-DD HH:MM:SS (2026-01-15 13:30:00); ISO 8601"
        elif isinstance(field, forms.DateField):
            fmt = "YYYY-MM-DD (2026-01-15)"
        elif isinstance(field, forms.TimeField):
            fmt = "HH:MM:SS" if name == "birth_time" else "HH:MM"
        elif isinstance(field, forms.BooleanField):
            fmt = "true / false"
        elif isinstance(
            field, (forms.FloatField, forms.IntegerField, forms.DecimalField)
        ):
            fmt = str(_("Number"))
        elif name == "tags":
            fmt = str(_("Tag names separated by commas"))
        else:
            fmt = str(_("Text"))
        result.append(
            {
                "name": name,
                "label": field.label,
                "required": field.required,
                "format": fmt,
            }
        )
    return result


class ImportData(LoginRequiredMixin, StaffOnlyMixin, View):
    template_name = "babybuddy/import.html"

    def page(self, request, form, **context):
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "guide": (
                    guide(form.selected_kind, request.user)
                    if form.selected_kind
                    else []
                ),
                "import_timezone": timezone.get_current_timezone_name(),
                "import_type": (
                    REGISTRY[form.selected_kind]._meta.model._meta.verbose_name
                    if form.selected_kind
                    else ""
                ),
                **context,
            },
        )

    def get(self, request):
        form = UploadForm(request.user, kind=request.GET.get("kind"))
        if not form.selected_kind:
            raise PermissionDenied()
        if request.GET.get("template") == "1":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = (
                f'attachment; filename="{form.selected_kind}-template.csv"'
            )
            csv.writer(response).writerow(columns(form.selected_kind, request.user))
            return response
        return self.page(request, form)

    def post(self, request):
        if request.POST.get("confirm"):
            return self.confirm(request)
        form = UploadForm(
            request.user, request.POST, request.FILES, kind=request.POST.get("kind")
        )
        if not form.is_valid():
            return self.page(request, form)
        options = {
            "kind": form.cleaned_data["kind"],
            "child": getattr(form.cleaned_data["child"], "pk", None),
            "unit": form.cleaned_data["unit"],
            "timezone": timezone.get_current_timezone_name(),
        }
        try:
            rows = read_rows(
                form.cleaned_data["file"], columns(options["kind"], request.user)
            )
        except forms.ValidationError as error:
            form.add_error("file", error)
            return self.page(request, form)
        digest = hashlib.sha256(
            json.dumps([options, rows], sort_keys=True).encode()
        ).hexdigest()
        completed = ImportBatch.objects.filter(
            user=request.user, digest=digest, completed_at__isnull=False
        ).first()
        if completed:
            return self.page(request, form, batch=completed)
        errors = process_rows(request.user, options, rows)
        if errors:
            return self.page(request, form, row_errors=errors)
        # Retain completed digests for duplicate protection, expire private drafts.
        ImportBatch.objects.filter(
            user=request.user,
            completed_at=None,
            created_at__lt=timezone.now() - timedelta(hours=1),
        ).delete()
        batch, _created = ImportBatch.objects.get_or_create(
            user=request.user,
            digest=digest,
            defaults={"options": options, "rows": rows, "count": len(rows)},
        )
        return self.page(request, form, batch=batch, preview=rows[:20])

    def confirm(self, request):
        try:
            key = forms.UUIDField().clean(request.POST["confirm"])
        except forms.ValidationError:
            from django.http import Http404

            raise Http404()
        with transaction.atomic():
            batch = get_object_or_404(
                ImportBatch.objects.select_for_update(), pk=key, user=request.user
            )
            validate_options(request.user, batch.options)
            form = UploadForm(request.user, kind=batch.options["kind"])
            if batch.completed_at:
                messages.info(request, _("This file has already been imported."))
                return redirect("babybuddy:import")
            if batch.created_at < timezone.now() - timedelta(hours=1):
                messages.error(
                    request, _("The preview expired. Upload the file again.")
                )
                return redirect("babybuddy:import")
            # Claim the receipt with a write before saving rows (also on SQLite).
            claimed = ImportBatch.objects.filter(pk=batch.pk, completed_at=None).update(
                completed_at=timezone.now()
            )
            if not claimed:
                return redirect("babybuddy:import")
            errors = process_rows(request.user, batch.options, batch.rows, commit=True)
            if errors:
                transaction.set_rollback(True)
            else:
                batch.rows = []
                batch.save(update_fields=["rows"])
        if errors:
            return self.page(request, form, row_errors=errors)
        messages.success(
            request, _("Imported entries: %(count)s.") % {"count": batch.count}
        )
        return redirect("babybuddy:import")
