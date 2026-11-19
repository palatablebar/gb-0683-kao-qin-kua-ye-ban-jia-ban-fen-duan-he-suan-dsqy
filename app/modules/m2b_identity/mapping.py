"""权威工号映射（HR 主数据）的解析与校验。

映射是身份归属唯一的权威来源。每条绑定声明在 [from_date, to_date] 闭区间内，
工号 badge 归属自然人 person。工号被新员工复用是合法场景，前提是两段区间不重叠；
同一工号在同一日期被两个自然人同时持有，属于区间冲突（ID_WINDOW），相关打卡不得采信。
"""
from datetime import date
from app.errors import DomainError

SENTINELS = ('', '-', 'N/A', 'NULL', '未知', None)


def _iso_day(value, field):
    if value in SENTINELS:
        return None
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except (ValueError, TypeError):
        raise DomainError('ID_MAPPING', '映射字段 %s 不是有效日期' % field)


def parse(identity_map):
    """把 parameters.identity_map 归一为按工号索引的绑定表。"""
    if identity_map in SENTINELS:
        return {}
    if not isinstance(identity_map, list):
        raise DomainError('ID_MAPPING', 'identity_map 必须是绑定列表')
    index = {}
    for pos, raw in enumerate(identity_map):
        if not isinstance(raw, dict):
            raise DomainError('ID_MAPPING', '第 %d 条映射不是对象' % (pos + 1))
        person = str(raw.get('person', '')).strip()
        badge = str(raw.get('employee', '')).strip()
        if not person or not badge:
            raise DomainError('ID_MAPPING', '第 %d 条映射缺少 person 或 employee' % (pos + 1))
        start = _iso_day(raw.get('from_date'), 'from_date')
        end = _iso_day(raw.get('to_date'), 'to_date')
        if start is None:
            raise DomainError('ID_MAPPING', '工号 %s 的映射缺少 from_date' % badge)
        if end is not None and end < start:
            raise DomainError('ID_MAPPING', '工号 %s 的生效区间倒置' % badge)
        index.setdefault(badge, []).append({'person': person, 'employee': badge,
                                            'from_date': start, 'to_date': end})
    for badge in index:
        index[badge].sort(key=lambda b: (b['from_date'], b['to_date'] or '9999-12-31', b['person']))
    return index


def bindings_on(index, badge, day):
    """返回工号在某日生效的全部绑定（0 条=未覆盖，>1 条=区间冲突）。"""
    return [b for b in index.get(badge, ())
            if b['from_date'] <= day and (b['to_date'] is None or day <= b['to_date'])]


def window_conflicts(index):
    """检测同一工号同一日期被两个自然人同时持有的区间重叠。"""
    conflicts = []
    for badge, binds in index.items():
        ordered = sorted(binds, key=lambda b: b['from_date'])
        for earlier, later in zip(ordered, ordered[1:]):
            if earlier['person'] != later['person']:
                open_end = earlier['to_date'] is None
                if open_end or later['from_date'] <= earlier['to_date']:
                    conflicts.append({'employee': badge,
                                      'persons': sorted({earlier['person'], later['person']}),
                                      'from_date': later['from_date'],
                                      'to_date': earlier['to_date']})
    return conflicts
