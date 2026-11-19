import base64
from flask import request,render_template,jsonify
from app.errors import DomainError
from app.config import TITLE,MODULES,SHORT,SAMPLES
from app.workflow import run,load,sample_parameters
from app import store

def payload():
    data=request.get_json(silent=True) or {}
    if not isinstance(data,dict):raise DomainError('PAYLOAD','请求必须是对象')
    if 'csv' in data and not isinstance(data['csv'],str):raise DomainError('CSV','CSV内容必须是文本')
    sample=data.get('sample',request.args.get('sample','dirty.csv'))
    if sample not in SAMPLES:raise DomainError('SAMPLE','样例名称无效')
    content=data.get('csv')
    if isinstance(content,str):
        parameters=data.get('parameters')
        if parameters is None:parameters={}
    else:
        # 样例侧车参数作为默认值；请求显式给出的 parameters 覆盖默认值。
        merged=sample_parameters(sample)
        explicit=data.get('parameters')
        if explicit is not None:
            if not isinstance(explicit,dict):raise DomainError('PARAMETERS','参数必须是对象')
            merged.update(explicit)
        parameters=merged
    return (content.encode() if isinstance(content,str) else load(sample)),parameters

def api(stage):
    content,parameters=payload();return jsonify(run(content,parameters,stage))

def page(stage,template,prefix=None):
    latest=store.history();state=store.get(latest[0]['id']) if latest else run(load('dirty.csv'),sample_parameters('dirty.csv'))
    if 'sample' in request.args:
        sample=request.args['sample']
        if sample not in SAMPLES:raise DomainError('SAMPLE','样例名称无效')
        source=load(sample);parameters=sample_parameters(sample)
    elif state.get('source_b64'):
        source=base64.b64decode(state['source_b64']);parameters=state.get('manifest',{}).get('parameters',{})
    else:
        source=load('dirty.csv');parameters=sample_parameters('dirty.csv')
    data=run(source,parameters,prefix if prefix is not None else stage)
    return render_template(template,title=TITLE,short=SHORT,modules=MODULES,current=stage,data=data,run=state,history=latest)
