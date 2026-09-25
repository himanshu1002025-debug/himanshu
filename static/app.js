// Reads window.__alerts (embedded by the dashboard template)
// and renders a sleep-hours line chart. That's the entire
// client-side script for the project.

(function () {
  const canvas = document.getElementById('sleepChart');
  if (!canvas || !window.Chart) return;

const dataEl = document.getElementById('alerts-data');
if (!dataEl) return;
const alerts = JSON.parse(dataEl.textContent);

  new Chart(canvas, {
    type: 'line',
    data: {
      labels: alerts.map(a => a.day),
      datasets: [{
        label: 'Sleep hours',
        data: alerts.map(a => a.sleepHours),
        borderColor: '#6B8F71',
        backgroundColor: 'rgba(107, 143, 113, 0.12)',
        fill: true,
        tension: 0.3,
        borderWidth: 3,
        pointBackgroundColor: alerts.map(a =>
          a.status === 'unusual' ? '#D97A5F' : '#6B8F71'
        ),
        pointBorderColor: '#fff',
        pointBorderWidth: 2,
        pointRadius: alerts.map(a => a.status === 'unusual' ? 6 : 3),
        pointHoverRadius: 8,
      }]
    },
    options: {
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
          max: 10,
          grid: { color: '#EDEAE3' },
          ticks: { color: '#7A7368', font: { size: 11 } }
        }
      }
    }
  });
})();