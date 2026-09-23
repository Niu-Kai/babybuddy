document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("[data-meal-foods]").forEach(function (editor) {
    const form = editor.closest("form");
    const rows = editor.querySelector("[data-food-rows]");
    const template = rows.firstElementChild.cloneNode(true);
    const add = editor.querySelector("[data-add-food]");
    const fieldRow = editor.closest(".row.mb-3");
    function refresh() {
      const solid = Array.from(
        form.querySelectorAll(
          '[name="type"]:checked, [name="secondary_type"]:checked',
        ),
      ).some((input) => input.value === "solid food");
      if (fieldRow) fieldRow.hidden = !solid;
      const methods = Array.from(form.querySelectorAll('[name="method"]'));
      if (
        solid &&
        !methods.some(
          (input) =>
            input.checked && ["parent fed", "self fed"].includes(input.value),
        )
      ) {
        const parentFed = methods.find((input) => input.value === "parent fed");
        if (parentFed) parentFed.checked = true;
      }
      methods.forEach(function (input) {
        const unavailable =
          solid && !["parent fed", "self fed"].includes(input.value);
        const label = form.querySelector('label[for="' + input.id + '"]');
        if (label) label.hidden = unavailable;
        input.disabled = unavailable;
      });
      const side = form.querySelector('[name="last_breast"]');
      const sideRow = side && side.closest(".row.mb-3");
      if (sideRow)
        sideRow.hidden = !methods.some(
          (input) => input.checked && input.value === "both breasts",
        );
      // Hidden controls retain existing foods so switching types cannot silently erase them.
      ["amount", "secondary_amount", "entry_unit"].forEach(function (name) {
        const input = form.elements.namedItem(name);
        if (!input) return;
        const row = input.closest(".row.mb-3");
        if (row) row.hidden = solid;
        input.disabled = solid;
      });
      add.disabled = rows.children.length >= 20;
    }
    add.addEventListener("click", function () {
      if (rows.children.length >= 20) return;
      const row = template.cloneNode(true);
      row.querySelectorAll("input, select").forEach((input) => {
        input.value = "";
      });
      rows.appendChild(row);
      row.querySelector('input[type="text"]').focus();
      refresh();
    });
    editor.addEventListener("click", function (event) {
      const remove = event.target.closest("[data-remove-food]");
      if (!remove) return;
      const row = remove.closest("[data-food-row]");
      if (rows.children.length === 1) {
        row.querySelectorAll("input, select").forEach((input) => {
          input.value = "";
        });
      } else row.remove();
      refresh();
    });
    form
      .querySelectorAll(
        '[name="type"], [name="secondary_type"], [name="method"]',
      )
      .forEach((input) => input.addEventListener("change", refresh));
    refresh();
  });
});
