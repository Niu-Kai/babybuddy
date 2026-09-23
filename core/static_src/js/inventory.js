document.addEventListener("DOMContentLoaded", function () {
  const gettext = window.gettext || ((text) => text);
  const category = document.getElementById("id_category");
  const size = document.getElementById("id_size");
  if (!category || !size || !document.getElementById("diaper-sizes")) return;
  const label = document.querySelector('label[for="id_size"]');
  const guide = document.querySelector("[data-diaper-guide]");
  function updateSizeChoices() {
    const diapers = category.value === "diapers";
    if (label)
      label.textContent = diapers
        ? gettext("Diaper size / weight range")
        : gettext("Size");
    if (guide) guide.hidden = !diapers;
    size.placeholder = diapers
      ? gettext("Choose a package weight range or type a size")
      : "";
    const list =
      category.value === "diapers"
        ? "diaper-sizes"
        : category.value === "clothing"
          ? "clothing-sizes"
          : "";
    if (list) size.setAttribute("list", list);
    else size.removeAttribute("list");
  }
  category.addEventListener("change", updateSizeChoices);
  updateSizeChoices();
});
