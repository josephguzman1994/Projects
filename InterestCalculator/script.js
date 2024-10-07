let calculatorCount = 0;
const maxCalculators = 4;
let charts = [];
let summaryChart;

// Define an array of colors for the calculators
const colors = ['rgb(0, 0, 255)', 'rgb(0, 128, 0)', 'rgb(255, 0, 0)', 'rgb(255, 255, 0)'];

// Wait for Chart.js and its plugins to load
document.addEventListener('DOMContentLoaded', function () {
    if (typeof Chart === 'undefined' || typeof ChartDataLabels === 'undefined' || typeof ChartAnnotation === 'undefined') {
        console.error('Chart.js or its plugins are not loaded properly');
        return;
    }

    Chart.register(ChartAnnotation);
    Chart.register(ChartDataLabels);

    // Add the first calculator
    addCalculator();

    // Set up the formula explanation event listener
    document.getElementById('formula').addEventListener('click', explainFormula);

    // MathJax typesetting
    MathJax.typesetPromise().then(() => {
        console.log('MathJax typesetting complete');
    }).catch((err) => console.log('MathJax typesetting failed: ' + err.message));
});

window.MathJax = {
    tex: {
        inlineMath: [['$', '$'], ['\\(', '\\)']]
    },
    svg: {
        fontCache: 'global'
    }
};

function handleTitleChange(event) {
    const title = event.target;
    const calculatorId = title.closest('.calculator').id;
    updateSummaryChart();
}

function addCalculator() {
    if (calculatorCount >= maxCalculators) {
        alert("Maximum number of calculators reached!");
        return;
    }

    calculatorCount++;
    const calculatorId = `calculator${calculatorCount}`;
    const calculatorHtml = createCalculatorHtml(calculatorId);

    const container = document.getElementById('calculatorsContainer');
    const newCalculator = document.createElement('div');
    newCalculator.innerHTML = calculatorHtml;

    // Create a MutationObserver to watch for when the calculator is added to the DOM
    const observer = new MutationObserver((mutations, obs) => {
        const addedNode = mutations[0].addedNodes[0];
        if (addedNode && addedNode.id === calculatorId) {
            calculateGrowth(calculatorId);
            obs.disconnect(); // Stop observing
        }
    });

    // Start observing the container for child list changes
    observer.observe(container, { childList: true });

    container.appendChild(newCalculator.firstElementChild);

    newCalculator.querySelector('.calculator-title').addEventListener('blur', handleTitleChange);

    if (calculatorCount >= maxCalculators) {
        document.getElementById('addCalculatorBtn').style.display = 'none';
    }
}

function createCalculatorHtml(id) {
    return `
        <div class="calculator" id="${id}">
            <h2 class="calculator-title" contenteditable="true">Calculator ${calculatorCount}</h2>
            <div class="controls">
                <div class="control-group">
                    <label for="initial${id}">Initial Contribution ($):</label>
                    <input type="number" id="initial${id}" value="5000">
                </div>
                <div class="control-group">
                    <label for="annualContribution${id}">Annual Contribution ($): <span id="annualValue${id}">6000</span></label>
                    <input type="range" id="annualContribution${id}" min="0" max="50000" step="50" value="6000" oninput="updateValues('${id}')">
                </div>
                <div class="control-group">
                    <label for="interestRate${id}">Annual Interest Rate (%): <span id="interestValue${id}">7</span></label>
                    <input type="range" id="interestRate${id}" min="0" max="15" step="0.1" value="7" oninput="updateValues('${id}')">
                </div>
                <div class="control-group">
                    <label for="years${id}">Number of Years: <span id="yearsValue${id}">30</span></label>
                    <input type="range" id="years${id}" min="1" max="60" step="1" value="30" oninput="updateValues('${id}')">
                </div>
                <button onclick="calculateGrowth('${id}')">Calculate</button>
            </div>
            <h2 id="result${id}"></h2>
            <div class="chart-container">
                <canvas id="growthChart${id}"></canvas>
            </div>
        </div>
    `;
}

function updateValues(id) {
    document.getElementById(`annualValue${id}`).textContent = document.getElementById(`annualContribution${id}`).value;
    document.getElementById(`interestValue${id}`).textContent = document.getElementById(`interestRate${id}`).value;
    document.getElementById(`yearsValue${id}`).textContent = document.getElementById(`years${id}`).value;
    calculateGrowth(id);
}

function calculateGrowth(id) {
    const initialContribution = parseFloat(document.getElementById(`initial${id}`)?.value || 5000);
    const annualContribution = parseFloat(document.getElementById(`annualContribution${id}`)?.value || 6000);
    const interestRate = parseFloat(document.getElementById(`interestRate${id}`)?.value || 7) / 100;
    const years = parseInt(document.getElementById(`years${id}`)?.value || 30);

    const balances = calculateBalances(initialContribution, annualContribution, interestRate, years);

    // Calculate total personal contribution
    const totalPersonalContribution = initialContribution + (annualContribution * years);

    const resultElement = document.getElementById(`result${id}`);
    if (resultElement) {
        resultElement.innerHTML = `
            After ${years} years:<br>
            Your investment will grow to: <strong>$${balances[years].toFixed(2)}</strong><br>
            Your personal contribution: <strong>$${totalPersonalContribution.toFixed(2)}</strong><br>
            Interest earned: <strong>$${(balances[years] - totalPersonalContribution).toFixed(2)}</strong>
        `;
    }


    plotGrowthChart(balances, `growthChart${id}`, id);

    updateTotalResult();
}

function calculateBalances(initialContribution, annualContribution, interestRate, years) {
    let balances = [];
    let total = initialContribution;

    for (let i = 0; i <= years; i++) {
        if (i > 0) {
            total = total * (1 + interestRate) + annualContribution;
        }
        balances.push(total);
    }

    return balances;
}

function updateTotalResult() {
    let totalResult = 0;
    let individualResults = [];
    for (let i = 1; i <= calculatorCount; i++) {
        const calculator = document.getElementById(`calculator${i}`);
        const resultElement = calculator.querySelector(`#resultcalculator${i}`);
        const titleElement = calculator.querySelector('.calculator-title');
        if (resultElement && resultElement.textContent) {
            const result = parseFloat(resultElement.textContent.split('$')[1]);
            if (!isNaN(result)) {
                totalResult += result;
                individualResults.push({ label: titleElement.textContent, value: result });
            }
        }
    }
    document.getElementById("totalResult").textContent = `Sum of all balances: $${totalResult.toFixed(2)}`;
    updateSummaryChart(individualResults, totalResult);
}

function plotGrowthChart(balances, chartId, calculatorId) {
    const years = balances.length - 1;
    const finalBalance = balances[balances.length - 1];

    const initialContribution = parseFloat(document.getElementById(`initial${calculatorId}`)?.value || 5000);
    const annualContribution = parseFloat(document.getElementById(`annualContribution${calculatorId}`)?.value || 6000);
    const totalPersonalContribution = initialContribution + (annualContribution * years);
    const interestEarned = finalBalance - totalPersonalContribution;

    const contributionPercentage = (totalPersonalContribution / finalBalance * 100).toFixed(1);
    const interestPercentage = (interestEarned / finalBalance * 100).toFixed(1);

    if (charts[calculatorId]) {
        charts[calculatorId].destroy();
    }

    const ctx = document.getElementById(chartId).getContext('2d');
    const colorIndex = parseInt(calculatorId.replace('calculator', '')) - 1;

    charts[calculatorId] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: Array.from({ length: years + 1 }, (v, i) => i),
            datasets: [
                {
                    label: `Total Balance`,
                    data: balances,
                    borderColor: colors[colorIndex],
                    tension: 0.1,
                    fill: false
                },
                {
                    label: `Interest Earned (${interestPercentage}%)`,
                    data: balances.map(balance => Math.min(balance, finalBalance)),
                    borderColor: 'rgba(0, 128, 0, 0.5)',
                    backgroundColor: 'rgba(0, 128, 0, 0.2)',
                    fill: '+1',
                    pointRadius: 0,
                    tension: 0.1
                },
                {
                    label: `Total Contribution (${contributionPercentage}%)`,
                    data: balances.map(balance => Math.min(balance, totalPersonalContribution)),
                    borderColor: 'rgba(0, 0, 0, 0.5)',
                    backgroundColor: 'rgba(0, 0, 0, 0.1)',
                    fill: 'origin',
                    pointRadius: 0,
                    tension: 0.1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
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
                    },
                    ticks: {
                        callback: function (value, index, values) {
                            return '$' + value.toLocaleString();
                        }
                    }
                }
            },
            plugins: {
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function (context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(context.parsed.y);
                            }
                            return label;
                        }
                    }
                },
                legend: {
                    display: true,
                    position: 'top'
                }
            }
        }
    });
}

function updateSummaryChart(results, total) {
    const ctx = document.getElementById('summaryChart').getContext('2d');

    if (summaryChart) {
        summaryChart.destroy();
    }

    summaryChart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: results.map(r => r.label),
            datasets: [{
                data: results.map(r => r.value),
                backgroundColor: colors.slice(0, results.length)
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            const value = context.raw;
                            const percentage = ((value / total) * 100).toFixed(2);
                            return `$${value.toFixed(2)} (${percentage}%)`;
                        }
                    }
                },
                datalabels: {
                    formatter: (value, ctx) => {
                        const percentage = ((value / total) * 100).toFixed(2);
                        return `$${value.toFixed(2)}\n(${percentage}%)`;
                    },
                    color: '#fff',
                    textStrokeColor: '#000',
                    textStrokeWidth: 4,
                    font: {
                        weight: 'bold',
                        size: 12
                    }
                }
            }
        },
        plugins: [ChartDataLabels]
    });
}

function explainFormula() {
    const explanation = `
        Where:
        A = Final amount
        P = Initial principal balance
        r = Annual interest rate (in decimal form)
        n = Number of years
        C = Annual contribution
    `;
    alert(explanation);
}

function initializeCalculator() {
    addCalculator();
    document.getElementById('formula').addEventListener('click', explainFormula);

    setTimeout(() => {
        MathJax.typesetPromise().then(() => {
            console.log('MathJax typesetting complete');
            if (calculatorCount > 0) {
                console.log('Calculating growth for calculator1');
                calculateGrowth('calculator1');
            } else {
                console.log('No calculators added yet');
            }
        }).catch((err) => console.log('MathJax typesetting failed: ' + err.message));
    }, 100);
}