"""身份归属裁决核心。

裁决优先级（自上而下，不可越级）：
1. 权威映射在该日冲突（同工号两人同时生效）：整工号当日打卡隔离，依据 ID_WINDOW。
2. 工号当日存在复用硬证据（同日两个不同 IN 时刻）：即便工号有映射，也无法判断
   哪条打卡属于映射中的自然人，当日全部打卡隔离，依据 ID_REUSE。
3. 权威映射命中且唯一：按映射确认自然人，依据 MAPPING。
4. 工号被并档建议引用且无映射：隔离待确认，依据 ID_ALIAS，等待人工确认。
5. 严格模式下无映射的工号：隔离，依据 ID_REUSE。
6. 其余工号全周期只出现一个稳定身份：确认为独立主档，依据 SINGLETON。

任何无法确认的打卡都进入 quarantine 并从 rows 中剔除，因此 M3 之后的工时归集、
工资对账与封存只能看到已确认身份；原始工号与原值原样保留在隔离记录里。
"""
from collections import defaultdict
from decimal import Decimal

from app.modules.m2b_identity import mapping as mapping_mod
from app.modules.m2b_identity.evidence import reuse_by_double_punch, alias_proposals

# 裁决依据码 → 中文含义，供页面与导出直接呈现。
BASIS = {
    'MAPPING': '权威工号映射确认',
    'SINGLETON': '全周期单一工号确认',
    'ID_WINDOW': '工号生效区间冲突',
    'ID_REUSE': '工号复用证据，归属待确认',
    'ID_ALIAS': '历史工号合并线索，待人工确认',
}


def _stable_key(badge):
    return 'P-' + str(badge)


def resolve(state):
    params = state.get('parameters', {}) or {}
    strict = bool(params.get('identity_strict', False))
    index = mapping_mod.parse(params.get('identity_map'))
    window_conflicts = mapping_mod.window_conflicts(index)
    # 预计算每个工号落入区间重叠的归属日，命中的打卡按 ID_WINDOW 隔离。
    conflict_days = defaultdict(set)
    for conflict in window_conflicts:
        end = conflict['to_date'] or '9999-12-31'
        for r in state['rows']:
            if r['employee'] == conflict['employee'] and conflict['from_date'] <= r['shift_day'] <= end:
                conflict_days[conflict['employee']].add(r['shift_day'])

    double_punch = reuse_by_double_punch(state['rows'])
    mapped_badges = set(index.keys())
    proposals = alias_proposals(state['rows'], mapped_badges)
    proposed_badges = set()
    for proposal in proposals:
        proposed_badges.add(proposal['from_employee'])
        proposed_badges.add(proposal['to_employee'])

    # 逐行裁决：decision[line] = (person_key, basis) 或 ('', hold_code, detail)。
    decision = {}
    held = []

    def hold(row, code, detail):
        decision[row['_line']] = None
        held.append((row, code, detail))

    conflict_persons = defaultdict(set)
    for conflict in window_conflicts:
        conflict_persons[conflict['employee']].update(conflict['persons'])

    for r in sorted(state['rows'], key=lambda x: x['_line']):
        badge, day = r['employee'], r['shift_day']
        binds = mapping_mod.bindings_on(index, badge, day)
        if len(binds) > 1 or day in conflict_days.get(badge, set()):
            persons = sorted({b['person'] for b in binds}) or sorted(conflict_persons.get(badge, set()))
            hold(r, 'ID_WINDOW', '工号 %s 在 %s 同时归属 %s'
                 % (badge, day, '/'.join(persons) if persons else '多个自然人'))
            continue
        if badge in double_punch and day in double_punch[badge]:
            hold(r, 'ID_REUSE', '工号 %s 在 %s 存在同日双进场，无法区分实际持卡人'
                 % (badge, day))
            continue
        if len(binds) == 1:
            decision[r['_line']] = (binds[0]['person'], 'MAPPING')
            continue
        if badge in proposed_badges:
            hold(r, 'ID_ALIAS', '工号 %s 存在换号并档线索，等待人工确认' % badge)
            continue
        if strict:
            hold(r, 'ID_REUSE', '严格模式下工号 %s 无权威映射，不予确认' % badge)
            continue
        decision[r['_line']] = (_stable_key(badge), 'SINGLETON')

    # 仅从已确认行构建主档，历史工号窗口按实际出现的归属日合并。
    masters = {}
    for r in state['rows']:
        verdict = decision.get(r['_line'])
        if verdict is None:
            continue
        person_key, basis = verdict
        r['person_key'] = person_key
        r['identity_basis'] = basis
        master = masters.setdefault(person_key, {
            'person_key': person_key, 'display_name': person_key,
            'basis_set': set(), 'badges': defaultdict(lambda: {'days': set(), 'basis': set()}),
            'shift_days': set(), 'lines': set(), 'paid': Decimal('0')})
        master['basis_set'].add(basis)
        master['shift_days'].add(r['shift_day'])
        master['lines'].add(r['_line'])
        badge_info = master['badges'][r['employee']]
        badge_info['days'].add(r['shift_day'])
        badge_info['basis'].add(basis)
        try:
            master['paid'] += Decimal(str(r.get('paid', '0')))
        except Exception:
            pass

    for row, code, detail in held:
        state['quarantine'].append({'line': row['_line'], 'id': row['id'], 'employee': row['employee'],
                                    'shift_day': row['shift_day'], 'code': code,
                                    'reason': BASIS[code], 'detail': detail, 'raw': row['_raw']})
    hold_lines = {row['_line'] for row, _, _ in held}
    state['rows'] = [r for r in state['rows'] if r['_line'] not in hold_lines]

    master_list = _serialise_masters(masters)
    counters = {'MAPPING': 0, 'SINGLETON': 0, 'ID_WINDOW': 0, 'ID_REUSE': 0, 'ID_ALIAS': 0}
    for master in master_list:
        for badge in master['historical_employee_numbers']:
            counters[badge['basis']] += 1
    for _, code, _ in held:
        counters[code] += 1
    state['identity'] = {
        'rule_version': state.get('identity_rule_version', ''),
        'mode': 'strict' if strict else 'evidence',
        'masters': master_list,
        'alias_proposals': proposals,
        'window_conflicts': window_conflicts,
        'reuse_evidence': [{'employee': b, 'shift_days': d} for b, d in sorted(double_punch.items())],
        'held_count': len(held),
        'held_paid': str(sum((Decimal(str(r.get('paid', '0'))) for r, _, _ in held), Decimal('0'))),
        'confirmed_persons': len(master_list),
        'counters': counters,
    }
    return state


def _serialise_masters(masters):
    out = []
    for person_key in sorted(masters):
        master = masters[person_key]
        badges = []
        for badge in sorted(master['badges']):
            info = master['badges'][badge]
            days = sorted(info['days'])
            basis = 'MAPPING' if 'MAPPING' in info['basis'] else 'SINGLETON'
            badges.append({'employee': badge, 'basis': basis,
                           'from_date': days[0], 'to_date': days[-1],
                           'windows': [[d, d] for d in days]})
        out.append({
            'person_key': person_key,
            'display_name': master['display_name'],
            'status': '已确认',
            'basis': 'MAPPING' if 'MAPPING' in master['basis_set'] else 'SINGLETON',
            'historical_employee_numbers': badges,
            'affected_shift_days': sorted(master['shift_days']),
            'source_lines': sorted(master['lines']),
            'paid_total': str(master['paid']),
        })
    return out
