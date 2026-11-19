from flask import Blueprint
from app.web import api, page

bp = Blueprint('m2b_identity', __name__)


@bp.get('/m2b_identity')
def screen():
    # 显式要求完整前三阶段（采信→班次日历→身份归属），避免与遗留数字阶段 3 冲突。
    return page(3, 'm2b_identity.html', prefix=('m1_ingest', 'm2_mapping', 'm2b_identity'))


@bp.route('/api/m2b_identity', methods=['GET', 'POST'])
def preview():
    return api(('m1_ingest', 'm2_mapping', 'm2b_identity'))
