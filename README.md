# 全球市场每日观察

中文单页静态金融市场仪表盘。页面读取已生成的 JSON；定时 Python 脚本获取行情、计算变化、识别宏观状态。不会用模拟数据填充缺项。首次仓库内快照来自实际 FRED 和 CoinGecko 请求，生成时间及每项行情日期以页面为准。

## 已部署网址与验证

公开访问：<https://weixb1818-cmyk.github.io/global-market-monitor/>，无需登录。

源码仓库：<https://github.com/weixb1818-cmyk/global-market-monitor>，可见性为 **Public**，任何人均可查看代码、已提交的数据与工作流记录。每日自动更新和部署已启用，时间为 UTC 00:15／东京 09:15；可在 Actions 手动触发。

独立验证包括 W3C Nu HTML Checker（检查 HTML 语法）与 GitHub 云端 Chromium（桌面 1440×900、手机 390×844），后者检查 17 张卡片、缺失提示、JavaScript 异常和横向滚动，并上传实际页面截图。可在 **Actions → Independent public browser verification → Run workflow** 重新验证，下载 `public-browser-verification` 附件查看报告和截图。HTML 语法通过不等于行情数值获得第三方审计，尚缺的行情项目仍以页面提示为准。

## 本地运行

需要 Python 3.10+、联网和 IANA 时区数据库。Windows 请先安装 Python，并在虚拟环境额外安装 `tzdata`。

```bash
cd /home/ubuntu/panel
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python scripts/update_data.py      # 可重复执行；可选密钥见下文
python -m http.server 8000
```

浏览器打开 <http://localhost:8000/>。请通过 HTTP 服务打开，不要双击 `index.html`：浏览器通常禁止 `file://` 页面读取本地 JSON。若只查看现有快照，可直接运行 HTTP 服务，不必先更新。

测试：

```bash
python -m unittest discover -s tests -v
node --check app.js
node tests/test_ui.cjs
```

## 17项指标的计算方法与数据来源

这里区分指标本身的定义与本项目的计算。指数、收益率和 OAS 采用供应商发布值；本项目负责筛选已完成日线、单位转换、前期／近20期变化及规则解读。来源链接同时注明原始发布机构、实际接口与尚未接入的目标源；当前实际来源和日期以各卡片为准。

**A · 价格／汇率／价格指数**：变化率 = (最新原值 ÷ 参考原值 − 1) × 100%，包括 DXY、两项股指、黄金／WTI／铜、BTC、ETH 和两个汇率。参考值为 0 时显示“—”。

**B · 收益率／利差**：原始单位均为百分数值：变化(bp) = (最新原值 − 参考原值) × 100。收益率水平仍显示 %；两项国债利差及 HY OAS 水平 = 原值 × 100，以 bp 显示。例如 4.00% → 4.25% 为 +25bp；利差 0.30% 为 +30bp。

**C · VIX**：变化(点) = 最新指数值 − 参考指数值，例如 20 → 25 为 +5 点。

**前期与近20期**：前期参考上一有效观测；近20期参考向前第20个有效观测，至少需要21个值。20期不是20个自然日，也不保证所有指标比较区间相同。休市／空值不补造观测；不足时显示“—”。计算使用原始精度，页面显示值另行四舍五入。

| 指标 | 定义及本项目处理 | 来源与接入情况 | 单位／变化 |
|---|---|---|---|
| 美元指数 DXY | ICE 六种货币固定权重的几何加权现货美元指数。直接采用授权指数日线，不在本项目用汇率篮子重建。 | [ICE 指数定义](https://developer.ice.com/fixed-income-data-services/catalog/ice-data-indices-currency-indices)；[Barchart DXY00 API](https://www.barchart.com/ondemand/api/getHistory)。拟接入 ICE／Barchart DXY00；目前缺授权源。 | 点；变化用 A |
| 美国 2 年期国债 | 美国国债收益率曲线上的 2 年固定期限名义收益率，采用官方发布值。 | [FRED DGS2](https://fred.stlouisfed.org/series/DGS2)。原始发布：美联储 H.15；由 FRED 提供。 | %；变化用 B |
| 美国 10 年期国债 | 美国国债收益率曲线上的 10 年固定期限名义收益率，采用官方发布值。 | [FRED DGS10](https://fred.stlouisfed.org/series/DGS10)。原始发布：美联储 H.15；由 FRED 提供。 | %；变化用 B |
| 美国 10 年期实际利率 | 10 年固定期限通胀保值国债（TIPS）的实际收益率，直接读取 DFII10，不用名义利率减当期通胀估算。 | [FRED DFII10](https://fred.stlouisfed.org/series/DFII10)。原始发布：美联储 H.15；由 FRED 提供。 | %；变化用 B |
| 10Y − 2Y | 同日 10Y 收益率 − 2Y 收益率。主值采用官方 T10Y2Y，原值乘 100 转成 bp；另以同日 DGS10、DGS2 核验，不跨日期相减。 | [FRED T10Y2Y](https://fred.stlouisfed.org/series/T10Y2Y)。FRED 官方利差；底层来自美国财政部。 | bp；变化用 B |
| 10Y − 3M | 同日 10Y 收益率 − 3M 收益率。主值采用官方 T10Y3M，原值乘 100 转成 bp；同日 DGS10、DGS3MO 仅辅助核验。 | [FRED T10Y3M](https://fred.stlouisfed.org/series/T10Y3M)；[辅助 DGS3MO](https://fred.stlouisfed.org/series/DGS3MO)。FRED 官方利差；底层来自美国财政部。 | bp；变化用 B |
| VIX 波动率指数 | Cboe 根据标普 500 指数期权价格计算的未来约 30 天年化隐含波动率指数。读取官方指数日收盘，不由本项目重新计算。 | [FRED VIXCLS](https://fred.stlouisfed.org/series/VIXCLS)；[Cboe 方法说明](https://www.cboe.com/tradable-products/volatility-trading/)。原始发布：Cboe；由 FRED 提供。 | 点；变化用 C |
| 高收益债信用利差 | ICE BofA 美国高收益债指数的期权调整利差（OAS）：成分债相对国债即期曲线的期权调整利差按市值加权；原值乘 100 转为 bp。 | [FRED BAMLH0A0HYM2](https://fred.stlouisfed.org/series/BAMLH0A0HYM2)。原始发布：ICE Data Indices；由 FRED 提供。 | bp；变化用 B |
| 标普 500 指数 | S&P 500 流通市值加权价格指数的日收盘。直接读取指数点位，不含股息再投资，不使用 ETF 价格。 | [FRED SP500](https://fred.stlouisfed.org/series/SP500)；[S&P 指数方法](https://www.spglobal.com/spdji/en/methodology/article/sp-us-indices-methodology/)。原始发布：S&P Dow Jones Indices；由 FRED 提供。 | 点；变化用 A |
| 纳斯达克 100 指数 | Nasdaq-100 大型非金融企业的修正市值加权价格指数日收盘，不是纳斯达克综合指数，也不是 ETF。 | [FRED NASDAQ100](https://fred.stlouisfed.org/series/NASDAQ100)；[Nasdaq 指数方法](https://beta.indexes.nasdaq.com/docs/methodology_NDX.pdf)。原始发布：Nasdaq；由 FRED 提供。 | 点；变化用 A |
| 黄金参考价（合成） | XAU 每金衡盎司美元的多源合成参考价；由 Frankfurter 根据央行等机构的参考报价合成。本项目读取其 XAU/USD，不将其视作 COMEX 期货、LBMA 定盘价或现货日收盘。 | [Frankfurter XAU](https://api.frankfurter.dev/v2/currency/xau)；[方法及使用说明](https://frankfurter.dev/)。已接入免费合成参考历史。各上游可能不同日，来源日期另行保留；数值可能偏离当日现货。 | USD/oz；变化用 A |
| WTI 库欣现货 | WTI 库欣现货日价 DCOILWTICO，由 EIA 发布、FRED 分发，直接采用 USD/bbl 原值；不是 NYMEX 近月期货，无期货换月拼接。 | [FRED / EIA DCOILWTICO](https://fred.stlouisfed.org/series/DCOILWTICO)；[EIA 使用许可](https://www.eia.gov/about/copyrights_reuse.php)。已接入免费现货历史。发布有滞后，按真实日期显示；超过时效阈值时标为延迟。 | USD/bbl；变化用 A |
| COMEX 铜近月期货 | COMEX 铜近月期货日收盘，按每磅美元报价；若源按美分报价，供数方须先除以 100 转为美元。换月规则待核验，不使用 LME 铜或现货替代。 | [CME 铜合约定义](https://www.cmegroup.com/markets/metals/base/copper.contractSpecs.html)。拟用授权期货日线；富途当前无权限。 | USD/lb；变化用 A |
| 比特币 BTC | CoinGecko bitcoin 的美元价格。取 00:00 UTC 的每日样本并标记为前一 UTC 日期，作为该日结束快照；不代表某一家交易所的收盘价。 | [CoinGecko market_chart](https://docs.coingecko.com/reference/coins-id-market-chart)。已接入 CoinGecko；vs_currency=usd，interval=daily。 | USD/BTC；变化用 A |
| 以太坊 ETH | CoinGecko ethereum 的美元价格。取 00:00 UTC 的每日样本并标记为前一 UTC 日期，作为该日结束快照；不采用 ETH/BTC 交叉盘。 | [CoinGecko market_chart](https://docs.coingecko.com/reference/coins-id-market-chart)。已接入 CoinGecko；vs_currency=usd，interval=daily。 | USD/ETH；变化用 A |
| 美元 / 日元（参考） | ECB 同日参考交叉汇率：JPY/USD = EURJPY ÷ EURUSD。两条欧元参考汇率须有相同日期；代表日参考价，不是纽约收盘或实时美元兑日元。 | [ECB 参考汇率](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html)；[ECB 转载条件](https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html)。已接入 ECB 官方90日 XML 历史。项目已明确披露交叉换算；注明 ECB 来源。 | JPY/USD；变化用 A |
| 美元 / 离岸人民币（参考） | USD/CNH 多源合成参考汇率，每1美元对应的离岸人民币数。接口目录须明确为 Offshore，响应须为 USD/CNH；不接受 CNY，不标为纽约收盘。 | [Frankfurter CNH](https://frankfurter.dev/currencies/cnh/)；[合成方法及使用说明](https://frankfurter.dev/)。已接入免费历史；保留非异常上游的独立日期，跳过全部来源沿用旧日的行。部分上游日期可能不同。 | CNH/USD；变化用 A |

**更新与日期**：每天北京时间08:15调度一次，可能排队；快照生成时间不等于每项行情日期。美债、股指、VIX、OAS 和 DXY 在纽约18:00前保守排除当日数据；期货适配器在纽约17:00前排除当日数据，且须提供已收盘日期。CoinGecko 仅取已完成 UTC 日。ECB 和 Frankfurter 当前只接收前一 UTC 日及更早的参考观测；合成序列保留各来源日期，不把全部来源均为旧日的沿用行当新观测。Twelve Data 适配器保留但当前未使用。每张卡保留独立“截至”日期；来源失败保留历史并标识失败／延迟，不把旧值改成今天。

**期货口径**：依据本次允许商品使用现货的要求，WTI 已明确改为 EIA 库欣现货；黄金改为 XAU/USD 合成参考价，明确不是现货收盘或期货。旧期货历史不得拼入新序列。铜仍未接入，保留原 COMEX 铜近月定义；如未来接入期货，须先确认换月和报价单位。

FRED 的利差主系列与收益率分项可能不同步。只有同一日期的两端收益率齐全时才核验利差，核验值不会替换官方主系列。页面的完整说明位于 [计算方法与数据来源](https://weixb1818-cmyk.github.io/global-market-monitor/#methodology)。

## 本轮六项数据源核查（2026-11-21）

已有真实值由11/17提高为15/17，其中14项未过期、WTI一项发布延迟；缺失仍为 DXY 和铜。新增四项无需Key，没有注册或购买订阅。黄金和CNH为参考序列，不能按交易所收盘价理解。

| 指标 | 推荐来源 | 免费额度及限制 | 最新实测日期 | 接入难度／结果 |
|---|---|---|---|---|
| dxy | ICE / Barchart DXY00；东方财富 UDI／新浪 DINIW 为待授权候选 | 未核实有免费公开展示授权；网页接口无已公布官方额度 | 2026-11-20 | 较高：需核实ICE原始指数来源和公开展示授权；未接入；不使用其他美元指数。 |
| gold | Frankfurter XAU/USD 合成参考价 | 免费，无API Key、无日/月配额；有防滥用限速 | 2026-11-20 | 低：2请求/日，含元数据与历史；已接入；不是现货收盘或COMEX期货。 |
| wti | EIA 库欣 WTI 现货，经 FRED DCOILWTICO | 免费CSV，无需Key；无可承诺的无限调用额度，每日1次 | 2026-11-17 | 低：复用FRED适配器；已接入，但当前发布滞后，标为延迟。 |
| copper | 优先获授权的COMEX/LME日线；Gold API HG仅为候选 | Gold API现价免费免Key；免费历史10次/小时，需要免费注册Key | 2026-11-20（新浪CFD）；Gold API只有11-21抓取时间 | 中至高：先确认官方报价单位、基准及历史权限；未接入：Gold API铜单位未在官方文档核实；新浪CFD不当期货；门户站外展示需许可。 |
| usdjpy | ECB 日参考汇率：同日EURJPY÷EURUSD | 免费官方XML，无Key；未公布日/月硬配额，每日1次 | 2026-11-20 | 低：同日两条汇率交叉换算；已接入，注明ECB与换算，非纽约收盘。 |
| usdcnh | Frankfurter USD/CNH 多源合成参考汇率 | 免费，无API Key、无日/月配额；有防滥用限速 | 2026-11-20 | 低：2请求/日；核实Offshore元数据及准确货币对；已接入；保留来源日期，不能用CNY替代。 |

- **东方财富**：实测美元指数 `100.UDI`、日元 `119.USDJPY`、离岸人民币 `133.USDCNH` 各100条日线，最新11月20日；商品页面也存在，但本机商品历史请求失败。其[法律声明](https://about.eastmoney.com/home/legal)要求站外转载传播取得书面许可，未把无需Key视为可公开再分发。
- **新浪**：已实测 DXY、USD/JPY、USD/CNH 与 GC／CL／HG 历史，最新11月20日；商品页面存在CFD标注，不能冒充交易所期货。[用户协议第6.1节](https://finance.sina.com.cn/roll/2021-05-12/doc-ikmxzfmm2033220.shtml)限制未获许可的站外展示。
- **腾讯**：实测到三个商品及日元报价；美元指数返回8月10日旧时间，日线请求返回 `param error`；本次CNH候选代码没有返回有效行情。没有据此断言腾讯完全没有CNH，只是尚未核实准确代码、日线历史及公开转发许可。
- 这三家网页接口的正式免费日／月配额和SLA未找到，少量测试成功不代表无限额或长期稳定。

**公开使用依据**：[EIA 政府数据重用](https://www.eia.gov/about/copyrights_reuse.php)、[ECB 转载及修改披露条件](https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html)、[Frankfurter 合成汇率商业使用FAQ](https://frankfurter.dev/)。Frankfurter 的[数据条款](https://frankfurter.dev/license/)仍要求注意上游条件；项目采用其明确允许免费使用的合成路由，不以MIT代码许可代替数据授权。

CNH 的元数据明确为 Chinese Renminbi Yuan Offshore；已核查[印尼央行原始目录](https://www.bi.go.id/en/statistik/informasi-kurs/transaksi-bi/default.aspx)单列CNH、CNY，未将CNY映射为CNH。黄金元数据明确为 Gold (Troy Ounce)。合成值保留每个参与来源的日期和被排除异常源的过滤，不补出纯沿用日期。

Gold API 可免费读取XAU及HG现价，官方允许网站使用；历史为免费10次/小时但需要注册Key。其黄金金衡盎司单位有官方说明，铜单位及具体基准未明确，因此未把HG代码当成足够依据。使用贵金属现价或参考价都不能静默覆盖期货历史。

完整、可机读的核查记录：[data/source_research.json](data/source_research.json)。本次最新日期不保证未来每次更新都相同，页面始终显示实际源日期。

## 数据源、定义与当前限制

| 指标 | 实现 | 接入情况 / 口径 |
|---|---|---|
| 2Y、10Y、10Y 实际利率、10Y−2Y、10Y−3M、VIX、HY OAS | FRED | 对应规格中的原始系列；不跨日期相减。可选官方 FRED API Key；无 Key 时尝试 FRED Graph CSV。 |
| 标普 500、纳斯达克 100 | FRED `SP500`、`NASDAQ100` | 指数本身的日收盘；不是 ETF。FRED 有发布滞后，页面显示各自日期。指数数据受版权约束，发布前应核对相关权利及许可，尤其 SP500 标记了预先批准要求。 |
| BTC、ETH | CoinGecko 官方 `market_chart` | 取每日 **00:00 UTC** 样本作为前一 UTC 日结束快照；忽略当前未完成日期及日内样本。生产环境建议配置 Demo API Key。 |
| USD/JPY、USD/CNH | ECB 官方参考汇率／Frankfurter 离岸人民币合成参考汇率 | 两者均已免费接入；单位、日期与计算见上表。原 Twelve Data 适配器保留但不启用，不需要上传其账户密钥。 |
| DXY | Barchart DXY00 官方 API／授权源适配器 | 已实现现货指数品种校验；当前未配置授权凭证，故显示缺失。不用贸易加权美元指数或美元指数期货替代。 |
| 黄金、WTI、铜 | Frankfurter XAU/USD 合成参考价／EIA 库欣 WTI 现货／铜仍待授权 | 本次明确改变黄金和 WTI 的定义并重置原序列，避免混用期货历史。铜的品种、单位或公开展示授权尚未同时核实。 |

富途 OpenD 是本机进程，GitHub Actions 不能访问 `127.0.0.1` 上的本机 OpenD；如以后取得权限，应在本机运行更新任务并将结果发布，或使用自托管 Actions runner，同时完成品种、授权与换月验证。当前代码不会尝试买行情卡，也不会发交易请求。

FRED 的 ICE HY OAS 历史自 2026 年 4 月起在 FRED 仅保留最近三年；它是信用利差而非收益率。FRED、Nasdaq、S&P、ICE、CoinGecko 和 Twelve Data 的数据各有使用、展示或再分发条件；本项目代码不授予数据再分发许可。公开部署前请按所用账户与数据源条款确认权限。参见 [FRED SP500](https://fred.stlouisfed.org/series/SP500)、[FRED HY OAS](https://fred.stlouisfed.org/series/BAMLH0A0HYM2)、[富途行情权限](https://openapi.futunn.com/futu-api-doc/intro/authority.html)、[Twelve Data EOD 权限](https://support.twelvedata.com/en/articles/12682324-end-of-day-eod-pricing-market-data)。

## 配置密钥及更新

环境变量供更新脚本使用，绝不会写入浏览器代码：

```bash
export FRED_API_KEY='你的FRED密钥'             # 可选；不配置则使用CSV
export COINGECKO_API_KEY='你的CoinGecko Demo密钥'  # 推荐
export TWELVE_DATA_API_KEY='你的Twelve Data密钥'   # 保留的可选适配器；当前免费方案不需要
python scripts/update_data.py
```

请勿将密钥加入 Git 仓库或填入页面。已找到本机 Twelve Data 配置并验证两个货币对的日线读取；公开展示授权未确认，因此尚未配置线上 Secret。API 返回的错误、网络限制或无权限会显示为缺失／延迟／更新失败，保留已有有效数据。脚本日志不会输出 API Key 或请求 URL。

### 自有或获授权数据商的适配器

当前 DXY 和铜仍可通过授权适配器接入。原黄金、WTI 期货适配器也保留：只有显式修改 config.json 恢复对应期货定义和 provider=external 后才启用，不会自动替换当前免费序列。接口可分别通过 `MARKET_DATA_DXY_URL`、`MARKET_DATA_GOLD_URL`、`MARKET_DATA_WTI_URL`、`MARKET_DATA_COPPER_URL` 指定。URL 应返回按时间递增或无序均可的 JSON：

```json
{"symbol":"DXY","unit":"点","source":"已授权数据源及品种说明","daily_close":true,"complete_through":"YYYY-MM-DD","observations":[{"date":"YYYY-MM-DD","value":123.45}]}
```

这只是字段格式示意，`123.45` 不是项目行情，不能作为真实数据发布。生产响应必须提供至少 21 个真实有效观测、准确的行情日期、已完成交易时段的最后日期 `complete_through` 和单位，并经权利方许可。期货的 `symbol` 分别是 `GC_FRONT`、`CL_FRONT`、`HG_FRONT`，单位分别是 `USD/oz`、`USD/bbl`、`USD/lb`。服务必须保证每个历史点采用一致的近月选取和换月拼接规则，并在 `source` 描述该规则。脚本拒绝元数据不匹配的响应；它不能独立证明供应商确实履行了口径承诺，接入前需要自行核验。URL 如果含密钥，请放 Secret，不能放代码或网页。

## GitHub Pages 与自动更新

1. 将项目放入自己拥有的 GitHub 仓库，提交源码、`data/` 和 `.github/workflows/update.yml`，不要提交 `.venv` 或密钥。
2. 在仓库 **Settings → Secrets and variables → Actions** 设置需要的 `FRED_API_KEY`、`COINGECKO_API_KEY`、`TWELVE_DATA_API_KEY` 以及授权行情适配器 URL。缺少可选密钥时相关卡片标记缺失；不得向仓库提交秘密。
3. 在 **Settings → Actions → General → Workflow permissions** 允许 workflow 读写仓库内容；如果分支保护不允许推送，请调整为允许该自动化或使用其他发布流程。
4. 在 **Settings → Pages → Build and deployment** 将 Source 设为 **GitHub Actions**。本项目工作流会在更新 JSON 后显式上传并部署静态页面。公开站点及行情数据的再分发必须先符合各数据源许可。
5. Actions 中手动运行 **Update daily market snapshot** 验证。此后工作流按每天 UTC 00:15（北京时间 08:15、东京 09:15）调度并提交 JSON；GitHub 定时任务可能排队延迟。页面地址通常为 `https://<用户名>.github.io/<仓库名>/`，具体地址以 Pages 设置显示为准。

自动提交只有真正有修改时才产生。全源失败时保留上次 `snapshot.json`，更新 `last_attempt.json` 并使任务失败；部分来源失败时保留对应历史，页面标识失败或延迟。手动刷新：在 Actions 选择 workflow → **Run workflow**，或本地执行更新脚本。

## 计算、日期和故障处理

- `config.json` 包含固定 17 项配置与阈值；宏观规则的优先级为金融压力扩散、增长担忧定价、金融条件趋紧、温和宽松、中性／信号分歧。DXY 单独缺失／过期时降为明确标识的有限提示；其他关键20期缺失／过期则停止趋势判断。
- 价格类按百分比，VIX 按点，利率与利差变化按 bp；利差水平以 `FRED 原值 × 100` 显示 bp。20 期比较当前值与该系列向前第 20 个有效观测。
- FRED 按每个系列自身定义取日值（WTI 为 EIA 现货价，并非所有系列都是收盘价），纽约18:00前保守排除当天数据；ECB、Frankfurter 和 CoinGecko 只接收前一完整 UTC 日及更早日期。参考序列不标为市场收盘，合成来源可能不同日，逐项保留来源日期。
- NYSE 交易日历用于美股、VIX 和 HY；美债按 NYSE 休市日与美国联邦假日的并集近似；期货使用 CME 会话，外汇使用工作日与主要全球休市日。连续超过两个预期交易日无更新才标延迟；加密日线距其 UTC 收盘超过 36 小时标延迟。特殊休市或来源停更仍应结合该源发布说明与独立日期判断。
- 每次成功先校验、计算、再使用临时文件替换 JSON；单项失败保留历史。数据有损坏时拒绝覆盖；两个 JSON 文件分别原子替换，不是跨文件事务。浏览器会使用附带的交易日历重新检查时效，避免调度停止后一直显示旧状态。
- 如果全源失败，先检查网络、FRED API Key／CoinGecko 密钥及额度、Twelve Data 账户权限；`Actions` 日志包含失败项但不包含密钥。检查 `data/last_attempt.json`、快照时间和每卡日期。不能连接 OpenD 或行情权限不足时，使用有权的日线源，不得静默替换品种，不得以在岸人民币冒充离岸人民币或使用模拟值。

## 独立审查后的修正

- DXY 缺失或过期、但实际利率／2Y／HY／VIX 四项有效时，首页显示“有限风险提示”，明确标注 DXY 缺失和结论不完整。可提示信用与波动共同恶化、短端下行伴随风险恶化等信号；不会据此给出需要美元信号的“温和宽松”或“金融条件趋紧”完整判断。其余四项中任一关键 20 期缺失或过期时仍停止趋势判断。
- VIX ≥25、HY OAS ≥450bp 分别提供绝对风险水平提示，独立于近20期方向；高位但回落不等于“压力正在扩散”。过期数据不再输出当前高位提示。
- 各卡保留独立日期，宏观依据也逐项附日期。利差核验结果保存在 `snapshot.spread_checks`；没有相同日期的两端收益率时记录 `not_comparable`，不跨日期相减。
- NYSE、CME、外汇分别使用各自配置的会话日历；美债使用 NYSE 休市日与美国联邦假日的并集作为不发布日近似，包含 Good Friday、Veterans Day 等差异。CME 短时交易仍算一个有效交易时段，外汇采用工作日并排除元旦和圣诞节；来源若另有特殊休市，应以其发布说明为准。
- 浏览器在打开时重新检查各项时效：DXY 单独过期时降为有限提示，其他关键项过期时停止趋势判断，绝对风险提示也过滤过期项。

### DXY 的已核实路径与接入方式

ICE 的[原始指数目录](https://developer.ice.com/fixed-income-data-services/catalog/ice-data-indices-currency-indices)明确提供六种货币固定权重的现货美元指数日线／日终／历史数据，交付方式包括 ICE Data API 和 ICE Data Files。原生指数不是美元指数期货，也不是贸易加权美元指数。

Barchart 的[官方品种页](https://barchart.websol.barchart.com/?1_show=futureDetail&symbol=DXY00)将 `DXY00` 标注为 **U.S. Dollar Index Cash / ICEFI**；其[官方历史 API](https://www.barchart.com/ondemand/api/getHistory)提供 `getHistory` 日线。项目已增加 Barchart 官方 API 适配器，先用 `getQuote` 核对品种名和 `DXY00` 标识，再取 `type=daily` 历史。不会抓取网页、绕过限流或使用指数期货替代。当前无相应凭证，所以适配器已实现但尚未经过真实授权账户的成功调用验证。

可操作步骤：向 ICE 或 Barchart 确认 DXY 现货指数历史访问及本网站公开展示权限；获得凭证后配置 `BARCHART_API_KEY`。如已有 ICE 的授权转发服务，继续使用现有 `MARKET_DATA_DXY_URL` 接口。两种配置同时存在时优先采用显式指定的授权 URL。

```bash
# 交互输入，不把密钥写进代码或命令历史
 gh secret set BARCHART_API_KEY --repo weixb1818-cmyk/global-market-monitor
 gh workflow run update.yml --repo weixb1818-cmyk/global-market-monitor
```

### 当前免费接入与原期货口径

本次用户允许商品采用现货，因此 WTI 已明确切换为 EIA 库欣现货，黄金为明确标注的 XAU/USD 合成参考价。铜暂保留原期货定义并标缺失。原富途权限与 Twelve Data 账户探测作为历史证据保留在 data/source_access.json；当前四项免费接入不依赖这些账户。更换 provider、symbol、unit 或 series_definition 时，更新器清除该项旧历史，防止不同口径拼接计算20期涨跌。

### 定时运行的证据与限制

日常 cron `15 0 * * *` 是 UTC 00:15，即北京时间每天 08:15。GitHub 原生定时任务可能排队或延迟，不能保证精确到分钟；[官方说明](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows)也明确指出这一点。手动运行成功只能证明流水线可用，不能证明调度器触发。

本次曾临时设置短时 cron 探针，尝试观察真实的 `schedule` 事件，但核查窗口内没有观察到原生触发，额外 cron 已移除。未将手动事件改写成定时事件，也没有把探针当作北京时间08:15的自然触发。

每次更新将 `event`、实际匹配的 cron 和 `run_url` 写入 `snapshot.update_context` 与 `last_attempt.update_context`。页面页脚可直接打开该次运行。部署后由另一个云端 job 请求实际公开页面、CSS、JS、快照和更新记录，核对17个指标、快照生成时间及运行URL，防止把“上传制品成功”误当成网站已更新。


本次定时核查结果（2026-11-21）：仓库在当天北京时间08:15之后创建。短时 cron 探针、默认分支／启用状态检查及重新启用工作流后，核查窗口内仍未获得原生 `event=schedule` 记录，因此**尚未验证原生定时实际触发，不能宣布第3项完成**。临时高频 cron 已移除，仅保留日常 `15 0 * * *`。首次自然日常窗口为 **2026-11-22 北京时间08:15**，GitHub 可能排队延迟。

[这次成功的手动全链路运行](https://github.com/weixb1818-cmyk/global-market-monitor/actions/runs/44880971573)已通过42项Python测试、UI单元检查、取数、部署及公网回读；[独立浏览器验证](https://github.com/weixb1818-cmyk/global-market-monitor/actions/runs/44880770421)通过桌面／手机布局、有限风险提示、绝对风险与独立数据日期检查。这两类成功均没有冒充定时成功。详细状态见 [verification/review-summary.json](verification/review-summary.json)。

每次部署现在额外保存 `publication-evidence` 制品和 GitHub Job Summary，校验真实 GitHub 事件、cron、快照及更新记录属于同一次运行。只有原生 `schedule`、日常 cron 匹配、取数成功且公网回读一致时，`native_daily_schedule_verified` 才为 true；全源失败后发布旧快照不会被判成定时更新成功。更新工作流成功后，`workflow_run` 会自动触发独立的桌面／手机浏览器验收，浏览器还会核对它读取的行情确实来自触发验收的那次运行。

本机 Twelve Data 的只读账户验证已完成（2026-11-21）：两个准确货币对各返回99个已完成日线，技术可接入。服务商的[外部使用规则](https://support.twelvedata.com/en/articles/5332349-commercial-and-personal-usage)要求相应展示／再分发权；本机 API 可读不等于已取得此权利。因当前不能确认账户的授权范围，尚未把密钥上传至 GitHub 或发布该账户行情。此为此前账户核查记录；当前免费方案不依赖该密钥。未来恢复 Twelve Data 时须确认公开授权并显式切换 provider，重置对应历史，不能拼接参考汇率与收盘价。

最新补充验收（2026-11-21）：[47项测试、更新、部署及公网回读](https://github.com/weixb1818-cmyk/global-market-monitor/actions/runs/44882757226)成功，并[自动触发独立浏览器验收](https://github.com/weixb1818-cmyk/global-market-monitor/actions/runs/44882812965)成功。前者仍是 `workflow_dispatch`，后者为 `workflow_run`，均没有被标为原生定时成功；`publication-evidence` 中该标志为 false。

本轮免费数据源接入验收：[55项测试、取数、部署及公网回读](https://github.com/weixb1818-cmyk/global-market-monitor/actions/runs/44885895078)成功；[独立桌面／手机浏览器验收](https://github.com/weixb1818-cmyk/global-market-monitor/actions/runs/44885978426)成功。公开快照实测15项有值，DXY与铜缺失，WTI延迟，宏观状态继续明确为DXY缺失下的有限提示。无新增付费订阅。
