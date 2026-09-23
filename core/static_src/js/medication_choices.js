document.addEventListener("DOMContentLoaded", function () {
  const input = document.querySelector("[data-medication-choices]");
  if (!input) return;
  const form = input.closest("form"),
    list = document.createElement("datalist");
  list.id = "medication-history";
  input.after(list);
  let choices = [],
    revision = 0,
    selectedHistory = false;
  async function load() {
    const current = ++revision;
    choices = [];
    list.replaceChildren();
    const child = form.querySelector(
      '[name="child"]:checked, select[name="child"], input[type="hidden"][name="child"]',
    );
    if (!child || !child.value) return;
    try {
      const response = await fetch(
        input.dataset.medicationChoices +
          "?child=" +
          encodeURIComponent(child.value),
        { credentials: "same-origin" },
      );
      if (!response.ok) return;
      const data = await response.json();
      if (current !== revision) return;
      choices = data.medications;
      choices.forEach((entry) => {
        const option = document.createElement("option");
        option.value = entry.name;
        option.label =
          entry.name + " · " + entry.dosage + " " + entry.dosage_unit;
        list.appendChild(option);
      });
    } catch (_) {
      /* Manual entry stays available without suggestions. */
    }
  }
  input.addEventListener("change", function () {
    const entry = choices.find((entry) => entry.name === input.value);
    if (!entry) return;
    selectedHistory = true;
    ["dosage", "next_dose_interval"].forEach((name) => {
      if (form.elements.namedItem(name))
        form.elements.namedItem(name).value = entry[name] ?? "";
    });
    const unit = Array.from(form.querySelectorAll('[name="dosage_unit"]')).find(
      (option) => option.value === entry.dosage_unit,
    );
    if (unit) {
      unit.checked = true;
      unit.dispatchEvent(new Event("change", { bubbles: true }));
    }
  });
  form.querySelectorAll('[name="child"]').forEach((child) =>
    child.addEventListener("change", function () {
      if (selectedHistory) {
        input.value = "";
        ["dosage", "next_dose_interval"].forEach((name) => {
          if (form.elements.namedItem(name))
            form.elements.namedItem(name).value = "";
        });
        form.querySelectorAll('[name="dosage_unit"]').forEach((option) => {
          option.checked = false;
        });
        selectedHistory = false;
      }
      load();
    }),
  );
  load();
});
