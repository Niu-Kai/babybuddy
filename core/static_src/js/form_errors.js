// Keep validation feedback visible after submitting long entry forms.
document.addEventListener("DOMContentLoaded", function () {
  const summary = document.querySelector("[data-form-errors]");
  if (!summary) return;
  requestAnimationFrame(() => {
    summary.focus({ preventScroll: true });
    summary.scrollIntoView({ block: "center", behavior: "instant" });
  });
  summary.addEventListener("click", (event) => {
    const link = event.target.closest('a[href^="#"]');
    if (!link) return;
    const field = document.getElementById(link.getAttribute("href").slice(1));
    if (!field) return;
    event.preventDefault();
    for (
      let parent = field.parentElement;
      parent;
      parent = parent.parentElement
    ) {
      if (parent.tagName === "DETAILS") parent.open = true;
    }
    field.focus({ preventScroll: true });
    field.scrollIntoView({ block: "center", behavior: "instant" });
  });
});
