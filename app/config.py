TITLE='考勤跨夜班与加班分段核算'
SHORT='shiftledger'
RULE_VERSION='2026.11.19-v2'
# m2b_identity 在班次日历之后、跨夜配对之前执行，身份归属驱动后续所有归集与对账。
MODULES=[('m1_ingest', '打卡采信'), ('m2_mapping', '班次日历'), ('m2b_identity', '身份归属'), ('m3_versions', '跨夜配对'), ('m4_segments', '缺卡复核'), ('m5_calculate', '工时切段'), ('m6_reconcile', '薪资对账'), ('m7_archive', '周期归档')]
SAMPLES=('dirty.csv','clean.csv','legacy.csv','identity.csv')
# 身份裁决规则版本单独参与幂等键，映射规则变化即令旧结果失效。
IDENTITY_RULE_VERSION='identity-2026.11.19-v1'
# 同一工号两段在岗间隔超过该天数（含边界）视为时间线断档的复用疑点，仅作待确认线索。
REUSE_GAP_DAYS=31
REQUIRED=['id', 'employee', 'shift_day', 'version', 'punch', 'at', 'shift_start', 'shift_end', 'break_start', 'break_end', 'hourly_rate', 'paid']
NUMERIC=['version', 'hourly_rate', 'paid']
DATES=['shift_day']
TIMES=['at']
