# Inheritance House Scenarios — Web Interface

Browser-based UI for the inheritance house scenarios (keep vs. sell & invest), with sliders and inputs for all modeling parameters and charts for deterministic and Monte Carlo results.

## Setup

From the project root (`Retirement_Calculations`):

```bash
pip install -r web_app/requirements.txt
```

(Or install `flask` and `numpy` if you already use the main script.)

## Run

From the project root:

```bash
python3 web_app/app.py
```

Then open **http://127.0.0.1:5000** in your browser.

## Features

- **Parameters** (left panel): Property & sale, Monte Carlo return assumptions, Scenario 3 (withdrawals), Scenario 4 (estate inheritance), Roth IRA and other assets. Use sliders and number inputs; changing values and clicking **Run comparison** or **Run Monte Carlo** updates results.
- **Comparison**: Deterministic net worth at benchmark years (7, 12, 17, 35), sale breakdown, and trajectory charts for all scenarios plus Roth IRA.
- **Monte Carlo**: Median and 25th–75th percentile bands for scenarios 1–4 and for **Roth IRA appreciation over time**; benchmark table of medians and S2−S1 difference.

All inputs from the terminal/prompt flow in the original script are available on the page (with defaults pre-filled).
