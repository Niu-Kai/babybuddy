# WHO BMI-for-age median reference

`who_bmi_medians.json` contains [age in days, median BMI (kg/m²)] pairs from the M column of the WHO expanded BMI-for-age z-score tables, retrieved September 21, 2026. Values are used without extrapolation. The discontinuity around age two reflects the source transition from length to standing height; chart lines are separated there.

- [WHO BMI-for-age standards](https://www.who.int/toolkits/child-growth-standards/standards/body-mass-index-for-age-bmi-for-age)
- [Boys source](https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/body-mass-index-for-age/expanded-tables/bfa-boys-zscore-expanded-tables.xlsx)
- [Girls source](https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/body-mass-index-for-age/expanded-tables/bfa-girls-zscore-expanded-tables.xlsx)

The other growth references use the existing WHO percentile tables in the application database. The comparison line is the median (50th percentile), not an individual target. Age uses the existing corrected birth date for premature children.
