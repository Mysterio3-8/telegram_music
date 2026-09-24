// Жесты приложения. Владелец 22.09 прислал развёрнутое ТЗ («как во всех
// приложениях»): свайп от левого края — назад, по обложке влево/вправо — смена
// трека, вниз — свернуть плеер, вверх по мини-плееру — развернуть, по строке
// трека вбок — быстрые действия.
//
// ⚠️ Главное правило здесь — ЗАМОК ОСИ. Владелец отдельным пунктом просил:
// «они должны строго свайпаться горизонтально или вертикально, но не на все
// оси». Поэтому направление определяется один раз, на первых AXIS_LOCK_PX
// пикселях, и до конца жеста не меняется: палец, ушедший вбок, уже не свернёт
// плеер, а начатая прокрутка не превратится в смену трека.
//
// ⚠️ Второе правило — не воевать с прокруткой. Пока ось не выбрана, ничего не
// отменяем; выбрали горизонталь — гасим прокрутку (preventDefault), выбрали
// вертикаль внутри списка — не мешаем ему листаться.

const AXIS_LOCK_PX = 12; // после какого смещения решаем, вбок это или вверх-вниз
const EDGE_ZONE_PX = 32; // ширина «зоны края» для жеста «назад»
const SWIPE_MIN_PX = 64; // короче — это промах, а не жест
const ROW_MAX_SHIFT = 88; // насколько далеко уезжает строка трека под пальцем
const FLING_MS = 400; // быстрый короткий свайп засчитываем с меньшим порогом
const FLING_MIN_PX = 32;

export function installGestures(root, handlers) {
  let start = null;

  const reset = () => {
    if (start && start.row) releaseRow(start.row, false);
    start = null;
  };

  root.addEventListener(
    "touchstart",
    (event) => {
      if (event.touches.length !== 1) return reset();
      const touch = event.touches[0];
      start = {
        x: touch.clientX,
        y: touch.clientY,
        time: Date.now(),
        axis: null, // null | "x" | "y"
        scrollTop: document.scrollingElement ? document.scrollingElement.scrollTop : 0,
        fromEdge: touch.clientX <= EDGE_ZONE_PX,
        art: closest(event.target, ".player-art"),
        mini: closest(event.target, ".mini-player"),
        row: rowUnder(event.target),
        inScroller: Boolean(closest(event.target, ".h-scroll")),
        onSlider: Boolean(closest(event.target, "[data-role='seek']") || closest(event.target, ".player-seek")),
      };
    },
    { passive: true }
  );

  root.addEventListener(
    "touchmove",
    (event) => {
      if (!start || event.touches.length !== 1) return;
      const touch = event.touches[0];
      const dx = touch.clientX - start.x;
      const dy = touch.clientY - start.y;

      if (start.axis === null) {
        if (Math.abs(dx) < AXIS_LOCK_PX && Math.abs(dy) < AXIS_LOCK_PX) return;
        start.axis = Math.abs(dx) > Math.abs(dy) ? "x" : "y";
        // Полоса перемотки живёт своей жизнью: её тянут пальцем, и жест
        // «свернуть плеер» отсюда срабатывать не должен (совет из ТЗ владельца).
        if (start.onSlider) start = null;
        return;
      }

      if (start.axis === "x") {
        if (start.inScroller) return; // горизонтальную ленту листает она сама
        if (start.row) {
          shiftRow(start.row, dx);
          if (event.cancelable) event.preventDefault();
          return;
        }
        if (start.fromEdge || start.art || start.mini) {
          if (event.cancelable) event.preventDefault();
        }
      }
    },
    { passive: false }
  );

  root.addEventListener("touchend", (event) => {
    if (!start) return;
    const touch = event.changedTouches[0];
    const dx = touch.clientX - start.x;
    const dy = touch.clientY - start.y;
    const fast = Date.now() - start.time < FLING_MS;
    const enough = (value) => Math.abs(value) >= (fast ? FLING_MIN_PX : SWIPE_MIN_PX);
    const context = { ...start };
    if (start.row) releaseRow(start.row, enough(dx) && start.axis === "x");
    start = null;

    if (context.axis === "x") {
      if (context.row) {
        if (!enough(dx)) return;
        handlers.onRowSwipe(context.row, dx > 0 ? "right" : "left");
        return;
      }
      if (!enough(dx)) return;
      if (context.art || context.mini) {
        handlers.onTrackSwipe(dx > 0 ? "prev" : "next");
        return;
      }
      if (dx > 0 && context.fromEdge) handlers.onBack();
      return;
    }

    if (context.axis === "y") {
      if (!enough(dy)) return;
      if (dy < 0) {
        handlers.onSwipeUp(context);
        return;
      }
      handlers.onSwipeDown(context);
    }
  });

  root.addEventListener("touchcancel", reset);
}

function closest(node, selector) {
  return node && node.closest ? node.closest(selector) : null;
}

function rowUnder(node) {
  const row = closest(node, ".track-row");
  if (!row) return null;
  // Минусы (отрицательный id) и живые кандидаты («live:…») в библиотеку и
  // очередь не кладутся — свайпать их нечем.
  const id = Number(row.dataset.id);
  return Number.isFinite(id) && id > 0 ? row : null;
}

function shiftRow(row, dx) {
  const clamped = Math.max(-ROW_MAX_SHIFT, Math.min(ROW_MAX_SHIFT, dx));
  row.style.transition = "none";
  row.style.transform = `translateX(${clamped}px)`;
  row.classList.toggle("is-swiping-right", clamped > 8);
  row.classList.toggle("is-swiping-left", clamped < -8);
}

function releaseRow(row, fired) {
  row.style.transition = "transform .18s ease";
  row.style.transform = "";
  row.classList.remove("is-swiping-right", "is-swiping-left");
  if (fired) {
    row.classList.add("is-swipe-done");
    setTimeout(() => row.classList.remove("is-swipe-done"), 260);
  }
}
