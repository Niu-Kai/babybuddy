document.addEventListener("DOMContentLoaded", function () {
  const total = document.querySelector("[data-pumping-total]");
  if (!total) return;
  const form = total.closest("form");
  const left = form.elements.namedItem("left_amount"),
    right = form.elements.namedItem("right_amount");
  function update() {
    const split = left.value.trim() !== "" || right.value.trim() !== "";
    total.readOnly = split;
    if (split) {
      const a = Number(left.value.replace(",", ".")),
        b = Number(right.value.replace(",", "."));
      total.value = Number.isFinite(a + b)
        ? String(Math.round((a + b) * 1000000) / 1000000)
        : "";
      const side =
        left.value.trim() && right.value.trim()
          ? "both"
          : left.value.trim()
            ? "left"
            : "right";
      const option = form.querySelector('[name="side"][value="' + side + '"]');
      if (option) option.checked = true;
    }
  }
  [left, right].forEach((input) => input.addEventListener("input", update));
  update();
});
