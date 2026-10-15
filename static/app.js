// Family Care — client-side scripts.
// Three jobs: toggle the mobile sidebar drawer, render the sleep chart,
// render the activity chart.

(function () {
  // ---------- Mobile sidebar toggle ----------
  const toggles = document.querySelectorAll('[data-toggle="sidebar"]');
  const sidebar = document.querySelector('.sidebar');
  const overlay = document.querySelector('.sidebar-overlay');

  toggles.forEach(el => {
    el.addEventListener('click', () => {
      sidebar?.classList.toggle('open');
      overlay?.classList.toggle('open');
    });
  });

  // ---------- Charts ----------
  if (!window.Chart) return;

  const dataEl = document.getElementById('alerts-data');
  if (!dataEl) return;

  let alerts;
  try {
    alerts = JSON.parse(dataEl.textContent);
  } catch (e) {
    console.error('Could not parse alerts data', e);
    return;
  }

  // Shared chart options — same look for both charts
  function baseOptions(yMax) {
    const opts = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#3A362F',
          padding: 12,
          cornerRadius: 8,
          titleFont: { size: 13 },
          bodyFont: { size: 13 },
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#7A7368', font: { size: 11 } }
        },
        y: {
          beginAtZero: true,
          grid: { color: '#EDEAE3' },
          ticks: { color: '#7A7368', font: { size: 11 } }
        }
      }
    };
    if (yMax !== undefined) opts.scales.y.max = yMax;
    return opts;
  }

  function renderChart(canvasId, dataKey, label, color, yMax) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    new Chart(canvas, {
      type: 'line',
      data: {
        labels: alerts.map(a => a.day),
        datasets: [{
          label,
          data: alerts.map(a => a[dataKey]),
          borderColor: color,
          backgroundColor: color + '20',
          fill: true,
          tension: 0.3,
          borderWidth: 3,
          pointBackgroundColor: alerts.map(a =>
            a.status === 'unusual' ? '#D97A5F' : color
          ),
          pointBorderColor: '#fff',
          pointBorderWidth: 2,
          pointRadius: alerts.map(a => a.status === 'unusual' ? 6 : 3),
          pointHoverRadius: 8,
        }]
      },
      options: baseOptions(yMax)
    });
  }

  renderChart('sleepChart', 'sleepHours', 'Sleep hours', '#6B8F71', 10);
  renderChart('activityChart', 'movementCount', 'Activity level', '#6B8EB0');
})();