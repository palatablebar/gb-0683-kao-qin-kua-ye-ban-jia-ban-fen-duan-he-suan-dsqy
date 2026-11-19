# 夜班工时与工资

班次属于shift_day；计划结束时间不大于开始时间时跨到次日。打卡是带偏移的时间，先存UTC，再用Asia/Shanghai拆分实际日历日。休息区间按夜班日期归属处理，先从实际工作区间扣除。单班最多18小时，打卡须为整分钟。缺IN或OUT整班隔离，不猜补卡。

按实际日历日判断法定假日、周末，法定假日优先3倍、周末2倍、工作日8小时内1倍、超过8小时1.5倍；正常分钟按同员工同日累计，跨班片段共享阈值。参数holidays可传日期列表，默认仅2026-10-01。金额按片段Decimal计算到分，paid为实发工资，差额为应发减实发。此规则用于样例计算，不替代当地劳动法规。

## 通用采信约定

CSV按UTF-8 BOM、UTF-8、GB18030回退，保留逻辑记录结束行号；引号内换行由CSV解析。重复表头单独计数，列数不齐隔离。编码与ID按字符串保形。缺失哨兵为 `-`、`N/A`、`NULL`、`未知` 与空串；不得作为零。数值先NFKC归一、去千分位，再用Decimal。日期采用ISO；时间必须带偏移并转UTC。空文件、全空行、仅表头分别返回EMPTY_FILE、BLANK_FILE、HEADER_ONLY。

重复键为(id,version)，完全相同行去重；同键内容冲突则整组隔离，不取最后一行。行数对账：输入=采纳+隔离+空行+重复表头+完全重复。运行幂等键由输入字节、参数与规则版本计算。

同一员工/归属日/方向的最高版本若有时刻、时薪、班次、休息或实发金额冲突，则整班隔离；选中IN与OUT的时薪、班次起止与休息起止也必须完全一致。

## 身份归属（M2B）

工号 `employee` 可换、可被新员工复用，不是稳定身份。自然人主档 `person_key` 一经生成不再复用，主档下挂历史工号窗口 `historical_employee_numbers`（工号、依据、起止归属日、逐日窗口）与受影响班次日 `affected_shift_days`、来源行 `source_lines`。

权威映射来自参数 `identity_map`，元素为 `{person, employee, from_date, to_date}`，`to_date=null` 表示至今；同工号同日被两个 person 持有时为区间冲突（ID_WINDOW）。数据侧硬证据为同一工号同一归属日出现两个不同 IN 时刻（ID_REUSE），优先级高于映射。两工号在岗区间不重叠且首尾间隔达到 `REUSE_GAP_DAYS`（默认31天）仅生成并档建议 `alias_proposals`（ID_ALIAS），保持待确认。`identity_strict=true` 时无映射工号一律不予确认。

裁决依据码：MAPPING（权威映射确认）、SINGLETON（全周期单一工号确认）、ID_WINDOW（生效区间冲突）、ID_REUSE（复用证据/严格模式拒绝）、ID_ALIAS（并档线索待确认）。未确认打卡写入 `quarantine`（保留来源行、原始工号、原值与说明）并从 `rows` 剔除，因此 M3 起按 `person_key` 配对、切段、计薪与对账。`reconcile.identity_held` 为待确认打卡数，`reconcile.payable` 要求行数对账平衡且 `identity_held=0`；不可付批次封存导出返回 422。身份规则版本 `IDENTITY_RULE_VERSION` 与映射参数共同参与 run_id 哈希，规则或映射变化即产生新批次，旧结果不再被复用；同源重跑 run_id 不变，存储层不新增重复员工或金额。
