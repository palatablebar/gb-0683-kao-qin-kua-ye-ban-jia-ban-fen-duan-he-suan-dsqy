import io,csv,json,hashlib

def _json(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True)

def bundle(state):
    out=io.StringIO(newline='');writer=csv.writer(out)
    rid=state.get('run_id','preview')
    writer.writerow(['记录类型','批次','来源行','业务ID','原因码','内容'])
    writer.writerow(['运行清单',rid,'','','',_json(state.get('manifest',{}))])
    writer.writerow(['对账',rid,'','','',_json(state.get('reconcile',{}))])
    # 身份归属结果先于一切金额证据：每名员工的主档、历史工号与受影响班次完整呈现。
    identity=state.get('identity',{})
    writer.writerow(['身份规则',rid,'','','',_json({'rule_version':identity.get('rule_version'),'mode':identity.get('mode')})])
    for master in identity.get('masters',[]):
        writer.writerow(['员工主档',rid,'',master['person_key'],master['basis'],_json(master)])
    for proposal in identity.get('alias_proposals',[]):
        writer.writerow(['并档待确认',rid,'',proposal['from_employee']+'->'+proposal['to_employee'],'ID_ALIAS',_json(proposal)])
    for conflict in identity.get('window_conflicts',[]):
        writer.writerow(['工号区间冲突',rid,'',conflict['employee'],'ID_WINDOW',_json(conflict)])
    for evidence in identity.get('reuse_evidence',[]):
        writer.writerow(['工号复用证据',rid,'',evidence['employee'],'ID_REUSE',_json(evidence)])
    for row in state.get('calculations',[]):
        writer.writerow(['计算',rid,row.get('line',''),row.get('id',''),row.get('code',''),_json(row)])
    for row in state['quarantine']:
        writer.writerow(['隔离',rid,row['line'],row.get('id',''),row['code'],_json(row.get('raw',{}))])
    return '﻿'+out.getvalue()

def checksum(state):
    return hashlib.sha256(bundle(state).encode('utf-8')).hexdigest()
