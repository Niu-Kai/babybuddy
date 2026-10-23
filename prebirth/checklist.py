"""Optional starter list, adapted from NHS hospital-bag guidance; customize locally."""

from django.utils.translation import gettext_noop

STARTER_ITEMS = [
    ("documents", gettext_noop("ID, insurance card, and hospital paperwork")),
    ("documents", gettext_noop("Birth preferences and care-team contact details")),
    ("documents", gettext_noop("Phone and long charging cable")),
    ("parent", gettext_noop("Comfortable clothes, robe, and non-slip slippers")),
    ("parent", gettext_noop("Toiletries, glasses, and hair ties")),
    ("parent", gettext_noop("Maternity pads and comfortable underwear")),
    ("parent", gettext_noop("Nursing bra and breast pads, if wanted")),
    ("parent", gettext_noop("Regular medications and an up-to-date medication list")),
    ("parent", gettext_noop("Water bottle and snacks approved by your care team")),
    ("baby", gettext_noop("Going-home clothes in two sizes")),
    (
        "baby",
        gettext_noop("Blanket, diapers, and wipes if your hospital requests them"),
    ),
    ("baby", gettext_noop("Properly installed rear-facing car seat for the trip home")),
    ("support", gettext_noop("Change of clothes and toiletries")),
    ("support", gettext_noop("Snacks, water, and charger")),
    ("home", gettext_noop("Confirm the hospital entrance, parking, and route")),
    ("home", gettext_noop("Arrange care for other children and pets")),
    ("home", gettext_noop("Keep hospital bags and car-seat instructions ready")),
]
