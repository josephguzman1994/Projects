(function () {
  'use strict';

  if (typeof Chart !== 'undefined' && typeof window['chartjs-plugin-annotation'] !== 'undefined') {
    Chart.register(window['chartjs-plugin-annotation']);
  }

  const API = '';
  let chartTrajectories = null;
  let chartPlanTrajectories = null;
  let chartMC = null;
  let chartPlanMC = null;
  let chartDrawdownShortfall = null;
  let chartDrawdownBalance = null;
  let chartDrawdownScan = null;
  let chartDrawdownImpact = null;
  let chartBudget = null;
  let chartSustainableWithdrawal = null;
  let lastScenariosData = null;
  let lastMcData = null;
  let lastPlansData = null;
  let lastDrawdownData = null;
  /** Spending sensitivity: { 0.5: drawdownResponse, 0.8: ..., 1.0: ..., 1.2: ..., 1.5: ... } */
  let lastSpendingSensitivity = null;
  let currentInflationRate = 0.03;
  let currentRetirementIncomeRate = 0.045;
  let currentEsTailPct = 0.05;
  const MAX_SCENARIOS = 10;
  const MIN_MC_PATHS = 50;
  const MAX_MC_PATHS = 100000;

  /** Single palette for all charts so the same scenario/plan keeps the same color everywhere. */
  const CHART_COLORS = ['#3b82f6', '#14b8a6', '#22c55e', '#a855f7', '#f97316', '#eab308', '#ec4899', '#6366f1'];

  /** Budget tab: category ids in display order (must match input ids budget_<id>). */
  const BUDGET_CATEGORIES = [
    'housing', 'utilities', 'groceries', 'dining_out', 'transport', 'healthcare', 'insurance',
    'subscriptions', 'shopping', 'travel', 'gifts_donations', 'childcare', 'pet_food', 'pet_insurance',
    'phone', 'gym', 'other'
  ];
  const BUDGET_STORAGE_KEY = 'retirement_budget';
  /** Distinct colors for budget pie (one per category + annual one-offs). */
  const BUDGET_CHART_COLORS = [
    '#3b82f6', '#14b8a6', '#22c55e', '#a855f7', '#f97316', '#eab308', '#ec4899', '#6366f1',
    '#0ea5e9', '#10b981', '#f43f5e', '#8b5cf6', '#e11d48', '#059669', '#d946ef', '#ea580c',
    '#2563eb', '#7c3aed', '#dc2626', '#ca8a04'
  ];

  var SCENARIO_TEMPLATES = {
    keep_property: 'Keep property (appreciation only)',
    sell_invest: 'Sell and invest house proceeds',
    sell_invest_withdrawals: 'Sell and invest + withdrawals',
    inheritance_only: 'Inheritance (projected value)',
    roth: 'Roth IRA growth',
    other_property: 'Property with Mortgage'
  };

  var SCENARIO_TYPES = SCENARIO_TEMPLATES;

  function nextId() { return 's' + Date.now() + '_' + Math.random().toString(36).slice(2, 8); }
  function nextPlanId() { return 'p' + Date.now() + '_' + Math.random().toString(36).slice(2, 8); }

  var scenarioList = [];
  var planList = [];
  var customStockAssets = [];
  var editingScenarioId = null;
  const MAX_CUSTOM_STOCK_ASSETS = 10;

  function $(id) { return document.getElementById(id); }

  function setLoading(visible, msg) {
    const overlay = $('loadingOverlay');
    const content = $('resultsContent');
    const msgEl = $('loadingMsg');
    if (overlay) overlay.classList.toggle('is-visible', !!visible);
    if (content) content.setAttribute('aria-busy', !!visible);
    if (msgEl) msgEl.textContent = msg || 'Updating projections…';
  }

  function showError(msg, dismissible) {
    const banner = $('errorBanner');
    const text = $('errorBannerText');
    if (!banner || !text) return;
    if (!msg) {
      banner.classList.remove('is-visible');
      text.textContent = '';
      return;
    }
    text.textContent = msg;
    banner.classList.add('is-visible');
    if (dismissible !== false) {
      const dismiss = $('errorBannerDismiss');
      if (dismiss) dismiss.onclick = function () { showError(''); };
    }
  }

  function formatCurrency(n) {
    if (n == null || isNaN(n)) return '—';
    if (Math.abs(n) >= 1e6) return '$' + (n / 1e6).toFixed(2) + 'M';
    return '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  }

  function toTodaysDollars(nominal, yearsFromToday, inflationRate) {
    if (nominal == null || isNaN(nominal)) return null;
    var r = Number(inflationRate);
    if (isNaN(r)) r = 0;
    return nominal / Math.pow(1 + r, Number(yearsFromToday) || 0);
  }

  function nominalTodayHtml(nominal, yearsFromToday) {
    var today = toTodaysDollars(nominal, yearsFromToday, currentInflationRate);
    var incomeNominal = (nominal == null || isNaN(nominal)) ? null : Number(nominal) * currentRetirementIncomeRate;
    var incomeToday = (today == null || isNaN(today)) ? null : Number(today) * currentRetirementIncomeRate;
    var ratePct = (currentRetirementIncomeRate * 100).toFixed(1);
    return '<div class="num-main">' + formatCurrency(nominal) + '</div>' +
      '<div class="num-sub">Today$: ' + formatCurrency(today) + '</div>' +
      '<div class="num-sub">Income @' + ratePct + '%: ' + formatCurrency(incomeNominal) + '</div>' +
      '<div class="num-sub">Income Today$: ' + formatCurrency(incomeToday) + '</div>';
  }

  function formatPct(v, digits) {
    if (v == null || isNaN(v)) return '—';
    var d = digits == null ? 1 : digits;
    return (Number(v) * 100).toFixed(d) + '%';
  }

  function renderAssumptionsBanner(globalParams) {
    var el = $('assumptionsBanner');
    if (!el || !globalParams) return;
    var parts = [
      'Inflation ' + formatPct(globalParams.inflation_rate, 1),
      'Stoch infl ' + (globalParams.enable_stochastic_inflation ? 'ON' : 'OFF'),
      'Corr ' + (globalParams.enable_correlation ? (globalParams.correlation_preset || 'balanced') : 'OFF'),
      'Profile ' + (globalParams.stock_profile_preset || 'overall_stock'),
      'Income eq ' + formatPct(globalParams.retirement_income_rate, 1),
      'ES tail ' + formatPct(globalParams.es_tail_pct, 1),
      'MC paths ' + Math.round(globalParams.mc_n_paths || 0),
      'Benchmarks [' + (globalParams.benchmark_years || []).join(', ') + ']'
    ];
    el.innerHTML = '<span class="label">Assumptions:</span><span class="muted">' + parts.join(' \u00b7 ') + '</span>';
  }

  function getScenarioDriverChips(sc, globalParams) {
    var p = Object.assign({}, globalParams || {}, sc.params || {});
    var chips = [];
    var hasHouseRisk = sc.type === 'keep_property' ||
      sc.type === 'sell_invest' ||
      sc.type === 'sell_invest_withdrawals' ||
      sc.type === 'other_property';
    var hasPortfolioRisk = sc.type === 'sell_invest' || sc.type === 'sell_invest_withdrawals' || sc.type === 'roth';
    if (hasPortfolioRisk) {
      var profileAssets = buildStockPresetAssets(
        p.stock_profile_preset || 'overall_stock',
        p,
        normalizeCustomStockAssets(p.custom_stock_assets || [])
      );
      var effMu = profileAssets.reduce(function (acc, a) { return acc + Number(a.weight || 0) * Number(a.mean || 0); }, 0);
      var effVar = profileAssets.reduce(function (acc, a) {
        var w = Number(a.weight || 0);
        var s = Number(a.std || 0);
        return acc + (w * w * s * s);
      }, 0);
      var effSigma = Math.sqrt(Math.max(0, effVar));
      chips.push('\u03bcstock ' + formatPct(effMu, 1));
      chips.push('\u03c3stock ' + formatPct(effSigma, 1));
    } else {
      if (p.stock_return_mean != null) chips.push('\u03bcstock ' + formatPct(p.stock_return_mean, 1));
      if (p.stock_return_std != null) chips.push('\u03c3stock ' + formatPct(p.stock_return_std, 1));
    }
    if (hasHouseRisk && p.house_return_mean != null) chips.push('\u03bchouse ' + formatPct(p.house_return_mean, 1));
    if (hasHouseRisk && p.house_return_std != null) chips.push('\u03c3house ' + formatPct(p.house_return_std, 1));
    if (hasPortfolioRisk && p.stock_profile_preset) chips.push('Profile ' + String(p.stock_profile_preset));
    if (p.use_fat_tails != null) chips.push('Fat-tail ' + (p.use_fat_tails ? 'ON' : 'OFF'));
    if (p.use_fat_tails && p.fat_tail_df != null) chips.push('df ' + Number(p.fat_tail_df).toFixed(1));
    if (p.withdrawal_rate != null && sc.type === 'sell_invest_withdrawals') chips.push('w/d ' + formatPct(p.withdrawal_rate, 2));
    return chips;
  }

  function parseBenchmarkYears(str) {
    if (!str || typeof str !== 'string') return [7, 12, 17, 35];
    return str.split(/[\s,]+/).map(function (s) { return parseInt(s, 10); }).filter(function (n) { return !isNaN(n) && n >= 0 && n <= 120; });
  }

  function collectDrawdownParams(globalParams) {
    var spendingToday = Math.max(0, Number($('drawdown_spending_today')?.value) || 0);
    var replacementIncome = Math.max(0, Number($('drawdown_replacement_income_today')?.value) || spendingToday);
    var startYear = clampNumber(Number($('drawdown_start_year')?.value), 0, 120);
    if (!isFinite(startYear)) startYear = 35;
    var endYear = clampNumber(Number($('drawdown_end_year')?.value), startYear + 1, 120);
    if (!isFinite(endYear)) endYear = Math.max(startYear + 1, 70);
    var incomeSources = [];
    var ssAmount = Math.max(0, Number($('ss_amount_today')?.value) || 0);
    var ssStart = clampNumber(Number($('ss_start_year')?.value), 0, 120);
    if (ssAmount > 0) {
      incomeSources.push({
        id: 'ss',
        name: 'Social Security',
        start_year: isFinite(ssStart) ? ssStart : 36,
        end_year: 120,
        amount_today: ssAmount,
        inflation_linked: true
      });
    }
    return {
      enabled: !!$('drawdown_enabled')?.checked,
      start_year: startYear,
      end_year: endYear,
      spending_today: spendingToday,
      replacement_income_today: replacementIncome,
      spending_rule: 'real_flat',
      success_threshold: clampNumber((Number($('drawdown_success_threshold')?.value) || 90) / 100, 0.5, 0.99),
      safe_withdrawal_rate: clampNumber((Number($('drawdown_safe_withdrawal_rate')?.value) || ((globalParams && globalParams.retirement_income_rate) || 0.045) * 100) / 100, 0.005, 0.15),
      inflation_mode_for_spending: $('drawdown_inflation_mode')?.value || 'flat',
      coast_growth_rate: clampNumber((Number($('drawdown_coast_growth_rate')?.value) || ((globalParams && globalParams.stock_return_mean) || 0.08) * 100) / 100, -0.02, 0.2),
      target_terminal_fraction: clampNumber((Number($('drawdown_target_terminal_fraction')?.value) || 0) / 100, 0, 1),
      income_sources: incomeSources,
      retirement_year_candidates: []
    };
  }

  function normalizeCustomStockAssets(assets) {
    var cleaned = (assets || [])
      .map(function (a, i) {
        return {
          name: String((a && a.name) || ('Asset ' + (i + 1))).slice(0, 60),
          weight: clampNumber(Number(a && a.weight), 0, 1),
          mean: clampNumber(Number(a && a.mean), -0.5, 1.0),
          std: clampNumber(Number(a && a.std), 0, 2.0)
        };
      })
      .filter(function (a) { return isFinite(a.weight) && isFinite(a.mean) && isFinite(a.std); })
      .slice(0, MAX_CUSTOM_STOCK_ASSETS);
    if (!cleaned.length) return [];
    var sumW = cleaned.reduce(function (acc, a) { return acc + a.weight; }, 0);
    if (!isFinite(sumW) || sumW <= 0) {
      var eq = 1 / cleaned.length;
      cleaned.forEach(function (a) { a.weight = eq; });
      return cleaned;
    }
    cleaned.forEach(function (a) { a.weight = a.weight / sumW; });
    return cleaned;
  }

  function buildStockPresetAssets(preset, context, existingCustom) {
    var p = String(preset || 'overall_stock').toLowerCase();
    var stockMean = clampNumber(Number(context && context.stock_return_mean), -0.5, 1.0);
    var stockStd = clampNumber(Number(context && context.stock_return_std), 0, 2.0);
    var bondMean = clampNumber(Number(context && context.bond_return_mean), -0.5, 1.0);
    var bondStd = clampNumber(Number(context && context.bond_return_std), 0, 2.0);
    if (!isFinite(stockMean)) stockMean = 0.08;
    if (!isFinite(stockStd)) stockStd = 0.17;
    if (!isFinite(bondMean)) bondMean = 0.045;
    if (!isFinite(bondStd)) bondStd = 0.08;
    if (p === 'bond_profile') {
      return normalizeCustomStockAssets([{ name: 'Bond sleeve', weight: 1.0, mean: bondMean, std: bondStd }]);
    }
    if (p === 'three_fund') {
      return normalizeCustomStockAssets([
        { name: 'US Equity', weight: 0.55, mean: stockMean, std: stockStd },
        { name: 'Intl Equity', weight: 0.25, mean: stockMean - 0.005, std: stockStd * 1.05 },
        { name: 'US Bonds', weight: 0.20, mean: bondMean, std: bondStd }
      ]);
    }
    if (p === 'custom_profile') {
      if (existingCustom && existingCustom.length) return normalizeCustomStockAssets(existingCustom);
      return normalizeCustomStockAssets([{ name: 'Asset 1', weight: 1.0, mean: stockMean, std: stockStd }]);
    }
    return normalizeCustomStockAssets([{ name: 'Overall stock', weight: 1.0, mean: stockMean, std: stockStd }]);
  }

  function getGlobalStockContext() {
    return {
      stock_return_mean: Number($('stock_return_mean')?.value) / 100,
      stock_return_std: Number($('stock_return_std')?.value) / 100,
      bond_return_mean: Number($('bond_return_mean')?.value) / 100,
      bond_return_std: Number($('bond_return_std')?.value) / 100
    };
  }

  function applyGlobalStockProfileDefaults() {
    var preset = $('stock_profile_preset') ? $('stock_profile_preset').value : 'overall_stock';
    customStockAssets = buildStockPresetAssets(preset, getGlobalStockContext(), customStockAssets);
  }

  function renderCustomStockAssets() {
    var wrap = $('customStockProfileWrap');
    var rows = $('customStockAssetRows');
    var preset = $('stock_profile_preset') ? $('stock_profile_preset').value : 'overall_stock';
    if (wrap) wrap.style.display = 'block';
    if (!rows) return;
    rows.innerHTML = '';
    var editable = preset === 'custom_profile';
    var addBtn = $('btnAddCustomStockAsset');
    if (addBtn) addBtn.style.display = editable ? 'inline-block' : 'none';
    customStockAssets.forEach(function (a, idx) {
      var row = document.createElement('div');
      row.className = 'slider-row';
      row.style.gap = '8px';

      var name = document.createElement('input');
      name.type = 'text';
      name.placeholder = 'Asset name';
      name.value = a.name || ('Asset ' + (idx + 1));
      name.style.flex = '2';
      name.disabled = !editable;
      name.addEventListener('change', function () {
        a.name = name.value.trim() || ('Asset ' + (idx + 1));
      });

      var weight = document.createElement('input');
      weight.type = 'number';
      weight.min = '0';
      weight.max = '100';
      weight.step = '0.1';
      weight.title = 'Weight %';
      weight.value = ((a.weight || 0) * 100).toFixed(1);
      weight.style.width = '90px';
      weight.disabled = !editable;
      weight.addEventListener('change', function () {
        a.weight = clampNumber(Number(weight.value) / 100, 0, 1);
      });

      var mean = document.createElement('input');
      mean.type = 'number';
      mean.min = '-50';
      mean.max = '100';
      mean.step = '0.1';
      mean.title = 'Mean %';
      mean.value = ((a.mean || 0) * 100).toFixed(1);
      mean.style.width = '90px';
      mean.disabled = !editable;
      mean.addEventListener('change', function () {
        a.mean = clampNumber(Number(mean.value) / 100, -0.5, 1.0);
      });

      var std = document.createElement('input');
      std.type = 'number';
      std.min = '0';
      std.max = '200';
      std.step = '0.1';
      std.title = 'Std %';
      std.value = ((a.std || 0) * 100).toFixed(1);
      std.style.width = '90px';
      std.disabled = !editable;
      std.addEventListener('change', function () {
        a.std = clampNumber(Number(std.value) / 100, 0, 2.0);
      });

      var remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn btn-secondary btn-icon';
      remove.textContent = 'Remove';
      remove.disabled = !editable;
      remove.addEventListener('click', function () {
        customStockAssets.splice(idx, 1);
        renderCustomStockAssets();
      });

      row.appendChild(name);
      row.appendChild(weight);
      row.appendChild(mean);
      row.appendChild(std);
      row.appendChild(remove);
      rows.appendChild(row);
    });
  }

  function addCustomStockAsset() {
    if (customStockAssets.length >= MAX_CUSTOM_STOCK_ASSETS) {
      showError('Custom profile supports up to ' + MAX_CUSTOM_STOCK_ASSETS + ' assets.');
      return;
    }
    customStockAssets.push({
      name: 'Asset ' + (customStockAssets.length + 1),
      weight: customStockAssets.length ? 0.1 : 1.0,
      mean: 0.07,
      std: 0.15
    });
    customStockAssets = normalizeCustomStockAssets(customStockAssets);
    renderCustomStockAssets();
  }

  function collectParams() {
    const pctCash = Number($('pct_cash_reserve').value) / 100;
    const nBenef = Number($('inheritance_beneficiary_n').value) || 3;
    const benchmarkInput = $('benchmark_years');
    let benchmarkYears = benchmarkInput ? parseBenchmarkYears(benchmarkInput.value) : [7, 12, 17, 35];
    const drawdownEnd = Number($('drawdown_end_year')?.value);
    if (isFinite(drawdownEnd) && drawdownEnd >= 0 && benchmarkYears.indexOf(drawdownEnd) === -1) {
      benchmarkYears = benchmarkYears.slice();
      benchmarkYears.push(drawdownEnd);
      benchmarkYears.sort(function (a, b) { return a - b; });
    }
    return {
      home_value_today: Number($('home_value_today').value),
      years_live_in_before_sale: Number($('years_live_in_before_sale').value),
      home_appreciation_rate: Number($('home_appreciation_rate')?.value) / 100 || 0.01,
      selling_costs_pct: Number($('selling_costs_pct').value) / 100,
      pct_cash_reserve: pctCash,
      pct_invest: 1 - pctCash,
      mc_n_paths: Math.max(MIN_MC_PATHS, Math.min(MAX_MC_PATHS, Number($('mc_n_paths').value) || 10000)),
      use_fat_tails: false,
      fat_tail_df: 5,
      stock_return_mean: Number($('stock_return_mean').value) / 100,
      stock_return_std: Number($('stock_return_std').value) / 100,
      stock_profile_preset: $('stock_profile_preset')?.value || 'overall_stock',
      custom_stock_assets: normalizeCustomStockAssets(customStockAssets),
      house_return_mean: Number($('house_return_mean').value) / 100,
      house_return_std: Number($('house_return_std').value) / 100,
      withdrawal_start_year: Number($('withdrawal_start_year').value),
      withdrawal_rate: Number($('withdrawal_rate').value) / 100,
      include_scenario_4: $('include_scenario_4').checked,
      inheritance_portfolio_today: Number($('inheritance_portfolio_today').value),
      inheritance_growth_rate: Number($('inheritance_growth_rate').value) / 100,
      inheritance_return_mean: Number($('inheritance_return_mean').value) / 100,
      inheritance_return_std: Number($('inheritance_return_std').value) / 100,
      inheritance_years_until_receipt: Number($('inheritance_years_until_receipt').value),
      inheritance_beneficiary_share: 1 / nBenef,
      benchmark_years: benchmarkYears.length ? benchmarkYears : [7, 12, 17, 35],
      inflation_rate: Number($('inflation_rate')?.value) / 100 || 0.03,
      enable_stochastic_inflation: !!$('enable_stochastic_inflation')?.checked,
      inflation_return_mean: Number($('inflation_return_mean')?.value) / 100 || 0.03,
      inflation_return_std: Number($('inflation_return_std')?.value) / 100 || 0.015,
      enable_correlation: !!$('enable_correlation')?.checked,
      correlation_preset: $('correlation_preset')?.value || 'balanced',
      bond_return_mean: Number($('bond_return_mean')?.value) / 100 || 0.045,
      bond_return_std: Number($('bond_return_std')?.value) / 100 || 0.08,
      retirement_income_rate: Number($('retirement_income_rate')?.value) / 100 || 0.045,
      es_tail_pct: Number($('es_tail_pct')?.value) / 100 || 0.05,
      roth_balance_today: Number($('roth_balance_today').value),
      roth_annual_contribution: Number($('roth_annual_contribution').value),
      roth_contribution_years: Number($('roth_contribution_years').value),
      investment_return_rate: Number($('investment_return_rate').value) / 100,
      other_house_value_today: Number($('other_house_value_today').value),
      other_house_mortgage_remaining: Number($('other_house_mortgage_remaining').value),
      other_house_mortgage_payoff_years: Number($('other_house_mortgage_payoff_years').value),
      other_house_appreciation_rate: Number($('other_house_appreciation_rate')?.value) / 100 || 0.01
    };
  }

  var PARAM_FIELDS = {
    keep_property: [
      { key: 'home_value_today', label: 'Property value today ($)', type: 'number', min: 0, step: 1000 },
      { key: 'years_live_in_before_sale', label: 'Years in property before sale', type: 'number', min: 1, max: 30 },
      { key: 'home_appreciation_rate', label: 'House appreciation (deterministic) (%)', type: 'percent', min: -2, max: 10 },
      { key: 'house_return_mean', label: 'House return mean (%)', type: 'percent', min: -2, max: 10 },
      { key: 'house_return_std', label: 'House return std (%)', type: 'percent', min: 0, max: 25 },
      { key: 'use_fat_tails', label: 'Use fat-tail returns', type: 'boolean' },
      { key: 'fat_tail_df', label: 'Tail heaviness (df)', type: 'number', min: 2.1, max: 30, step: 0.5 }
    ],
    sell_invest: [
      { key: 'home_value_today', label: 'Property value today ($)', type: 'number', min: 0, step: 1000 },
      { key: 'years_live_in_before_sale', label: 'Years before sale', type: 'number', min: 1, max: 30 },
      { key: 'pct_cash_reserve', label: 'Cash reserve (%)', type: 'percent', min: 0, max: 100 },
      { key: 'selling_costs_pct', label: 'Selling costs (%)', type: 'percent', min: 0, max: 20 },
      { key: 'investment_return_rate', label: 'Investment return (%)', type: 'percent', min: 0, max: 20 },
      { key: 'cash_reserve_return_rate', label: 'Cash reserve return (%)', type: 'percent', min: 0, max: 10 },
      { key: 'house_return_mean', label: 'House return mean (%)', type: 'percent', min: -2, max: 10 },
      { key: 'house_return_std', label: 'House return std (%)', type: 'percent', min: 0, max: 25 },
      { key: 'stock_return_mean', label: 'Stock return mean (%)', type: 'percent', min: 0, max: 15 },
      { key: 'stock_return_std', label: 'Stock return std (%)', type: 'percent', min: 5, max: 40 },
      {
        key: 'stock_profile_preset',
        label: 'Portfolio distribution profile',
        type: 'select',
        options: [
          { value: 'overall_stock', label: 'Overall stock profile (current default)' },
          { value: 'bond_profile', label: 'Typical bond profile' },
          { value: 'three_fund', label: 'Typical 3-fund profile' },
          { value: 'custom_profile', label: 'Custom profile (up to 10 assets)' }
        ]
      },
      { key: 'custom_stock_assets', label: 'Custom portfolio assets JSON', type: 'json', rows: 6 },
      { key: 'use_fat_tails', label: 'Use fat-tail returns', type: 'boolean' },
      { key: 'fat_tail_df', label: 'Tail heaviness (df)', type: 'number', min: 2.1, max: 30, step: 0.5 }
    ],
    sell_invest_withdrawals: [
      { key: 'home_value_today', label: 'Property value today ($)', type: 'number', min: 0, step: 1000 },
      { key: 'years_live_in_before_sale', label: 'Years before sale', type: 'number', min: 1, max: 30 },
      { key: 'pct_cash_reserve', label: 'Cash reserve (%)', type: 'percent', min: 0, max: 100 },
      { key: 'selling_costs_pct', label: 'Selling costs (%)', type: 'percent', min: 0, max: 20 },
      { key: 'investment_return_rate', label: 'Investment return (%)', type: 'percent', min: 0, max: 20 },
      { key: 'cash_reserve_return_rate', label: 'Cash reserve return (%)', type: 'percent', min: 0, max: 10 },
      { key: 'withdrawal_start_year', label: 'Withdrawal start year', type: 'number', min: 1, max: 40 },
      { key: 'withdrawal_rate', label: 'Withdrawal rate (%)', type: 'percent', min: 0, max: 10 },
      { key: 'house_return_mean', label: 'House return mean (%)', type: 'percent', min: -2, max: 10 },
      { key: 'house_return_std', label: 'House return std (%)', type: 'percent', min: 0, max: 25 },
      { key: 'stock_return_mean', label: 'Stock return mean (%)', type: 'percent', min: 0, max: 15 },
      { key: 'stock_return_std', label: 'Stock return std (%)', type: 'percent', min: 5, max: 40 },
      {
        key: 'stock_profile_preset',
        label: 'Portfolio distribution profile',
        type: 'select',
        options: [
          { value: 'overall_stock', label: 'Overall stock profile (current default)' },
          { value: 'bond_profile', label: 'Typical bond profile' },
          { value: 'three_fund', label: 'Typical 3-fund profile' },
          { value: 'custom_profile', label: 'Custom profile (up to 10 assets)' }
        ]
      },
      { key: 'custom_stock_assets', label: 'Custom portfolio assets JSON', type: 'json', rows: 6 },
      { key: 'use_fat_tails', label: 'Use fat-tail returns', type: 'boolean' },
      { key: 'fat_tail_df', label: 'Tail heaviness (df)', type: 'number', min: 2.1, max: 30, step: 0.5 }
    ],
    inheritance_only: [
      { key: 'inheritance_portfolio_today', label: 'Estate portfolio value today ($)', type: 'number', min: 0, step: 100000 },
      { key: 'inheritance_years_until_receipt', label: 'Years until receipt', type: 'number', min: 1, max: 50 },
      { key: 'inheritance_beneficiary_share', label: 'Your share (1/n, e.g. 0.333 for 1/3)', type: 'number', min: 0.01, max: 1, step: 0.01 },
      { key: 'inheritance_growth_rate', label: 'Estate growth until receipt (%)', type: 'percent', min: 0, max: 15 },
      { key: 'inheritance_return_mean', label: 'Inheritance MC return mean (%)', type: 'percent', min: 0, max: 12 },
      { key: 'inheritance_return_std', label: 'Inheritance MC return std (%)', type: 'percent', min: 0, max: 30 },
      { key: 'use_fat_tails', label: 'Use fat-tail returns', type: 'boolean' },
      { key: 'fat_tail_df', label: 'Tail heaviness (df)', type: 'number', min: 2.1, max: 30, step: 0.5 }
    ],
    roth: [
      { key: 'roth_balance_today', label: 'Roth balance today ($)', type: 'number', min: 0, step: 500 },
      { key: 'roth_annual_contribution', label: 'Annual contribution ($)', type: 'number', min: 0, step: 500 },
      { key: 'roth_contribution_years', label: 'Years of contributions', type: 'number', min: 0, max: 50 },
      { key: 'investment_return_rate', label: 'Investment return (%)', type: 'percent', min: 0, max: 20 },
      { key: 'stock_return_mean', label: 'Stock return mean (%)', type: 'percent', min: 0, max: 15 },
      { key: 'stock_return_std', label: 'Stock return std (%)', type: 'percent', min: 5, max: 40 },
      {
        key: 'stock_profile_preset',
        label: 'Portfolio distribution profile',
        type: 'select',
        options: [
          { value: 'overall_stock', label: 'Overall stock profile (current default)' },
          { value: 'bond_profile', label: 'Typical bond profile' },
          { value: 'three_fund', label: 'Typical 3-fund profile' },
          { value: 'custom_profile', label: 'Custom profile (up to 10 assets)' }
        ]
      },
      { key: 'custom_stock_assets', label: 'Custom portfolio assets JSON', type: 'json', rows: 6 },
      { key: 'use_fat_tails', label: 'Use fat-tail returns', type: 'boolean' },
      { key: 'fat_tail_df', label: 'Tail heaviness (df)', type: 'number', min: 2.1, max: 30, step: 0.5 }
    ],
    other_property: [
      { key: 'other_house_value_today', label: 'Property value today ($)', type: 'number', min: 0, step: 1000 },
      { key: 'other_house_mortgage_remaining', label: 'Mortgage remaining ($)', type: 'number', min: 0, step: 1000 },
      { key: 'other_house_mortgage_payoff_years', label: 'Years to pay off mortgage', type: 'number', min: 0.5, max: 40, step: 0.5 },
      { key: 'other_house_appreciation_rate', label: 'Appreciation rate (deterministic) (%)', type: 'percent', min: -2, max: 10 },
      { key: 'house_return_mean', label: 'House return mean (%)', type: 'percent', min: -2, max: 10 },
      { key: 'house_return_std', label: 'House return std (%)', type: 'percent', min: 0, max: 25 },
      { key: 'use_fat_tails', label: 'Use fat-tail returns', type: 'boolean' },
      { key: 'fat_tail_df', label: 'Tail heaviness (df)', type: 'number', min: 2.1, max: 30, step: 0.5 }
    ]
  };

  function clampNumber(val, min, max) {
    if (val == null || isNaN(val)) return val;
    var out = Number(val);
    if (min != null && out < min) out = min;
    if (max != null && out > max) out = max;
    return out;
  }

  function normalizeScenarioParams(sc) {
    if (!sc || !sc.type) return { changed: false, messages: [] };
    var fields = PARAM_FIELDS[sc.type] || [];
    sc.params = sc.params || {};
    var changed = false;
    var messages = [];
    fields.forEach(function (f) {
      var key = f.key;
      if (sc.params[key] === undefined || sc.params[key] === null) return;
      if (f.type === 'boolean') {
        var b = !!sc.params[key];
        if (sc.params[key] !== b) {
          sc.params[key] = b;
          changed = true;
        }
        return;
      }
      if (f.type === 'select') return;
      if (f.type === 'json') {
        if (key === 'custom_stock_assets') {
          var normalizedAssets = normalizeCustomStockAssets(sc.params[key]);
          if (JSON.stringify(normalizedAssets) !== JSON.stringify(sc.params[key])) {
            sc.params[key] = normalizedAssets;
            changed = true;
            messages.push((f.label || key) + ' normalized to valid assets (max ' + MAX_CUSTOM_STOCK_ASSETS + ').');
          }
        }
        return;
      }
      var raw = Number(sc.params[key]);
      if (isNaN(raw)) return;
      var min = f.min;
      var max = f.max;
      if (f.type === 'percent') {
        if (min != null) min = min / 100;
        if (max != null) max = max / 100;
      }
      var clamped = clampNumber(raw, min, max);
      if (clamped !== raw) {
        sc.params[key] = clamped;
        changed = true;
        messages.push((f.label || key) + ' clamped to ' + (f.type === 'percent' ? (clamped * 100).toFixed(2) + '%' : clamped));
      }
    });
    return { changed: changed, messages: messages };
  }

  function getDefaultParamsForType(type) {
    var global = collectParams();
    var keys = (PARAM_FIELDS[type] || []).map(function (f) { return f.key; });
    var out = {};
    keys.forEach(function (k) {
      var v = global[k];
      if (v !== undefined && v !== null && (typeof v !== 'number' || !isNaN(v))) out[k] = v;
    });
    if (type === 'sell_invest' || type === 'sell_invest_withdrawals') {
      if (out.pct_cash_reserve !== undefined) out.pct_invest = 1 - out.pct_cash_reserve;
    }
    return out;
  }

  function bindSliders() {
    const pairs = [
      ['selling_costs_pct', 1, '%'],
      ['pct_cash_reserve', 1, '%'],
      ['stock_return_mean', 1, '%'],
      ['stock_return_std', 1, '%'],
      ['house_return_mean', 0.25, '%'],
      ['house_return_std', 1, '%'],
      ['withdrawal_rate', 0.25, '%'],
      ['inheritance_growth_rate', 0.25, '%'],
      ['inheritance_return_mean', 0.5, '%'],
      ['inheritance_return_std', 1, '%'],
      ['investment_return_rate', 0.25, '%'],
      ['inflation_return_mean', 0.1, '%'],
      ['inflation_return_std', 0.1, '%'],
      ['bond_return_mean', 0.1, '%'],
      ['bond_return_std', 0.1, '%']
    ];
    pairs.forEach(function (item) {
      var id = item[0], step = item[1], suffix = item[2];
      var slider = $(id);
      var valEl = $(id + '_val');
      if (!slider || !valEl) return;
      function update() {
        var v = Number(slider.value);
        valEl.textContent = (step >= 1 ? Math.round(v) : v) + suffix;
      }
      slider.addEventListener('input', update);
      update();
    });
  }

  var CORRELATION_PRESET_EXPLANATIONS = {
    balanced: 'Balanced baseline: modest stock-house linkage, mild stock-bond diversification, and moderate inflation sensitivity.',
    inflation_stress: 'Inflation stress: stronger inflation co-movement with assets and deeper stock-bond divergence during inflation shocks.',
    growth_boom: 'Growth boom: stronger stock-house co-movement with comparatively lower inflation linkage.'
  };

  function updateCorrelationPresetTooltip() {
    var presetEl = $('correlation_preset');
    if (!presetEl) return;
    var key = String(presetEl.value || 'balanced').toLowerCase();
    var desc = CORRELATION_PRESET_EXPLANATIONS[key] || CORRELATION_PRESET_EXPLANATIONS.balanced;
    presetEl.title = desc;
    presetEl.setAttribute('aria-label', 'Correlation preset. ' + desc);
  }

  function renderScenarioList() {
    var emptyEl = $('scenarioListEmpty');
    var container = $('scenarioListCards');
    if (!container) return;
    var globalParams = collectParams();
    if (emptyEl) emptyEl.style.display = scenarioList.length ? 'none' : 'block';
    container.innerHTML = '';
    scenarioList.forEach(function (sc, idx) {
      normalizeScenarioParams(sc);
      var card = document.createElement('div');
      card.className = 'scenario-card';
      card.setAttribute('data-id', sc.id);
      var nameInput = document.createElement('input');
      nameInput.type = 'text';
      nameInput.className = 'name-input';
      nameInput.value = sc.name;
      nameInput.placeholder = 'Scenario name';
      nameInput.addEventListener('change', function () {
        sc.name = nameInput.value.trim() || SCENARIO_TEMPLATES[sc.type] || sc.type;
        renderPlanList();
      });
      var badge = document.createElement('span');
      badge.className = 'type-badge';
      badge.textContent = SCENARIO_TEMPLATES[sc.type] || sc.type;
      var editBtn = document.createElement('button');
      editBtn.type = 'button';
      editBtn.className = 'btn btn-secondary btn-icon';
      editBtn.textContent = 'Edit';
      editBtn.addEventListener('click', function () { openEditModal(sc); });
      var dupBtn = document.createElement('button');
      dupBtn.type = 'button';
      dupBtn.className = 'btn btn-secondary btn-icon';
      dupBtn.textContent = 'Duplicate';
      dupBtn.addEventListener('click', function () {
        if (scenarioList.length >= MAX_SCENARIOS) {
          showError('Maximum scenarios reached (' + MAX_SCENARIOS + '). Remove one to duplicate.');
          return;
        }
        scenarioList.splice(idx + 1, 0, { id: nextId(), name: sc.name + ' (copy)', type: sc.type, params: JSON.parse(JSON.stringify(sc.params || {})) });
        renderScenarioList();
        renderPlanList();
      });
      var remBtn = document.createElement('button');
      remBtn.type = 'button';
      remBtn.className = 'btn btn-secondary btn-icon';
      remBtn.textContent = 'Remove';
      remBtn.addEventListener('click', function () {
        scenarioList.splice(idx, 1);
        renderScenarioList();
        renderPlanList();
      });
      var chipsWrap = document.createElement('div');
      chipsWrap.className = 'driver-chips';
      getScenarioDriverChips(sc, globalParams).forEach(function (text) {
        var chip = document.createElement('span');
        chip.className = 'driver-chip';
        chip.textContent = text;
        chipsWrap.appendChild(chip);
      });
      card.appendChild(nameInput);
      card.appendChild(badge);
      card.appendChild(chipsWrap);
      card.appendChild(editBtn);
      card.appendChild(dupBtn);
      card.appendChild(remBtn);
      container.appendChild(card);
    });
  }

  function openAddMenu() {
    var menu = $('addScenarioMenu');
    if (menu) {
      menu.classList.add('is-open');
      menu.setAttribute('aria-hidden', 'false');
    }
  }

  function closeAddMenu() {
    var menu = $('addScenarioMenu');
    if (menu) {
      menu.classList.remove('is-open');
      menu.setAttribute('aria-hidden', 'true');
    }
  }

  function addScenarioFromTemplate(type) {
    if (scenarioList.length >= MAX_SCENARIOS) {
      showError('Maximum scenarios reached (' + MAX_SCENARIOS + '). Remove one to add another.');
      return;
    }
    var name = SCENARIO_TEMPLATES[type] || type;
    var params = getDefaultParamsForType(type);
    var sc = { id: nextId(), name: name, type: type, params: params };
    scenarioList.push(sc);
    closeAddMenu();
    renderScenarioList();
    renderPlanList();
    openEditModal(sc);
  }

  function openEditModal(scenario) {
    editingScenarioId = scenario.id;
    var modal = $('editScenarioModal');
    var title = $('editScenarioModalTitle');
    var formEl = $('editScenarioForm');
    if (!modal || !formEl) return;
    if (title) title.textContent = 'Edit scenario: ' + (scenario.name || scenario.type);
    var fields = PARAM_FIELDS[scenario.type] || [];
    var global = collectParams();
    normalizeScenarioParams(scenario);
    formEl.innerHTML = '';
    fields.forEach(function (f) {
      var val = scenario.params && scenario.params[f.key] !== undefined ? scenario.params[f.key] : global[f.key];
      if (f.type === 'percent' && typeof val === 'number' && Math.abs(val) <= 1 && val !== 0) val = val * 100;
      var div = document.createElement('div');
      div.className = f.type === 'boolean' ? 'form-group checkbox-row' : 'form-group';
      var label = document.createElement('label');
      label.textContent = f.label;
      label.setAttribute('for', 'edit_' + f.key);
      if (f.type === 'boolean') {
        var inputBool = document.createElement('input');
        inputBool.id = 'edit_' + f.key;
        inputBool.type = 'checkbox';
        inputBool.setAttribute('data-key', f.key);
        inputBool.setAttribute('data-type', f.type || 'number');
        inputBool.checked = !!val;
        div.appendChild(inputBool);
        div.appendChild(label);
      } else if (f.type === 'select') {
        var select = document.createElement('select');
        select.id = 'edit_' + f.key;
        select.setAttribute('data-key', f.key);
        select.setAttribute('data-type', f.type || 'select');
        (f.options || []).forEach(function (opt) {
          var option = document.createElement('option');
          option.value = opt.value;
          option.textContent = opt.label;
          select.appendChild(option);
        });
        select.value = val == null ? ((f.options && f.options[0] && f.options[0].value) || '') : String(val);
        div.appendChild(label);
        div.appendChild(select);
      } else if (f.type === 'json') {
        var ta = document.createElement('textarea');
        ta.id = 'edit_' + f.key;
        ta.setAttribute('data-key', f.key);
        ta.setAttribute('data-type', f.type || 'json');
        ta.rows = f.rows || 6;
        ta.placeholder = '[{"name":"US Equity","weight":0.6,"mean":0.08,"std":0.17}]';
        ta.value = JSON.stringify(Array.isArray(val) ? val : [], null, 2);
        div.appendChild(label);
        div.appendChild(ta);
        var hint = document.createElement('span');
        hint.className = 'hint';
        hint.textContent = 'List of up to 10 assets: [{name, weight, mean, std}] with decimals (e.g. mean 0.08).';
        div.appendChild(hint);
      } else {
        var input = document.createElement('input');
        input.id = 'edit_' + f.key;
        input.type = 'number';
        input.setAttribute('data-key', f.key);
        input.setAttribute('data-type', f.type || 'number');
        if (f.min !== undefined) input.min = f.min;
        if (f.max !== undefined) input.max = f.max;
        if (f.step !== undefined) input.step = f.step;
        input.value = val == null ? '' : val;
        div.appendChild(label);
        div.appendChild(input);
      }
      formEl.appendChild(div);
    });
    var profileSelect = formEl.querySelector('#edit_stock_profile_preset');
    var customAssetsTa = formEl.querySelector('#edit_custom_stock_assets');
    if (profileSelect && customAssetsTa) {
      function getScenarioProfileContextFromForm() {
        function readPct(id, fallback) {
          var el = formEl.querySelector('#' + id);
          if (!el || el.value === '') return fallback;
          var n = Number(el.value);
          if (!isFinite(n)) return fallback;
          return n / 100;
        }
        var merged = Object.assign({}, global || {}, scenario.params || {});
        return {
          stock_return_mean: readPct('edit_stock_return_mean', merged.stock_return_mean),
          stock_return_std: readPct('edit_stock_return_std', merged.stock_return_std),
          bond_return_mean: merged.bond_return_mean,
          bond_return_std: merged.bond_return_std
        };
      }
      function applyScenarioProfileDefaults() {
        var preset = String(profileSelect.value || 'overall_stock');
        var existing = [];
        try {
          existing = JSON.parse(String(customAssetsTa.value || '[]'));
        } catch (e) {
          existing = [];
        }
        var assets = buildStockPresetAssets(preset, getScenarioProfileContextFromForm(), existing);
        customAssetsTa.value = JSON.stringify(assets, null, 2);
      }
      applyScenarioProfileDefaults();
      profileSelect.addEventListener('change', applyScenarioProfileDefaults);
    }
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeEditModal() {
    var modal = $('editScenarioModal');
    if (modal) {
      modal.classList.remove('is-open');
      modal.setAttribute('aria-hidden', 'true');
    }
    editingScenarioId = null;
  }

  function saveEditModal() {
    if (!editingScenarioId) return;
    var sc = scenarioList.filter(function (s) { return s.id === editingScenarioId; })[0];
    if (!sc) return;
    var formEl = $('editScenarioForm');
    if (!formEl) return;
    var inputs = formEl.querySelectorAll('input[data-key], select[data-key], textarea[data-key]');
    sc.params = sc.params || {};
    var hasInvalidJson = false;
    inputs.forEach(function (input) {
      var key = input.getAttribute('data-key');
      var dataType = input.getAttribute('data-type');
      if (dataType === 'boolean') {
        sc.params[key] = !!input.checked;
        return;
      }
      if (dataType === 'select') {
        sc.params[key] = String(input.value || '');
        return;
      }
      if (dataType === 'json') {
        var rawJson = String(input.value || '').trim();
        if (!rawJson) {
          sc.params[key] = [];
          return;
        }
        try {
          var parsed = JSON.parse(rawJson);
          if (key === 'custom_stock_assets') sc.params[key] = normalizeCustomStockAssets(parsed);
          else sc.params[key] = parsed;
        } catch (e) {
          showError('Invalid JSON for ' + key + '. Please fix and save again.');
          hasInvalidJson = true;
        }
        return;
      }
      var val = input.value === '' ? undefined : Number(input.value);
      if (val !== undefined && !isNaN(val)) {
        if (dataType === 'percent') sc.params[key] = val / 100;
        else sc.params[key] = val;
      }
    });
    if (sc.type === 'sell_invest' || sc.type === 'sell_invest_withdrawals') {
      if (sc.params.pct_cash_reserve !== undefined) sc.params.pct_invest = 1 - sc.params.pct_cash_reserve;
    }
    if (hasInvalidJson) return;
    var normalized = normalizeScenarioParams(sc);
    closeEditModal();
    renderScenarioList();
    renderPlanList();
    if (normalized.changed) {
      showError('Some scenario values were outside allowed ranges and were clamped.');
    }
  }

  function sanitizePlans() {
    var validIds = {};
    scenarioList.forEach(function (s) { validIds[s.id] = true; });
    planList = planList.filter(function (p) {
      p.component_ids = (p.component_ids || []).filter(function (id) { return !!validIds[id]; });
      return true;
    });
  }

  function renderPlanList() {
    sanitizePlans();
    var emptyEl = $('planListEmpty');
    var container = $('planListCards');
    if (!container) return;
    if (emptyEl) emptyEl.style.display = planList.length ? 'none' : 'block';
    container.innerHTML = '';
    planList.forEach(function (plan, idx) {
      var card = document.createElement('div');
      card.className = 'plan-card';

      var head = document.createElement('div');
      head.className = 'plan-head';
      var nameInput = document.createElement('input');
      nameInput.type = 'text';
      nameInput.className = 'plan-name-input';
      nameInput.value = plan.name || ('Plan ' + (idx + 1));
      nameInput.addEventListener('change', function () {
        plan.name = nameInput.value.trim() || ('Plan ' + (idx + 1));
      });
      var remBtn = document.createElement('button');
      remBtn.type = 'button';
      remBtn.className = 'btn btn-secondary btn-icon';
      remBtn.textContent = 'Remove';
      remBtn.addEventListener('click', function () {
        planList.splice(idx, 1);
        renderPlanList();
      });
      head.appendChild(nameInput);
      head.appendChild(remBtn);
      card.appendChild(head);

      var components = document.createElement('div');
      components.className = 'plan-components';
      if (!scenarioList.length) {
        var noSc = document.createElement('span');
        noSc.className = 'scenario-list-empty';
        noSc.textContent = 'Add scenarios first';
        components.appendChild(noSc);
      } else {
        scenarioList.forEach(function (sc) {
          var label = document.createElement('label');
          var cb = document.createElement('input');
          cb.type = 'checkbox';
          cb.checked = (plan.component_ids || []).indexOf(sc.id) >= 0;
          cb.addEventListener('change', function () {
            plan.component_ids = plan.component_ids || [];
            if (cb.checked && plan.component_ids.indexOf(sc.id) < 0) plan.component_ids.push(sc.id);
            if (!cb.checked) plan.component_ids = plan.component_ids.filter(function (id) { return id !== sc.id; });
          });
          label.appendChild(cb);
          label.appendChild(document.createTextNode(sc.name || SCENARIO_TEMPLATES[sc.type] || sc.id));
          components.appendChild(label);
        });
      }
      card.appendChild(components);
      container.appendChild(card);
    });
  }

  function addPlan() {
    if (planList.length >= MAX_SCENARIOS) {
      showError('Maximum plans reached (' + MAX_SCENARIOS + ').');
      return;
    }
    var ids = scenarioList.map(function (s) { return s.id; });
    planList.push({
      id: nextPlanId(),
      name: 'Plan ' + (planList.length + 1),
      component_ids: ids.slice()
    });
    renderPlanList();
  }

  function collectScenarios() {
    return scenarioList.map(function (s) {
      return { id: s.id, name: s.name || SCENARIO_TYPES[s.type], type: s.type, params: s.params || {} };
    });
  }

  function collectPlans() {
    sanitizePlans();
    return planList
      .map(function (p) {
        return {
          id: p.id,
          name: p.name || p.id,
          component_ids: (p.component_ids || []).slice()
        };
      })
      .filter(function (p) { return p.component_ids.length > 0; });
  }

  function setupTabs() {
    var tabIds = ['tabOverview', 'tabTrajectories', 'tabMC', 'tabBudget'];
    var panelIds = ['panelOverview', 'panelTrajectories', 'panelMC', 'panelBudget'];
    tabIds.forEach(function (tabId, i) {
      var tab = $(tabId);
      var panel = $(panelIds[i]);
      if (!tab || !panel) return;
      tab.addEventListener('click', function () {
        tabIds.forEach(function (id, j) {
          var t = $(id);
          var p = $(panelIds[j]);
          if (t) t.setAttribute('aria-selected', j === i ? 'true' : 'false');
          if (p) p.classList.toggle('is-active', j === i);
        });
      });
    });
  }

  function getBudgetState() {
    var monthlyByCategory = {};
    var monthlyTotal = 0;
    BUDGET_CATEGORIES.forEach(function (id) {
      var el = $('budget_' + id);
      var v = el ? Math.max(0, parseFloat(el.value) || 0) : 0;
      monthlyByCategory[id] = v;
      monthlyTotal += v;
    });
    var oneoffsEl = $('budget_annual_oneoffs');
    var annualOneoffs = oneoffsEl ? Math.max(0, parseFloat(oneoffsEl.value) || 0) : 0;
    var oneoffsMonthly = annualOneoffs / 12;
    var totalMonthlyEquivalent = monthlyTotal + oneoffsMonthly;
    var annualTarget = monthlyTotal * 12 + annualOneoffs;

    var categoryLabels = {
      housing: 'Housing', utilities: 'Utilities', groceries: 'Groceries & food', dining_out: 'Dining out',
      transport: 'Transport', healthcare: 'Healthcare', insurance: 'Insurance', subscriptions: 'Subscriptions',
      shopping: 'Shopping & discretionary', travel: 'Travel', gifts_donations: 'Gifts & donations',
      childcare: 'Childcare', pet_food: 'Pet food', pet_insurance: 'Pet insurance', phone: 'Phone bill',
      gym: 'Gym', other: 'Other'
    };
    var pieLabels = [];
    var pieValues = [];
    BUDGET_CATEGORIES.forEach(function (id) {
      if (monthlyByCategory[id] > 0) {
        pieLabels.push(categoryLabels[id] || id);
        pieValues.push(monthlyByCategory[id]);
      }
    });
    if (annualOneoffs > 0) {
      pieLabels.push('Annual one-offs');
      pieValues.push(oneoffsMonthly);
    }
    return {
      monthlyByCategory: monthlyByCategory,
      monthlyTotal: monthlyTotal,
      annualOneoffs: annualOneoffs,
      annualTarget: annualTarget,
      totalMonthlyEquivalent: totalMonthlyEquivalent,
      pieLabels: pieLabels,
      pieValues: pieValues
    };
  }

  function updateBudgetChart() {
    var canvas = $('chartBudget');
    if (!canvas) return;
    var state = getBudgetState();
    if (chartBudget) chartBudget.destroy();
    chartBudget = null;
    if (state.pieValues.length === 0) {
      var ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }
    var colors = BUDGET_CHART_COLORS.slice();
    while (colors.length < state.pieLabels.length) colors.push('#94a3b8');
    chartBudget = new Chart(canvas.getContext('2d'), {
      type: 'pie',
      data: {
        labels: state.pieLabels,
        datasets: [{
          data: state.pieValues,
          backgroundColor: colors.slice(0, state.pieLabels.length),
          borderColor: 'transparent',
          borderWidth: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: { position: 'right' },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                var v = ctx.raw;
                var pct = state.totalMonthlyEquivalent > 0 ? (100 * v / state.totalMonthlyEquivalent).toFixed(1) : 0;
                return ctx.label + ': ' + formatCurrency(v) + '/mo (' + pct + '%)';
              }
            }
          }
        }
      }
    });
  }

  function renderBudgetSummary() {
    var state = getBudgetState();
    var monthlyEl = $('budgetMonthlyTotal');
    var annualEl = $('budgetAnnualTarget');
    if (monthlyEl) monthlyEl.textContent = formatCurrency(state.monthlyTotal) + '/mo';
    if (annualEl) annualEl.textContent = formatCurrency(Math.round(state.annualTarget / 1000) * 1000);
  }

  function setupBudgetTab() {
    function refresh() {
      renderBudgetSummary();
      updateBudgetChart();
    }
    BUDGET_CATEGORIES.forEach(function (id) {
      var el = $('budget_' + id);
      if (el) {
        el.addEventListener('input', refresh);
        el.addEventListener('change', refresh);
      }
    });
    var oneoffsEl = $('budget_annual_oneoffs');
    if (oneoffsEl) {
      oneoffsEl.addEventListener('input', refresh);
      oneoffsEl.addEventListener('change', refresh);
    }
    var applyBtn = $('btnBudgetApply');
    if (applyBtn) {
      applyBtn.addEventListener('click', function () {
        var state = getBudgetState();
        var target = Math.round(state.annualTarget / 1000) * 1000;
        var spendingEl = $('drawdown_spending_today');
        var replacementEl = $('drawdown_replacement_income_today');
        if (spendingEl) spendingEl.value = target;
        if (replacementEl) replacementEl.value = target;
        refresh();
        showError('Annual spending target set to ' + formatCurrency(target) + '. Update projections to apply.', true);
      });
    }
    try {
      var saved = localStorage.getItem(BUDGET_STORAGE_KEY);
      if (saved) {
        var obj = JSON.parse(saved);
        BUDGET_CATEGORIES.forEach(function (id) {
          var el = $('budget_' + id);
          if (el && obj[id] != null && !isNaN(obj[id])) el.value = Math.max(0, obj[id]);
        });
        if (oneoffsEl && obj.annual_oneoffs != null && !isNaN(obj.annual_oneoffs)) oneoffsEl.value = Math.max(0, obj.annual_oneoffs);
      }
    } catch (e) { /* ignore */ }
    refresh();
    document.addEventListener('change', function saveBudget(e) {
      if (!e.target || !e.target.id) return;
      if (e.target.id === 'budget_annual_oneoffs' || BUDGET_CATEGORIES.some(function (id) { return e.target.id === 'budget_' + id; })) {
        var state = getBudgetState();
        var obj = {};
        BUDGET_CATEGORIES.forEach(function (id) { obj[id] = state.monthlyByCategory[id]; });
        obj.annual_oneoffs = state.annualOneoffs;
        try { localStorage.setItem(BUDGET_STORAGE_KEY, JSON.stringify(obj)); } catch (err) { /* ignore */ }
      }
    });
  }

  function renderSaleBreakdown(data) {
    var el = $('saleBreakdown');
    if (!el) return;
    var breakdowns = data.sale_breakdowns || {};
    var firstKey = Object.keys(breakdowns)[0];
    var sale = firstKey ? breakdowns[firstKey] : {};
    if (!sale || sale.sale_price == null) {
      el.innerHTML = '<span class="loading">No sale data. Add a Sell & invest scenario.</span>';
      return;
    }
    var rows = [
      ['Sale price (gross)', sale.sale_price],
      ['Selling costs', sale.selling_costs_dollars],
      ['Net proceeds', sale.net_proceeds]
    ];
    el.innerHTML = '<table><thead><tr><th>Item</th><th>Amount</th></tr></thead><tbody>' +
      rows.map(function (r) { return '<tr><td>' + r[0] + '</td><td class="num currency">' + formatCurrency(r[1]) + '</td></tr>'; }).join('') +
      '</tbody></table>';
  }

  function renderBenchmarkTable(data) {
    var years = data.benchmark_years || [];
    var el = $('benchmarkTable');
    if (!el) return;
    var scenarios = data.scenarios || {};
    var order = scenarioList.map(function (s) { return s.id; }).filter(function (id) { return scenarios[id]; });
    if (!years.length || !order.length) {
      el.innerHTML = '<span class="loading">Add scenarios and update projections.</span>';
      return;
    }
    var html = '<table><thead><tr><th>Years</th>';
    order.forEach(function (id) { html += '<th>' + (scenarios[id].name || id) + '</th>'; });
    var retireEndYear = Number($('drawdown_end_year')?.value);
    html += '</tr></thead><tbody>';
    years.forEach(function (y) {
      var label = (isFinite(retireEndYear) && y === retireEndYear) ? y + ' (retire)' : String(y);
      html += '<tr><td>' + label + '</td>';
      order.forEach(function (id) {
        var vb = scenarios[id].values_at_benchmark || {};
        html += '<td class="num">' + nominalTodayHtml(vb[y], y) + '</td>';
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  }

  function renderMCBenchmarkTable(data) {
    var el = $('mcBenchmarkTable');
    if (!el) return;
    if (!data || !data.benchmark_years || !data.scenarios) {
      el.innerHTML = '<span class="loading">Update projections to see Monte Carlo medians.</span>';
      return;
    }
    var scenarios = data.scenarios || {};
    var order = scenarioList.map(function (s) { return s.id; }).filter(function (id) { return scenarios[id]; });
    var years = data.benchmark_years || [];
    if (!order.length || !years.length) {
      el.innerHTML = '<span class="loading">Add scenarios and update projections.</span>';
      return;
    }
    var showRiskCols = !!$('mcShowRiskColumns')?.checked;
    function metricCell(sc, y) {
      var med = (sc.values_at_benchmark || {})[y];
      var p25 = (sc.p25_at_benchmark || {})[y];
      var p75 = (sc.p75_at_benchmark || {})[y];
      var p10 = (sc.p10_at_benchmark || {})[y];
      var es = (sc.es_at_benchmark || {})[y];
      var spread = (p75 == null || p25 == null) ? null : Number(p75) - Number(p25);
      var ratio = (med == null || !isFinite(med) || med === 0 || p25 == null) ? null : Number(p25) / Number(med);
      return {
        spread: spread,
        ratio: ratio,
        p10: p10,
        es: es
      };
    }
    var html = '<table><thead><tr><th>Years</th>';
    order.forEach(function (id) {
      var nm = scenarios[id].name || id;
      html += '<th>' + nm + ' (med)</th>';
      if (showRiskCols) {
        html += '<th>' + nm + ' (p75-p25)</th>';
        html += '<th>' + nm + ' (p25/med)</th>';
        html += '<th>' + nm + ' (p10)</th>';
        html += '<th>' + nm + ' (ES)</th>';
      }
    });
    var retireEndYear = Number($('drawdown_end_year')?.value);
    html += '</tr></thead><tbody>';
    years.forEach(function (y) {
      var label = (isFinite(retireEndYear) && y === retireEndYear) ? y + ' (retire)' : String(y);
      html += '<tr><td>' + label + '</td>';
      order.forEach(function (id) {
        var sc = scenarios[id] || {};
        var vb = sc.values_at_benchmark || {};
        html += '<td class="num">' + nominalTodayHtml(vb[y], y) + '</td>';
        if (showRiskCols) {
          var m = metricCell(sc, y);
          html += '<td class="num">' + formatCurrency(m.spread) + '</td>';
          html += '<td class="num">' + (m.ratio == null || isNaN(m.ratio) ? '—' : (m.ratio * 100).toFixed(1) + '%') + '</td>';
          html += '<td class="num">' + formatCurrency(m.p10) + '</td>';
          html += '<td class="num">' + formatCurrency(m.es) + '</td>';
        }
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  }

  function renderCombinedPlanTable(data) {
    var el = $('combinedPlanTable');
    if (!el) return;
    if (!data || !data.plans) {
      el.innerHTML = '<span class="loading">Update projections to see combined plan statistics.</span>';
      return;
    }
    var planIds = Object.keys(data.plans);
    if (!planIds.length) {
      el.innerHTML = '<span class="loading">No plan output yet.</span>';
      return;
    }
    var years = data.benchmark_years || [];
    if (!years.length) {
      el.innerHTML = '<span class="loading">No benchmark years in plan output.</span>';
      return;
    }
    var html = '<table><thead><tr><th>Years</th>';
    planIds.forEach(function (pid) {
      var p = data.plans[pid] || {};
      html += '<th>' + (p.name || pid) + '</th>';
    });
    var retireEndYear = Number($('drawdown_end_year')?.value);
    html += '</tr></thead><tbody>';
    years.forEach(function (y) {
      var label = (isFinite(retireEndYear) && y === retireEndYear) ? y + ' (retire)' : String(y);
      html += '<tr><td>' + label + '</td>';
      planIds.forEach(function (pid) {
        var plan = data.plans[pid] || {};
        var det = (plan.values_at_benchmark || {})[y];
        var med = (plan.median && plan.median.length > y) ? plan.median[y] : null;
        var p25 = (plan.p25_at_benchmark || {})[y];
        var p75 = (plan.p75_at_benchmark || {})[y];
        html += '<td class="num">' +
          '<div class="num-main">Det: ' + formatCurrency(det) + '</div>' +
          '<div class="num-sub">MC med: ' + formatCurrency(med) + '</div>' +
          '<div class="num-sub">MC p25/p75: ' + formatCurrency(p25) + ' / ' + formatCurrency(p75) + '</div>' +
          '</td>';
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  }

  function renderDrawdownSummary(data) {
    var el = $('drawdownSummary');
    if (!el) return;
    if (!data || !data.plans) {
      el.innerHTML = '<span class="loading">Update projections to see drawdown metrics.</span>';
      return;
    }
    var plans = data.plans || {};
    var planIds = Object.keys(plans);
    if (!planIds.length) {
      el.innerHTML = '<span class="loading">No plan data available for drawdown.</span>';
      return;
    }
    var order = planOrderFromData({ plans: plans });
    if (!order.length) order = planIds;
    var firstPlan = order.length ? (plans[order[0]] || {}).drawdown : {};
    var threshold = (firstPlan.success_threshold != null && !isNaN(firstPlan.success_threshold))
      ? (firstPlan.success_threshold * 100).toFixed(0) : '90';
    var html = '<table><thead><tr><th>Plan</th><th>Success prob.</th><th>Failure</th><th>Depletion prob.</th><th>Target start year</th><th>Recommended year (' + threshold + '% success)</th><th>Worst year</th><th>Assumed portfolio (year 0)</th><th>End balance (median)</th><th>Sustainable W (median)</th><th>Coast FIRE now (det.)</th><th>Coast FIRE now (prob. @ ' + threshold + '%)</th><th>Required at start</th><th>Median depletion year</th></tr></thead><tbody>';
    order.forEach(function (pid) {
      var p = plans[pid] || {};
      var d = p.drawdown || {};
      var success = d.success_probability;
      var failure = d.failure_probability;
      var depProb = d.depletion_probability_by_end_year;
      var targetYear = d.start_year;
      var recommendedYear = d.earliest_feasible_retirement_year;
      var coastDet = d.coast_fire_number_today;
      var coastProb = d.coast_fire_now_probabilistic;
      var assumed0 = d.portfolio_at_year_0_median;
      var worstY = d.worst_shortfall_year;
      var worstP = d.worst_shortfall_probability;
      var worstCell = (worstY != null && worstP != null && worstP > 0)
        ? (worstY + ' (' + (worstP * 100).toFixed(1) + '%)') : '—';
      var sustMed = d.sustainable_withdrawal_median;
      var y = d.yearly;
      var endBalance = null;
      if (y && y.portfolio_end_nominal_p50 && y.portfolio_end_nominal_p50.length) {
        endBalance = y.portfolio_end_nominal_p50[y.portfolio_end_nominal_p50.length - 1];
      }
      html += '<tr>' +
        '<td>' + (p.name || pid) + '</td>' +
        '<td class="num">' + (success == null || isNaN(success) ? '—' : (success * 100).toFixed(1) + '%') + '</td>' +
        '<td class="num">' + (failure == null || isNaN(failure) ? '—' : (failure * 100).toFixed(1) + '%') + '</td>' +
        '<td class="num">' + (depProb == null || isNaN(depProb) ? '—' : (depProb * 100).toFixed(1) + '%') + '</td>' +
        '<td class="num">' + (targetYear != null && !isNaN(targetYear) ? targetYear : '—') + '</td>' +
        '<td class="num">' + (recommendedYear != null ? recommendedYear : '—') + '</td>' +
        '<td class="num">' + worstCell + '</td>' +
        '<td class="num currency">' + (assumed0 != null && !isNaN(assumed0) ? formatCurrency(assumed0) : '—') + '</td>' +
        '<td class="num currency">' + (endBalance != null && !isNaN(endBalance) ? formatCurrency(endBalance) : '—') + '</td>' +
        '<td class="num currency">' + (sustMed != null && !isNaN(sustMed) ? formatCurrency(Math.round(sustMed)) : '—') + '</td>' +
        '<td class="num currency">' + formatCurrency(coastDet) + '</td>' +
        '<td class="num currency">' + (coastProb != null && !isNaN(coastProb) ? formatCurrency(coastProb) : '—') + '</td>' +
        '<td class="num currency">' + formatCurrency(d.required_portfolio_at_start_year_nominal) + '</td>' +
        '<td class="num">' + (d.median_depletion_year == null ? 'No depletion' : d.median_depletion_year) + '</td>' +
        '</tr>';
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  }

  function renderSustainableWithdrawalSummary(data) {
    var el = $('sustainableWithdrawalSummary');
    if (!el) return;
    if (!data || !data.plans) {
      el.innerHTML = '<span class="loading">Update projections to see sustainable withdrawal.</span>';
      return;
    }
    var order = planOrderFromData({ plans: data.plans });
    if (!order.length) {
      el.innerHTML = '<span class="loading">No plan data.</span>';
      return;
    }
    var targetFrac = (order.length && data.plans[order[0]].drawdown && data.plans[order[0]].drawdown.target_terminal_fraction != null)
      ? (data.plans[order[0]].drawdown.target_terminal_fraction * 100).toFixed(0) : '0';
    var html = '<div class="table-wrap"><table><thead><tr><th>Plan</th><th>p10</th><th>p25</th><th>Median</th><th>p75</th><th>p90</th></tr></thead><tbody>';
    order.forEach(function (pid) {
      var p = data.plans[pid] || {};
      var d = p.drawdown || {};
      var p10 = d.sustainable_withdrawal_p10;
      var p25 = d.sustainable_withdrawal_p25;
      var med = d.sustainable_withdrawal_median;
      var p75 = d.sustainable_withdrawal_p75;
      var p90 = d.sustainable_withdrawal_p90;
      function cell(v) {
        return '<td class="num currency">' + (v != null && !isNaN(v) ? formatCurrency(Math.round(v)) : '—') + '</td>';
      }
      html += '<tr><td>' + (p.name || pid) + '</td>' + cell(p10) + cell(p25) + cell(med) + cell(p75) + cell(p90) + '</tr>';
    });
    html += '</tbody></table></div>';
    html += '<p class="section-hint">Target terminal balance: ' + targetFrac + '% of start (0% = exhaust by retirement end).</p>';
    el.innerHTML = html;
  }

  function buildSustainableWithdrawalChart(data) {
    var canvas = $('chartSustainableWithdrawal');
    if (!canvas) return;
    if (chartSustainableWithdrawal) { chartSustainableWithdrawal.destroy(); chartSustainableWithdrawal = null; }
    if (!data || !data.plans) {
      var ctx = canvas.getContext('2d');
      if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }
    var order = planOrderFromData({ plans: data.plans });
    if (!order.length) return;
    var firstPlan = data.plans[order[0]] || {};
    var d = firstPlan.drawdown || {};
    var perPath = d.sustainable_withdrawal_per_path;
    if (!perPath || !perPath.length) return;
    var arr = perPath.filter(function (v) { return v != null && isFinite(v) && v >= 0; });
    if (!arr.length) return;
    var minV = Math.min.apply(null, arr);
    var maxV = Math.max.apply(null, arr);
    var numBins = 24;
    if (maxV <= minV) maxV = minV + 1;
    var step = (maxV - minV) / numBins || 1;
    var bins = [];
    var labels = [];
    for (var i = 0; i < numBins; i++) {
      var lo = minV + i * step;
      var hi = lo + step;
      bins.push(0);
      labels.push(formatCurrency(Math.round(lo / 1000) * 1000));
    }
    arr.forEach(function (v) {
      var idx = Math.min(numBins - 1, Math.floor((v - minV) / step));
      if (idx >= 0) bins[idx]++;
    });
    chartSustainableWithdrawal = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'Paths',
          data: bins,
          backgroundColor: 'rgba(59, 130, 246, 0.6)',
          borderColor: '#3b82f6',
          borderWidth: 1
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: function (ctx) {
                var i = ctx[0].dataIndex;
                var lo = minV + i * step;
                var hi = lo + step;
                return formatCurrency(Math.round(lo)) + ' – ' + formatCurrency(Math.round(hi));
              },
              label: function (ctx) { return ctx.raw + ' paths'; }
            }
          }
        },
        scales: {
          x: {
            title: { display: true, text: 'Sustainable withdrawal (today\'s $/year)' },
            ticks: { maxRotation: 45, maxTicksLimit: 12 }
          },
          y: { title: { display: true, text: 'Number of paths' }, min: 0 }
        }
      }
    });
  }

  function renderDrawdownYearlyTables(data) {
    var el = document.getElementById('drawdownYearlyTables');
    if (!el) return;
    if (!data || !data.plans) {
      el.innerHTML = '<span class="loading">Update projections to see drawdown by year.</span>';
      return;
    }
    var plans = data.plans || {};
    var order = planOrderFromData({ plans: plans });
    if (!order.length) {
      el.innerHTML = '<span class="loading">No plan data for drawdown by year.</span>';
      return;
    }
    var html = '';
    order.forEach(function (pid) {
      var p = plans[pid] || {};
      var d = p.drawdown || {};
      var y = d.yearly;
      if (!y || !y.years || !y.years.length) return;
      var years = y.years;
      var shortfallProb = y.shortfall_probability || [];
      var p50 = y.portfolio_end_nominal_p50 || [];
      var p10 = y.portfolio_end_nominal_p10 || [];
      var p90 = y.portfolio_end_nominal_p90 || [];
      var withdraw = y.portfolio_withdrawal_nominal_p50 || [];
      var shortfallAmt = y.shortfall_nominal_p50 || [];
      html += '<h4 class="drawdown-plan-title">' + (p.name || pid) + '</h4>';
      html += '<div class="table-wrap"><table><thead><tr><th>Year</th><th>Shortfall prob.</th><th>Portfolio end (p50)</th><th>Portfolio end (p10–p90)</th><th>Withdrawal (p50)</th><th>Shortfall (p50)</th></tr></thead><tbody>';
      for (var i = 0; i < years.length; i++) {
        var sp = (shortfallProb[i] != null && !isNaN(shortfallProb[i])) ? (shortfallProb[i] * 100).toFixed(1) + '%' : '—';
        var lo = (p10[i] != null && !isNaN(p10[i])) ? formatCurrency(p10[i]) : '—';
        var hi = (p90[i] != null && !isNaN(p90[i])) ? formatCurrency(p90[i]) : '—';
        var range = lo + ' – ' + hi;
        html += '<tr>' +
          '<td class="num">' + years[i] + '</td>' +
          '<td class="num">' + sp + '</td>' +
          '<td class="num currency">' + formatCurrency(p50[i]) + '</td>' +
          '<td class="num currency">' + range + '</td>' +
          '<td class="num currency">' + formatCurrency(withdraw[i]) + '</td>' +
          '<td class="num currency">' + (shortfallAmt[i] != null && shortfallAmt[i] > 0 ? formatCurrency(shortfallAmt[i]) : '—') + '</td>' +
          '</tr>';
      }
      html += '</tbody></table></div>';
    });
    el.innerHTML = html || '<span class="loading">No yearly drawdown data.</span>';
  }

  function renderSpendingSensitivityTable() {
    var el = document.getElementById('spendingSensitivitySection');
    if (!el) return;
    if (!lastSpendingSensitivity || typeof lastSpendingSensitivity !== 'object') {
      el.innerHTML = '<span class="loading">Update projections to see spending sensitivity.</span>';
      return;
    }
    var mults = [0.5, 0.8, 1.0, 1.2, 1.5];
    var data100 = lastSpendingSensitivity[1.0];
    if (!data100 || !data100.plans) {
      el.innerHTML = '<span class="loading">No drawdown data for sensitivity.</span>';
      return;
    }
    var order = planOrderFromData({ plans: data100.plans });
    if (!order.length) {
      el.innerHTML = '<span class="loading">No plans for spending sensitivity.</span>';
      return;
    }
    var firstPlanId = order[0];
    var baseSpending = (data100.plans[firstPlanId] || {}).drawdown && (data100.plans[firstPlanId].drawdown.replacement_income_today != null)
      ? Number(data100.plans[firstPlanId].drawdown.replacement_income_today)
      : 0;
    var thresholdPct = (data100.plans[firstPlanId] && data100.plans[firstPlanId].drawdown && data100.plans[firstPlanId].drawdown.success_threshold != null)
      ? Math.round(data100.plans[firstPlanId].drawdown.success_threshold * 100)
      : 90;

    var headerCells = mults.map(function (m) {
      var amt = Math.round(baseSpending * m);
      return '<th class="num">' + (m * 100) + '% (' + formatCurrency(amt) + ')</th>';
    });
    var headerRow = '<tr><th>Plan</th>' + headerCells.join('') + '</tr>';

    var html = '';
    html += '<p class="section-hint" style="margin-bottom:0.75rem;">Success probability at your target retirement start year.</p>';
    html += '<div class="table-wrap"><table><thead>' + headerRow + '</thead><tbody>';
    order.forEach(function (pid) {
      var planName = (data100.plans[pid] || {}).name || pid;
      var cells = mults.map(function (m) {
        var data = lastSpendingSensitivity[m];
        if (!data || !data.plans || !data.plans[pid]) return '<td class="num">—</td>';
        var success = data.plans[pid].drawdown && data.plans[pid].drawdown.success_probability;
        if (success == null || isNaN(success)) return '<td class="num">—</td>';
        return '<td class="num">' + (success * 100).toFixed(1) + '%</td>';
      });
      html += '<tr><td>' + planName + '</td>' + cells.join('') + '</tr>';
      cells = mults.map(function (m) {
        var data = lastSpendingSensitivity[m];
        if (!data || !data.plans || !data.plans[pid]) return '<td class="num">—</td>';
        var success = data.plans[pid].drawdown && data.plans[pid].drawdown.success_probability;
        if (success == null || success >= 1) return '<td class="num">—</td>';
        var medYear = data.plans[pid].drawdown && data.plans[pid].drawdown.median_first_shortfall_year;
        return '<td class="num">' + (medYear != null && !isNaN(medYear) ? Math.round(medYear) : '—') + '</td>';
      });
      html += '<tr><td class="num-sub" style="padding-left:1.25rem;">First shortfall year (median)</td>' + cells.join('') + '</tr>';
    });
    html += '</tbody></table></div>';

    html += '<p class="section-hint" style="margin:1.25rem 0 0.75rem 0;">Depletion probability: fraction of paths where portfolio balance reaches 0 before retirement end date.</p>';
    html += '<div class="table-wrap"><table><thead>' + headerRow + '</thead><tbody>';
    order.forEach(function (pid) {
      var planName = (data100.plans[pid] || {}).name || pid;
      var cells = mults.map(function (m) {
        var data = lastSpendingSensitivity[m];
        if (!data || !data.plans || !data.plans[pid]) return '<td class="num">—</td>';
        var depProb = data.plans[pid].drawdown && data.plans[pid].drawdown.depletion_probability_by_end_year;
        if (depProb == null || isNaN(depProb)) return '<td class="num">—</td>';
        return '<td class="num">' + (depProb * 100).toFixed(1) + '%</td>';
      });
      html += '<tr><td>' + planName + '</td>' + cells.join('') + '</tr>';
      cells = mults.map(function (m) {
        var data = lastSpendingSensitivity[m];
        if (!data || !data.plans || !data.plans[pid]) return '<td class="num">—</td>';
        var depProb = data.plans[pid].drawdown && data.plans[pid].drawdown.depletion_probability_by_end_year;
        if (depProb == null || depProb <= 0) return '<td class="num">—</td>';
        var avgYear = data.plans[pid].drawdown && data.plans[pid].drawdown.average_year_balance_hits_zero;
        return '<td class="num">' + (avgYear != null && !isNaN(avgYear) ? Math.round(avgYear) : '—') + '</td>';
      });
      html += '<tr><td class="num-sub" style="padding-left:1.25rem;">Avg. year balance → 0</td>' + cells.join('') + '</tr>';
    });
    html += '</tbody></table></div>';

    html += '<p class="section-hint" style="margin:1.25rem 0 0.75rem 0;">Earliest feasible retirement year (at ' + thresholdPct + '% success).</p>';
    html += '<div class="table-wrap"><table><thead>' + headerRow + '</thead><tbody>';
    order.forEach(function (pid) {
      var planName = (data100.plans[pid] || {}).name || pid;
      var cells = mults.map(function (m) {
        var data = lastSpendingSensitivity[m];
        if (!data || !data.plans || !data.plans[pid]) return '<td class="num">—</td>';
        var year = data.plans[pid].drawdown && data.plans[pid].drawdown.earliest_feasible_retirement_year;
        if (year == null) return '<td class="num">—</td>';
        return '<td class="num">' + year + '</td>';
      });
      html += '<tr><td>' + planName + '</td>' + cells.join('') + '</tr>';
    });
    html += '</tbody></table></div>';
    el.innerHTML = html;
  }

  function runSpendingSensitivity() {
    var baseDrawdown = collectDrawdownParams(collectParams());
    if (!baseDrawdown.enabled) {
      lastSpendingSensitivity = null;
      renderSpendingSensitivityTable();
      return Promise.resolve();
    }
    var globalParams = collectParams();
    var scenarios = collectScenarios();
    var plans = collectPlans();
    var mults = [0.5, 0.8, 1.2, 1.5];
    var promises = mults.map(function (m) {
      var d = {
        enabled: baseDrawdown.enabled,
        start_year: baseDrawdown.start_year,
        end_year: baseDrawdown.end_year,
        spending_today: baseDrawdown.spending_today * m,
        replacement_income_today: baseDrawdown.replacement_income_today * m,
        spending_rule: baseDrawdown.spending_rule,
        success_threshold: baseDrawdown.success_threshold,
        safe_withdrawal_rate: baseDrawdown.safe_withdrawal_rate,
        inflation_mode_for_spending: baseDrawdown.inflation_mode_for_spending,
        coast_growth_rate: baseDrawdown.coast_growth_rate,
        income_sources: baseDrawdown.income_sources
      };
      return fetch(API + '/api/drawdown', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ global_params: globalParams, components: scenarios, plans: plans, drawdown: d })
      }).then(function (r) {
        return r.json().then(function (j) {
          if (!r.ok || j.error) throw new Error(j.error || r.statusText);
          return j;
        });
      });
    });
    return Promise.all(promises).then(function (results) {
      lastSpendingSensitivity = {
        0.5: results[0],
        0.8: results[1],
        1.0: lastDrawdownData,
        1.2: results[2],
        1.5: results[3]
      };
      renderSpendingSensitivityTable();
    }).catch(function (e) {
      lastSpendingSensitivity = null;
      renderSpendingSensitivityTable();
      throw e;
    });
  }

  function planOrderFromData(data) {
    var plans = (data && data.plans) || {};
    var ids = Object.keys(plans);
    var ordered = planList.map(function (p) { return p.id; }).filter(function (id) { return !!plans[id]; });
    ids.forEach(function (id) {
      if (ordered.indexOf(id) < 0) ordered.push(id);
    });
    return ordered;
  }

  function buildPlanTrajectoryChart(data) {
    var plans = (data && data.plans) || {};
    var order = planOrderFromData(data);
    if (!order.length) return;
    var first = plans[order[0]] || {};
    var years = first.years || [];
    if (!years.length) return;
    var datasets = [];
    order.forEach(function (pid, i) {
      var p = plans[pid] || {};
      var color = CHART_COLORS[i % CHART_COLORS.length];
      datasets.push({
        label: (p.name || pid) + ' (det)',
        data: p.values || [],
        borderColor: color,
        backgroundColor: 'transparent',
        fill: false,
        tension: 0.1,
        borderWidth: 2
      });
      datasets.push({
        label: (p.name || pid) + ' (MC med)',
        data: p.median || [],
        borderColor: color,
        backgroundColor: 'transparent',
        fill: false,
        tension: 0.1,
        borderDash: [6, 4],
        borderWidth: 1.5
      });
    });
    var canvas = $('chartPlanTrajectories');
    if (!canvas) return;
    if (chartPlanTrajectories) chartPlanTrajectories.destroy();
    chartPlanTrajectories = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { labels: years, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'top' } },
        scales: {
          x: { title: { display: true, text: 'Years from today' } },
          y: { title: { display: true, text: 'Net worth (nominal)' }, ticks: { callback: function (v) { return '$' + (v / 1e6).toFixed(1) + 'M'; } } }
        }
      }
    });
  }

  function buildPlanMCChart(data) {
    var plans = (data && data.plans) || {};
    var order = planOrderFromData(data);
    if (!order.length) return;
    var first = plans[order[0]] || {};
    var years = first.years || [];
    if (!years.length) return;
    var datasets = [];
    order.forEach(function (pid, i) {
      var p = plans[pid] || {};
      var color = CHART_COLORS[i % CHART_COLORS.length];
      if (p.p25 && p.p75 && p.p25.length && p.p75.length) {
        datasets.push({
          label: (p.name || pid) + ' 25–75%',
          data: p.p25,
          borderColor: 'transparent',
          borderWidth: 0,
          backgroundColor: hexToRgba(color, 0.2),
          fill: '+1',
          tension: 0.1
        });
        datasets.push({
          label: (p.name || pid) + ' 75%',
          data: p.p75,
          borderColor: 'transparent',
          borderWidth: 0,
          fill: false
        });
      }
      datasets.push({
        label: (p.name || pid) + ' (median)',
        data: p.median || [],
        borderColor: color,
        backgroundColor: 'transparent',
        fill: false,
        tension: 0.1,
        borderWidth: 2
      });
    });
    var canvas = $('chartPlanMC');
    if (!canvas) return;
    if (chartPlanMC) chartPlanMC.destroy();

    var annotations = {};
    if (lastDrawdownData && lastDrawdownData.plans) {
      var orderDd = planOrderFromData({ plans: lastDrawdownData.plans });
      var firstPlanDd = orderDd.length ? lastDrawdownData.plans[orderDd[0]] : null;
      var dd = firstPlanDd && firstPlanDd.drawdown ? firstPlanDd.drawdown : null;
      var thresholdPct = (dd && dd.success_threshold != null) ? Math.round(dd.success_threshold * 100) : 90;
      if (dd && dd.start_year != null && !isNaN(dd.start_year)) {
        annotations.targetRetirement = {
          type: 'line',
          xMin: dd.start_year,
          xMax: dd.start_year,
          xScaleID: 'x',
          borderColor: 'rgba(100,100,100,0.7)',
          borderWidth: 2,
          borderDash: [4, 4],
          adjustScaleRange: false,
          label: { display: true, content: 'Target retirement', position: 'start' }
        };
      }
      if (dd && dd.earliest_feasible_retirement_year != null && !isNaN(dd.earliest_feasible_retirement_year)) {
        annotations.recommendedYear = {
          type: 'line',
          xMin: dd.earliest_feasible_retirement_year,
          xMax: dd.earliest_feasible_retirement_year,
          xScaleID: 'x',
          borderColor: 'rgba(60,130,200,0.9)',
          borderWidth: 2,
          adjustScaleRange: false,
          label: { display: true, content: 'Recommended (' + thresholdPct + '% success)', position: 'start' }
        };
      }
    }

    var chartOptions = {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'top' } },
      scales: {
        x: { title: { display: true, text: 'Years from today' } },
        y: { title: { display: true, text: 'Net worth (nominal)' }, ticks: { callback: function (v) { return '$' + (v / 1e6).toFixed(1) + 'M'; } } }
      }
    };
    if (Object.keys(annotations).length > 0) {
      chartOptions.plugins.annotation = { annotations: annotations };
    }

    chartPlanMC = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { labels: years, datasets: datasets },
      options: chartOptions
    });
  }

  function buildDrawdownShortfallChart(data) {
    var canvas = document.getElementById('chartDrawdownShortfall');
    if (!canvas) return;
    if (chartDrawdownShortfall) { chartDrawdownShortfall.destroy(); chartDrawdownShortfall = null; }
    if (!data || !data.plans) return;
    var plans = data.plans || {};
    var order = planOrderFromData({ plans: plans });
    var datasets = [];
    order.forEach(function (pid, i) {
      var p = plans[pid] || {};
      var d = p.drawdown || {};
      var y = d.yearly;
      if (!y || !y.years || !y.years.length) return;
      var prob = (y.shortfall_probability || []).map(function (v) { return (v != null && !isNaN(v)) ? v * 100 : 0; });
      datasets.push({
        label: (p.name || pid),
        data: prob,
        borderColor: CHART_COLORS[i % CHART_COLORS.length],
        backgroundColor: 'transparent',
        fill: false,
        tension: 0.2,
        borderWidth: 2
      });
    });
    if (!datasets.length) return;
    var firstPlan = plans[order[0]] || {};
    var labels = (firstPlan.drawdown && firstPlan.drawdown.yearly && firstPlan.drawdown.yearly.years) || [];
    if (!labels.length) return;
    chartDrawdownShortfall = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { labels: labels, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'top' } },
        scales: {
          x: { title: { display: true, text: 'Years from today' } },
          y: { title: { display: true, text: 'Shortfall probability (%)' }, min: 0, max: 100 }
        }
      }
    });
  }

  function buildDrawdownBalanceChart(data) {
    var canvas = document.getElementById('chartDrawdownBalance');
    if (!canvas) return;
    if (chartDrawdownBalance) { chartDrawdownBalance.destroy(); chartDrawdownBalance = null; }
    if (!data || !data.plans) return;
    var plans = data.plans || {};
    var order = planOrderFromData({ plans: plans });
    var datasets = [];
    order.forEach(function (pid, i) {
      var p = plans[pid] || {};
      var d = p.drawdown || {};
      var y = d.yearly;
      if (!y || !y.years || !y.years.length) return;
      var color = CHART_COLORS[i % CHART_COLORS.length];
      var p10 = y.portfolio_end_nominal_p10 || [];
      var p90 = y.portfolio_end_nominal_p90 || [];
      if (p10.length && p90.length) {
        datasets.push({
          label: (p.name || pid) + ' 10–90%',
          data: p10,
          borderColor: 'transparent',
          backgroundColor: hexToRgba(color, 0.2),
          fill: '+1',
          tension: 0.2
        });
        datasets.push({
          label: (p.name || pid) + ' 90%',
          data: p90,
          borderColor: 'transparent',
          fill: false
        });
      }
      datasets.push({
        label: (p.name || pid) + ' (median)',
        data: y.portfolio_end_nominal_p50 || [],
        borderColor: color,
        backgroundColor: 'transparent',
        fill: false,
        tension: 0.2,
        borderWidth: 2
      });
    });
    if (!datasets.length) return;
    var firstPlan = plans[order[0]] || {};
    var labels = (firstPlan.drawdown && firstPlan.drawdown.yearly && firstPlan.drawdown.yearly.years) || [];
    if (!labels.length) return;
    chartDrawdownBalance = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { labels: labels, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'top' } },
        scales: {
          x: { title: { display: true, text: 'Years from today' } },
          y: { title: { display: true, text: 'Portfolio end of year (nominal)' }, ticks: { callback: function (v) { return '$' + (v / 1e6).toFixed(1) + 'M'; } } }
        }
      }
    });
  }

  function buildDrawdownScanChart(data) {
    var canvas = document.getElementById('chartDrawdownScan');
    if (!canvas) return;
    if (chartDrawdownScan) { chartDrawdownScan.destroy(); chartDrawdownScan = null; }
    if (!data || !data.plans) return;
    var plans = data.plans || {};
    var order = planOrderFromData({ plans: plans });
    var threshold = (order.length && plans[order[0]] && plans[order[0]].drawdown && plans[order[0]].drawdown.success_threshold != null)
      ? plans[order[0]].drawdown.success_threshold * 100 : 90;
    var datasets = [];
    order.forEach(function (pid, i) {
      var p = plans[pid] || {};
      var d = p.drawdown || {};
      var scan = d.retirement_year_scan || [];
      if (!scan.length) return;
      var years = scan.map(function (x) { return x.year; });
      var probs = scan.map(function (x) { return (x.success_probability != null && !isNaN(x.success_probability)) ? x.success_probability * 100 : 0; });
      datasets.push({
        label: (p.name || pid),
        data: probs,
        borderColor: CHART_COLORS[i % CHART_COLORS.length],
        backgroundColor: 'transparent',
        fill: false,
        tension: 0.2,
        borderWidth: 2
      });
    });
    if (!datasets.length) return;
    var scan0 = (plans[order[0]] && plans[order[0]].drawdown && plans[order[0]].drawdown.retirement_year_scan) || [];
    var labels = scan0.map(function (x) { return x.year; });
    if (!labels.length) return;
    datasets.push({
      label: 'Target (' + threshold + '%)',
      data: labels.map(function () { return threshold; }),
      borderColor: 'rgba(128,128,128,0.8)',
      borderDash: [4, 4],
      borderWidth: 1.5,
      pointRadius: 0,
      fill: false
    });
    chartDrawdownScan = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { labels: labels, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'top' } },
        scales: {
          x: { title: { display: true, text: 'Retirement start year (years from today)' } },
          y: { title: { display: true, text: 'Success probability (%)' }, min: 0, max: 100 }
        }
      }
    });
  }

  function buildDrawdownImpactChart() {
    var canvas = document.getElementById('chartDrawdownImpact');
    if (!canvas) return;
    if (chartDrawdownImpact) { chartDrawdownImpact.destroy(); chartDrawdownImpact = null; }
    if (!lastDrawdownData || !lastDrawdownData.plans || !lastPlansData || !lastPlansData.plans) return;
    var order = planOrderFromData({ plans: lastDrawdownData.plans });
    if (!order.length) return;
    var pid = order[0];
    var plan = lastPlansData.plans[pid] || {};
    var dd = (lastDrawdownData.plans[pid] || {}).drawdown || {};
    var yearly = dd.yearly;
    if (!yearly || !yearly.years || !yearly.years.length) return;
    var startYear = dd.start_year != null ? Number(dd.start_year) : 0;
    var endYear = dd.end_year != null ? Number(dd.end_year) : yearly.years[yearly.years.length - 1];
    var p50 = yearly.portfolio_end_nominal_p50 || [];
    var p10 = yearly.portfolio_end_nominal_p10 || [];
    var p90 = yearly.portfolio_end_nominal_p90 || [];
    var planMedian = plan.median || [];
    var planName = plan.name || pid;

    var labels = [];
    for (var y = 0; y <= endYear; y++) labels.push(y);
    var noWithdrawals = labels.map(function (y) {
      return (y < planMedian.length && planMedian[y] != null && !isNaN(planMedian[y])) ? planMedian[y] : null;
    });
    var afterMedian = labels.map(function (y) {
      if (y < startYear) return (y < planMedian.length && planMedian[y] != null && !isNaN(planMedian[y])) ? planMedian[y] : null;
      var j = y - startYear;
      return (j < p50.length && p50[j] != null && !isNaN(p50[j])) ? p50[j] : null;
    });
    var afterP10 = labels.map(function (y) {
      if (y < startYear) return null;
      var j = y - startYear;
      return (j < p10.length && p10[j] != null && !isNaN(p10[j])) ? p10[j] : null;
    });
    var afterP90 = labels.map(function (y) {
      if (y < startYear) return null;
      var j = y - startYear;
      return (j < p90.length && p90[j] != null && !isNaN(p90[j])) ? p90[j] : null;
    });

    var colorNo = CHART_COLORS[0];
    var colorAfter = CHART_COLORS[1];
    var datasets = [
      {
        label: planName + ' — net worth if no withdrawals',
        data: noWithdrawals,
        borderColor: colorNo,
        backgroundColor: 'transparent',
        fill: false,
        tension: 0.2,
        borderWidth: 2
      },
      {
        label: planName + ' — 10–90% after withdrawals',
        data: afterP10,
        borderColor: 'transparent',
        backgroundColor: hexToRgba(colorAfter, 0.2),
        fill: '+1',
        tension: 0.2
      },
      {
        label: planName + ' — 90% after withdrawals',
        data: afterP90,
        borderColor: 'transparent',
        fill: false
      },
      {
        label: planName + ' — median after withdrawals',
        data: afterMedian,
        borderColor: colorAfter,
        backgroundColor: 'transparent',
        fill: false,
        tension: 0.2,
        borderWidth: 2
      }
    ];

    chartDrawdownImpact = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { labels: labels, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'top' } },
        scales: {
          x: { title: { display: true, text: 'Years from today' } },
          y: { title: { display: true, text: 'Portfolio / net worth (nominal)' }, ticks: { callback: function (v) { return '$' + (v / 1e6).toFixed(1) + 'M'; } } }
        }
      }
    });
  }

  function hexToRgba(hex, alpha) {
    if (!hex || hex[0] !== '#') return hex;
    var raw = hex.slice(1);
    if (raw.length === 3) raw = raw.split('').map(function (c) { return c + c; }).join('');
    if (raw.length !== 6) return hex;
    var r = parseInt(raw.slice(0, 2), 16);
    var g = parseInt(raw.slice(2, 4), 16);
    var b = parseInt(raw.slice(4, 6), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
  }

  function buildTrajectoryChart(data) {
    var scenarios = data.scenarios || {};
    var order = scenarioList.map(function (s) { return s.id; }).filter(function (id) { return scenarios[id]; });
    if (!order.length) return;
    var first = scenarios[order[0]];
    var years = first.years || [];
    if (!years.length) return;
    var datasets = order.map(function (id, i) {
      var sc = scenarios[id];
      return {
        label: sc.name || id,
        data: sc.values || [],
        borderColor: CHART_COLORS[i % CHART_COLORS.length],
        backgroundColor: 'transparent',
        fill: false,
        tension: 0.1
      };
    });
    var canvas = $('chartTrajectories');
    if (chartTrajectories) chartTrajectories.destroy();
    chartTrajectories = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { labels: years, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top' },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                var nominal = ctx.parsed.y;
                var yearsFromToday = Number(ctx.label);
                var today = toTodaysDollars(nominal, yearsFromToday, currentInflationRate);
                return ctx.dataset.label + ': ' + formatCurrency(nominal) + ' (Today$: ' + formatCurrency(today) + ')';
              }
            }
          }
        },
        scales: {
          x: { title: { display: true, text: 'Years from today' } },
          y: { title: { display: true, text: 'Net worth (nominal)' }, ticks: { callback: function (v) { return '$' + (v / 1e6).toFixed(1) + 'M'; } } }
        }
      }
    });
  }

  function buildMCChart(data) {
    var scenarios = data.scenarios || {};
    var order = scenarioList.map(function (s) { return s.id; }).filter(function (id) { return scenarios[id]; });
    if (!order.length) return;
    var first = scenarios[order[0]];
    var years = (first && first.years) || [];
    if (!years.length) return;
    var datasets = [];
    order.forEach(function (id, i) {
      var sc = scenarios[id];
      var color = CHART_COLORS[i % CHART_COLORS.length];
      if (sc.p25 && sc.p75 && sc.p25.length && sc.p75.length) {
        datasets.push({
          label: (sc.name || id) + ' 25–75%',
          data: sc.p25,
          borderColor: 'transparent',
          borderWidth: 0,
          backgroundColor: hexToRgba(color, 0.2),
          fill: '+1',
          tension: 0.1
        });
        datasets.push({
          label: (sc.name || id) + ' 75%',
          data: sc.p75,
          borderColor: 'transparent',
          borderWidth: 0,
          fill: false
        });
      }
      datasets.push({
        label: (sc.name || id) + (sc.is_deterministic ? ' (deterministic)' : ' (median)'),
        data: sc.median || sc.values || [],
        borderColor: color,
        backgroundColor: 'transparent',
        fill: false,
        tension: 0.1,
        borderWidth: 2
      });
    });
    var canvas = $('chartMC');
    if (chartMC) chartMC.destroy();
    chartMC = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { labels: years, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { position: 'top' },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                var nominal = ctx.parsed.y;
                var yearsFromToday = Number(ctx.label);
                var today = toTodaysDollars(nominal, yearsFromToday, currentInflationRate);
                return ctx.dataset.label + ': ' + formatCurrency(nominal) + ' (Today$: ' + formatCurrency(today) + ')';
              }
            }
          }
        },
        scales: {
          x: { title: { display: true, text: 'Years from today' } },
          y: { title: { display: true, text: 'Net worth (nominal)' }, ticks: { callback: function (v) { return '$' + (v / 1e6).toFixed(1) + 'M'; } } }
        }
      }
    });
  }

  function runScenarioMonteCarlo(globalParams, scenarios) {
    return fetch(API + '/api/scenarios_monte_carlo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ global_params: globalParams, scenarios: scenarios })
    }).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok || j.error) throw new Error(j.error || r.statusText);
        return j;
      });
    });
  }

  function exportBenchmarkCsv() {
    if (!lastScenariosData || !lastScenariosData.benchmark_years || !lastScenariosData.benchmark_years.length) {
      showError('Update projections first to export the table.');
      return;
    }
    var scenarios = lastScenariosData.scenarios || {};
    var order = scenarioList.map(function (s) { return s.id; }).filter(function (id) { return scenarios[id]; });
    if (!order.length) return;
    var finalBenchmarkYear = Math.max.apply(null, lastScenariosData.benchmark_years || []);
    if (!isFinite(finalBenchmarkYear) || finalBenchmarkYear < 1) return;

    function rounded(n) {
      if (n == null || isNaN(n)) return '';
      return String(Math.round(Number(n)));
    }

    var headers = ['Years'];
    order.forEach(function (id) {
      var name = (scenarios[id].name || id).replace(/,/g, ';');
      headers.push(name + ' (nominal)');
      headers.push(name + ' (today$)');
      headers.push(name + ' (income nominal)');
      headers.push(name + ' (income today$)');
    });
    var rows = [headers.join(',')];
    for (var y = 1; y <= finalBenchmarkYear; y += 1) {
      var cells = [String(y)];
      order.forEach(function (id) {
        var vals = scenarios[id].values || [];
        var nominal = vals.length > y ? vals[y] : null;
        var today = toTodaysDollars(nominal, y, currentInflationRate);
        var incomeNominal = nominal == null || isNaN(nominal) ? null : Number(nominal) * currentRetirementIncomeRate;
        var incomeToday = today == null || isNaN(today) ? null : Number(today) * currentRetirementIncomeRate;
        cells.push(rounded(nominal));
        cells.push(rounded(today));
        cells.push(rounded(incomeNominal));
        cells.push(rounded(incomeToday));
      });
      rows.push(cells.join(','));
    }
    if (lastPlansData && lastPlansData.plans) {
      var plans = lastPlansData.plans || {};
      var planOrder = planOrderFromData(lastPlansData);
      if (planOrder.length) {
        var planMaxYear = 0;
        planOrder.forEach(function (pid) {
          var p = plans[pid] || {};
          var ys = p.years || [];
          if (ys.length) planMaxYear = Math.max(planMaxYear, ys[ys.length - 1]);
        });
        rows.push('');
        rows.push('Combined plans');
        var planHeaders = ['Years'];
        planOrder.forEach(function (pid) {
          var name = ((plans[pid] || {}).name || pid).replace(/,/g, ';');
          planHeaders.push(name + ' (nominal)');
          planHeaders.push(name + ' (today$)');
          planHeaders.push(name + ' (income nominal)');
          planHeaders.push(name + ' (income today$)');
        });
        rows.push(planHeaders.join(','));
        for (var py = 1; py <= planMaxYear; py += 1) {
          var planCells = [String(py)];
          planOrder.forEach(function (pid) {
            var p = plans[pid] || {};
            var nominal = (p.values && p.values.length > py) ? p.values[py] : null;
            var today = toTodaysDollars(nominal, py, currentInflationRate);
            var incomeNominal = nominal == null || isNaN(nominal) ? null : Number(nominal) * currentRetirementIncomeRate;
            var incomeToday = today == null || isNaN(today) ? null : Number(today) * currentRetirementIncomeRate;
            planCells.push(rounded(nominal));
            planCells.push(rounded(today));
            planCells.push(rounded(incomeNominal));
            planCells.push(rounded(incomeToday));
          });
          rows.push(planCells.join(','));
        }
      }
    }
    var csv = rows.join('\n');
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'benchmark_years.csv';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function exportMonteCarloCsv() {
    if (!lastMcData || !lastMcData.scenarios || !lastMcData.benchmark_years || !lastMcData.benchmark_years.length) {
      showError('Update projections first to export Monte Carlo data.');
      return;
    }
    var scenarios = lastMcData.scenarios || {};
    var order = scenarioList.map(function (s) { return s.id; }).filter(function (id) { return scenarios[id]; });
    if (!order.length) return;
    var finalBenchmarkYear = Math.max.apply(null, lastMcData.benchmark_years);
    if (!isFinite(finalBenchmarkYear) || finalBenchmarkYear < 0) return;

    function rounded(n) {
      if (n == null || isNaN(n)) return '';
      return String(Math.round(Number(n)));
    }

    function seriesAtYear(sc, key, y) {
      var arr = sc[key];
      if (arr && arr.length > y) return arr[y];
      if (key === 'median' && sc.values && sc.values.length > y) return sc.values[y];
      return null;
    }

    var headers = ['Years'];
    order.forEach(function (id) {
      var name = (scenarios[id].name || id).replace(/,/g, ';');
      headers.push(name + ' (nominal median)');
      headers.push(name + ' (today$ median)');
      headers.push(name + ' (income nominal median)');
      headers.push(name + ' (income today$ median)');
      headers.push(name + ' (p75-p25)');
      headers.push(name + ' (p25/median)');
      headers.push(name + ' (p10)');
      headers.push(name + ' (ES)');
    });

    var rows = [headers.join(',')];
    for (var y = 0; y <= finalBenchmarkYear; y += 1) {
      var cells = [String(y)];
      order.forEach(function (id) {
        var sc = scenarios[id] || {};
        var nominalMedian = seriesAtYear(sc, 'median', y);
        var todayMedian = toTodaysDollars(nominalMedian, y, currentInflationRate);
        var incomeNominalMedian = nominalMedian == null || isNaN(nominalMedian) ? null : Number(nominalMedian) * currentRetirementIncomeRate;
        var incomeTodayMedian = todayMedian == null || isNaN(todayMedian) ? null : Number(todayMedian) * currentRetirementIncomeRate;
        var p25 = seriesAtYear(sc, 'p25', y);
        var p75 = seriesAtYear(sc, 'p75', y);
        var p10 = seriesAtYear(sc, 'p10', y);
        var es = seriesAtYear(sc, 'es', y);
        var spread = (p75 == null || isNaN(p75) || p25 == null || isNaN(p25)) ? null : Number(p75) - Number(p25);
        var ratio = (nominalMedian == null || isNaN(nominalMedian) || nominalMedian === 0 || p25 == null || isNaN(p25))
          ? null
          : Number(p25) / Number(nominalMedian);
        cells.push(rounded(nominalMedian));
        cells.push(rounded(todayMedian));
        cells.push(rounded(incomeNominalMedian));
        cells.push(rounded(incomeTodayMedian));
        cells.push(rounded(spread));
        cells.push(ratio == null || isNaN(ratio) ? '' : (ratio * 100).toFixed(2) + '%');
        cells.push(rounded(p10));
        cells.push(rounded(es));
      });
      rows.push(cells.join(','));
    }

    var csv = rows.join('\n');
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'monte_carlo_medians_yearly.csv';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function exportPlanCsv() {
    if (!lastPlansData || !lastPlansData.plans) {
      showError('Update projections first to export combined plan data.');
      return;
    }
    var plans = lastPlansData.plans || {};
    var order = planOrderFromData(lastPlansData);
    if (!order.length) return;
    var maxYear = 0;
    order.forEach(function (pid) {
      var p = plans[pid] || {};
      var years = p.years || [];
      if (years.length) maxYear = Math.max(maxYear, years[years.length - 1]);
    });
    function rounded(n) {
      if (n == null || isNaN(n)) return '';
      return String(Math.round(Number(n)));
    }
    var headers = ['Years'];
    order.forEach(function (pid) {
      var name = ((plans[pid] || {}).name || pid).replace(/,/g, ';');
      headers.push(name + ' (det)');
      headers.push(name + ' (mc_median)');
      headers.push(name + ' (mc_p25)');
      headers.push(name + ' (mc_p75)');
    });
    var rows = [headers.join(',')];
    for (var y = 0; y <= maxYear; y += 1) {
      var cells = [String(y)];
      order.forEach(function (pid) {
        var p = plans[pid] || {};
        cells.push(rounded((p.values || [])[y]));
        cells.push(rounded((p.median || [])[y]));
        cells.push(rounded((p.p25 || [])[y]));
        cells.push(rounded((p.p75 || [])[y]));
      });
      rows.push(cells.join(','));
    }
    var csv = rows.join('\n');
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'combined_plans_yearly.csv';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function exportPlanMonteCarloCsv() {
    if (!lastPlansData || !lastPlansData.plans || !lastPlansData.benchmark_years || !lastPlansData.benchmark_years.length) {
      showError('Update projections first to export combined plan Monte Carlo data.');
      return;
    }
    var plans = lastPlansData.plans || {};
    var order = planOrderFromData(lastPlansData);
    if (!order.length) return;
    var finalBenchmarkYear = Math.max.apply(null, lastPlansData.benchmark_years || []);
    if (!isFinite(finalBenchmarkYear) || finalBenchmarkYear < 0) return;

    function rounded(n) {
      if (n == null || isNaN(n)) return '';
      return String(Math.round(Number(n)));
    }

    function seriesAtYear(p, key, y) {
      var arr = p[key];
      if (arr && arr.length > y) return arr[y];
      return null;
    }

    var headers = ['Years'];
    order.forEach(function (pid) {
      var name = ((plans[pid] || {}).name || pid).replace(/,/g, ';');
      headers.push(name + ' (nominal median)');
      headers.push(name + ' (today$ median)');
      headers.push(name + ' (income nominal median)');
      headers.push(name + ' (income today$ median)');
      headers.push(name + ' (p25)');
      headers.push(name + ' (p75)');
      headers.push(name + ' (p75-p25)');
      headers.push(name + ' (p25/median)');
      headers.push(name + ' (p10)');
      headers.push(name + ' (ES)');
    });

    var rows = [headers.join(',')];
    for (var y = 0; y <= finalBenchmarkYear; y += 1) {
      var cells = [String(y)];
      order.forEach(function (pid) {
        var p = plans[pid] || {};
        var med = seriesAtYear(p, 'median', y);
        var p25 = seriesAtYear(p, 'p25', y);
        var p75 = seriesAtYear(p, 'p75', y);
        var p10 = seriesAtYear(p, 'p10', y);
        var es = seriesAtYear(p, 'es', y);
        var today = toTodaysDollars(med, y, currentInflationRate);
        var incomeNominal = med == null || isNaN(med) ? null : Number(med) * currentRetirementIncomeRate;
        var incomeToday = today == null || isNaN(today) ? null : Number(today) * currentRetirementIncomeRate;
        var spread = (p75 == null || isNaN(p75) || p25 == null || isNaN(p25)) ? null : Number(p75) - Number(p25);
        var ratio = (med == null || isNaN(med) || med === 0 || p25 == null || isNaN(p25)) ? null : Number(p25) / Number(med);
        cells.push(rounded(med));
        cells.push(rounded(today));
        cells.push(rounded(incomeNominal));
        cells.push(rounded(incomeToday));
        cells.push(rounded(p25));
        cells.push(rounded(p75));
        cells.push(rounded(spread));
        cells.push(ratio == null || isNaN(ratio) ? '' : (ratio * 100).toFixed(2) + '%');
        cells.push(rounded(p10));
        cells.push(rounded(es));
      });
      rows.push(cells.join(','));
    }

    var csv = rows.join('\n');
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'combined_plans_monte_carlo_yearly.csv';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function renderPlanMCBenchmarkTable(data) {
    var el = $('planMcBenchmarkTable');
    if (!el) return;
    if (!data || !data.plans) {
      el.innerHTML = '<span class="loading">Update projections to see combined plan Monte Carlo medians.</span>';
      return;
    }
    var planIds = planOrderFromData(data);
    var years = data.benchmark_years || [];
    if (!planIds.length || !years.length) {
      el.innerHTML = '<span class="loading">No plan data available.</span>';
      return;
    }
    var showRiskCols = !!$('planMcShowRiskColumns')?.checked;
    var html = '<table><thead><tr><th>Years</th>';
    planIds.forEach(function (pid) {
      var p = data.plans[pid] || {};
      var name = p.name || pid;
      html += '<th>' + name + ' (med)</th>';
      if (showRiskCols) {
        html += '<th>' + name + ' (p75-p25)</th>';
        html += '<th>' + name + ' (p25/med)</th>';
        html += '<th>' + name + ' (p10)</th>';
        html += '<th>' + name + ' (ES)</th>';
      }
    });
    var retireEndYear = Number($('drawdown_end_year')?.value);
    html += '</tr></thead><tbody>';
    years.forEach(function (y) {
      var label = (isFinite(retireEndYear) && y === retireEndYear) ? y + ' (retire)' : String(y);
      html += '<tr><td>' + label + '</td>';
      planIds.forEach(function (pid) {
        var p = data.plans[pid] || {};
        var med = (p.median && p.median.length > y) ? p.median[y] : (p.values_at_benchmark || {})[y];
        var p25 = (p.p25_at_benchmark || {})[y];
        var p75 = (p.p75_at_benchmark || {})[y];
        var p10 = (p.p10_at_benchmark || {})[y];
        var es = (p.es_at_benchmark || {})[y];
        html += '<td class="num">' + nominalTodayHtml(med, y) + '</td>';
        if (showRiskCols) {
          var spread = (p75 == null || p25 == null) ? null : Number(p75) - Number(p25);
          var ratio = (med == null || !isFinite(med) || med === 0 || p25 == null) ? null : Number(p25) / Number(med);
          html += '<td class="num">' + formatCurrency(spread) + '</td>';
          html += '<td class="num">' + (ratio == null || isNaN(ratio) ? '—' : (ratio * 100).toFixed(1) + '%') + '</td>';
          html += '<td class="num">' + formatCurrency(p10) + '</td>';
          html += '<td class="num">' + formatCurrency(es) + '</td>';
        }
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  }

  function applyDefaultsToForm(d) {
    if (!d) return;
    var set = function (id, val) {
      var el = $(id);
      if (el && val != null) el.value = val;
    };
    set('home_value_today', d.home_value_today);
    set('years_live_in_before_sale', d.years_live_in_before_sale);
    set('selling_costs_pct', d.selling_costs_pct != null ? Math.round(d.selling_costs_pct * 100) : 6);
    set('pct_cash_reserve', d.pct_cash_reserve != null ? Math.round(d.pct_cash_reserve * 100) : 23);
    set('mc_n_paths', d.mc_n_paths);
    set('stock_return_mean', d.stock_return_mean != null ? Math.round(d.stock_return_mean * 100) : 8);
    set('stock_return_std', d.stock_return_std != null ? Math.round(d.stock_return_std * 100) : 17);
    set('stock_profile_preset', d.stock_profile_preset != null ? d.stock_profile_preset : 'overall_stock');
    customStockAssets = normalizeCustomStockAssets(d.custom_stock_assets || []);
    if (!customStockAssets.length) {
      customStockAssets = [{
        name: 'Asset 1',
        weight: 1.0,
        mean: d.stock_return_mean != null ? d.stock_return_mean : 0.08,
        std: d.stock_return_std != null ? d.stock_return_std : 0.17
      }];
    }
    applyGlobalStockProfileDefaults();
    set('house_return_mean', d.house_return_mean != null ? d.house_return_mean * 100 : 1);
    set('house_return_std', d.house_return_std != null ? Math.round(d.house_return_std * 100) : 8);
    set('withdrawal_start_year', d.withdrawal_start_year);
    set('withdrawal_rate', d.withdrawal_rate != null ? Math.round(d.withdrawal_rate * 100 * 100) / 100 : 2);
    set('inheritance_portfolio_today', d.inheritance_portfolio_today);
    set('inheritance_years_until_receipt', d.inheritance_years_until_receipt);
    set('inheritance_growth_rate', d.inheritance_growth_rate != null ? d.inheritance_growth_rate * 100 : 4.5);
    set('inheritance_return_mean', d.inheritance_return_mean != null ? Math.round(d.inheritance_return_mean * 100) : 5);
    set('inheritance_return_std', d.inheritance_return_std != null ? Math.round(d.inheritance_return_std * 100) : 14);
    if (d.inheritance_beneficiary_share != null && d.inheritance_beneficiary_share > 0) {
      set('inheritance_beneficiary_n', Math.round(1 / d.inheritance_beneficiary_share));
    } else {
      set('inheritance_beneficiary_n', 3);
    }
    $('include_scenario_4').checked = d.include_scenario_4 !== false;
    set('roth_balance_today', d.roth_balance_today);
    set('roth_annual_contribution', d.roth_annual_contribution != null ? d.roth_annual_contribution : 7500);
    set('roth_contribution_years', d.roth_contribution_years);
    set('investment_return_rate', d.investment_return_rate != null ? Math.round(d.investment_return_rate * 100 * 100) / 100 : 7);
    set('other_house_value_today', d.other_house_value_today);
    set('other_house_mortgage_remaining', d.other_house_mortgage_remaining);
    set('other_house_mortgage_payoff_years', d.other_house_mortgage_payoff_years);
    set('inflation_rate', d.inflation_rate != null ? Math.round(d.inflation_rate * 1000) / 10 : 3);
    if ($('enable_stochastic_inflation')) $('enable_stochastic_inflation').checked = !!d.enable_stochastic_inflation;
    set('inflation_return_mean', d.inflation_return_mean != null ? Math.round(d.inflation_return_mean * 1000) / 10 : 3.0);
    set('inflation_return_std', d.inflation_return_std != null ? Math.round(d.inflation_return_std * 1000) / 10 : 1.5);
    if ($('enable_correlation')) $('enable_correlation').checked = !!d.enable_correlation;
    set('correlation_preset', d.correlation_preset != null ? d.correlation_preset : 'balanced');
    set('bond_return_mean', d.bond_return_mean != null ? Math.round(d.bond_return_mean * 1000) / 10 : 4.5);
    set('bond_return_std', d.bond_return_std != null ? Math.round(d.bond_return_std * 1000) / 10 : 8.0);
    set('retirement_income_rate', d.retirement_income_rate != null ? Math.round(d.retirement_income_rate * 1000) / 10 : 4.5);
    set('es_tail_pct', d.es_tail_pct != null ? Math.round(d.es_tail_pct * 1000) / 10 : 5.0);
    if ($('drawdown_enabled')) $('drawdown_enabled').checked = true;
    set('drawdown_start_year', 35);
    set('drawdown_end_year', 70);
    set('drawdown_spending_today', 100000);
    set('drawdown_replacement_income_today', 100000);
    set('drawdown_safe_withdrawal_rate', d.retirement_income_rate != null ? Math.round(d.retirement_income_rate * 1000) / 10 : 5);
    set('drawdown_success_threshold', 90);
    set('drawdown_inflation_mode', 'flat');
    set('drawdown_coast_growth_rate', d.stock_return_mean != null ? Math.round(d.stock_return_mean * 1000) / 10 : 8.0);
    set('drawdown_target_terminal_fraction', 0);
    set('ss_start_year', 36);
    set('ss_amount_today', 36000);
    if (d.benchmark_years && Array.isArray(d.benchmark_years)) {
      set('benchmark_years', d.benchmark_years.join(', '));
    }
    renderCustomStockAssets();
    updateCorrelationPresetTooltip();
    bindSliders();
  }

  function resetToDefaults() {
    showError('');
    scenarioList = [];
    planList = [];
    lastMcData = null;
    lastPlansData = null;
    lastDrawdownData = null;
    lastSpendingSensitivity = null;
    if (chartPlanTrajectories) {
      chartPlanTrajectories.destroy();
      chartPlanTrajectories = null;
    }
    if (chartPlanMC) {
      chartPlanMC.destroy();
      chartPlanMC = null;
    }
    if (chartDrawdownShortfall) {
      chartDrawdownShortfall.destroy();
      chartDrawdownShortfall = null;
    }
    if (chartDrawdownBalance) {
      chartDrawdownBalance.destroy();
      chartDrawdownBalance = null;
    }
    if (chartDrawdownScan) {
      chartDrawdownScan.destroy();
      chartDrawdownScan = null;
    }
    if (chartDrawdownImpact) {
      chartDrawdownImpact.destroy();
      chartDrawdownImpact = null;
    }
    var drawdownYearlyEl = document.getElementById('drawdownYearlyTables');
    if (drawdownYearlyEl) drawdownYearlyEl.innerHTML = '<span class="loading">Update projections to see drawdown by year.</span>';
    renderSpendingSensitivityTable();
    renderScenarioList();
    renderPlanList();
    renderDrawdownSummary(null);
    renderSustainableWithdrawalSummary(null);
    buildSustainableWithdrawalChart(null);
    setLoading(true, 'Loading defaults…');
    fetch(API + '/api/defaults')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        applyDefaultsToForm(data);
        renderAssumptionsBanner(collectParams());
        setLoading(false);
      })
      .catch(function (e) {
        showError(e.message || 'Could not load defaults.');
        setLoading(false);
      });
  }

  function startBrowserHeartbeat() {
    function ping() {
      fetch(API + '/api/ping', {
        method: 'POST',
        keepalive: true
      }).catch(function () { /* best effort only */ });
    }
    ping();
    setInterval(ping, 5000);
  }

  function updateProjections() {
    showError('');
    var btn = $('btnUpdate');
    if (btn) btn.disabled = true;
    setLoading(true, 'Updating projections…');
    var globalParams = collectParams();
    var drawdown = collectDrawdownParams(globalParams);
    currentInflationRate = globalParams.inflation_rate || 0.03;
    currentRetirementIncomeRate = globalParams.retirement_income_rate || 0.045;
    currentEsTailPct = globalParams.es_tail_pct || 0.05;
    renderAssumptionsBanner(globalParams);
    var scenarios = collectScenarios();
    var plans = collectPlans();
    if (!scenarios.length) {
      showError('Add at least one scenario.');
      setLoading(false);
      if (btn) btn.disabled = false;
      return;
    }
    if (scenarios.length > MAX_SCENARIOS) {
      showError('Too many scenarios. Maximum allowed is ' + MAX_SCENARIOS + '.');
      setLoading(false);
      if (btn) btn.disabled = false;
      return;
    }

    fetch(API + '/api/scenarios', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ global_params: globalParams, scenarios: scenarios })
    })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || r.statusText); return j; }); })
      .then(function (data) {
        lastScenariosData = data;
        renderSaleBreakdown(data);
        renderBenchmarkTable(data);
        buildTrajectoryChart(data);
        setLoading(true, 'Running Monte Carlo…');
        return runScenarioMonteCarlo(globalParams, scenarios);
      })
      .then(function (mcData) {
        if (mcData && mcData.meta && mcData.meta.inflation_report_rate != null) {
          currentInflationRate = Number(mcData.meta.inflation_report_rate) || currentInflationRate;
        }
        lastMcData = mcData;
        buildMCChart(mcData);
        renderMCBenchmarkTable(mcData);
        return fetch(API + '/api/plans', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ global_params: globalParams, components: scenarios, plans: plans, drawdown: drawdown })
        }).then(function (r) {
          return r.json().then(function (j) { if (!r.ok || j.error) throw new Error(j.error || r.statusText); return j; });
        });
      })
      .then(function (planData) {
        if (planData && planData.meta && planData.meta.inflation_report_rate != null) {
          currentInflationRate = Number(planData.meta.inflation_report_rate) || currentInflationRate;
        }
        lastPlansData = planData;
        renderCombinedPlanTable(planData);
        buildPlanTrajectoryChart(planData);
        buildPlanMCChart(planData);
        renderPlanMCBenchmarkTable(planData);
        setLoading(true, 'Running drawdown analysis…');
        return fetch(API + '/api/drawdown', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ global_params: globalParams, components: scenarios, plans: plans, drawdown: drawdown })
        }).then(function (r) {
          return r.json().then(function (j) { if (!r.ok || j.error) throw new Error(j.error || r.statusText); return j; });
        });
      })
      .then(function (drawdownData) {
        lastDrawdownData = drawdownData;
        renderDrawdownSummary(drawdownData);
        renderSustainableWithdrawalSummary(drawdownData);
        buildSustainableWithdrawalChart(drawdownData);
        renderDrawdownYearlyTables(drawdownData);
        buildDrawdownShortfallChart(drawdownData);
        buildDrawdownBalanceChart(drawdownData);
        buildDrawdownScanChart(drawdownData);
        buildDrawdownImpactChart();
        if (lastPlansData) buildPlanMCChart(lastPlansData);
        setLoading(true, 'Running spending sensitivity…');
        return runSpendingSensitivity();
      })
      .catch(function (e) {
        showError(e.message || 'Something went wrong.');
      })
      .finally(function () {
        setLoading(false);
        if (btn) btn.disabled = false;
      });
  }

  $('btnUpdate').addEventListener('click', updateProjections);
  $('btnReset').addEventListener('click', resetToDefaults);
  if ($('btnAddPlan')) $('btnAddPlan').addEventListener('click', addPlan);
  $('btnExportCsv').addEventListener('click', exportBenchmarkCsv);
  if ($('btnExportMcCsv')) $('btnExportMcCsv').addEventListener('click', exportMonteCarloCsv);
  if ($('btnExportPlanCsv')) $('btnExportPlanCsv').addEventListener('click', exportPlanCsv);
  if ($('btnExportPlanMcCsv')) $('btnExportPlanMcCsv').addEventListener('click', exportPlanMonteCarloCsv);
  if ($('mcShowRiskColumns')) {
    $('mcShowRiskColumns').addEventListener('change', function () {
      if (lastMcData) renderMCBenchmarkTable(lastMcData);
    });
  }
  if ($('planMcShowRiskColumns')) {
    $('planMcShowRiskColumns').addEventListener('change', function () {
      if (lastPlansData) renderPlanMCBenchmarkTable(lastPlansData);
    });
  }
  if ($('stock_profile_preset')) {
    $('stock_profile_preset').addEventListener('change', function () {
      applyGlobalStockProfileDefaults();
      renderCustomStockAssets();
    });
  }
  if ($('btnAddCustomStockAsset')) {
    $('btnAddCustomStockAsset').addEventListener('click', addCustomStockAsset);
  }
  if ($('correlation_preset')) {
    $('correlation_preset').addEventListener('change', updateCorrelationPresetTooltip);
  }

  var btnAdd = $('btnAddScenario');
  var addMenu = $('addScenarioMenu');
  if (btnAdd) {
    btnAdd.addEventListener('click', function (e) {
      e.stopPropagation();
      if (addMenu && addMenu.classList.contains('is-open')) closeAddMenu();
      else openAddMenu();
    });
  }
  if (addMenu) {
    addMenu.querySelectorAll('[role="menuitem"]').forEach(function (btn) {
      btn.addEventListener('click', function (e) { e.stopPropagation(); addScenarioFromTemplate(btn.getAttribute('data-type')); });
    });
  }
  document.addEventListener('click', function () { closeAddMenu(); });

  var editModal = $('editScenarioModal');
  var editBackdrop = $('editScenarioModalBackdrop');
  var editCancel = $('editScenarioCancel');
  var editSave = $('editScenarioSave');
  if (editBackdrop) editBackdrop.addEventListener('click', closeEditModal);
  if (editCancel) editCancel.addEventListener('click', closeEditModal);
  if (editSave) editSave.addEventListener('click', function () { saveEditModal(); });

  bindSliders();
  applyGlobalStockProfileDefaults();
  renderCustomStockAssets();
  updateCorrelationPresetTooltip();
  setupTabs();
  setupBudgetTab();
  renderScenarioList();
  renderPlanList();
  renderDrawdownSummary(null);
  renderSustainableWithdrawalSummary(null);
  buildSustainableWithdrawalChart(null);
  startBrowserHeartbeat();

  if (scenarioList.length > 0) updateProjections();
})();
