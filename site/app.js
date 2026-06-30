const state = {
  manifest: null,
  daily: null,
  selectedDay: null,
  selectedIndex: 0,
  isPlaying: false,
  isLooping: false,
};

const els = {
  dateTitle: document.querySelector("#dateTitle"),
  refreshButton: document.querySelector("#refreshButton"),
  runMeta: document.querySelector("#runMeta"),
  countMeta: document.querySelector("#countMeta"),
  daySelect: document.querySelector("#daySelect"),
  emptyState: document.querySelector("#emptyState"),
  playerView: document.querySelector("#playerView"),
  listDate: document.querySelector("#listDate"),
  newsList: document.querySelector("#newsList"),
  sourceName: document.querySelector("#sourceName"),
  storyTitle: document.querySelector("#storyTitle"),
  sourceLink: document.querySelector("#sourceLink"),
  playButton: document.querySelector("#playButton"),
  playIcon: document.querySelector("#playIcon"),
  replayButton: document.querySelector("#replayButton"),
  autoAdvance: document.querySelector("#autoAdvance"),
  loopButton: document.querySelector("#loopButton"),
  audioPlayer: document.querySelector("#audioPlayer"),
  subtitleLines: document.querySelector("#subtitleLines"),
  chineseText: document.querySelector("#chineseText"),
};

function cacheBust(url) {
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}v=${Date.now()}`;
}

async function fetchJson(url) {
  const response = await fetch(cacheBust(url), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load ${url}: ${response.status}`);
  }
  return response.json();
}

function availableDays() {
  return [...(state.manifest?.days || [])].sort((a, b) => b.date.localeCompare(a.date));
}

function findDay(date) {
  return (state.manifest?.days || []).find((day) => day.date === date) || null;
}

async function loadLatest() {
  setStatus("Fetching latest content...", "");
  try {
    state.manifest = await fetchJson("manifest.json");
    renderDayOptions();
    if (!state.manifest.latestDataUrl) {
      renderEmpty();
      return;
    }
    await loadDay(state.manifest.latestDate);
  } catch (error) {
    renderError(error);
  }
}

async function loadDay(date) {
  const day = findDay(date);
  const dataUrl = day?.dataUrl || state.manifest?.latestDataUrl;
  if (!dataUrl) {
    renderEmpty();
    return;
  }

  setStatus(`Fetching ${day?.date || "selected day"}...`, "");
  els.audioPlayer.pause();
  state.daily = await fetchJson(dataUrl);
  state.selectedDay = day || {
    date: state.daily.date,
    dataUrl,
    itemCount: state.daily.items?.length || 0,
  };
  state.selectedIndex = 0;
  state.isPlaying = false;
  renderDayOptions();
  renderAll();
}

function selectedItem() {
  return state.daily?.items?.[state.selectedIndex] ?? null;
}

function setStatus(left, right) {
  els.runMeta.textContent = left;
  els.countMeta.textContent = right || "";
}

function renderEmpty() {
  els.dateTitle.textContent = "DailyNews";
  els.daySelect.disabled = true;
  els.emptyState.hidden = false;
  els.playerView.hidden = true;
  setStatus("No daily content has been built yet.", "");
}

function renderError(error) {
  els.emptyState.hidden = false;
  els.playerView.hidden = true;
  els.dateTitle.textContent = "DailyNews";
  setStatus(error.message, "");
}

function renderDayOptions() {
  const days = availableDays();
  els.daySelect.replaceChildren();
  days.forEach((day) => {
    const option = document.createElement("option");
    option.value = day.date;
    option.textContent = `${day.date} - ${day.itemCount || 0} stories`;
    option.selected = day.date === (state.selectedDay?.date || state.manifest?.latestDate);
    els.daySelect.append(option);
  });
  els.daySelect.disabled = days.length === 0;
}

function renderAll() {
  const daily = state.daily;
  els.emptyState.hidden = true;
  els.playerView.hidden = false;
  els.dateTitle.textContent = daily.is_demo ? `${daily.date} demo` : daily.date;
  els.listDate.textContent = daily.timezone || "";
  const itemCount = daily.items?.length ?? 0;
  const dayCount = state.manifest?.days?.length || 0;
  const historyDays = state.manifest?.settings?.historyDays || dayCount;
  setStatus(
    `${daily.timezone || state.manifest.settings?.timezone || "Local"} - ${daily.cefr_level || state.manifest.settings?.cefrLevel || "B2"}`,
    `${itemCount} ${itemCount === 1 ? "story" : "stories"} - ${dayCount}/${historyDays} days`
  );
  renderList();
  renderStory();
}

function renderList() {
  const items = state.daily.items || [];
  els.newsList.replaceChildren();
  items.forEach((item, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `story-button${index === state.selectedIndex ? " active" : ""}`;
    button.addEventListener("click", () => {
      state.selectedIndex = index;
      state.isPlaying = false;
      renderList();
      renderStory();
    });

    const number = document.createElement("div");
    number.className = "story-index";
    number.textContent = String(index + 1);

    const text = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = item.title || "Untitled story";
    const source = document.createElement("span");
    source.textContent = item.source?.name || "Unknown source";
    text.append(title, source);
    button.append(number, text);
    els.newsList.append(button);
  });
}

function renderStory() {
  const item = selectedItem();
  if (!item) {
    renderEmpty();
    return;
  }

  els.sourceName.textContent = item.source?.name || "Unknown source";
  els.storyTitle.textContent = item.title || "Untitled story";
  els.chineseText.textContent = item.chinese || "";

  if (item.source?.url) {
    els.sourceLink.hidden = false;
    els.sourceLink.href = item.source.url;
    els.sourceLink.textContent = `Source - ${item.source?.name || "Unknown source"}`;
  } else {
    els.sourceLink.hidden = true;
    els.sourceLink.removeAttribute("href");
    els.sourceLink.textContent = "Source";
  }

  loadAudioSource();
  renderSubtitles();
}

function loadAudioSource() {
  const item = selectedItem();
  const audioUrl = item?.audio?.english;
  els.audioPlayer.pause();
  state.isPlaying = false;
  els.playIcon.className = "play-symbol icon-play";
  if (audioUrl) {
    els.audioPlayer.src = audioUrl;
    els.playButton.disabled = false;
    els.replayButton.disabled = false;
  } else {
    els.audioPlayer.removeAttribute("src");
    els.playButton.disabled = true;
    els.replayButton.disabled = true;
  }
}

function renderSubtitles() {
  const item = selectedItem();
  const cues = item?.subtitles?.english || [];
  els.subtitleLines.replaceChildren();

  if (!cues.length) {
    const empty = document.createElement("p");
    empty.className = "subtitle-line";
    empty.textContent = item?.english || "";
    els.subtitleLines.append(empty);
    return;
  }

  cues.forEach((cue, index) => {
    const line = document.createElement("p");
    line.className = "subtitle-line";
    line.dataset.index = String(index);
    line.dataset.start = String(cue.start);
    line.dataset.end = String(cue.end);
    line.textContent = cue.text;
    els.subtitleLines.append(line);
  });
}

async function togglePlay() {
  if (!els.audioPlayer.src) {
    return;
  }
  if (state.isPlaying) {
    els.audioPlayer.pause();
    return;
  }
  await els.audioPlayer.play();
}

function playbackErrorMessage(error) {
  const message = error?.message || "";
  if (error?.name === "NotAllowedError" || message.includes("interact with the document")) {
    return "Tap play once to allow audio playback.";
  }
  return message || "Audio playback failed.";
}

function replayCurrent() {
  if (!els.audioPlayer.src) {
    return;
  }
  els.audioPlayer.currentTime = 0;
  els.audioPlayer.play().catch((error) => setStatus(playbackErrorMessage(error), ""));
}

function updateSubtitleHighlight() {
  const time = els.audioPlayer.currentTime;
  let activeLine = null;
  els.subtitleLines.querySelectorAll(".subtitle-line").forEach((line) => {
    const start = Number(line.dataset.start);
    const end = Number(line.dataset.end);
    const isActive = Number.isFinite(start) && Number.isFinite(end) && time >= start && time <= end;
    line.classList.toggle("active", isActive);
    if (isActive) {
      activeLine = line;
    }
  });

  if (activeLine) {
    activeLine.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function handleEnded() {
  const items = state.daily?.items || [];
  const nextIndex = state.selectedIndex + 1;
  if (items[nextIndex]) {
    if (!els.autoAdvance.checked && !state.isLooping) {
      return;
    }
    state.selectedIndex = nextIndex;
    renderList();
    renderStory();
    els.audioPlayer.play().catch((error) => setStatus(playbackErrorMessage(error), ""));
    return;
  }

  if (state.isLooping && items.length > 0) {
    state.selectedIndex = 0;
    els.autoAdvance.checked = true;
    renderList();
    renderStory();
    els.audioPlayer.play().catch((error) => setStatus(playbackErrorMessage(error), ""));
  }
}

function toggleLoop() {
  state.isLooping = !state.isLooping;
  els.loopButton.classList.toggle("active", state.isLooping);
  els.loopButton.setAttribute("aria-pressed", String(state.isLooping));
  if (state.isLooping) {
    els.autoAdvance.checked = true;
  }
}

function handleAutoAdvanceChange() {
  if (state.isLooping && !els.autoAdvance.checked) {
    state.isLooping = false;
    els.loopButton.classList.remove("active");
    els.loopButton.setAttribute("aria-pressed", "false");
  }
}

els.refreshButton.addEventListener("click", loadLatest);
els.daySelect.addEventListener("change", () => {
  loadDay(els.daySelect.value).catch((error) => renderError(error));
});
els.playButton.addEventListener("click", () => {
  togglePlay().catch((error) => setStatus(playbackErrorMessage(error), ""));
});
els.replayButton.addEventListener("click", replayCurrent);
els.loopButton.addEventListener("click", toggleLoop);
els.autoAdvance.addEventListener("change", handleAutoAdvanceChange);
els.audioPlayer.addEventListener("play", () => {
  state.isPlaying = true;
  els.playIcon.className = "play-symbol icon-pause";
});
els.audioPlayer.addEventListener("pause", () => {
  state.isPlaying = false;
  els.playIcon.className = "play-symbol icon-play";
});
els.audioPlayer.addEventListener("timeupdate", updateSubtitleHighlight);
els.audioPlayer.addEventListener("ended", handleEnded);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("service-worker.js").catch(() => {});
}

loadLatest();
