from database.neo4j_client import Neo4jClient

from analysis.material import analyze_materials
from analysis.external_risk import analyze_external_risks
from analysis.disaster import analyze_disasters

from llm.chain import generate_explanation

from llm.formatter import (
    format_material_analysis,
    format_external_risk,
    format_disaster
)


def main():

    print("=" * 70)
    print("전력 기자재 공급망 위험 분석 시스템")
    print("=" * 70)


    # ========================================================
    # Neo4j 연결
    # ========================================================

    db = Neo4jClient()


    try:

        # ====================================================
        # 1. 원자재 분석
        # ====================================================

        print("\n[1] 원자재 가격 분석")
        print("-" * 70)

        materials = analyze_materials(db)


        for data in materials:

            print(f"\n원자재: {data['material']}")
            print(f"기준가격: {data['standard_price']}")
            print(f"현재가격: {data['current_price']}")
            print(f"상승률: {data['increase_rate']:.2f}%")
            print(f"위험도: {data['risk_level']}")

            print(
                f"경로: "
                f"{data['material']} → "
                f"{data['equipment']} → "
                f"{data['supply_problem']} → "
                f"{data['project']}"
            )


            # 위험한 경우만 LLM 분석
            if data["increase_rate"] >= 10:

                analysis_text = format_material_analysis(
                    data
                )

                explanation = generate_explanation(
                    analysis_text
                )

                print("\n[AI 분석]")
                print(explanation)


        # ====================================================
        # 2. 외부 리스크
        # ====================================================

        print("\n\n[2] 외부 공급망 리스크")
        print("-" * 70)

        external_risks = analyze_external_risks(db)


        for data in external_risks:

            print(f"\n리스크: {data['risk_name']}")

            print(
                f"경로: "
                f"{data['risk_name']} → "
                f"{data['material']} → "
                f"{data['equipment']} → "
                f"{data['supply_problem']} → "
                f"{data['project']}"
            )


            analysis_text = format_external_risk(
                data
            )

            explanation = generate_explanation(
                analysis_text
            )

            print("\n[AI 분석]")
            print(explanation)


        # ====================================================
        # 3. 자연재해
        # ====================================================

        print("\n\n[3] 자연재해 위험")
        print("-" * 70)

        disasters = analyze_disasters(db)


        for data in disasters:

            print(f"\n재해: {data['disaster']}")

            print(
                f"경로: "
                f"{data['disaster']} → "
                f"{data['construction_risk']} → "
                f"{data['project']}"
            )


            analysis_text = format_disaster(
                data
            )

            explanation = generate_explanation(
                analysis_text
            )

            print("\n[AI 분석]")
            print(explanation)


    finally:

        db.close()


    print("\n")
    print("=" * 70)
    print("분석 완료")
    print("=" * 70)


if __name__ == "__main__":

    main()