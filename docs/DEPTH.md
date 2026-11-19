# 深度登记 考勤跨夜班与加班分段核算

规模：中型。核心规则：跨夜按班次归属日配对，休息区间先扣除，再按法定日期和工时阈值切分倍率。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 打卡采信 | 查看并复算打卡采信 | `/api/m1_ingest` | `app/modules/m1_ingest/reader.py` | `tests/test_ingest.py` |
| M2 班次日历 | 查看并复算班次日历 | `/api/m2_mapping` | `app/modules/m2_mapping/rules.py` | `tests/test_mapping.py` |
| M2B 身份归属 | 裁决工号换号/复用并确认主档 | `/api/m2b_identity` | `app/modules/m2b_identity/resolver.py` | `tests/test_identity.py` |
| M3 跨夜配对 | 查看并复算跨夜配对 | `/api/m3_versions` | `app/modules/m3_versions/rules.py` | `tests/test_versions.py` |
| M4 缺卡复核 | 查看并复算缺卡复核 | `/api/m4_segments` | `app/modules/m4_segments/rules.py` | `tests/test_segments.py` |
| M5 工时切段 | 查看并复算工时切段 | `/api/m5_calculate` | `app/modules/m5_calculate/rules.py` | `tests/test_calculate.py` |
| M6 薪资对账 | 查看并复算薪资对账 | `/api/m6_reconcile` | `app/modules/m6_reconcile/compare.py` | `tests/test_reconcile.py` |
| M7 周期归档 | 查看并复算周期归档 | `/api/m7_archive` | `app/modules/m7_archive/export_out.py` | `tests/test_archive.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现 | 处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-01 | GB18030中文 | 固定UTF-8失败 | 按编码链回退 | `app/modules/m1_ingest/decode.py` | `tests/test_ingest.py::test_legacy_encoding` |
| TRAP-02 | 表头BOM | 首列键失配 | 去除BOM | `app/modules/m1_ingest/decode.py` | `tests/test_ingest.py::test_bom` |
| TRAP-03 | 引号内换行 | 分行误计 | csv逻辑记录 | `app/modules/m1_ingest/reader.py` | `tests/test_ingest.py::test_preserves_multiline_note` |
| TRAP-05 | 列数错位 | 静默补列 | WIDTH隔离 | `app/modules/m1_ingest/reader.py` | `tests/test_ingest.py::test_width_isolation` |
| TRAP-06 | 全角千分位 | float失败 | NFKC与Decimal | `app/modules/m2_mapping/coerce.py` | `tests/test_mapping.py::test_thousands` |
| TRAP-07 | 空值哨兵 | 空值当零 | MISSING隔离 | `app/modules/m2_mapping/coerce.py` | `tests/test_mapping.py::test_missing_numeric` |
| TRAP-08 | 前导零ID | 编码失真 | 字符串保形 | `app/modules/m2_mapping/rules.py` | `tests/test_mapping.py::test_identifier_zeroes` |
| TRAP-10 | 浮点误差 | 累计失准 | Decimal求和 | `app/modules/m2_mapping/coerce.py` | `tests/test_mapping.py::test_decimal_precision` |
| TRAP-14 | 同版冲突 | 最后覆盖 | 整组隔离 | `app/modules/m2_mapping/rules.py` | `tests/test_mapping.py::test_real_conflict_quarantine` |
| TRAP-18 | 三种空态 | 除零或伪成功 | 三个错误码 | `app/modules/m1_ingest/reader.py` | `tests/test_ingest.py::test_empty_three_states` |
| TRAP-26 | 旧版本复核 | 覆盖新结论 | 事务条件更新 | `app/store.py` | `tests/test_archive.py::test_stale_review` |
| TRAP-23 | 休息与跨夜端点 | 重复或漏计 | 半开区间切片 | `app/modules/m4_segments/rules.py` | `tests/test_segments.py::test_break_removed` |
| TRAP-19 | 假日与周末重叠 | 费率相加 | 假日优先 | `app/modules/m5_calculate/rules.py` | `tests/test_calculate.py::test_holiday_overrides_rest` |
| TRAP-30 | 换号合并断档 | 按现行工号拆分，工时扣款断档 | 自然人主档+历史工号窗口 | `app/modules/m2b_identity/resolver.py` | `tests/test_identity.py::test_mapping_merges_reassigned_badges_into_one_master` |
| TRAP-31 | 工号被新人复用 | 按工号合并，两人班次工资串档 | 同日双IN硬证据优先隔离，映射不得覆盖 | `app/modules/m2b_identity/resolver.py` | `tests/test_identity.py::test_reused_badge_double_punch_is_held_even_with_mapping` |
| TRAP-32 | 启发式并档误判 | 仅凭断档自动并人 | 仅生成待确认建议，不入可付批次 | `app/modules/m2b_identity/evidence.py` | `tests/test_identity.py::test_alias_proposal_stays_unconfirmed_and_outside_payable` |
| TRAP-33 | 映射规则变更 | 旧结论继续生效 | 映射+身份规则版本入幂等键，旧 run_id 失效 | `app/manifest.py` | `tests/test_identity.py::test_mapping_change_invalidates_old_run_and_rerun_is_idempotent` |
| TRAP-34 | 重跑产生重复员工/金额 | 追加写入 | 同源同映射同 run_id，INSERT OR IGNORE | `app/store.py` | `tests/test_identity.py::test_mapping_change_invalidates_old_run_and_rerun_is_idempotent` |

## 身份归属裁决

身份在班次日历之后、跨夜配对之前裁决，输出自然人主档 `person_key`、历史工号窗口与受影响班次日。优先级：映射区间冲突(ID_WINDOW) → 同日双IN复用(ID_REUSE) → 权威映射唯一命中(MAPPING) → 断档并档线索(ID_ALIAS，待确认) → 严格模式拒绝 → 全周期单一工号(SINGLETON)。任何未确认打卡进入隔离并从下游剔除，`reconcile.payable=false` 时封存导出返回 422。原始工号与原值随隔离记录保留，重算不丢行。

## 对账规则

输入行数=采纳+隔离+空行+重复表头+完全重复；业务总数与计算证据独立求和。隔离行保留来源行、ID、原因码与原值。

## 已知不覆盖

不做多租户权限和外部服务联调。行业规则以项目数据字典为准。文件上限2MB，逐行解析后在上限内完成分组计算。
