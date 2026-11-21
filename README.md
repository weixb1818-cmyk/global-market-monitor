# 全球市场每日观察

中文单页静态金融市场仪表盘。页面读取已生成的 JSON；定时 Python 脚本获取行情、计算变化、识别宏观状态。不会用模拟数据填充缺项。首次仓库内快照来自实际 FRED 和 CoinGecko 请求，生成时间及每项行情日期以页面为准。

## 已部署网址与验证

公开访问：<https://weixb1818-cmyk.github.io/global-market-monitor/>，无需登录。

源码仓库：<https://github.com/weixb1818-cmyk/global-market-monitor>。每日自动更新和部署已启用，时间为 UTC 00:15／东京 09:15；可在 Actions 手动触发。

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

## 数据源、定义与当前限制

| 指标 | 实现 | 接入情况 / 口径 |
|---|---|---|
| 2Y、10Y、10Y 实际利率、10Y−2Y、10Y−3M、VIX、HY OAS | FRED | 对应规格中的原始系列；不跨日期相减。可选官方 FRED API Key；无 Key 时尝试 FRED Graph CSV。 |
| 标普 500、纳斯达克 100 | FRED `SP500`、`NASDAQ100` | 指数本身的日收盘；不是 ETF。FRED 有发布滞后，页面显示各自日期。指数数据受版权约束，发布前应核对相关权利及许可，尤其 SP500 标记了预先批准要求。 |
| BTC、ETH | CoinGecko 官方 `market_chart` | 取每日 **00:00 UTC** 样本作为前一 UTC 日结束快照；忽略当前未完成日期及日内样本。生产环境建议配置 Demo API Key。 |
| USD/JPY、USD/CNH | Twelve Data `USD/JPY`、`USD/CNH` | 已在官方目录核实 `USD/CNH` 为 Chinese Yuan (Offshore)。每日线依数据源本地时区，只使用已完成日线；需 `TWELVE_DATA_API_KEY`，品种与历史数据是否可用取决于账户权限。日线的 `timezone` 参数会被服务商忽略。 |
| DXY | 外部已授权日线适配器 | 不用贸易加权美元指数替代。当前无已验证且可用的 DXY 日线授权源，故显示缺失。 |
| 黄金、WTI、铜 | 外部已授权日线适配器 | 必须分别是 COMEX 黄金近月 USD/oz、NYMEX WTI 近月 USD/bbl、COMEX 铜近月 USD/lb，且数据源须固定、公开说明换月与历史拼接方式。本机富途 OpenD 可连接，但这三项返回“行情权限不足”，因此目前没有安全地接入；获得相应 CME 行情权限后，还须核验近月连续序列和换月口径。Twelve Data 的常见商品数据是现货，不能直接替代期货。 |

富途 OpenD 是本机进程，GitHub Actions 不能访问 `127.0.0.1` 上的本机 OpenD；如以后取得权限，应在本机运行更新任务并将结果发布，或使用自托管 Actions runner，同时完成品种、授权与换月验证。当前代码不会尝试买行情卡，也不会发交易请求。

FRED 的 ICE HY OAS 历史自 2026 年 4 月起在 FRED 仅保留最近三年；它是信用利差而非收益率。FRED、Nasdaq、S&P、ICE、CoinGecko 和 Twelve Data 的数据各有使用、展示或再分发条件；本项目代码不授予数据再分发许可。公开部署前请按所用账户与数据源条款确认权限。参见 [FRED SP500](https://fred.stlouisfed.org/series/SP500)、[FRED HY OAS](https://fred.stlouisfed.org/series/BAMLH0A0HYM2)、[富途行情权限](https://openapi.futunn.com/futu-api-doc/intro/authority.html)、[Twelve Data EOD 权限](https://support.twelvedata.com/en/articles/12682324-end-of-day-eod-pricing-market-data)。

## 配置密钥及更新

环境变量供更新脚本使用，绝不会写入浏览器代码：

```bash
export FRED_API_KEY='你的FRED密钥'             # 可选；不配置则使用CSV
export COINGECKO_API_KEY='你的CoinGecko Demo密钥'  # 推荐
export TWELVE_DATA_API_KEY='你的Twelve Data密钥'   # 外汇需要
python scripts/update_data.py
```

请勿将密钥加入 Git 仓库或填入页面。Twelve Data 在此机器的现有进程环境中未发现密钥，使用前请自行通过环境变量或 GitHub Secrets 提供。API 返回的错误、网络限制或无权限会显示为缺失／延迟／更新失败，保留已有有效数据。脚本日志不会输出 API Key 或请求 URL。

### 自有或获授权数据商的适配器

DXY 和三项期货各使用一个 URL，可分别通过 `MARKET_DATA_DXY_URL`、`MARKET_DATA_GOLD_URL`、`MARKET_DATA_WTI_URL`、`MARKET_DATA_COPPER_URL` 指定。URL 应返回按时间递增或无序均可的 JSON：

```json
{"symbol":"DXY","unit":"点","source":"已授权数据源及品种说明","daily_close":true,"complete_through":"YYYY-MM-DD","observations":[{"date":"YYYY-MM-DD","value":123.45}]}
```

这只是字段格式示意，`123.45` 不是项目行情，不能作为真实数据发布。生产响应必须提供至少 21 个真实有效观测、准确的行情日期、已完成交易时段的最后日期 `complete_through` 和单位，并经权利方许可。期货的 `symbol` 分别是 `GC_FRONT`、`CL_FRONT`、`HG_FRONT`，单位分别是 `USD/oz`、`USD/bbl`、`USD/lb`。服务必须保证每个历史点采用一致的近月选取和换月拼接规则，并在 `source` 描述该规则。脚本拒绝元数据不匹配的响应；它不能独立证明供应商确实履行了口径承诺，接入前需要自行核验。URL 如果含密钥，请放 Secret，不能放代码或网页。

## GitHub Pages 与自动更新

1. 将项目放入自己拥有的 GitHub 仓库，提交源码、`data/` 和 `.github/workflows/update.yml`，不要提交 `.venv` 或密钥。
2. 在仓库 **Settings → Secrets and variables → Actions** 设置需要的 `FRED_API_KEY`、`COINGECKO_API_KEY`、`TWELVE_DATA_API_KEY` 以及授权行情适配器 URL。缺少可选密钥时相关卡片标记缺失；不得向仓库提交秘密。
3. 在 **Settings → Actions → General → Workflow permissions** 允许 workflow 读写仓库内容；如果分支保护不允许推送，请调整为允许该自动化或使用其他发布流程。
4. 在 **Settings → Pages → Build and deployment** 将 Source 设为 **GitHub Actions**。本项目工作流会在更新 JSON 后显式上传并部署静态页面。公开站点及行情数据的再分发必须先符合各数据源许可。
5. Actions 中手动运行 **Update daily market snapshot** 验证。此后工作流每天 UTC 00:15（东京 09:15）自动运行并提交 JSON；GitHub 定时任务可能排队延迟。页面地址通常为 `https://<用户名>.github.io/<仓库名>/`，具体地址以 Pages 设置显示为准。

自动提交只有真正有修改时才产生。全源失败时保留上次 `snapshot.json`，更新 `last_attempt.json` 并使任务失败；部分来源失败时保留对应历史，页面标识失败或延迟。手动刷新：在 Actions 选择 workflow → **Run workflow**，或本地执行更新脚本。

## 计算、日期和故障处理

- `config.json` 包含固定 17 项配置与阈值；宏观规则的优先级为金融压力扩散、增长担忧定价、金融条件趋紧、温和宽松、中性／信号分歧。DXY 单独缺失／过期时降为明确标识的有限提示；其他关键20期缺失／过期则停止趋势判断。
- 价格类按百分比，VIX 按点，利率与利差变化按 bp；利差水平以 `FRED 原值 × 100` 显示 bp。20 期比较当前值与该系列向前第 20 个有效观测。
- FRED 采用其发布的日收盘，纽约 18:00 前保守地排除当天数据；CoinGecko 采用前一个完整 UTC 日；Twelve Data 日线使用其市场本地日界并排除未完成日。数据不同时到达，页面显示每项独立日期。
- NYSE 交易日历用于美股、VIX 和 HY；美债按 NYSE 休市日与美国联邦假日的并集近似；期货使用 CME 会话，外汇使用工作日与主要全球休市日。连续超过两个预期交易日无更新才标延迟；加密日线距其 UTC 收盘超过 36 小时标延迟。特殊休市或来源停更仍应结合该源发布说明与独立日期判断。
- 每次成功先校验、计算、再使用临时文件替换 JSON；单项失败保留历史。数据有损坏时拒绝覆盖；两个 JSON 文件分别原子替换，不是跨文件事务。浏览器会使用附带的交易日历重新检查时效，避免调度停止后一直显示旧状态。
- 如果全源失败，先检查网络、FRED API Key／CoinGecko 密钥及额度、Twelve Data 账户权限；`Actions` 日志包含失败项但不包含密钥。检查 `data/last_attempt.json`、快照时间和每卡日期。不能连接 OpenD 或行情权限不足时，使用有权的日线源，切勿用 ETF、现货、在岸人民币或模拟值替代。

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

### 其余五项的障碍和处理步骤

| 指标 | 已核查的障碍 | 具体解决方式 |
|---|---|---|
| 黄金期货 | 富途 `US.GCcurrent` 返回行情权限不足；常见 Twelve Data 黄金为现货 | 取得 COMEX API 行情权限；核对近月与换月历史规则，保持 USD/oz；通过已有 `MARKET_DATA_GOLD_URL` 提供日线 |
| WTI 期货 | 富途 `US.CLcurrent` 返回行情权限不足；WTI 现货不符合本指标 | 取得 NYMEX API 行情权限；固定近月切换与不复权／复权方式，保持 USD/bbl；配置 `MARKET_DATA_WTI_URL` |
| 铜期货 | 富途 `US.HGcurrent` 返回行情权限不足；其他铜现货或 LME 铜不是 COMEX 铜 | 取得 COMEX API 行情权限；固定近月换月规则，保持 USD/lb；配置 `MARKET_DATA_COPPER_URL` |
| USD/JPY | Twelve Data 官方目录有准确代码，当前进程及仓库未配置密钥 | `gh secret set TWELVE_DATA_API_KEY --repo weixb1818-cmyk/global-market-monitor`；运行更新；确认账户能返回至少21个已完成日线观测 |
| USD/CNH | 目录明确为 Chinese Yuan (Offshore)，尚未验证有权账户的日线访问 | 使用同一 Secret；核对响应 `meta.symbol=USD/CNH`、数据源日界和21期历史；若套餐无此权限，向服务商开通该代码的历史权限，不使用 USD/CNY 替换 |

富途本机 OpenD 不能由 GitHub-hosted runner 的 localhost 访问。取得权限后，可选择本机运行更新并发布、配置 self-hosted runner，或由获授权的 HTTPS 服务导出符合既有 JSON 格式的近月序列。购买权限和公开再分发授权属于账户操作，本项目没有自动购买或交易行为。完整核查记录保存在 [data/source_access.json](data/source_access.json)。

### 定时运行的证据与限制

日常 cron `15 0 * * *` 是 UTC 00:15，即北京时间每天 08:15。GitHub 原生定时任务可能排队或延迟，不能保证精确到分钟；[官方说明](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows)也明确指出这一点。手动运行成功只能证明流水线可用，不能证明调度器触发。

本次核查临时设置短时 cron 探针，使用真实的 `schedule` 事件验证调度、取数、部署和公网回读，验证后移除额外 cron。实际结果和精确运行链接会保存在本地验证报告及工作流记录中；临时探针不等于已经观察到下一次北京时间08:15的自然触发。

每次更新将 `event`、实际匹配的 cron 和 `run_url` 写入 `snapshot.update_context` 与 `last_attempt.update_context`。页面页脚可直接打开该次运行。部署后由另一个云端 job 请求实际公开页面、CSS、JS、快照和更新记录，核对17个指标、快照生成时间及运行URL，防止把“上传制品成功”误当成网站已更新。
