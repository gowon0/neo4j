def format_material_analysis(data):

    return f"""
[분석 유형]
원자재 가격 상승

[원자재]
이름: {data['material']}
코드: {data['material_code']}

[가격 정보]
기준가격: {data['standard_price']}
현재가격: {data['current_price']}
상승률: {data['increase_rate']}%
위험도: {data['risk_level']}

[기자재]
{data['equipment']}

[원가 영향]
영향도: {data['material_impact']}
방향: {data['material_direction']}
사유: {data['material_reason']}

[수급 문제]
{data['supply_problem']}
영향도: {data['supply_impact']}
사유: {data['supply_reason']}

[공사 프로젝트]
{data['project']}
상태: {data['project_status']}
프로젝트 영향도: {data['project_impact']}

[지식그래프 영향 경로]
{data['material']}
→ {data['equipment']}
→ {data['supply_problem']}
→ {data['project']}
"""


def format_external_risk(data):

    return f"""
[분석 유형]
외부 공급망 리스크

[외부 리스크]
이름: {data['risk_name']}
분류: {data['risk_category']}
심각도: {data['risk_severity']}
사유: {data['risk_reason']}

[원자재]
{data['material']}

[기자재]
{data['equipment']}

[수급 문제]
{data['supply_problem']}
심각도: {data['supply_severity']}

[공사 프로젝트]
{data['project']}
상태: {data['project_status']}

[영향 경로]
{data['risk_name']}
→ {data['material']}
→ {data['equipment']}
→ {data['supply_problem']}
→ {data['project']}
"""


def format_disaster(data):

    return f"""
[분석 유형]
자연재해

[자연재해]
이름: {data['disaster']}
분류: {data['disaster_category']}
심각도: {data['disaster_severity']}
사유: {data['disaster_reason']}

[공사 위험]
{data['construction_risk']}
심각도: {data['construction_severity']}
사유: {data['construction_reason']}

[공사 프로젝트]
{data['project']}
상태: {data['project_status']}

[영향 경로]
{data['disaster']}
→ {data['construction_risk']}
→ {data['project']}
"""