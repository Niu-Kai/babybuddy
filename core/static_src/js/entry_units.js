/* Preserve the measurement when switching an explicit entry unit. */
document.addEventListener("DOMContentLoaded", function () {
  const factors = {
    cm: 1,
    in: 2.54,
    kg: 1,
    lb: 0.45359237,
    oz: 0.028349523125,
    mL: 1,
    "fl oz": 29.5735295625,
  };
  document
    .querySelectorAll("select[data-unit-fields]")
    .forEach(function (select) {
      let previous = select.value;
      const names = select.dataset.unitFields.split(",");
      function labels() {
        names.forEach(function (name) {
          const input = select.form.elements.namedItem(name);
          if (!input) return;
          const label = select.form.querySelector(
            'label[for="' + input.id + '"]',
          );
          if (!label) return;
          if (!label.dataset.originalLabel)
            label.dataset.originalLabel = label.textContent.trim();
          const unitLabel = select.value
            ? select.options[select.selectedIndex].text
            : "";
          label.textContent =
            label.dataset.originalLabel +
            (unitLabel ? " (" + unitLabel + ")" : "");
        });
      }
      select.addEventListener("change", function () {
        const next = select.value;
        if (previous && next) {
          names.forEach(function (name) {
            const input = select.form.elements.namedItem(name);
            if (!input || !input.value.trim()) return;
            const number = Number(input.value.replace(",", "."));
            if (!Number.isFinite(number)) return;
            let result = number;
            if (previous === "F" && next === "C")
              result = ((number - 32) * 5) / 9;
            else if (previous === "C" && next === "F")
              result = (number * 9) / 5 + 32;
            else if (factors[previous] && factors[next])
              result = (number * factors[previous]) / factors[next];
            input.value = Number(result.toFixed(10));
          });
        }
        previous = next;
        labels();
      });
      labels();
    });
});

document.addEventListener("DOMContentLoaded", function () {
  document
    .querySelectorAll(".comparison-grid .record-table")
    .forEach(function (table) {
      const headers = Array.from(table.querySelectorAll("thead th"), (cell) =>
        cell.textContent.trim(),
      );
      table.querySelectorAll("tbody tr").forEach(function (row) {
        if (row.children.length !== headers.length) return;
        Array.from(row.children).forEach(function (cell, index) {
          cell.dataset.label = headers[index];
        });
      });
      table.classList.add("comparison-records");
    });
});
