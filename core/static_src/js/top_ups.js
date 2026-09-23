document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("[data-top-up]").forEach(function (section) {
    const form = section.closest("form");
    const toggle = form.elements.namedItem("top_up_enabled");
    function refresh() {
      const method = form.querySelector('[name="method"]:checked');
      const nursing =
        method &&
        ["left breast", "right breast", "both breasts"].includes(method.value);
      section.hidden = !nursing && !toggle.checked;
      section.querySelectorAll("[data-top-up-detail]").forEach(function (row) {
        row.hidden = !toggle.checked;
      });
    }
    toggle.addEventListener("change", refresh);
    form
      .querySelectorAll('[name="method"]')
      .forEach((input) => input.addEventListener("change", refresh));
    refresh();
  });
});
