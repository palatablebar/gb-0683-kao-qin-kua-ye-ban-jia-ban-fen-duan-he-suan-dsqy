"""身份归属裁决：工号换号、工号复用、断档并档线索、严格模式与可付批次闸门。"""
import csv, io, json
import pytest
from app.workflow import run, load, sample_parameters
from app.modules.m7_archive.export_out import bundle
from app.config import IDENTITY_RULE_VERSION


@pytest.fixture
def identity_params():
    return sample_parameters('identity.csv')


@pytest.fixture
def identity_state(identity_params):
    return run(load('identity.csv'), identity_params)


def _master(state, person):
    return next(m for m in state['identity']['masters'] if m['person_key'] == person)


def test_mapping_merges_reassigned_badges_into_one_master(identity_state):
    # 王五换号：E201 与 E202 必须归入同一自然人主档，历史工号与生效区间都保留。
    wang = _master(identity_state, '王五')
    badges = {b['employee']: (b['from_date'], b['to_date']) for b in wang['historical_employee_numbers']}
    assert badges == {'E201': ('2026-09-25', '2026-09-25'), 'E202': ('2026-10-01', '2026-10-01')}
    assert wang['basis'] == 'MAPPING'
    # 换号前后两个班次都归集到同一主档，工时不断档。
    wang_shifts = [s for s in identity_state['shifts'] if s['person_key'] == '王五']
    assert {s['day'] for s in wang_shifts} == {'2026-09-25', '2026-10-01'}
    assert sum(x['minutes'] for x in identity_state['segments'] if x['person_key'] == '王五') == 840


def test_reused_badge_double_punch_is_held_even_with_mapping(identity_state):
    # E201 在 2026-10-02 同日双 IN：即使 HR 把 E201 映射给赵六，也无法区分实际持卡人，
    # 当日四条打卡全部隔离，赵六不得形成可付主档。
    held = [q for q in identity_state['quarantine'] if q['code'] == 'ID_REUSE']
    assert len(held) == 4 and {q['shift_day'] for q in held} == {'2026-10-02'}
    assert all(q['employee'] == 'E201' and q['raw']['employee'] == 'E201' for q in held)
    assert all(m['person_key'] != '赵六' for m in identity_state['identity']['masters'])
    assert identity_state['identity']['reuse_evidence'][0]['employee'] == 'E201'


def test_alias_proposal_stays_unconfirmed_and_outside_payable(identity_state):
    # E401→E402 仅有断档线索，没有权威映射：只能作为待确认建议，两侧打卡全部拦截。
    proposals = identity_state['identity']['alias_proposals']
    assert len(proposals) == 1 and proposals[0]['from_employee'] == 'E401'
    assert proposals[0]['to_employee'] == 'E402' and proposals[0]['status'] == '待确认'
    alias_held = [q for q in identity_state['quarantine'] if q['code'] == 'ID_ALIAS']
    assert {q['employee'] for q in alias_held} == {'E401', 'E402'}
    assert all(m['person_key'] not in ('E401', 'E402') for m in identity_state['identity']['masters'])


def test_singleton_badge_confirmed_without_mapping(identity_state):
    sun = _master(identity_state, 'P-E501')
    assert sun['basis'] == 'SINGLETON'
    assert [b['employee'] for b in sun['historical_employee_numbers']] == ['E501']


def test_unconfirmed_records_cannot_enter_payable_batch(identity_state):
    r = identity_state['reconcile']
    assert r['balanced'] is True and r['payable'] is False
    assert r['identity_held'] == identity_state['identity']['held_count'] == 8
    # 工时与金额只覆盖已确认身份：6 条已采信打卡 = 三个完整夜班。
    assert identity_state['business']['minutes'] == 1260
    assert identity_state['business']['held_paid'] == '880'
    assert identity_state['archive']['ready'] is False


def test_raw_employee_number_and_value_never_lost(identity_state):
    # 重算不丢记录、不丢原始工号：隔离行保留来源行、原始工号与原值。
    for q in identity_state['quarantine']:
        assert q['line'] > 0 and q['employee'] and q['raw'].get('id')
    rows = list(csv.reader(io.StringIO(bundle(identity_state).lstrip('﻿'))))
    types = {r[0] for r in rows}
    assert {'员工主档', '并档待确认', '工号复用证据', '隔离'}.issubset(types)


def test_person_payable_groups_by_natural_person(identity_state):
    payable = {p['person_key']: p['payable'] for p in identity_state['identity']['person_payable']}
    # 王五两个夜班各 220（120 分钟假日 3 倍 + 300 分钟正常 1 倍）。
    assert payable['王五'] == '460.00'
    assert payable['P-E501'] == '220.00'


def test_window_conflict_quarantines_overlapping_claims():
    params = {'identity_map': [
        {'person': '张三', 'employee': 'E001', 'from_date': '2026-10-01', 'to_date': None},
        {'person': '李四', 'employee': 'E001', 'from_date': '2026-10-01', 'to_date': '2026-10-31'}]}
    state = run(load('clean.csv'), params)
    assert state['identity']['window_conflicts']
    held = [q for q in state['quarantine'] if q['code'] == 'ID_WINDOW']
    assert held and {q['employee'] for q in held} == {'E001'}
    assert state['reconcile']['payable'] is False


def test_strict_mode_rejects_unmapped_badges():
    state = run(load('clean.csv'), {'identity_strict': True})
    # clean.csv 全部工号都没有权威映射，严格模式下无一可确认。
    assert state['identity']['confirmed_persons'] == 0
    assert state['identity']['held_count'] == state['input_count']
    assert state['reconcile']['payable'] is False


def test_evidence_mode_default_confirms_stable_badges():
    state = run(load('clean.csv'), {})
    assert state['reconcile']['payable'] is True
    assert state['identity']['confirmed_persons'] == 18
    assert state['identity']['held_count'] == 0


def test_mapping_change_invalidates_old_run_and_rerun_is_idempotent():
    base = run(load('clean.csv'), {})
    mapped = run(load('clean.csv'), {'identity_map': [
        {'person': '员工甲', 'employee': 'E001', 'from_date': '2026-09-01', 'to_date': None}]})
    # 映射规则变化 → 幂等键变化，旧批次结果自然失效（两个 run_id 不同）。
    assert base['run_id'] != mapped['run_id']
    # 同一输入（含同一映射）重跑 → 同一 run_id，不产生重复员工或重复金额。
    again = run(load('clean.csv'), {'identity_map': [
        {'person': '员工甲', 'employee': 'E001', 'from_date': '2026-09-01', 'to_date': None}]})
    assert again['run_id'] == mapped['run_id']
    assert again['identity']['confirmed_persons'] == mapped['identity']['confirmed_persons']
    assert again['business']['total'] == mapped['business']['total']


def test_identity_rule_version_is_part_of_manifest(identity_state):
    assert identity_state['manifest']['identity_rule_version'] == IDENTITY_RULE_VERSION


def test_export_refuses_sealing_when_identity_unresolved(client):
    saved = client.post('/api/runs', json={'sample': 'identity.csv'}).get_json()
    resp = client.get('/api/archive/' + saved['run_id'] + '/export.csv')
    assert resp.status_code == 422 and resp.get_json()['code'] == 'IDENTITY'


def test_resolved_batch_exports_and_seals(client):
    saved = client.post('/api/runs', json={'sample': 'clean.csv'}).get_json()
    resp = client.get('/api/archive/' + saved['run_id'] + '/export.csv')
    assert resp.status_code == 200
    text = resp.data.decode('utf-8-sig')
    assert '员工主档' in text
    rows = list(csv.reader(io.StringIO(text)))
    reconcile_row = next(r for r in rows if r[0] == '对账')
    body = json.loads(reconcile_row[-1])
    assert body['payable'] is True
