import os
from typing import List, Dict

from dotenv import load_dotenv
from neo4j import GraphDatabase

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate


# ============================================================
# 1. 환경변수 로드
# ============================================================

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# ============================================================
# 2. Neo4j 연결
# ============================================================

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
)


# ============================================================
# 3. LangChain LLM 설정
# ============================================================

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.2
)


# ============================================================
# 4. LLM Prompt
# ============================================================

prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """
당신은 전력 기자재 공급망 위험 분석 시스템의 AI 분석 담당자입니다.

주어진 데이터는 Neo4j 지식그래프에서 조회된 사실입니다.

반드시 주어진 데이터와 관계만을 근거로 설명해야 합니다.
존재하지 않는 원인이나 관계를 임의로 만들어내지 마세요.

설명은 다음 순서로 작성하세요.

1. 위험 원인
2. 기자재에 미치는 영향
3. 수급 문제
4. 영향을 받는 공사 프로젝트

숫자가 제공되었다면 상승률이나 영향도를 자연스럽게 설명하세요.

전문적이지만 이해하기 쉬운 한국어로 2~4문장 정도로 답변하세요.
"""
    ),
    (
        "human",
        """
다음 데이터를 기반으로 공급망 위험을 설명해주세요.

[분석 데이터]

{analysis_data}
"""
    )
])


llm_chain = prompt | llm


# ============================================================
# 5. 원자재 가격 상승률 계산
# ============================================================

def calculate_increase_rate(standard, current):
    """
    기준가격 대비 현재가격 상승률 계산

    상승률(%)
    = (현재가격 - 기준가격) / 기준가격 * 100
    """

    try:
        standard = float(standard)
        current = float(current)

        if standard == 0:
            return 0.0

        rate = ((current - standard) / standard) * 100

        return rate

    except (TypeError, ValueError):
        return 0.0


# ============================================================
# 6. 원자재 가격 상승 데이터 조회
# ============================================================

def get_material_risks(tx):
    query = """
    MATCH (m:원자재)-[r1:원가영향]->(e:기자재)
          -[r2:수급영향]->(s:수급문제)
          -[r3:프로젝트영향]->(p:공사프로젝트)

    RETURN
        m.name AS material,
        m.code AS material_code,
        m.standard AS standard_price,
        m.current AS current_price,

        e.name AS equipment,

        s.name AS supply_problem,
        s.severity AS supply_severity,

        p.name AS project,
        p.status AS project_status,

        r1.impact AS material_impact,
        r1.direction AS material_direction,
        r1.reason AS material_reason,

        r2.impact AS supply_impact,
        r2.reason AS supply_reason,

        r3.impact AS project_impact
    """

    result = tx.run(query)

    return [record.data() for record in result]


def analyze_material_risks():

    with driver.session() as session:

        records = session.execute_read(
            get_material_risks
        )

    results = []

    for record in records:

        standard = record["standard_price"]
        current = record["current_price"]

        # 상승률 계산
        increase_rate = calculate_increase_rate(
            standard,
            current
        )

        record["increase_rate"] = increase_rate

        # ====================================================
        # 위험도 판정
        # ====================================================

        if increase_rate >= 20:
            risk_level = "매우위험"

        elif increase_rate >= 15:
            risk_level = "위험"

        elif increase_rate >= 10:
            risk_level = "경고"

        else:
            risk_level = "정상"

        record["risk_level"] = risk_level

        results.append(record)

    return results


# ============================================================
# 7. 외부 리스크 → 원자재 → 기자재 → 수급 → 프로젝트
# ============================================================

def get_external_risks(tx):

    query = """
    MATCH (risk:리스크요인)-[r1]->(m:원자재)
          -[r2:원가영향]->(e:기자재)
          -[r3:수급영향]->(s:수급문제)
          -[r4:프로젝트영향]->(p:공사프로젝트)

    WHERE risk.isActive = true

    RETURN
        risk.name AS risk_name,
        risk.category AS risk_category,
        risk.severity AS risk_severity,
        risk.reason AS risk_reason,

        type(r1) AS risk_relationship,
        r1.impact AS risk_impact,

        m.name AS material,

        e.name AS equipment,

        s.name AS supply_problem,
        s.severity AS supply_severity,

        p.name AS project,
        p.status AS project_status,

        r2.impact AS material_impact,
        r2.direction AS material_direction,
        r2.reason AS material_reason,

        r3.impact AS supply_impact,
        r4.impact AS project_impact
    """

    result = tx.run(query)

    return [record.data() for record in result]


def analyze_external_risks():

    with driver.session() as session:

        records = session.execute_read(
            get_external_risks
        )

    return records


# ============================================================
# 8. 자연재해 → 공사위험 → 프로젝트
# ============================================================

def get_disaster_risks(tx):

    query = """
    MATCH (d:자연재해)-[r1:발생원인]->(c:공사위험)
          -[r2:공사영향]->(p:공사프로젝트)

    WHERE d.isActive = true

    RETURN
        d.name AS disaster,
        d.category AS disaster_category,
        d.severity AS disaster_severity,
        d.reason AS disaster_reason,

        c.name AS construction_risk,
        c.severity AS construction_severity,
        c.reason AS construction_reason,

        p.name AS project,
        p.status AS project_status,

        r1.impact AS disaster_impact,
        r2.impact AS project_impact
    """

    result = tx.run(query)

    return [record.data() for record in result]


def analyze_disaster_risks():

    with driver.session() as session:

        records = session.execute_read(
            get_disaster_risks
        )

    return records


# ============================================================
# 9. LLM에 전달할 데이터 만들기
# ============================================================

def create_material_analysis_text(data):

    return f"""
위험 유형: 원자재 가격 상승

원자재: {data['material']}

기준가격: {data['standard_price']}
현재가격: {data['current_price']}
가격 상승률: {data['increase_rate']:.1f}%

가격 상승 위험도: {data['risk_level']}

영향 기자재: {data['equipment']}

원가 영향도: {data['material_impact']}
영향 방향: {data['material_direction']}
영향 사유: {data['material_reason']}

수급 문제: {data['supply_problem']}
수급 영향도: {data['supply_impact']}

영향 프로젝트: {data['project']}
프로젝트 영향도: {data['project_impact']}

그래프 경로:

{data['material']}
→ {data['equipment']}
→ {data['supply_problem']}
→ {data['project']}
"""


def create_external_analysis_text(data):

    return f"""
위험 유형: 외부 공급망 리스크

외부 리스크: {data['risk_name']}
분류: {data['risk_category']}
심각도: {data['risk_severity']}
위험 사유: {data['risk_reason']}

원자재: {data['material']}

기자재: {data['equipment']}

수급 문제: {data['supply_problem']}
수급 심각도: {data['supply_severity']}

영향 프로젝트: {data['project']}

그래프 경로:

{data['risk_name']}
→ {data['material']}
→ {data['equipment']}
→ {data['supply_problem']}
→ {data['project']}
"""


def create_disaster_analysis_text(data):

    return f"""
위험 유형: 자연재해

자연재해: {data['disaster']}
분류: {data['disaster_category']}
심각도: {data['disaster_severity']}
위험 사유: {data['disaster_reason']}

공사 위험: {data['construction_risk']}
공사 위험 심각도: {data['construction_severity']}
공사 위험 사유: {data['construction_reason']}

영향 프로젝트: {data['project']}

그래프 경로:

{data['disaster']}
→ {data['construction_risk']}
→ {data['project']}
"""


# ============================================================
# 10. LangChain을 이용한 자연어 설명 생성
# ============================================================

def generate_llm_explanation(analysis_text):

    response = llm_chain.invoke({
        "analysis_data": analysis_text
    })

    return response.content


# ============================================================
# 11. 메인 실행
# ============================================================

def main():

    print("=" * 70)
    print("전력 기자재 공급망 위험 분석 시스템")
    print("=" * 70)


    # ========================================================
    # STEP 1. 원자재 가격 분석
    # ========================================================

    print("\n[1] 원자재 가격 상승 분석")
    print("-" * 70)

    material_results = analyze_material_risks()

    for data in material_results:

        print(f"\n원자재 : {data['material']}")
        print(f"기준가격 : {data['standard_price']}")
        print(f"현재가격 : {data['current_price']}")
        print(f"상승률 : {data['increase_rate']:.1f}%")
        print(f"위험도 : {data['risk_level']}")

        print(
            f"영향경로 : "
            f"{data['material']} → "
            f"{data['equipment']} → "
            f"{data['supply_problem']} → "
            f"{data['project']}"
        )

        # 10% 이상 상승한 경우 LLM 분석
        if data["increase_rate"] >= 10:

            analysis_text = create_material_analysis_text(data)

            explanation = generate_llm_explanation(
                analysis_text
            )

            print("\n[AI 분석]")
            print(explanation)


    # ========================================================
    # STEP 2. 외부 리스크 분석
    # ========================================================

    print("\n\n[2] 외부 공급망 리스크 분석")
    print("-" * 70)

    external_results = analyze_external_risks()

    for data in external_results:

        print(f"\n외부 리스크 : {data['risk_name']}")

        print(
            f"영향경로 : "
            f"{data['risk_name']} → "
            f"{data['material']} → "
            f"{data['equipment']} → "
            f"{data['supply_problem']} → "
            f"{data['project']}"
        )

        analysis_text = create_external_analysis_text(data)

        explanation = generate_llm_explanation(
            analysis_text
        )

        print("\n[AI 분석]")
        print(explanation)


    # ========================================================
    # STEP 3. 자연재해 분석
    # ========================================================

    print("\n\n[3] 자연재해 위험 분석")
    print("-" * 70)

    disaster_results = analyze_disaster_risks()

    for data in disaster_results:

        print(f"\n자연재해 : {data['disaster']}")

        print(
            f"영향경로 : "
            f"{data['disaster']} → "
            f"{data['construction_risk']} → "
            f"{data['project']}"
        )

        analysis_text = create_disaster_analysis_text(data)

        explanation = generate_llm_explanation(
            analysis_text
        )

        print("\n[AI 분석]")
        print(explanation)


    print("\n")
    print("=" * 70)
    print("분석 완료")
    print("=" * 70)


# ============================================================
# 12. 실행
# ============================================================

if __name__ == "__main__":

    try:
        main()

    except Exception as e:

        print("\n[ERROR]")
        print(e)

    finally:

        driver.close()