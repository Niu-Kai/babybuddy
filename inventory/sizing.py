"""US manufacturer diaper guides, checked September 21, 2026.

These are weight guides, not age standards. Specialty products and revised
packages may differ; custom package sizes remain supported.

https://www.pampers.com/en-us/baby/diapering/article/diaper-size-and-weight-chart
https://www.huggies.com/en-us/resources/parenting/everyday-diaper-tips/diaper-size-calculator
"""

SIZE_ORDER = ("preemie", "newborn", "1", "2", "3", "4", "5", "6", "7", "8")
GUIDES = {
    "Pampers": (
        "Under 6 lbs",
        "Under 10 lbs",
        "8–14 lbs",
        "10–22 lbs",
        "13–26 lbs",
        "15–34 lbs",
        "20–37 lbs",
        "23–44 lbs",
        "26–50 lbs",
        "30+ lbs",
    ),
    "Huggies": (
        "Up to 6 lbs",
        "Up to 10 lbs",
        "8–14 lbs",
        "12–18 lbs",
        "16–28 lbs",
        "22–37 lbs",
        "Over 27 lbs",
        "Over 35 lbs",
        "Over 41 lbs",
        "Over 46 lbs",
    ),
}
DIAPER_SIZES = []
ALIASES = {}
for brand, ranges in GUIDES.items():
    for code, weight in zip(SIZE_ORDER, ranges):
        name = code.title() if code in {"preemie", "newborn"} else code
        label = f"{weight} · {brand} {name}"
        DIAPER_SIZES.append(label)
        for alias in (label, f"{brand} {name}", f"{brand} Size {name}"):
            ALIASES[alias.casefold()] = (brand, code)


def diaper_size(value):
    value = value.casefold().strip()
    if value in ALIASES:
        return ALIASES[value]
    code = value.removeprefix("size ")
    code = {"nb": "newborn", "n": "newborn", "p": "preemie"}.get(code, code)
    return (None, code) if code in SIZE_ORDER else (None, value)


def same_diaper_size(first, second):
    brand_a, code_a = diaper_size(first)
    brand_b, code_b = diaper_size(second)
    # Preserve old unbranded records, without equating two explicit brands.
    return code_a == code_b and (not brand_a or not brand_b or brand_a == brand_b)


def diaper_fit(stock_size, current_size):
    if same_diaper_size(stock_size, current_size):
        return "current"
    brand_a, code_a = diaper_size(stock_size)
    brand_b, code_b = diaper_size(current_size)
    if brand_a and brand_b and brand_a != brand_b:
        return "review"
    if code_a in SIZE_ORDER and code_b in SIZE_ORDER:
        return (
            "next"
            if SIZE_ORDER.index(code_a) > SIZE_ORDER.index(code_b)
            else "outgrown"
        )
    return "review"
