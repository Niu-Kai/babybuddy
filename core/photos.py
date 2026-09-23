"""Normalize uploaded child photos before storing private media."""

from io import BytesIO
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.translation import gettext_lazy as _


def prepare_photo(upload):
    if not upload or getattr(upload, "_babybuddy_photo", False):
        return upload
    if upload.size > 20 * 1024 * 1024:
        raise ValidationError(_("Choose a photo smaller than 20 MB."))
    try:
        upload.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload) as source:
                if source.format not in {"JPEG", "PNG", "WEBP", "GIF"}:
                    raise ValidationError(
                        _(
                            "Choose a JPEG, PNG, WebP, or GIF photo. Convert HEIC photos to JPEG first."
                        )
                    )
                if source.width * source.height > 40_000_000:
                    raise ValidationError(
                        _("Choose a photo smaller than 40 megapixels.")
                    )
                source.seek(0)
                oriented = ImageOps.exif_transpose(source)
                oriented.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                # Paste into a new image: no EXIF, GPS, comments, or other metadata.
                clean = Image.new("RGB", oriented.size, "white")
                if "A" in oriented.getbands() or "transparency" in oriented.info:
                    rgba = oriented.convert("RGBA")
                    clean.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    clean.paste(oriented.convert("RGB"))
                output = BytesIO()
                clean.save(output, format="JPEG", quality=88, optimize=True)
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise ValidationError(
            _(
                "This photo could not be read. Choose a valid JPEG, PNG, WebP, or GIF photo."
            )
        )
    finally:
        upload.seek(0)
    result = SimpleUploadedFile(
        "child-photo.jpg", output.getvalue(), content_type="image/jpeg"
    )
    result._babybuddy_photo = True
    return result
