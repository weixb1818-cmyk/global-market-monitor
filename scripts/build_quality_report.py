#!/usr/bin/env python3
"""Generate an auditable Chinese report from retained real evidence."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def read(name):return json.loads((ROOT/name).read_text())

def main():
    snap=read('data/snapshot.json');research=read('verification/commodity-research.json');analysis=read('verification/macro-analysis.json');schedule=read('verification/schedule-10-days.json');evidence=read('data/source_evidence.json')
    checks={'dxy':'DINIW代码/名称、JSONP、OHLC、日期；非ICE直连', 'gold':'金衡盎司/币对、成分日期、修订；参考价', 'wti':'DCOILWTICO现货原值、实际日期/延迟', 'copper':'品种/单位/最小价位、100日期/CME；换月未完全核实', 'usdjpy':'ECB同日EUR两端交叉，正有限值', 'usdcnh':'Offshore/CNH元数据及币对，成分日期；非CNY', 'btc':'bitcoin/USD、完整UTC日样本，非单所收盘', 'eth':'ethereum/USD、完整UTC日样本，非单所收盘', 'spread10y2y':'官方主值及同日底层、>2bp告警', 'spread10y3m':'官方主值及同日底层、>2bp告警'}
    lines=['# 下一阶段数据质量与分析验收记录','',f"快照生成时间：`{snap['generated_at']}`。本报告由归档JSON生成；不同指标分别保留行情日期，17项有值不等于17项均成功更新。",'',
           '## 17项来源与质量核验','', '| 指标 | 实际免费来源 / 代码 | 单位 | 行情日期 | 状态 | 观测数 | 核验及边界 |','|---|---|---|---|---|---:|---|']
    for c in snap['indicators']:lines.append(f"| {c['name']} | {c['provider']} / `{c['symbol']}` | {c['unit']} | {c['as_of']} | {c['status']}"+('，本轮失败保留' if c.get('error') else '')+f" | {c.get('observation_count',0)} | {checks.get(c['id'],'官方FRED系列/有限值/独立日期；水平单位及变化换算，发布滞后不补造')} |")
    lines+=['','各来源链接和计算方法见[README](../README.md#17项指标的计算方法与数据来源)及[配置](../config.json)。没有接入商业API或新增订阅；门户公开接口的免费可访问性不构成正式数据授权或长期可用性保证。', '',
            '## P0：异常状态边界','',
            '宏观与绝对高位提示只接受 status=ok、无error且有限数值；方向分类还要求有效20期变化。DXY单独异常时保留原有限风险提示，其他关键输入异常时停止分类。未知状态不放行。失败价格可展示，但小字只说明沿用历史。全源失败保留原快照，前端依据最后尝试记录阻断旧快照的正常结论。异常响应、脚本到JSON到前端以及真实Chromium失败路径均有测试。', '',
            '## 商品口径与适用性','',
            '黄金：XAU为金衡盎司，报价USD/oz。Frankfurter多源合成参考价并非COMEX成交价、LBMA定盘或统一现货收盘。保留每个未排除来源的日期，标记混合日期，记录同日历史修订；不在本轮更换定义或重新缩放历史。']
    g=research.get('gold',{})
    lines +=[f"本次14日研究窗口有{g.get('n',0)}个同日NBP交叉参考样本：NBP黄金PLN/克 × 31.1034768 ÷ 同日USDPLN。合成值相对该参考的绝对偏差中位数{g.get('median_abs_difference_pct',0):.3f}%，最大{g.get('max_abs_difference_pct',0):.3f}%；有{g.get('blend_rows_with_mixed_dates',0)}个研究行混合不同来源日期。NBP也是合成源之一，该比较并非完全独立，不证明可交易价准确性。",'',
              '依据：[Frankfurter方法](https://frankfurter.dev/methodology/)、[其历史缓存/修订说明](https://frankfurter.dev/python/)、[NBP官方API](https://api.nbp.pl/en.html)。逐日值、来源机构及哈希见[商品研究JSON](../verification/commodity-research.json)。本轮[接口探测记录](../verification/reference-probes-2026-11-23.json)显示旧FRED黄金系列404、CNBC黄金历史403；没有绕过限制或用其替换生产。', '',
              'WTI：EIA库欣实物现货，经FRED DCOILWTICO提供；与NYMEX交割月份期货、展期收益不同。保留数据所属日期；过期时只显示日期与延迟，不输出方向。未过期也仅解释已知现货历史趋势，明确非当日期货交易信号。依据：[EIA定义](https://www.eia.gov/dnav/pet/TblDefs/pet_pri_spt_tbldef2.asp)。', '',
              '铜：保留101.HG00Y、USD/lb、bjdw报价单位、zxbddw 0.0005美元/磅最小价位及CME交易日检查。公开品种页和合约元数据没有提供足以确定连续序列换月日期、选约及复权方式的方法。交割月份不是换月算法。继续标记“换月口径未完全核实”；跨期变化不是可交易期货全收益，不推断换月点、不另造价格拼接。依据：[品种页](https://quote.eastmoney.com/globalfuture/HG00Y.html)、[元数据](https://futsse-static.eastmoney.com/redis?msgid=101_4_info)。', '',
              '## 两项利差实际核验','', '| 利差 | 同日样本数 | >2bp告警 | 最近共同日期 | 官方 / 底层计算 | 差值 |','|---|---:|---:|---|---|---:|']
    for check in snap['spread_history_checks']:
        r=check['latest_common']
        lines.append(f"| {check['id']} | {check['observations']} | {check['warnings']} | {r['as_of'] if r else '无'} | "+(f"{r['official_bp']:.2f} / {r['same_date_bp']:.2f} bp | {r['signed_difference_bp']:.6f} bp |" if r else '— | — |'))
    lines+=['','最新官方利差日期与底层日期不齐时仍为not_comparable，不把最近共同日期的通过当成最新日期已核验。实际长短端值、带符号差值、容差及所有比较见snapshot的spread_checks/spread_history_checks。官方FRED利差使用财政部直接序列，DGS系列来自H.15，遇差异需告警并保留官方主值，不强行改价。依据：[T10Y2Y](https://fred.stlouisfed.org/series/T10Y2Y)、[T10Y3M](https://fred.stlouisfed.org/series/T10Y3M)。', '',
            '## 宏观历史分析与投资参考价值','',
            '冻结config原阈值及优先级，不事后调参。美元与实际利率同升可组织融资与估值压力信息；VIX与HY共同恶化可组织压力扩散信息；曲线变化帮助分辨长短端驱动，但不直接证明增长或衰退。信号冲突、日期跨度及异常输入应明确不确定性。这些是规则的解释用途，投资预警能力需要独立结果验证。', '',
            f"严格可用性复盘：以每日第一份真实归档快照为输入，可用时间取生成时间与Git提交时间的较晚者，共{len(analysis['strict_archived_availability']['signals'])}天；成熟的资产/5或20期后续窗口共{analysis['strict_archived_availability']['mature_outcomes']}个。不得用今天下载的早期历史生成当年可用信号。本轮无法从严格样本中给出已成熟的成功/失败案例，也无法证明预测能力。", '',
            '以下仅为当前版本历史的描述性对照，**不是无未来信息泄漏的回测**：假设2或4个自然日发布延迟，使用原规则；这些假设不能消除历史修订、未知实际发布时间。统计有重叠窗口、小样本及状态不均衡，不能据此评价实盘收益。', '',
            '| 假设延迟 | 资产 | 后续期数 | 规则状态 | 重叠日样本 / 状态变化样本 | 平均收盘最大回撤 |','|---:|---|---:|---|---|---:|']
    for scenario in analysis['descriptive_current_vintage']['lag_scenarios']:
        for r in scenario['groups']:
            if r['n_daily_overlapping'] and r['state']!='数据不足：暂不判断':lines.append(f"| {scenario['assumed_calendar_day_lag']}天 | {r['asset']} | {r['horizon']} | {r['state']} | {r['n_daily_overlapping']} / {r['n_state_transitions']} | {r['mean_max_drawdown_pct']:.2f}% |")
    lines+=['','成功与失败对照使用预先固定标签：警示状态包括压力扩散、增长担忧、条件趋紧；后续5期收盘最大回撤≤-3%、20期≤-5%记为风险事件。这是评估标签，未改宏观阈值；预警后无回撤也可能是合理风险提示，不能直接视作策略失败。案例按时间取第一例，未挑最大跌幅。', '',
            '| 假设延迟 | 描述性案例 | 信号日 | 状态 | 标普500后续20期收盘最大回撤 |','|---:|---|---|---|---:|']
    names={'warning_and_drawdown':'预警后回撤','warning_without_drawdown':'预警后未达回撤标签（误报对照）','missed_drawdown':'未预警但发生回撤（漏报对照）','no_warning_no_drawdown':'未预警且未达回撤标签'}
    for scenario in analysis['descriptive_current_vintage']['lag_scenarios']:
        for kind,r in scenario['first_cases'].items():lines.append(f"| {scenario['assumed_calendar_day_lag']}天 | {names[kind]} | {r['signal_at'][:10]} | {r['state']} | {r['outcomes']['sp500']['20']['max_close_drawdown_pct']:.2f}% |")
    lines+=['','完整每日信号、独立输入日期、曲线变化、三项资产5/20期收益/入场后不利变化/峰谷回撤、阈值及历史哈希见[分析JSON](../verification/macro-analysis.json)，复核命令为`python scripts/analyze_macro.py`。计量采用信号后的第一个完整资产日收盘为参考，再观察5/20个有效观测间隔；不是日内回撤，不假设能在信号前收盘价成交；窗口有缺失预期交易日则拒绝计量，股票按NYSE交易日、BTC按UTC自然日。当前证据支持解释型风险整理，尚不足以宣称可预测涨跌或有可交易优势。', '',
            '## 调度与审计复现','',
            f"计划仍为北京时间08:15；新增08:45和10:15免费补偿检查，若当天已有状态ok的更新则跳过，部分/全失败可重试。不承诺消除GitHub相关性延迟。当前10自然日窗口只有{schedule['observed_days']}天实际原生schedule记录，十日验收尚未完成；上线前、待运行、漏跑明确区分。实际创建/启动/最后作业完成时间和链接见[十日记录](../verification/schedule-10-days.json)。备份与主任务分开标识；未部署的跳过任务不会伪造公网回读或浏览器验收。页面超过计划2小时仍没有当日更新记录会提示延迟/漏跑，该提示宽限不是宏观阈值。", '',
            f"Python直接及传递依赖已固定，运行器固定Ubuntu 24.04、Playwright固定1.58.2；每次取数记录请求起止、HTTP状态、响应SHA-256、来源日期、修订和生成文件哈希。本轮记录{len(evidence['requests'])}次HTTP请求、{len(evidence['revisions'])}条同日价格修订。默认只保存允许复用的ECB统计XML受限响应，其余保留元数据/哈希，不把哈希冒充原始行情已归档。记录见[data/source_evidence.json](../data/source_evidence.json)，历次版本可通过Git查看，云端另保存artifact。依据：[ECB复用说明](https://www.ecb.europa.eu/services/disclaimer/html/index.en.html)。", '',
            '未来仍需：真实连续10日运行；更多成熟的前瞻样本或具备全部输入历史发布版本的资料；核实HG00Y换月规则；最新日期底层美债补齐；长期观察合成参考价修订及免费接口可用性。没有用付费数据、虚构样本或调参填补这些缺口。']
    (ROOT/'docs/DATA_QUALITY_REPORT.md').write_text('\n'.join(lines)+'\n')

if __name__=='__main__':main()
