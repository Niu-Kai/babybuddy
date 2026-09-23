document.addEventListener("DOMContentLoaded", function () {
  document
    .querySelectorAll("[data-appointment-choice]")
    .forEach(function (picker) {
      const input = picker.querySelector("input");
      const toggle = picker.querySelector("[data-choice-toggle]");
      const list = picker.querySelector('[role="listbox"]');
      const options = Array.from(list.querySelectorAll('[role="option"]'));
      let active = -1;
      toggle.hidden = false;
      input.setAttribute("role", "combobox");
      input.setAttribute("aria-autocomplete", "none");
      input.setAttribute("aria-haspopup", "listbox");
      input.setAttribute("aria-controls", list.id);
      input.setAttribute("aria-expanded", "false");
      function close() {
        list.hidden = true;
        input.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-expanded", "false");
        input.removeAttribute("aria-activedescendant");
      }
      function highlight(index) {
        active = index;
        options.forEach(function (option, i) {
          option.setAttribute("aria-selected", String(i === active));
        });
        input.setAttribute("aria-activedescendant", options[active].id);
        options[active].scrollIntoView({ block: "nearest" });
      }
      function numericValue(value) {
        if (picker.dataset.choiceKind === "duration") return Number(value);
        const match = value
          .trim()
          .match(/^(\d{1,2}):(\d{2})(?::\d{2})?(?:\s*(AM|PM))?$/i);
        if (!match) return NaN;
        let hour = Number(match[1]);
        if (match[3])
          hour = (hour % 12) + (match[3].toUpperCase() === "PM" ? 12 : 0);
        return hour * 60 + Number(match[2]);
      }
      function open() {
        list.hidden = false;
        input.setAttribute("aria-expanded", "true");
        toggle.setAttribute("aria-expanded", "true");
        input.focus();
        const value = numericValue(input.value);
        let index = options.findIndex(function (option) {
          return option.dataset.choiceValue === input.value;
        });
        if (index < 0) {
          index = options.findIndex(function (option) {
            return (
              option.dataset.choiceValue !== "" &&
              numericValue(option.dataset.choiceValue) >= value
            );
          });
        }
        highlight(index < 0 ? 0 : index);
      }
      function choose(index) {
        input.value = options[index].dataset.choiceValue;
        close();
        input.focus();
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
      toggle.addEventListener("click", function () {
        if (list.hidden) open();
        else {
          close();
          input.focus();
        }
      });
      options.forEach(function (option, index) {
        option.addEventListener("mousedown", function (event) {
          event.preventDefault();
        });
        option.addEventListener("click", function () {
          choose(index);
        });
      });
      input.addEventListener("input", close);
      picker.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
          close();
          return;
        }
        if (event.key === "Tab") {
          close();
          return;
        }
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          if (list.hidden) open();
          else
            highlight(
              (active + (event.key === "ArrowDown" ? 1 : -1) + options.length) %
                options.length,
            );
        } else if (!list.hidden && event.key === "Enter") {
          event.preventDefault();
          choose(active);
        }
      });
      picker.addEventListener("focusout", function (event) {
        if (!picker.contains(event.relatedTarget)) close();
      });
      document.addEventListener("click", function (event) {
        if (!picker.contains(event.target)) close();
      });
    });

  document
    .querySelectorAll("[data-appointment-time]")
    .forEach(function (container) {
      const fields = ["appointment_date", "start_time", "duration_minutes"].map(
        function (name) {
          return container.querySelector('[name$="' + name + '"]');
        },
      );
      const output = container.querySelector("[data-appointment-end]");
      let timer;
      let controller;
      let revision = 0;
      function update() {
        clearTimeout(timer);
        if (controller) controller.abort();
        const current = ++revision;
        if (!fields[0].value || !fields[1].value) {
          output.textContent = container.dataset.incomplete;
          return;
        }
        timer = setTimeout(async function () {
          controller = new AbortController();
          const params = new URLSearchParams();
          if (container.dataset.originalStart) {
            params.set("reference_start", container.dataset.originalStart);
          }
          ["appointment_date", "start_time", "duration_minutes"].forEach(
            function (name, index) {
              params.set(name, fields[index].value);
            },
          );
          const occurrence = container
            .closest("form")
            .querySelector('[name="time_occurrence"]');
          if (occurrence) params.set("time_occurrence", occurrence.value);
          try {
            const response = await fetch(
              container.dataset.previewUrl + "?" + params,
              { credentials: "same-origin", signal: controller.signal },
            );
            const result = await response.json();
            if (current === revision)
              output.textContent =
                result.display || container.dataset.unavailable;
          } catch (error) {
            if (error.name !== "AbortError" && current === revision)
              output.textContent = container.dataset.unavailable;
          }
        }, 200);
      }
      fields.forEach(function (field) {
        field.addEventListener("input", update);
        field.addEventListener("change", update);
      });
      const occurrence = container
        .closest("form")
        .querySelector('[name="time_occurrence"]');
      if (occurrence) occurrence.addEventListener("change", update);
      update();
    });
});
