from app.modules.m7_archive.export_out import checksum


def execute(state):
    reconcile=state.get('reconcile',{})
    state['archive']={'sha256':checksum(state),
        'evidence_count':(len(state.get('calculations',[]))+len(state['quarantine'])
                          +len(state.get('identity',{}).get('masters',[]))),
        # 封存只承认可付批次：身份未确认的打卡存在时不得封存付款。
        'ready':bool(reconcile.get('balanced',False) and reconcile.get('payable',False)),
        'payable':bool(reconcile.get('payable',False))}
    return state
