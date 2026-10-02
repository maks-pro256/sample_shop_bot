import re


# Лимиты совпадают с длиной колонок в models.py: длиннее PostgreSQL не сохранит
NAME_MAX_LENGTH = 25
CATEGORY_NAME_MAX_LENGTH = 25
CARD_NAME_MAX_LENGTH = 50
CARD_DESCRIPTION_MAX_LENGTH = 256
ADDRESS_MIN_LENGTH = 5
ADDRESS_MAX_LENGTH = 300
MAX_PRICE = 10_000_000

RUSSIAN_PHONE = re.compile(r"^(?:\+7|7|8)(\d{10})$")


def clean_text(text: str | None, max_length: int, min_length: int = 1) -> str | None:
    """Убирает лишние пробелы; None, если текста нет или длина вне границ"""
    if not text:
        return None
    text = text.strip()
    return text if min_length <= len(text) <= max_length else None


def clean_name(text: str | None) -> str | None:
    """Имя из букв, пробелов и дефисов длиной 2–25 символов, например «Анна-Мария»"""
    if not text:
        return None
    name = " ".join(text.split())
    if not 2 <= len(name) <= NAME_MAX_LENGTH:
        return None
    if not all(char.isalpha() or char in " -" for char in name):
        return None
    return name.title()


def normalize_phone(text: str | None) -> str | None:
    """Российский номер в формате +7XXXXXXXXXX. Пробелы, скобки и дефисы допускаются"""
    if not text:
        return None
    match = RUSSIAN_PHONE.match(re.sub(r"[\s\-()]", "", text))
    return f"+7{match.group(1)}" if match else None


def parse_price(text: str | None) -> int | None:
    if not text or not text.strip().isdigit():
        return None
    price = int(text.strip())
    return price if 1 <= price <= MAX_PRICE else None
