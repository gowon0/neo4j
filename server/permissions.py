"""권한 목록과 기본 역할.

화면 접근 권한 = 해당 화면의 *.view (시뮬레이션은 simulation.run).
내보내기는 조회 권한과 내보내기 권한이 모두 있어야 한다.
"""

PERMISSIONS = [
    ("dashboard.view", "대시보드 조회", "대시보드"),
    ("forecast.view", "수요예측 조회", "수요예측"),
    ("forecast.export", "수요예측 내보내기", "수요예측"),
    ("orders.view", "발주관리 화면 조회", "발주"),
    ("orders.create", "발주 등록", "발주"),
    ("orders.update", "발주 상태 변경", "발주"),
    ("orders.export", "발주 목록 내보내기", "발주"),
    ("inventory.view", "재고관리 조회", "재고"),
    ("inventory.export", "재고 내보내기", "재고"),
    ("simulation.run", "시뮬레이션 실행", "시뮬레이션"),
    ("simulation.export", "시뮬레이션 내보내기", "시뮬레이션"),
    ("risks.view", "위험 알림 조회", "위험 알림"),
    ("risks.refresh", "위험 알림 새로 분석(AI 호출)", "위험 알림"),
    ("risks.export", "위험 알림 내보내기", "위험 알림"),
    ("data.view", "데이터 관리 조회", "데이터"),
    ("data.refresh", "데이터 새로고침", "데이터"),
    ("settings.view", "설정 조회", "설정"),
    ("users.manage", "사용자 관리", "관리"),
    ("roles.manage", "역할·권한 관리", "관리"),
    ("audit.view", "감사 로그 조회", "관리"),
]

ALL = [code for code, _, _ in PERMISSIONS]
ALL_SET = frozenset(ALL)

ADMIN_ROLE = "관리자"

DEFAULT_ROLES = [
    {
        "name": ADMIN_ROLE,
        "description": "모든 기능과 사용자·권한·감사 로그 관리",
        "permissions": ALL,
    },
    {
        "name": "구매담당",
        "description": "발주 등록·변경, 수요예측·재고 조회, 시뮬레이션",
        "permissions": [
            "dashboard.view", "forecast.view", "forecast.export",
            "orders.view", "orders.create", "orders.update", "orders.export",
            "inventory.view", "inventory.export",
            "simulation.run", "simulation.export",
            "risks.view", "risks.export",
        ],
    },
    {
        "name": "재고담당",
        "description": "재고 조회·내보내기, 발주는 조회만",
        "permissions": [
            "dashboard.view", "forecast.view",
            "orders.view", "inventory.view", "inventory.export",
            "risks.view",
        ],
    },
    {
        "name": "수요계획",
        "description": "수요예측·시뮬레이션·위험 분석·데이터 조회",
        "permissions": [
            "dashboard.view", "forecast.view", "forecast.export",
            "inventory.view",
            "simulation.run", "simulation.export",
            "risks.view", "risks.refresh", "risks.export",
            "data.view",
        ],
    },
    {
        "name": "조회자",
        "description": "대시보드·수요예측·재고·위험 알림 조회만",
        "permissions": [
            "dashboard.view", "forecast.view", "inventory.view", "risks.view",
        ],
    },
]


def catalog():

    return [
        {"code": code, "label": label, "group": group}
        for code, label, group in PERMISSIONS
    ]


def valid(codes):
    """알 수 없는 권한 코드를 제거한 정렬된 목록."""

    return sorted({c for c in codes if c in ALL_SET}, key=ALL.index)
