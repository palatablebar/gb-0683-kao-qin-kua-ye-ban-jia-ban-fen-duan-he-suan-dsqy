# 考勤跨夜班与加班分段核算

面向制造企业薪酬核算员，处理采信、判定、核算、复核与归档。

## 启动

```bash
docker compose up --build -d
```

访问 http://localhost:18252 。初次启动自动运行脏样例，可切换 clean.csv、legacy.csv 与 identity.csv。顶部“运行批次”会重新计算，同源输入（含同一映射参数）复用批次。

## 业务模块

- 打卡采信：`/m1_ingest`、`/api/m1_ingest`
- 班次日历：`/m2_mapping`、`/api/m2_mapping`
- 身份归属：`/m2b_identity`、`/api/m2b_identity`
- 跨夜配对：`/m3_versions`、`/api/m3_versions`
- 缺卡复核：`/m4_segments`、`/api/m4_segments`
- 工时切段：`/m5_calculate`、`/api/m5_calculate`
- 薪资对账：`/m6_reconcile`、`/api/m6_reconcile`
- 周期归档：`/m7_archive`、`/api/m7_archive`

## 身份归属

工号可换号、可被新员工复用，不能作为身份。系统在班次日历之后按权威映射 `identity_map`（生效区间）确认自然人主档 `person_key`，主档保留全部历史工号窗口与受影响班次；同工号同日双进场视为复用硬证据，优先级高于映射。断档只产生待确认并档建议。任何无法确认的打卡一律隔离、不进入可付批次，封存导出对不可付批次返回 422。原始工号与原值随记录保留，映射或身份规则版本变化会改变 run_id 使旧结果失效，同源重跑不新增重复员工或金额。详见 `docs/DATA-DICTIONARY.md`。

## 核心规则

跨夜按班次归属日配对，休息区间先扣除，再按法定日期和工时阈值切分倍率。完整数值、边界和异常定义见 `docs/DATA-DICTIONARY.md`。

## 验证

```bash
docker compose exec -T app pytest -q
docker compose config --quiet
```

原始样例在 `sample_data/`。测试在 `tests/`。封存文件是单份CSV，含运行清单、计算证据、隔离原因与对账。复核需提交当前版本，陈旧复核返回409。

## 数据与限制

SQLite保存在records命名卷，普通重启与构建不会清除。确认可丢弃本项目数据后，运行 `docker compose down -v` 再启动可重置。单文件上限2MB；不接入外部业务系统；历史规则由本项目样例定义，不代表实际行业标准。
