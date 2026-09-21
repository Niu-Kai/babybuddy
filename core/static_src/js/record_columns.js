document.addEventListener("DOMContentLoaded", function () {
  document
    .querySelectorAll("[data-record-columns]")
    .forEach(function (control) {
      const tables = Array.from(document.querySelectorAll(".record-table"));
      const choices = new Map();
      tables.forEach(function (table) {
        table
          .querySelectorAll("thead [data-column]")
          .forEach(function (header) {
            choices.set(header.dataset.column, header.textContent.trim());
          });
      });
      if (!choices.size) return;
      if (
        tables.some(function (table) {
          return table.querySelector('tr[data-column="notes"]');
        })
      ) {
        choices.set("notes", control.dataset.notesLabel);
      }
      let hidden = new Set();
      try {
        const saved = JSON.parse(
          localStorage.getItem(control.dataset.storageKey),
        );
        if (Array.isArray(saved))
          hidden = new Set(
            saved.filter(function (key) {
              return typeof key === "string";
            }),
          );
      } catch (_) {
        /* Controls still work when browser storage is unavailable. */
      }
      const inputs = new Map();
      const optionList = control.querySelector("[data-column-options]");
      function save() {
        try {
          localStorage.setItem(
            control.dataset.storageKey,
            JSON.stringify(Array.from(hidden)),
          );
        } catch (_) {}
      }
      function visibleHeaders(table) {
        return Array.from(table.querySelectorAll("thead [data-column]")).filter(
          function (cell) {
            return !hidden.has(cell.dataset.column);
          },
        );
      }
      function apply() {
        // Always leave at least one data column in every visible table.
        tables.forEach(function (table) {
          if (!visibleHeaders(table).length) {
            const first = table.querySelector("thead [data-column]");
            if (first) hidden.delete(first.dataset.column);
          }
          table.querySelectorAll("[data-column]").forEach(function (cell) {
            cell.hidden = hidden.has(cell.dataset.column);
          });
          const width = visibleHeaders(table).length;
          table.querySelectorAll("tbody [colspan]").forEach(function (cell) {
            cell.colSpan = Math.max(1, width);
          });
        });
        inputs.forEach(function (input, key) {
          input.checked = !hidden.has(key);
          input.disabled =
            input.checked &&
            tables.some(function (table) {
              const visible = visibleHeaders(table);
              return visible.length === 1 && visible[0].dataset.column === key;
            });
        });
      }
      choices.forEach(function (label, key) {
        const wrapper = document.createElement("label");
        const input = document.createElement("input");
        input.type = "checkbox";
        input.className = "form-check-input";
        // No name: display choices must not become query filters on submit.
        const text = document.createElement("span");
        text.textContent = label;
        wrapper.append(input, text);
        optionList.append(wrapper);
        inputs.set(key, input);
        input.addEventListener("change", function () {
          if (input.checked) hidden.delete(key);
          else hidden.add(key);
          apply();
          save();
        });
      });
      control
        .querySelector("[data-columns-reset]")
        .addEventListener("click", function () {
          hidden.clear();
          apply();
          save();
        });
      control.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
          control.open = false;
          control.querySelector("summary").focus();
        }
      });
      document.addEventListener("click", function (event) {
        if (!control.contains(event.target)) control.open = false;
      });
      apply();
      control.hidden = false;
    });
});
