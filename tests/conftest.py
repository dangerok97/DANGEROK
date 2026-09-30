"""Generatori di identificativi FITTIZI ma formalmente validi, solo per i test."""
import string

_DISP = [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23]


def cf_fittizio(base15: str = "RSSMRA80A01H501") -> str:
    dd = dict(zip("0123456789", _DISP[:10]))
    dd.update(zip(string.ascii_uppercase, _DISP))
    pp = {c: i for i, c in enumerate("0123456789")}
    pp.update({c: i for i, c in enumerate(string.ascii_uppercase)})
    tot = sum(dd[c] if i % 2 == 0 else pp[c] for i, c in enumerate(base15))
    return base15 + string.ascii_uppercase[tot % 26]


def piva_fittizia(base10: str = "1234567890") -> str:
    s = 0
    for i, ch in enumerate(base10):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        s += d
    return base10 + str((10 - s % 10) % 10)


def iban_fittizio(bban: str = "X0542811101000000123456") -> str:
    r = bban + "IT00"
    num = "".join(str(int(c, 36)) for c in r)
    chk = 98 - int(num) % 97
    return f"IT{chk:02d}{bban}"
