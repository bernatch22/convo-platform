/* The deck runtime: which slide is showing, and nothing else.
 *
 * Lifted in spirit from ~/pinecall/presentations/decks/pinecall.html — the same
 * chassis (absolute slides, .is-active / .is-past, the [data-anim] stagger,
 * arrows/space/Home/End) with the framework taken out. There is no state store,
 * no build step for the runtime and no narrator: the URL hash IS the state, so
 * every slide is linkable and reload lands where you were.
 */

(function () {
  var stage = document.getElementById("stage");
  var slides = Array.prototype.slice.call(stage.querySelectorAll(".slide"));
  var progress = document.querySelector(".progress");
  var dots = document.querySelector(".dots");
  var i = 0;

  /** Fit the fixed 1600x900 stage inside whatever viewport we were given. */
  function fit() {
    var s = Math.min(window.innerWidth / 1600, window.innerHeight / 900);
    document.documentElement.style.setProperty("--scale", String(s));
  }

  /** Show slide n (clamped), and write it into the hash so reload survives. */
  function go(n, silent) {
    var next = Math.max(0, Math.min(slides.length - 1, n));
    i = next;
    slides.forEach(function (el, k) {
      el.classList.toggle("is-active", k === i);
      el.classList.toggle("is-past", k < i);
    });
    if (progress) progress.style.width = (slides.length < 2 ? 100 : (i / (slides.length - 1)) * 100) + "%";
    if (dots) {
      Array.prototype.forEach.call(dots.children, function (b, k) {
        b.setAttribute("aria-current", k === i ? "true" : "false");
      });
    }
    if (!silent) history.replaceState(null, "", "#" + String(i + 1));
    document.title = (slides[i].dataset.title || "convo") + " · " + (i + 1) + "/" + slides.length;
  }

  /** The slide asked for in the hash, 1-based, or the first one. */
  function fromHash() {
    var n = parseInt((location.hash || "").replace("#", ""), 10);
    return isNaN(n) ? 0 : n - 1;
  }

  /** Every box on this slide that spilled out of the room it was given. */
  function overflow(el) {
    var worst = 0, culprit = "";
    var boxes = el.querySelectorAll("*");
    for (var j = 0; j < boxes.length; j++) {
      var b = boxes[j];
      if (getComputedStyle(b).overflow !== "visible") continue;
      var spill = b.scrollHeight - b.clientHeight;
      if (spill > worst) { worst = spill; culprit = String(b.className || b.tagName).trim(); }
    }
    return { spill: worst, culprit: culprit };
  }

  /* ?audit — measure every slide and report through document.title, the one
   * value `chrome --headless --dump-dom` hands back without a devtools client.
   *
   * Two different overflows ruin a slide and neither warns you: the section
   * growing past 900px becomes a silent SECOND page in the PDF, and a flex or
   * grid track whose content does not fit stays 900px tall while OVERLAPPING
   * what is under it — worse, because it still looks like a slide. Check both.
   * See audit.mjs. */
  if (/[?&]audit\b/.test(location.search)) {
    // Measure the slide as it PRINTS, not as it enters: the [data-anim] stagger
    // parks every element 10px lower, and measuring that reports a 10px
    // overflow on a slide that fits perfectly.
    var off = document.createElement("style");
    off.textContent = ".slide [data-anim]{opacity:1!important;transform:none!important;transition:none!important}";
    document.head.appendChild(off);

    document.title = "AUDIT:" + JSON.stringify(slides.map(function (el, k) {
      var page = Math.max(0, el.scrollHeight - 900);
      var inner = overflow(el);
      var spill = inner.spill > 1 ? inner.spill : 0;
      return {
        n: k + 1,
        title: el.dataset.title || "",
        height: el.scrollHeight,
        over: Math.max(page, spill),
        where: page >= spill ? (page ? "la lámina entera" : "") : inner.culprit
      };
    }));
    return;
  }

  if (dots) {
    slides.forEach(function (el, k) {
      var b = document.createElement("button");
      b.type = "button";
      b.title = (k + 1) + ". " + (el.dataset.title || "");
      b.addEventListener("click", function () { go(k); });
      dots.appendChild(b);
    });
  }

  window.addEventListener("keydown", function (e) {
    var tag = e.target && e.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA") return;
    if (e.key === "ArrowRight" || e.key === " " || e.key === "PageDown") { go(i + 1); e.preventDefault(); }
    else if (e.key === "ArrowLeft" || e.key === "PageUp") { go(i - 1); e.preventDefault(); }
    else if (e.key === "Home") { go(0); e.preventDefault(); }
    else if (e.key === "End") { go(slides.length - 1); e.preventDefault(); }
    else if (e.key === "f" || e.key === "F") {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen && document.documentElement.requestFullscreen();
    }
  });

  window.addEventListener("hashchange", function () { go(fromHash(), true); });
  window.addEventListener("resize", fit);

  fit();
  go(fromHash(), true);
})();
