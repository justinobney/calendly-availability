"use strict";

const HOURS = { start: 7, end: 19, height: 72 };
const MS_DAY = 24 * 60 * 60 * 1000;

const elements = {
  ownerName: document.querySelector("#ownerName"),
  summary: document.querySelector("#summary"),
  notice: document.querySelector("#notice"),
  calendarRegion: document.querySelector("#calendarRegion"),
  calendar: document.querySelector("#calendar"),
  weekLabel: document.querySelector("#weekLabel"),
  legend: document.querySelector("#legend"),
  previousWeek: document.querySelector("#previousWeek"),
  nextWeek: document.querySelector("#nextWeek"),
  todayButton: document.querySelector("#todayButton"),
  overlayToggle: document.querySelector("#overlayToggle"),
  doneButton: document.querySelector("#doneButton"),
  drawer: document.querySelector("#detailDrawer"),
  backdrop: document.querySelector("#drawerBackdrop"),
  closeDrawer: document.querySelector("#closeDrawer"),
  drawerTitle: document.querySelector("#drawerTitle"),
  drawerRange: document.querySelector("#drawerRange"),
  durationFilter: document.querySelector("#durationFilter"),
  drawerContent: document.querySelector("#drawerContent"),
};

let serverState = null;
let weekStart = null;
let firstAvailableWeek = null;
let showOverlay = true;
let activeSegment = null;
let selectedDuration = "any";

function parseDateKey(value) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day, 12));
}

function dateKey(value) {
  return value.toISOString().slice(0, 10);
}

function addDays(value, count) {
  return new Date(value.getTime() + count * MS_DAY);
}

function mondayFor(value) {
  const day = value.getUTCDay();
  return addDays(value, -(day === 0 ? 6 : day - 1));
}

function isoDatePart(value) {
  return value.slice(0, 10);
}

function isoMinutes(value) {
  return Number(value.slice(11, 13)) * 60 + Number(value.slice(14, 16));
}

function formatClock(value) {
  const hours = Number(value.slice(11, 13));
  const minutes = value.slice(14, 16);
  const suffix = hours >= 12 ? "PM" : "AM";
  const hour = hours % 12 || 12;
  return `${hour}:${minutes} ${suffix}`;
}

function formatDay(value, options) {
  return new Intl.DateTimeFormat(undefined, { timeZone: "UTC", ...options }).format(value);
}

function intervalsOverlap(startA, endA, startB, endB) {
  return new Date(startA) < new Date(endB) && new Date(endA) > new Date(startB);
}

function isChoiceBusy(start, end) {
  if (!showOverlay) return false;
  return serverState.overlay.busy.some((busy) => intervalsOverlap(start, end, busy.start, busy.end));
}

function rangePosition(startIso, endIso) {
  const startMinutes = Math.max(isoMinutes(startIso), HOURS.start * 60);
  const endMinutes = Math.min(isoMinutes(endIso), HOURS.end * 60);
  if (endMinutes <= startMinutes) return null;
  return {
    top: ((startMinutes - HOURS.start * 60) / 60) * HOURS.height,
    height: Math.max(16, ((endMinutes - startMinutes) / 60) * HOURS.height),
  };
}

function renderLegend() {
  elements.legend.replaceChildren();
  const items = [
    ["Available", ""],
    [serverState.overlay.label, "busy"],
  ];
  for (const [label, type] of items) {
    const item = document.createElement("span");
    item.className = "legend-item";
    const swatch = document.createElement("span");
    swatch.className = `legend-swatch ${type}`.trim();
    item.append(swatch, document.createTextNode(label));
    elements.legend.append(item);
  }
}

function renderHeader() {
  const availability = serverState.availability;
  elements.ownerName.textContent = availability.owner.name;
  const stats = availability.stats;
  const collection = availability.collection;
  const sourceDetail = collection?.mode === "live"
    ? `${collection.http_attempts} Calendly requests`
    : "saved snapshot";
  elements.summary.textContent = `${stats.available_days} open days, ${stats.unique_starts} start times, ${stats.event_types} booking links, ${sourceDetail}`;
  elements.overlayToggle.disabled = false;
  elements.previousWeek.disabled = false;
  elements.todayButton.disabled = false;
  elements.nextWeek.disabled = false;
  elements.overlayToggle.textContent = showOverlay ? "Hide my calendar" : "Show my calendar";
  renderLegend();
}

function renderCalendar() {
  if (!serverState || !weekStart) return;
  const availability = serverState.availability;
  const weekEnd = addDays(weekStart, 6);
  const sameMonth = weekStart.getUTCMonth() === weekEnd.getUTCMonth();
  elements.weekLabel.textContent = sameMonth
    ? `${formatDay(weekStart, { month: "long" })} ${weekStart.getUTCDate()}-${weekEnd.getUTCDate()}, ${weekEnd.getUTCFullYear()}`
    : `${formatDay(weekStart, { month: "short", day: "numeric" })} to ${formatDay(weekEnd, { month: "short", day: "numeric", year: "numeric" })}`;

  elements.calendar.replaceChildren();
  const head = document.createElement("div");
  head.className = "calendar-head";
  const spacer = document.createElement("div");
  spacer.className = "head-spacer";
  head.append(spacer);
  const todayKey = dateKey(new Date());
  for (let index = 0; index < 7; index += 1) {
    const day = addDays(weekStart, index);
    const dayHead = document.createElement("div");
    dayHead.className = `day-head ${dateKey(day) === todayKey ? "today" : ""}`.trim();
    dayHead.innerHTML = `<span class="day-name">${formatDay(day, { weekday: "short" })}</span><span class="day-number">${day.getUTCDate()}</span>`;
    head.append(dayHead);
  }

  const body = document.createElement("div");
  body.className = "calendar-body";
  const gutter = document.createElement("div");
  gutter.className = "time-gutter";
  for (let hour = HOURS.start; hour <= HOURS.end; hour += 1) {
    const label = document.createElement("span");
    label.className = `time-label ${hour === HOURS.start ? "first" : ""}`.trim();
    label.style.top = `${(hour - HOURS.start) * HOURS.height}px`;
    label.textContent = `${hour % 12 || 12} ${hour < 12 ? "AM" : "PM"}`;
    gutter.append(label);
  }
  body.append(gutter);

  for (let index = 0; index < 7; index += 1) {
    const day = addDays(weekStart, index);
    const key = dateKey(day);
    const column = document.createElement("div");
    column.className = "day-column";
    column.dataset.date = key;
    const segments = availability.segments.filter((segment) => isoDatePart(segment.start) === key);
    if (segments.length === 0) {
      const empty = document.createElement("span");
      empty.className = "empty-day";
      empty.textContent = "No availability";
      column.append(empty);
    }
    for (const segment of segments) {
      const position = rangePosition(segment.start, segment.end);
      if (!position) continue;
      const block = document.createElement("button");
      block.type = "button";
      block.className = "availability-block";
      block.style.top = `${position.top}px`;
      block.style.height = `${position.height}px`;
      block.setAttribute("aria-label", `Available ${formatClock(segment.start)} to ${formatClock(segment.end)}`);
      const label = document.createElement("strong");
      label.textContent = "Available";
      block.append(label);
      if (position.height >= 42) {
        const detail = document.createElement("span");
        detail.textContent = `${formatClock(segment.start)} to ${formatClock(segment.end)}`;
        block.append(detail);
      }
      block.addEventListener("click", () => openSegment(segment));
      column.append(block);
    }
    if (showOverlay) {
      const busyItems = serverState.overlay.busy.filter((busy) => isoDatePart(busy.start) === key);
      for (const busy of busyItems) {
        const position = rangePosition(busy.start, busy.end);
        if (!position) continue;
        const block = document.createElement("div");
        block.className = "busy-block";
        block.style.top = `${position.top}px`;
        block.style.height = `${position.height}px`;
        block.setAttribute("aria-label", `${busy.title}, ${formatClock(busy.start)} to ${formatClock(busy.end)}`);
        const title = document.createElement("strong");
        title.textContent = busy.title;
        block.append(title);
        if (position.height >= 42) {
          const detail = document.createElement("span");
          detail.textContent = `${formatClock(busy.start)} to ${formatClock(busy.end)}`;
          block.append(detail);
        }
        column.append(block);
      }
    }
    body.append(column);
  }
  elements.calendar.append(head, body);
}

function startsForSegment(segment) {
  const availability = serverState.availability;
  const accepted = new Set(segment.starts);
  return availability.starts.filter((item) => accepted.has(item.start));
}

function configureDurationFilter(starts) {
  const durations = [...new Set(starts.flatMap((item) => item.choices.map((choice) => choice.duration_minutes)))].sort((a, b) => a - b);
  if (selectedDuration !== "any" && !durations.includes(Number(selectedDuration))) selectedDuration = "any";
  elements.durationFilter.replaceChildren();
  const anyOption = document.createElement("option");
  anyOption.value = "any";
  anyOption.textContent = "Any length";
  elements.durationFilter.append(anyOption);
  for (const duration of durations) {
    const option = document.createElement("option");
    option.value = String(duration);
    option.textContent = `${duration} minutes`;
    elements.durationFilter.append(option);
  }
  elements.durationFilter.value = selectedDuration;
}

function renderDrawerChoices(segment) {
  const starts = startsForSegment(segment);
  const day = parseDateKey(isoDatePart(segment.start));
  elements.drawerTitle.textContent = formatDay(day, { weekday: "long", month: "long", day: "numeric" });
  elements.drawerRange.textContent = `${formatClock(segment.start)} to ${formatClock(segment.end)}`;
  elements.drawerContent.replaceChildren();

  for (const item of starts) {
    const visibleChoices = selectedDuration === "any"
      ? item.choices
      : item.choices.filter((choice) => choice.duration_minutes === Number(selectedDuration));
    if (visibleChoices.length === 0) continue;
    const group = document.createElement("section");
    group.className = "start-group";
    const heading = document.createElement("h3");
    heading.textContent = formatClock(item.start);
    group.append(heading);
    const choices = document.createElement("div");
    choices.className = "choice-list";
    for (const choice of visibleChoices) {
      const busy = isChoiceBusy(item.start, choice.end);
      const link = document.createElement("a");
      link.className = "booking-choice";
      link.href = choice.booking_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      const text = document.createElement("span");
      const name = document.createElement("span");
      name.className = "choice-name";
      name.textContent = choice.event_name;
      const meta = document.createElement("span");
      meta.className = `choice-meta ${busy ? "conflict" : ""}`.trim();
      meta.textContent = busy ? `${choice.duration_minutes} minutes, conflicts with my calendar` : `${choice.duration_minutes} minutes`;
      text.append(name, meta);
      const action = document.createElement("span");
      action.className = "choice-action";
      action.textContent = "Book";
      link.append(text, action);
      choices.append(link);
    }
    group.append(choices);
    elements.drawerContent.append(group);
  }
}

function openSegment(segment) {
  activeSegment = segment;
  const starts = startsForSegment(segment);
  configureDurationFilter(starts);
  renderDrawerChoices(segment);
  elements.backdrop.hidden = false;
  elements.drawer.classList.add("open");
  elements.drawer.setAttribute("aria-hidden", "false");
  elements.closeDrawer.focus();
}

function closeDrawer() {
  activeSegment = null;
  elements.drawer.classList.remove("open");
  elements.drawer.setAttribute("aria-hidden", "true");
  elements.backdrop.hidden = true;
}

async function stopServer() {
  elements.doneButton.disabled = true;
  elements.doneButton.textContent = "Closing";
  try {
    await fetch("/api/done", { method: "POST" });
    elements.summary.textContent = "Server stopped. You can close this tab.";
  } catch {
    elements.summary.textContent = "The local server is already stopped.";
  }
}

async function loadState() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    if (!response.ok) throw new Error(`Server returned ${response.status}`);
    serverState = await response.json();
    if (serverState.status === "loading") {
      const progress = serverState.collection_progress;
      const completed = progress?.successful_responses || 0;
      const pending = Math.max(0, (progress?.http_attempts || 0) - completed);
      elements.summary.textContent = "Collecting public availability";
      elements.notice.classList.remove("error");
      elements.notice.textContent = completed
        ? `Checking each public booking link. ${completed} requests completed${pending ? `, ${pending} in flight or retrying` : ""}.`
        : "Checking each public booking link. The calendar will appear here when collection finishes.";
      setTimeout(loadState, 800);
      return;
    }
    if (serverState.status === "error") throw new Error(serverState.error || "Availability collection failed");
    if (serverState.status !== "ready") throw new Error("Calendar data is not ready");
    const firstSegment = serverState.availability.segments[0];
    firstAvailableWeek = mondayFor(parseDateKey(isoDatePart(firstSegment.start)));
    weekStart = firstAvailableWeek;
    renderHeader();
    renderCalendar();
    elements.notice.hidden = true;
    elements.calendarRegion.hidden = false;
  } catch (error) {
    elements.summary.textContent = "Availability collection failed";
    elements.notice.classList.add("error");
    elements.notice.textContent = `Could not load the local calendar: ${error.message}`;
  }
}

async function refreshOverlay() {
  if (!serverState || serverState.status !== "ready" || document.hidden) return;
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    if (!response.ok) return;
    const nextState = await response.json();
    if (nextState.overlay.updated_at === serverState.overlay.updated_at) return;
    serverState.overlay = nextState.overlay;
    renderHeader();
    renderCalendar();
    if (activeSegment) openSegment(activeSegment);
  } catch {
    // A transient poll failure should not replace an already usable calendar.
  }
}

elements.previousWeek.addEventListener("click", () => {
  if (!weekStart) return;
  weekStart = addDays(weekStart, -7);
  closeDrawer();
  renderCalendar();
});

elements.nextWeek.addEventListener("click", () => {
  if (!weekStart) return;
  weekStart = addDays(weekStart, 7);
  closeDrawer();
  renderCalendar();
});

elements.todayButton.addEventListener("click", () => {
  if (!firstAvailableWeek) return;
  weekStart = firstAvailableWeek;
  closeDrawer();
  renderCalendar();
});

elements.overlayToggle.addEventListener("click", () => {
  showOverlay = !showOverlay;
  renderHeader();
  closeDrawer();
  renderCalendar();
});

elements.doneButton.addEventListener("click", stopServer);
elements.closeDrawer.addEventListener("click", closeDrawer);
elements.backdrop.addEventListener("click", closeDrawer);
elements.durationFilter.addEventListener("change", () => {
  selectedDuration = elements.durationFilter.value;
  if (activeSegment) renderDrawerChoices(activeSegment);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawer();
});

loadState();
setInterval(refreshOverlay, 2000);
