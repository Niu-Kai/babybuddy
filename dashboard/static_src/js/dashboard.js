/* Baby Buddy Dashboard
 *
 * Provides a "watch" function to refresh the dashboard at a chosen interval
 * and when the page comes back into view. The refresh swaps the dashboard's
 * content in place instead of reloading the page, so nothing flashes.
 */
BabyBuddy.Dashboard = (function ($) {
  var runIntervalId = null;
  var dashboardElement = null;
  var hidden = null;
  var updating = false;
  var lastUpdate = 0;

  // Regaining focus should not refresh more often than this.
  var FOCUS_THROTTLE_MS = 15000;

  var Dashboard = {
    watch: function (element_id, refresh_rate) {
      dashboardElement = $("#" + element_id);

      if (dashboardElement.length == 0) {
        console.error("Baby Buddy: Dashboard element not found.");
        return false;
      }

      if (typeof document.hidden !== "undefined") {
        hidden = "hidden";
      } else if (typeof document.msHidden !== "undefined") {
        hidden = "msHidden";
      } else if (typeof document.webkitHidden !== "undefined") {
        hidden = "webkitHidden";
      }

      if (
        typeof window.addEventListener === "undefined" ||
        typeof document.hidden === "undefined"
      ) {
        if (refresh_rate) {
          runIntervalId = setInterval(this.update, refresh_rate);
        }
      } else {
        window.addEventListener("focus", Dashboard.handleFocus, false);
        if (refresh_rate) {
          runIntervalId = setInterval(
            Dashboard.handleVisibilityChange,
            refresh_rate,
          );
        }
      }
    },

    handleVisibilityChange: function () {
      if (!document[hidden]) {
        Dashboard.update();
      }
    },

    handleFocus: function () {
      if (Date.now() - lastUpdate > FOCUS_THROTTLE_MS) {
        Dashboard.handleVisibilityChange();
      }
    },

    update: function () {
      if (updating || document.body.classList.contains("arranging-panels")) {
        return;
      }
      updating = true;

      fetch(window.location.href, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      })
        .then(function (response) {
          if (!response.ok) {
            throw new Error("Dashboard refresh failed: " + response.status);
          }
          return response.text();
        })
        .then(function (html) {
          var fresh = new DOMParser()
            .parseFromString(html, "text/html")
            .getElementById(dashboardElement.attr("id"));
          if (!fresh) {
            // Probably redirected (e.g. logged out); fall back to a reload.
            window.location.reload();
            return;
          }
          dashboardElement.html(fresh.innerHTML);
          var household = new DOMParser()
            .parseFromString(html, "text/html")
            .getElementById("household-lactation");
          var current = document.getElementById("household-lactation");
          if (household && current) current.replaceWith(household);
        })
        .catch(function () {
          window.location.reload();
        })
        .finally(function () {
          updating = false;
          lastUpdate = Date.now();
        });
    },
  };

  return Dashboard;
})(jQuery);
