from collections import defaultdict
from datetime import datetime,date,time,timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal
from app.errors import DomainError
ZONE=ZoneInfo('Asia/Shanghai')

def schedule(row):
    try:
        day=date.fromisoformat(row['shift_day']);start=datetime.combine(day,time.fromisoformat(row['shift_start']),ZONE);end=datetime.combine(day,time.fromisoformat(row['shift_end']),ZONE)
        if end<=start:end+=timedelta(days=1)
        if end-start>timedelta(hours=18):raise ValueError()
        bs=datetime.combine(day,time.fromisoformat(row['break_start']),ZONE);be=datetime.combine(day,time.fromisoformat(row['break_end']),ZONE)
        if bs<start:bs+=timedelta(days=1)
        if be<=bs:be+=timedelta(days=1)
        if not start<=bs<be<=end:raise ValueError()
        return start,end,bs,be
    except (ValueError,TypeError):raise DomainError('RANGE','班次或休息区间无效')

def apply(state):
    groups=defaultdict(list);bad=[]
    for r in state['rows']:
        try:
            schedule(r)
            if r['punch'] not in ('IN','OUT') or Decimal(str(r['hourly_rate']))<0:raise DomainError('RANGE','打卡或时薪无效')
            # 身份归属已在 m2b_identity 裁决：按稳定主档 person_key 配对，
            # 同一自然人换号前后的班次连续，被复用工号的他人记录不会串入。
            # 遗留的分阶段预览（未跑身份裁决）回退为按原始工号配对。
            groups[(r.get('person_key',r['employee']),r['shift_day'])].append(r)
        except DomainError as e:bad.append((r,e.code))
    shifts=[]
    for (person_key,day),rows in sorted(groups.items()):
        selected={};conflict=False
        for kind in ('IN','OUT'):
            candidates=[r for r in rows if r['punch']==kind]
            if not candidates:continue
            version=max(Decimal(str(r['version'])) for r in candidates);high=[r for r in candidates if Decimal(str(r['version']))==version]
            signature_fields=('at','hourly_rate','shift_start','shift_end','break_start','break_end','paid')
            signatures={tuple(str(r[k]) for k in signature_fields) for r in high}
            if len(signatures)>1:conflict=True
            selected[kind]=sorted(high,key=lambda r:r['id'])[0]
        if 'IN' in selected and 'OUT' in selected:
            shared=('hourly_rate','shift_start','shift_end','break_start','break_end')
            if any(str(selected['IN'][k])!=str(selected['OUT'][k]) for k in shared):conflict=True
        if conflict:bad.extend((r,'CONFLICT') for r in rows);continue
        anchor=selected.get('IN') or selected.get('OUT')
        person_key=anchor.get('person_key',anchor['employee'])
        shifts.append({'id':person_key+'/'+day,'person_key':person_key,
                       'employee':anchor['employee'],'employee_numbers':sorted({r['employee'] for r in rows}),
                       'day':day,'in':selected.get('IN'),'out':selected.get('OUT'),'sources':rows})
    lines={r['_line'] for r,_ in bad};state['rows']=[r for r in state['rows'] if r['_line'] not in lines]
    for r,c in bad:state['quarantine'].append({'line':r['_line'],'id':r['id'],'code':c,'raw':r['_raw']})
    state['shifts']=shifts;return state
