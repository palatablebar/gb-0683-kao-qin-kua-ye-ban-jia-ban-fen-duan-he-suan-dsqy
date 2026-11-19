import hashlib,json,time
from datetime import datetime,timezone
from app.config import RULE_VERSION,IDENTITY_RULE_VERSION

def identity(content, parameters):
    # 身份裁决规则版本与映射参数一并入键：映射规则或裁决规则变化，旧批次立即失效，
    # 而同一输入（含同一映射）重跑得到同一 run_id，存储层 INSERT OR IGNORE 不会新增重复。
    raw = (content + json.dumps(parameters,sort_keys=True,ensure_ascii=False).encode()
           + RULE_VERSION.encode() + IDENTITY_RULE_VERSION.encode())
    return hashlib.sha256(raw).hexdigest()[:20]

def manifest(content, parameters, elapsed):
    return {'sha256':hashlib.sha256(content).hexdigest(),'rule_version':RULE_VERSION,
        'identity_rule_version':IDENTITY_RULE_VERSION,
        'parameters':parameters,'elapsed_ms':round(elapsed*1000),
        'generated_at':datetime.now(timezone.utc).isoformat(),'timezone':'Asia/Shanghai'}
