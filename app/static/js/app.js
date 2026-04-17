function dseApp() {
  return {
    theme: 'light',
    mainView: 'runs',
    runs: [], stats: {}, selectedRun: null, selectedRunDetail: null,
    records: [], loading: false, syncing: false,
    globalAnalysis: null, globalAnalysisLoading: false, globalAnalysisDirty: true, _globalAnalysisTimer: null,
    crossScenarioReports: [], crossScenarioReportsLoading: false, crossScenarioReportsLoaded: false,
    selectedCrossScenarioPath: '', selectedCrossScenarioReport: null, crossScenarioLoading: false,
    legacyReports: [], legacyReportsLoading: false, legacyReportsLoaded: false,
    selectedLegacyReportPath: '', legacyReportFrameSrc: '',
    tableCatalog: [], tableColumns: [], tableRows: [], tableLoading: false,
    tableCatalogLoaded: false,
    tableBrowser: { selected: 'opt_runs', q: '', limit: 50, offset: 0, total: 0 },
    showModal: false, activeTab: 'overview',
    filterQ: '', filterAlgo: '', filterSpace: '', filterGroup: '',
    showParetoOnly: false,
    selectedRecord: null, selectedEffectiveConfig: null, effectiveConfigLoading: false,
    selectedRunAnalysis: null, analysisLoading: false,
    _effectiveConfigCache: {},
    _crossScenarioCache: {},
    tabs: [
      { id: 'overview', label: '概览' },
      { id: 'analysis', label: '分析' },
      { id: 'records',  label: '评估记录' },
      { id: 'config',   label: '生效配置' },
      { id: 'scatter',  label: '散点图' },
    ],
    _charts: {},
    _globalCharts: {},

    async init() {
      this.theme = localStorage.getItem('mnsim-dse-theme') || 'light'
      this.loading = true
      await Promise.all([this.loadStats(), this.loadRuns()])
      this.loading = false
      // Redraw global charts whenever loading completes (catches timing edge-cases)
      this.$watch('globalAnalysisLoading', (loading) => {
        if (!loading && this.globalAnalysis && this.mainView === 'analysis') {
          this.$nextTick(() => this.drawGlobalCharts())
        }
      })
    },

    async loadStats() {
      const r = await fetch('/api/stats')
      this.stats = await r.json()
    },

    async loadRuns() {
      const r = await fetch('/api/runs')
      this.runs = await r.json()
    },

    buildRunFilterParams() {
      const params = new URLSearchParams()
      const q = this.filterQ.trim()
      if (q) params.set('q', q)
      if (this.filterAlgo) params.set('algo', this.filterAlgo)
      if (this.filterSpace) params.set('space', this.filterSpace)
      if (this.filterGroup) params.set('group', this.filterGroup)
      return params
    },

    queueGlobalAnalysisReload() {
      this.globalAnalysisDirty = true
      if (this.mainView !== 'analysis') return
      clearTimeout(this._globalAnalysisTimer)
      this._globalAnalysisTimer = setTimeout(() => this.loadGlobalAnalysis(), 250)
    },

    async loadGlobalAnalysis() {
      this.globalAnalysisLoading = true
      try {
        const r = await fetch('/api/analysis/global?' + this.buildRunFilterParams().toString())
        this.globalAnalysis = await r.json()
        this.globalAnalysisDirty = false
      } finally {
        this.globalAnalysisLoading = false
      }
      // Schedule chart draw AFTER both globalAnalysis and globalAnalysisLoading
      // have been committed, so the canvas container is already visible in DOM.
      this.$nextTick(() => this.drawGlobalCharts())
    },

    async loadCrossScenarioReports(force = false) {
      if (this.crossScenarioReportsLoaded && !force) {
        if (!this.selectedCrossScenarioReport && this.selectedCrossScenarioPath) {
          await this.openCrossScenarioReport(this.selectedCrossScenarioPath)
        }
        return
      }
      if (force) this._crossScenarioCache = {}
      this.crossScenarioReportsLoading = true
      try {
        const r = await fetch('/api/cross-scenario/reports')
        this.crossScenarioReports = await r.json()
        this.crossScenarioReportsLoaded = true
        if (!this.crossScenarioReports.length) {
          this.selectedCrossScenarioPath = ''
          this.selectedCrossScenarioReport = null
          return
        }
        if (!this.selectedCrossScenarioPath || !this.crossScenarioReports.some(report => report.relpath === this.selectedCrossScenarioPath)) {
          this.selectedCrossScenarioPath = this.crossScenarioReports[0].relpath
          this.selectedCrossScenarioReport = null
        }
      } finally {
        this.crossScenarioReportsLoading = false
      }
      if (this.selectedCrossScenarioPath) {
        await this.openCrossScenarioReport(this.selectedCrossScenarioPath)
      }
    },

    async openCrossScenarioReport(relpath) {
      if (!relpath) return
      this.selectedCrossScenarioPath = relpath
      if (this._crossScenarioCache[relpath]) {
        this.selectedCrossScenarioReport = this._crossScenarioCache[relpath]
        return
      }
      this.crossScenarioLoading = true
      try {
        const safePath = relpath.split('/').map(part => encodeURIComponent(part)).join('/')
        const r = await fetch(`/api/cross-scenario/reports/${safePath}`)
        if (!r.ok) {
          this.selectedCrossScenarioReport = null
          return
        }
        const d = await r.json()
        this._crossScenarioCache[relpath] = d
        this.selectedCrossScenarioReport = d
      } finally {
        this.crossScenarioLoading = false
      }
    },

    async setMainView(view) {
      this.mainView = view
      if (view === 'analysis' && (this.globalAnalysisDirty || !this.globalAnalysis)) {
        await this.loadGlobalAnalysis()
      }
      if (view === 'crossScenario') {
        if (!this.crossScenarioReportsLoaded) {
          await this.loadCrossScenarioReports()
        } else if (!this.selectedCrossScenarioReport && this.selectedCrossScenarioPath) {
          await this.openCrossScenarioReport(this.selectedCrossScenarioPath)
        }
      }
      if (view === 'legacyReport' && !this.legacyReportsLoaded) {
        await this.loadLegacyReports()
      }
      if (view === 'database' && !this.tableCatalogLoaded) {
        await this.loadTables()
      }
    },

    async loadLegacyReports(force = false) {
      if (this.legacyReportsLoaded && !force) return
      this.legacyReportsLoading = true
      try {
        const r = await fetch('/api/legacy-analysis/reports')
        this.legacyReports = await r.json()
        this.legacyReportsLoaded = true
        if (!this.selectedLegacyReportPath && this.legacyReports.length) {
          this.selectedLegacyReportPath = this.legacyReports[0].relpath
        } else if (this.selectedLegacyReportPath && !this.legacyReports.some(report => report.relpath === this.selectedLegacyReportPath)) {
          this.selectedLegacyReportPath = this.legacyReports[0]?.relpath || ''
        }
        this.updateLegacyReportFrame()
      } finally {
        this.legacyReportsLoading = false
      }
    },

    updateLegacyReportFrame() {
      this.legacyReportFrameSrc = this.selectedLegacyReportPath
        ? `/legacy-analysis/${this.selectedLegacyReportPath}`
        : ''
    },

    async loadTables() {
      const r = await fetch('/api/db/tables')
      this.tableCatalog = await r.json()
      this.tableCatalogLoaded = true
      if (!this.tableCatalog.length) {
        this.tableColumns = []
        this.tableRows = []
        this.tableBrowser.total = 0
        return
      }
      if (!this.tableCatalog.some(t => t.name === this.tableBrowser.selected)) {
        this.tableBrowser.selected = this.tableCatalog[0].name
      }
      await this.loadTableRows(true)
    },

    async loadTableRows(reset = false) {
      if (!this.tableBrowser.selected) return
      if (reset) this.tableBrowser.offset = 0
      this.tableLoading = true
      const params = new URLSearchParams({
        limit: String(this.tableBrowser.limit),
        offset: String(this.tableBrowser.offset),
      })
      const q = this.tableBrowser.q.trim()
      if (q) params.set('q', q)
      const r = await fetch(`/api/db/tables/${this.tableBrowser.selected}?` + params)
      const d = await r.json()
      this.tableColumns = d.columns || []
      this.tableRows = d.rows || []
      this.tableBrowser.total = d.total || 0
      this.tableLoading = false
    },

    async loadEffectiveConfig(rec) {
      if (!rec?.record_id) return
      this.selectedRecord = rec
      if (this._effectiveConfigCache[rec.record_id]) {
        this.selectedEffectiveConfig = this._effectiveConfigCache[rec.record_id]
        return
      }
      this.selectedEffectiveConfig = null
      this.effectiveConfigLoading = true
      try {
        const r = await fetch(`/api/records/${rec.record_id}/effective_config`)
        const d = await r.json()
        this._effectiveConfigCache[rec.record_id] = d
        this.selectedEffectiveConfig = d
      } finally {
        this.effectiveConfigLoading = false
      }
    },

    async selectRecord(rec, switchTab = false) {
      if (switchTab) this.setActiveTab('config')
      await this.loadEffectiveConfig(rec)
    },

    async openAnalysisRecord(recordId) {
      const rec = this.records.find(item => item.record_id === recordId)
      if (!rec) return
      await this.selectRecord(rec, true)
    },

    async openGlobalAnalysisRecord(row) {
      const run = this.runs.find(item => item.id === row.run_id)
      if (!run) return
      await this.openRun(run)
      await this.openAnalysisRecord(row.record_id)
    },

    setActiveTab(tabId) {
      this.activeTab = tabId
      if (tabId === 'analysis' && this.selectedRun && !this.selectedRunAnalysis && !this.analysisLoading) {
        this.ensureRunAnalysis()
      }
      if (tabId === 'scatter' && this.records.length) {
        this.$nextTick(() => this.drawCharts())
      }
    },

    async ensureRunAnalysis() {
      if (!this.selectedRun || this.selectedRunAnalysis || this.analysisLoading) return
      this.analysisLoading = true
      try {
        const r = await fetch(`/api/runs/${this.selectedRun.id}/analysis`)
        this.selectedRunAnalysis = await r.json()
      } finally {
        this.analysisLoading = false
      }
    },

    toggleTheme() {
      this.theme = this.theme === 'light' ? 'dark' : 'light'
      localStorage.setItem('mnsim-dse-theme', this.theme)
      if (this.mainView === 'analysis' && this.globalAnalysis) {
        this.$nextTick(() => this.drawGlobalCharts())
      }
      if (this.activeTab === 'scatter' && this.records.length) {
        this.$nextTick(() => this.drawCharts())
      }
    },

    async sync() {
      this.syncing = true
      const r = await fetch('/api/sync', { method: 'POST' })
      const d = await r.json()
      this.syncing = false
      await Promise.all([this.loadStats(), this.loadRuns()])
      if (this.crossScenarioReportsLoaded || this.mainView === 'crossScenario') await this.loadCrossScenarioReports(true)
      if (this.legacyReportsLoaded) await this.loadLegacyReports(true)
      if (this.tableCatalogLoaded) await this.loadTables()
      this.globalAnalysisDirty = true
      if (this.mainView === 'analysis') await this.loadGlobalAnalysis()
      if ((d.imported || 0) > 0 || (d.refreshed || 0) > 0) {
        alert(`✅ 导入 ${d.imported || 0} 个新实验，刷新 ${(d.refreshed || 0)} 个已有实验`)
      }
      else alert('已是最新，无新数据')
    },

    async openRun(run) {
      this.selectedRun = run
      this.activeTab = 'overview'
      this.showParetoOnly = false
      this.showModal = true
      this.analysisLoading = false
      this.selectedRunAnalysis = null
      // Load detail
      const [detailRes, recRes] = await Promise.all([
        fetch(`/api/runs/${run.id}`),
        fetch(`/api/runs/${run.id}/records`),
      ])
      this.selectedRunDetail = await detailRes.json()
      this.records = await recRes.json()
      this.selectedRecord = this.records[0] || null
      this.selectedEffectiveConfig = null
      if (this.selectedRecord) {
        await this.loadEffectiveConfig(this.selectedRecord)
      }
      // Draw charts after short delay (tab switch)
      this.$nextTick(() => { if (this.activeTab === 'scatter') this.drawCharts() })
    },

    closeModal() {
      this.showModal = false
      this.selectedRun = null
      this.records = []
      this.selectedRecord = null
      this.selectedEffectiveConfig = null
      this.selectedRunAnalysis = null
      this.analysisLoading = false
      Object.values(this._charts).forEach(c => c?.destroy())
      this._charts = {}
    },

    drawGlobalCharts() {
      const rows = this.globalAnalysis?.plot_rows || []
      const isLight = this.theme === 'light'
      const axisColor  = isLight ? '#475569' : '#94a3b8'
      const titleColor = isLight ? '#334155' : '#64748b'
      const gridColor  = isLight ? 'rgba(100,116,139,0.12)' : 'rgba(255,255,255,0.06)'
      const bgFill     = isLight ? '#ffffff' : '#0f172a'
      const presetColors = {
        P0: '#2563eb', P1: '#0f766e', P2: '#7c3aed', P3: '#db2777', P4: '#ea580c',
      }
      const colorOf  = row => presetColors[row.rram_preset] || (isLight ? '#3b82f6' : '#60a5fa')
      const bgColorOf = row => {
        const base = colorOf(row)
        const alpha = row.feasible ? (isLight ? 'dd' : 'e0') : (isLight ? '40' : '38')
        return `${base}${alpha}`
      }
      const borderColorOf = row => row.global_pareto ? (isLight ? '#0f172a' : '#f8fafc') : 'transparent'
      const borderWidthOf = row => row.global_pareto ? 1.8 : 0
      const radiusOf = row => row.global_pareto ? 6 : 4.5
      const axisStyle = {
        grid: { color: gridColor },
        ticks: { color: axisColor, font: { size: 10 } },
      }
      const tooltipFor = row => ([
        `preset: ${row.rram_preset || '—'}  xbar: ${row.xbar_size || '—'}`,
        `ADC: ${row.adc_choice || '—'}  DAC: ${row.dac_num || '—'}  PE: ${row.pe_num || '—'}`,
        `时延: ${this.fmtLatency(row.latency_ns)}  能耗: ${this.fmtEnergy(row.energy_nj)}`,
        `面积: ${this.fmtArea(row.area_um2)}` + (row.accuracy != null ? `  精度: ${this.fmtPercent(row.accuracy, 2)}` : ''),
        `${row.global_pareto ? '★ 全局Pareto' : '非Pareto'} · ${row.feasible ? '可行' : '不可行'}`,
        `${row.run_group || '—'} · #${row.eval_index ?? '—'} ${row.phase || ''}`.trim(),
      ].filter(Boolean))
      const baseOpts = (xlabel, ylabel) => ({
        responsive: true,
        maintainAspectRatio: true,
        animation: { duration: 250 },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: isLight ? 'rgba(15,23,42,0.92)' : 'rgba(15,23,42,0.96)',
            titleColor: '#e2e8f0',
            bodyColor: '#94a3b8',
            borderColor: isLight ? '#334155' : '#475569',
            borderWidth: 1,
            padding: 10,
            callbacks: { afterBody: ctx => tooltipFor(ctx.raw._r) },
          },
        },
        scales: {
          x: { ...axisStyle, title: { display: true, text: xlabel, color: titleColor, font: { size: 10 } } },
          y: { ...axisStyle, title: { display: true, text: ylabel, color: titleColor, font: { size: 10 } } },
        },
      })
      const mkDataset = (items, xMap, yMap) => ({
        label: '评估点',
        data: items.map(row => ({ x: xMap(row), y: yMap(row), _r: row })),
        backgroundColor: items.map(bgColorOf),
        borderColor: items.map(borderColorOf),
        borderWidth: items.map(borderWidthOf),
        pointRadius: items.map(radiusOf),
        pointHoverRadius: items.map(row => radiusOf(row) + 2),
      })
      const mk = (id, items, xMap, yMap, opts) => {
        const el = document.getElementById(id)
        if (!el) return
        // Fill chart background
        const bgPlugin = {
          id: 'bg', beforeDraw: (chart) => {
            const ctx = chart.canvas.getContext('2d')
            ctx.save()
            ctx.fillStyle = bgFill
            ctx.fillRect(0, 0, chart.width, chart.height)
            ctx.restore()
          }
        }
        this._globalCharts[id] = new Chart(el, {
          type: 'scatter',
          data: { datasets: [mkDataset(items, xMap, yMap)] },
          options: opts,
          plugins: [bgPlugin],
        })
      }

      Object.values(this._globalCharts).forEach(c => c?.destroy())
      this._globalCharts = {}

      const latEn  = rows.filter(r => r.latency_ns != null && r.energy_nj != null)
      const latAr  = rows.filter(r => r.latency_ns != null && r.area_um2 != null)
      const enAr   = rows.filter(r => r.energy_nj  != null && r.area_um2 != null)
      const latAcc = rows.filter(r => r.latency_ns != null && r.accuracy != null)

      mk('global-chart-lat-en',  latEn,  r => r.latency_ns/1e6, r => r.energy_nj/1e3,  baseOpts('Latency (ms)', 'Energy (µJ)'))
      mk('global-chart-lat-ar',  latAr,  r => r.latency_ns/1e6, r => r.area_um2/1e6,   baseOpts('Latency (ms)', 'Area (mm²)'))
      mk('global-chart-en-ar',   enAr,   r => r.energy_nj/1e3,  r => r.area_um2/1e6,   baseOpts('Energy (µJ)',  'Area (mm²)'))
      mk('global-chart-lat-acc', latAcc, r => r.latency_ns/1e6, r => r.accuracy*100,    baseOpts('Latency (ms)', 'Accuracy (%)'))
    },

    drawCharts() {
      const all = this.records.filter(r => r.latency_ns && r.energy_nj)
      const pareto = all.filter(r => r.is_pareto)
      const nonPareto = all.filter(r => !r.is_pareto)
      const isLight = this.theme === 'light'
      const axisColor  = isLight ? '#475569' : '#94a3b8'
      const titleColor = isLight ? '#334155' : '#64748b'
      const gridColor  = isLight ? 'rgba(100,116,139,0.12)' : 'rgba(255,255,255,0.06)'
      const bgFill     = isLight ? '#ffffff' : '#0f172a'
      const normalPoint = isLight ? 'rgba(59,130,246,0.55)' : 'rgba(99,102,241,0.5)'
      const paretoPoint = isLight ? 'rgba(14,116,240,0.95)' : 'rgba(96,165,250,0.9)'
      const bgPlugin = {
        id: 'bg', beforeDraw: (chart) => {
          const ctx = chart.canvas.getContext('2d')
          ctx.save(); ctx.fillStyle = bgFill
          ctx.fillRect(0, 0, chart.width, chart.height)
          ctx.restore()
        }
      }

      const mkDataset = (recs, label, color, size) => ({
        label, data: recs.map(r => ({ x: r.latency_ns/1e6, y: r.energy_nj/1e3, _r: r })),
        backgroundColor: color, borderColor: color,
        pointRadius: size, pointHoverRadius: size + 2,
      })

      const axisStyle = {
        grid: { color: gridColor },
        ticks: { color: axisColor, font: { size: 10 } },
      }
      const legendStyle = { labels: { color: axisColor, font: { size: 10 } } }
      const tooltipFmt = (ctx) => {
        const r = ctx.raw._r
        return [
          `时延 / Latency: ${this.fmtLatency(r.latency_ns)}`,
          `能耗 / Energy: ${this.fmtEnergy(r.energy_nj)}`,
          r.accuracy != null ? `精度 / ACC: ${(r.accuracy*100).toFixed(2)}%` : null,
          `#${r.eval_index} ${r.phase}`,
        ].filter(Boolean)
      }
      const baseOpts = (xlabel, ylabel) => ({
        responsive: true, maintainAspectRatio: true,
        plugins: { legend: legendStyle, tooltip: { callbacks: { afterBody: tooltipFmt } } },
        scales: {
          x: { ...axisStyle, title: { display: true, text: xlabel, color: titleColor, font: { size: 10 } } },
          y: { ...axisStyle, title: { display: true, text: ylabel, color: titleColor, font: { size: 10 } } },
        },
      })

      // Destroy old charts
      Object.values(this._charts).forEach(c => c?.destroy())
      this._charts = {}

      const mk = (id, datasets, opts) => {
        const el = document.getElementById(id)
        if (!el) return
        this._charts[id] = new Chart(el, { type: 'scatter', data: { datasets }, options: opts, plugins: [bgPlugin] })
      }

      mk('chart-lat-en', [
        mkDataset(nonPareto, '普通点', normalPoint, 4),
        mkDataset(pareto,    'Pareto', paretoPoint, 7),
      ], baseOpts('时延 / Latency (ms)', '能耗 / Energy (µJ)'))

      const all2 = this.records.filter(r => r.energy_nj && r.area_um2)
      const p2 = all2.filter(r=>r.is_pareto), np2 = all2.filter(r=>!r.is_pareto)
      const mkDataset2 = (recs, label, color, size) => ({
        label, data: recs.map(r => ({ x: r.energy_nj/1e3, y: r.area_um2/1e6, _r: r })),
        backgroundColor: color, borderColor: color,
        pointRadius: size, pointHoverRadius: size + 2,
      })
      mk('chart-en-ar', [
        mkDataset2(np2, '普通点', normalPoint, 4),
        mkDataset2(p2,  'Pareto', paretoPoint, 7),
      ], { ...baseOpts('能耗 / Energy (µJ)', '面积 / Area (mm²)'),
           plugins: { ...baseOpts('','').plugins,
             tooltip: { callbacks: { afterBody: (ctx) => {
               const r = ctx.raw._r
               return [`能耗 / Energy: ${this.fmtEnergy(r.energy_nj)}`,
                       `面积 / Area: ${this.fmtArea(r.area_um2)}`,
                       `#${r.eval_index} ${r.phase}`]
             }}}
           }
         })

      const acc = this.records.filter(r => r.latency_ns && r.accuracy != null)
      mk('chart-lat-acc', [{
        label: '评估点',
        data: acc.map(r => ({ x: r.latency_ns/1e6, y: r.accuracy*100, _r: r })),
        backgroundColor: acc.map(r => r.is_pareto ? paretoPoint : normalPoint),
        pointRadius: acc.map(r => r.is_pareto ? 7 : 4),
      }], { ...baseOpts('时延 / Latency (ms)', '精度 / Accuracy (%)'),
            plugins: { legend: { display: false },
              tooltip: { callbacks: { afterBody: (ctx) => {
                const r = ctx.raw._r
                return [`精度 / ACC: ${(r.accuracy*100).toFixed(2)}%`,
                        `时延 / Latency: ${this.fmtLatency(r.latency_ns)}`,
                        `#${r.eval_index} ${r.phase}`]
              }}}}
          })
    },

    get filteredRuns() {
      const q = this.filterQ.trim().toLowerCase()
      return this.runs.filter(run => {
        if (this.filterAlgo && run.algo !== this.filterAlgo) return false
        if (this.filterSpace && run.space_profile !== this.filterSpace) return false
        if (this.filterGroup && run.run_group !== this.filterGroup) return false
        if (!q) return true
        return [
          run.algo,
          run.run_group,
          run.space_profile,
          run.trial_dir,
          run.sim_config_name,
        ].some(v => String(v || '').toLowerCase().includes(q))
      })
    },

    get filteredRecords() {
      return this.showParetoOnly ? this.records.filter(r => r.is_pareto) : this.records
    },

    get paramCols() {
      const cols = new Set()
      for (const r of this.records) {
        Object.keys(r.params || {}).forEach(k => cols.add(k))
      }
      // Preferred order
      const preferred = ['rram_preset','xbar_size','adc_choice','dac_num',
                         'xbar_polarity','sub_position','group_num','pe_num',
                         'tile_connection','inter_tile_bw']
      const ordered = preferred.filter(k => cols.has(k))
      for (const k of cols) { if (!ordered.includes(k)) ordered.push(k) }
      return ordered
    },

    get statCards() {
      return [
        { label: '实验运行数', value: this.stats.total_runs ?? '…' },
        { label: '评估记录（原始）', value: this.stats.total_records ?? '…' },
        { label: '评估点（去重）', value: this.stats.total_measurements ?? '…' },
        { label: 'Pareto 点数', value: this.stats.total_pareto ?? '…' },
        { label: '唯一设计点', value: this.stats.total_design_points ?? '…' },
      ]
    },

    get globalAnalysisScopeText() {
      const scope = this.globalAnalysis?.scope
      if (!scope) return '当前筛选'
      return `命中 ${scope.matched_runs ?? 0} 个实验`
    },

    get mainViewTitle() {
      const mapping = {
        runs: '实验列表',
        analysis: '全局分析',
        crossScenario: '跨场景分析',
        database: '数据库表',
        legacyReport: '旧版报告',
      }
      return mapping[this.mainView] || '工作台'
    },

    get mainViewDescription() {
      const mapping = {
        runs: '查看 run、scenario、contract 和明细入口，适合日常追踪实验执行状态。',
        analysis: '面向数据库聚合的全局视角，用来判断当前筛选范围内的 Pareto、可行率和推荐配置。',
        crossScenario: '正式展示 observed / repeat-summary 两类 cross-scenario robustness 结果，用来判断最优设计迁移。',
        database: '直接浏览 SQLite 原始表，主要用于排查导入、schema 和数据一致性问题。',
        legacyReport: '保留旧版 analyze_results.py 报告入口，作为历史兼容和补充可视化。',
      }
      return mapping[this.mainView] || '本地 MNSIM DSE 工作台。'
    },

    get crossScenarioScopeText() {
      const count = this.crossScenarioReports.length
      if (!count) return '暂无报告'
      return `发现 ${count} 份 contract 化跨场景报告`
    },

    get crossScenarioTopCandidate() {
      return this.selectedCrossScenarioReport?.summary?.top_candidate || null
    },

    get crossScenarioTopCandidates() {
      return (this.selectedCrossScenarioReport?.summary_rows || []).slice(0, 3)
    },

    get crossScenarioScenarioNamesText() {
      const names = this.selectedCrossScenarioReport?.report?.scenario_names || []
      if (!names.length) return '—'
      if (names.length <= 4) return names.join(' / ')
      return `${names.slice(0, 4).join(' / ')} 等 ${names.length} 个`
    },

    get crossScenarioSummaryCards() {
      const summary = this.selectedCrossScenarioReport?.summary
      const report = this.selectedCrossScenarioReport?.report
      const top = summary?.top_candidate
      if (!summary || !report) return []
      return [
        { zh: '报告模式', en: 'Mode', value: report.mode_short_label || '—', sub: report.mode_label_zh },
        { zh: '场景数', en: 'Scenarios', value: summary.scenario_count ?? 0, sub: this.crossScenarioScenarioNamesText },
        { zh: '候选数', en: 'Candidates', value: summary.candidate_count ?? 0, sub: `full-match ${summary.full_match_candidates ?? 0}` },
        { zh: 'Rank-1 最差精度', en: 'Rank-1 Worst ACC', value: top?.worst_accuracy != null ? this.fmtPercent(top.worst_accuracy, 2) : '—', sub: top ? `candidate #${top.candidate_index}` : null },
        { zh: 'Rank-1 平均精度', en: 'Rank-1 Mean ACC', value: top?.mean_accuracy != null ? this.fmtPercent(top.mean_accuracy, 2) : '—', sub: top?.std_accuracy != null ? `std ${this.fmtPercent(top.std_accuracy, 2)}` : null },
        { zh: 'Rank-1 平均 Yield', en: 'Rank-1 Mean Yield', value: top?.mean_yield != null ? this.fmtPercent(top.mean_yield, 1) : '—', sub: 'across scenarios' },
        { zh: 'Rank-1 平均时延', en: 'Rank-1 Mean Latency', value: this.fmtLatency(top?.mean_latency_ns), sub: 'mean over scenarios' },
        { zh: 'Rank-1 平均能耗', en: 'Rank-1 Mean Energy', value: this.fmtEnergy(top?.mean_energy_nj), sub: 'mean over scenarios' },
      ]
    },

    get crossScenarioHighlights() {
      const report = this.selectedCrossScenarioReport?.report
      const summary = this.selectedCrossScenarioReport?.summary
      const top = summary?.top_candidate
      const runner = summary?.runner_up
      if (!report || !summary) return []
      const items = [
        `当前报告覆盖 ${summary.scenario_count ?? 0} 个 measured preset 场景、${summary.candidate_count ?? 0} 个候选设计点。`,
        report.mode_key === 'observed'
          ? '这份报告直接按各场景观测结果聚合，更适合判断 measured preset 是否真的导致最优设计迁移。'
          : '这份报告先在场景内做 repeat robustness，再跨场景汇总，更适合看候选点的稳定性下界。',
      ]
      if (top) {
        const params = this.crossScenarioParamSummary(top).slice(0, 4).map(item => `${item.label.en}=${item.value}`).join(' / ')
        items.push(`当前 Rank-1 候选为 ${params || '—'}，最差精度 ${top.worst_accuracy != null ? this.fmtPercent(top.worst_accuracy, 2) : '—'}，平均能耗 ${this.fmtEnergy(top.mean_energy_nj)}。`)
      }
      if (top && runner && top.worst_accuracy != null && runner.worst_accuracy != null) {
        const diff = ((top.worst_accuracy - runner.worst_accuracy) * 100).toFixed(2)
        items.push(`Rank-1 相比 Rank-2 的最差精度差值为 ${diff}% ，这能直接反映 robust ranking 是否被真正拉开。`)
      }
      return items
    },

    get crossScenarioCautions() {
      const report = this.selectedCrossScenarioReport?.report
      const summary = this.selectedCrossScenarioReport?.summary
      if (!report || !summary) return []
      const items = [
        'cross-scenario 排名依赖候选集合；如果每个场景只保留很少的 Top-K，排名仍然是 first-look 而不是最终论文结论。',
        'observed 与 repeat-summary 两种口径的排序都应该保留；前者更敏感，后者更保守，不能互相替代。',
      ]
      if ((summary.full_match_candidates || 0) < (summary.candidate_count || 0)) {
        items.push('存在没有覆盖全部场景的候选点，解释结果时要注意“matched_scenarios / scenario_count”是否完整。')
      }
      if (report.scenario_count <= 2) {
        items.push('当前仅覆盖少量 measured preset，已经能看 first-look migration，但还不足以代表最终 robust design rule。')
      }
      return items
    },

    get globalAnalysisSummaryCards() {
      const summary = this.globalAnalysis?.summary
      if (!summary) return []
      return [
        { zh: '实验数', en: 'Matched Runs', value: summary.matched_runs ?? 0, sub: 'opt_runs' },
        { zh: '样本数', en: 'Samples', value: summary.samples ?? 0, sub: 'run_evaluations' },
        { zh: '可行样本', en: 'Feasible Samples', value: summary.feasible_samples ?? 0, sub: this.fmtPercent(summary.feasible_rate ?? 0) },
        { zh: '全局 Pareto', en: 'Global Pareto', value: summary.global_pareto_samples ?? 0, sub: '当前筛选范围' },
        { zh: '唯一设计点', en: 'Unique Design Points', value: summary.unique_design_points ?? 0, sub: 'design_points' },
        { zh: '最小时延', en: 'Best Latency', value: this.fmtLatency(summary.best_latency_ns), sub: summary.best_latency_eval_index ? `#${summary.best_latency_eval_index}` : null },
        { zh: '最低能耗', en: 'Best Energy', value: this.fmtEnergy(summary.best_energy_nj), sub: summary.best_energy_eval_index ? `#${summary.best_energy_eval_index}` : null },
        { zh: '最高精度', en: 'Best Accuracy', value: summary.best_accuracy != null ? this.fmtPercent(summary.best_accuracy, 2) : '—', sub: summary.best_accuracy_eval_index ? `#${summary.best_accuracy_eval_index}` : null },
      ]
    },

    get globalRecommendationStage() {
      const summary = this.globalAnalysis?.summary
      if (!summary || !summary.samples) return '样本不足，暂不能判断'
      const rate = Number(summary.feasible_rate || 0)
      const pareto = Number(summary.global_pareto_samples || 0)
      if (rate >= 0.7 && pareto >= 3) return '进入正式搜索（已有稳定候选）'
      if (rate >= 0.4) return '进入收束验证（空间可继续缩小）'
      if (rate > 0) return '继续筛选空间（可行域仍偏窄）'
      return '重新检查配置（当前未出现可行点）'
    },

    get globalHighlights() {
      const summary = this.globalAnalysis?.summary
      const scope = this.globalAnalysis?.scope
      const top = this.globalTopRankConfigs[0]
      if (!summary) return []
      const items = [
        `当前筛选命中 ${summary.matched_runs ?? 0} 个实验、${summary.samples ?? 0} 个评估样本，数据库口径下可行率为 ${this.fmtPercent(summary.feasible_rate ?? 0)}。`,
        `当前范围内共有 ${summary.global_pareto_samples ?? 0} 个全局 Pareto 点，可作为下一轮重点对比候选。`,
      ]
      if (top) {
        const parts = this.analysisParamSummary(top.params).slice(0, 4).map(item => `${item.label.en}=${item.value}`)
        items.push(`当前综合排序第一的候选点来自 ${(top.run_group || '未分组实验')}，核心参数为 ${parts.join(' / ') || '—'}。`)
      }
      if ((scope?.runs || []).length > 1) {
        items.push(`当前分析已跨多个 run 做统一重算，Pareto 与排名结论不再受单次实验视角限制。`)
      }
      return items
    },

    get globalActions() {
      const summary = this.globalAnalysis?.summary
      if (!summary) return []
      const actions = []
      const rate = Number(summary.feasible_rate || 0)
      if (rate <= 0) {
        actions.push('优先回到实验配置，检查精度门槛、器件预设和关键结构参数，先跑出至少一个可行点。')
        actions.push('确认 run 的 accuracy_target 是否过高，以及当前参数空间是否被限制得过窄。')
        return actions
      }
      if (rate < 0.4) {
        actions.push('先收缩设计空间，把当前已经出现可行点的参数组合单独拉出来做定向扫描。')
        actions.push('减少明显失效的参数档位，避免后续搜索继续把预算浪费在不可行区域。')
      } else {
        actions.push('以 Top-3 候选点为中心，围绕关键变量做小范围精细搜索，而不是重新铺开全空间。')
        actions.push('把当前全局 Pareto 点导向论文候选集，重点比较 latency / energy / area 的取舍。')
      }
      actions.push('若要验证结论稳定性，建议固定主结构参数，只变动一到两个核心维度重新跑实验。')
      return actions
    },

    get globalCautions() {
      const summary = this.globalAnalysis?.summary
      const scope = this.globalAnalysis?.scope
      if (!summary) return []
      const items = [
        '当前页面使用数据库实时聚合结果，不再依赖 CSV；因此数值以 opt_runs、run_evaluations、measurements、design_points 的联表结果为准。',
        '“Top-3 推荐配置”是具体评估记录，不是分组均值；同一组参数在不同 run 中仍可能因为上下文、阶段或种子不同而出现差异。',
      ]
      if ((scope?.runs || []).length === 1) {
        items.push('当前实际上只命中 1 个实验，虽然页面叫“全局分析”，但结论仍更接近单次 run 视角。')
      } else {
        items.push('当前结果跨多个实验统一排序，若筛选条件过宽，不同实验目标混在一起会稀释单一实验结论。')
      }
      if ((summary.global_pareto_samples || 0) <= 1) {
        items.push('当前 Pareto 点数量很少，说明可行解边界还不稳定，不建议过早下最终结论。')
      }
      return items
    },

    get globalTopRankConfigs() {
      return (this.globalAnalysis?.top_configs || []).slice(0, 3)
    },

    globalRankBadge(idx) {
      return ['Rank-1', 'Rank-2', 'Rank-3'][idx] || `Rank-${idx + 1}`
    },

    globalRankReason(row, idx) {
      const summary = this.globalAnalysis?.summary || {}
      const reasons = []
      if (idx === 0) reasons.push('综合平衡分最佳')
      if (row?.global_pareto) reasons.push('位于全局 Pareto 前沿')
      if (row?.feasible) reasons.push('满足精度门槛')
      if (summary.best_latency_eval_index === row?.eval_index && summary.best_latency_ns === row?.latency_ns) reasons.push('时延最优')
      if (summary.best_energy_eval_index === row?.eval_index && summary.best_energy_nj === row?.energy_nj) reasons.push('能耗最优')
      if (summary.best_area_eval_index === row?.eval_index && summary.best_area_um2 === row?.area_um2) reasons.push('面积最优')
      if (summary.best_accuracy_eval_index === row?.eval_index && summary.best_accuracy === row?.accuracy) reasons.push('精度最高')
      return reasons.slice(0, 3).join(' / ') || '综合表现稳定，适合作为下一轮重点候选。'
    },

    crossScenarioRankReason(row, idx) {
      const reasons = []
      if (idx === 0) reasons.push('当前 robust 排名第一')
      if (row.matched_scenarios != null && row.scenario_count != null && row.matched_scenarios === row.scenario_count) {
        reasons.push('覆盖全部场景')
      }
      if (row.worst_accuracy != null) reasons.push(`worst ${this.fmtPercent(row.worst_accuracy, 2)}`)
      if (row.mean_yield != null) reasons.push(`yield ${this.fmtPercent(row.mean_yield, 1)}`)
      return reasons.slice(0, 3).join(' / ') || '跨场景表现稳定。'
    },

    globalScopeValues(field) {
      const runs = this.globalAnalysis?.scope?.runs || []
      if (!runs.length) return '—'
      const values = [...new Set(runs.map(run => run?.[field]).filter(v => v !== null && v !== undefined && String(v) !== ''))]
      if (!values.length) return '—'
      if (values.length <= 3) return values.join(' / ')
      return `${values.slice(0, 3).join(' / ')} 等 ${values.length} 项`
    },

    globalBestText(metric) {
      const summary = this.globalAnalysis?.summary
      const top = this.globalTopRankConfigs
      if (!summary) return '—'
      if (metric === 'latency') {
        return summary.best_latency_ns != null
          ? `${this.fmtLatency(summary.best_latency_ns)}${summary.best_latency_eval_index ? ` · #${summary.best_latency_eval_index}` : ''}`
          : '—'
      }
      if (metric === 'energy') {
        return summary.best_energy_nj != null
          ? `${this.fmtEnergy(summary.best_energy_nj)}${summary.best_energy_eval_index ? ` · #${summary.best_energy_eval_index}` : ''}`
          : '—'
      }
      if (metric === 'area') {
        return summary.best_area_um2 != null
          ? `${this.fmtArea(summary.best_area_um2)}${summary.best_area_eval_index ? ` · #${summary.best_area_eval_index}` : ''}`
          : '—'
      }
      if (metric === 'accuracy') {
        return summary.best_accuracy != null
          ? `${this.fmtPercent(summary.best_accuracy, 2)}${summary.best_accuracy_eval_index ? ` · #${summary.best_accuracy_eval_index}` : ''}`
          : '—'
      }
      return top.length ? `#${top[0].eval_index}` : '—'
    },

    get globalGuideSteps() {
      return [
        { title: '先看摘要', desc: '先确认当前筛选命中多少实验、可行率是否足够，再判断现在是继续摸底还是进入正式收束。' },
        { title: '再看 Top-3', desc: 'Top-3 展示的是具体记录点，适合直接回跳到实验详情里检查原始指标与生效配置。' },
        { title: '然后看分组统计', desc: '分组摘要用于看哪些参数档位整体更稳，避免只盯住单个偶然最优点。' },
        { title: '最后做定向复跑', desc: '把当前领先的参数组合作为中心，缩小范围做复跑，比重新全量搜索更高效。' },
      ]
    },

    get globalPrimaryGroupSections() {
      const sections = this.globalAnalysis?.group_sections || []
      const preferred = ['rram_preset', 'xbar_size', 'adc_choice', 'pe_num']
      const ordered = preferred
        .map(key => sections.find(section => section.key === key))
        .filter(Boolean)
      return ordered.length ? ordered : sections.slice(0, 4)
    },

    get runConfigKV() {
      const r = this.selectedRunDetail
      if (!r) return []
      const rc = r.run_config || {}
      const fmt = v => v === true ? '✓' : v === false ? '✗' : String(v ?? '—')
      return [
        { zh: '网络', en: 'NN', v: rc.nn || r.nn },
        { zh: '基础配置', en: 'SimConfig', v: r.sim_config_name || r.sim_config_hash?.slice(0,8) || '—' },
        { zh: '设计空间', en: 'Space', v: r.space_profile },
        { zh: '契约版本', en: 'Contract', v: rc.contract_version || 'legacy' },
        { zh: '场景名称', en: 'Scenario', v: rc.scenario?.name || 'nominal' },
        { zh: '场景类型', en: 'Scenario Kind', v: rc.scenario?.kind || 'nominal' },
        { zh: '预算', en: 'Budget', v: fmt(r.budget) },
        { zh: '初始评估', en: 'Init Evals', v: fmt(rc.init_evals) },
        { zh: '运行精度', en: 'Run Accuracy', v: fmt(rc.run_accuracy) },
        { zh: '启用SAF', en: 'Enable SAF', v: fmt(rc.enable_saf) },
        { zh: '启用波动', en: 'Variation', v: fmt(rc.enable_variation) },
        { zh: '精度目标', en: 'ACC Target', v: r.accuracy_target != null ? (r.accuracy_target*100).toFixed(0)+'%' : '—' },
        { zh: '设备', en: 'Device', v: rc.device },
        { zh: '总耗时', en: 'Wall Time', v: this.fmtDuration(r.wall_time_s) },
        { zh: '超体积', en: 'Hypervolume', v: this.fmtHV(r.hypervolume) },
        { zh: 'Pareto 数量', en: 'Pareto Size', v: fmt(r.pareto_size) },
        { zh: '来源', en: 'Source', v: r.source_type },
        { zh: '开始时间', en: 'Started', v: this.fmtDate(r.started_at) },
      ]
    },

    get algoKwargs() {
      const ak = this.selectedRunDetail?.run_config?.algo_kwargs || {}
      return Object.entries(ak).map(([k,v]) => {
        const labels = this.algoParamLabel(k)
        return { zh: labels.zh, en: labels.en, v: String(v), k }
      })
    },

    get bestMetrics() {
      const recs = this.records
      if (!recs.length) return []
      const minBy = (arr, fn) => arr.reduce((a,b) => fn(a)<fn(b)?a:b, arr[0])
      const maxBy = (arr, fn) => arr.reduce((a,b) => fn(a)>fn(b)?a:b, arr[0])
      const lat = minBy(recs.filter(r=>r.latency_ns), r=>r.latency_ns)
      const en  = minBy(recs.filter(r=>r.energy_nj),  r=>r.energy_nj)
      const ar  = minBy(recs.filter(r=>r.area_um2),   r=>r.area_um2)
      const acc = recs.some(r=>r.accuracy!=null)
                  ? maxBy(recs.filter(r=>r.accuracy!=null), r=>r.accuracy)
                  : null
      return [
        { zh: '最小时延', en: 'Best Latency',  value: this.fmtLatency(lat?.latency_ns), color: 'text-blue-400',  sub: `#${lat?.eval_index}` },
        { zh: '最低能耗', en: 'Best Energy',   value: this.fmtEnergy(en?.energy_nj),   color: 'text-purple-400', sub: `#${en?.eval_index}` },
        { zh: '最小面积', en: 'Best Area',     value: this.fmtArea(ar?.area_um2),      color: 'text-cyan-400',   sub: `#${ar?.eval_index}` },
        { zh: '最高精度', en: 'Best Accuracy', value: acc ? (acc.accuracy*100).toFixed(2)+'%' : '—',
          color: 'text-green-400', sub: acc ? `#${acc.eval_index}` : null },
      ]
    },

    get analysisSummaryCards() {
      const summary = this.selectedRunAnalysis?.summary
      if (!summary) return []
      return [
        { zh: '样本数', en: 'Samples', value: summary.samples ?? 0, sub: 'run_evaluations' },
        { zh: '可行样本', en: 'Feasible Samples', value: summary.feasible_samples ?? 0, sub: this.fmtPercent(summary.feasible_rate ?? 0) },
        { zh: '全局 Pareto', en: 'Global Pareto', value: summary.global_pareto_samples ?? 0, sub: '当前 run 内重算' },
        { zh: '唯一设计点', en: 'Unique Design Points', value: summary.unique_design_points ?? 0, sub: 'design_points' },
        { zh: '唯一测量', en: 'Unique Measurements', value: summary.unique_measurements ?? 0, sub: 'measurements' },
        { zh: '最小时延', en: 'Best Latency', value: this.fmtLatency(summary.best_latency_ns), sub: summary.best_latency_eval_index ? `#${summary.best_latency_eval_index}` : null },
        { zh: '最低能耗', en: 'Best Energy', value: this.fmtEnergy(summary.best_energy_nj), sub: summary.best_energy_eval_index ? `#${summary.best_energy_eval_index}` : null },
        { zh: '最高精度', en: 'Best Accuracy', value: summary.best_accuracy != null ? this.fmtPercent(summary.best_accuracy, 2) : '—', sub: summary.best_accuracy_eval_index ? `#${summary.best_accuracy_eval_index}` : null },
      ]
    },

    analysisParamSummary(params) {
      if (!params) return []
      const preferred = ['rram_preset','xbar_size','adc_choice','dac_num','xbar_polarity','sub_position','group_num','pe_num','tile_connection','inter_tile_bw']
      const keys = preferred.filter(key => Object.prototype.hasOwnProperty.call(params, key))
      for (const key of Object.keys(params)) {
        if (!keys.includes(key)) keys.push(key)
      }
      return keys.map(key => ({ key, value: params[key], label: this.paramLabel(key) }))
    },

    crossScenarioParamSummary(row) {
      if (!row) return []
      const preferred = ['rram_preset','xbar_size','adc_choice','dac_num','xbar_polarity','sub_position','group_num','pe_num','tile_connection','inter_tile_bw']
      const keys = preferred.filter(key => row[key] !== undefined && row[key] !== null && row[key] !== '')
      return keys.map(key => ({ key, value: row[key], label: this.paramLabel(key) }))
    },

    crossScenarioReportPreview(report) {
      const top = report?.top_candidate
      if (!top) return '当前报告还没有有效候选。'
      const params = this.crossScenarioParamSummary(top).slice(0, 3).map(item => `${item.label.en}=${item.value}`).join(' / ')
      const worst = top.worst_accuracy != null ? this.fmtPercent(top.worst_accuracy, 2) : '—'
      return `Rank-1: ${params || '—'} · worst ${worst}`
    },

    // ── Formatters ──────────────────────────────────────────────────────────
    fmtLatency(ns) {
      if (ns == null) return '—'
      if (ns >= 1e9)  return (ns/1e9).toFixed(2) + ' s'
      if (ns >= 1e6)  return (ns/1e6).toFixed(2) + ' ms'
      return (ns/1e3).toFixed(1) + ' µs'
    },
    fmtEnergy(nj) {
      if (nj == null) return '—'
      if (nj >= 1e6)  return (nj/1e6).toFixed(2) + ' mJ'
      if (nj >= 1e3)  return (nj/1e3).toFixed(2) + ' µJ'
      return nj.toFixed(1) + ' nJ'
    },
    fmtArea(um2) {
      if (um2 == null) return '—'
      if (um2 >= 1e12) return (um2/1e12).toFixed(2) + ' m²'
      if (um2 >= 1e6)  return (um2/1e6).toFixed(2) + ' mm²'
      if (um2 >= 1e3)  return (um2/1e3).toFixed(1) + ' ×10³ µm²'
      return um2.toFixed(0) + ' µm²'
    },
    fmtHV(hv) {
      if (hv == null) return '—'
      if (hv === 0)   return '0'
      const exp = Math.floor(Math.log10(Math.abs(hv)))
      const man = hv / Math.pow(10, exp)
      return man.toFixed(2) + 'e' + exp
    },
    fmtDuration(s) {
      if (s == null) return '—'
      if (s < 60) return s.toFixed(1) + 's'
      if (s < 3600) return Math.floor(s/60) + 'm ' + Math.floor(s%60) + 's'
      return Math.floor(s/3600) + 'h ' + Math.floor((s%3600)/60) + 'm'
    },
    fmtPercent(v, digits = 1) {
      if (v == null) return '—'
      return (v * 100).toFixed(digits) + '%'
    },
    fmtDate(iso) {
      if (!iso) return '—'
      try {
        const d = new Date(iso)
        return d.toLocaleDateString('zh-CN', { month:'2-digit', day:'2-digit' }) + ' ' +
               d.toLocaleTimeString('zh-CN', { hour:'2-digit', minute:'2-digit' })
      } catch { return iso.slice(0,16) }
    },
    trialName(path) {
      if (!path) return ''
      const parts = path.replace(/\\/g,'/').split('/')
      return parts.slice(-1)[0]
    },
    get selectedTableMeta() {
      return this.tableCatalog.find(t => t.name === this.tableBrowser.selected) || null
    },
    get selectedTableMetaZh() {
      const meta = this.selectedTableMeta
      if (!meta) return ''
      const desc = this.tableDescriptions()[meta.name]
      return desc ? `${desc.zh} / ${desc.en}` : meta.name
    },
    get selectedTableIsSimConfigs() {
      return this.tableBrowser.selected === 'sim_configs'
    },
    get tablePageText() {
      if (!this.tableBrowser.total) return '0 / 0'
      const start = this.tableBrowser.offset + 1
      const end = Math.min(this.tableBrowser.offset + this.tableBrowser.limit, this.tableBrowser.total)
      return `${start}-${end} / ${this.tableBrowser.total}`
    },
    tableDescriptions() {
      return {
        opt_runs: { zh: '实验运行表', en: 'Optimization Runs' },
        run_evaluations: { zh: '评估记录表', en: 'Run Evaluations' },
        measurements: { zh: '去重测量表', en: 'Measurements' },
        design_points: { zh: '设计点表', en: 'Design Points' },
        eval_contexts: { zh: '评估上下文表', en: 'Evaluation Contexts' },
        sim_configs: { zh: '仿真配置表，展开显示配置内容', en: 'Simulation Configs with expanded content' },
      }
    },
    dimensionDescriptions() {
      return {
        rram_preset: { zh: 'RRAM 预设', en: 'RRAM Preset' },
        xbar_size: { zh: '交叉阵列尺寸', en: 'Crossbar Size' },
        adc_choice: { zh: 'ADC 选择', en: 'ADC Choice' },
        dac_num: { zh: 'DAC 数量', en: 'DAC Number' },
        xbar_polarity: { zh: '阵列极性', en: 'Crossbar Polarity' },
        sub_position: { zh: '子阵位置', en: 'Sub Position' },
        group_num: { zh: '组数', en: 'Group Number' },
        pe_num: { zh: 'PE 数量', en: 'PE Number' },
        tile_connection: { zh: 'Tile 连接方式', en: 'Tile Connection' },
        inter_tile_bw: { zh: 'Tile 间带宽', en: 'Inter-Tile Bandwidth' },
      }
    },
    sectionDescriptions() {
      return {
        General: { zh: '通用配置', en: 'General' },
        'Device level': { zh: '器件层', en: 'Device level' },
        'Crossbar level': { zh: '交叉阵列层', en: 'Crossbar level' },
        'Interface level': { zh: '接口层', en: 'Interface level' },
        'Process element level': { zh: '处理单元层', en: 'Process element level' },
        'Tile level': { zh: 'Tile 层', en: 'Tile level' },
        'Architecture level': { zh: '架构层', en: 'Architecture level' },
        'Network level': { zh: '网络层', en: 'Network level' },
        'Accuracy level': { zh: '精度层', en: 'Accuracy level' },
        'NoC level': { zh: '片上网络层', en: 'NoC level' },
        'Buffer level': { zh: '缓冲层', en: 'Buffer level' },
        'ADC level': { zh: 'ADC 层', en: 'ADC level' },
        'DAC level': { zh: 'DAC 层', en: 'DAC level' },
        'Digital module': { zh: '数字模块', en: 'Digital module' },
        'Algorithm Configuration': { zh: '算法配置', en: 'Algorithm Configuration' },
      }
    },
    algoParamDescriptions() {
      return {
        accuracy_target: { zh: '精度目标', en: 'Accuracy Target' },
        population: { zh: '种群大小', en: 'Population' },
        evals_per_gen: { zh: '每代评估数', en: 'Evaluations per Generation' },
        w_latency: { zh: '时延权重', en: 'Latency Weight' },
        w_energy: { zh: '能耗权重', en: 'Energy Weight' },
        w_area: { zh: '面积权重', en: 'Area Weight' },
        two_stage: { zh: '两阶段评估', en: 'Two-stage Evaluation' },
        topk_accuracy: { zh: '复评 Top-K', en: 'Top-K Accuracy Recheck' },
        accuracy_penalty: { zh: '精度惩罚', en: 'Accuracy Penalty' },
      }
    },
    paramLabel(name) {
      return this.dimensionDescriptions()[name] || { zh: name, en: name }
    },
    sectionLabel(name) {
      return this.sectionDescriptions()[name] || { zh: name, en: name }
    },
    algoParamLabel(name) {
      return this.algoParamDescriptions()[name] || { zh: name, en: name }
    },
    columnDescriptions() {
      return {
        id: { zh: '主键', en: 'Primary Key' },
        trial_dir: { zh: '运行目录', en: 'Trial Directory' },
        run_group: { zh: '实验组', en: 'Run Group' },
        source_type: { zh: '来源类型', en: 'Source Type' },
        algo: { zh: '算法', en: 'Algorithm' },
        seed: { zh: '随机种子', en: 'Seed' },
        space_profile: { zh: '设计空间', en: 'Space Profile' },
        eval_context_id: { zh: '评估上下文ID', en: 'Eval Context ID' },
        accuracy_target: { zh: '精度目标', en: 'Accuracy Target' },
        budget: { zh: '预算', en: 'Budget' },
        status: { zh: '状态', en: 'Status' },
        total_evaluated: { zh: '总评估数', en: 'Total Evaluated' },
        pareto_size: { zh: 'Pareto 数量', en: 'Pareto Size' },
        hypervolume: { zh: '超体积', en: 'Hypervolume' },
        hv_reference_point: { zh: 'HV 参考点', en: 'HV Reference Point' },
        wall_time_s: { zh: '总耗时(秒)', en: 'Wall Time (s)' },
        started_at: { zh: '开始时间', en: 'Started At' },
        finished_at: { zh: '结束时间', en: 'Finished At' },
        run_config_json: { zh: '运行配置JSON', en: 'Run Config JSON' },
        imported_at: { zh: '导入时间', en: 'Imported At' },
        run_id: { zh: '运行ID', en: 'Run ID' },
        measurement_id: { zh: '测量ID', en: 'Measurement ID' },
        eval_index: { zh: '评估序号', en: 'Evaluation Index' },
        phase: { zh: '阶段', en: 'Phase' },
        is_pareto: { zh: '是否 Pareto', en: 'Is Pareto' },
        design_point_id: { zh: '设计点ID', en: 'Design Point ID' },
        latency_ns: { zh: '时延(ns)', en: 'Latency (ns)' },
        energy_nj: { zh: '能耗(nJ)', en: 'Energy (nJ)' },
        area_um2: { zh: '面积(um^2)', en: 'Area (um^2)' },
        power_w: { zh: '功耗(W)', en: 'Power (W)' },
        accuracy: { zh: '精度', en: 'Accuracy' },
        elapsed_s: { zh: '单点评估耗时(秒)', en: 'Elapsed (s)' },
        measured_at: { zh: '测量时间', en: 'Measured At' },
        params_hash: { zh: '参数哈希', en: 'Params Hash' },
        params_json: { zh: '参数JSON', en: 'Params JSON' },
        context_hash: { zh: '上下文哈希', en: 'Context Hash' },
        sim_config_id: { zh: '配置ID', en: 'Sim Config ID' },
        nn: { zh: '网络', en: 'Network' },
        dataset_module: { zh: '数据集模块', en: 'Dataset Module' },
        weights_path: { zh: '权重路径', en: 'Weights Path' },
        run_accuracy: { zh: '运行精度', en: 'Run Accuracy' },
        enable_saf: { zh: '启用 SAF', en: 'Enable SAF' },
        enable_variation: { zh: '启用波动', en: 'Enable Variation' },
        enable_rratio: { zh: '启用电阻比', en: 'Enable RRatio' },
        fixed_qrange: { zh: '固定量化范围', en: 'Fixed QRange' },
        name: { zh: '名称', en: 'Name' },
        content_hash: { zh: '内容哈希', en: 'Content Hash' },
        content: { zh: '配置内容', en: 'Content' },
        created_at: { zh: '创建时间', en: 'Created At' },
        Device_Tech: { zh: '器件工艺节点', en: 'Device Tech' },
        Device_Type: { zh: '器件类型', en: 'Device Type' },
        Device_Area: { zh: '器件面积', en: 'Device Area' },
        Device_SAF: { zh: '器件失效率', en: 'Device SAF' },
        Read_Level: { zh: '读取电平', en: 'Read Level' },
        Read_Voltage: { zh: '读取电压', en: 'Read Voltage' },
        Write_Level: { zh: '写入电平', en: 'Write Level' },
        Write_Voltage: { zh: '写入电压', en: 'Write Voltage' },
        Read_Latency: { zh: '读取时延', en: 'Read Latency' },
        Write_Latency: { zh: '写入时延', en: 'Write Latency' },
        Device_Level: { zh: '器件电平数', en: 'Device Level Count' },
        Device_Resistance: { zh: '器件电阻', en: 'Device Resistance' },
        Device_Variation: { zh: '器件波动', en: 'Device Variation' },
        Xbar_Size: { zh: '交叉阵列尺寸', en: 'Crossbar Size' },
        Subarray_Size: { zh: '子阵尺寸', en: 'Subarray Size' },
        Cell_Type: { zh: '存储单元类型', en: 'Cell Type' },
        Transistor_Tech: { zh: '晶体管工艺节点', en: 'Transistor Technology' },
        Wire_Resistance: { zh: '连线电阻', en: 'Wire Resistance' },
        Wire_Capacity: { zh: '连线电容', en: 'Wire Capacitance' },
        Load_Resistance: { zh: '负载电阻', en: 'Load Resistance' },
        Area_Calculation: { zh: '面积计算模式', en: 'Area Calculation' },
        PIM_Type: { zh: 'PIM 类型', en: 'PIM Type' },
        ADC_Choice: { zh: 'ADC 选择', en: 'ADC Choice' },
        ADC_Num: { zh: 'ADC 数量', en: 'ADC Number' },
        DAC_Num: { zh: 'DAC 数量', en: 'DAC Number' },
        PE_inBuf_Size: { zh: 'PE 输入缓冲大小', en: 'PE Input Buffer Size' },
        PE_inBuf_Area: { zh: 'PE 输入缓冲面积', en: 'PE Input Buffer Area' },
        Tile_outBuf_Size: { zh: 'Tile 输出缓冲大小', en: 'Tile Output Buffer Size' },
        Tile_outBuf_Area: { zh: 'Tile 输出缓冲面积', en: 'Tile Output Buffer Area' },
        DFU_Buf_Size: { zh: 'DFU 缓冲大小', en: 'DFU Buffer Size' },
        DFU_Buf_Area: { zh: 'DFU 缓冲面积', en: 'DFU Buffer Area' },
        Digital_Frequency: { zh: '数字频率', en: 'Digital Frequency' },
        Adder_Tech: { zh: '加法器工艺', en: 'Adder Technology' },
        Adder_Area: { zh: '加法器面积', en: 'Adder Area' },
        Adder_Power: { zh: '加法器功耗', en: 'Adder Power' },
        Multiplier_Tech: { zh: '乘法器工艺', en: 'Multiplier Technology' },
        Multiplier_Area: { zh: '乘法器面积', en: 'Multiplier Area' },
        Multiplier_Power: { zh: '乘法器功耗', en: 'Multiplier Power' },
        ShiftReg_Tech: { zh: '移位寄存器工艺', en: 'Shift Register Technology' },
        ShiftReg_Area: { zh: '移位寄存器面积', en: 'Shift Register Area' },
        ShiftReg_Power: { zh: '移位寄存器功耗', en: 'Shift Register Power' },
        Reg_Tech: { zh: '寄存器工艺', en: 'Register Technology' },
        Reg_Area: { zh: '寄存器面积', en: 'Register Area' },
        Reg_Power: { zh: '寄存器功耗', en: 'Register Power' },
        JointModule_Tech: { zh: '联合模块工艺', en: 'Joint Module Technology' },
        JointModule_Area: { zh: '联合模块面积', en: 'Joint Module Area' },
        JointModule_Power: { zh: '联合模块功耗', en: 'Joint Module Power' },
        Xbar_Polarity: { zh: '阵列极性', en: 'Crossbar Polarity' },
        Sub_Position: { zh: '子阵位置', en: 'Sub Position' },
        Group_Num: { zh: '组数', en: 'Group Number' },
        PE_Num: { zh: 'PE 数量', en: 'PE Number' },
        Pooling_shape: { zh: '池化窗口形状', en: 'Pooling Shape' },
        Pooling_unit_num: { zh: '池化单元数量', en: 'Pooling Unit Number' },
        Pooling_Tech: { zh: '池化单元工艺', en: 'Pooling Technology' },
        Pooling_area: { zh: '池化单元面积', en: 'Pooling Area' },
        Tile_Adder_Num: { zh: 'Tile 加法器数量', en: 'Tile Adder Number' },
        Tile_Adder_Level: { zh: 'Tile 加法器级数', en: 'Tile Adder Level' },
        Tile_ShiftReg_Num: { zh: 'Tile 移位寄存器数量', en: 'Tile Shift Register Number' },
        Tile_ShiftReg_Level: { zh: 'Tile 移位寄存器级数', en: 'Tile Shift Register Level' },
        Tile_Connection: { zh: 'Tile 连接方式', en: 'Tile Connection' },
        Inter_Tile_Bandwidth: { zh: 'Tile 间带宽', en: 'Inter-Tile Bandwidth' },
        Intra_Tile_Bandwidth: { zh: 'Tile 内带宽', en: 'Intra-Tile Bandwidth' },
        Buffer_Choice: { zh: '缓冲类型选择', en: 'Buffer Choice' },
        Buffer_Technology: { zh: '缓冲工艺', en: 'Buffer Technology' },
        Buffer_ReadPower: { zh: '缓冲读功耗', en: 'Buffer Read Power' },
        Buffer_WritePower: { zh: '缓冲写功耗', en: 'Buffer Write Power' },
        Buffer_Bitwidth: { zh: '缓冲位宽', en: 'Buffer Bitwidth' },
        LUT_Capacity: { zh: '查找表容量', en: 'LUT Capacity' },
        LUT_Area: { zh: '查找表面积', en: 'LUT Area' },
        LUT_Power: { zh: '查找表功耗', en: 'LUT Power' },
        LUT_Bandwidth: { zh: '查找表带宽', en: 'LUT Bandwidth' },
        Read_Power: { zh: '读功耗', en: 'Read Power' },
        Write_Power: { zh: '写功耗', en: 'Write Power' },
        Read_Energy: { zh: '读能耗', en: 'Read Energy' },
        Write_Energy: { zh: '写能耗', en: 'Write Energy' },
        Leakage_Power: { zh: '漏电功耗', en: 'Leakage Power' },
        ADC_Precision: { zh: 'ADC 精度', en: 'ADC Precision' },
        DAC_Precision: { zh: 'DAC 精度', en: 'DAC Precision' },
        PE_group: { zh: 'PE 分组', en: 'PE Group' },
        Tile_Num: { zh: 'Tile 数量', en: 'Tile Number' },
        Buffer_Size: { zh: '缓冲大小', en: 'Buffer Size' },
        Weight_Polarity: { zh: '权重极性', en: 'Weight Polarity' },
        Simulation_Level: { zh: '仿真层级', en: 'Simulation Level' },
        NoC_enable: { zh: '启用NoC', en: 'Enable NoC' },
      }
    },
    tableDisplayName(name) {
      const desc = this.tableDescriptions()[name]
      return desc ? `${desc.zh} / ${desc.en}` : name
    },
    tableColumnLabel(name, brief = false) {
      const desc = this.columnDescriptions()[name]
      if (!desc) return brief ? name : `${name} / ${name}`
      return brief ? desc.zh : `${desc.zh} / ${desc.en}`
    },
    tableRowKey(row, idx) {
      return row.id ?? `${this.tableBrowser.selected}-${this.tableBrowser.offset + idx}`
    },
    fmtCell(value) {
      if (value == null || value === '') return '—'
      if (typeof value === 'object') return JSON.stringify(value)
      return String(value)
    },
    parseSimConfig(content) {
      const text = String(content || '')
      if (!text.trim()) return []
      const lines = text.replace(/\r\n/g, '\n').split('\n')
      const sections = []
      let current = { name: 'General', items: [] }
      sections.push(current)
      let pendingComment = ''

      for (const rawLine of lines) {
        const line = rawLine.trim()
        if (!line) continue
        if (line.startsWith('[') && line.endsWith(']')) {
          current = { name: line.slice(1, -1), items: [] }
          sections.push(current)
          pendingComment = ''
          continue
        }
        if (line.startsWith('#') || line.startsWith(';')) {
          pendingComment = pendingComment ? `${pendingComment} ${line}` : line
          current.items.push({ kind: 'comment', comment: line })
          continue
        }
        const eq = rawLine.indexOf('=')
        if (eq >= 0) {
          const key = rawLine.slice(0, eq).trim()
          const value = rawLine.slice(eq + 1).trim()
          current.items.push({
            kind: 'kv',
            key,
            value,
            comment: pendingComment,
          })
          pendingComment = ''
          continue
        }
        current.items.push({ kind: 'comment', comment: rawLine.trim() })
      }
      return sections.filter(section => section.items.length)
    },
    tablePrevPage() {
      if (this.tableBrowser.offset === 0) return
      this.tableBrowser.offset = Math.max(0, this.tableBrowser.offset - this.tableBrowser.limit)
      this.loadTableRows()
    },
    tableNextPage() {
      if (this.tableBrowser.offset + this.tableBrowser.limit >= this.tableBrowser.total) return
      this.tableBrowser.offset += this.tableBrowser.limit
      this.loadTableRows()
    },
  }
}

// Watch tab change for chart redraw
document.addEventListener('alpine:init', () => {
  Alpine.effect(() => {
    // accessed inside openRun via nextTick
  })
})

document.addEventListener('alpine:init', () => {
  Alpine.data('dseApp', dseApp)
})
