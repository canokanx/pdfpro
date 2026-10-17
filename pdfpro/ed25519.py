# -*- coding: utf-8 -*-
"""
Ed25519 imza (RFC 8032 referans uygulamasi, saf Python - ek kutuphane gerektirmez).
Guncelleme paketlerinin gercekten yoneticiden geldigini dogrulamak icin kullanilir.
"""
import hashlib
import os

p = 2 ** 255 - 19
q = 2 ** 252 + 27742317777372353535851937790883648493


def _inv(x):
    return pow(x, p - 2, p)


d = -121665 * _inv(121666) % p
_SQRT_M1 = pow(2, (p - 1) // 4, p)


def _sha512(s):
    return hashlib.sha512(s).digest()


def _add(P, Q):
    A, B = (P[1] - P[0]) * (Q[1] - Q[0]) % p, (P[1] + P[0]) * (Q[1] + Q[0]) % p
    C, D = 2 * P[3] * Q[3] * d % p, 2 * P[2] * Q[2] % p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F, G * H, F * G, E * H)


def _mul(s, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _equal(P, Q):
    if (P[0] * Q[2] - Q[0] * P[2]) % p != 0:
        return False
    return (P[1] * Q[2] - Q[1] * P[2]) % p == 0


def _recover_x(y, sign):
    if y >= p:
        return None
    x2 = (y * y - 1) * _inv(d * y * y + 1)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (p + 3) // 8, p)
    if (x * x - x2) % p != 0:
        x = x * _SQRT_M1 % p
    if (x * x - x2) % p != 0:
        return None
    if (x & 1) != sign:
        x = p - x
    return x


_gy = 4 * _inv(5) % p
_gx = _recover_x(_gy, 0)
G = (_gx, _gy, 1, _gx * _gy % p)


def _compress(P):
    zinv = _inv(P[2])
    x, y = P[0] * zinv % p, P[1] * zinv % p
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % p)


def _expand(secret):
    if len(secret) != 32:
        raise ValueError("Gizli anahtar 32 bayt olmali")
    h = _sha512(secret)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def _modq(s):
    return int.from_bytes(_sha512(s), "little") % q


def anahtar_uret():
    """(gizli_32bayt, acik_32bayt)"""
    gizli = os.urandom(32)
    return gizli, acik_anahtar(gizli)


def acik_anahtar(gizli):
    a, _ = _expand(gizli)
    return _compress(_mul(a, G))


def imzala(gizli, mesaj):
    a, onek = _expand(gizli)
    A = _compress(_mul(a, G))
    r = _modq(onek + mesaj)
    Rs = _compress(_mul(r, G))
    h = _modq(Rs + A + mesaj)
    s = (r + h * a) % q
    return Rs + int.to_bytes(s, 32, "little")


def dogrula(acik, mesaj, imza):
    try:
        if len(acik) != 32 or len(imza) != 64:
            return False
        A = _decompress(acik)
        R = _decompress(imza[:32])
        if not A or not R:
            return False
        s = int.from_bytes(imza[32:], "little")
        if s >= q:
            return False
        h = _modq(imza[:32] + acik + mesaj)
        return _equal(_mul(s, G), _add(R, _mul(h, A)))
    except Exception:
        return False
