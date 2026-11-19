from decimal import Decimal

def balance(state):
    accepted=len(state['rows']);isolated=len(state['quarantine'])
    accounted=accepted+isolated+state['blank_count']+state['header_count']+state['duplicate_count']
    identity=state.get('identity',{})
    held=identity.get('held_count',0)
    return {'input':state['input_count'],'accepted':accepted,'isolated':isolated,
        'identity_held':held,
        'blank':state['blank_count'],'headers':state['header_count'],'duplicates':state['duplicate_count'],
        'accounted':accounted,'balanced':accounted==state['input_count'],
        # 可付批次要求：行数对账平衡，且不存在任何身份未确认的打卡。
        'payable':accounted==state['input_count'] and held==0,
        'confirmed_persons':identity.get('confirmed_persons',0),
        'business':state.get('business',{})}
