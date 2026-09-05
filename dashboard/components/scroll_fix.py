"""Mouse horizontal-scroll affordances for wide st.dataframe tables.

Streamlit renders dataframes with glide-data-grid: its scrollbar is an
auto-hiding overlay, shift+wheel scrolls the grid vertically, and dragging
draws a cell selection — leaving mouse users no working horizontal-scroll
gesture (only trackpad two-finger swipe). This module injects a small
same-origin script that maps shift+wheel to horizontal scrolling and
left-drag to panning by driving glide's internal DOM scroller directly,
and keeps a slim scrollbar visible.

The `.dvn-scroller` hook is glide's real scroll container; it is pinned by
Streamlit's dataframe implementation, and every step no-ops when absent.
"""

from __future__ import annotations

from streamlit.components.v1 import html as components_html

_SCRIPT = """
<script>
(function () {
  var doc = window.parent.document;
  if (doc.getElementById("cti-scroll-fix-style")) return;

  var style = doc.createElement("style");
  style.id = "cti-scroll-fix-style";
  style.textContent =
    // Chromium honors standard scrollbar properties; setting scrollbar-color
    // switches the grid's overlay scrollbar to a slim always-visible one.
    ".dvn-scroller{scrollbar-width:thin;" +
    "scrollbar-color:rgba(148,163,184,.55) transparent}" +
    '[data-testid="stDataFrame"] canvas{cursor:grab}' +
    ".cti-panning [data-testid='data-grid-canvas']{cursor:grabbing!important}";
  doc.head.appendChild(style);

  function scrollerOf(target) {
    var df = target && target.closest
      ? target.closest('[data-testid="stDataFrame"]')
      : null;
    return df ? df.querySelector(".dvn-scroller") : null;
  }

  // glide treats shift+wheel as vertical; map it to horizontal instead.
  // passive:false is required — Chrome makes document-level wheel listeners
  // passive by default, which would ignore preventDefault and still scroll
  // the page.
  doc.addEventListener(
    "wheel",
    function (e) {
      if (!e.shiftKey || e.deltaY === 0) return;
      var sc = scrollerOf(e.target);
      if (!sc) return;
      e.preventDefault();
      e.stopPropagation();
      sc.scrollLeft += e.deltaY;
    },
    { capture: true, passive: false }
  );

  // Left-drag pans the grid instead of drawing a cell selection. Moves are
  // swallowed as soon as the button is down on a grid; a stationary click
  // (no movement) still reaches glide's row-selection handling.
  var pan = null;
  doc.addEventListener(
    "pointerdown",
    function (e) {
      if (e.button !== 0) return;
      var sc = scrollerOf(e.target);
      if (!sc) return;
      pan = {
        x0: e.clientX,
        y0: e.clientY,
        x: e.clientX,
        y: e.clientY,
        id: e.pointerId,
        moved: false,
        sc: sc,
      };
    },
    true
  );
  doc.addEventListener(
    "pointermove",
    function (e) {
      if (!pan || e.pointerId !== pan.id) return;
      e.preventDefault();
      e.stopPropagation();
      if (
        !pan.moved &&
        Math.abs(e.clientX - pan.x0) < 3 &&
        Math.abs(e.clientY - pan.y0) < 3
      )
        return;
      if (!pan.moved) {
        pan.moved = true;
        pan.sc.classList.add("cti-panning");
      }
      pan.sc.scrollLeft -= e.clientX - pan.x;
      pan.sc.scrollTop -= e.clientY - pan.y;
      pan.x = e.clientX;
      pan.y = e.clientY;
    },
    true
  );
  doc.addEventListener(
    "pointerup",
    function (e) {
      if (!pan || e.pointerId !== pan.id) return;
      if (pan.moved) {
        e.preventDefault();
        e.stopPropagation();
        pan.sc.classList.remove("cti-panning");
      }
      pan = null;
    },
    true
  );
  doc.addEventListener(
    "pointercancel",
    function () {
      if (pan) pan.sc.classList.remove("cti-panning");
      pan = null;
    },
    true
  );
})();
</script>
"""


def apply_table_scroll_fix() -> None:
    components_html(_SCRIPT, height=0)
