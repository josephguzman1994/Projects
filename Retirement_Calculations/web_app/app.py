#!/usr/bin/env python3
"""
Web API for Inheritance House Scenarios.
Exposes run_comparison and run_monte_carlo with JSON params and responses.
"""

import json
import math
import os
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# Run from project root so inheritance_house_scenarios can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, request, jsonify, send_from_directory
from dataclasses import asdict

from inheritance_house_scenarios import (
    HouseScenarioParams,
    CORRELATION_PRESETS,
    sample_stock_portfolio_returns,
    stock_profile_moments,
    default_params,
    merge_params,
    run_comparison,
    run_monte_carlo,
    run_scenarios,
    NUMPY_AVAILABLE,
)
from drawdown_engine import DrawdownEngine

if NUMPY_AVAILABLE:
    import numpy as np

app = Flask(__name__, static_folder="static", static_url_path="")

_PING_LOCK = threading.Lock()
_LAST_BROWSER_PING = 0.0
_HAS_SEEN_BROWSER_PING = False
_IDLE_SHUTDOWN_SECONDS = 20
MAX_SCENARIOS = 10
MIN_MC_PATHS = 500
MAX_MC_PATHS = 50000
ALLOWED_SCENARIO_TYPES = {
    "keep_property",
    "sell_invest",
    "sell_invest_withdrawals",
    "inheritance_only",
    "roth",
    "other_property",
}


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}
    return default


def params_from_json(data: dict) -> HouseScenarioParams:
    """Build HouseScenarioParams from JSON-friendly dict. Missing keys use defaults."""
    defaults = default_params()
    # Use defaults for any missing or null values
    def get(key: str, default):
        val = data.get(key)
        if val is None:
            return default
        return val

    benchmark = get("benchmark_years", list(defaults.benchmark_years))
    if isinstance(benchmark, list):
        cleaned = []
        for y in benchmark:
            try:
                yi = int(y)
            except (TypeError, ValueError):
                continue
            if 0 <= yi <= 120:
                cleaned.append(yi)
        benchmark = tuple(sorted(set(cleaned))) if cleaned else defaults.benchmark_years
    else:
        benchmark = defaults.benchmark_years

    home_seq = data.get("home_return_sequence")
    if home_seq is not None and isinstance(home_seq, list):
        home_seq = tuple(float(r) for r in home_seq)
    else:
        home_seq = defaults.home_return_sequence

    basis = data.get("basis_at_sale")
    if basis is not None and basis != "":
        try:
            basis = float(basis)
        except (TypeError, ValueError):
            basis = None
    else:
        basis = None

    home_value_today = _clamp(float(get("home_value_today", defaults.home_value_today)), 1.0, 1e12)
    years_live_in_before_sale = int(_clamp(int(get("years_live_in_before_sale", defaults.years_live_in_before_sale)), 1, 120))
    pct_cash_reserve = _clamp(float(get("pct_cash_reserve", defaults.pct_cash_reserve)), 0.0, 1.0)
    pct_invest = _clamp(float(get("pct_invest", defaults.pct_invest)), 0.0, 1.0)
    if abs((pct_cash_reserve + pct_invest) - 1.0) > 0.2:
        pct_invest = 1.0 - pct_cash_reserve
    corr_preset_raw = (str(get("correlation_preset", defaults.correlation_preset)).strip().lower() or defaults.correlation_preset)
    corr_preset = corr_preset_raw if corr_preset_raw in CORRELATION_PRESETS else defaults.correlation_preset
    stock_profile_raw = (str(get("stock_profile_preset", defaults.stock_profile_preset)).strip().lower() or defaults.stock_profile_preset)
    if stock_profile_raw not in {"overall_stock", "bond_profile", "three_fund", "custom_profile"}:
        stock_profile_raw = defaults.stock_profile_preset
    raw_assets = get("custom_stock_assets", defaults.custom_stock_assets)
    def _safe_float(v, default):
        try:
            return float(v)
        except (TypeError, ValueError):
            return float(default)
    custom_assets = []
    if isinstance(raw_assets, list):
        for i, a in enumerate(raw_assets[:10]):
            if not isinstance(a, dict):
                continue
            custom_assets.append({
                "name": str(a.get("name") or f"Asset {i + 1}")[:60],
                "weight": _clamp(_safe_float(a.get("weight", 0.0), 0.0), 0.0, 1.0),
                "mean": _clamp(_safe_float(a.get("mean", 0.0), 0.0), -0.5, 1.0),
                "std": _clamp(_safe_float(a.get("std", 0.0), 0.0), 0.0, 2.0),
            })
    return HouseScenarioParams(
        home_value_today=home_value_today,
        years_live_in_before_sale=years_live_in_before_sale,
        pct_cash_reserve=pct_cash_reserve,
        pct_invest=pct_invest,
        selling_costs_pct=_clamp(float(get("selling_costs_pct", defaults.selling_costs_pct)), 0.0, 0.5),
        basis_at_sale=basis,
        primary_residence_exclusion=_clamp(float(get("primary_residence_exclusion", defaults.primary_residence_exclusion)), 0.0, 5e6),
        capital_gains_tax_rate=_clamp(float(get("capital_gains_tax_rate", defaults.capital_gains_tax_rate)), 0.0, 0.6),
        home_appreciation_rate=_clamp(float(get("home_appreciation_rate", defaults.home_appreciation_rate)), -0.5, 1.0),
        home_return_sequence=home_seq,
        investment_return_rate=_clamp(float(get("investment_return_rate", defaults.investment_return_rate)), -0.5, 1.0),
        cash_reserve_return_rate=_clamp(float(get("cash_reserve_return_rate", defaults.cash_reserve_return_rate)), -0.1, 0.3),
        mc_n_paths=int(_clamp(int(get("mc_n_paths", defaults.mc_n_paths)), MIN_MC_PATHS, MAX_MC_PATHS)),
        use_fat_tails=_parse_bool(get("use_fat_tails", defaults.use_fat_tails), defaults.use_fat_tails),
        fat_tail_df=_clamp(float(get("fat_tail_df", defaults.fat_tail_df)), 2.1, 100.0),
        stock_return_mean=_clamp(float(get("stock_return_mean", defaults.stock_return_mean)), -0.5, 1.0),
        stock_return_std=_clamp(float(get("stock_return_std", defaults.stock_return_std)), 0.0, 2.0),
        stock_profile_preset=stock_profile_raw,
        custom_stock_assets=custom_assets,
        house_return_mean=_clamp(float(get("house_return_mean", defaults.house_return_mean)), -0.5, 1.0),
        house_return_std=_clamp(float(get("house_return_std", defaults.house_return_std)), 0.0, 2.0),
        withdrawal_start_year=int(_clamp(int(get("withdrawal_start_year", defaults.withdrawal_start_year)), 1, 120)),
        withdrawal_rate=_clamp(float(get("withdrawal_rate", defaults.withdrawal_rate)), 0.0, 0.3),
        include_scenario_4=_parse_bool(get("include_scenario_4", defaults.include_scenario_4), defaults.include_scenario_4),
        inheritance_portfolio_today=_clamp(float(get("inheritance_portfolio_today", defaults.inheritance_portfolio_today)), 0.0, 1e13),
        inheritance_growth_rate=_clamp(float(get("inheritance_growth_rate", defaults.inheritance_growth_rate)), -0.5, 1.0),
        inheritance_return_mean=_clamp(float(get("inheritance_return_mean", defaults.inheritance_return_mean)), -0.5, 1.0),
        inheritance_return_std=_clamp(float(get("inheritance_return_std", defaults.inheritance_return_std)), 0.0, 2.0),
        inheritance_years_until_receipt=int(_clamp(int(get("inheritance_years_until_receipt", defaults.inheritance_years_until_receipt)), 1, 120)),
        inheritance_beneficiary_share=_clamp(float(get("inheritance_beneficiary_share", defaults.inheritance_beneficiary_share)), 0.01, 1.0),
        benchmark_years=benchmark,
        inflation_rate=_clamp(float(get("inflation_rate", defaults.inflation_rate)), -0.05, 0.2),
        enable_stochastic_inflation=_parse_bool(get("enable_stochastic_inflation", defaults.enable_stochastic_inflation), defaults.enable_stochastic_inflation),
        inflation_return_mean=_clamp(float(get("inflation_return_mean", defaults.inflation_return_mean)), -0.05, 0.2),
        inflation_return_std=_clamp(float(get("inflation_return_std", defaults.inflation_return_std)), 0.0, 0.25),
        enable_correlation=_parse_bool(get("enable_correlation", defaults.enable_correlation), defaults.enable_correlation),
        correlation_preset=corr_preset,
        bond_return_mean=_clamp(float(get("bond_return_mean", defaults.bond_return_mean)), -0.2, 0.3),
        bond_return_std=_clamp(float(get("bond_return_std", defaults.bond_return_std)), 0.0, 0.5),
        retirement_income_rate=_clamp(float(get("retirement_income_rate", defaults.retirement_income_rate)), 0.005, 0.3),
        es_tail_pct=_clamp(float(get("es_tail_pct", defaults.es_tail_pct)), 0.005, 0.2),
        roth_balance_today=_clamp(float(get("roth_balance_today", defaults.roth_balance_today)), 0.0, 1e11),
        roth_annual_contribution=_clamp(float(get("roth_annual_contribution", defaults.roth_annual_contribution)), 0.0, 1e6),
        roth_contribution_years=int(_clamp(int(get("roth_contribution_years", defaults.roth_contribution_years)), 0, 120)),
        other_house_value_today=_clamp(float(get("other_house_value_today", defaults.other_house_value_today)), 0.0, 1e12),
        other_house_mortgage_remaining=_clamp(float(get("other_house_mortgage_remaining", defaults.other_house_mortgage_remaining)), 0.0, 1e12),
        other_house_mortgage_payoff_years=_clamp(float(get("other_house_mortgage_payoff_years", defaults.other_house_mortgage_payoff_years)), 0.1, 120.0),
        other_house_appreciation_rate=_clamp(float(get("other_house_appreciation_rate", defaults.other_house_appreciation_rate)), -0.5, 1.0),
    )


def serialize_comparison(results: dict) -> dict:
    """Convert run_comparison output to JSON-serializable dict."""
    out = {
        "benchmark_years": results["benchmark_years"],
        "scenario1": results["scenario1"],
        "scenario2": results["scenario2"],
        "scenario3": results["scenario3"],
        "scenario4": results["scenario4"],
        "difference": results["difference"],
        "roth_at_benchmark": results["roth_at_benchmark"],
        "other_house_equity_at_benchmark": results["other_house_equity_at_benchmark"],
        "sale_costs_breakdown": results["sale_costs_breakdown"],
        "params": asdict(results["params"]),
    }
    # Convert benchmark dict keys to strings for JSON; values stay numeric
    for key in ("scenario1", "scenario2", "scenario3", "scenario4", "difference", "roth_at_benchmark", "other_house_equity_at_benchmark"):
        out[key] = {str(k): v for k, v in out[key].items()}

    # Trajectories: (years, values) -> { years: [], scenario1: [], ... }
    t1_years, t1_vals = results["trajectory1"]
    t2_years, t2_vals = results["trajectory2"]
    t3_years, t3_vals = results["trajectory3"]
    t4_years, t4_vals = results["trajectory4"]
    roth_years, roth_vals = results["trajectory_roth"]
    other_years, other_vals = results["trajectory_other_house_equity"]

    out["trajectories"] = {
        "years": list(t1_years),
        "scenario1": list(t1_vals),
        "scenario2": list(t2_vals),
        "scenario3": list(t3_vals),
        "scenario4": list(t4_vals),
        "roth": list(roth_vals),
        "other_house_equity": list(other_vals),
    }
    out["sale_costs_breakdown"] = {k: (v if v == v else None) for k, v in results["sale_costs_breakdown"].items()}
    # params dataclass -> dict (for JSON)
    p = results["params"]
    out["params"] = asdict(p)
    # benchmark_years tuple -> list
    out["params"]["benchmark_years"] = list(p.benchmark_years)
    if p.home_return_sequence is not None:
        out["params"]["home_return_sequence"] = list(p.home_return_sequence)
    return out


def serialize_mc(mc_results: dict) -> dict:
    """Convert run_monte_carlo output to JSON-serializable dict."""
    if not mc_results:
        return {"error": "Monte Carlo not available (numpy required)"}

    def to_list(arr):
        try:
            return arr.tolist()
        except AttributeError:
            return list(arr)

    out = {
        "years": mc_results["years"],
        "benchmark_years": mc_results["benchmark_years"],
        "n_paths": mc_results["n_paths"],
        "s1_median": to_list(mc_results["s1_median"]),
        "s1_p10": to_list(mc_results["s1_p10"]),
        "s1_p25": to_list(mc_results["s1_p25"]),
        "s1_p75": to_list(mc_results["s1_p75"]),
        "s1_es": to_list(mc_results["s1_es"]),
        "s2_median": to_list(mc_results["s2_median"]),
        "s2_p10": to_list(mc_results["s2_p10"]),
        "s2_p25": to_list(mc_results["s2_p25"]),
        "s2_p75": to_list(mc_results["s2_p75"]),
        "s2_es": to_list(mc_results["s2_es"]),
        "s3_median": to_list(mc_results["s3_median"]),
        "s3_p10": to_list(mc_results["s3_p10"]),
        "s3_p25": to_list(mc_results["s3_p25"]),
        "s3_p75": to_list(mc_results["s3_p75"]),
        "s3_es": to_list(mc_results["s3_es"]),
        "benchmark_median1": {str(k): v for k, v in mc_results["benchmark_median1"].items()},
        "benchmark_median2": {str(k): v for k, v in mc_results["benchmark_median2"].items()},
        "benchmark_median3": {str(k): v for k, v in mc_results["benchmark_median3"].items()},
        "benchmark_p10_1": {str(k): v for k, v in mc_results["benchmark_p10_1"].items()},
        "benchmark_p10_2": {str(k): v for k, v in mc_results["benchmark_p10_2"].items()},
        "benchmark_p10_3": {str(k): v for k, v in mc_results["benchmark_p10_3"].items()},
        "benchmark_es_1": {str(k): v for k, v in mc_results["benchmark_es_1"].items()},
        "benchmark_es_2": {str(k): v for k, v in mc_results["benchmark_es_2"].items()},
        "benchmark_es_3": {str(k): v for k, v in mc_results["benchmark_es_3"].items()},
        "diff_medians": {str(k): v for k, v in mc_results["diff_medians"].items()},
        "benchmark_roth_median": {str(k): v for k, v in mc_results["benchmark_roth_median"].items()},
        "benchmark_roth_p10": {str(k): v for k, v in mc_results["benchmark_roth_p10"].items()},
        "benchmark_roth_es": {str(k): v for k, v in mc_results["benchmark_roth_es"].items()},
        "benchmark_other_house_equity": {str(k): v for k, v in mc_results["benchmark_other_house_equity"].items()},
        "roth_median": to_list(mc_results["roth_median"]),
        "roth_p10": to_list(mc_results["roth_p10"]),
        "roth_p25": to_list(mc_results["roth_p25"]),
        "roth_p75": to_list(mc_results["roth_p75"]),
        "roth_es": to_list(mc_results["roth_es"]),
        "es_tail_pct": mc_results.get("es_tail_pct"),
    }
    if mc_results.get("s4_median") is not None:
        out["s4_median"] = to_list(mc_results["s4_median"])
        out["s4_p10"] = to_list(mc_results["s4_p10"])
        out["s4_p25"] = to_list(mc_results["s4_p25"])
        out["s4_p75"] = to_list(mc_results["s4_p75"])
        out["s4_es"] = to_list(mc_results["s4_es"])
        out["benchmark_median4"] = {str(k): v for k, v in mc_results["benchmark_median4"].items()}
        out["benchmark_p10_4"] = {str(k): v for k, v in mc_results["benchmark_p10_4"].items()}
        out["benchmark_es_4"] = {str(k): v for k, v in mc_results["benchmark_es_4"].items()}
    return out


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/defaults", methods=["GET"])
def api_defaults():
    """Return default parameters as JSON."""
    p = default_params()
    d = asdict(p)
    d["benchmark_years"] = list(p.benchmark_years)
    d["home_return_sequence"] = list(p.home_return_sequence) if p.home_return_sequence else None
    return jsonify(d)


@app.route("/api/compare", methods=["POST"])
def api_compare():
    """Run deterministic comparison. Body: JSON object of parameters."""
    try:
        started = time.monotonic()
        data = request.get_json() or {}
        params = params_from_json(data)
        results = run_comparison(params)
        out = serialize_comparison(results)
        out["meta"] = {
            "runtime_ms": int((time.monotonic() - started) * 1000),
            "benchmark_count": len(out.get("benchmark_years") or []),
            "final_benchmark_year": max(out.get("benchmark_years") or [0]),
        }
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


def scenario_overrides_from_json(data: dict) -> dict:
    """Build overrides dict for merge_params. Frontend sends params with decimals (e.g. 0.25 for 25%)."""
    if not data or not isinstance(data, dict):
        return {}
    out = dict(data)
    if "benchmark_years" in out and isinstance(out["benchmark_years"], list):
        out["benchmark_years"] = tuple(int(y) for y in out["benchmark_years"])
    if "pct_invest" in out and "pct_cash_reserve" not in out:
        out["pct_cash_reserve"] = 1.0 - float(out["pct_invest"])
    return out


def _mc_series_for_scenario_type(mc: dict, scenario_type: str) -> dict:
    """Map run_monte_carlo output to scenario-specific median/p25/p75 series."""
    years = list(mc["years"])
    if scenario_type == "keep_property":
        return {
            "years": years,
            "median": list(mc["s1_median"]),
            "p10": list(mc["s1_p10"]),
            "p25": list(mc["s1_p25"]),
            "p75": list(mc["s1_p75"]),
            "es": list(mc["s1_es"]),
            "values_at_benchmark": {str(k): v for k, v in mc["benchmark_median1"].items()},
            "p25_at_benchmark": {str(k): float(mc["s1_p25"][k]) for k in mc["benchmark_median1"].keys()},
            "p75_at_benchmark": {str(k): float(mc["s1_p75"][k]) for k in mc["benchmark_median1"].keys()},
            "p10_at_benchmark": {str(k): v for k, v in mc["benchmark_p10_1"].items()},
            "es_at_benchmark": {str(k): v for k, v in mc["benchmark_es_1"].items()},
        }
    if scenario_type == "sell_invest":
        return {
            "years": years,
            "median": list(mc["s2_median"]),
            "p10": list(mc["s2_p10"]),
            "p25": list(mc["s2_p25"]),
            "p75": list(mc["s2_p75"]),
            "es": list(mc["s2_es"]),
            "values_at_benchmark": {str(k): v for k, v in mc["benchmark_median2"].items()},
            "p25_at_benchmark": {str(k): float(mc["s2_p25"][k]) for k in mc["benchmark_median2"].keys()},
            "p75_at_benchmark": {str(k): float(mc["s2_p75"][k]) for k in mc["benchmark_median2"].keys()},
            "p10_at_benchmark": {str(k): v for k, v in mc["benchmark_p10_2"].items()},
            "es_at_benchmark": {str(k): v for k, v in mc["benchmark_es_2"].items()},
        }
    if scenario_type == "sell_invest_withdrawals":
        return {
            "years": years,
            "median": list(mc["s3_median"]),
            "p10": list(mc["s3_p10"]),
            "p25": list(mc["s3_p25"]),
            "p75": list(mc["s3_p75"]),
            "es": list(mc["s3_es"]),
            "values_at_benchmark": {str(k): v for k, v in mc["benchmark_median3"].items()},
            "p25_at_benchmark": {str(k): float(mc["s3_p25"][k]) for k in mc["benchmark_median3"].keys()},
            "p75_at_benchmark": {str(k): float(mc["s3_p75"][k]) for k in mc["benchmark_median3"].keys()},
            "p10_at_benchmark": {str(k): v for k, v in mc["benchmark_p10_3"].items()},
            "es_at_benchmark": {str(k): v for k, v in mc["benchmark_es_3"].items()},
        }
    if scenario_type == "inheritance_only" and mc.get("s4_median") is not None:
        return {
            "years": years,
            "median": list(mc["s4_median"]),
            "p10": list(mc["s4_p10"]),
            "p25": list(mc["s4_p25"]),
            "p75": list(mc["s4_p75"]),
            "es": list(mc["s4_es"]),
            "values_at_benchmark": {str(k): v for k, v in mc["benchmark_median4"].items()},
            "p25_at_benchmark": {str(k): float(mc["s4_p25"][k]) for k in mc["benchmark_median4"].keys()},
            "p75_at_benchmark": {str(k): float(mc["s4_p75"][k]) for k in mc["benchmark_median4"].keys()},
            "p10_at_benchmark": {str(k): v for k, v in mc["benchmark_p10_4"].items()},
            "es_at_benchmark": {str(k): v for k, v in mc["benchmark_es_4"].items()},
        }
    if scenario_type == "roth":
        return {
            "years": years,
            "median": list(mc["roth_median"]),
            "p10": list(mc["roth_p10"]),
            "p25": list(mc["roth_p25"]),
            "p75": list(mc["roth_p75"]),
            "es": list(mc["roth_es"]),
            "values_at_benchmark": {str(k): v for k, v in mc["benchmark_roth_median"].items()},
            "p25_at_benchmark": {str(k): float(mc["roth_p25"][k]) for k in mc["benchmark_roth_median"].keys()},
            "p75_at_benchmark": {str(k): float(mc["roth_p75"][k]) for k in mc["benchmark_roth_median"].keys()},
            "p10_at_benchmark": {str(k): v for k, v in mc["benchmark_roth_p10"].items()},
            "es_at_benchmark": {str(k): v for k, v in mc["benchmark_roth_es"].items()},
        }
    return {}


def _run_one_scenario_mc(global_params_dict: dict, scenario_config: dict) -> tuple:
    """
    Run Monte Carlo for one scenario. Used by ProcessPoolExecutor and for in-process dedup.
    Returns (scenario_result_dict, inflation_report_rate_or_none).
    All args must be JSON-serializable so the worker can receive them.
    """
    base_params = params_from_json(global_params_dict)
    typ = str(scenario_config.get("type") or "")
    overrides = scenario_config.get("params") or {}
    params = merge_params(base_params, overrides)
    if typ == "inheritance_only":
        params.include_scenario_4 = True
    mc_results = run_monte_carlo(params)
    inflation = float(mc_results["inflation_report_rate"]) if params.enable_stochastic_inflation else None
    mapped = _mc_series_for_scenario_type(mc_results, typ)
    sid = str(scenario_config.get("id") or "")
    name = str(scenario_config.get("name") or sid)
    if not mapped:
        result = {
            "id": sid,
            "name": name,
            "type": typ,
            "years": [],
            "median": [],
            "p25": [],
            "p75": [],
            "values_at_benchmark": {},
            "p25_at_benchmark": {},
            "p75_at_benchmark": {},
            "p10_at_benchmark": {},
            "es_at_benchmark": {},
            "is_deterministic": True,
        }
        return (result, inflation)
    result = {
        "id": sid,
        "name": name,
        "type": typ,
        "years": mapped["years"],
        "median": mapped["median"],
        "p10": mapped.get("p10") or [],
        "p25": mapped["p25"],
        "p75": mapped["p75"],
        "es": mapped.get("es") or [],
        "values_at_benchmark": mapped["values_at_benchmark"],
        "p25_at_benchmark": mapped.get("p25_at_benchmark") or {},
        "p75_at_benchmark": mapped.get("p75_at_benchmark") or {},
        "p10_at_benchmark": mapped.get("p10_at_benchmark") or {},
        "es_at_benchmark": mapped.get("es_at_benchmark") or {},
    }
    return (result, inflation)


def _sample_returns_for_params(rng, params: HouseScenarioParams, mean: float, std: float, n_paths: int, max_year: int):
    if params.use_fat_tails:
        df = max(2.1, float(params.fat_tail_df))
        z = rng.standard_t(df=df, size=(n_paths, max_year + 1))
        z = z * math.sqrt((df - 2.0) / df)
        out = mean + std * z
    else:
        out = rng.normal(mean, std, size=(n_paths, max_year + 1))
    return np.clip(out, -0.99, 2.0)


def _sample_joint_factor_returns_for_params(rng, params: HouseScenarioParams, n_paths: int, max_year: int):
    """Sample stock/house/inflation factors with optional correlation presets."""
    corr_key = str(params.correlation_preset or "balanced").strip().lower()
    if corr_key not in CORRELATION_PRESETS:
        corr_key = "balanced"
    corr = np.array(CORRELATION_PRESETS[corr_key], dtype=float)
    stock_mean, stock_std = stock_profile_moments(params)
    stock_profile_key = str(params.stock_profile_preset or "overall_stock").strip().lower()
    if params.enable_correlation:
        if params.use_fat_tails:
            df = max(2.1, float(params.fat_tail_df))
            z = rng.standard_t(df=df, size=(n_paths, max_year + 1, 4))
            z = z * math.sqrt((df - 2.0) / df)
        else:
            z = rng.normal(0.0, 1.0, size=(n_paths, max_year + 1, 4))
        L = np.linalg.cholesky(corr + np.eye(4) * 1e-12)
        z = z @ L.T
        stock = np.clip(stock_mean + stock_std * z[:, :, 0], -0.99, 2.0)
        house = np.clip(params.house_return_mean + params.house_return_std * z[:, :, 2], -0.99, 2.0)
        inflation = np.clip(params.inflation_return_mean + params.inflation_return_std * z[:, :, 3], -0.20, 0.50)
    else:
        stock, stock_profile_key = sample_stock_portfolio_returns(rng, params, n_paths, max_year)
        house = _sample_returns_for_params(rng, params, params.house_return_mean, params.house_return_std, n_paths, max_year)
        if params.use_fat_tails:
            df = max(2.1, float(params.fat_tail_df))
            z = rng.standard_t(df=df, size=(n_paths, max_year + 1))
            z = z * math.sqrt((df - 2.0) / df)
            inflation = params.inflation_return_mean + params.inflation_return_std * z
        else:
            inflation = rng.normal(params.inflation_return_mean, params.inflation_return_std, size=(n_paths, max_year + 1))
        inflation = np.clip(inflation, -0.20, 0.50)
    return {
        "stock": stock,
        "house": house,
        "inflation": inflation,
        "correlation_preset": corr_key,
        "stock_profile_preset": stock_profile_key,
    }


def _net_proceeds_from_sale_local(sale_price: float, p: HouseScenarioParams) -> float:
    selling_costs = sale_price * p.selling_costs_pct
    basis = p.basis_at_sale if p.basis_at_sale is not None else p.home_value_today
    gain = max(0.0, sale_price - basis)
    taxable_gain = max(0.0, gain - p.primary_residence_exclusion)
    cap_gains_tax = taxable_gain * p.capital_gains_tax_rate
    return sale_price - selling_costs - cap_gains_tax


def _component_paths_for_type(rng, p: HouseScenarioParams, scenario_type: str, n_paths: int, max_year: int):
    """Return [n_paths, max_year+1] matrix for one component type."""
    out = np.zeros((n_paths, max_year + 1))
    factors = _sample_joint_factor_returns_for_params(rng, p, n_paths, max_year)
    if scenario_type == "other_property":
        house_returns = factors["house"]
        payoff_per_year = p.other_house_mortgage_remaining / max(1.0, p.other_house_mortgage_payoff_years)
        for path in range(n_paths):
            value = float(p.other_house_value_today)
            balance = float(p.other_house_mortgage_remaining)
            for t in range(max_year + 1):
                out[path, t] = max(0.0, value - balance)
                if t < max_year:
                    value = value * (1.0 + house_returns[path, t])
                    balance = max(0.0, balance - payoff_per_year)
        return out

    stock_returns = factors["stock"]
    house_returns = factors["house"]

    if scenario_type == "keep_property":
        for path in range(n_paths):
            val = float(p.home_value_today)
            for t in range(max_year + 1):
                out[path, t] = val
                if t < max_year:
                    val = val * (1.0 + house_returns[path, t])
        return out

    if scenario_type == "sell_invest":
        sale_year = int(p.years_live_in_before_sale)
        for path in range(n_paths):
            house_val = float(p.home_value_today)
            for t in range(sale_year + 1):
                if t <= max_year:
                    out[path, t] = house_val
                if t < sale_year:
                    house_val = house_val * (1.0 + house_returns[path, t])
            sale_price = house_val
            net_proceeds = _net_proceeds_from_sale_local(sale_price, p)
            cash_portion = net_proceeds * p.pct_cash_reserve
            invest_portion = net_proceeds * p.pct_invest
            for t in range(sale_year + 1, max_year + 1):
                years_growth = t - (sale_year + 1)
                cash_val = cash_portion * ((1 + p.cash_reserve_return_rate) ** (years_growth + 1))
                invest_val = invest_portion
                for y in range(sale_year + 1, t + 1):
                    invest_val = invest_val * (1.0 + stock_returns[path, y])
                out[path, t] = cash_val + invest_val
        return out

    if scenario_type == "sell_invest_withdrawals":
        sale_year = int(p.years_live_in_before_sale)
        withdraw_start = int(p.withdrawal_start_year)
        w_rate = float(p.withdrawal_rate)
        for path in range(n_paths):
            house_val = float(p.home_value_today)
            for t in range(sale_year + 1):
                if t <= max_year:
                    out[path, t] = house_val
                if t < sale_year:
                    house_val = house_val * (1.0 + house_returns[path, t])
            sale_price = house_val
            net_proceeds = _net_proceeds_from_sale_local(sale_price, p)
            cash_p = net_proceeds * p.pct_cash_reserve
            invest_p = net_proceeds * p.pct_invest
            for t in range(sale_year + 1, max_year + 1):
                if t >= withdraw_start:
                    total_beg = cash_p + invest_p
                    remaining = (1.0 - w_rate) * total_beg
                    cash_p = (remaining * p.pct_cash_reserve) * (1.0 + p.cash_reserve_return_rate)
                    invest_p = (remaining * p.pct_invest) * (1.0 + stock_returns[path, t])
                else:
                    cash_p = cash_p * (1.0 + p.cash_reserve_return_rate)
                    invest_p = invest_p * (1.0 + stock_returns[path, t])
                out[path, t] = cash_p + invest_p
        return out

    if scenario_type == "inheritance_only":
        inheritance_returns = _sample_returns_for_params(
            rng, p, p.inheritance_return_mean, p.inheritance_return_std, n_paths, max_year
        )
        for path in range(n_paths):
            port_val = float(p.inheritance_portfolio_today)
            for t in range(max_year + 1):
                out[path, t] = p.inheritance_beneficiary_share * port_val
                if t < max_year:
                    port_val = port_val * (1.0 + inheritance_returns[path, t])
        return out

    if scenario_type == "roth":
        for path in range(n_paths):
            balance = float(p.roth_balance_today)
            for t in range(max_year + 1):
                out[path, t] = balance
                if t < max_year:
                    balance = balance * (1.0 + stock_returns[path, t])
                    if t < p.roth_contribution_years:
                        balance += p.roth_annual_contribution
        return out

    return out


def _summarize_paths(paths, es_tail_pct: float) -> dict:
    """One sort for all percentiles and ES (efficiency gain)."""
    es_alpha = min(0.5, max(0.001, float(es_tail_pct)))
    n = paths.shape[0]
    sorted_paths = np.sort(paths, axis=0)
    k = max(1, int(math.ceil(es_alpha * n)))
    # Linear interpolation consistent with np.percentile(..., method="linear")
    def _perc(q):
        idx = (n - 1) * (q / 100.0)
        lo = int(np.floor(idx))
        hi = min(lo + 1, n - 1)
        w = idx - lo
        return (1.0 - w) * sorted_paths[lo, :] + w * sorted_paths[hi, :]
    p10 = _perc(10)
    p25 = _perc(25)
    median = _perc(50)
    p75 = _perc(75)
    es = np.mean(sorted_paths[:k, :], axis=0)
    return {
        "median": median,
        "p10": p10,
        "p25": p25,
        "p75": p75,
        "es": es,
        "es_tail_pct": es_alpha,
    }


@app.route("/api/scenarios", methods=["POST"])
def api_scenarios():
    """Run flexible scenario list. Body: { global_params: {...}, scenarios: [ { id, name, type, params } ] }."""
    try:
        started = time.monotonic()
        data = request.get_json() or {}
        global_data = data.get("global_params") or data
        params = params_from_json(global_data)
        raw_list = data.get("scenarios") or []
        if len(raw_list) > MAX_SCENARIOS:
            return jsonify({"error": f"Too many scenarios: max {MAX_SCENARIOS}."}), 400
        scenario_configs = []
        for i, s in enumerate(raw_list):
            sid = s.get("id") or s.get("name") or str(i)
            name = s.get("name") or "Unnamed"
            typ = s.get("type") or ""
            if typ not in ALLOWED_SCENARIO_TYPES:
                return jsonify({"error": f"Unsupported scenario type: {typ}"}), 400
            overrides = scenario_overrides_from_json(s.get("params") or {})
            scenario_configs.append({"id": sid, "name": name, "type": typ, "params": overrides})
        results = run_scenarios(params, scenario_configs)
        out = {
            "benchmark_years": results["benchmark_years"],
            "scenarios": {},
            "sale_breakdowns": results.get("sale_breakdowns") or {},
        }
        for sid, sc in results["scenarios"].items():
            out["scenarios"][sid] = {
                "name": sc["name"],
                "type": sc["type"],
                "years": sc["years"],
                "values": sc["values"],
                "values_at_benchmark": {str(k): v for k, v in sc["values_at_benchmark"].items()},
            }
        for sid, breakdown in out["sale_breakdowns"].items():
            out["sale_breakdowns"][sid] = {k: (v if v == v else None) for k, v in breakdown.items()}
        out["meta"] = {
            "runtime_ms": int((time.monotonic() - started) * 1000),
            "scenario_count": len(out["scenarios"]),
            "benchmark_count": len(out.get("benchmark_years") or []),
            "final_benchmark_year": max(out.get("benchmark_years") or [0]),
            "limits": {
                "max_scenarios": MAX_SCENARIOS,
                "mc_n_paths_min": MIN_MC_PATHS,
                "mc_n_paths_max": MAX_MC_PATHS,
            },
        }
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/monte_carlo", methods=["POST"])
def api_monte_carlo():
    """Run Monte Carlo simulation. Body: JSON object of parameters."""
    if not NUMPY_AVAILABLE:
        return jsonify({"error": "numpy is required for Monte Carlo"}), 400
    try:
        started = time.monotonic()
        data = request.get_json() or {}
        params = params_from_json(data)
        mc_results = run_monte_carlo(params)
        out = serialize_mc(mc_results)
        out["meta"] = {
            "runtime_ms": int((time.monotonic() - started) * 1000),
            "n_paths": out.get("n_paths"),
            "benchmark_count": len(out.get("benchmark_years") or []),
            "final_benchmark_year": max(out.get("benchmark_years") or [0]),
        }
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/scenarios_monte_carlo", methods=["POST"])
def api_scenarios_monte_carlo():
    """Run Monte Carlo for all scenarios in one request."""
    try:
        started = time.monotonic()
        data = request.get_json() or {}
        global_data = data.get("global_params") or data
        base_params = params_from_json(global_data)
        raw_list = data.get("scenarios") or []
        if len(raw_list) > MAX_SCENARIOS:
            return jsonify({"error": f"Too many scenarios: max {MAX_SCENARIOS}."}), 400
        scenario_configs = []
        for i, s in enumerate(raw_list):
            sid = s.get("id") or s.get("name") or str(i)
            name = s.get("name") or "Unnamed"
            typ = s.get("type") or ""
            if typ not in ALLOWED_SCENARIO_TYPES:
                return jsonify({"error": f"Unsupported scenario type: {typ}"}), 400
            overrides = scenario_overrides_from_json(s.get("params") or {})
            scenario_configs.append({"id": sid, "name": name, "type": typ, "params": overrides})

        deterministic = run_scenarios(base_params, scenario_configs)
        out = {
            "benchmark_years": deterministic.get("benchmark_years") or list(base_params.benchmark_years),
            "scenarios": {},
        }
        max_year = max(out["benchmark_years"]) if out["benchmark_years"] else 0
        rng = np.random.default_rng() if NUMPY_AVAILABLE else None
        inflation_report_rate = float(base_params.inflation_rate)

        # other_property: run in main process (uses _component_paths_for_type, not run_monte_carlo)
        for cfg in scenario_configs:
            sid = str(cfg["id"])
            typ = str(cfg.get("type") or "")
            name = str(cfg.get("name") or sid)
            if typ != "other_property":
                continue
            if not NUMPY_AVAILABLE:
                return jsonify({"error": "numpy is required for Monte Carlo"}), 400
            overrides = cfg.get("params") or {}
            params = merge_params(base_params, overrides)
            paths = _component_paths_for_type(rng, params, typ, int(params.mc_n_paths), max_year)
            summary = _summarize_paths(paths, params.es_tail_pct)
            bms = out["benchmark_years"] or []
            out["scenarios"][sid] = {
                "id": sid,
                "name": name,
                "type": typ,
                "years": list(range(max_year + 1)),
                "median": summary["median"].tolist(),
                "p10": summary["p10"].tolist(),
                "p25": summary["p25"].tolist(),
                "p75": summary["p75"].tolist(),
                "es": summary["es"].tolist(),
                "values_at_benchmark": {str(y): float(summary["median"][y]) for y in bms},
                "p25_at_benchmark": {str(y): float(summary["p25"][y]) for y in bms},
                "p75_at_benchmark": {str(y): float(summary["p75"][y]) for y in bms},
                "p10_at_benchmark": {str(y): float(summary["p10"][y]) for y in bms},
                "es_at_benchmark": {str(y): float(summary["es"][y]) for y in bms},
            }

        # Group MC scenarios by (type, params) so we run each unique combo once (dedup)
        mc_key_to_sids = {}  # (typ, params_json) -> [(sid, name), ...]
        mc_key_to_config = {}  # (typ, params_json) -> one cfg
        for cfg in scenario_configs:
            typ = str(cfg.get("type") or "")
            if typ == "other_property":
                continue
            overrides = cfg.get("params") or {}
            key = (typ, json.dumps(overrides, sort_keys=True))
            mc_key_to_sids.setdefault(key, []).append((str(cfg["id"]), str(cfg.get("name") or cfg["id"])))
            if key not in mc_key_to_config:
                mc_key_to_config[key] = cfg

        if not NUMPY_AVAILABLE and mc_key_to_sids:
            return jsonify({"error": "numpy is required for Monte Carlo"}), 400

        unique_mc_tasks = [(key, mc_key_to_config[key], mc_key_to_sids[key]) for key in mc_key_to_sids]
        max_workers = min(len(unique_mc_tasks), os.cpu_count() or 4, 8)

        if len(unique_mc_tasks) <= 1:
            # In-process to avoid process spawn overhead
            for key, config, sid_names in unique_mc_tasks:
                result, inf = _run_one_scenario_mc(global_data, config)
                if inf is not None:
                    inflation_report_rate = inf
                for sid, name in sid_names:
                    out["scenarios"][sid] = {**result, "id": sid, "name": name}
        else:
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_run_one_scenario_mc, global_data, config): (key, sid_names) for key, config, sid_names in unique_mc_tasks}
                for fut in futures:
                    key, sid_names = futures[fut]
                    try:
                        result, inf = fut.result()
                        if inf is not None:
                            inflation_report_rate = inf
                        for sid, name in sid_names:
                            out["scenarios"][sid] = {**result, "id": sid, "name": name}
                    except Exception as e:
                        return jsonify({"error": str(e)}), 400

        # Keep benchmark years aligned with any scenario-specific outputs (e.g. inheritance receipt year).
        years_union = set(int(y) for y in out.get("benchmark_years", []))
        for sc in out["scenarios"].values():
            for y in (sc.get("values_at_benchmark") or {}).keys():
                try:
                    years_union.add(int(y))
                except (TypeError, ValueError):
                    pass
        out["benchmark_years"] = sorted(years_union)
        out["meta"] = {
            "runtime_ms": int((time.monotonic() - started) * 1000),
            "scenario_count": len(out["scenarios"]),
            "benchmark_count": len(out.get("benchmark_years") or []),
            "final_benchmark_year": max(out.get("benchmark_years") or [0]),
            "inflation_report_rate": inflation_report_rate,
            "stochastic_inflation_enabled": bool(base_params.enable_stochastic_inflation),
            "correlation_enabled": bool(base_params.enable_correlation),
            "correlation_preset": base_params.correlation_preset,
            "stock_profile_preset": base_params.stock_profile_preset,
            "limits": {
                "max_scenarios": MAX_SCENARIOS,
                "mc_n_paths_min": MIN_MC_PATHS,
                "mc_n_paths_max": MAX_MC_PATHS,
            },
        }

        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/plans", methods=["POST"])
def api_plans():
    """Combine selected components into plans and compute deterministic + MC stats."""
    if not NUMPY_AVAILABLE:
        return jsonify({"error": "numpy is required for plan Monte Carlo"}), 400
    try:
        started = time.monotonic()
        data = request.get_json() or {}
        global_data = data.get("global_params") or data
        base_params = params_from_json(global_data)

        raw_components = data.get("components")
        if raw_components is None:
            raw_components = data.get("scenarios") or []
        if len(raw_components) > MAX_SCENARIOS:
            return jsonify({"error": f"Too many components: max {MAX_SCENARIOS}."}), 400

        component_configs = []
        component_ids = []
        for i, c in enumerate(raw_components):
            cid = str(c.get("id") or c.get("name") or f"c{i}")
            name = str(c.get("name") or cid)
            typ = str(c.get("type") or "")
            if typ not in ALLOWED_SCENARIO_TYPES:
                return jsonify({"error": f"Unsupported component type: {typ}"}), 400
            overrides = scenario_overrides_from_json(c.get("params") or {})
            component_configs.append({"id": cid, "name": name, "type": typ, "params": overrides})
            component_ids.append(cid)

        if not component_configs:
            return jsonify({"error": "No components provided."}), 400

        raw_plans = data.get("plans") or [{
            "id": "combined",
            "name": "Combined selected scenarios",
            "component_ids": component_ids,
        }]
        if len(raw_plans) > MAX_SCENARIOS:
            return jsonify({"error": f"Too many plans: max {MAX_SCENARIOS}."}), 400

        deterministic = run_scenarios(base_params, component_configs)
        benchmark_years = list(deterministic.get("benchmark_years") or list(base_params.benchmark_years))
        benchmark_max = max(benchmark_years) if benchmark_years else 0

        draw_cfg, _ = DrawdownEngine.parse_config(
            data.get("drawdown") or {},
            default_withdrawal_rate=base_params.retirement_income_rate,
            default_inflation_rate=base_params.inflation_rate,
            default_growth_rate=base_params.stock_return_mean,
        )
        path_max_year = benchmark_max
        if draw_cfg.enabled and getattr(draw_cfg, "end_year", None) is not None:
            path_max_year = max(path_max_year, int(draw_cfg.end_year))
            benchmark_years = sorted(set(benchmark_years) | {int(draw_cfg.end_year)})

        years = list(range(path_max_year + 1))
        n_paths = int(base_params.mc_n_paths)

        by_id = {c["id"]: c for c in component_configs}
        component_paths = {}
        rng = np.random.default_rng()
        for c in component_configs:
            p = merge_params(base_params, c.get("params") or {})
            if c["type"] == "inheritance_only":
                p.include_scenario_4 = True
            component_paths[c["id"]] = _component_paths_for_type(rng, p, c["type"], n_paths, path_max_year)

        plans_out = {}
        deterministic_scenarios = deterministic.get("scenarios") or {}
        for i, plan in enumerate(raw_plans):
            pid = str(plan.get("id") or f"p{i}")
            pname = str(plan.get("name") or pid)
            plan_component_ids = [str(x) for x in (plan.get("component_ids") or [])]
            if not plan_component_ids:
                return jsonify({"error": f"Plan '{pid}' has no component_ids."}), 400
            for cid in plan_component_ids:
                if cid not in by_id:
                    return jsonify({"error": f"Plan '{pid}' references unknown component '{cid}'."}), 400

            summed_paths = np.zeros((n_paths, path_max_year + 1))
            det_total = np.zeros(path_max_year + 1)
            for cid in plan_component_ids:
                summed_paths += component_paths[cid]
                det_vals = (deterministic_scenarios.get(cid) or {}).get("values") or []
                if det_vals:
                    arr = np.array(det_vals, dtype=float)
                    if arr.shape[0] < path_max_year + 1:
                        arr = np.pad(arr, (0, path_max_year + 1 - arr.shape[0]), mode="edge")
                    det_total += arr[: path_max_year + 1]

            s = _summarize_paths(summed_paths, base_params.es_tail_pct)
            plans_out[pid] = {
                "id": pid,
                "name": pname,
                "component_ids": plan_component_ids,
                "years": years,
                "values": det_total.tolist(),
                "values_at_benchmark": {str(y): float(det_total[y]) for y in benchmark_years},
                "median": s["median"].tolist(),
                "p10": s["p10"].tolist(),
                "p25": s["p25"].tolist(),
                "p75": s["p75"].tolist(),
                "es": s["es"].tolist(),
                "p10_at_benchmark": {str(y): float(s["p10"][y]) for y in benchmark_years},
                "p25_at_benchmark": {str(y): float(s["p25"][y]) for y in benchmark_years},
                "p75_at_benchmark": {str(y): float(s["p75"][y]) for y in benchmark_years},
                "es_at_benchmark": {str(y): float(s["es"][y]) for y in benchmark_years},
            }

        return jsonify({
            "benchmark_years": benchmark_years,
            "plans": plans_out,
            "meta": {
                "runtime_ms": int((time.monotonic() - started) * 1000),
                "component_count": len(component_configs),
                "plan_count": len(plans_out),
                "n_paths": n_paths,
                "final_benchmark_year": max(benchmark_years) if benchmark_years else 0,
                "inflation_report_rate": float(base_params.inflation_return_mean if base_params.enable_stochastic_inflation else base_params.inflation_rate),
                "stochastic_inflation_enabled": bool(base_params.enable_stochastic_inflation),
                "correlation_enabled": bool(base_params.enable_correlation),
                "correlation_preset": base_params.correlation_preset,
                "stock_profile_preset": base_params.stock_profile_preset,
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/drawdown", methods=["POST"])
def api_drawdown():
    """Phase A drawdown analysis on combined plan paths."""
    if not NUMPY_AVAILABLE:
        return jsonify({"error": "numpy is required for drawdown analysis"}), 400
    try:
        started = time.monotonic()
        data = request.get_json() or {}
        global_data = data.get("global_params") or data
        base_params = params_from_json(global_data)

        raw_components = data.get("components")
        if raw_components is None:
            raw_components = data.get("scenarios") or []
        if len(raw_components) > MAX_SCENARIOS:
            return jsonify({"error": f"Too many components: max {MAX_SCENARIOS}."}), 400

        component_configs = []
        component_ids = []
        for i, c in enumerate(raw_components):
            cid = str(c.get("id") or c.get("name") or f"c{i}")
            name = str(c.get("name") or cid)
            typ = str(c.get("type") or "")
            if typ not in ALLOWED_SCENARIO_TYPES:
                return jsonify({"error": f"Unsupported component type: {typ}"}), 400
            overrides = scenario_overrides_from_json(c.get("params") or {})
            component_configs.append({"id": cid, "name": name, "type": typ, "params": overrides})
            component_ids.append(cid)

        if not component_configs:
            return jsonify({"error": "No components provided."}), 400

        raw_plans = data.get("plans") or [{
            "id": "combined",
            "name": "Combined selected scenarios",
            "component_ids": component_ids,
        }]
        if len(raw_plans) > MAX_SCENARIOS:
            return jsonify({"error": f"Too many plans: max {MAX_SCENARIOS}."}), 400

        deterministic = run_scenarios(base_params, component_configs)
        benchmark_years = list(deterministic.get("benchmark_years") or list(base_params.benchmark_years))
        benchmark_max = max(benchmark_years) if benchmark_years else 0

        draw_cfg, cfg_warnings = DrawdownEngine.parse_config(
            data.get("drawdown") or {},
            default_withdrawal_rate=base_params.retirement_income_rate,
            default_inflation_rate=base_params.inflation_rate,
            default_growth_rate=base_params.stock_return_mean,
        )
        # Extend path horizon to end of retirement so drawdown can simulate full period
        path_max_year = benchmark_max
        if draw_cfg.enabled and draw_cfg.end_year is not None:
            path_max_year = max(path_max_year, int(draw_cfg.end_year))

        n_paths = int(base_params.mc_n_paths)
        by_id = {c["id"]: c for c in component_configs}
        component_paths = {}
        rng = np.random.default_rng()
        for c in component_configs:
            p = merge_params(base_params, c.get("params") or {})
            if c["type"] == "inheritance_only":
                p.include_scenario_4 = True
            component_paths[c["id"]] = _component_paths_for_type(rng, p, c["type"], n_paths, path_max_year)

        inflation_for_drawdown = (
            float(base_params.inflation_return_mean)
            if draw_cfg.inflation_mode_for_spending == "stochastic_path"
            else float(base_params.inflation_rate)
        )

        plans_out = {}
        for i, plan in enumerate(raw_plans):
            pid = str(plan.get("id") or f"p{i}")
            pname = str(plan.get("name") or pid)
            plan_component_ids = [str(x) for x in (plan.get("component_ids") or [])]
            if not plan_component_ids:
                return jsonify({"error": f"Plan '{pid}' has no component_ids."}), 400
            for cid in plan_component_ids:
                if cid not in by_id:
                    return jsonify({"error": f"Plan '{pid}' references unknown component '{cid}'."}), 400

            summed_paths = np.zeros((n_paths, path_max_year + 1))
            for cid in plan_component_ids:
                summed_paths += component_paths[cid]

            plans_out[pid] = {
                "id": pid,
                "name": pname,
                "component_ids": plan_component_ids,
                "drawdown": DrawdownEngine.analyze_plan_paths(
                    summed_paths, draw_cfg, inflation_for_drawdown
                ),
            }

        return jsonify({
            "benchmark_years": benchmark_years,
            "plans": plans_out,
            "meta": {
                "runtime_ms": int((time.monotonic() - started) * 1000),
                "component_count": len(component_configs),
                "plan_count": len(plans_out),
                "n_paths": n_paths,
                "drawdown_rule": draw_cfg.spending_rule,
                "inflation_mode_for_spending": draw_cfg.inflation_mode_for_spending,
                "success_threshold": draw_cfg.success_threshold,
                "warnings": cfg_warnings,
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/ping", methods=["POST"])
def api_ping():
    """Heartbeat endpoint so local dev server can auto-exit after browser closes."""
    global _LAST_BROWSER_PING, _HAS_SEEN_BROWSER_PING
    with _PING_LOCK:
        _LAST_BROWSER_PING = time.monotonic()
        _HAS_SEEN_BROWSER_PING = True
    return jsonify({"ok": True})


def _idle_shutdown_watchdog():
    """Best-effort local-dev shutdown when no browser heartbeats are received."""
    while True:
        time.sleep(2.0)
        with _PING_LOCK:
            has_ping = _HAS_SEEN_BROWSER_PING
            last_ping = _LAST_BROWSER_PING
        if not has_ping:
            continue
        if time.monotonic() - last_ping > _IDLE_SHUTDOWN_SECONDS:
            print("No browser heartbeat detected; shutting down.")
            os._exit(0)


if __name__ == "__main__":
    import webbrowser

    def open_browser():
        time.sleep(1.5)  # give the server a moment to start
        webbrowser.open("http://127.0.0.1:5000/")

    threading.Thread(target=open_browser, daemon=True).start()
    threading.Thread(target=_idle_shutdown_watchdog, daemon=True).start()
    print("Opening http://127.0.0.1:5000/ in your browser...")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
