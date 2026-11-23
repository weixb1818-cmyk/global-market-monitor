# 全球市场仪表盘审计交接说明

核查日期：2026-11-23。此文记录已实现内容、实测证据和剩余问题，不是审计通过结论。页面与仓库仍公开，按用户明确的内部学习用途使用数据，未新增付费订阅。

## 审计入口与固定版本

- [线上仪表盘](https://weixb1818-cmyk.github.io/global-market-monitor/) · [17项计算与来源说明](https://weixb1818-cmyk.github.io/global-market-monitor/#methodology) · [当前数据快照](https://weixb1818-cmyk.github.io/global-market-monitor/data/snapshot.json)
- 本次核对的数据及实现版本：[提交 5c32360](https://github.com/weixb1818-cmyk/global-market-monitor/commit/5c323605f0c3dddccb410ca9f6ed6f798128a282)。线上快照生成于 `2026-11-23T07:44:43.513085+00:00`，每个指标的行情日期另行保留。
- 固定版本的 [配置](https://github.com/weixb1818-cmyk/global-market-monitor/blob/5c323605f0c3dddccb410ca9f6ed6f798128a282/config.json)、[Python更新脚本](https://github.com/weixb1818-cmyk/global-market-monitor/blob/5c323605f0c3dddccb410ca9f6ed6f798128a282/scripts/update_data.py)、[快照](https://github.com/weixb1818-cmyk/global-market-monitor/blob/5c323605f0c3dddccb410ca9f6ed6f798128a282/data/snapshot.json) 和 [规范化历史](https://github.com/weixb1818-cmyk/global-market-monitor/blob/5c323605f0c3dddccb410ca9f6ed6f798128a282/data/history.json) 可用于复核；历史文件是解析和筛选后的观测，不标称接口原始响应。
- [证据目录](verification/audit-2026-11-23/) · [机器可读总表](verification/review-summary.json) · [文件SHA-256清单](verification/audit-2026-11-23/manifest.json)

## 本次完成的改动

1. 保持静态 HTML/CSS/JavaScript + Python 更新脚本 + GitHub Pages 架构，固定17项指标、单页蓝白界面和手机适配；没有增加就业、ISM、CPI、交易系统或预测模型。
2. 补齐六项此前缺失指标：DXY采用新浪DINIW；铜采用东方财富COMEX铜HG00Y；黄金采用明确标注的XAU/USD合成参考价；WTI采用EIA库欣现货；USD/JPY采用ECB同日参考汇率交叉换算；USD/CNH采用明确为离岸人民币的合成参考汇率。各项的口径差异公开说明，不将CNY、CFD、ETF或其他美元指数混入目标指标。
3. DXY接入历史后恢复完整宏观识别。DXY单独缺失、过期或20期不足时，使用实际利率、HY OAS、VIX、2Y提供“有限风险提示”，明确结论不完整；其他关键输入无效时停止趋势判断。既有分类优先级和可配置阈值保留。
4. 增加绝对风险提示：VIX≥25、HY OAS≥450bp分别提醒高位风险；不把“仍处高位”和“风险正在扩散”混为一谈。
5. 每项卡片和宏观信号保留独立日期，浏览器重新检查时效。利差只使用同日两端收益率核验；日期不齐时标记不可比较，不跨日期相减。不同provider、symbol、unit或series_definition切换时清除旧序列，避免不同口径拼接。
6. 增加缺失、过期和更新失败处理；失败保留真实历史，不改成今天。全源失败保留上次快照并报告失败。铜历史不可用时，可回退到已核实纽约17:00的收盘末笔快照，拒绝盘中、未来、非交易日时间；快照不标成官方结算价。历史不足时不计算变化，不用昨结伪造昨收或历史。
7. 添加17项指标的方法说明、README、来源核查记录、Python回归测试和云端桌面/手机验收；完整宏观信号下桌面17卡底部约890px，仍能在1440×900首屏展示。

主要实现提交：[4980642](https://github.com/weixb1818-cmyk/global-market-monitor/commit/4980642)、[0a4f786](https://github.com/weixb1818-cmyk/global-market-monitor/commit/0a4f786)、[42ec627](https://github.com/weixb1818-cmyk/global-market-monitor/commit/42ec627)。

## 当前17项数据及口径

下表对应固定版本快照，不代表所有市场同一时间的实时行情。最新一轮17项有值、来源更新失败0项，宏观模式为 `full`；WTI仍为延迟。

| ID | 指标 | 实际来源 / 代码 | 展示单位 | 数据日期 | 有效观测数 | 状态 |
|---|---|---|---|---|---:|---|
| `dxy` | 美元指数 DXY | 新浪 DINIW / `DXY` | 点 | 2026-11-20 | 120 | 正常 |
| `us2y` | 美国 2 年期国债 | FRED / `DGS2` | % | 2026-11-19 | 91 | 正常 |
| `us10y` | 美国 10 年期国债 | FRED / `DGS10` | % | 2026-11-19 | 91 | 正常 |
| `real10y` | 美国 10 年期实际利率 | FRED / `DFII10` | % | 2026-11-19 | 91 | 正常 |
| `spread10y2y` | 10Y − 2Y | FRED / `T10Y2Y` | bp | 2026-11-20 | 92 | 正常 |
| `spread10y3m` | 10Y − 3M | FRED / `T10Y3M` | bp | 2026-11-20 | 92 | 正常 |
| `vix` | VIX 波动率指数 | FRED / `VIXCLS` | 点 | 2026-11-19 | 94 | 正常 |
| `hy` | 高收益债信用利差 | FRED / `BAMLH0A0HYM2` | bp | 2026-11-19 | 94 | 正常 |
| `sp500` | 标普 500 指数 | FRED / `SP500` | 点 | 2026-11-19 | 93 | 正常 |
| `nasdaq100` | 纳斯达克 100 指数 | FRED / `NASDAQ100` | 点 | 2026-11-19 | 93 | 正常 |
| `gold` | 黄金参考价（合成） | Frankfurter 合成参考价 / `XAU/USD` | USD/oz | 2026-11-22 | 120 | 正常 |
| `wti` | WTI 库欣现货 | FRED / `DCOILWTICO` | USD/bbl | 2026-11-17 | 90 | 延迟 |
| `copper` | COMEX 铜（HG00Y） | 东方财富 101.HG00Y / `HG00Y` | USD/lb | 2026-11-20 | 100 | 正常 |
| `btc` | 比特币 BTC | CoinGecko UTC日末快照 / `bitcoin` | USD | 2026-11-22 | 93 | 正常 |
| `eth` | 以太坊 ETH | CoinGecko UTC日末快照 / `ethereum` | USD | 2026-11-22 | 93 | 正常 |
| `usdjpy` | 美元 / 日元（参考） | ECB 同日交叉参考汇率 / `USD/JPY` | JPY/USD | 2026-11-20 | 65 | 正常 |
| `usdcnh` | 美元 / 离岸人民币（参考） | Frankfurter 合成参考价 / `USD/CNH` | CNH/USD | 2026-11-22 | 114 | 正常 |

### 需要重点核对的两个指标

**DXY**：抓取渠道为新浪DINIW，底层目标为六种货币固定权重的美元指数，不是ICE直连。先校验报价代码及“美元指数”名称，再解析固定JSONP中的历史字符串，不执行返回的JavaScript。历史字段为日期、开、低、高、收；拒绝非法价格和重复日期。保守排除纽约当日日线，可能额外滞后一个交易日。120个观测用于项目自己的前期与20期计算。

- [新浪品种页](https://finance.sina.com.cn/money/forex/hq/DINIW.shtml)
- 历史：`vip.stock.finance.sina.com.cn/forex/api/jsonp.php/var%20_DATA=/NewForexService.getDayKLine?symbol=DINIW`
- [ICE指数定义](https://developer.ice.com/fixed-income-data-services/catalog/ice-data-indices-currency-indices)

**铜**：抓取渠道为东方财富，代码 `101.HG00Y`，元数据核对为HG／COMEX铜，单位美元/磅。接口历史价格直接读取；回退报价整数按4位精度除以10⁴，不对历史值再次缩放。当前有100个日线，前期及20期变化均可计算。换月细则尚未核实，名称为“COMEX 铜（HG00Y）”，不声称严格近月或固定月份，也不把其他数据商的昨结/昨收直接拼进历史。

- [东方财富品种页](https://quote.eastmoney.com/globalfuture/HG00Y.html) · [品种及单位元数据](https://futsse-static.eastmoney.com/redis?msgid=101_4_info)
- 日线：`push2his.eastmoney.com/api/qt/stock/kline/get`，关键参数 `secid=101.HG00Y, klt=101, fqt=0`
- 回退报价：`push2.eastmoney.com/api/qt/stock/get`，校验 `f57/f58/f107/f59`，以 `f86`判断日期和收盘时间；不使用`f60`生成虚构历史。

### 计算与规则复核点

- 价格、汇率、DXY：变化(%) = `(最新值 / 参考值 - 1) × 100`；不直接套用其他报价接口的`change_pct`。
- 收益率与利差的变化：`(最新百分数原值 - 参考百分数原值) × 100`，单位bp；利差水平为FRED原值×100。VIX变化按指数点计算。
- 近20期对比向前第20个有效观测，至少需要21个值；不是20个自然日，缺失和休市不补造。
- 黄金为合成参考价，非COMEX期货、LBMA定盘或现货收盘；USD/JPY为ECB同日EURJPY÷EURUSD；USD/CNH必须是Offshore/CNH，不能用CNY替代。WTI是库欣现货，非期货。
- 分类优先级：金融压力扩散 → 增长担忧定价 → 金融条件趋紧 → 温和宽松 → 中性/信号分歧。具体阈值和条件以固定版本配置及脚本为准，宏观状态是规则分类。

## 测试及已成功的工作流

| 验证 | 最新证据 | 结果 |
|---|---|---|
| Python及UI检查 | [11月23日定时运行](https://github.com/weixb1818-cmyk/global-market-monitor/actions/runs/45133283595) | 66项Python测试及JavaScript/UI检查通过 |
| 自动触发、更新、部署、公网回读 | 同上；[publication.json](verification/audit-2026-11-23/publication.json) | `event=schedule`，`cron=15 0 * * *`；更新成功，线上快照匹配运行记录 |
| 桌面及手机浏览器 | [云端运行](https://github.com/weixb1818-cmyk/global-market-monitor/actions/runs/45133420434)；[浏览器报告](verification/audit-2026-11-23/browser-report.json) | 17卡、无横向溢出、无页面JS异常、独立日期及17行方法说明检查通过 |
| HTML语法 | [校验返回](verification/audit-2026-11-23/html-validation.json) | 0个error；此项验证HTML语法 |

测试覆盖宏观规则及阈值边界、DXY有限模式、绝对风险、单位换算、数据缺失/过期/全源失败保留、休市、同日利差、历史不足、来源切换隔离、JSONP安全解析，以及铜元数据和时间验证。浏览器和自动测试不替代第三方对行情口径的实质审计。

## 定时触发：已验证自动流程，准点要求仍未满足

配置为UTC每日00:15，即北京时间08:15。已观察到两次原生`schedule`触发，并完成更新、部署和浏览器检查；但运行创建时间明显晚于计划时间：

| 日期 | 目标北京时间 | 运行创建时间（北京） | 相对目标延迟 | 成功记录 |
|---|---|---|---|---|
| 2026-11-22 | 08:15 | 14:54:51 | 6小时39分51秒 | [44995841393](https://github.com/weixb1818-cmyk/global-market-monitor/actions/runs/44995841393) |
| 2026-11-23 | 08:15 | 15:44:21 | 7小时29分21秒 | [45133283595](https://github.com/weixb1818-cmyk/global-market-monitor/actions/runs/45133283595) |

[时间证据JSON](verification/audit-2026-11-23/schedule-timing.json)。比较采用GitHub API的`createdAt`和配置的cron，不将手动运行当定时证明。延迟原因尚未查明，不能宣称“北京时间08:15准点自动更新”已经验收通过。`native_daily_schedule_verified=true`只表示触发类型、cron和发布回读相符，不检查执行准点性。若必须准点，需要另行解决调度保障并重新验收。

## CNBC研究状态

**CNBC尚未接入生产。** 当前`config.json`、线上快照及来源仍为新浪DXY／东方财富铜。

2026-11-22北京时间的只读研究发现，CNBC历史接口分别返回DXY 538条、铜500条记录；这是未经完整交易日/换月校验的研究记录数，不标称已经入库的有效观测。详见[实测记录](verification/audit-2026-11-23/cnbc-history-research.json)。因此，早先“CNBC没有可回溯历史”的说法已修正。

- `https://ts-api.cnbc.com/harmony/app/charts/1Y.json?symbol=.DXY`
- `https://ts-api.cnbc.com/harmony/app/charts/1Y.json?symbol=%40HG.1`

报价接口与历史接口同日价格不同：研究样本中DXY报价103.84、历史收盘103.807；铜报价5.465、历史收盘5.485。铜报价时间还出现周六及晚于核查时刻的情况，不能直接作为交易日期。名称里的Dec’26能显示对应月份，但`.1`不足以独立证明严格近月、主力选择及完整换月规则。暂未进行足够交易日的并行稳定性验证，不替换或拼接现有历史。

## 剩余问题与审计关注点

1. WTI数据仍截至2026-11-17，页面标为延迟；17项有值不表示所有日期都更新到当天。
2. 东方财富铜接口曾间歇失败；最新一轮正常，失败时仍需核对保留旧值及提示。HG00Y换月规则尚未核实。
3. 08:15准点执行未达标；原生定时自动流程已成功。
4. 部分数据为参考价或合成序列；各上游日期可能不同。日历为近似实现，特殊休市仍有复核空间。
5. CNBC仅完成研究探测，未通过生产切换验收。门户公开接口未核实有官方API额度或SLA；没有新增订阅，也不声称已取得数据公开分发许可。

## 后续四项审计修正

本轮仅修正铜的 `bjdw` 报价单位与 `zxbddw` 最小变动价位独立校验、铜历史日期完整性检查、两项曲线的实际交叉核验状态，以及过期与失败的组合显示。宏观函数、阈值、17项配置及页面布局未改变；本文件前述固定版本和2026-11-23证据仍作为历史验收记录保留。

铜异常日期/缺口不会被 `observations()` 的去重/排序掩盖；入库前发现异常则保留旧历史并标注错误。快照新增 `history_checks` 记录保留序列的实际检查结果，不表示源端更新一定成功，源端失败仍看该指标 `error` 和 `last_attempt.json`。缺口检查范围为已保留历史的首末日期；尾部时效继续按原交易日机制判断。报价单位和最小价位校验不改变既有 USD/lb 价格，也不会清空或重新缩放历史。

收益率曲线继续保留FRED直接发布值；方法说明动态显示 `not_comparable` 对应的“尚未完成同日底层交叉核验”，不存在跨日期相减。数据同时延迟且失败时，卡片并列显示两个状态并注明沿用历史。

本轮修正验收：[实现提交 0f789b0](https://github.com/weixb1818-cmyk/global-market-monitor/commit/0f789b0)；[77项测试、更新、部署及公网回读](https://github.com/weixb1818-cmyk/global-market-monitor/actions/runs/45155204607)成功；[桌面及手机浏览器验收](https://github.com/weixb1818-cmyk/global-market-monitor/actions/runs/45155370843)成功；HTML校验0错误。[完整验收记录](verification/audit-fixes-2026-11-23/acceptance.json)与[证据目录](verification/audit-fixes-2026-11-23/)已归档。现有铜100条历史逐值未变、100个唯一升序日期、预期CME交易日100个、缺口0；本轮源端更新失败时回退报价处于盘中而被拒绝，保留历史并提示失败。两项曲线仍明确标为尚未完成同日底层交叉核验，FRED官方主值保留。宏观函数与阈值、17项配置、页面布局保持不变。
