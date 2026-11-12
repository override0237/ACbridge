"""Small privacy helpers."""


def mask_phone(phone: str) -> str:
    """'+237670123456' -> '+237 6** *** *56': enough to recognise your own number, nothing more."""
    digits = phone.lstrip("+")
    if len(digits) < 8:
        return "***"
    cc, rest = digits[:3], digits[3:]
    return f"+{cc} {rest[0]}{'*' * (len(rest) - 3)}{rest[-2:]}"
