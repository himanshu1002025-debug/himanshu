// Connect-wearable page: handles the three-step flow and the
// "connected wearables" list.

(function () {
  let selectedBrand = null;

  function pickBrand(brand) {
    selectedBrand = brand;
    document.querySelectorAll('.wearable-card').forEach(c => {
      c.classList.toggle('selected', c.dataset.brand === brand);
    });
    document.getElementById('pickBrandName').textContent = brand;
    document.getElementById('pickPersonStep').hidden = false;
    document.getElementById('pickPersonStep').scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  document.querySelectorAll('.wearable-card').forEach(card => {
    card.addEventListener('click', () => pickBrand(card.dataset.brand));
  });

  window.confirmWearableConnect = async function () {
    const elderlyId = parseInt(document.getElementById('elderlySelect').value, 10);
    if (!selectedBrand || !elderlyId) return;

    document.getElementById('pickPersonStep').hidden = true;
    document.getElementById('connectingBrandName').textContent = selectedBrand;
    document.getElementById('connectingStep').hidden = false;
    document.getElementById('connectedStep').hidden = true;

    await new Promise(r => setTimeout(r, 1400));

    try {
      const res = await fetch('/api/connect-wearable', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brand: selectedBrand, elderlyId })
      });
      const data = await res.json();

      if (!res.ok) {
        alert(data.error || 'Could not connect wearable.');
        document.getElementById('connectingStep').hidden = true;
        document.getElementById('pickPersonStep').hidden = false;
        return;
      }

      document.getElementById('connectingStep').hidden = true;
      document.getElementById('connectedBrand').textContent = selectedBrand;
      document.getElementById('connectedKey').textContent = data.apiKey;
      document.getElementById('connectedStep').hidden = false;
      document.getElementById('connectedStep').scrollIntoView({ behavior: 'smooth', block: 'center' });

      document.querySelectorAll('.wearable-card').forEach(c => c.classList.remove('selected'));
      selectedBrand = null;

      loadConnectedWearables();
    } catch (err) {
      alert('Network error while connecting.');
      document.getElementById('connectingStep').hidden = true;
      document.getElementById('pickPersonStep').hidden = false;
    }
  };

  async function loadConnectedWearables() {
    const list = document.getElementById('connectedList');
    try {
      const res = await fetch('/api/connected-wearables');
      const data = await res.json();
      const wearables = data.wearables || [];

      if (wearables.length === 0) {
        list.innerHTML = '<p class="muted-text">No wearables connected yet. Pick a device above to get started.</p>';
        return;
      }

      list.innerHTML = wearables.map(w => `
        <div class="connected-card ${w.active ? 'connected-card-active' : ''}">
          <div class="connected-card-left">
            <div class="connected-card-brand">${w.brand}</div>
            <div class="connected-card-person">for ${w.personName}</div>
            <div class="connected-card-meta">
              ${w.active
                ? '<span class="connected-dot"></span> Live · last reading ' + (w.lastReading ?? '—')
                : 'Disconnected'}
            </div>
          </div>
          <div class="connected-card-right">
            <code class="connected-key">${w.apiKey}</code>
            ${w.active
              ? `<button class="logout-button" onclick="disconnectWearable(${w.id})">Disconnect</button>`
              : ''}
          </div>
        </div>
      `).join('');
    } catch (err) {
      list.innerHTML = '<p class="muted-text">Could not load wearables.</p>';
    }
  }

  window.disconnectWearable = async function (id) {
    if (!confirm('Disconnect this wearable? Readings will stop.')) return;
    try {
      await fetch(`/api/disconnect-wearable/${id}`, { method: 'POST' });
      loadConnectedWearables();
    } catch (err) {
      alert('Network error.');
    }
  };

  loadConnectedWearables();
  setInterval(loadConnectedWearables, 10000);
})();