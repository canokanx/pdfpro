# -*- coding: utf-8 -*-
"""
PDF PRO - Resim (tarama / fotograf / kimlik karti) uzerindeki yaziyi duzeltme

 1) bul()      : Tiklanan noktadaki (veya cizilen kutudaki) yaziyi OCR ile okur. Yazi yan veya
                 ters duruyorsa (kimlik kartlari, ehliyet arkasi) yonu kendisi bulur.
                 Harflerin gercek taban cizgisini, buyuk harf yuksekligini, rengini ve
                 kalinligini resimden olcer.
 2) degistir() : Eski yaziyi resimden siler, arka plan dokusunu yeniden olusturur (inpaint)
                 ve ayni yer / renk / boy / yon / genislikte yeni yaziyi yazar.

OpenCV (cv2) varsa doku korunur; yoksa cevre rengiyle duz ortulur.
"""
import io
import math

from .cekirdek import fitz, PdfProHata

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    import cv2
except Exception:
    cv2 = None

OLCEK = 4.0            # isleme cozunurlugu (4 = 288 dpi)
_CAP_ONBELLEK = {}


def cv2_var():
    return cv2 is not None and np is not None


# ------------------------------------------------------------------ yardimcilar
def _sayfa_resmi(page, rect, olcek=OLCEK):
    pix = page.get_pixmap(clip=rect, matrix=fitz.Matrix(olcek, olcek), alpha=False, annots=False)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return np.ascontiguousarray(a[..., :3])


def _dondur_nokta(u, v, k, w, h):
    """np.rot90(img, k) sonrasi (u,v) noktasinin yeni yeri. w,h: dondurulmeden onceki boyut."""
    for _ in range(k % 4):
        u, v, w, h = v, w - 1 - u, h, w
    return u, v


def _geri_dondur_nokta(x, y, k, w, h):
    """_dondur_nokta'nin tersi. w,h: ORIJINAL (dondurulmemis) boyut."""
    kk = (4 - k % 4) % 4
    ww, hh = (h, w) if k % 2 else (w, h)
    return _dondur_nokta(x, y, kk, ww, hh)


def _pil(a):
    from PIL import Image
    return Image.fromarray(a)


def _ocr_hazirla():
    from .ocr import _hazirla
    return _hazirla()


def cap_orani(font):
    """Fontun buyuk harf yuksekligi / font boyu (Arial ~0.716)."""
    anahtar = id(font)
    if anahtar in _CAP_ONBELLEK:
        return _CAP_ONBELLEK[anahtar]
    oran = 0.716
    try:
        from PIL import ImageFont
        f = ImageFont.truetype(io.BytesIO(font.buffer), 1000)
        b = f.getbbox("H")
        if b and b[3] > b[1]:
            oran = (b[3] - b[1]) / 1000.0
    except Exception:
        pass
    if not 0.5 < oran < 0.9:
        oran = 0.716
    _CAP_ONBELLEK[anahtar] = oran
    return oran


def _resim_alani(page, x, y):
    """Tiklanan noktayi iceren en kucuk resmin sayfadaki alani (yoksa None)."""
    p = fitz.Point(x, y)
    en_kucuk = None
    try:
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") == 1:
                r = fitz.Rect(b["bbox"])
                if r.contains(p) and (en_kucuk is None or r.get_area() < en_kucuk.get_area()):
                    en_kucuk = r
    except Exception:
        pass
    return en_kucuk


def _yazi_maskesi(parca):
    """Yazi piksellerinin maskesi (255 = yazi). Yazi zeminden koyu da olabilir acik da."""
    if parca.size == 0:
        return np.zeros(parca.shape[:2], np.uint8), True
    gri = (0.299 * parca[..., 0] + 0.587 * parca[..., 1] + 0.114 * parca[..., 2]).astype(np.uint8)
    kenar = np.concatenate([gri[0, :], gri[-1, :], gri[:, 0], gri[:, -1]])
    zemin = float(np.median(kenar)) if kenar.size else 255.0
    koyu_yazi = (zemin - float(np.percentile(gri, 3))) >= (float(np.percentile(gri, 97)) - zemin)
    g = gri if koyu_yazi else (255 - gri)
    if cv2 is not None:
        g2 = cv2.GaussianBlur(g, (3, 3), 0)
        _, m = cv2.threshold(g2, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    else:
        zz = zemin if koyu_yazi else 255 - zemin
        m = ((g < zz - 40) * 255).astype(np.uint8)
    return m, koyu_yazi


def _olcumler(maske):
    """Harflerin taban cizgisi, ust cizgisi, sol/sag kenari ve kalinligi (piksel)."""
    H, W = maske.shape
    sonuc = {"taban": H - 1, "ust": 0, "sol": 0, "sag": W - 1, "kalinlik": 0}
    if maske.sum() == 0:
        return sonuc
    if cv2 is not None:
        n, _, stats, _ = cv2.connectedComponentsWithStats((maske > 0).astype(np.uint8), 8)
        parcalar = [stats[i] for i in range(1, n) if stats[i][cv2.CC_STAT_AREA] >= 6]
        if parcalar:
            yuks = np.array([s[cv2.CC_STAT_HEIGHT] for s in parcalar])
            buyuk = [s for s in parcalar if s[cv2.CC_STAT_HEIGHT] >= 0.8 * np.median(sorted(yuks)[-max(1, len(yuks) // 2):])]
            altlar = np.array([s[cv2.CC_STAT_TOP] + s[cv2.CC_STAT_HEIGHT] for s in buyuk])
            ustler = np.array([s[cv2.CC_STAT_TOP] for s in buyuk])
            taban = float(np.median(altlar))
            # noktali / sapkali harflerin (İ, Ü, Ş) ust parcalarini sayma: govdelerin ust medyani
            ust = float(np.median(ustler))
            sonuc.update(taban=taban, ust=ust,
                         sol=float(min(s[cv2.CC_STAT_LEFT] for s in parcalar)),
                         sag=float(max(s[cv2.CC_STAT_LEFT] + s[cv2.CC_STAT_WIDTH] for s in parcalar)))
        dt = cv2.distanceTransform((maske > 0).astype(np.uint8), cv2.DIST_L2, 3)
        sonuc["kalinlik"] = 2 * float(np.median(dt[maske > 0])) + 1
    else:
        satirlar = np.where(maske.any(axis=1))[0]
        sutunlar = np.where(maske.any(axis=0))[0]
        sonuc.update(taban=float(satirlar.max()), ust=float(satirlar.min()),
                     sol=float(sutunlar.min()), sag=float(sutunlar.max()))
    return sonuc


# ------------------------------------------------------------------ bul
def _ocr_kelimeler(pyt, r, dil, psm):
    veri = pyt.image_to_data(_pil(r), lang=dil, config=f"--psm {psm}", output_type=pyt.Output.DICT)
    kelimeler = []
    for i, t in enumerate(veri["text"]):
        t = (t or "").strip()
        try:
            guven = float(veri["conf"][i])
        except Exception:
            guven = -1
        if t and guven >= 0:
            kelimeler.append({"t": t, "c": guven, "x": veri["left"][i], "y": veri["top"][i],
                              "w": veri["width"][i], "h": veri["height"][i],
                              "anahtar": (veri["block_num"][i], veri["par_num"][i], veri["line_num"][i])})
    return kelimeler


_ETIKET = __import__("re").compile(r"^\w{1,3}[.:)]$")


def _tiklanan_grup(kelimeler, hx, hy):
    """Tiklanan kelimeyi ve ona bitisik (ayni satirda, araligi dar) kelimeleri dondurur.
    '4b.' '2.' gibi alan numaralari (etiketler) gruba katilmaz."""
    pay = 6
    secili = [w for w in kelimeler if w["x"] - pay <= hx <= w["x"] + w["w"] + pay
              and w["y"] - pay <= hy <= w["y"] + w["h"] + pay]
    if not secili:
        return None
    ana = min(secili, key=lambda w: abs(w["x"] + w["w"] / 2 - hx) + abs(w["y"] + w["h"] / 2 - hy))
    satir = sorted([w for w in kelimeler if w["anahtar"] == ana["anahtar"]], key=lambda w: w["x"])
    i = satir.index(ana)
    yuk = ana["h"]

    def bitisik(a, b):
        return b["x"] - (a["x"] + a["w"]) < yuk * 0.6 and not _ETIKET.match(a["t"] if a is not ana else "")

    sol = i
    while sol > 0 and bitisik(satir[sol - 1], satir[sol]) and not _ETIKET.match(satir[sol - 1]["t"]):
        sol -= 1
    sag = i
    while sag < len(satir) - 1 and satir[sag + 1]["x"] - (satir[sag]["x"] + satir[sag]["w"]) < yuk * 0.6:
        sag += 1
    return satir[sol:sag + 1]


def _yon_puani(kelimeler):
    """Bu yonde okunan yazinin ne kadar 'gercek' oldugu: anlamli kelimelerin guven ortalamasi."""
    iyi = [w["c"] for w in kelimeler if len(w["t"]) >= 3 and any(ch.isalnum() for ch in w["t"])]
    if not iyi:
        return 0.0
    return (sum(iyi) / len(iyi)) * math.log(1 + len(iyi))


def bul(page, x=None, y=None, alan=None, dil="tur+eng"):
    """Resimdeki yaziyi bulur. x,y: tiklanan nokta  |  alan: cizilen kutu (fitz.Rect).
    Bulunamazsa None."""
    if np is None:
        raise PdfProHata("Bu özellik için numpy gerekli. KURULUM.bat'ı tekrar çalıştırın.")
    pyt = _ocr_hazirla()
    sayfa = page.rect
    ra = _resim_alani(page, x, y) if alan is None else None

    denemeler = []
    if alan is not None:
        bolge = fitz.Rect(alan) & sayfa
        denemeler = [(bolge, k) for k in (0, 1, 3, 2)]
    else:
        genis = fitz.Rect(x - 150, y - 28, x + 150, y + 28) & sayfa       # once yatay, hizli
        kare = fitz.Rect(x - 110, y - 110, x + 110, y + 110) & sayfa     # sonra yan/ters yazi
        if ra is not None:
            genis &= ra
            kare &= ra
        denemeler = [(genis, 0), (kare, 1), (kare, 3), (kare, 2)]

    en_iyi = None
    for bolge, k in denemeler:
        if bolge.is_empty or bolge.width < 4 or bolge.height < 4:
            continue
        if en_iyi is not None and k == 2 and en_iyi[0] > 150:
            continue                    # ters yazi denemesine gerek yok
        resim = _sayfa_resmi(page, bolge)
        H, W = resim.shape[:2]
        r = np.ascontiguousarray(np.rot90(resim, k))
        try:
            kelimeler = _ocr_kelimeler(pyt, r, dil, 6 if alan is not None else 11)
        except PdfProHata:
            raise
        except Exception as e:
            raise PdfProHata(f"OCR çalışmadı:\n{e}")
        puan = _yon_puani(kelimeler)
        if alan is not None:
            grup = [w for w in kelimeler if w["c"] > 10 or len(w["t"]) > 1]
        else:
            hx, hy = _dondur_nokta((x - bolge.x0) * OLCEK, (y - bolge.y0) * OLCEK, k, W, H)
            grup = _tiklanan_grup(kelimeler, hx, hy)
        if not grup:
            continue
        if en_iyi is None or puan > en_iyi[0]:
            en_iyi = (puan, k, grup, r, bolge, W, H)
        if k == 0 and min(w["c"] for w in grup) >= 75 and puan > 150:
            break           # duz yazi guvenle bulundu, yan yonleri deneme
    if not en_iyi:
        return None
    _, k, grup, r, bolge, W, H = en_iyi
    # metin
    satirlar = {}
    for w in grup:
        satirlar.setdefault(w["anahtar"], []).append(w)
    sirali = sorted(satirlar.values(), key=lambda ws: min(w["y"] for w in ws))
    metin = "\n".join(" ".join(w["t"] for w in sorted(ws, key=lambda w: w["x"])) for ws in sirali)
    kutu_r = (min(w["x"] for w in grup), min(w["y"] for w in grup),
              max(w["x"] + w["w"] for w in grup), max(w["y"] + w["h"] for w in grup))
    return _bilgi_hesapla(r, k, kutu_r, metin, bolge, W, H, len(sirali), pyt, dil)


def _kutuyu_genislet(r, x0, y0, x1, y1):
    """OCR kelimeyi eksik okuduysa (or. 'AYNUR' yerine 'AYN') ayni satirdaki bitisik harfleri de kutuya katar."""
    if cv2 is None:
        return x0, x1
    h = y1 - y0
    ex0, ex1 = max(0, x0 - 3 * h), min(r.shape[1], x1 + 3 * h)
    parca = r[y0:y1, ex0:ex1]
    m, _ = _yazi_maskesi(parca)
    n, _, st, _ = cv2.connectedComponentsWithStats((m > 0).astype(np.uint8), 8)
    harfler = []
    for i in range(1, n):
        x, y, w, hh, alan = st[i]
        if alan < 8 or hh < 0.3 * h or hh > 1.3 * h:
            continue
        harfler.append((ex0 + x, ex0 + x + w))
    if not harfler:
        return x0, x1
    harfler.sort()
    bosluk = 0.35 * h
    degisti = True
    while degisti:
        degisti = False
        for a, b in harfler:
            if a < x0 and b >= x0 - bosluk and b <= x1:
                x0, degisti = a, True
            if b > x1 and a <= x1 + bosluk and a >= x0:
                x1, degisti = b, True
    return x0, x1


def _bilgi_hesapla(r, k, kutu_r, metin, bolge, W, H, satir_sayisi, pyt=None, dil="tur+eng"):
    x0, y0, x1, y1 = [int(v) for v in kutu_r]
    pay = 3
    x0, y0 = max(0, x0 - pay), max(0, y0 - pay)
    x1, y1 = min(r.shape[1], x1 + pay), min(r.shape[0], y1 + pay)
    if satir_sayisi == 1:
        gx0, gx1 = _kutuyu_genislet(r, x0, y0, x1, y1)
        if (gx0, gx1) != (x0, x1):
            x0, x1 = gx0, gx1
            if pyt is not None:   # genisleyen kutuyu tek satir olarak yeniden oku
                try:
                    t = pyt.image_to_string(_pil(np.ascontiguousarray(r[y0:y1, max(0, x0 - 4):x1 + 4])),
                                            lang=dil, config="--psm 7").strip()
                    if t:
                        metin = t
                except Exception:
                    pass
    parca = r[y0:y1, x0:x1]
    maske, koyu = _yazi_maskesi(parca)
    if maske.sum() > 0:
        # murekkebin ozu: kenar (yumusama) piksellerini degil en dolgun %40'ini al
        gri = parca.mean(axis=2)
        mp = maske > 0
        esik = np.percentile(gri[mp], 40 if koyu else 60)
        oz = mp & ((gri <= esik) if koyu else (gri >= esik))
        if oz.sum() < 5:
            oz = mp
        renk = tuple(float(np.median(parca[..., c][oz])) / 255 for c in range(3))
    else:
        renk = (0, 0, 0)
    if satir_sayisi == 1:
        o = _olcumler(maske)
        cap_px = max(2.0, o["taban"] - o["ust"])
        if not any(ch.isupper() or ch.isdigit() or ch in "bdfhklt" for ch in metin):
            cap_px = cap_px / 0.725          # sadece kucuk harf: olculen x-yuksekligi
        taban_px = y0 + o["taban"]
        sol_px = x0 + o["sol"]
        gen_px = max(1.0, o["sag"] - o["sol"])
        kalinlik_px = o["kalinlik"]
        aralik_pt = cap_px / OLCEK * 1.75
    else:
        satir_yuk = (y1 - y0) / satir_sayisi
        cap_px = satir_yuk * 0.62
        taban_px = y0 + satir_yuk * 0.8
        sol_px, gen_px = x0, (x1 - x0)
        kalinlik_px = 0
        if cv2 is not None and maske.sum() > 20:
            dt = cv2.distanceTransform((maske > 0).astype(np.uint8), cv2.DIST_L2, 3)
            kalinlik_px = 2 * float(np.percentile(dt[maske > 0], 80))
        aralik_pt = satir_yuk / OLCEK
    cap_pt = cap_px / OLCEK
    # sayfa koordinatlarina cevir
    sx = lambda u: bolge.x0 + u / OLCEK
    sy = lambda v: bolge.y0 + v / OLCEK
    p0 = _geri_dondur_nokta(sol_px, taban_px, k, W, H)
    p1 = _geri_dondur_nokta(sol_px + 100, taban_px, k, W, H)
    taban = (sx(p0[0]), sy(p0[1]))
    dx, dy = sx(p1[0]) - taban[0], sy(p1[1]) - taban[1]
    yon_aci = int(round(math.degrees(math.atan2(-dy, dx)) / 90.0)) * 90 % 360
    koseler = [_geri_dondur_nokta(a, b, k, W, H) for a, b in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
    kutu = fitz.Rect(sx(min(c[0] for c in koseler)), sy(min(c[1] for c in koseler)),
                     sx(max(c[0] for c in koseler)), sy(max(c[1] for c in koseler)))
    return {"metin": metin, "kutu": tuple(kutu), "k": k, "cap_pt": cap_pt,
            "boyut": round(max(3.0, min(cap_pt / 0.716, 120.0)), 1),
            "renk": renk, "kalin": (kalinlik_px / max(cap_px, 1)) > 0.22,
            "taban": taban, "yon_aci": yon_aci, "genislik_pt": gen_px / OLCEK,
            "satir_araligi": aralik_pt, "koyu_yazi": koyu, "satir_sayisi": satir_sayisi}


def olc(page, rect, metin):
    """Bilinen bir yazinin (or. OCR katmanindan) resimdeki olculerini cikarir; OCR yapmaz."""
    if np is None:
        return None
    rect = fitz.Rect(rect)
    pay = max(1.5, rect.height * 0.15)
    bolge = fitz.Rect(rect.x0 - pay, rect.y0 - pay, rect.x1 + pay, rect.y1 + pay) & page.rect
    if bolge.is_empty:
        return None
    r = _sayfa_resmi(page, bolge)
    H, W = r.shape[:2]
    kutu_r = ((rect.x0 - bolge.x0) * OLCEK, (rect.y0 - bolge.y0) * OLCEK,
              (rect.x1 - bolge.x0) * OLCEK, (rect.y1 - bolge.y0) * OLCEK)
    try:
        return _bilgi_hesapla(r, 0, kutu_r, metin, bolge, W, H, metin.count("\n") + 1)
    except Exception:
        return None


# ------------------------------------------------------------------ degistir
def eski_yaziyi_sil(page, kutu, boyut):
    """Kutudaki yaziyi resimden siler, zemini yeniden olusturur."""
    from .duzenle import guvenli_sil
    kutu = fitz.Rect(kutu)
    pay = max(2.0, boyut * 0.3)
    alan = fitz.Rect(kutu.x0 - pay, kutu.y0 - pay, kutu.x1 + pay, kutu.y1 + pay) & page.rect
    r = _sayfa_resmi(page, alan)
    H, W = r.shape[:2]
    ix0, iy0 = int((kutu.x0 - alan.x0) * OLCEK), int((kutu.y0 - alan.y0) * OLCEK)
    ix1, iy1 = int(math.ceil((kutu.x1 - alan.x0) * OLCEK)), int(math.ceil((kutu.y1 - alan.y0) * OLCEK))
    ic = r[max(0, iy0):iy1, max(0, ix0):ix1]
    m_ic, koyu = _yazi_maskesi(ic)
    if cv2 is not None and ic.size:
        # yerel zeminden belirgin farkli pikseller (yumusak kenarlar, desenli zemin): Otsu'ya ek
        gri = cv2.cvtColor(ic, cv2.COLOR_RGB2GRAY).astype(np.int16)
        k = max(15, (min(ic.shape[:2]) // 2) * 2 + 1)
        zemin = cv2.medianBlur(cv2.cvtColor(ic, cv2.COLOR_RGB2GRAY), min(k, 51) | 1).astype(np.int16)
        fark = (zemin - gri) if koyu else (gri - zemin)
        m_ic = np.maximum(m_ic, ((fark > 22) * 255).astype(np.uint8))
    maske = np.zeros((H, W), np.uint8)
    maske[max(0, iy0):iy1, max(0, ix0):ix1] = m_ic
    if cv2 is not None:
        maske = cv2.dilate(maske, np.ones((3, 3), np.uint8), iterations=4)
        temiz = cv2.inpaint(r, maske, max(3, int(OLCEK * 2)), cv2.INPAINT_TELEA)
        # inpaint izlerini yumusat: sadece maske icinde hafif bulanik
        bul = cv2.GaussianBlur(temiz, (5, 5), 0)
        temiz = np.where(maske[..., None] > 0, bul, temiz)
    else:
        temiz = r.copy()
        dis = maske == 0
        if dis.any():
            temiz[maske > 0] = np.median(r[dis], axis=0).astype(np.uint8)
    buf = io.BytesIO()
    _pil(temiz).save(buf, "PNG")
    try:  # gizli OCR katmanindaki eski yaziyi da kaldir (arama / kopyalama dogru olsun)
        guvenli_sil(page, kutu)
    except Exception:
        pass
    page.insert_image(alan, stream=buf.getvalue(), keep_proportion=False, overlay=True)


def degistir(page, bilgi, yeni_metin, font=None, boyut=None, renk=None, hiza="sol", genislik_uydur=True):
    """Resimdeki eski yaziyi siler ve ayni yer / renk / boy / yonde yenisini yazar.
    font: fitz.Font (None = Arial benzeri). genislik_uydur: harf genisligini orijinale benzet."""
    from .duzenle import font_al, sayfa_hazirla, tw_yaz
    if np is None:
        raise PdfProHata("Bu özellik için numpy gerekli.")
    sayfa_hazirla(page)
    font = font or font_al(False, bilgi.get("kalin", False), False)
    if boyut:
        b = boyut
    else:
        b = bilgi.get("cap_pt", bilgi["boyut"] * 0.716) / cap_orani(font)
    eski_yaziyi_sil(page, bilgi["kutu"], b)
    if not yeni_metin.strip():
        return
    rk = renk or bilgi["renk"]
    aci = bilgi.get("yon_aci", 0)
    tx, ty = bilgi["taban"]
    satirlar = yeni_metin.split("\n")
    aralik = bilgi.get("satir_araligi") or b * 1.15
    ux, uy = math.cos(math.radians(aci)), -math.sin(math.radians(aci))   # yazi yonu (sayfada)
    nx, ny = -uy, ux                                                       # bir alt satira gecis yonu
    # yatay olcek: eski yazinin genisligine benzet (dar/genis fontlar icin)
    olcek = 1.0
    eski = bilgi.get("metin", "").split("\n")[0]
    if genislik_uydur and eski and bilgi.get("genislik_pt") and bilgi.get("satir_sayisi", 1) == 1:
        tahmini = font.text_length(eski, b)
        if tahmini > 1:
            olcek = max(0.72, min(1.2, bilgi["genislik_pt"] / tahmini))
    eski_gen = bilgi.get("genislik_pt") or 0
    for i, s in enumerate(satirlar):
        uz = font.text_length(s, b) * olcek
        kay = 0.0
        if hiza == "orta":
            kay = (eski_gen - uz) / 2
        elif hiza == "sag":
            kay = eski_gen - uz
        px = tx + ux * kay + nx * i * aralik
        py = ty + uy * kay + ny * i * aralik
        tw = fitz.TextWriter(page.rect, color=rk)
        tw.append(fitz.Point(px, py), s, font=font, fontsize=b)
        m = fitz.Matrix(olcek, 0, 0, 1, 0, 0)
        if aci:
            m = m * fitz.Matrix(aci)
        if aci or abs(olcek - 1) > 0.01:
            tw_yaz(page, tw, morph=(fitz.Point(px, py), m))
        else:
            tw_yaz(page, tw)
