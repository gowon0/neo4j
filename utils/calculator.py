from config.settings import (
    WARNING_THRESHOLD,
    DANGER_THRESHOLD,
    VERY_DANGER_THRESHOLD
)


def calculate_increase_rate(standard, current):

    try:

        standard = float(standard)
        current = float(current)

        if standard == 0:
            return 0.0

        return (
            (current - standard)
            / standard
        ) * 100

    except (TypeError, ValueError):

        return 0.0


def calculate_risk_level(increase_rate):

    if increase_rate >= VERY_DANGER_THRESHOLD:

        return "매우위험"

    if increase_rate >= DANGER_THRESHOLD:

        return "위험"

    if increase_rate >= WARNING_THRESHOLD:

        return "경고"

    return "정상"