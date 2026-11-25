# 本机定时触发说明（2026-11-25）

原生GitHub定时事件曾延迟数小时。改为已有常在线主机在北京时间08:15调用已有GitHub工作流，08:45、10:15检查补偿；GitHub原有三次cron保留为备用。取数、计算、提交和Pages部署仍在GitHub执行，无新增服务费用。17项、阈值、来源适配器和页面结构不变。

## 运行与保护

- 主机：现有Ubuntu环境，部署目录`/home/ubuntu/panel`，系统时区Asia/Shanghai，cron常驻。若换机器，需先验证时区、网络与`gh`账户的Actions写权限。
- `scripts/local_trigger.py`只依赖Python标准库，使用现有`/usr/bin/gh`登录；不把凭证写入源码、参数、日志或GitHub。
- 当天08:15以后已有`status=ok`的公开更新，且对应整个GitHub工作流成功时，自动路线跳过。原生主任务也使用此判断。`partial`或`failed`允许下一时段补偿；旧价格存在不算抓取成功。数据过期提示继续独立保留。
- 发现运行中/排队中的更新工作流则跳过；本机文件锁防并发。每时段先保存派发意图，再请求API；超时结果不明时不在同一时段盲重发，由下一补偿时段重新检查。每天最多三次本机正常派发，GitHub备用遇部分失败仍可能继续补偿。人工刷新保持可用。
- 正常定时仅在所属时段后10分钟内派发；不会补发昨天的任务。错过主任务可由后两时段或GitHub备用补偿。该主机也停机时没有额外商业监控；网页原有漏跑/过期提示继续工作。
- 真实GitHub事件保持`workflow_dispatch`；附加`origin=host_cron`、`planned_at`、`requested_at`和唯一`dispatch_id`。诊断用`host_timer_test`单独标记，不计作自然定时运行。页面更新记录链接区分来源。
- 工作流制品`publication-evidence`核对公网快照的实际事件、来源、计划时间及关联ID；GitHub记录运行创建、启动、完成时间。十日审计同时收集本机和原生触发，但排除诊断作为自然成功日；运行中的本次任务尚无完成结论，要在后续审计或最终API记录核实。

## 安装和检查

在已有`gh`登录的主机运行：

```sh
/usr/bin/python3 scripts/install_local_timer.py --root /home/ubuntu/panel
/usr/bin/systemctl is-active cron
/usr/bin/crontab -l
```

安装器核查主机时区、cron服务与仓库访问，备份完整旧crontab，只替换本项目标记块，并回读验证；不修改其他任务、系统时区或认证。Ubuntu cron不依赖`CRON_TZ`支持，而使用已核验的系统时区。派发写权限由实际全链路验证确认，仓库只读检查本身不证明有派发权限。

管理块如下（其他任务不应提交到仓库）：

```cron
# BEGIN global-market-monitor host timer
# Host timezone must be Asia/Shanghai (checked by installer).
15 8 * * * /usr/bin/python3 /home/ubuntu/panel/scripts/local_trigger.py --slot 08:15 >> /home/ubuntu/panel/.runtime/market-timer/cron.log 2>&1
45 8 * * * /usr/bin/python3 /home/ubuntu/panel/scripts/local_trigger.py --slot 08:45 >> /home/ubuntu/panel/.runtime/market-timer/cron.log 2>&1
15 10 * * * /usr/bin/python3 /home/ubuntu/panel/scripts/local_trigger.py --slot 10:15 >> /home/ubuntu/panel/.runtime/market-timer/cron.log 2>&1
# END global-market-monitor host timer
```

本机日志、每时段意图文件、锁、备份在`.runtime/market-timer/`，目录700、文件600，由`.gitignore`排除。`events.jsonl`记录调用/计划/接受时间与错误类型；API拒绝或网络异常返回非零并记日志，不能当更新成功。派发成功只代表GitHub接受请求，最终完成以对应工作流和公网回读为准。

诊断命令会执行一次真正的取数及发布，不是模拟行情：

```sh
/usr/bin/python3 scripts/local_trigger.py --slot 08:15 --verify
```

`--verify`可绕过时段及当日健康限制，不能绕过已有运行中的工作流。不要将此选项加入cron。`dispatch_id`出现在运行标题中，可从日志唯一关联任务；`gh run list --workflow update.yml`查看结果。源码更新后需同步主机的`local_trigger.py`及其标准库依赖`schedule_audit.py`。

卸载只移除本项目块：

```sh
/usr/bin/python3 scripts/install_local_timer.py --root /home/ubuntu/panel --remove
```

主机需在线、账号授权需有效、网络需能访问GitHub。独立调用避开原生cron创建事件前的延迟，但GitHub接收、runner排队及行情源仍可能延迟，不能承诺08:15整页面完成，也不声称已经取得连续10日准点证据。11月25日12:48:53本机诊断派发、12:51:17部署完成，独立浏览器检查通过；最终本地105项测试通过，实际云端链路103项通过（最后两项为缓存防护核验）。铜来源部分失败与WTI延迟继续明示。真实验证及首次自然运行日期见[验收记录](../verification/host-timer-2026-11-25/acceptance.json)。
