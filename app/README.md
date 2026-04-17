# App Structure

`app/` 是本地 DSE 可视化与查询服务，当前按“入口 / 后端模块 / 静态资源”三层组织：

- `server.py`
  Flask 入口，只负责 app 初始化、DB 生命周期和路由绑定。
- `backend/shared.py`
  路径常量、公共 helper、配置展开和 CSV typed reader。
- `backend/analysis.py`
  run/global analysis 的聚合与排序逻辑。
- `backend/reports.py`
  cross-scenario 报告与 legacy report 的扫描和装载。
- `backend/sync.py`
  `artifacts/dse` 到 SQLite 的同步入口。
- `static/index.html`
  页面骨架与各主视图布局。
- `static/css/app.css`
  页面样式。
- `static/js/app.js`
  Alpine 状态机、交互逻辑、图表绘制与 formatter。
- `dse_records.db`
  本地 SQLite 缓存数据库。

当前设计原则：

- `server.py` 不再承载大段分析逻辑
- `index.html` 不再内联大块 CSS/JS
- 新的分析视图优先通过 contract 化 JSON API 接入，而不是继续堆 iframe/legacy 分支

