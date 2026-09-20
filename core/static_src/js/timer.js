/* Baby Buddy Timer
 *
 * Uses a supplied ID to run a timer. The element using the ID must have
 * three children with the following classes:
 *  * timer-seconds
 *  * timer-minutes
 *  * timer-hours
 */
BabyBuddy.Timer = (function ($) {
  var runIntervalId = null;
  var timerId = null;
  var timerElement = null;
  var lastUpdate = new Date();
  var hidden = null;

  var Timer = {
    run: function (timer_id, element_id) {
      timerId = timer_id;
      timerElement = $("#" + element_id);

      if (timerElement.length === 0) {
        console.error("BBTimer: Timer element not found.");
        return false;
      }

      if (
        timerElement.find(".timer-seconds").length === 0 ||
        timerElement.find(".timer-minutes").length === 0 ||
        timerElement.find(".timer-hours").length === 0
      ) {
        console.error("BBTimer: Element does not contain expected children.");
        return false;
      }

      runIntervalId = setInterval(this.tick, 1000);

      // Another user may stop (delete) this timer while the page is open;
      // detect that so nobody records a second entry from a dead timer
      // (babybuddy/babybuddy#983).
      setInterval(Timer.check, 15000);

      // If the page just came in to view, update the timer data with the
      // current actual duration. This will (potentially) help mobile
      // phones that lock with the timer page open.
      if (typeof document.hidden !== "undefined") {
        hidden = "hidden";
      } else if (typeof document.msHidden !== "undefined") {
        hidden = "msHidden";
      } else if (typeof document.webkitHidden !== "undefined") {
        hidden = "webkitHidden";
      }
      window.addEventListener("focus", Timer.handleVisibilityChange, false);
    },

    handleVisibilityChange: function () {
      if (!document[hidden] && new Date() - lastUpdate > 1) {
        Timer.update();
      }
    },

    tick: function () {
      var s = timerElement.find(".timer-seconds");
      var seconds = Number(s.text());
      if (seconds < 59) {
        s.text(seconds + 1);
        return;
      } else {
        s.text(0);
      }

      var m = timerElement.find(".timer-minutes");
      var minutes = Number(m.text());
      if (minutes < 59) {
        m.text(minutes + 1);
        return;
      } else {
        m.text(0);
      }

      var h = timerElement.find(".timer-hours");
      var hours = Number(h.text());
      h.text(hours + 1);
    },

    check: function () {
      $.get("/api/timers/" + timerId + "/").fail(function (response) {
        if (response.status === 404) {
          Timer.stopped();
        }
      });
    },

    stopped: function () {
      clearInterval(runIntervalId);
      $("#timer-stopped").removeClass("d-none");
      $("#timer-actions").addClass("d-none");
      $("#timer-status").addClass("text-body-secondary");
    },

    update: function () {
      $.get("/api/timers/" + timerId + "/", function (data) {
        if (data && "duration" in data) {
          clearInterval(runIntervalId);
          var duration = data.duration.split(/[\s:.]/);
          if (duration.length === 5) {
            duration[0] = parseInt(duration[0]) * 24 + parseInt(duration[1]);
            duration[1] = duration[2];
            duration[2] = duration[3];
          }
          timerElement.find(".timer-hours").text(parseInt(duration[0]));
          timerElement.find(".timer-minutes").text(parseInt(duration[1]));
          timerElement.find(".timer-seconds").text(parseInt(duration[2]));
          lastUpdate = new Date();
          runIntervalId = setInterval(Timer.tick, 1000);
        }
      });
    },
  };

  return Timer;
})(jQuery);

/**
 * Keep the screen on while a timer page is open, via the Screen Wake Lock
 * API. The choice is remembered for the browser session
 * (babybuddy/babybuddy#1070).
 */
BabyBuddy.WakeLock = (function () {
  var storageKey = "keepScreenOn";
  var lock = null;

  function request() {
    navigator.wakeLock
      .request("screen")
      .then(function (sentinel) {
        lock = sentinel;
      })
      .catch(function () {
        lock = null;
      });
  }

  function release() {
    if (lock) {
      lock.release();
      lock = null;
    }
  }

  return {
    init: function (checkbox_id) {
      var checkbox = document.getElementById(checkbox_id);
      if (!checkbox) {
        return;
      }
      if (!("wakeLock" in navigator)) {
        checkbox.disabled = true;
        checkbox.parentElement.classList.add("text-body-secondary");
        return;
      }
      checkbox.checked = sessionStorage.getItem(storageKey) === "true";
      if (checkbox.checked) {
        request();
      }
      checkbox.addEventListener("change", function () {
        sessionStorage.setItem(storageKey, checkbox.checked);
        if (checkbox.checked) {
          request();
        } else {
          release();
        }
      });
      document.addEventListener("visibilitychange", function () {
        if (document.visibilityState === "visible" && checkbox.checked) {
          request();
        }
      });
    },
  };
})();
