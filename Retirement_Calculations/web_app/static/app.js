(function () {
  'use strict';

  const API = '';
  let chartTrajectories = null;
  let chartMC = null;
  let lastScenariosData = null;
  let lastMcData = null;
  let currentInflationRate = 0.03;
  let currentRetirementIncomeRate = 0.045;
  let currentEsTailPct = 0.05;

  var SCENARIO_TEMPLATES = {
    keep_property: 'Keep property (appreciation only)',
    sell_invest: 'Sell and invest house proceeds',
    sell_invest_withdrawals: 'Sell and invest + withdrawals',
    inheritance_only: 'Inheritance (projected value)',
    roth: 'Roth IRA growth',
    other_property: 'Other property equity'
  };

  var SCENARIO_TYPES = SCENARIO_TEMPLATES;

  function nextId() { return 's' + Date.now() + '_' + Math.random().toString(36).slice(2, 8); }

  var scenarioList = [];
  var editingScenarioId = null;

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
    if (p.stock_return_mean != null) chips.push('\u03bcstock ' + formatPct(p.stock_return_mean, 1));
    if (p.stock_return_std != null) chips.push('\u03c3stock ' + formatPct(p.stock_return_std, 1));
    if (p.use_fat_tails != null) chips.push('Fat-tail ' + (p.use_fat_tails ? 'ON' : 'OFF'));
    if (p.use_fat_tails && p.fat_tail_df != null) chips.push('df ' + Number(p.fat_tail_df).toFixed(1));
    if (p.withdrawal_rate != null && sc.type === 'sell_invest_withdrawals') chips.push('w/d ' + formatPct(p.withdrawal_rate, 2));
    return chips;
  }

  function parseBenchmarkYears(str) {
    if (!str || typeof str !== 'string') return [7, 12, 17, 35];
    return str.split(/[\s,]+/).map(function (s) { return parseInt(s, 10); }).filter(function (n) { return !isNaN(n) && n >= 0; });
  }

  function collectParams() {
    const pctCash = Number($('pct_cash_reserve').value) / 100;
    const nBenef = Number($('inheritance_beneficiary_n').value) || 3;
    const benchmarkInput = $('benchmark_years');
    const benchmarkYears = benchmarkInput ? parseBenchmarkYears(benchmarkInput.value) : [7, 12, 17, 35];
    return {
      home_value_today: Number($('home_value_today').value),
      years_live_in_before_sale: Number($('years_live_in_before_sale').value),
      home_appreciation_rate: Number($('home_appreciation_rate')?.value) / 100 || 0.004,
      selling_costs_pct: Number($('selling_costs_pct').value) / 100,
      pct_cash_reserve: pctCash,
      pct_invest: 1 - pctCash,
      mc_n_paths: Number($('mc_n_paths').value),
      use_fat_tails: false,
      fat_tail_df: 5,
      stock_return_mean: Number($('stock_return_mean').value) / 100,
      stock_return_std: Number($('stock_return_std').value) / 100,
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
      retirement_income_rate: Number($('retirement_income_rate')?.value) / 100 || 0.045,
      es_tail_pct: Number($('es_tail_pct')?.value) / 100 || 0.05,
      roth_balance_today: Number($('roth_balance_today').value),
      roth_annual_contribution: Number($('roth_annual_contribution').value),
      roth_contribution_years: Number($('roth_contribution_years').value),
      investment_return_rate: Number($('investment_return_rate').value) / 100,
      other_house_value_today: Number($('other_house_value_today').value),
      other_house_mortgage_remaining: Number($('other_house_mortgage_remaining').value),
      other_house_mortgage_payoff_years: Number($('other_house_mortgage_payoff_years').value),
      other_house_appreciation_rate: 0.004
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
      { key: 'fat_tail_df', label: 'Tail heaviness (df)', type: 'number', min: 2.5, max: 30, step: 0.5 }
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
      { key: 'use_fat_tails', label: 'Use fat-tail returns', type: 'boolean' },
      { key: 'fat_tail_df', label: 'Tail heaviness (df)', type: 'number', min: 2.5, max: 30, step: 0.5 }
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
      { key: 'use_fat_tails', label: 'Use fat-tail returns', type: 'boolean' },
      { key: 'fat_tail_df', label: 'Tail heaviness (df)', type: 'number', min: 2.5, max: 30, step: 0.5 }
    ],
    inheritance_only: [
      { key: 'inheritance_portfolio_today', label: 'Estate portfolio value today ($)', type: 'number', min: 0, step: 100000 },
      { key: 'inheritance_years_until_receipt', label: 'Years until receipt', type: 'number', min: 1, max: 50 },
      { key: 'inheritance_beneficiary_share', label: 'Your share (1/n, e.g. 0.333 for 1/3)', type: 'number', min: 0.01, max: 1, step: 0.01 },
      { key: 'inheritance_growth_rate', label: 'Estate growth until receipt (%)', type: 'percent', min: 0, max: 15 },
      { key: 'inheritance_return_mean', label: 'Inheritance MC return mean (%)', type: 'percent', min: 0, max: 12 },
      { key: 'inheritance_return_std', label: 'Inheritance MC return std (%)', type: 'percent', min: 0, max: 30 },
      { key: 'use_fat_tails', label: 'Use fat-tail returns', type: 'boolean' },
      { key: 'fat_tail_df', label: 'Tail heaviness (df)', type: 'number', min: 2.5, max: 30, step: 0.5 }
    ],
    roth: [
      { key: 'roth_balance_today', label: 'Roth balance today ($)', type: 'number', min: 0, step: 500 },
      { key: 'roth_annual_contribution', label: 'Annual contribution ($)', type: 'number', min: 0, step: 500 },
      { key: 'roth_contribution_years', label: 'Years of contributions', type: 'number', min: 0, max: 50 },
      { key: 'investment_return_rate', label: 'Investment return (%)', type: 'percent', min: 0, max: 20 },
      { key: 'stock_return_mean', label: 'Stock return mean (%)', type: 'percent', min: 0, max: 15 },
      { key: 'stock_return_std', label: 'Stock return std (%)', type: 'percent', min: 5, max: 40 },
      { key: 'use_fat_tails', label: 'Use fat-tail returns', type: 'boolean' },
      { key: 'fat_tail_df', label: 'Tail heaviness (df)', type: 'number', min: 2.5, max: 30, step: 0.5 }
    ],
    other_property: [
      { key: 'other_house_value_today', label: 'Property value today ($)', type: 'number', min: 0, step: 1000 },
      { key: 'other_house_mortgage_remaining', label: 'Mortgage remaining ($)', type: 'number', min: 0, step: 1000 },
      { key: 'other_house_mortgage_payoff_years', label: 'Years to pay off mortgage', type: 'number', min: 0.5, max: 40, step: 0.5 },
      { key: 'other_house_appreciation_rate', label: 'Appreciation rate (%)', type: 'percent', min: 0, max: 10 }
    ]
  };

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
      ['investment_return_rate', 0.25, '%']
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

  function renderScenarioList() {
    var emptyEl = $('scenarioListEmpty');
    var container = $('scenarioListCards');
    if (!container) return;
    var globalParams = collectParams();
    if (emptyEl) emptyEl.style.display = scenarioList.length ? 'none' : 'block';
    container.innerHTML = '';
    scenarioList.forEach(function (sc, idx) {
      var card = document.createElement('div');
      card.className = 'scenario-card';
      card.setAttribute('data-id', sc.id);
      var nameInput = document.createElement('input');
      nameInput.type = 'text';
      nameInput.className = 'name-input';
      nameInput.value = sc.name;
      nameInput.placeholder = 'Scenario name';
      nameInput.addEventListener('change', function () { sc.name = nameInput.value.trim() || SCENARIO_TEMPLATES[sc.type] || sc.type; });
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
        scenarioList.splice(idx + 1, 0, { id: nextId(), name: sc.name + ' (copy)', type: sc.type, params: JSON.parse(JSON.stringify(sc.params || {})) });
        renderScenarioList();
      });
      var remBtn = document.createElement('button');
      remBtn.type = 'button';
      remBtn.className = 'btn btn-secondary btn-icon';
      remBtn.textContent = 'Remove';
      remBtn.addEventListener('click', function () {
        scenarioList.splice(idx, 1);
        renderScenarioList();
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
    var name = SCENARIO_TEMPLATES[type] || type;
    var params = getDefaultParamsForType(type);
    var sc = { id: nextId(), name: name, type: type, params: params };
    scenarioList.push(sc);
    closeAddMenu();
    renderScenarioList();
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
    formEl.innerHTML = '';
    fields.forEach(function (f) {
      var val = scenario.params && scenario.params[f.key] !== undefined ? scenario.params[f.key] : global[f.key];
      if (f.type === 'percent' && typeof val === 'number' && Math.abs(val) <= 1 && val !== 0) val = val * 100;
      var div = document.createElement('div');
      div.className = f.type === 'boolean' ? 'form-group checkbox-row' : 'form-group';
      var label = document.createElement('label');
      label.textContent = f.label;
      label.setAttribute('for', 'edit_' + f.key);
      var input = document.createElement('input');
      input.id = 'edit_' + f.key;
      input.type = f.type === 'boolean' ? 'checkbox' : 'number';
      input.setAttribute('data-key', f.key);
      input.setAttribute('data-type', f.type || 'number');
      if (f.type === 'boolean') {
        input.checked = !!val;
        div.appendChild(input);
        div.appendChild(label);
      } else {
        if (f.min !== undefined) input.min = f.min;
        if (f.max !== undefined) input.max = f.max;
        if (f.step !== undefined) input.step = f.step;
        input.value = val == null ? '' : val;
        div.appendChild(label);
        div.appendChild(input);
      }
      formEl.appendChild(div);
    });
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
    var inputs = formEl.querySelectorAll('input[data-key]');
    sc.params = sc.params || {};
    inputs.forEach(function (input) {
      var key = input.getAttribute('data-key');
      var dataType = input.getAttribute('data-type');
      if (dataType === 'boolean') {
        sc.params[key] = !!input.checked;
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
    closeEditModal();
    renderScenarioList();
  }

  function collectScenarios() {
    return scenarioList.map(function (s) {
      return { id: s.id, name: s.name || SCENARIO_TYPES[s.type], type: s.type, params: s.params || {} };
    });
  }

  function setupTabs() {
    var tabIds = ['tabOverview', 'tabTrajectories', 'tabMC'];
    var panelIds = ['panelOverview', 'panelTrajectories', 'panelMC'];
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
    html += '</tr></thead><tbody>';
    years.forEach(function (y) {
      var label = y === 35 ? y + ' (retire)' : String(y);
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
    html += '</tr></thead><tbody>';
    years.forEach(function (y) {
      var label = y === 35 ? y + ' (retire)' : String(y);
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

  var CHART_COLORS = ['#22c55e', '#3b82f6', '#a855f7', '#14b8a6', '#f97316', '#eab308', '#ec4899', '#6366f1'];

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

  function applyDefaultsToForm(d) {
    if (!d) return;
    var set = function (id, val) {
      var el = $(id);
      if (el && val != null) el.value = val;
    };
    set('home_value_today', d.home_value_today);
    set('years_live_in_before_sale', d.years_live_in_before_sale);
    set('selling_costs_pct', d.selling_costs_pct != null ? Math.round(d.selling_costs_pct * 100) : 6);
    set('pct_cash_reserve', d.pct_cash_reserve != null ? Math.round(d.pct_cash_reserve * 100) : 25);
    set('mc_n_paths', d.mc_n_paths);
    set('stock_return_mean', d.stock_return_mean != null ? Math.round(d.stock_return_mean * 100) : 8);
    set('stock_return_std', d.stock_return_std != null ? Math.round(d.stock_return_std * 100) : 17);
    set('house_return_mean', d.house_return_mean != null ? d.house_return_mean * 100 : 0.5);
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
    set('roth_annual_contribution', d.roth_annual_contribution);
    set('roth_contribution_years', d.roth_contribution_years);
    set('investment_return_rate', d.investment_return_rate != null ? Math.round(d.investment_return_rate * 100 * 100) / 100 : 7);
    set('other_house_value_today', d.other_house_value_today);
    set('other_house_mortgage_remaining', d.other_house_mortgage_remaining);
    set('other_house_mortgage_payoff_years', d.other_house_mortgage_payoff_years);
    set('inflation_rate', d.inflation_rate != null ? Math.round(d.inflation_rate * 1000) / 10 : 3);
    set('retirement_income_rate', d.retirement_income_rate != null ? Math.round(d.retirement_income_rate * 1000) / 10 : 4.5);
    set('es_tail_pct', d.es_tail_pct != null ? Math.round(d.es_tail_pct * 1000) / 10 : 5.0);
    if (d.benchmark_years && Array.isArray(d.benchmark_years)) {
      set('benchmark_years', d.benchmark_years.join(', '));
    }
    bindSliders();
  }

  function resetToDefaults() {
    showError('');
    scenarioList = [];
    lastMcData = null;
    renderScenarioList();
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
    currentInflationRate = globalParams.inflation_rate || 0.03;
    currentRetirementIncomeRate = globalParams.retirement_income_rate || 0.045;
    currentEsTailPct = globalParams.es_tail_pct || 0.05;
    renderAssumptionsBanner(globalParams);
    var scenarios = collectScenarios();
    if (!scenarios.length) {
      showError('Add at least one scenario.');
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
        lastMcData = mcData;
        buildMCChart(mcData);
        renderMCBenchmarkTable(mcData);
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
  $('btnExportCsv').addEventListener('click', exportBenchmarkCsv);
  if ($('btnExportMcCsv')) $('btnExportMcCsv').addEventListener('click', exportMonteCarloCsv);
  if ($('mcShowRiskColumns')) {
    $('mcShowRiskColumns').addEventListener('change', function () {
      if (lastMcData) renderMCBenchmarkTable(lastMcData);
    });
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
  setupTabs();
  renderScenarioList();
  startBrowserHeartbeat();

  if (scenarioList.length > 0) updateProjections();
})();
