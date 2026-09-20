if (typeof jQuery === "undefined") {
  throw new Error("Baby Buddy requires jQuery.");
}

/**
 * Baby Buddy Namespace
 *
 * Default namespace for the Baby Buddy app.
 *
 * @type {{}}
 */
var BabyBuddy = (function () {
  return {};
})();

/**
 * Pull to refresh.
 *
 * @type {{init: BabyBuddy.PullToRefresh.init, onRefresh: BabyBuddy.PullToRefresh.onRefresh}}
 */
BabyBuddy.PullToRefresh = (function (ptr) {
  return {
    init: function () {
      ptr.init({
        mainElement: "body",
        onRefresh: this.onRefresh,
      });
    },

    onRefresh: function () {
      window.location.reload();
    },
  };
})(PullToRefresh);

/**
 * Show a loading spinner on the submit button when a form is submitted and
 * prevent double-submission.
 */
(function handleFormSubmit() {
  $("form").on("submit", function (event) {
    var submitter =
      (event.originalEvent && event.originalEvent.submitter) ||
      $(this).find('[type="submit"]')[0];
    if (!submitter || $(submitter).prop("disabled")) return;
    $(submitter)
      .prop("disabled", true)
      .prepend(
        '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>',
      );
  });
})();

/**
 * Let an optional pill (radio) selection be cleared by clicking the selected
 * option again. Required groups keep normal radio behaviour
 * (babybuddy/babybuddy#870).
 */
(function deselectablePills() {
  $(document).on("mousedown touchstart", ".pill-container label", function () {
    var input = document.getElementById(this.getAttribute("for"));
    if (input) {
      input.dataset.wasChecked = input.checked ? "true" : "false";
    }
  });
  $(document).on(
    "click",
    ".pill-container input[type=radio]:not([required])",
    function () {
      if (this.dataset.wasChecked === "true") {
        this.checked = false;
        this.dataset.wasChecked = "false";
        $(this).trigger("change");
      }
    },
  );
})();

/**
 * Add a "copy start time" button under an end time field so a short entry in
 * the past needs the date and time picked only once
 * (babybuddy/babybuddy#728).
 */
(function copyStartTime() {
  window.addEventListener("load", function () {
    var start = document.getElementById("id_start");
    var end = document.getElementById("id_end");
    if (!start || !end || !end.dataset.copyLabel) {
      return;
    }
    var button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-sm btn-outline-secondary mt-2";
    button.textContent = end.dataset.copyLabel;
    button.addEventListener("click", function () {
      end.value = start.value;
      end.dispatchEvent(new Event("change", { bubbles: true }));
    });
    end.insertAdjacentElement("afterend", button);
  });
})();

BabyBuddy.RememberAdvancedToggle = function (ptr) {
  localStorage.setItem("advancedForm", event.newState);
};

(function toggleAdvancedFields() {
  window.addEventListener("load", function () {
    if (localStorage.getItem("advancedForm") !== "open") {
      return;
    }

    document.querySelectorAll(".advanced-fields").forEach(function (node) {
      node.open = true;
    });
  });
})();
