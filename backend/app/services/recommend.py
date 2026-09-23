"""
Рекомендация для отдела благоустройства по микрорайону (простая и объяснимая эвристика).

  навесы      = базовое число по индексу дефицита тени (≥75 → 3, ≥60 → 2, ≥45 → 1)
                + по одному на каждые 2 открытые жалобы «нет тени»
  фонтанчики  = 1, если индекс ≥ 60, + по одному на каждую открытую жалобу «нужна вода»
  ремонт      = по числу открытых жалоб «не работает кондиционер на остановке»
  приоритет   = высокий (индекс ≥ 70), средний (≥ 50), низкий

Индекс отражает физику (нагрев, зелень, укрытия), жалобы — конкретные места, где болит сейчас.
Цифры — стартовая точка для выезда инспектора, а не смета.
"""
import math


def _plural(n: int, one: str, few: str, many: str) -> str:
    n100, n10 = n % 100, n % 10
    if n10 == 1 and n100 != 11:
        return one
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return few
    return many


def recommend(index: float, open_no_shade: int, open_need_fountain: int, open_broken_ac: int) -> dict:
    base = 3 if index >= 75 else 2 if index >= 60 else 1 if index >= 45 else 0
    shades = base + math.ceil(open_no_shade / 2)
    fountains = (1 if index >= 60 else 0) + open_need_fountain
    repairs = open_broken_ac
    priority = "high" if index >= 70 else "medium" if index >= 50 else "low"

    parts = []
    if shades:
        parts.append(f"установить {shades} {_plural(shades, 'навес', 'навеса', 'навесов')}")
    if fountains:
        parts.append(f"{fountains} {_plural(fountains, 'фонтанчик', 'фонтанчика', 'фонтанчиков')}")
    if repairs:
        parts.append(f"отремонтировать {repairs} {_plural(repairs, 'кондиционер', 'кондиционера', 'кондиционеров')}")
    text = (", ".join(parts) if parts else "плановый мониторинг").capitalize()
    return {"shades": shades, "fountains": fountains, "ac_repairs": repairs, "priority": priority, "text": text}
