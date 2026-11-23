# 新审计团队起读说明

交接日期：2026-11-23。

后续阶段已继续修改代码；本页66ad918为旧轮固定基线。新阶段请先读[阶段交付](docs/NEXT_STAGE_DELIVERY.md)、[数据质量与分析报告](docs/DATA_QUALITY_REPORT.md)及[固定版本验收](verification/quality-stage-2026-11-23/acceptance.json)。本文件由开发方提供，旨在让未参与前序讨论的团队独立复核，不是第三方审计结论。

## 先固定版本

本轮审计基线为 **`66ad918c3235409dffd2fdbc3366c5d7b21e2673`**，包含最后四项修正及验收材料。请以该提交复核，避免每日自动数据提交改变样本。此次交接只补充文档和校验清单，不改生产逻辑、阈值、17项指标、页面或工作流。

- [固定版本源码](https://github.com/weixb1818-cmyk/global-market-monitor/tree/66ad918c3235409dffd2fdbc3366c5d7b21e2673)
- [最后四项实现差异](https://github.com/weixb1818-cmyk/global-market-monitor/commit/0f789b042add00d859678bdf99f31c5f96efd2e9)
- [固定版本最新验收](https://github.com/weixb1818-cmyk/global-market-monitor/blob/66ad918c3235409dffd2fdbc3366c5d7b21e2673/verification/audit-fixes-2026-11-23/acceptance.json)
- [基线全部已跟踪文件的 SHA-256 清单](verification/audit-handoff-2026-11-23/manifest.json)
- [线上页面](https://weixb1818-cmyk.github.io/global-market-monitor/)及[快照](https://weixb1818-cmyk.github.io/global-market-monitor/data/snapshot.json)会继续变化，线上值应与其自身 `generated_at`、`update_context` 及独立行情日期一起核对。

`AUDIT.md` 与 README 保留了多轮历史记录：其中 5c32360、66项测试、来源失败0项对应早先版本，不代表最后修正后的结果。最新基线为77项Python测试通过、17项有值、WTI延迟、铜本轮更新失败并沿用历史。`acceptance.json` 内 `current_curve_checks` 是本地修改前检查记录，`current_spread_checks` 是更新后结果；请结合时间和字段说明判断，不把二者混为同一次结果。

原始需求见此次按工作区文件逐字归档的 [V1.0规格](docs/global_macro_dashboard_codex_spec.md)。相对于原文，后续用户明确要求或接受的范围调整有：DXY单独不足时允许有限风险提示并声明结论不完整；商品可考虑现货或期货但必须明示；内部学习用途不以公开展示授权审查阻塞接入；调度验收明确要求北京时间08:15。当前黄金合成参考价并非原建议COMEX近月，铜也未完成严格近月定义核实，应作为口径差异审查，不宣称原规格逐条无偏差。此处为开发方对后续要求的整理，仓库未归档完整聊天记录，不替代需求方确认。

## 范围与数据流

架构为静态 HTML/CSS/JavaScript + Python 更新脚本 + GitHub Actions/Pages。抓取→品种/单位/日期校验→规范化历史→变化及宏观规则计算→JSON快照→静态页面。没有交易、预测或新增经济数据模块。

| 复核对象 | 文件 / 重点 |
|---|---|
| 17项定义、实际渠道、单位、计算 | `config.json`、README 的17项方法表、`index.html` 方法说明 |
| 抓取及转换 | `scripts/update_data.py` 的各源适配器；当前 DXY 为新浪 DINIW、铜为东方财富 HG00Y，CNBC没有接入生产 |
| 历史与快照 | `data/history.json`、`data/snapshot.json`；前者是处理后观测，不是接口原始响应 |
| 宏观与时效 | `calculate`、`classify`、`risk_levels`、`compare_spreads`；`app.js` 打开页面时再次检查时效 |
| 失败记录 | 单项 `error`、快照 `sources_failed`、`data/last_attempt.json`、历史Git提交与Actions日志；没有单独的永久失败账本，部署成功不表示全部来源更新成功 |
| 发布及验证 | `.github/workflows/update.yml`、`scripts/verify_public.py`、`.github/workflows/verify.yml`、`tests/verify_live.cjs` |

黄金是合成参考价，WTI是库欣现货，铜是HG00Y且换月未核实，USD/JPY是ECB同日交叉参考汇率，USD/CNH是离岸合成参考价；这些口径不能读成统一的现货或期货收盘。DXY不以其他美元指数替代，CNH不以CNY替代。前期及20期变化由本项目历史计算，20期至少需要21个有效观测。

## 最后四项修改的验收点

| 修改 | 应复核的行为 | 对应测试 |
|---|---|---|
| 铜元数据 | `bjdw`检查报价单位、`zxbddw`独立检查0.0005美元/磅最小价位；历史未重新缩放 | `tests/test_portal_sources.py` |
| 铜历史 | 规范化前验证唯一日期/升序；合并后验证CME区间缺口；异常报错且保留历史，不补造、不用报价掩盖异常 | 同上；`snapshot.history_checks` |
| 两项利差 | 保留FRED直接值，缺少同日底层时明确显示“尚未完成同日底层交叉核验”，不跨日期相减 | `tests/test_dashboard.py`、`tests/test_ui.cjs` |
| 组合异常 | 同时过期且失败时并列显示“数据延迟 · 更新失败，沿用历史”；旧失败及全局机制仍保留 | `tests/test_ui.cjs`、`tests/verify_live.cjs` |

基线铜100条观测，2026-07-06至11-20，100个唯一升序日期，按当前CME日历区间预期100个交易日、缺口0。此结果只证明保留历史通过现有检查，不能证明本轮源端抓取成功或换月规则已核实。最后一轮铜历史未更新，回退报价处于盘中而被拒绝，旧100条逐值保留。

## 复核步骤

先在新的审计目录固定基线，避免改动日常更新工作区：

```bash
git clone https://github.com/weixb1818-cmyk/global-market-monitor.git global-market-monitor-audit
cd global-market-monitor-audit
git checkout --detach 66ad918c3235409dffd2fdbc3366c5d7b21e2673
```

清单在后续文档提交中发布，可下载后对固定基线逐文件校验。清单不包含自身，无循环哈希；SHA-256证明与已归档基线的一致性，不证明上游行情正确。

```bash
git show origin/main:verification/audit-handoff-2026-11-23/manifest.json > /tmp/market-audit-manifest.json
python3 - <<'PY'
import hashlib, json, pathlib, subprocess
m = json.load(open('/tmp/market-audit-manifest.json'))
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == m['baseline_commit']
for name, expected in m['files'].items():
    assert hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest() == expected, name
print('PASS:', len(m['files']), 'baseline files')
PY
```

运行既有计算及界面测试（需要Python 3.10+、Node.js，云端Python为3.12、浏览器任务Node为22）：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
node --check app.js
node tests/test_ui.cjs
python -m http.server 8000
```

打开 `http://localhost:8000/` 查看固定快照。浏览器按实际打开时间重算时效，因此日后重放时的延迟标签、宏观状态可能与归档截图不同；这不应通过把历史数据改成今天来消除。`python scripts/update_data.py` 会联网并覆盖本地数据，仅应在另一份可丢弃的克隆中执行，用来复测当前源端可用性；它不能复现过去原始响应。

浏览器复测可在另一终端安装 Playwright 后运行既有脚本，结果写入本地 `verification/`：

```bash
npm install --prefix /tmp/market-audit-browser playwright
/tmp/market-audit-browser/node_modules/.bin/playwright install chromium
NODE_PATH=/tmp/market-audit-browser/node_modules DASHBOARD_URL=http://localhost:8000/ node tests/verify_live.cjs
```

Linux如缺系统依赖，按Playwright提示安装；也可直接查验下列云端运行及其附件。测试及浏览器校验均由开发方配置，不是独立审计团队签字。

## 已有证据的边界

- [77项测试、更新、部署和公网回读](https://github.com/weixb1818-cmyk/global-market-monitor/actions/runs/45155204607)：`workflow_dispatch`，代码 `0f789b0`；数据写回提交 `85e9d3b`，快照时间 `2026-11-23T10:20:52.801426+00:00`，单项源失败1个。此次不是定时触发证明。
- [桌面及手机浏览器](https://github.com/weixb1818-cmyk/global-market-monitor/actions/runs/45155370843)：`workflow_run`，`headSha=85e9d3b`，检查17卡、日期、方法状态及布局。公开页通过测试不等于上游价格获得独立核验。
- [原生定时及时间证据](verification/audit-2026-11-23/schedule-timing.json)：两次 `schedule` 全链路成功，但比08:15目标晚约6小时40分、7小时29分。该调度证据早于最后四项修正，不能冒充修正后的一次准点定时验收。
- [最新修正验收材料](verification/audit-fixes-2026-11-23/)：JSON报告已入库；截图在浏览器 Actions 附件中，有保留期限，不承诺永久可下载。

## 尚未关闭的问题

| 项目 | 基线事实及影响 | 关闭所需证据 |
|---|---|---|
| 北京08:15准点更新 | 原生定时成功，但显著延迟；原因未查明 | 修正后连续自然日的目标/实际触发、更新、部署和回读时间；预先约定可接受延迟 |
| 铜连续品种定义 | HG00Y换月规则未核实，不称严格近月；源端间歇失败 | 供应商换月说明及滚动日前后历史核对、持续源端可用性记录 |
| 同日利差交叉核验 | 两项均 `not_comparable`，官方主值保留 | 相同日期的长短端底层收益率齐全，并与官方利差在配置容差内一致 |
| WTI时效 | 基线日期11-17，已标延迟 | 后续真实日线发布及恢复时效的记录，不补造日期 |
| 参考价与日历 | 合成/参考价不等于统一市场收盘；部分日历为近似 | 对相应发布规则、特殊休市及来源成分日期作进一步独立核对 |
| 原始取数可追溯性 | 不具备每轮每接口的完整原始HTTP响应归档；现有历史是规范化数据 | 如审计要求重放原始输入，应另行确定响应归档范围、时间戳/哈希及留存方案；不能事后补称已有原始证据 |
| 环境完全重现 | Python依赖为版本范围、Playwright未锁版本 | 若要求环境完全重现，需另行补充依赖锁定；测试结论属于当时环境，不保证未来依赖解析结果完全相同 |

项目为内部学习使用，未新增长期订阅。门户公开接口没有经过官方SLA或长期稳定性认证；代码公开不等于数据授权获证。CNBC仅为研究候选，未与现有历史拼接。

请审计团队分别给出：通过项、附条件通过项、未通过项和证据不足项；每个发现附基线提交、文件/函数、复现输入、实际结果与期望结果。尤其请独立核对品种身份、单位、源端时间与交易日，而不只确认页面能打开。
