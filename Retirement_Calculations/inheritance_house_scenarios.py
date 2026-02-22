#!/usr/bin/env python3
"""
Inheritance House Scenarios: Keep vs. Sell & Invest

Models net worth under two scenarios after inheriting a Eugene, OR property:
- Scenario 1: Keep the house and live in it (home appreciation only).
- Scenario 2: Sell after 2 years (securing the $500k primary-residence exclusion),
  set aside 25% for housing/moving, invest 75% in diversified ETFs (e.g. VOO/VTI).

Compares net worth at 7, 12, 17, and 35 years (retirement), with visualizations.

Monte Carlo: When numpy is available, runs a sequence-of-returns simulation for both
the house (keep scenario) and the sale-invest scenario (stocks after sale). Displays
median path (solid line) and 1-sigma band (transparent), and prints difference of
medians at benchmark years. Stock: configurable expected return and std (e.g. 8%/17%).
House: configurable expected return and std (e.g. 0.5%/8%; short-term often <1%).

Tax note: Inherited property typically receives a step-up in basis to FMV at death.
Living in the home 2 years qualifies for the $500k (married) primary-residence
exclusion. This script assumes no federal capital gains tax on the year-2 sale;
adjust if your situation differs.
"""

import csv
import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None

try:
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# Reuse formatting from retirement calculator when available
try:
    from retirement_calculator import format_currency
except ImportError:
    def format_currency(amount: float) -> str:
        return f"${amount:,.2f}"


# ---------------------------------------------------------------------------
# Parameters (Eugene, OR inheritance hypothetical)
# ---------------------------------------------------------------------------

@dataclass
class HouseScenarioParams:
    """Configurable parameters for the inheritance house scenarios."""
    # Property
    home_value_today: float = 864_000
    years_live_in_before_sale: int = 2
    # Scenario 2: sale and allocation
    pct_cash_reserve: float = 0.25   # 25% for housing elsewhere + sinking fund
    pct_invest: float = 0.75         # 75% into ETFs
    selling_costs_pct: float = 0.06  # e.g. 6% (commission + closing)
    # Sale: tax assumptions (at point of sale)
    basis_at_sale: Optional[float] = None  # cost basis at sale; None = use home_value_today (stepped-up)
    primary_residence_exclusion: float = 500_000  # $500k exclusion (married)
    capital_gains_tax_rate: float = 0.0  # federal rate on taxable gain; 0 = none after exclusion
    # Growth assumptions (deterministic fallback)
    home_appreciation_rate: float = 0.004  # conservative; e.g. 0.4% (Zillow 1-yr style)
    home_return_sequence: Optional[Tuple[float, ...]] = None  # per-year returns; if set, overrides rate for those years
    investment_return_rate: float = 0.07    # e.g. VOO/VTI long-term nominal
    cash_reserve_return_rate: float = 0.02  # savings / high-yield
    # Monte Carlo: sequence of returns (annual)
    mc_n_paths: int = 10000                  # number of simulation paths
    stock_return_mean: float = 0.08          # expected annual return (e.g. 8%)
    stock_return_std: float = 0.17          # annual volatility (e.g. 17%)
    house_return_mean: float = 0.005        # expected annual house return (0.5%; short-term often <1%)
    house_return_std: float = 0.08          # annual house volatility (e.g. 8%)
    use_fat_tails: bool = False             # if True, sample returns from Student-t (fatter tails)
    fat_tail_df: float = 5.0                # Student-t degrees of freedom; lower = fatter tails
    # Scenario 3: same as Scenario 2 but withdraw from portfolio from given year
    withdrawal_start_year: int = 17         # start 2% withdrawals at this year
    withdrawal_rate: float = 0.02           # annual withdrawal rate (e.g. 2%)
    # Scenario 4: projected value of estate inheritance only (no addition of Scenario 2)
    include_scenario_4: bool = True
    inheritance_portfolio_today: float = 9_000_000   # mother's portfolio value today
    inheritance_growth_rate: float = 0.045           # deterministic: growth until receipt (e.g. 4.5%)
    inheritance_return_mean: float = 0.05           # Monte Carlo: mean annual return (e.g. 5%)
    inheritance_return_std: float = 0.14            # Monte Carlo: volatility (e.g. 14%)
    inheritance_years_until_receipt: int = 24       # years from today when inheritance is received
    inheritance_beneficiary_share: float = 1.0 / 3  # your share (e.g. 1/3 with two sisters)
    # Benchmark years from today (35 = retirement); inheritance_years_until_receipt added when S4 included
    benchmark_years: Tuple[int, ...] = (7, 12, 17, 35)
    # Reporting assumption: convert nominal results to today's dollars
    inflation_rate: float = 0.03
    retirement_income_rate: float = 0.045  # annual income-equivalent rule (e.g. 4.5%)
    es_tail_pct: float = 0.05  # expected shortfall tail (e.g. 5% worst outcomes)
    # Other assets (common to all scenarios): Roth IRA + other house
    roth_balance_today: float = 35_500
    roth_annual_contribution: float = 7_000
    roth_contribution_years: int = 35  # contribute through this year (e.g. until retirement)
    other_house_value_today: float = 316_000
    other_house_mortgage_remaining: float = 140_748
    other_house_mortgage_payoff_years: float = 20.0  # years to pay off (linear payoff assumed)
    other_house_appreciation_rate: float = 0.004  # same as home_appreciation_rate default


# ---------------------------------------------------------------------------
# House value growth (single rate or sequence of returns)
# ---------------------------------------------------------------------------

def _house_value_multiplier(params: HouseScenarioParams, years_from_today: int) -> float:
    """
    Multiplier for home value over N years.
    If home_return_sequence is set, use those annual returns for the first len(sequence) years,
    then use home_appreciation_rate for remaining years. Otherwise use (1 + rate)^years.
    """
    if years_from_today <= 0:
        return 1.0
    if params.home_return_sequence:
        mult = 1.0
        for i in range(min(years_from_today, len(params.home_return_sequence))):
            mult *= 1.0 + params.home_return_sequence[i]
        for _ in range(years_from_today - len(params.home_return_sequence)):
            mult *= 1.0 + params.home_appreciation_rate
        return mult
    return (1.0 + params.home_appreciation_rate) ** years_from_today


# ---------------------------------------------------------------------------
# Scenario 1: Keep the house
# ---------------------------------------------------------------------------

def scenario1_net_worth_at_year(
    params: HouseScenarioParams,
    years_from_today: int
) -> float:
    """Net worth at a given year if you keep the house (home value only)."""
    return params.home_value_today * _house_value_multiplier(params, years_from_today)


def scenario1_trajectory(
    params: HouseScenarioParams,
    max_years: int
) -> Tuple[List[int], List[float]]:
    """Year-by-year net worth for Scenario 1 (keep house)."""
    years = list(range(max_years + 1))
    values = [scenario1_net_worth_at_year(params, y) for y in years]
    return years, values


# ---------------------------------------------------------------------------
# Scenario 2: Sell after 2 years, 25% cash / 75% invest
# ---------------------------------------------------------------------------

def _sale_price_at_year(params: HouseScenarioParams, years_from_today: int) -> float:
    """Estimated sale price if sold at end of given year (uses sequence or rate)."""
    return params.home_value_today * _house_value_multiplier(params, years_from_today)


def sale_costs_breakdown(params: HouseScenarioParams) -> dict:
    """
    Total costs at point of sale (year 2): selling costs + capital gains tax.
    Returns dict with sale_price, selling_costs_dollars, taxable_gain, cap_gains_tax, net_proceeds.
    """
    sale_price = _sale_price_at_year(params, params.years_live_in_before_sale)
    selling_costs_dollars = sale_price * params.selling_costs_pct
    basis = params.basis_at_sale if params.basis_at_sale is not None else params.home_value_today
    gain_before_exclusion = max(0.0, sale_price - basis)
    taxable_gain = max(0.0, gain_before_exclusion - params.primary_residence_exclusion)
    cap_gains_tax = taxable_gain * params.capital_gains_tax_rate
    net_proceeds = sale_price - selling_costs_dollars - cap_gains_tax
    return {
        "sale_price": sale_price,
        "selling_costs_dollars": selling_costs_dollars,
        "basis": basis,
        "gain_before_exclusion": gain_before_exclusion,
        "taxable_gain": taxable_gain,
        "cap_gains_tax": cap_gains_tax,
        "net_proceeds": net_proceeds,
        "total_costs_at_sale": selling_costs_dollars + cap_gains_tax,
    }


def scenario2_proceeds_after_sale(params: HouseScenarioParams) -> float:
    """Net proceeds from selling at end of year 2 (after selling costs and tax)."""
    return sale_costs_breakdown(params)["net_proceeds"]


def scenario2_net_worth_at_year(
    params: HouseScenarioParams,
    years_from_today: int
) -> float:
    """
    Net worth at a given year if you sell after 2 years:
    - Before year 2: we still model as "if you sold at this point" for comparison,
      but the script treats sale as happening at year 2. So before year 2 we show
      home value (same as Scenario 1).
    - At/after year 2: cash reserve (25%) + investment (75%), each grown from year 2.
    """
    if years_from_today <= params.years_live_in_before_sale:
        return scenario1_net_worth_at_year(params, years_from_today)

    net_proceeds = scenario2_proceeds_after_sale(params)
    cash_portion = net_proceeds * params.pct_cash_reserve
    invest_portion = net_proceeds * params.pct_invest

    years_growth = years_from_today - params.years_live_in_before_sale
    cash_value = cash_portion * ((1 + params.cash_reserve_return_rate) ** years_growth)
    invest_value = invest_portion * ((1 + params.investment_return_rate) ** years_growth)
    return cash_value + invest_value


def scenario2_trajectory(
    params: HouseScenarioParams,
    max_years: int
) -> Tuple[List[int], List[float]]:
    """Year-by-year net worth for Scenario 2 (sell after 2 years)."""
    years = list(range(max_years + 1))
    values = [scenario2_net_worth_at_year(params, y) for y in years]
    return years, values


def scenario2_trajectory_breakdown(
    params: HouseScenarioParams,
    max_years: int
) -> Tuple[List[int], List[float], List[float], List[float]]:
    """Year-by-year net worth for Scenario 2 split into cash bucket and investment bucket."""
    years = list(range(max_years + 1))
    total_list: List[float] = []
    cash_list: List[float] = []
    invest_list: List[float] = []
    for y in years:
        if y <= params.years_live_in_before_sale:
            total_list.append(scenario1_net_worth_at_year(params, y))
            cash_list.append(0.0)   # no cash/invest buckets until after sale
            invest_list.append(0.0)
            continue
        net_proceeds = scenario2_proceeds_after_sale(params)
        cash_portion = net_proceeds * params.pct_cash_reserve
        invest_portion = net_proceeds * params.pct_invest
        years_growth = y - params.years_live_in_before_sale
        cash_val = cash_portion * ((1 + params.cash_reserve_return_rate) ** years_growth)
        invest_val = invest_portion * ((1 + params.investment_return_rate) ** years_growth)
        cash_list.append(cash_val)
        invest_list.append(invest_val)
        total_list.append(cash_val + invest_val)
    return years, total_list, cash_list, invest_list


# ---------------------------------------------------------------------------
# Scenario 3: Sell & invest, then 2% withdrawals from year 17
# ---------------------------------------------------------------------------

def scenario3_trajectory_and_withdrawals(
    params: HouseScenarioParams,
    max_years: int
) -> Tuple[List[int], List[float], List[float], List[float], List[float]]:
    """
    Year-by-year net worth for Scenario 3 (sell after 2 years, then withdraw 2%/yr from year 17).
    Returns (years, total_list, cash_list, invest_list, withdrawal_by_year).
    withdrawal_by_year[i] = dollar amount withdrawn in that year (0 before withdrawal_start_year).
    """
    years = list(range(max_years + 1))
    total_list: List[float] = []
    cash_list: List[float] = []
    invest_list: List[float] = []
    withdrawal_by_year: List[float] = [0.0] * (max_years + 1)
    sale_year = params.years_live_in_before_sale
    withdraw_start = params.withdrawal_start_year
    w_rate = params.withdrawal_rate

    for y in years:
        if y <= sale_year:
            total_list.append(scenario1_net_worth_at_year(params, y))
            cash_list.append(0.0)
            invest_list.append(0.0)
            continue
        if y == sale_year + 1:
            net_proceeds = scenario2_proceeds_after_sale(params)
            cash_p = net_proceeds * params.pct_cash_reserve * (1.0 + params.cash_reserve_return_rate)
            invest_p = net_proceeds * params.pct_invest * (1.0 + params.investment_return_rate)
        else:
            if y >= withdraw_start:
                total_beg = cash_p + invest_p
                withdrawal_by_year[y] = w_rate * total_beg
                remaining = total_beg - withdrawal_by_year[y]
                cash_p = (remaining * params.pct_cash_reserve) * (1.0 + params.cash_reserve_return_rate)
                invest_p = (remaining * params.pct_invest) * (1.0 + params.investment_return_rate)
            else:
                years_growth = y - (sale_year + 1)
                cash_p = (net_proceeds * params.pct_cash_reserve) * ((1.0 + params.cash_reserve_return_rate) ** (years_growth + 1))
                invest_p = (net_proceeds * params.pct_invest) * ((1.0 + params.investment_return_rate) ** (years_growth + 1))
        cash_list.append(cash_p)
        invest_list.append(invest_p)
        total_list.append(cash_p + invest_p)

    return years, total_list, cash_list, invest_list, withdrawal_by_year


def scenario3_net_worth_at_year(params: HouseScenarioParams, years_from_today: int) -> float:
    """Net worth at a given year for Scenario 3 (sell & invest, then 2% withdrawals from year 17)."""
    max_year = max(params.benchmark_years)
    _, total_list, _, _, _ = scenario3_trajectory_and_withdrawals(params, max_year)
    return total_list[years_from_today] if years_from_today <= max_year else total_list[-1]


# ---------------------------------------------------------------------------
# Scenario 4: projected value of estate inheritance only (no Scenario 2)
# ---------------------------------------------------------------------------

def _inheritance_received_at_receipt(params: HouseScenarioParams) -> float:
    """Your share of the estate when received (portfolio grows at inheritance_growth_rate until receipt year)."""
    R = params.inheritance_years_until_receipt
    portfolio_at_receipt = params.inheritance_portfolio_today * ((1.0 + params.inheritance_growth_rate) ** R)
    return params.inheritance_beneficiary_share * portfolio_at_receipt


def _inheritance_value_at_year(params: HouseScenarioParams, years_from_today: int) -> float:
    """Inheritance component of net worth at year t: your share of the portfolio growing at inheritance_growth_rate every year (no split/reinvest at receipt)."""
    if not params.include_scenario_4 or years_from_today < 0:
        return 0.0
    return (
        params.inheritance_beneficiary_share
        * params.inheritance_portfolio_today
        * ((1.0 + params.inheritance_growth_rate) ** years_from_today)
    )


def scenario4_net_worth_at_year(params: HouseScenarioParams, years_from_today: int) -> float:
    """Net worth at a given year for Scenario 4 (projected inheritance value only)."""
    if not params.include_scenario_4:
        return 0.0
    return _inheritance_value_at_year(params, years_from_today)


def scenario4_trajectory(params: HouseScenarioParams, max_years: int) -> Tuple[List[int], List[float]]:
    """Year-by-year net worth for Scenario 4 (inheritance value only)."""
    years = list(range(max_years + 1))
    if not params.include_scenario_4:
        return years, [0.0] * (max_years + 1)
    vals4 = [_inheritance_value_at_year(params, y) for y in years]
    return years, vals4


# ---------------------------------------------------------------------------
# Other assets: Roth IRA + other house (common to all scenarios)
# ---------------------------------------------------------------------------

def roth_balance_at_year(params: HouseScenarioParams, years_from_today: int, return_rate: float) -> float:
    """Roth balance at end of year t: prior balance * (1+rate) + contribution (if still contributing). Uses given return_rate (e.g. investment_return_rate)."""
    if years_from_today < 0:
        return 0.0
    balance = params.roth_balance_today
    for t in range(years_from_today):
        balance = balance * (1.0 + return_rate)
        if t < params.roth_contribution_years:
            balance += params.roth_annual_contribution
    return balance


def other_house_equity_at_year(params: HouseScenarioParams, years_from_today: int) -> float:
    """Other house equity at end of year t: value (appreciated) minus mortgage balance (linear payoff)."""
    if years_from_today < 0:
        return 0.0
    value = params.other_house_value_today * ((1.0 + params.other_house_appreciation_rate) ** years_from_today)
    payoff_per_year = params.other_house_mortgage_remaining / max(1.0, params.other_house_mortgage_payoff_years)
    balance = max(0.0, params.other_house_mortgage_remaining - years_from_today * payoff_per_year)
    return max(0.0, value - balance)


def roth_trajectory(params: HouseScenarioParams, max_years: int) -> Tuple[List[int], List[float]]:
    """Year-by-year Roth balance (deterministic, uses investment_return_rate)."""
    years = list(range(max_years + 1))
    vals = [roth_balance_at_year(params, y, params.investment_return_rate) for y in years]
    return years, vals


def other_house_equity_trajectory(params: HouseScenarioParams, max_years: int) -> Tuple[List[int], List[float]]:
    """Year-by-year other house equity (deterministic)."""
    years = list(range(max_years + 1))
    vals = [other_house_equity_at_year(params, y) for y in years]
    return years, vals


# ---------------------------------------------------------------------------
# Monte Carlo: sequence of returns
# ---------------------------------------------------------------------------

def _net_proceeds_from_sale(
    sale_price: float,
    params: HouseScenarioParams,
) -> float:
    """Net proceeds after selling costs and capital gains tax."""
    selling_costs = sale_price * params.selling_costs_pct
    basis = params.basis_at_sale if params.basis_at_sale is not None else params.home_value_today
    gain = max(0.0, sale_price - basis)
    taxable_gain = max(0.0, gain - params.primary_residence_exclusion)
    cap_gains_tax = taxable_gain * params.capital_gains_tax_rate
    return sale_price - selling_costs - cap_gains_tax


def run_monte_carlo(params: HouseScenarioParams, seed: Optional[int] = None) -> dict:
    """
    Run Monte Carlo simulation with sequence of returns for house and (after sale) stocks.
    Returns for each year: median, 25th and 75th percentiles (quartiles) for all three scenarios.
    Scenario 3: same as Scenario 2 but withdraw withdrawal_rate from start of withdrawal_start_year each year.
    """
    if not NUMPY_AVAILABLE:
        return {}
    rng = np.random.default_rng(seed)
    benchmark_years = _effective_benchmark_years(params)
    max_year = max(benchmark_years)
    n_paths = params.mc_n_paths
    sale_year = params.years_live_in_before_sale
    tail_df = max(2.1, float(params.fat_tail_df))
    es_alpha = min(0.5, max(0.001, float(params.es_tail_pct)))

    def sample_returns(mean: float, std: float) -> "np.ndarray":
        """Sample annual returns using Normal or Student-t with matched mean/std."""
        if params.use_fat_tails:
            # Standard t(df) has variance df/(df-2); rescale to unit variance before applying std.
            z = rng.standard_t(df=tail_df, size=(n_paths, max_year + 1))
            z = z * math.sqrt((tail_df - 2.0) / tail_df)
            out = mean + std * z
        else:
            out = rng.normal(mean, std, size=(n_paths, max_year + 1))
        return np.clip(out, -0.99, 2.0)

    # Pre-sample all returns: [path, year]
    house_returns = sample_returns(params.house_return_mean, params.house_return_std)
    stock_returns = sample_returns(params.stock_return_mean, params.stock_return_std)

    s1_paths = np.zeros((n_paths, max_year + 1))
    s2_paths = np.zeros((n_paths, max_year + 1))

    for p in range(n_paths):
        # Scenario 1: house value only
        val = params.home_value_today
        for t in range(max_year + 1):
            s1_paths[p, t] = val
            if t < max_year:
                val = val * (1.0 + house_returns[p, t])

        # Scenario 2: house until sale, then cash + investment
        house_val = params.home_value_today
        for t in range(sale_year + 1):
            s2_paths[p, t] = house_val
            if t < sale_year:
                house_val = house_val * (1.0 + house_returns[p, t])
        sale_price = house_val
        net_proceeds = _net_proceeds_from_sale(sale_price, params)
        cash_portion = net_proceeds * params.pct_cash_reserve
        invest_portion = net_proceeds * params.pct_invest
        for t in range(sale_year + 1, max_year + 1):
            years_growth = t - (sale_year + 1)  # years since sale
            cash_val = cash_portion * ((1 + params.cash_reserve_return_rate) ** (years_growth + 1))
            invest_val = invest_portion
            for y in range(sale_year + 1, t + 1):
                invest_val = invest_val * (1.0 + stock_returns[p, y])
            s2_paths[p, t] = cash_val + invest_val

    s3_paths = np.zeros((n_paths, max_year + 1))
    withdraw_start = params.withdrawal_start_year
    w_rate = params.withdrawal_rate

    for p in range(n_paths):
        # Scenario 3: same as Scenario 2 until withdrawal_start_year; then withdraw w_rate of beginning-of-year balance each year
        house_val = params.home_value_today
        for t in range(sale_year + 1):
            s3_paths[p, t] = house_val
            if t < sale_year:
                house_val = house_val * (1.0 + house_returns[p, t])
        sale_price = house_val  # same as Scenario 2: sell at end of year sale_year
        net_proceeds = _net_proceeds_from_sale(sale_price, params)
        cash_p = net_proceeds * params.pct_cash_reserve
        invest_p = net_proceeds * params.pct_invest
        for t in range(sale_year + 1, max_year + 1):
            if t >= withdraw_start:  # first withdrawal at start of year withdraw_start
                total_beg = cash_p + invest_p
                remaining = (1.0 - w_rate) * total_beg
                cash_p = (remaining * params.pct_cash_reserve) * (1.0 + params.cash_reserve_return_rate)
                invest_p = (remaining * params.pct_invest) * (1.0 + stock_returns[p, t])
            else:
                cash_p = cash_p * (1.0 + params.cash_reserve_return_rate)
                invest_p = invest_p * (1.0 + stock_returns[p, t])
            s3_paths[p, t] = cash_p + invest_p

    # Scenario 4: inheritance value only (no S2); portfolio grows at inheritance_return mean/std
    s4_paths = np.zeros((n_paths, max_year + 1))
    if params.include_scenario_4:
        inheritance_returns = sample_returns(params.inheritance_return_mean, params.inheritance_return_std)
        for p in range(n_paths):
            port_val = params.inheritance_portfolio_today
            for t in range(max_year + 1):
                inv_value = params.inheritance_beneficiary_share * port_val
                s4_paths[p, t] = inv_value
                if t < max_year:
                    port_val = port_val * (1.0 + inheritance_returns[p, t])

    # Roth IRA: each path grows with stock_returns; contribute for first roth_contribution_years
    roth_paths = np.zeros((n_paths, max_year + 1))
    for p in range(n_paths):
        balance = float(params.roth_balance_today)
        for t in range(max_year + 1):
            roth_paths[p, t] = balance
            if t < max_year:
                balance = balance * (1.0 + stock_returns[p, t])
                if t < params.roth_contribution_years:
                    balance += params.roth_annual_contribution
    roth_median = np.median(roth_paths, axis=0)
    benchmark_roth_median = {y: float(roth_median[y]) for y in benchmark_years}
    # Other house: deterministic (same for all paths)
    benchmark_other_house_equity = {y: other_house_equity_at_year(params, y) for y in benchmark_years}

    years = list(range(max_year + 1))
    def summarize_paths(paths: "np.ndarray") -> Dict[str, "np.ndarray"]:
        p10 = np.percentile(paths, 10, axis=0)
        p25 = np.percentile(paths, 25, axis=0)
        p75 = np.percentile(paths, 75, axis=0)
        median = np.median(paths, axis=0)
        k = max(1, int(math.ceil(es_alpha * paths.shape[0])))
        sorted_paths = np.sort(paths, axis=0)
        es = np.mean(sorted_paths[:k, :], axis=0)
        return {"median": median, "p10": p10, "p25": p25, "p75": p75, "es": es}

    s1_stats = summarize_paths(s1_paths)
    s2_stats = summarize_paths(s2_paths)
    s3_stats = summarize_paths(s3_paths)
    s4_stats = summarize_paths(s4_paths) if params.include_scenario_4 else {
        "median": np.zeros(max_year + 1),
        "p10": np.zeros(max_year + 1),
        "p25": np.zeros(max_year + 1),
        "p75": np.zeros(max_year + 1),
        "es": np.zeros(max_year + 1),
    }
    s1_median, s1_p10, s1_p25, s1_p75, s1_es = s1_stats["median"], s1_stats["p10"], s1_stats["p25"], s1_stats["p75"], s1_stats["es"]
    s2_median, s2_p10, s2_p25, s2_p75, s2_es = s2_stats["median"], s2_stats["p10"], s2_stats["p25"], s2_stats["p75"], s2_stats["es"]
    s3_median, s3_p10, s3_p25, s3_p75, s3_es = s3_stats["median"], s3_stats["p10"], s3_stats["p25"], s3_stats["p75"], s3_stats["es"]
    s4_median, s4_p10, s4_p25, s4_p75, s4_es = s4_stats["median"], s4_stats["p10"], s4_stats["p25"], s4_stats["p75"], s4_stats["es"]

    benchmark_median1 = {y: float(s1_median[y]) for y in benchmark_years}
    benchmark_median2 = {y: float(s2_median[y]) for y in benchmark_years}
    benchmark_median3 = {y: float(s3_median[y]) for y in benchmark_years}
    benchmark_median4 = {y: float(s4_median[y]) for y in benchmark_years} if params.include_scenario_4 else {}
    benchmark_p10_1 = {y: float(s1_p10[y]) for y in benchmark_years}
    benchmark_p10_2 = {y: float(s2_p10[y]) for y in benchmark_years}
    benchmark_p10_3 = {y: float(s3_p10[y]) for y in benchmark_years}
    benchmark_p10_4 = {y: float(s4_p10[y]) for y in benchmark_years} if params.include_scenario_4 else {}
    benchmark_es_1 = {y: float(s1_es[y]) for y in benchmark_years}
    benchmark_es_2 = {y: float(s2_es[y]) for y in benchmark_years}
    benchmark_es_3 = {y: float(s3_es[y]) for y in benchmark_years}
    benchmark_es_4 = {y: float(s4_es[y]) for y in benchmark_years} if params.include_scenario_4 else {}
    diff_medians = {y: benchmark_median2[y] - benchmark_median1[y] for y in benchmark_years}

    out = {
        "params": params,
        "years": years,
        "s1_median": s1_median,
        "s1_p10": s1_p10,
        "s1_p25": s1_p25,
        "s1_p75": s1_p75,
        "s1_es": s1_es,
        "s2_median": s2_median,
        "s2_p10": s2_p10,
        "s2_p25": s2_p25,
        "s2_p75": s2_p75,
        "s2_es": s2_es,
        "s3_median": s3_median,
        "s3_p10": s3_p10,
        "s3_p25": s3_p25,
        "s3_p75": s3_p75,
        "s3_es": s3_es,
        "benchmark_years": list(benchmark_years),
        "benchmark_median1": benchmark_median1,
        "benchmark_median2": benchmark_median2,
        "benchmark_median3": benchmark_median3,
        "benchmark_p10_1": benchmark_p10_1,
        "benchmark_p10_2": benchmark_p10_2,
        "benchmark_p10_3": benchmark_p10_3,
        "benchmark_es_1": benchmark_es_1,
        "benchmark_es_2": benchmark_es_2,
        "benchmark_es_3": benchmark_es_3,
        "diff_medians": diff_medians,
        "n_paths": n_paths,
    }
    if params.include_scenario_4:
        out["s4_median"] = s4_median
        out["s4_p10"] = s4_p10
        out["s4_p25"] = s4_p25
        out["s4_p75"] = s4_p75
        out["s4_es"] = s4_es
        out["benchmark_median4"] = benchmark_median4
        out["benchmark_p10_4"] = benchmark_p10_4
        out["benchmark_es_4"] = benchmark_es_4
    out["benchmark_roth_median"] = benchmark_roth_median
    out["benchmark_other_house_equity"] = benchmark_other_house_equity
    roth_stats = summarize_paths(roth_paths)
    out["roth_median"] = roth_stats["median"]
    out["roth_p10"] = roth_stats["p10"]
    out["roth_p25"] = roth_stats["p25"]
    out["roth_p75"] = roth_stats["p75"]
    out["roth_es"] = roth_stats["es"]
    out["benchmark_roth_p10"] = {y: float(roth_stats["p10"][y]) for y in benchmark_years}
    out["benchmark_roth_es"] = {y: float(roth_stats["es"][y]) for y in benchmark_years}
    out["es_tail_pct"] = es_alpha
    return out


# ---------------------------------------------------------------------------
# Comparison and formatting
# ---------------------------------------------------------------------------

def _effective_benchmark_years(params: HouseScenarioParams) -> Tuple[int, ...]:
    """Benchmark years including inheritance receipt year when Scenario 4 is included."""
    if not params.include_scenario_4:
        return params.benchmark_years
    R = params.inheritance_years_until_receipt
    return tuple(sorted(set(params.benchmark_years) | {R}))


def run_comparison(params: HouseScenarioParams) -> dict:
    """Compute net worth for all scenarios at benchmark years and max year."""
    benchmark_years = _effective_benchmark_years(params)
    max_year = max(benchmark_years)
    traj2_years, traj2_total, traj2_cash, traj2_invest = scenario2_trajectory_breakdown(params, max_year)
    traj3_years, traj3_total, traj3_cash, traj3_invest, traj3_withdrawals = scenario3_trajectory_and_withdrawals(params, max_year)
    traj4_years, traj4_total = scenario4_trajectory(params, max_year)
    roth_years, roth_vals = roth_trajectory(params, max_year)
    other_house_years, other_house_vals = other_house_equity_trajectory(params, max_year)
    results = {
        "params": params,
        "benchmark_years": list(benchmark_years),
        "scenario1": {},
        "scenario2": {},
        "scenario3": {},
        "scenario4": {},
        "difference": {},   # scenario2 - scenario1
        "trajectory1": scenario1_trajectory(params, max_year),
        "trajectory2": (traj2_years, traj2_total),
        "trajectory2_cash": traj2_cash,
        "trajectory2_invest": traj2_invest,
        "trajectory3": (traj3_years, traj3_total),
        "trajectory3_cash": traj3_cash,
        "trajectory3_invest": traj3_invest,
        "trajectory3_withdrawals": traj3_withdrawals,
        "trajectory4": (traj4_years, traj4_total),
        "trajectory_roth": (roth_years, roth_vals),
        "trajectory_other_house_equity": (other_house_years, other_house_vals),
        "sale_costs_breakdown": sale_costs_breakdown(params),
    }
    roth_by_year = dict(zip(roth_years, roth_vals))
    other_house_by_year = dict(zip(other_house_years, other_house_vals))
    for y in benchmark_years:
        nw1 = scenario1_net_worth_at_year(params, y)
        nw2 = scenario2_net_worth_at_year(params, y)
        nw3 = scenario3_net_worth_at_year(params, y)
        nw4 = scenario4_net_worth_at_year(params, y) if params.include_scenario_4 else 0.0
        results["scenario1"][y] = nw1
        results["scenario2"][y] = nw2
        results["scenario3"][y] = nw3
        results["scenario4"][y] = nw4
        results["difference"][y] = nw2 - nw1
    results["roth_at_benchmark"] = {y: roth_by_year.get(y, 0.0) for y in benchmark_years}
    results["other_house_equity_at_benchmark"] = {y: other_house_by_year.get(y, 0.0) for y in benchmark_years}
    return results


def print_report(results: dict) -> None:
    """Print a text summary of the comparison."""
    p = results["params"]
    sale = results["sale_costs_breakdown"]
    print("\n" + "=" * 70)
    print("INHERITANCE HOUSE SCENARIOS: KEEP vs. SELL & INVEST")
    print("=" * 70)
    print(f"\nProperty: Eugene, OR | Value today: {format_currency(p.home_value_today)}")
    print(f"Plan: Live in 2 years to secure $500k primary-residence exclusion.")
    print(f"\nAssumptions:")
    if p.home_return_sequence:
        seq_pct = ", ".join(f"{r*100:.1f}%" for r in p.home_return_sequence)
        print(f"  Home appreciation:     sequence of returns: [{seq_pct}] then {p.home_appreciation_rate*100:.2f}%/yr")
    else:
        print(f"  Home appreciation:     {p.home_appreciation_rate*100:.2f}% per year")
    print(f"  Investment return:     {p.investment_return_rate*100:.2f}% per year (e.g. VOO/VTI)")
    print(f"  Cash reserve return:   {p.cash_reserve_return_rate*100:.2f}% per year")
    print(f"  Selling costs:         {p.selling_costs_pct*100:.0f}% of sale price")
    print(f"  Capital gains tax:    {p.capital_gains_tax_rate*100:.0f}% on taxable gain (exclusion {format_currency(p.primary_residence_exclusion)})")
    print(f"  After sale:            {p.pct_cash_reserve*100:.0f}% cash reserve, {p.pct_invest*100:.0f}% invested")
    if p.include_scenario_4:
        recv = _inheritance_received_at_receipt(p)
        print(f"\n  Scenario 4 (inheritance value only):")
        print(f"  Mother's portfolio today: {format_currency(p.inheritance_portfolio_today)}")
        print(f"  Growth until receipt:     {p.inheritance_growth_rate*100:.1f}% per year (deterministic)")
        print(f"  Monte Carlo inheritance:  μ={p.inheritance_return_mean*100:.0f}%, σ={p.inheritance_return_std*100:.0f}%")
        print(f"  Years until receipt:     {p.inheritance_years_until_receipt}")
        print(f"  Your share:              {p.inheritance_beneficiary_share*100:.0f}% (1/{int(1/p.inheritance_beneficiary_share)} with siblings)")
        print(f"  Inheritance at receipt:  {format_currency(recv)} (portfolio continues at same growth assumption)")

    print(f"\n--- COSTS AT SALE (year {p.years_live_in_before_sale}) ---")
    print(f"  Sale price (gross):    {format_currency(sale['sale_price'])}")
    print(f"  Selling costs ({p.selling_costs_pct*100:.0f}%):   {format_currency(sale['selling_costs_dollars'])}")
    print(f"  Basis (stepped-up):    {format_currency(sale['basis'])}")
    print(f"  Gain before exclusion:{format_currency(sale['gain_before_exclusion'])}")
    print(f"  Taxable gain:          {format_currency(sale['taxable_gain'])} (after {format_currency(p.primary_residence_exclusion)} exclusion)")
    print(f"  Capital gains tax:     {format_currency(sale['cap_gains_tax'])}")
    print(f"  TOTAL COSTS AT SALE:   {format_currency(sale['total_costs_at_sale'])}")
    print(f"  NET PROCEEDS:          {format_currency(sale['net_proceeds'])}")

    net_proceeds = sale["net_proceeds"]
    print(f"\nScenario 2 — Allocation of net proceeds:")
    print(f"  Cash reserve ({p.pct_cash_reserve*100:.0f}%):   {format_currency(net_proceeds * p.pct_cash_reserve)}")
    print(f"  To invest ({p.pct_invest*100:.0f}%):       {format_currency(net_proceeds * p.pct_invest)}")

    print("\n" + "-" * 70)
    print("NET WORTH COMPARISON AT BENCHMARK YEARS (35 = retirement)")
    if p.include_scenario_4:
        print(f"  Scenario 4: Inheritance only (received year {p.inheritance_years_until_receipt})")
    print("-" * 70)
    w_pct = p.withdrawal_rate * 100
    s4_col = f" {'Inheritance':>14}" if p.include_scenario_4 else ""
    print(f"{'Years out':<12} {'Keep house':>14} {'Sell & invest':>14} {'Sell + ' + f'{w_pct:.1f}%' + ' w/d':>14} {'Diff (2−1)':>14}{s4_col}")
    print("-" * 70)
    for y in results["benchmark_years"]:
        s1 = results["scenario1"][y]
        s2 = results["scenario2"][y]
        s3 = results["scenario3"][y]
        diff = results["difference"][y]
        if y == 35:
            label = f"{y} (retire)"
        elif p.include_scenario_4 and y == p.inheritance_years_until_receipt:
            label = f"{y} (inherit)"
        else:
            label = str(y)
        row = f"{label:<12} {format_currency(s1):>14} {format_currency(s2):>14} {format_currency(s3):>14} {format_currency(diff):>14}"
        if p.include_scenario_4:
            row += f" {format_currency(results['scenario4'][y]):>14}"
        print(row)
    print("=" * 70)

    # Scenario 3: 2% withdrawal amount each year (from withdrawal_start_year through max benchmark)
    w_start = p.withdrawal_start_year
    w_rate = p.withdrawal_rate
    withdrawals = results["trajectory3_withdrawals"]
    traj3_years = results["trajectory3"][0]
    max_y = max(traj3_years) if traj3_years else 0
    if w_start <= max_y and w_start < len(withdrawals) and any(w > 0 for w in withdrawals):
        print(f"\n--- Scenario 3: {w_rate*100:.1f}% withdrawal amount each year (from year {w_start}) ---")
        print(f"{'Year':<8} {'Withdrawal (' + f'{w_rate*100:.1f}%' + ')':>18}")
        print("-" * 28)
        for y in range(w_start, min(max_y + 1, len(withdrawals))):
            if withdrawals[y] > 0:
                print(f"{y:<8} {format_currency(withdrawals[y]):>18}")
        print("=" * 70)
    print("\n(Diff (2−1) = Sell & invest net worth minus Keep house.)")
    print("Tax: Assumes stepped-up basis and $500k exclusion → no federal cap gains on sale.")
    print("=" * 70 + "\n")


def print_monte_carlo_diff_medians(mc_results: dict) -> None:
    """Print difference of medians at benchmark years (Monte Carlo), including Scenario 3 and 4 when present."""
    if not mc_results or "diff_medians" not in mc_results:
        return
    p = mc_results["params"]
    print("\n" + "-" * 70)
    print("MONTE CARLO: MEDIANS AND DIFFERENCES (25th–75th quartile bands)")
    print("-" * 70)
    inh_note = f"  |  Inheritance: μ={p.inheritance_return_mean*100:.0f}%, σ={p.inheritance_return_std*100:.0f}%" if p.include_scenario_4 else ""
    print(f"  N = {mc_results['n_paths']} paths  |  House: μ={p.house_return_mean*100:.1f}%, σ={p.house_return_std*100:.0f}%  |  Stock: μ={p.stock_return_mean*100:.0f}%, σ={p.stock_return_std*100:.0f}%{inh_note}")
    print("-" * 70)
    w_pct = p.withdrawal_rate * 100
    s4_col = " {'Inheritance (med)':>16}" if p.include_scenario_4 else ""
    print(f"{'Years out':<12} {'Keep (med)':>14} {'Sell (med)':>14} {'Sell+' + f'{w_pct:.1f}%' + ' (med)':>14} {'S2−S1':>14} {'S3−S1':>14}{s4_col}")
    print("-" * 70)
    for y in mc_results["benchmark_years"]:
        m1 = mc_results["benchmark_median1"][y]
        m2 = mc_results["benchmark_median2"][y]
        m3 = mc_results["benchmark_median3"][y]
        diff21 = mc_results["diff_medians"][y]
        diff31 = m3 - m1
        if y == 35:
            label = f"{y} (retire)"
        elif p.include_scenario_4 and y == p.inheritance_years_until_receipt:
            label = f"{y} (inherit)"
        else:
            label = str(y)
        row = f"{label:<12} {format_currency(m1):>14} {format_currency(m2):>14} {format_currency(m3):>14} {format_currency(diff21):>14} {format_currency(diff31):>14}"
        if p.include_scenario_4:
            m4 = mc_results["benchmark_median4"][y]
            row += f" {format_currency(m4):>16}"
        print(row)
    print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# Visualizations
# ---------------------------------------------------------------------------

def plot_monte_carlo_trajectories(mc_results: dict, save_path: str = "inheritance_house_trajectory_mc.png") -> None:
    """Plot median (solid) and 25th–75th quartile band (transparent) for all scenarios (incl. S4 when present)."""
    if not MATPLOTLIB_AVAILABLE or not mc_results:
        return
    p = mc_results["params"]
    years = mc_results["years"]
    max_year = max(years)
    s1_median = mc_results["s1_median"]
    s1_p25, s1_p75 = mc_results["s1_p25"], mc_results["s1_p75"]
    s2_median = mc_results["s2_median"]
    s2_p25, s2_p75 = mc_results["s2_p25"], mc_results["s2_p75"]
    s3_median = mc_results["s3_median"]
    s3_p25, s3_p75 = mc_results["s3_p25"], mc_results["s3_p75"]
    purple = "#7b1fa2"
    teal = "#00897b"

    fig, ax = plt.subplots(figsize=(12, 6))
    # Scenario 1: median solid, quartile band
    ax.fill_between(years, s1_p25, s1_p75, color="#2e7d32", alpha=0.25, label="Scenario 1: Keep house (25–75%)")
    ax.plot(years, s1_median, color="#2e7d32", linewidth=2.5, label="Scenario 1: Keep house (median)")
    # Scenario 2: median solid, quartile band
    ax.fill_between(years, s2_p25, s2_p75, color="#1565c0", alpha=0.25, label="Scenario 2: Sell & invest (25–75%)")
    ax.plot(years, s2_median, color="#1565c0", linewidth=2.5, label="Scenario 2: Sell & invest (median)")
    # Scenario 3: median solid, quartile band (purple)
    w_pct = p.withdrawal_rate * 100
    ax.fill_between(years, s3_p25, s3_p75, color=purple, alpha=0.25, label=f"Scenario 3: Sell + {w_pct:.1f}% w/d (25–75%)")
    ax.plot(years, s3_median, color=purple, linewidth=2.5, label=f"Scenario 3: Sell + {w_pct:.1f}% w/d (median)")
    # Scenario 4: Inheritance only (teal)
    if p.include_scenario_4 and "s4_median" in mc_results:
        s4_median = mc_results["s4_median"]
        s4_p25, s4_p75 = mc_results["s4_p25"], mc_results["s4_p75"]
        ax.fill_between(years, s4_p25, s4_p75, color=teal, alpha=0.25, label="Scenario 4: Inheritance (25–75%)")
        ax.plot(years, s4_median, color=teal, linewidth=2.5, label="Scenario 4: Inheritance (median)")

    for y in mc_results["benchmark_years"]:
        ax.axvline(x=y, color="gray", linestyle="--", alpha=0.5)
    if p.include_scenario_4 and p.inheritance_years_until_receipt <= max_year:
        ax.axvline(x=p.inheritance_years_until_receipt, color=teal, linestyle="-", alpha=0.7, linewidth=1.5)
    ax.set_xlabel("Years from today", fontsize=12, fontweight="bold")
    ax.set_ylabel("Net worth", fontsize=12, fontweight="bold")
    ax.set_title("Monte Carlo: Net worth over time (median, 25th–75th quartiles)", fontsize=13, fontweight="bold")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"${x/1e6:.2f}M"))
    ax.set_xlim(-0.5, max_year + 0.5)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"Monte Carlo trajectory plot saved to '{save_path}'")
    plt.close()


def plot_monte_carlo_trajectories_s1_s2_s3(mc_results: dict, save_path: str = "inheritance_house_trajectory_mc_s1_s2_s3.png") -> None:
    """Plot median and 25th–75th quartile band for scenarios 1, 2, and 3 only (no inheritance)."""
    if not MATPLOTLIB_AVAILABLE or not mc_results:
        return
    p = mc_results["params"]
    years = mc_results["years"]
    max_year = max(years)
    s1_median = mc_results["s1_median"]
    s1_p25, s1_p75 = mc_results["s1_p25"], mc_results["s1_p75"]
    s2_median = mc_results["s2_median"]
    s2_p25, s2_p75 = mc_results["s2_p25"], mc_results["s2_p75"]
    s3_median = mc_results["s3_median"]
    s3_p25, s3_p75 = mc_results["s3_p25"], mc_results["s3_p75"]
    purple = "#7b1fa2"
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.fill_between(years, s1_p25, s1_p75, color="#2e7d32", alpha=0.25, label="Scenario 1: Keep house (25–75%)")
    ax.plot(years, s1_median, color="#2e7d32", linewidth=2.5, label="Scenario 1: Keep house (median)")
    ax.fill_between(years, s2_p25, s2_p75, color="#1565c0", alpha=0.25, label="Scenario 2: Sell & invest (25–75%)")
    ax.plot(years, s2_median, color="#1565c0", linewidth=2.5, label="Scenario 2: Sell & invest (median)")
    w_pct = p.withdrawal_rate * 100
    ax.fill_between(years, s3_p25, s3_p75, color=purple, alpha=0.25, label=f"Scenario 3: Sell + {w_pct:.1f}% w/d (25–75%)")
    ax.plot(years, s3_median, color=purple, linewidth=2.5, label=f"Scenario 3: Sell + {w_pct:.1f}% w/d (median)")
    for y in p.benchmark_years:
        ax.axvline(x=y, color="gray", linestyle="--", alpha=0.5)
    ax.set_xlabel("Years from today", fontsize=12, fontweight="bold")
    ax.set_ylabel("Net worth", fontsize=12, fontweight="bold")
    ax.set_title("Monte Carlo: Net worth over time — Scenarios 1–3 (median, 25th–75th quartiles)", fontsize=12, fontweight="bold")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"${x/1e6:.2f}M"))
    ax.set_xlim(-0.5, max_year + 0.5)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"Monte Carlo S1–S3 trajectory plot saved to '{save_path}'")
    plt.close()


def plot_monte_carlo_inheritance_comparison(mc_results: dict, save_path: str = "inheritance_house_mc_inheritance_comparison.png") -> None:
    """Bar chart: S1, S2, S3 MC medians at benchmark years, with a bar next to each showing scenario + inheritance (total net worth).
    Before receipt year: '+inheritance' bars = scenario + your projected share of the inheritance portfolio (growing until receipt).
    At/after receipt: '+inheritance' bars = actual net worth (scenario + inheritance received and grown)."""
    if not MATPLOTLIB_AVAILABLE or not mc_results:
        return
    p = mc_results["params"]
    if not p.include_scenario_4 or "benchmark_median4" not in mc_results:
        return
    R = p.inheritance_years_until_receipt
    benchmarks = list(mc_results["benchmark_years"])
    bm1 = mc_results["benchmark_median1"]
    bm2 = mc_results["benchmark_median2"]
    bm3 = mc_results["benchmark_median3"]
    bm4 = mc_results["benchmark_median4"]
    # Inheritance at each benchmark: S4 is inheritance-only, so bm4[y] is the inheritance value.
    inv_at = [bm4[y] for y in benchmarks]
    s1_alone = [bm1[y] for y in benchmarks]
    s2_alone = [bm2[y] for y in benchmarks]
    s3_alone = [bm3[y] for y in benchmarks]
    s1_plus_inv = [bm1[y] + inv_at[j] for j, y in enumerate(benchmarks)]
    s2_plus_inv = [bm2[y] + inv_at[j] for j, y in enumerate(benchmarks)]
    s3_plus_inv = [bm3[y] + inv_at[j] for j, y in enumerate(benchmarks)]

    green = "#2e7d32"
    green_light = "#81c784"
    blue = "#1565c0"
    teal = "#00897b"
    purple = "#7b1fa2"
    purple_light = "#ba68c8"
    w_pct = p.withdrawal_rate * 100

    n = len(benchmarks)
    x = list(range(n))
    width = 0.12
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.bar([i - 2.5 * width for i in x], s1_alone, width, label="S1: Keep house", color=green, alpha=0.9)
    ax.bar([i - 1.5 * width for i in x], s1_plus_inv, width, label="S1 + inheritance", color=green_light, alpha=0.9)
    ax.bar([i - 0.5 * width for i in x], s2_alone, width, label="S2: Sell & invest", color=blue, alpha=0.9)
    ax.bar([i + 0.5 * width for i in x], s2_plus_inv, width, label="S2 + inheritance", color=teal, alpha=0.9)
    ax.bar([i + 1.5 * width for i in x], s3_alone, width, label=f"S3: Sell + {w_pct:.1f}% w/d", color=purple, alpha=0.9)
    ax.bar([i + 2.5 * width for i in x], s3_plus_inv, width, label="S3 + inheritance", color=purple_light, alpha=0.9)

    ax.set_ylabel("Net worth (MC median)", fontsize=12, fontweight="bold")
    ax.set_xlabel("Years from today", fontsize=12, fontweight="bold")
    ax.set_title("Monte Carlo: S1–S3 vs S1–S3 + inheritance at benchmark years", fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) if y != p.inheritance_years_until_receipt else f"{y}\n(inherit)" for y in benchmarks])
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"${v/1e6:.2f}M"))
    ax.grid(True, alpha=0.3, axis="y", linestyle="--")
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"Monte Carlo inheritance comparison (bar chart) saved to '{save_path}'")
    plt.close()


def plot_net_worth_trajectories(results: dict, save_path: str = "inheritance_house_trajectory.png") -> None:
    """Plot both scenarios' net worth over time; Scenario 2 shows cash vs investment buckets (stacked)."""
    if not MATPLOTLIB_AVAILABLE:
        print("Matplotlib not available. Skipping trajectory plot.")
        return

    years1, values1 = results["trajectory1"]
    years2, values2 = results["trajectory2"]
    cash_list = results["trajectory2_cash"]
    invest_list = results["trajectory2_invest"]
    params = results["params"]
    max_year = max(params.benchmark_years)
    sale_year = params.years_live_in_before_sale

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(years1, values1, color="#2e7d32", linewidth=2.5, label="Scenario 1: Keep house", marker="o", markersize=4, markevery=max(1, max_year // 5))
    ax.plot(years2, values2, color="#1565c0", linewidth=2, linestyle="--", label="Scenario 2: Total", alpha=0.9)

    # Stacked area for Scenario 2: cash (withheld) and investment bucket from sale year onward
    idx_sale = sale_year + 1  # first index after sale
    if idx_sale <= len(years2):
        x_stack = years2[idx_sale:]
        cash_stack = cash_list[idx_sale:]
        invest_stack = invest_list[idx_sale:]
        ax.fill_between(x_stack, 0, cash_stack, color="#ffb74d", alpha=0.85, label="Scenario 2: Cash reserve")
        ax.fill_between(x_stack, cash_stack, [c + i for c, i in zip(cash_stack, invest_stack)], color="#1565c0", alpha=0.7, label="Scenario 2: Investment")
    ax.legend(loc="upper left", fontsize=9)

    for y in params.benchmark_years:
        ax.axvline(x=y, color="gray", linestyle="--", alpha=0.5)
        nw1 = results["scenario1"][y]
        nw2 = results["scenario2"][y]
        ax.scatter([y], [nw1], color="#2e7d32", s=80, zorder=5)
        ax.scatter([y], [nw2], color="#1565c0", s=80, zorder=5)

    ax.set_xlabel("Years from today", fontsize=12, fontweight="bold")
    ax.set_ylabel("Net worth", fontsize=12, fontweight="bold")
    ax.set_title("Inheritance house: Net worth over time — Keep vs. Sell & invest (cash vs investment)", fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"${x/1e6:.2f}M"))
    ax.set_xlim(-0.5, max_year + 0.5)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"Trajectory plot saved to '{save_path}'")
    plt.close()


def plot_benchmark_bars(
    results: dict,
    save_path: str = "inheritance_house_benchmarks.png",
    mc_results: dict | None = None,
) -> None:
    """Bar chart comparing net worth at benchmark years (MC median when mc_results provided, else deterministic).
    Includes Scenario 4 (inheritance only) when present."""
    if not MATPLOTLIB_AVAILABLE:
        print("Matplotlib not available. Skipping benchmark bar chart.")
        return

    params = results["params"]
    use_mc = bool(mc_results and mc_results.get("benchmark_median1"))
    if use_mc:
        benchmarks = list(mc_results["benchmark_years"])
        keep = [mc_results["benchmark_median1"][y] for y in benchmarks]
        s2_totals = [mc_results["benchmark_median2"][y] for y in benchmarks]
        s3_totals = [mc_results["benchmark_median3"][y] for y in benchmarks]
        s4_totals = [mc_results["benchmark_median4"][y] for y in benchmarks] if params.include_scenario_4 else []
    else:
        benchmarks = results["benchmark_years"]
        keep = [results["scenario1"][y] for y in benchmarks]
        years_list = results["trajectory2"][0]
        cash_list = results["trajectory2_cash"]
        invest_list = results["trajectory2_invest"]
        sell_cash = [cash_list[years_list.index(y)] for y in benchmarks]
        sell_invest = [invest_list[years_list.index(y)] for y in benchmarks]
        s2_totals = [sell_invest[j] + sell_cash[j] for j in range(len(benchmarks))]
        s3_totals = [results["scenario3"][y] for y in benchmarks]
        s4_totals = [results["scenario4"][y] for y in benchmarks] if params.include_scenario_4 else []

    purple = "#7b1fa2"
    teal = "#00897b"
    x = range(len(benchmarks))
    width = 0.2 if params.include_scenario_4 else 0.25
    off = width * 1.5 if params.include_scenario_4 else width

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar([i - off for i in x], keep, width, label="Scenario 1: Keep house", color="#2e7d32", alpha=0.85)
    if use_mc:
        ax.bar([i - width/2 for i in x], s2_totals, width, label="Scenario 2: Sell & invest", color="#1565c0", alpha=0.85)
    else:
        ax.bar([i - width/2 for i in x], sell_invest, width, label="Scenario 2: Investment", color="#1565c0", alpha=0.85)
        ax.bar([i - width/2 for i in x], sell_cash, width, bottom=sell_invest, label="Scenario 2: Cash", color="#ffb74d", alpha=0.9)
    w_pct = params.withdrawal_rate * 100
    ax.bar([i + width/2 for i in x], s3_totals, width, label=f"Scenario 3: Sell + {w_pct:.1f}% w/d", color=purple, alpha=0.85)
    if params.include_scenario_4 and s4_totals:
        ax.bar([i + off for i in x], s4_totals, width, label="Scenario 4: Inheritance", color=teal, alpha=0.85)

    xtick_labels = [str(y) if (not params.include_scenario_4 or y != params.inheritance_years_until_receipt) else f"{y}\n(inherit)" for y in benchmarks]
    ax.set_ylabel("Net worth", fontsize=12, fontweight="bold")
    ax.set_xlabel("Years from today", fontsize=12, fontweight="bold")
    title = "Net worth at benchmark years (MC median)"
    if not use_mc:
        title = "Net worth at benchmark years (deterministic)"
    if params.include_scenario_4:
        title += " (incl. inheritance receipt)"
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(xtick_labels)
    ax.legend(loc="upper left", fontsize=8)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, p: f"${v/1e6:.2f}M"))
    ax.grid(True, alpha=0.3, axis="y", linestyle="--")
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"Benchmark bar chart saved to '{save_path}'")
    plt.close()


def plot_total_net_worth_stacked_bars(
    results: dict,
    save_path: str = "inheritance_house_total_net_worth.png",
    mc_results: dict | None = None,
) -> None:
    """Stacked bar chart: total net worth at benchmark years = scenario + Roth + other house. Each bar broken down by asset."""
    if not MATPLOTLIB_AVAILABLE:
        print("Matplotlib not available. Skipping total net worth stacked bar chart.")
        return
    params = results["params"]
    use_mc = bool(mc_results and mc_results.get("benchmark_median1"))
    if use_mc:
        benchmarks = list(mc_results["benchmark_years"])
        s1_vals = [mc_results["benchmark_median1"][y] for y in benchmarks]
        s2_vals = [mc_results["benchmark_median2"][y] for y in benchmarks]
        s3_vals = [mc_results["benchmark_median3"][y] for y in benchmarks]
        s4_vals = [mc_results["benchmark_median4"][y] for y in benchmarks] if params.include_scenario_4 else []
        roth_vals = [mc_results["benchmark_roth_median"][y] for y in benchmarks]
        other_vals = [mc_results["benchmark_other_house_equity"][y] for y in benchmarks]
    else:
        benchmarks = results["benchmark_years"]
        s1_vals = [results["scenario1"][y] for y in benchmarks]
        s2_vals = [results["scenario2"][y] for y in benchmarks]
        s3_vals = [results["scenario3"][y] for y in benchmarks]
        s4_vals = [results["scenario4"][y] for y in benchmarks] if params.include_scenario_4 else []
        roth_vals = [results["roth_at_benchmark"][y] for y in benchmarks]
        other_vals = [results["other_house_equity_at_benchmark"][y] for y in benchmarks]

    n_bench = len(benchmarks)
    n_scenarios = 4 if params.include_scenario_4 else 3
    width = 0.18 if n_scenarios == 4 else 0.22
    w_pct = params.withdrawal_rate * 100
    green, blue, purple, teal = "#2e7d32", "#1565c0", "#7b1fa2", "#00897b"
    roth_color, other_color = "#ff8f00", "#5d4037"

    fig, ax = plt.subplots(figsize=(14, 7))
    scenario_groups = [
        (s1_vals, "S1: Keep house", green),
        (s2_vals, "S2: Sell & invest", blue),
        (s3_vals, f"S3: Sell + {w_pct:.1f}% w/d", purple),
    ]
    if params.include_scenario_4:
        scenario_groups.append((s4_vals, "S4: Inheritance", teal))
    x_centers = list(range(n_bench))
    for sc_idx, (sc_vals, label, color) in enumerate(scenario_groups):
        # offset so bars are grouped per benchmark year
        offset = (sc_idx - (n_scenarios - 1) / 2) * width
        x_pos = [i + offset for i in x_centers]
        ax.bar(x_pos, sc_vals, width, label=label, color=color, alpha=0.9)
        ax.bar(x_pos, roth_vals, width, bottom=sc_vals, color=roth_color, alpha=0.9, label="Roth IRA" if sc_idx == 0 else "")
        bottom_2 = [s + r for s, r in zip(sc_vals, roth_vals)]
        ax.bar(x_pos, other_vals, width, bottom=bottom_2, color=other_color, alpha=0.9, label="Other house" if sc_idx == 0 else "")
    ax.set_ylabel("Total net worth", fontsize=12, fontweight="bold")
    ax.set_xlabel("Years from today", fontsize=12, fontweight="bold")
    title = "Total net worth at benchmark years (scenario + Roth + other house)"
    if use_mc:
        title += " [MC median]"
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xticks(x_centers)
    ax.set_xticklabels([str(y) if (not params.include_scenario_4 or y != params.inheritance_years_until_receipt) else f"{y}\n(inherit)" for y in benchmarks])
    ax.legend(loc="upper left", fontsize=8)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"${v/1e6:.2f}M"))
    ax.grid(True, alpha=0.3, axis="y", linestyle="--")
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"Total net worth (stacked) bar chart saved to '{save_path}'")
    plt.close()


def plot_benchmark_bars_s1_s2_s3(
    results: dict,
    save_path: str = "inheritance_house_benchmarks_s1_s2_s3.png",
    mc_results: dict | None = None,
) -> None:
    """Bar chart comparing net worth at benchmark years for scenarios 1–3 only (MC median when mc_results provided)."""
    if not MATPLOTLIB_AVAILABLE:
        print("Matplotlib not available. Skipping S1–S3 benchmark bar chart.")
        return
    params = results["params"]
    benchmarks = list(params.benchmark_years)
    use_mc = bool(mc_results and mc_results.get("benchmark_median1"))
    if use_mc:
        keep = [mc_results["benchmark_median1"][y] for y in benchmarks]
        s2_totals = [mc_results["benchmark_median2"][y] for y in benchmarks]
        s3_totals = [mc_results["benchmark_median3"][y] for y in benchmarks]
    else:
        keep = [results["scenario1"][y] for y in benchmarks]
        years_list = results["trajectory2"][0]
        cash_list = results["trajectory2_cash"]
        invest_list = results["trajectory2_invest"]
        sell_cash = [cash_list[years_list.index(y)] for y in benchmarks]
        sell_invest = [invest_list[years_list.index(y)] for y in benchmarks]
        s2_totals = [sell_invest[j] + sell_cash[j] for j in range(len(benchmarks))]
        s3_totals = [results["scenario3"][y] for y in benchmarks]
    purple = "#7b1fa2"
    x = range(len(benchmarks))
    width = 0.25
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar([i - width for i in x], keep, width, label="Scenario 1: Keep house", color="#2e7d32", alpha=0.85)
    if use_mc:
        ax.bar([i for i in x], s2_totals, width, label="Scenario 2: Sell & invest", color="#1565c0", alpha=0.85)
    else:
        ax.bar([i for i in x], sell_invest, width, label="Scenario 2: Investment", color="#1565c0", alpha=0.85)
        ax.bar([i for i in x], sell_cash, width, bottom=sell_invest, label="Scenario 2: Cash", color="#ffb74d", alpha=0.9)
    w_pct = params.withdrawal_rate * 100
    ax.bar([i + width for i in x], s3_totals, width, label=f"Scenario 3: Sell + {w_pct:.1f}% w/d", color=purple, alpha=0.85)
    ax.set_ylabel("Net worth", fontsize=12, fontweight="bold")
    ax.set_xlabel("Years from today", fontsize=12, fontweight="bold")
    title = "Net worth at benchmark years — Scenarios 1–3 (MC median)" if use_mc else "Net worth at benchmark years — Scenarios 1–3 (deterministic)"
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in benchmarks])
    ax.legend(loc="upper left", fontsize=8)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, p: f"${v/1e6:.2f}M"))
    ax.grid(True, alpha=0.3, axis="y", linestyle="--")
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"S1–S3 benchmark bar chart saved to '{save_path}'")
    plt.close()


def export_trajectories_csv(
    results: dict,
    filepath: str = "inheritance_house_trajectories.csv",
    inflation_rate: float = 0.03,
) -> None:
    """Export year-by-year net worth for all three scenarios to CSV (includes cash/investment and Scenario 3 withdrawals).
    Withdrawal today's $ = nominal / (1+inflation)^year (purchasing power in year-0 dollars). With 75% in stocks (~8%) and 25% in cash (~2%), blended growth typically exceeds inflation, so this series often rises over time."""
    p = results["params"]
    w_pct = p.withdrawal_rate * 100
    # Column names reflect actual withdrawal % (e.g. Withdrawal_2pct, Withdrawal_3_5pct)
    w_label = f"{int(w_pct)}" if w_pct == int(w_pct) else f"{w_pct:.1f}".replace(".", "_")
    col_wd = f"Withdrawal_{w_label}pct"
    col_wd_today = f"Withdrawal_{w_label}pct_today_dollars"
    col_s3 = f"Sell_plus_{w_label}pct_wd"

    years, vals1 = results["trajectory1"]
    _, vals2 = results["trajectory2"]
    _, vals3 = results["trajectory3"]
    _, vals4 = results["trajectory4"]
    _, roth_vals = results["trajectory_roth"]
    cash_list = results["trajectory2_cash"]
    invest_list = results["trajectory2_invest"]
    withdrawals = results["trajectory3_withdrawals"]
    header_row = [
        "Year", "Keep_house", "Sell_and_invest", col_s3, "Sell_cash", "Sell_invest",
        col_wd, col_wd_today, "Diff_S2_minus_S1",
        "Eugene_house_value", "Other_house_value", "Roth_IRA_balance",
    ]
    if p.include_scenario_4:
        header_row.append("S2_plus_inheritance")
        header_row.append("Inheritance_portfolio_projected")
        header_row.append("Inheritance_my_share")
    with open(filepath, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header_row)
        R = p.inheritance_years_until_receipt if p.include_scenario_4 else -1
        for i, y in enumerate(years):
            wd = withdrawals[i] if i < len(withdrawals) else 0
            # Today's $ = nominal / (1+inflation)^year (purchasing power in year-0 dollars)
            wd_today = wd / ((1.0 + inflation_rate) ** y) if y >= 0 and wd > 0 else 0.0
            other_house_val = p.other_house_value_today * ((1.0 + p.other_house_appreciation_rate) ** y)
            row = [
                y, f"{vals1[i]:,.2f}", f"{vals2[i]:,.2f}", f"{vals3[i]:,.2f}",
                f"{cash_list[i]:,.2f}", f"{invest_list[i]:,.2f}",
                f"{wd:,.2f}", f"{wd_today:,.2f}", f"{vals2[i] - vals1[i]:,.2f}",
                f"{vals1[i]:,.2f}", f"{other_house_val:,.2f}", f"{roth_vals[i]:,.2f}",
            ]
            if p.include_scenario_4:
                row.append(f"{vals4[i]:,.2f}")
                # Projected value of mother's portfolio at end of this year (grows until receipt year)
                if y <= R:
                    proj = p.inheritance_portfolio_today * ((1.0 + p.inheritance_growth_rate) ** y)
                    row.append(f"{proj:,.2f}")
                else:
                    row.append("")
                # Value of your share of the inheritance portfolio (grows at inheritance_growth_rate / MC returns; no split at receipt)
                my_share = _inheritance_value_at_year(p, y)
                row.append(f"{my_share:,.2f}")
            w.writerow(row)
    print(f"Year-by-year data exported to '{filepath}' (withdrawal today's $ at {inflation_rate*100:.0f}% inflation)")


def plot_difference_chart(results: dict, save_path: str = "inheritance_house_difference.png") -> None:
    """Plot how much ahead (or behind) Scenario 2 is vs. Scenario 1 at each benchmark."""
    if not MATPLOTLIB_AVAILABLE:
        return

    benchmarks = results["benchmark_years"]
    diffs = [results["difference"][y] for y in benchmarks]
    colors = ["#2e7d32" if d >= 0 else "#c62828" for d in diffs]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar([str(y) for y in benchmarks], [d / 1e6 for d in diffs], color=colors, alpha=0.85)
    ax.axhline(y=0, color="black", linewidth=0.8)
    ax.set_ylabel("Difference in net worth (millions $)", fontsize=12, fontweight="bold")
    ax.set_xlabel("Years from today", fontsize=12, fontweight="bold")
    ax.set_title("Sell & invest vs. Keep house: Net worth difference\n(positive = sell & invest is ahead)", fontsize=12, fontweight="bold")
    for bar, d in zip(bars, diffs):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02 if d >= 0 else bar.get_height() - 0.08,
                format_currency(d), ha="center", va="bottom" if d >= 0 else "top", fontsize=10, fontweight="bold")
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"Difference chart saved to '{save_path}'")
    plt.close()


# ---------------------------------------------------------------------------
# Main: default profile and interactive prompts
# ---------------------------------------------------------------------------

def default_params() -> HouseScenarioParams:
    """Return the default parameter profile (current recommended values)."""
    return HouseScenarioParams(
        home_value_today=864_000,
        years_live_in_before_sale=2,
        pct_cash_reserve=0.25,
        pct_invest=0.75,
        selling_costs_pct=0.06,
        basis_at_sale=None,
        primary_residence_exclusion=500_000,
        capital_gains_tax_rate=0.0,
        home_appreciation_rate=0.004,
        home_return_sequence=None,
        investment_return_rate=0.07,
        cash_reserve_return_rate=0.02,
        mc_n_paths=10000,
        stock_return_mean=0.08,
        stock_return_std=0.17,
        house_return_mean=0.005,
        house_return_std=0.08,
        withdrawal_start_year=17,
        withdrawal_rate=0.02,
        include_scenario_4=True,
        inheritance_portfolio_today=9_000_000,
        inheritance_growth_rate=0.045,
        inheritance_return_mean=0.05,
        inheritance_return_std=0.14,
        inheritance_years_until_receipt=24,
        inheritance_beneficiary_share=1.0 / 3,
        benchmark_years=(7, 12, 17, 35),
        roth_balance_today=35_500,
        roth_annual_contribution=7_000,
        roth_contribution_years=35,
        other_house_value_today=316_000,
        other_house_mortgage_remaining=140_748,
        other_house_mortgage_payoff_years=20.0,
        other_house_appreciation_rate=0.004,
    )


# ---------------------------------------------------------------------------
# Flexible scenario list: run multiple named scenarios (for web app)
# ---------------------------------------------------------------------------

def merge_params(base: HouseScenarioParams, overrides: Dict[str, Any]) -> HouseScenarioParams:
    """Build a new HouseScenarioParams from base with overrides applied."""
    d = asdict(base)
    for k, v in overrides.items():
        if k not in d:
            continue
        if v is None:
            continue
        if k == "benchmark_years":
            d[k] = tuple(v) if isinstance(v, list) else v
        elif k == "home_return_sequence" and isinstance(v, list):
            d[k] = tuple(float(x) for x in v)
        else:
            d[k] = v
    return HouseScenarioParams(**d)


def run_scenarios(
    global_params: HouseScenarioParams,
    scenario_configs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Run a list of named scenarios (deterministic). Each config has:
    - id: unique id (e.g. uuid or index)
    - name: display name
    - type: keep_property | sell_invest | sell_invest_withdrawals | inheritance_only | roth | other_property
    - params: dict of param overrides for this scenario (optional)
    Returns: { benchmark_years, scenarios: { id: { name, type, years, values, values_at_benchmark } }, sale_breakdowns: { id: {...} } }
    """
    benchmark_years = _effective_benchmark_years(global_params)
    max_year = max(benchmark_years)
    out: Dict[str, Any] = {
        "benchmark_years": list(benchmark_years),
        "scenarios": {},
        "sale_breakdowns": {},
    }
    for cfg in scenario_configs:
        sid = str(cfg.get("id") or cfg.get("name", ""))
        name = str(cfg.get("name", "Unnamed"))
        typ = str(cfg.get("type", ""))
        overrides = cfg.get("params") or {}
        params = merge_params(global_params, overrides)
        years: List[int]
        vals: List[float]
        if typ == "keep_property":
            years, vals = scenario1_trajectory(params, max_year)
        elif typ == "sell_invest":
            years, vals = scenario2_trajectory(params, max_year)
            out["sale_breakdowns"][sid] = {k: (v if v == v else None) for k, v in sale_costs_breakdown(params).items()}
        elif typ == "sell_invest_withdrawals":
            _y, vals, _c, _i, _w = scenario3_trajectory_and_withdrawals(params, max_year)
            years = list(range(max_year + 1))
            out["sale_breakdowns"][sid] = {k: (v if v == v else None) for k, v in sale_costs_breakdown(params).items()}
        elif typ == "inheritance_only":
            years, vals = scenario4_trajectory(params, max_year)
        elif typ == "roth":
            years, vals = roth_trajectory(params, max_year)
        elif typ == "other_property":
            years, vals = other_house_equity_trajectory(params, max_year)
        else:
            continue
        values_at_benchmark = {y: float(vals[y]) for y in benchmark_years if y < len(vals)}
        out["scenarios"][sid] = {
            "name": name,
            "type": typ,
            "years": years,
            "values": [float(v) for v in vals],
            "values_at_benchmark": values_at_benchmark,
        }
    return out


def _prompt_float(msg: str, default: float, min_val: float, max_val: float, scale: float = 1.0) -> float:
    """Prompt for a float; Enter uses default. scale: e.g. 0.01 for percentage input -> decimal."""
    try:
        raw = input(msg).strip()
        if not raw:
            return default
        val = float(raw) * scale
        if val < min_val or val > max_val:
            print(f"  Using default {default} (value must be between {min_val} and {max_val}).")
            return default
        return val
    except ValueError:
        print(f"  Invalid number; using default {default}.")
        return default


def _prompt_int(msg: str, default: int, min_val: int, max_val: int) -> int:
    """Prompt for an int; Enter uses default."""
    try:
        raw = input(msg).strip()
        if not raw:
            return default
        val = int(raw)
        if val < min_val or val > max_val:
            print(f"  Using default {default} (value must be between {min_val} and {max_val}).")
            return default
        return val
    except ValueError:
        print(f"  Invalid number; using default {default}.")
        return default


def prompt_params() -> HouseScenarioParams:
    """Prompt for all key parameters; Enter at each step uses default. Returns HouseScenarioParams."""
    print("\n--- Manual input (Enter = use default) ---\n")
    # Scenario 2: cash vs invest
    pct_cash = _prompt_float("Cash reserve % (Scenario 2; rest goes to investments) [default 25]: ", 0.25, 0.0, 100.0, 0.01)
    pct_invest = 1.0 - pct_cash
    # Year to sell
    years_live_in = _prompt_int("Years to live in house before sale (Scenario 2) [default 2]: ", 2, 1, 20)
    # Monte Carlo
    stock_mean = _prompt_float("Stock return mean % (Monte Carlo) [default 8]: ", 0.08, -20.0, 30.0, 0.01)
    stock_std = _prompt_float("Stock return std % (Monte Carlo) [default 17]: ", 0.17, 0.0, 50.0, 0.01)
    house_mean = _prompt_float("House return mean % (Monte Carlo) [default 0.5]: ", 0.005, -20.0, 30.0, 0.01)
    house_std = _prompt_float("House return std % (Monte Carlo) [default 8]: ", 0.08, 0.0, 50.0, 0.01)
    # Scenario 3
    withdrawal_rate = _prompt_float("Withdrawal rate % (Scenario 3) [default 2]: ", 0.02, 0.0, 20.0, 0.01)
    withdrawal_start = _prompt_int("Year to start withdrawals (Scenario 3) [default 17]: ", 17, 1, 40)
    # Optional: home value, selling costs, MC paths
    try:
        hv_raw = input("Home value today $ [default 864000]: ").strip()
        home_value = float(hv_raw) if hv_raw else 864_000
        if hv_raw:
            home_value = max(1.0, min(1e9, home_value))
    except ValueError:
        home_value = 864_000
    selling_costs = _prompt_float("Selling costs % [default 6]: ", 0.06, 0.0, 20.0, 0.01)
    mc_paths = _prompt_int("Monte Carlo paths [default 10000]: ", 10000, 100, 100_000)
    # Scenario 4: estate inheritance
    incl_s4 = input("Include Scenario 4 (inheritance only)? (y/n) [default y]: ").strip().lower()
    include_scenario_4 = incl_s4 in ("", "y", "yes")
    inheritance_portfolio_today = 9_000_000
    inheritance_growth_rate = 0.045
    inheritance_years_until_receipt = 24
    inheritance_beneficiary_share = 1.0 / 3
    if include_scenario_4:
        try:
            pv_raw = input("Mother's portfolio value today $ [default 9000000]: ").strip()
            inheritance_portfolio_today = float(pv_raw) if pv_raw else 9_000_000
            if pv_raw:
                inheritance_portfolio_today = max(1.0, min(1e12, inheritance_portfolio_today))
        except ValueError:
            inheritance_portfolio_today = 9_000_000
        inheritance_growth_rate = _prompt_float("Portfolio growth % until receipt [default 4.5]: ", 0.045, -10.0, 30.0, 0.01)
        inheritance_years_until_receipt = _prompt_int("Years until inheritance receipt [default 24]: ", 24, 1, 50)
        nb_raw = input("Number of beneficiaries (e.g. 3 for 1/3 share) [default 3]: ").strip()
        try:
            n_benef = int(nb_raw) if nb_raw else 3
            n_benef = max(1, min(100, n_benef))
            inheritance_beneficiary_share = 1.0 / n_benef
        except ValueError:
            inheritance_beneficiary_share = 1.0 / 3
    print()
    return HouseScenarioParams(
        home_value_today=home_value,
        years_live_in_before_sale=years_live_in,
        pct_cash_reserve=pct_cash,
        pct_invest=pct_invest,
        selling_costs_pct=selling_costs,
        basis_at_sale=None,
        primary_residence_exclusion=500_000,
        capital_gains_tax_rate=0.0,
        home_appreciation_rate=0.004,
        home_return_sequence=None,
        investment_return_rate=0.07,
        cash_reserve_return_rate=0.02,
        mc_n_paths=mc_paths,
        stock_return_mean=stock_mean,
        stock_return_std=stock_std,
        house_return_mean=house_mean,
        house_return_std=house_std,
        withdrawal_start_year=withdrawal_start,
        withdrawal_rate=withdrawal_rate,
        include_scenario_4=include_scenario_4,
        inheritance_portfolio_today=inheritance_portfolio_today,
        inheritance_growth_rate=inheritance_growth_rate,
        inheritance_return_mean=0.05,
        inheritance_return_std=0.14,
        inheritance_years_until_receipt=inheritance_years_until_receipt,
        inheritance_beneficiary_share=inheritance_beneficiary_share,
        benchmark_years=(7, 12, 17, 35),
        roth_balance_today=35_500,
        roth_annual_contribution=7_000,
        roth_contribution_years=35,
        other_house_value_today=316_000,
        other_house_mortgage_remaining=140_748,
        other_house_mortgage_payoff_years=20.0,
        other_house_appreciation_rate=0.004,
    )


def main() -> None:
    use_default = input("Use default profile? (y/n) [default y]: ").strip().lower()
    if use_default in ("", "y", "yes"):
        params = default_params()
        print("Using default profile.\n")
    else:
        params = prompt_params()
    results = run_comparison(params)
    print_report(results)
    # Monte Carlo: median + 1-sigma bands and difference of medians
    mc_results = run_monte_carlo(params) if NUMPY_AVAILABLE else {}
    if mc_results:
        print_monte_carlo_diff_medians(mc_results)
        plot_monte_carlo_trajectories(mc_results)
        plot_monte_carlo_trajectories_s1_s2_s3(mc_results)
        plot_monte_carlo_inheritance_comparison(mc_results)
        plot_benchmark_bars(results, mc_results=mc_results)
        plot_benchmark_bars_s1_s2_s3(results, mc_results=mc_results)
        plot_total_net_worth_stacked_bars(results, mc_results=mc_results)
    else:
        plot_net_worth_trajectories(results)
        if not NUMPY_AVAILABLE:
            print("Monte Carlo skipped (numpy not installed). Install with: pip install numpy")
        plot_benchmark_bars(results)
        plot_benchmark_bars_s1_s2_s3(results)
        plot_total_net_worth_stacked_bars(results)
    plot_difference_chart(results)
    export_trajectories_csv(results)
    _print_sensitivity_note()
    print("\nDone. Re-run and choose 'n' for manual input to test other parameter values.")


def _print_sensitivity_note() -> None:
    """Print a short sensitivity example (e.g. sequence of returns or higher home growth)."""
    print("\n--- Sensitivity (alternative assumptions) ---")
    # Sequence of returns: e.g. Zillow-like 0.4% year 1, 0.6% year 2, then 0.4%/yr
    p_seq = HouseScenarioParams(
        home_value_today=864_000,
        years_live_in_before_sale=2,
        pct_cash_reserve=0.25,
        pct_invest=0.75,
        selling_costs_pct=0.06,
        capital_gains_tax_rate=0.0,
        home_appreciation_rate=0.004,
        home_return_sequence=(0.004, 0.006),
        investment_return_rate=0.07,
        cash_reserve_return_rate=0.02,
        benchmark_years=(7, 12, 17, 35),
    )
    r_seq = run_comparison(p_seq)
    print("Sequence of returns (year 1: 0.4%, year 2: 0.6%, then 0.4%/yr):")
    for y in (7, 12, 17, 35):
        d = r_seq["difference"][y]
        tag = " (retirement)" if y == 35 else ""
        print(f"  At {y} years{tag}: {format_currency(r_seq['scenario1'][y])} (keep) vs {format_currency(r_seq['scenario2'][y])} (sell) — diff {format_currency(d)}")
    # Higher flat home appreciation
    p_high = HouseScenarioParams(
        home_value_today=864_000,
        years_live_in_before_sale=2,
        pct_cash_reserve=0.25,
        pct_invest=0.75,
        selling_costs_pct=0.06,
        home_appreciation_rate=0.034,
        investment_return_rate=0.07,
        cash_reserve_return_rate=0.02,
        benchmark_years=(7, 12, 17, 35),
    )
    r_high = run_comparison(p_high)
    print("If home appreciates 3.4%/yr (less conservative):")
    for y in (7, 12, 17, 35):
        d = r_high["difference"][y]
        tag = " (retirement)" if y == 35 else ""
        print(f"  At {y} years{tag}: {format_currency(r_high['scenario1'][y])} (keep) vs {format_currency(r_high['scenario2'][y])} (sell) — diff {format_currency(d)}")
    print("(Set home_return_sequence or home_appreciation_rate in HouseScenarioParams for more cases.)")


if __name__ == "__main__":
    main()
