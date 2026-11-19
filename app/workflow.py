import time,importlib,json,base64
from pathlib import Path
from app.config import MODULES,SAMPLES,IDENTITY_RULE_VERSION
from app.errors import DomainError
from app.manifest import identity,manifest

def load(sample):
    if sample not in SAMPLES:raise DomainError('SAMPLE','样例名称无效')
    root=Path(__file__).resolve().parents[1]/'sample_data'
    return (root/sample).read_bytes()

def sample_parameters(sample):
    """样例自带的默认参数（如权威工号映射）；调用方显式传入的参数优先。"""
    side=Path(__file__).resolve().parents[1]/'sample_data'/(sample+'.params.json')
    if not side.exists():return {}
    return json.loads(side.read_text(encoding='utf-8'))

# 数字阶段沿用七模块时代的语义；完整流水线（stage=None 或 >=8）在班次日历之后、
# 跨夜配对之前插入身份归属，使身份裁决驱动后续所有归集、对账与封存。
_LEGACY_STAGE={3:['m1_ingest','m2_mapping','m3_versions'],
               4:['m1_ingest','m2_mapping','m3_versions','m4_segments'],
               5:['m1_ingest','m2_mapping','m3_versions','m4_segments','m5_calculate'],
               6:['m1_ingest','m2_mapping','m3_versions','m4_segments','m5_calculate','m6_reconcile'],
               7:['m1_ingest','m2_mapping','m3_versions','m4_segments','m5_calculate','m6_reconcile','m7_archive']}

def _plan(stage):
    if isinstance(stage,(list,tuple)):return list(stage)
    if stage is None or stage>=len(MODULES):return [entry[0] for entry in MODULES]
    if stage in _LEGACY_STAGE:return list(_LEGACY_STAGE[stage])
    return [entry[0] for entry in MODULES[:stage]]

def run(content,parameters=None,stage=None):
    if len(content)>2_000_000:raise DomainError('SIZE','文件超过2MB',413)
    params=parameters or {}
    if not isinstance(params,dict):raise DomainError('PARAMETERS','参数必须是对象')
    start=time.monotonic();state=None
    plan=_plan(stage)
    for n,name in enumerate(plan,1):
        fn=importlib.import_module('app.modules.'+name+'.service').execute
        if n==1:
            state=fn(content,params)
        else:
            state=fn(state)
        if name=='m2b_identity':
            # 让身份裁决结果与封存导出携带规则版本，而不是事后补写。
            state['identity']['rule_version']=IDENTITY_RULE_VERSION
    # Decimal values are serialized as strings before any storage or response.
    state=json.loads(json.dumps(state,default=str,ensure_ascii=False))
    state['identity_rule_version']=IDENTITY_RULE_VERSION
    state['run_id']=identity(content,params);state['manifest']=manifest(content,params,time.monotonic()-start)
    state['source_b64']=base64.b64encode(content).decode('ascii')
    if 'm7_archive' in _plan(stage):
        from app.modules.m7_archive.export_out import checksum
        state['archive']['sha256']=checksum(state)
    return state
