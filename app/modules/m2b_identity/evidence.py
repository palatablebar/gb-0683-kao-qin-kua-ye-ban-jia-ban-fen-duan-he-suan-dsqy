"""打卡数据自身能给出的身份疑点（弱证据，只可怀疑、不可自动并档）。

两类疑点：
1. 工号复用硬证据：同一工号同一归属日出现两个互不相同的 IN 打卡时刻，
   说明当天该工号被两个人使用，单一自然人无法同时进两次场。
2. 时间线断档 + 接续线索：工号最后一次打卡与新工号第一次打卡间隔超过阈值，
   且两个工号的在岗区间首尾相接、没有重叠，则给出“疑似同一人换号”的并档建议，
   一律保持待确认，绝不据此自动合并。
"""
from collections import defaultdict
from datetime import date, timedelta
from app.config import REUSE_GAP_DAYS


def _days(rows):
    return sorted({r['shift_day'] for r in rows})


def reuse_by_double_punch(rows):
    """返回存在同日双 IN 硬证据的工号集合及其证据。"""
    seen = defaultdict(lambda: defaultdict(set))
    for r in rows:
        if r.get('punch') == 'IN':
            seen[r['employee']][r['shift_day']].add(r['at'])
    evidence = {}
    for badge, days in seen.items():
        doubled = sorted(day for day, stamps in days.items() if len(stamps) > 1)
        if doubled:
            evidence[badge] = doubled
    return evidence


def _spans(rows):
    badges = defaultdict(list)
    for r in rows:
        badges[r['employee']].append(r['shift_day'])
    return {badge: (min(days), max(days)) for badge, days in badges.items()}


def alias_proposals(rows, mapped_badges, gap_days=REUSE_GAP_DAYS):
    """提出“老工号 → 新工号疑似同一自然人”的待确认建议。

    仅在两工号区间不重叠、首尾间隔达到断档阈值，且二者都未被权威映射覆盖时提出；
    每个工号至多给出一个建议，保证结果确定、可复算。
    """
    spans = _spans(rows)
    proposals = []
    for old_badge, (old_start, old_end) in sorted(spans.items()):
        if old_badge in mapped_badges:
            continue
        best = None
        old_last = date.fromisoformat(old_end)
        for new_badge, (new_start, new_end) in sorted(spans.items()):
            if new_badge == old_badge or new_badge in mapped_badges:
                continue
            first = date.fromisoformat(new_start)
            gap = (first - old_last).days
            # 区间不得重叠；间隔达到断档阈值才视为换号线索。
            if gap >= gap_days and (best is None or (gap, new_badge) < (best[0], best[1])):
                best = (gap, new_badge, new_end)
        if best:
            gap, new_badge, new_end = best
            proposals.append({'from_employee': old_badge, 'to_employee': new_badge,
                              'gap_days': gap, 'span': {'from_date': old_start, 'to_date': new_end},
                              'status': '待确认', 'basis': 'TIMELINE_GAP'})
    # 一个新工号只能承接一个老工号，保留排序后首个指向它的建议。
    claimed = set()
    unique = []
    for proposal in proposals:
        if proposal['to_employee'] in claimed:
            continue
        claimed.add(proposal['to_employee'])
        unique.append(proposal)
    return unique
