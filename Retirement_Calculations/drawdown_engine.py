from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


@dataclass
class IncomeSource:
    id: str
    name: str
    start_year: int
    end_year: int
    amount_today: float
    inflation_linked: bool = True


@dataclass
class DrawdownConfig:
    enabled: bool
    start_year: int
    end_year: int
    spending_today: float
    replacement_income_today: float
    spending_rule: str = "real_flat"
    success_threshold: float = 0.90
    safe_withdrawal_rate: float = 0.045
    inflation_mode_for_spending: str = "flat"
    coast_growth_rate: float = 0.06
    income_sources: List[IncomeSource] = None
    retirement_year_candidates: List[int] = None
    target_terminal_fraction: float = 0.0  # 0 = exhaust by end; 0.1 = leave 10% of start


class DrawdownEngine:
    @staticmethod
    def parse_config(
        data: Dict[str, Any],
        default_withdrawal_rate: float,
        default_inflation_rate: float,
        default_growth_rate: float,
    ) -> Tuple[DrawdownConfig, List[str]]:
        cfg = data or {}
        warnings: List[str] = []
        enabled = bool(cfg.get("enabled", True))
        start_year = int(_clamp(cfg.get("start_year", 35), 0, 120))
        end_year = int(_clamp(cfg.get("end_year", 70), start_year + 1, 120))
        spending_today = max(0.0, float(cfg.get("spending_today", 0.0)))
        replacement_income_today = max(0.0, float(cfg.get("replacement_income_today", spending_today)))
        spending_rule = str(cfg.get("spending_rule", "real_flat") or "real_flat").strip().lower()
        if spending_rule != "real_flat":
            warnings.append(f"Unsupported spending_rule '{spending_rule}', using real_flat.")
            spending_rule = "real_flat"
        success_threshold = _clamp(float(cfg.get("success_threshold", 0.90)), 0.50, 0.99)
        safe_withdrawal_rate = _clamp(float(cfg.get("safe_withdrawal_rate", default_withdrawal_rate)), 0.005, 0.15)
        inflation_mode = str(cfg.get("inflation_mode_for_spending", "flat") or "flat").strip().lower()
        if inflation_mode not in {"flat", "stochastic_path"}:
            warnings.append(f"Unsupported inflation_mode_for_spending '{inflation_mode}', using flat.")
            inflation_mode = "flat"
        coast_growth_rate = _clamp(float(cfg.get("coast_growth_rate", default_growth_rate)), -0.02, 0.20)

        raw_income = cfg.get("income_sources") or []
        income_sources: List[IncomeSource] = []
        for i, src in enumerate(raw_income[:20]):
            if not isinstance(src, dict):
                continue
            sid = str(src.get("id") or f"income_{i + 1}")
            sname = str(src.get("name") or sid)
            syear = int(_clamp(src.get("start_year", start_year), 0, 120))
            eyear = int(_clamp(src.get("end_year", 120), syear, 120))
            amt = max(0.0, float(src.get("amount_today", 0.0)))
            infl = bool(src.get("inflation_linked", True))
            income_sources.append(
                IncomeSource(
                    id=sid,
                    name=sname,
                    start_year=syear,
                    end_year=eyear,
                    amount_today=amt,
                    inflation_linked=infl,
                )
            )

        # Phase A default: automatically scan every possible retirement year from "today" (year 0)
        # through the configured end year.
        retirement_candidates = list(range(0, end_year + 1))

        target_terminal_fraction = _clamp(float(cfg.get("target_terminal_fraction", 0.0)), 0.0, 1.0)

        parsed = DrawdownConfig(
            enabled=enabled,
            start_year=start_year,
            end_year=end_year,
            spending_today=spending_today,
            replacement_income_today=replacement_income_today,
            spending_rule=spending_rule,
            success_threshold=success_threshold,
            safe_withdrawal_rate=safe_withdrawal_rate,
            inflation_mode_for_spending=inflation_mode,
            coast_growth_rate=coast_growth_rate,
            income_sources=income_sources,
            retirement_year_candidates=retirement_candidates,
            target_terminal_fraction=target_terminal_fraction,
        )
        return parsed, warnings

    @staticmethod
    def _nominal_amount_today(amount_today: float, year: int, inflation_rate: float) -> float:
        return float(amount_today) * ((1.0 + float(inflation_rate)) ** int(year))

    @staticmethod
    def _build_income_nominal_by_year(
        years: List[int], income_sources: List[IncomeSource], inflation_rate: float
    ) -> Dict[int, float]:
        out = {y: 0.0 for y in years}
        for src in income_sources or []:
            for y in years:
                if y < src.start_year or y > src.end_year:
                    continue
                if src.inflation_linked:
                    out[y] += DrawdownEngine._nominal_amount_today(src.amount_today, y, inflation_rate)
                else:
                    out[y] += float(src.amount_today)
        return out

    @staticmethod
    def _simulate_drawdown_for_start_year(
        paths: np.ndarray,
        cfg: DrawdownConfig,
        inflation_rate: float,
        start_year: int,
    ) -> Dict[str, Any]:
        n_paths, n_years = paths.shape
        max_year = n_years - 1
        end_year = min(cfg.end_year, max_year)
        if start_year > end_year:
            return {
                "success_probability": 0.0,
                "failure_probability": 1.0,
                "median_depletion_year": None,
                "depletion_probability_by_end_year": 1.0,
                "yearly": {"years": []},
            }

        years = list(range(start_year, end_year + 1))
        income_by_year = DrawdownEngine._build_income_nominal_by_year(years, cfg.income_sources, inflation_rate)
        eps = 1e-9

        balance = np.array(paths[:, start_year], dtype=float)
        spending_t = np.zeros((n_paths, len(years)))
        income_t = np.zeros((n_paths, len(years)))
        withdrawal_t = np.zeros((n_paths, len(years)))
        shortfall_t = np.zeros((n_paths, len(years)))
        end_balance_t = np.zeros((n_paths, len(years)))
        depletion_year = np.full(n_paths, -1, dtype=int)

        for i, y in enumerate(years):
            spend_nom = DrawdownEngine._nominal_amount_today(cfg.spending_today, y, inflation_rate)
            income_nom = float(income_by_year.get(y, 0.0))
            net_needed = max(0.0, spend_nom - income_nom)

            spend_arr = np.full(n_paths, spend_nom)
            income_arr = np.full(n_paths, income_nom)
            withdraw = np.minimum(balance, net_needed)
            short = np.maximum(0.0, net_needed - withdraw)
            after = balance - withdraw

            spending_t[:, i] = spend_arr
            income_t[:, i] = income_arr
            withdrawal_t[:, i] = withdraw
            shortfall_t[:, i] = short

            just_depleted = (depletion_year < 0) & (short > 0.0)
            depletion_year[just_depleted] = y

            if y < end_year:
                denom = np.maximum(paths[:, y], eps)
                growth = np.clip(paths[:, y + 1] / denom, 0.0, 10.0)
                balance = after * growth
            else:
                balance = after
            end_balance_t[:, i] = balance

        success = np.all(shortfall_t <= eps, axis=1)
        success_prob = float(np.mean(success))
        # Depletion = fraction of paths where portfolio balance hit 0 before retirement end
        depleted = np.any(end_balance_t <= eps, axis=1)
        dep_prob = float(np.mean(depleted))
        dep_vals = depletion_year[depletion_year >= 0]
        med_dep = int(np.median(dep_vals)) if dep_vals.size > 0 else None
        # Average year (over depleted paths) when portfolio balance first reaches 0
        first_year_balance_zero = np.full(n_paths, -1, dtype=np.float64)
        for i, y in enumerate(years):
            hit = (end_balance_t[:, i] <= eps) & (first_year_balance_zero < 0)
            first_year_balance_zero[hit] = float(y)
        depleted_idx = first_year_balance_zero >= 0
        avg_year_balance_hits_zero = (
            float(np.mean(first_year_balance_zero[depleted_idx]))
            if np.any(depleted_idx) else None
        )

        def q(arr: np.ndarray, pct: float) -> List[float]:
            return np.percentile(arr, pct, axis=0).tolist()

        yearly = {
            "years": years,
            "spending_nominal_p50": q(spending_t, 50),
            "spending_today_p50": [cfg.spending_today for _ in years],
            "income_sources_nominal_p50": q(income_t, 50),
            "portfolio_withdrawal_nominal_p50": q(withdrawal_t, 50),
            "shortfall_nominal_p50": q(shortfall_t, 50),
            "shortfall_probability": np.mean(shortfall_t > eps, axis=0).tolist(),
            "portfolio_end_nominal_p50": q(end_balance_t, 50),
            "spending_nominal_p10": q(spending_t, 10),
            "spending_nominal_p90": q(spending_t, 90),
            "portfolio_end_nominal_p10": q(end_balance_t, 10),
            "portfolio_end_nominal_p90": q(end_balance_t, 90),
        }

        needed_at_start = max(
            0.0,
            DrawdownEngine._nominal_amount_today(cfg.replacement_income_today, start_year, inflation_rate)
            - float(income_by_year.get(start_year, 0.0)),
        ) / max(cfg.safe_withdrawal_rate, 1e-9)
        coast_fire_now = needed_at_start / max((1.0 + cfg.coast_growth_rate) ** start_year, 1e-9)

        shortfall_probs = np.mean(shortfall_t > eps, axis=0)
        worst_idx = int(np.argmax(shortfall_probs)) if shortfall_probs.size > 0 else None
        worst_shortfall_year = int(years[worst_idx]) if worst_idx is not None else None
        worst_shortfall_probability = float(shortfall_probs[worst_idx]) if worst_idx is not None else None

        return {
            "success_probability": success_prob,
            "failure_probability": 1.0 - success_prob,
            "median_depletion_year": med_dep,
            "median_first_shortfall_year": med_dep,
            "depletion_probability_by_end_year": dep_prob,
            "average_year_balance_hits_zero": avg_year_balance_hits_zero,
            "required_portfolio_at_start_year_nominal": float(needed_at_start),
            "coast_fire_number_today": float(coast_fire_now),
            "worst_shortfall_year": worst_shortfall_year,
            "worst_shortfall_probability": worst_shortfall_probability,
            "yearly": yearly,
        }

    @staticmethod
    def _probabilistic_coast_fire(
        plan_paths: np.ndarray,
        config: DrawdownConfig,
        inflation_rate: float,
        target_success: float,
        max_iter: int = 30,
    ) -> Optional[float]:
        """Binary search for minimum P0 today such that success_prob >= target_success when
        scaling paths to start with P0 at year 0. Returns None if no such P0 found."""
        n_paths, n_years = plan_paths.shape
        start_year = int(config.start_year)
        if start_year >= n_years:
            return None
        p0_at_0 = np.maximum(plan_paths[:, 0], 1e-9)

        def success_prob_for_p0(p0: float) -> float:
            if p0 <= 0.0:
                return 0.0
            # Synthetic paths: value at t = p0 * (path[i,t] / path[i,0])
            scale = p0 / p0_at_0
            syn = plan_paths * scale[:, np.newaxis]
            result = DrawdownEngine._simulate_drawdown_for_start_year(
                syn, config, inflation_rate, start_year
            )
            return float(result.get("success_probability", 0.0))

        # Upper bound: use 2x max start-year value as initial wealth so we're likely to succeed
        high = float(np.max(plan_paths[:, start_year]) * 2.0) + 1e6
        if success_prob_for_p0(high) < target_success:
            return None
        low = 0.0
        for _ in range(max_iter):
            mid = (low + high) * 0.5
            if mid <= 0.0:
                return None
            sp = success_prob_for_p0(mid)
            if sp >= target_success:
                high = mid
            else:
                low = mid
            if (high - low) < 1.0:  # within $1
                break
        return float(high)

    @staticmethod
    def _simulate_drawdown_vectorized_w(
        paths: np.ndarray,
        start_year: int,
        end_year: int,
        w_per_path: np.ndarray,
        income_by_year: Dict[int, float],
        inflation_rate: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Vectorized drawdown with per-path constant real spending w_per_path (shape n_paths).
        Returns (has_shortfall: (n_paths,), end_balance: (n_paths,))."""
        n_paths, n_years_total = paths.shape
        years = list(range(start_year, end_year + 1))
        eps = 1e-9
        # w_per_path is (n_paths,); nominal spending per path per year: (n_paths, n_years)
        # spend_nom[i, j] = w_per_path[i] * (1+inf)^years[j]
        inflation_factors = np.array(
            [(1.0 + inflation_rate) ** y for y in years],
            dtype=float,
        )
        spend_nom = w_per_path[:, np.newaxis] * inflation_factors[np.newaxis, :]
        income_arr = np.array(
            [float(income_by_year.get(y, 0.0)) for y in years],
            dtype=float,
        )
        net_needed = np.maximum(0.0, spend_nom - income_arr[np.newaxis, :])
        balance = np.array(paths[:, start_year], dtype=float)
        any_shortfall = np.zeros(n_paths, dtype=bool)
        for i, y in enumerate(years):
            withdraw = np.minimum(balance, net_needed[:, i])
            short = np.maximum(0.0, net_needed[:, i] - withdraw)
            any_shortfall = any_shortfall | (short > eps)
            after = balance - withdraw
            if y < end_year:
                denom = np.maximum(paths[:, y], eps)
                growth = np.clip(paths[:, y + 1] / denom, 0.0, 10.0)
                balance = after * growth
            else:
                balance = after
        end_balance = np.maximum(0.0, balance)
        return any_shortfall, end_balance

    @staticmethod
    def sustainable_withdrawal_to_target(
        paths: np.ndarray,
        config: DrawdownConfig,
        inflation_rate: float,
        target_terminal_fraction: float = 0.0,
        max_iter: int = 30,
    ) -> Dict[str, Any]:
        """For each path, compute the constant real withdrawal (today's $) that achieves
        the target terminal balance (e.g. 0 = exhaust by end). Vectorized over all paths."""
        n_paths, n_years_total = paths.shape
        start_year = int(config.start_year)
        end_year = min(int(config.end_year), n_years_total - 1)
        if start_year > end_year:
            return {
                "sustainable_withdrawal_p10": None,
                "sustainable_withdrawal_p25": None,
                "sustainable_withdrawal_median": None,
                "sustainable_withdrawal_p75": None,
                "sustainable_withdrawal_p90": None,
                "sustainable_withdrawal_per_path": [],
                "target_terminal_fraction": target_terminal_fraction,
            }
        years = list(range(start_year, end_year + 1))
        income_by_year = DrawdownEngine._build_income_nominal_by_year(
            years, config.income_sources or [], inflation_rate
        )
        p0 = np.array(paths[:, start_year], dtype=float)
        valid = p0 > 0
        w_low = np.zeros(n_paths, dtype=float)
        w_high = np.where(valid, p0 + 1e6, 0.0)
        inflation_factor_end = (1.0 + inflation_rate) ** (end_year - start_year)
        target_nominal = (
            np.where(valid, p0 * target_terminal_fraction * inflation_factor_end, 0.0)
            if target_terminal_fraction > 0
            else None
        )
        for _ in range(max_iter):
            w_mid = np.where(valid, (w_low + w_high) * 0.5, 0.0)
            has_shortfall, end_balance = DrawdownEngine._simulate_drawdown_vectorized_w(
                paths, start_year, end_year, w_mid, income_by_year, inflation_rate
            )
            if target_terminal_fraction <= 0:
                where_shortfall = valid & has_shortfall
                where_ok = valid & (~has_shortfall)
                w_high = np.where(where_shortfall, w_mid, w_high)
                w_low = np.where(where_ok, w_mid, w_low)
            else:
                where_shortfall = valid & has_shortfall
                where_above_target = valid & (~has_shortfall) & (end_balance >= target_nominal)
                where_below_target = valid & (~has_shortfall) & (end_balance < target_nominal)
                w_high = np.where(where_shortfall | where_below_target, w_mid, w_high)
                w_low = np.where(where_above_target, w_mid, w_low)
            gap = np.where(valid, w_high - w_low, 0.0)
            if np.all(gap[valid] < 1.0):
                break
        w_per_path = np.where(valid, (w_low + w_high) * 0.5, 0.0)
        return {
            "sustainable_withdrawal_p10": float(np.percentile(w_per_path[valid], 10)) if np.any(valid) else None,
            "sustainable_withdrawal_p25": float(np.percentile(w_per_path[valid], 25)) if np.any(valid) else None,
            "sustainable_withdrawal_median": float(np.median(w_per_path[valid])) if np.any(valid) else None,
            "sustainable_withdrawal_p75": float(np.percentile(w_per_path[valid], 75)) if np.any(valid) else None,
            "sustainable_withdrawal_p90": float(np.percentile(w_per_path[valid], 90)) if np.any(valid) else None,
            "sustainable_withdrawal_per_path": w_per_path.tolist(),
            "target_terminal_fraction": target_terminal_fraction,
        }

    @staticmethod
    def analyze_plan_paths(
        plan_paths: np.ndarray,
        config: DrawdownConfig,
        inflation_rate: float,
    ) -> Dict[str, Any]:
        if not config.enabled:
            return {"enabled": False}

        base = DrawdownEngine._simulate_drawdown_for_start_year(
            plan_paths, config, inflation_rate, config.start_year
        )

        scan = []
        earliest = None
        for y in config.retirement_year_candidates or [config.start_year]:
            result = DrawdownEngine._simulate_drawdown_for_start_year(plan_paths, config, inflation_rate, int(y))
            sp = float(result.get("success_probability", 0.0))
            scan.append({"year": int(y), "success_probability": sp})
            if earliest is None and sp >= config.success_threshold:
                earliest = int(y)

        coast_prob = DrawdownEngine._probabilistic_coast_fire(
            plan_paths, config, inflation_rate, config.success_threshold
        )

        sustainable = DrawdownEngine.sustainable_withdrawal_to_target(
            plan_paths, config, inflation_rate, config.target_terminal_fraction
        )

        portfolio_at_year_0_median = float(np.median(plan_paths[:, 0])) if plan_paths.size > 0 else None

        out = {
            "enabled": True,
            "portfolio_at_year_0_median": portfolio_at_year_0_median,
            "start_year": int(config.start_year),
            "end_year": int(config.end_year),
            "spending_rule": config.spending_rule,
            "inflation_mode_for_spending": config.inflation_mode_for_spending,
            "replacement_income_today": float(config.replacement_income_today),
            "safe_withdrawal_rate": float(config.safe_withdrawal_rate),
            "success_threshold": float(config.success_threshold),
            "earliest_feasible_retirement_year": earliest,
            "retirement_year_scan": scan,
            "coast_fire_now_probabilistic": float(coast_prob) if coast_prob is not None else None,
            "sustainable_withdrawal_p10": sustainable.get("sustainable_withdrawal_p10"),
            "sustainable_withdrawal_p25": sustainable.get("sustainable_withdrawal_p25"),
            "sustainable_withdrawal_median": sustainable.get("sustainable_withdrawal_median"),
            "sustainable_withdrawal_p75": sustainable.get("sustainable_withdrawal_p75"),
            "sustainable_withdrawal_p90": sustainable.get("sustainable_withdrawal_p90"),
            "sustainable_withdrawal_per_path": sustainable.get("sustainable_withdrawal_per_path", []),
            "target_terminal_fraction": sustainable.get("target_terminal_fraction", 0.0),
        }
        out.update(base)
        return out
