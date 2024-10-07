let growthChart;

function updateValues() {
  document.getElementById("annualValue").textContent = document.getElementById("annualContribution").value;
  document.getElementById("interestValue").textContent = document.getElementById("interestRate").value;
  document.getElementById("yearsValue").textContent = document.getElementById("years").value;

  calculateGrowth();
}

function calculateGrowth() {
  const initialContribution = parseFloat(document.getElementById("initial").value);
  const annualContribution = parseFloat(document.getElementById("annualContribution").value);
  const interestRate = parseFloat(document.getElementById("interestRate").value) / 100;
  const years = parseInt(document.getElementById("years").value);

  let balances = [];
  let total = initialContribution;

  for (let i = 0; i <= years; i++) {
    if (i > 0) {
      total = total * (1 + interestRate) + annualContribution;
    }
    balances.push(total);
  }

  document.getElementById("result").textContent = `After ${years} years, your Roth IRA will grow to $${balances[years].toFixed(2)}.`;

  plotGrowthChart(balances);
}

function plotGrowthChart(balances) {
  const years = balances.length;
  const finalBalance = balances[balances.length - 1];

  if (growthChart) {
    growthChart.destroy(); // Destroy the existing chart before creating a new one
  }

  const ctx = document.getElementById('growthChart').getContext('2d');
  
  growthChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: Array.from({ length: years }, (v, i) => i),
      datasets: [{
        label: 'Growth over Time',
        data: balances,
        fill: false,
        borderColor: 'rgb(75, 192, 192)',
        tension: 0.1
      }]
    },
    options: {
      maintainAspectRatio: true, // Maintain the set aspect ratio to avoid resizing issues
      responsive: true,
      scales: {
        x: {
          title: {
            display: true,
            text: 'Years'
          }
        },
        y: {
          title: {
            display: true,
            text: 'Balance ($)'
          }
        }
      },
      plugins: {
        annotation: {
          annotations: {
            line1: {
              type: 'line',
              yMin: finalBalance,
              yMax: finalBalance,
              borderColor: 'rgba(255, 99, 132, 0.5)',
              borderWidth: 2,
              borderDash: [6, 6],
              label: {
                content: `Final Balance: $${finalBalance.toFixed(2)}`,
                enabled: true,
                position: 'end'
              }
            }
          }
        }
      }
    }
  });
}

window.onload = calculateGrowth;
