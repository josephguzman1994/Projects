#!/usr/bin/env python3
"""
Web API for Inheritance House Scenarios.
Exposes run_comparison and run_monte_carlo with JSON params and responses.
"""

import json
import os
import sys
import threading
import time
from pathlib import Path

# Run from project root so inheritance_house_scenarios can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, request, jsonify, send_from_directory
from dataclasses import asdict

from inheritance_house_scenarios import (
    HouseScenarioParams,
    default_params,
    merge_params,
    run_comparison,
    run_monte_carlo,
    run_scenarios,
    NUMPY_AVAILABLE,
)

app = Flask(__name__, static_folder="static", static_url_path="")

_PING_LOCK = threading.Lock()
_LAST_BROWSER_PING = 0.0
_HAS_SEEN_BROWSER_PING = False
_IDLE_SHUTDOWN_SECONDS = 20


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
        benchmark = tuple(int(y) for y in benchmark)
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

    return HouseScenarioParams(
        home_value_today=float(get("home_value_today", defaults.home_value_today)),
        years_live_in_before_sale=int(get("years_live_in_before_sale", defaults.years_live_in_before_sale)),
        pct_cash_reserve=float(get("pct_cash_reserve", defaults.pct_cash_reserve)),
        pct_invest=float(get("pct_invest", defaults.pct_invest)),
        selling_costs_pct=float(get("selling_costs_pct", defaults.selling_costs_pct)),
        basis_at_sale=basis,
        primary_residence_exclusion=float(get("primary_residence_exclusion", defaults.primary_residence_exclusion)),
        capital_gains_tax_rate=float(get("capital_gains_tax_rate", defaults.capital_gains_tax_rate)),
        home_appreciation_rate=float(get("home_appreciation_rate", defaults.home_appreciation_rate)),
        home_return_sequence=home_seq,
        investment_return_rate=float(get("investment_return_rate", defaults.investment_return_rate)),
        cash_reserve_return_rate=float(get("cash_reserve_return_rate", defaults.cash_reserve_return_rate)),
        mc_n_paths=int(get("mc_n_paths", defaults.mc_n_paths)),
        use_fat_tails=bool(get("use_fat_tails", defaults.use_fat_tails)),
        fat_tail_df=float(get("fat_tail_df", defaults.fat_tail_df)),
        stock_return_mean=float(get("stock_return_mean", defaults.stock_return_mean)),
        stock_return_std=float(get("stock_return_std", defaults.stock_return_std)),
        house_return_mean=float(get("house_return_mean", defaults.house_return_mean)),
        house_return_std=float(get("house_return_std", defaults.house_return_std)),
        withdrawal_start_year=int(get("withdrawal_start_year", defaults.withdrawal_start_year)),
        withdrawal_rate=float(get("withdrawal_rate", defaults.withdrawal_rate)),
        include_scenario_4=bool(get("include_scenario_4", defaults.include_scenario_4)),
        inheritance_portfolio_today=float(get("inheritance_portfolio_today", defaults.inheritance_portfolio_today)),
        inheritance_growth_rate=float(get("inheritance_growth_rate", defaults.inheritance_growth_rate)),
        inheritance_return_mean=float(get("inheritance_return_mean", defaults.inheritance_return_mean)),
        inheritance_return_std=float(get("inheritance_return_std", defaults.inheritance_return_std)),
        inheritance_years_until_receipt=int(get("inheritance_years_until_receipt", defaults.inheritance_years_until_receipt)),
        inheritance_beneficiary_share=float(get("inheritance_beneficiary_share", defaults.inheritance_beneficiary_share)),
        benchmark_years=benchmark,
        inflation_rate=float(get("inflation_rate", defaults.inflation_rate)),
        retirement_income_rate=float(get("retirement_income_rate", defaults.retirement_income_rate)),
        es_tail_pct=float(get("es_tail_pct", defaults.es_tail_pct)),
        roth_balance_today=float(get("roth_balance_today", defaults.roth_balance_today)),
        roth_annual_contribution=float(get("roth_annual_contribution", defaults.roth_annual_contribution)),
        roth_contribution_years=int(get("roth_contribution_years", defaults.roth_contribution_years)),
        other_house_value_today=float(get("other_house_value_today", defaults.other_house_value_today)),
        other_house_mortgage_remaining=float(get("other_house_mortgage_remaining", defaults.other_house_mortgage_remaining)),
        other_house_mortgage_payoff_years=float(get("other_house_mortgage_payoff_years", defaults.other_house_mortgage_payoff_years)),
        other_house_appreciation_rate=float(get("other_house_appreciation_rate", defaults.other_house_appreciation_rate)),
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
        data = request.get_json() or {}
        params = params_from_json(data)
        results = run_comparison(params)
        return jsonify(serialize_comparison(results))
    except Exception as e:
        return jsonify({"error": str(e)}), 400


def scenario_overrides_from_json(data: dict) -> dict:
    """Build overrides dict for merge_params. Frontend sends params with decimals (e.g. 0.25 for 25%)."""
    if not data:
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


@app.route("/api/scenarios", methods=["POST"])
def api_scenarios():
    """Run flexible scenario list. Body: { global_params: {...}, scenarios: [ { id, name, type, params } ] }."""
    try:
        data = request.get_json() or {}
        global_data = data.get("global_params") or data
        params = params_from_json(global_data)
        raw_list = data.get("scenarios") or []
        scenario_configs = []
        for i, s in enumerate(raw_list):
            sid = s.get("id") or s.get("name") or str(i)
            name = s.get("name") or "Unnamed"
            typ = s.get("type") or ""
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
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/monte_carlo", methods=["POST"])
def api_monte_carlo():
    """Run Monte Carlo simulation. Body: JSON object of parameters."""
    if not NUMPY_AVAILABLE:
        return jsonify({"error": "numpy is required for Monte Carlo"}), 400
    try:
        data = request.get_json() or {}
        params = params_from_json(data)
        mc_results = run_monte_carlo(params)
        return jsonify(serialize_mc(mc_results))
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/scenarios_monte_carlo", methods=["POST"])
def api_scenarios_monte_carlo():
    """Run Monte Carlo for all scenarios in one request."""
    try:
        data = request.get_json() or {}
        global_data = data.get("global_params") or data
        base_params = params_from_json(global_data)
        raw_list = data.get("scenarios") or []
        scenario_configs = []
        for i, s in enumerate(raw_list):
            sid = s.get("id") or s.get("name") or str(i)
            name = s.get("name") or "Unnamed"
            typ = s.get("type") or ""
            overrides = scenario_overrides_from_json(s.get("params") or {})
            scenario_configs.append({"id": sid, "name": name, "type": typ, "params": overrides})

        # Deterministic outputs are used for non-MC scenario types (e.g. other_property).
        deterministic = run_scenarios(base_params, scenario_configs)
        out = {
            "benchmark_years": deterministic.get("benchmark_years") or list(base_params.benchmark_years),
            "scenarios": {},
        }

        for cfg in scenario_configs:
            sid = str(cfg["id"])
            typ = str(cfg.get("type") or "")
            name = str(cfg.get("name") or sid)
            overrides = cfg.get("params") or {}

            if typ == "other_property":
                det = (deterministic.get("scenarios") or {}).get(sid) or {}
                out["scenarios"][sid] = {
                    "id": sid,
                    "name": name,
                    "type": typ,
                    "years": det.get("years") or [],
                    "values": det.get("values") or [],
                    "values_at_benchmark": {str(k): v for k, v in (det.get("values_at_benchmark") or {}).items()},
                    "p25_at_benchmark": {},
                    "p75_at_benchmark": {},
                    "p10_at_benchmark": {},
                    "es_at_benchmark": {},
                    "is_deterministic": True,
                }
                continue

            if not NUMPY_AVAILABLE:
                return jsonify({"error": "numpy is required for Monte Carlo"}), 400

            params = merge_params(base_params, overrides)
            if typ == "inheritance_only":
                params.include_scenario_4 = True
            mc_results = run_monte_carlo(params)
            mapped = _mc_series_for_scenario_type(mc_results, typ)
            if not mapped:
                out["scenarios"][sid] = {
                    "id": sid,
                    "name": name,
                    "type": typ,
                    "years": [],
                    "median": [],
                    "p25": [],
                    "p75": [],
                    "values_at_benchmark": {},
                    "is_deterministic": True,
                }
                continue
            out["scenarios"][sid] = {
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

        # Keep benchmark years aligned with any scenario-specific outputs (e.g. inheritance receipt year).
        years_union = set(int(y) for y in out.get("benchmark_years", []))
        for sc in out["scenarios"].values():
            for y in (sc.get("values_at_benchmark") or {}).keys():
                try:
                    years_union.add(int(y))
                except (TypeError, ValueError):
                    pass
        out["benchmark_years"] = sorted(years_union)

        return jsonify(out)
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
