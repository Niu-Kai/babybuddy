document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("[data-timeline-filters]").forEach(function (form) {
    const period = form.elements.namedItem("period");
    const date = form.elements.namedItem("date");
    const picker = form.querySelector("[data-date-picker]");
    const summary = picker.querySelector("summary");
    const value = picker.querySelector("[data-picker-value]");
    const label = form.querySelector("[data-picker-label]");
    const options = picker.querySelector("[data-picker-options]");
    const month = picker.querySelector("[data-picker-month]");
    const year = picker.querySelector("[data-picker-year]");
    const previous = picker.querySelector("[data-picker-prev]");
    const next = picker.querySelector("[data-picker-next]");
    const locale = document.documentElement.lang || "en-US";
    // UTC arithmetic represents calendar dates, independent of device time zone.
    function makeDate(y, m, d) {
      const result = new Date(0);
      result.setUTCFullYear(y, m, d);
      result.setUTCHours(0, 0, 0, 0);
      return result;
    }
    function parse(text) {
      const parts = text.split("-").map(Number);
      return makeDate(parts[0], parts[1] - 1, parts[2]);
    }
    function iso(day) {
      return day.toISOString().slice(0, 10);
    }
    function format(day, settings) {
      return new Intl.DateTimeFormat(locale, {
        ...settings,
        timeZone: "UTC",
      }).format(day);
    }
    function shortDate(day) {
      return format(day, { month: "short", day: "numeric", year: "numeric" });
    }
    function weekStart(day) {
      return makeDate(
        day.getUTCFullYear(),
        day.getUTCMonth(),
        day.getUTCDate() - day.getUTCDay(),
      );
    }
    function weekEnd(day) {
      return makeDate(
        day.getUTCFullYear(),
        day.getUTCMonth(),
        day.getUTCDate() + 6,
      );
    }
    function valid(day) {
      return day.getUTCFullYear() >= 1 && day.getUTCFullYear() <= 9999;
    }
    const today = parse(form.dataset.today);
    let selected =
      date.value && !Number.isNaN(parse(date.value).getTime())
        ? parse(date.value)
        : today;
    let shown = makeDate(selected.getUTCFullYear(), selected.getUTCMonth(), 1);
    for (let index = 0; index < 12; index++) {
      const option = document.createElement("option");
      option.value = index;
      option.textContent = format(makeDate(2026, index, 1), { month: "long" });
      month.append(option);
    }
    function updateSummary() {
      label.textContent =
        picker.dataset[period.value + "Label"] || picker.dataset.allLabel;
      date.disabled = period.value === "all";
      summary.setAttribute("aria-disabled", String(date.disabled));
      if (date.disabled) {
        value.textContent = picker.dataset.allLabel;
        picker.open = false;
      } else if (period.value === "year") {
        value.textContent = selected.getUTCFullYear();
      } else if (period.value === "month") {
        value.textContent = format(selected, {
          month: "long",
          year: "numeric",
        });
      } else if (period.value === "week") {
        const start = weekStart(selected);
        value.textContent =
          shortDate(start) + " – " + shortDate(weekEnd(start));
      } else {
        value.textContent = shortDate(selected);
      }
    }
    function choose(day) {
      selected = day;
      date.value = iso(day);
      shown = makeDate(day.getUTCFullYear(), day.getUTCMonth(), 1);
      updateSummary();
      render();
      picker.open = false;
      summary.focus();
    }
    function button(text, day, active, accessibleLabel) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "timeline-picker-choice";
      item.textContent = text;
      item.setAttribute("aria-pressed", String(active));
      if (accessibleLabel) item.setAttribute("aria-label", accessibleLabel);
      item.addEventListener("click", function () {
        choose(day);
      });
      options.append(item);
    }
    function render() {
      const mode = period.value;
      const y = shown.getUTCFullYear();
      const m = shown.getUTCMonth();
      options.replaceChildren();
      options.dataset.mode = mode;
      month.hidden = mode === "year" || mode === "month";
      month.value = m;
      year.value = y;
      previous.disabled =
        y === 1 && ((mode !== "day" && mode !== "week") || m === 0);
      next.disabled =
        y === 9999 && ((mode !== "day" && mode !== "week") || m === 11);
      if (mode === "year") {
        const first = Math.max(1, Math.min(9988, y - 5));
        for (let candidate = first; candidate < first + 12; candidate++) {
          button(
            String(candidate),
            makeDate(candidate, 0, 1),
            candidate === selected.getUTCFullYear(),
          );
        }
      } else if (mode === "month") {
        for (let index = 0; index < 12; index++) {
          const day = makeDate(y, index, 1);
          button(
            format(day, { month: "short" }),
            day,
            y === selected.getUTCFullYear() && index === selected.getUTCMonth(),
            format(day, { month: "long", year: "numeric" }),
          );
        }
      } else if (mode === "week") {
        const active = iso(weekStart(selected));
        for (
          let start = weekStart(shown);
          start.getTime() <= makeDate(y, m + 1, 0).getTime();
          start = makeDate(
            start.getUTCFullYear(),
            start.getUTCMonth(),
            start.getUTCDate() + 7,
          )
        ) {
          const end = weekEnd(start);
          if (valid(start) && valid(end))
            button(
              shortDate(start) + " – " + shortDate(end),
              start,
              iso(start) === active,
            );
        }
      } else if (mode === "day") {
        for (let index = 0; index < 7; index++) {
          const heading = document.createElement("span");
          heading.className = "timeline-picker-weekday";
          heading.textContent = format(makeDate(2026, 0, 4 + index), {
            weekday: "short",
          });
          options.append(heading);
        }
        for (let index = 0; index < shown.getUTCDay(); index++)
          options.append(document.createElement("span"));
        for (
          let index = 1;
          index <= makeDate(y, m + 1, 0).getUTCDate();
          index++
        ) {
          const day = makeDate(y, m, index);
          button(
            String(index),
            day,
            iso(day) === iso(selected),
            shortDate(day),
          );
        }
      }
    }
    function move(direction) {
      const mode = period.value;
      const y = shown.getUTCFullYear();
      const m = shown.getUTCMonth();
      shown =
        mode === "year"
          ? makeDate(Math.max(1, Math.min(9999, y + direction * 12)), m, 1)
          : mode === "month"
            ? makeDate(Math.max(1, Math.min(9999, y + direction)), m, 1)
            : makeDate(y, m + direction, 1);
      render();
    }
    previous.addEventListener("click", function () {
      move(-1);
    });
    next.addEventListener("click", function () {
      move(1);
    });
    month.addEventListener("change", function () {
      shown = makeDate(shown.getUTCFullYear(), Number(month.value), 1);
      render();
    });
    year.addEventListener("change", function () {
      if (year.checkValidity() && year.value)
        shown = makeDate(Number(year.value), shown.getUTCMonth(), 1);
      render();
    });
    picker
      .querySelector("[data-picker-today]")
      .addEventListener("click", function () {
        choose(today);
      });
    summary.addEventListener("click", function (event) {
      if (date.disabled) event.preventDefault();
    });
    picker.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        picker.open = false;
        summary.focus();
      }
    });
    document.addEventListener("click", function (event) {
      if (!picker.contains(event.target) && event.target !== period)
        picker.open = false;
    });
    period.addEventListener("change", function () {
      if (!date.value) date.value = iso(selected);
      updateSummary();
      render();
      picker.open = !date.disabled;
    });
    date.hidden = true;
    label.removeAttribute("for");
    picker.hidden = false;
    updateSummary();
    render();
  });
});
