const fields = [
  "UNITREE_ROBOT_IP",
  "LOW_BODY_HEIGHT",
  "NORMAL_BODY_HEIGHT",
  "CRAWL_DISTANCE_M",
  "CRAWL_SPEED_MPS",
  "MOVE_COMMAND_PERIOD_S",
  "REMOTE_FORWARD_LY",
  "REMOTE_PUBLISH_PERIOD_S",
  "KEYBOARD_AXIS_SCALE",
  "HEIGHT_STEP_M",
  "MIN_BODY_HEIGHT",
  "MAX_BODY_HEIGHT",
];

let defaults = {};
let localLogClearedAt = 0;
let keyboardActive = false;
let pressedKeys = new Set();

const statusPill = document.querySelector("#statusPill");
const taskMeta = document.querySelector("#taskMeta");
const logs = document.querySelector("#logs");
const keyboardState = document.querySelector("#keyboardState");
const leftStick = document.querySelector("#leftStick > div");
const rightStick = document.querySelector("#rightStick > div");
const leftAxis = document.querySelector("#leftAxis");
const rightAxis = document.querySelector("#rightAxis");
const targetHeight = document.querySelector("#targetHeight");
const measuredHeight = document.querySelector("#measuredHeight");
const velocityState = document.querySelector("#velocityState");
const modeState = document.querySelector("#modeState");
const motionModeState = document.querySelector("#motionModeState");
const heightCode = document.querySelector("#heightCode");
const heightLimitAlert = document.querySelector("#heightLimitAlert");
const heightSlider = document.querySelector("#heightSlider");
const heightSliderValue = document.querySelector("#heightSliderValue");
const heightSliderMin = document.querySelector("#heightSliderMin");
const heightSliderMax = document.querySelector("#heightSliderMax");
const videoState = document.querySelector("#videoState");
const videoFrame = document.querySelector(".video-frame");
const videoStream = document.querySelector("#videoStream");
const videoResolution = document.querySelector("#videoResolution");
const videoFrames = document.querySelector("#videoFrames");
const videoAge = document.querySelector("#videoAge");
let heightSliderTouched = false;
let heightSliderTimer = null;
let heightSliderLastSentAt = 0;
let heightSliderSending = false;
let heightSliderPendingValue = null;

function collectParams() {
  const params = {};
  for (const id of fields) {
    params[id] = document.querySelector(`#${id}`).value.trim();
  }
  return params;
}

function applyDefaults() {
  for (const id of fields) {
    const input = document.querySelector(`#${id}`);
    if (input && defaults[id] !== undefined) {
      input.value = defaults[id];
    }
  }
  syncHeightSliderConfig();
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || `请求失败: ${response.status}`);
  }
  return data;
}

async function runTask(task) {
  setBusy(true);
  try {
    await postJson("/api/run", { task, params: collectParams() });
  } catch (error) {
    alert(error.message);
  } finally {
    setBusy(false);
    await refreshStatus();
  }
}

async function stopTask() {
  setBusy(true);
  try {
    await postJson("/api/stop", {});
  } catch (error) {
    alert(error.message);
  } finally {
    setBusy(false);
    await refreshStatus();
  }
}

async function startKeyboard() {
  setBusy(true);
  try {
    await postJson("/api/keyboard/start", { params: collectParams() });
    keyboardActive = true;
  } catch (error) {
    alert(error.message);
  } finally {
    setBusy(false);
    await refreshStatus();
  }
}

async function stopKeyboard() {
  keyboardActive = false;
  pressedKeys.clear();
  updateStickUi({ lx: 0, ly: 0, rx: 0, ry: 0 });
  setBusy(true);
  try {
    await postJson("/api/keyboard/stop", {});
  } catch (error) {
    alert(error.message);
  } finally {
    setBusy(false);
    await refreshStatus();
  }
}

async function adjustHeight(direction) {
  if (!keyboardActive) {
    return;
  }
  try {
    const data = await postJson("/api/keyboard/height", { direction });
    if (data.limited) {
      showHeightLimit(data.message || "已经到达官方范围边界");
    } else {
      hideHeightLimit();
    }
  } catch (error) {
    alert(error.message);
  }
}

async function setHeightTarget(height) {
  if (!keyboardActive) {
    showHeightLimit("请先启动键盘遥控，再用滑动条控制高度");
    return;
  }
  try {
    const data = await postJson("/api/keyboard/height_target", { height });
    if (data.limited) {
      showHeightLimit(data.message || "已经到达偏移边界");
    } else {
      hideHeightLimit();
    }
  } catch (error) {
    alert(error.message);
  }
}

function queueHeightTarget(value) {
  heightSliderPendingValue = value;
  sendHeightTargetThrottled();
}

function sendHeightTargetThrottled() {
  if (heightSliderPendingValue === null) {
    return;
  }
  if (heightSliderSending) {
    return;
  }

  const now = performance.now();
  const delay = Math.max(0, 20 - (now - heightSliderLastSentAt));

  window.clearTimeout(heightSliderTimer);
  heightSliderTimer = window.setTimeout(async () => {
    if (heightSliderPendingValue === null || heightSliderSending) return;

    const value = heightSliderPendingValue;
    heightSliderPendingValue = null;
    heightSliderSending = true;
    heightSliderLastSentAt = performance.now();
    try {
      await setHeightTarget(value);
    } finally {
      heightSliderSending = false;
      if (heightSliderPendingValue !== null) {
        sendHeightTargetThrottled();
      }
    }
  }, delay);
}

function showHeightLimit(message) {
  heightLimitAlert.hidden = false;
  heightLimitAlert.textContent = message;
  window.clearTimeout(showHeightLimit.timer);
  showHeightLimit.timer = window.setTimeout(hideHeightLimit, 2600);
}

function hideHeightLimit() {
  heightLimitAlert.hidden = true;
  heightLimitAlert.textContent = "";
}

async function switchNormalMode() {
  setBusy(true);
  try {
    await postJson("/api/motion/normal", { params: collectParams() });
  } catch (error) {
    alert(error.message);
  } finally {
    setBusy(false);
    await refreshStatus();
  }
}

async function startVideo() {
  setBusy(true);
  try {
    await postJson("/api/video/start", { params: collectParams() });
    videoStream.src = `/api/video/stream?t=${Date.now()}`;
  } catch (error) {
    alert(error.message);
  } finally {
    setBusy(false);
    await refreshStatus();
  }
}

async function stopVideo() {
  setBusy(true);
  try {
    await postJson("/api/video/stop", {});
    videoStream.removeAttribute("src");
    videoFrame.classList.remove("streaming");
  } catch (error) {
    alert(error.message);
  } finally {
    setBusy(false);
    await refreshStatus();
  }
}

function setBusy(isBusy) {
  for (const button of document.querySelectorAll("button")) {
    button.disabled = isBusy;
  }
}

function axisFromKeys() {
  const has = (key) => pressedKeys.has(key);
  const lx = (has("d") ? 1 : 0) + (has("a") ? -1 : 0);
  const ly = (has("w") ? 1 : 0) + (has("s") ? -1 : 0);
  const rx = (has("l") ? 1 : 0) + (has("j") ? -1 : 0);
  const ry = (has("i") ? 1 : 0) + (has("k") ? -1 : 0);
  return { lx, ly, rx, ry };
}

function updateStickUi(axes) {
  const move = 56;
  leftStick.style.transform = `translate(${axes.lx * move}px, ${-axes.ly * move}px)`;
  rightStick.style.transform = `translate(${axes.rx * move}px, ${-axes.ry * move}px)`;
  leftAxis.textContent = `lx ${axes.lx.toFixed(2)} / ly ${axes.ly.toFixed(2)}`;
  rightAxis.textContent = `rx ${axes.rx.toFixed(2)} / ry ${axes.ry.toFixed(2)}`;
}

async function sendKeyboardInput() {
  const axes = axisFromKeys();
  updateStickUi(axes);
  if (!keyboardActive) {
    return;
  }
  try {
    await postJson("/api/keyboard/input", { axes });
  } catch (error) {
    keyboardActive = false;
    keyboardState.textContent = `异常: ${error.message}`;
  }
}

function fmtNumber(value, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(digits);
}

function syncHeightSliderConfig() {
  const min = Number(document.querySelector("#MIN_BODY_HEIGHT").value || defaults.MIN_BODY_HEIGHT || -0.13);
  const max = Number(document.querySelector("#MAX_BODY_HEIGHT").value || defaults.MAX_BODY_HEIGHT || 0.05);
  const step = Number(document.querySelector("#HEIGHT_STEP_M").value || defaults.HEIGHT_STEP_M || 0.01);
  heightSlider.min = String(min);
  heightSlider.max = String(max);
  heightSlider.step = String(step);
  heightSliderMin.textContent = `${min.toFixed(2)} m`;
  heightSliderMax.textContent = `${max.toFixed(2)} m`;
  const current = Number(heightSlider.value || 0);
  heightSlider.value = String(Math.max(min, Math.min(max, current)));
  heightSliderValue.textContent = `${Number(heightSlider.value).toFixed(2)} m`;
}

function fmtVelocity(value) {
  if (!Array.isArray(value)) {
    return "-";
  }
  return value.map((item) => Number(item).toFixed(2)).join(", ");
}

function renderStatus(data) {
  defaults = data.defaults || defaults;
  if (!document.body.dataset.defaultsLoaded) {
    applyDefaults();
    document.body.dataset.defaultsLoaded = "true";
  }

  statusPill.classList.toggle("running", data.running || data.keyboard?.running);
  statusPill.textContent = data.keyboard?.running ? "键盘遥控中" : (data.running ? "任务运行中" : "空闲");

  const task = data.task || "无";
  const exitCode = data.exit_code === null || data.exit_code === undefined ? "-" : data.exit_code;
  taskMeta.textContent = data.running ? `当前任务: ${task}` : `上次任务: ${task} / 退出码: ${exitCode}`;

  renderKeyboardStatus(data.keyboard || {});
  renderMotionModeStatus(data.motion_mode || {});
  renderVideoStatus(data.video || {});

  const visibleLogs = (data.logs || []).slice(localLogClearedAt);
  logs.textContent = visibleLogs.join("\n");
  logs.scrollTop = logs.scrollHeight;
}

function renderMotionModeStatus(motionMode) {
  if (motionMode.running) {
    motionModeState.textContent = "切换中";
    return;
  }
  if (motionMode.error) {
    motionModeState.textContent = `失败: ${motionMode.error}`;
    return;
  }
  const result = motionMode.last_result;
  if (!result) {
    motionModeState.textContent = "-";
    return;
  }
  motionModeState.textContent = `${result.before_mode || "-"} -> ${result.after_mode || "-"} / code ${result.set_code}`;
}

function renderVideoStatus(video) {
  if (video.error) {
    videoState.textContent = `异常: ${video.error}`;
  } else if (video.running) {
    videoState.textContent = video.connected ? "视频运行中" : "连接中";
  } else {
    videoState.textContent = "未启动";
  }

  if (video.running && !videoStream.getAttribute("src")) {
    videoStream.src = `/api/video/stream?t=${Date.now()}`;
  }
  if (video.running && video.frame_count > 0) {
    videoFrame.classList.add("streaming");
  }
  if (!video.running) {
    videoStream.removeAttribute("src");
    videoFrame.classList.remove("streaming");
  }

  const width = video.width || "-";
  const height = video.height || "-";
  videoResolution.textContent = `分辨率 ${width} x ${height}`;
  videoFrames.textContent = `帧数 ${video.frame_count || 0}`;
  videoAge.textContent = video.frame_age === null || video.frame_age === undefined
    ? "延迟 -"
    : `延迟 ${Number(video.frame_age).toFixed(2)}s`;
}

function renderKeyboardStatus(keyboard) {
  keyboardActive = Boolean(keyboard.running);
  const connected = keyboard.connected ? "已连接" : "连接中";
  keyboardState.textContent = keyboard.running ? `运行中 / ${connected}` : "未启动";
  if (keyboard.error) {
    keyboardState.textContent = `异常: ${keyboard.error}`;
  }

  const axes = keyboard.axes || { lx: 0, ly: 0, rx: 0, ry: 0 };
  if (!pressedKeys.size) {
    updateStickUi(axes);
  }

  targetHeight.textContent = `${fmtNumber(keyboard.target_height)} m`;
  if (!heightSliderTouched && keyboard.target_height !== null && keyboard.target_height !== undefined) {
    heightSlider.value = String(keyboard.target_height);
    heightSliderValue.textContent = `${Number(keyboard.target_height).toFixed(2)} m`;
  }
  measuredHeight.textContent = `${fmtNumber(keyboard.measured_height)} m`;
  heightCode.textContent = keyboard.last_height_code === null || keyboard.last_height_code === undefined
    ? "-"
    : String(keyboard.last_height_code);

  const state = keyboard.sport_state || {};
  velocityState.textContent = fmtVelocity(state.velocity);
  const mode = state.mode === null || state.mode === undefined ? "-" : state.mode;
  const gait = state.gait_type === null || state.gait_type === undefined ? "-" : state.gait_type;
  modeState.textContent = `${mode} / ${gait}`;
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status");
    renderStatus(await response.json());
  } catch (error) {
    statusPill.classList.remove("running");
    statusPill.textContent = "服务异常";
  }
}

for (const button of document.querySelectorAll("[data-task]")) {
  button.addEventListener("click", () => runTask(button.dataset.task));
}

document.querySelector("[data-action='normal-mode']").addEventListener("click", switchNormalMode);
document.querySelector("#stopTask").addEventListener("click", stopTask);
document.querySelector("#resetParams").addEventListener("click", applyDefaults);
document.querySelector("#startKeyboard").addEventListener("click", startKeyboard);
document.querySelector("#stopKeyboard").addEventListener("click", stopKeyboard);
document.querySelector("#startVideo").addEventListener("click", startVideo);
document.querySelector("#stopVideo").addEventListener("click", stopVideo);
document.querySelector("#heightUp").addEventListener("click", () => adjustHeight(1));
document.querySelector("#heightDown").addEventListener("click", () => adjustHeight(-1));
for (const id of ["MIN_BODY_HEIGHT", "MAX_BODY_HEIGHT", "HEIGHT_STEP_M"]) {
  document.querySelector(`#${id}`).addEventListener("change", syncHeightSliderConfig);
}
heightSlider.addEventListener("input", () => {
  heightSliderTouched = true;
  heightSliderValue.textContent = `${Number(heightSlider.value).toFixed(2)} m`;
  queueHeightTarget(Number(heightSlider.value));
});
heightSlider.addEventListener("change", () => {
  heightSliderTouched = false;
  queueHeightTarget(Number(heightSlider.value));
});
document.querySelector("#clearLog").addEventListener("click", () => {
  localLogClearedAt = logs.textContent ? logs.textContent.split("\n").length : 0;
  logs.textContent = "";
});

window.addEventListener("keydown", (event) => {
  const tag = event.target?.tagName?.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") {
    return;
  }

  const key = event.key.toLowerCase();
  if (["w", "a", "s", "d", "i", "j", "k", "l"].includes(key)) {
    pressedKeys.add(key);
    event.preventDefault();
  }

  if (!event.repeat && (key === "q" || event.key === "ArrowUp")) {
    event.preventDefault();
    adjustHeight(1);
  }

  if (!event.repeat && (key === "e" || event.key === "ArrowDown")) {
    event.preventDefault();
    adjustHeight(-1);
  }
});

window.addEventListener("keyup", (event) => {
  const key = event.key.toLowerCase();
  if (pressedKeys.delete(key)) {
    event.preventDefault();
  }
});

window.addEventListener("blur", () => {
  pressedKeys.clear();
  updateStickUi({ lx: 0, ly: 0, rx: 0, ry: 0 });
});

refreshStatus();
setInterval(refreshStatus, 1000);
setInterval(sendKeyboardInput, 50);
