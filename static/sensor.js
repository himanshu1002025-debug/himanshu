// Phone accelerometer → /api/sensor-data.
//
// Measures motion energy from DeviceMotionEvent, sends a scaled reading
// every 3 seconds. The scale is tuned so gentle hand movement lands in
// the same 80-120 range as the simulated device, so the anomaly detector
// treats both consistently.

(function () {
  let apiKey = null;
  let running = false;
  let motionHandler = null;
  let energyAccumulator = 0;
  let lastMagnitude = null;
  let lastEnergySnapshot = 0;
  let sendTimer = null;

  const statusEl = () => document.getElementById('deviceStatus');
  const logEl = () => document.getElementById('readingLog');
  const barEl = () => document.getElementById('motionBar');

  window.copySensorUrl = function (btn) {
    const code = btn.parentElement.querySelector('code');
    navigator.clipboard.writeText(code.textContent).then(() => {
      btn.textContent = 'Copied';
      setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
    });
  };

  function setStatus(text, tone) {
    const el = statusEl();
    if (!el) return;
    el.textContent = text;
    el.className = 'sensor-status';
    if (tone) el.classList.add('sensor-status-' + tone);
  }

  function addLogEntry(reading, action, ok) {
    const log = logEl();
    if (!log) return;
    const empty = log.querySelector('.reading-log-empty');
    if (empty) empty.remove();

    const row = document.createElement('div');
    row.className = 'reading-row' + (ok ? '' : ' reading-row-error');
    const time = new Date().toLocaleTimeString();
    row.innerHTML = `
      <span class="reading-time">${time}</span>
      <span class="reading-value">${reading ?? '—'}</span>
      <span class="reading-action">${action || 'failed'}</span>
    `;
    log.prepend(row);

    while (log.children.length > 12) log.lastChild.remove();
  }

  function onMotion(event) {
    const a = event.accelerationIncludingGravity;
    if (!a || a.x === null) return;

    const mag = Math.sqrt((a.x || 0) ** 2 + (a.y || 0) ** 2 + (a.z || 0) ** 2);

    if (lastMagnitude !== null) {
      energyAccumulator += Math.abs(mag - lastMagnitude);
    }
    lastMagnitude = mag;

    const bar = barEl();
    if (bar) {
      const pct = Math.min(energyAccumulator / 6, 1) * 100;
      bar.style.width = pct + '%';
    }
  }

  async function sendReading() {
    if (!running) return;

    const energy = energyAccumulator - lastEnergySnapshot;
    lastEnergySnapshot = energyAccumulator;

    const scaled = Math.round(80 + Math.min(energy * 0.9, 40));
    const reading = Math.max(0, Math.min(scaled, 100000));

    try {
      const response = await fetch('/api/sensor-data', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ apiKey, movementReading: reading })
      });
      const data = await response.json();
      if (response.ok) {
        addLogEntry(reading, data.action === 'updated' ? 'updated' : 'created', true);
      } else {
        addLogEntry(reading, data.error || 'rejected', false);
      }
    } catch (err) {
      addLogEntry(reading, 'network error', false);
    }
  }

  window.startSensor = async function () {
    apiKey = document.getElementById('apiKeyInput').value.trim();
    if (!apiKey) {
      setStatus('Please enter a device API key first.', 'error');
      return;
    }

    try {
      const info = await fetch(`/api/device-info/${encodeURIComponent(apiKey)}`);
      if (!info.ok) {
        setStatus('That API key was not recognised on the server.', 'error');
        return;
      }
      const infoData = await info.json();
      setStatus(`Connected — reporting for ${infoData.personName}.`, 'ok');
    } catch (err) {
      setStatus('Could not verify the API key (server unreachable).', 'error');
      return;
    }

    if (!('DeviceMotionEvent' in window)) {
      setStatus('This device/browser does not expose a motion sensor.', 'error');
      return;
    }

    if (typeof DeviceMotionEvent.requestPermission === 'function') {
      try {
        const result = await DeviceMotionEvent.requestPermission();
        if (result !== 'granted') {
          setStatus('Motion permission denied.', 'error');
          return;
        }
      } catch (err) {
        setStatus('Could not request motion permission.', 'error');
        return;
      }
    }

    motionHandler = onMotion;
    window.addEventListener('devicemotion', motionHandler, true);

    energyAccumulator = 0;
    lastEnergySnapshot = 0;
    lastMagnitude = null;
    running = true;

    document.getElementById('startBtn').disabled = true;
    document.getElementById('stopBtn').disabled = false;
    document.getElementById('motionBar').parentElement.parentElement.style.display = 'block';

    setStatus('Streaming motion data every 3 seconds.', 'ok');
    addLogEntry('—', 'started', true);

    sendTimer = setInterval(sendReading, 3000);
  };

  window.stopSensor = function () {
    running = false;
    if (sendTimer) clearInterval(sendTimer);
    if (motionHandler) {
      window.removeEventListener('devicemotion', motionHandler, true);
      motionHandler = null;
    }
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').disabled = true;
    const wrap = document.getElementById('motionBar');
    if (wrap) wrap.parentElement.parentElement.style.display = 'none';
    setStatus('Stopped.', null);
    addLogEntry('—', 'stopped', true);
  };
})();