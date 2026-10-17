# -*- coding: utf-8 -*-
"""
PDF PRO - Sayfa uzerinde dogrudan duzenleme
- satir_bul / satir_degistir : var olan yaziyi tiklayip degistirme
- yazi_ekle                  : sayfaya yeni yazi
- beyaz_kutu                 : bir alani beyazla ortme
- resim_yerlestir            : imza / kase / logo yerlestirme
Tum koordinatlar sayfanin GORUNEN halindedir; once sayfa_hazirla() cagrilir.
"""
import os

from .cekirdek import fitz, PdfProHata

PROGRAM_KLASORU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONT_ONBELLEK = {}


# ------------------------------------------------------------------ font
def font_dosyasi(serif=False, kalin=False, italik=False):
    win = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    yerel = os.path.join(PROGRAM_KLASORU, "fonts")
    if serif:
        win_ad = {(0, 0): "times.ttf", (1, 0): "timesbd.ttf", (0, 1): "timesi.ttf", (1, 1): "timesbi.ttf"}
        dv_ad = {(0, 0): "DejaVuSerif.ttf", (1, 0): "DejaVuSerif-Bold.ttf",
                 (0, 1): "DejaVuSerif-Italic.ttf", (1, 1): "DejaVuSerif-BoldItalic.ttf"}
    else:
        win_ad = {(0, 0): "arial.ttf", (1, 0): "arialbd.ttf", (0, 1): "ariali.ttf", (1, 1): "arialbi.ttf"}
        dv_ad = {(0, 0): "DejaVuSans.ttf", (1, 0): "DejaVuSans-Bold.ttf",
                 (0, 1): "DejaVuSans-Oblique.ttf", (1, 1): "DejaVuSans-BoldOblique.ttf"}
    k = (int(bool(kalin)), int(bool(italik)))
    for aday in (os.path.join(win, win_ad[k]), os.path.join(yerel, dv_ad[k]),
                 os.path.join("/usr/share/fonts/truetype/dejavu", dv_ad[k]),
                 os.path.join(win, win_ad[(k[0], 0)]), os.path.join(yerel, dv_ad[(k[0], 0)]),
                 os.path.join(yerel, "DejaVuSans.ttf"), os.path.join(win, "arial.ttf")):
        if os.path.isfile(aday):
            return aday
    return None


def font_al(serif=False, kalin=False, italik=False):
    y = font_dosyasi(serif, kalin, italik)
    if y not in _FONT_ONBELLEK:
        _FONT_ONBELLEK[y] = fitz.Font(fontfile=y) if y else fitz.Font("helv")
    return _FONT_ONBELLEK[y]


def renk_int(c):
    return ((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255


# ------------------------------------------------------------------ hazirlik
def sayfa_hazirla(page):
    """Dondurulmus sayfayi duz hale getirir (gorunum degismez) ve icerigi sarar."""
    if page.rotation:
        try:
            page.remove_rotation()
        except Exception:
            pass
    try:
        page.wrap_contents()
    except Exception:
        pass


# ------------------------------------------------------------------ satir bulma
def metin_verisi(page):
    """satir_bul icin onbelleklenebilir sayfa verisi: yazi bloklari + yatay cizgiler."""
    bloklar = page.get_text("dict")["blocks"]
    cizgiler, dikeyler = [], []

    def kutu(r):
        if r.width > 3:
            cizgiler.append((r.x0, r.x1, r.y0))
            cizgiler.append((r.x0, r.x1, r.y1))
        if r.height > 3:
            dikeyler.append((r.x0, r.y0, r.y1))
            dikeyler.append((r.x1, r.y0, r.y1))
    try:
        for d in page.get_drawings():
            for it in d["items"]:
                if it[0] == "l":
                    a, b = it[1], it[2]
                    if abs(a.y - b.y) < 1.0 and abs(a.x - b.x) > 3:
                        cizgiler.append((min(a.x, b.x), max(a.x, b.x), (a.y + b.y) / 2))
                    elif abs(a.x - b.x) < 1.0 and abs(a.y - b.y) > 3:
                        dikeyler.append(((a.x + b.x) / 2, min(a.y, b.y), max(a.y, b.y)))
                elif it[0] == "re":
                    r = it[1]
                    if r.height < 2.5 and r.width > 3:
                        cizgiler.append((r.x0, r.x1, (r.y0 + r.y1) / 2))
                    elif r.width < 2.5 and r.height > 3:
                        dikeyler.append(((r.x0 + r.x1) / 2, r.y0, r.y1))
                    else:
                        kutu(r)
                elif it[0] == "qu":
                    kutu(it[1].rect)
    except Exception:
        pass
    return {"bloklar": bloklar, "cizgiler": cizgiler, "dikeyler": dikeyler,
            "sayfa_genislik": page.rect.width}


LIGATUR = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
           "\ufb05": "st", "\ufb06": "st", "\u00ad": ""}


def ligatur_coz(t):
    for a, b in LIGATUR.items():
        if a in t:
            t = t.replace(a, b)
    return t


def _ham_satirlar(bloklar, dikey=False):
    """Yatay satirlar (dikey=False) veya 90/180/270 derece donuk satirlar (dikey=True)."""
    for blok in bloklar:
        if blok.get("type") != 0:
            continue
        for satir in blok["lines"]:
            dx, dy = satir["dir"]
            yatay = abs(dy) <= 0.01 and dx > 0
            if yatay == dikey:
                continue
            if dikey and not (abs(dx) <= 0.01 or abs(dy) <= 0.01):
                continue                       # egik (or. 45 derece) yazi: desteklenmez
            spans = [s for s in satir["spans"] if s["text"].strip()]
            if spans:
                yield fitz.Rect(satir["bbox"]), spans, satir["dir"]


def _boy(spans):
    return max(s["size"] for s in spans)


def _birlesik_satirlar(bloklar):
    """Ayni taban cizgisinde bitisik duran parcalari (or. 'BAKANLI' + 'ĞI' ayri fontla)
    tek satirda birlestirir. Her satir: {'rect','metin','spans','origin','boy'}"""
    ham = sorted(((r, sp) for r, sp, _ in _ham_satirlar(bloklar)), key=lambda h: (round(h[1][0]["origin"][1], 1), h[0].x0))
    kullanildi = [False] * len(ham)
    sonuc = []
    for i, (r, sp) in enumerate(ham):
        if kullanildi[i]:
            continue
        boy = _boy(sp)
        taban = sp[0]["origin"][1]
        grup = [(r, sp)]
        kullanildi[i] = True
        degisti = True
        while degisti:
            degisti = False
            for j, (r2, sp2) in enumerate(ham):
                if kullanildi[j]:
                    continue
                if abs(sp2[0]["origin"][1] - taban) > max(1.2, boy * 0.15) or abs(_boy(sp2) - boy) > boy * 0.35:
                    continue
                sol, sag = min(g[0].x0 for g in grup), max(g[0].x1 for g in grup)
                if r2.x0 - sag < boy * 0.6 and sol - r2.x1 < boy * 0.6:
                    grup.append((r2, sp2))
                    kullanildi[j] = True
                    degisti = True
        grup.sort(key=lambda g: g[0].x0)
        rect = fitz.Rect(grup[0][0])
        metin, son_x1 = "", None
        for r2, sp2 in grup:
            rect |= r2
            parca = "".join(x["text"] for x in sp2)
            if son_x1 is not None and r2.x0 - son_x1 > boy * 0.2 and not metin.endswith(" ") and not parca.startswith(" "):
                metin += " "
            metin += parca
            son_x1 = r2.x1
        spans = [x for _, s2 in grup for x in s2]
        sonuc.append({"rect": rect, "metin": ligatur_coz(metin.strip()), "spans": spans,
                      "origin": tuple(grup[0][1][0]["origin"]), "boy": boy, "aci": 0})
    # donuk (yan / ters) satirlar: tek tek
    import math
    for r, sp, (dx, dy) in _ham_satirlar(bloklar, dikey=True):
        sonuc.append({"rect": r, "metin": ligatur_coz("".join(x["text"] for x in sp).strip()), "spans": sp,
                      "origin": tuple(sp[0]["origin"]), "boy": _boy(sp),
                      "aci": int(round(math.degrees(math.atan2(-dy, dx)))) % 360})
    return sonuc


def _arada_cizgi(cizgiler, a, b):
    """a (ustteki) ve b (alttaki) satirlari arasinda yatay cizgi (tablo cizgisi) var mi?"""
    y0, y1 = a["origin"][1] + 0.5, b["origin"][1] - b["boy"] * 0.6   # taban cizgisi ile ust harf arasi
    x0, x1 = max(a["rect"].x0, b["rect"].x0), min(a["rect"].x1, b["rect"].x1)
    for cx0, cx1, cy in cizgiler:
        if y0 < cy < y1 and cx0 < x1 and cx1 > x0:
            return True
    return False


def satir_bul(page, x, y, tolerans=2, veri=None):
    """(x,y) noktasindaki yaziyi dondurur; yoksa None.
    Ayni hucredeki / paragraftaki alt alta satirlar birlikte (paragraf olarak) dondurulur."""
    veri = veri if veri is not None else metin_verisi(page)
    if isinstance(veri, list):
        veri = {"bloklar": veri, "cizgiler": []}
    satirlar_tum = veri.get("_birlesik")
    if satirlar_tum is None:
        satirlar_tum = veri["_birlesik"] = _birlesik_satirlar(veri["bloklar"])
    p = fitz.Point(x, y)
    tohum, en_iyi_mesafe = None, 1e9
    for s_ in satirlar_tum:
        r = s_["rect"]
        if fitz.Rect(r.x0 - tolerans, r.y0 - tolerans, r.x1 + tolerans, r.y1 + tolerans).contains(p):
            m = abs((r.y0 + r.y1) / 2 - y)
            if m < en_iyi_mesafe:
                en_iyi_mesafe, tohum = m, s_
    if not tohum:
        return None
    boy = tohum["boy"]

    def uyumlu(a):
        if a.get("aci", 0) != 0 or tohum.get("aci", 0) != 0:
            return False
        if abs(a["boy"] - boy) > boy * 0.06:     # paragraf satirlari ayni boyda olur
            return False
        sol_hizali = abs(a["rect"].x0 - tohum["rect"].x0) <= boy * 0.8
        ortali = abs((a["rect"].x0 + a["rect"].x1) / 2 - (tohum["rect"].x0 + tohum["rect"].x1) / 2) <= boy
        return sol_hizali or ortali

    aday = sorted([a for a in satirlar_tum if a is tohum or uyumlu(a)], key=lambda a: a["origin"][1])
    i = aday.index(tohum)
    para = [tohum]
    adim = None
    k = i
    while k > 0:                                    # yukari
        a, b = aday[k - 1], aday[k]
        fark = b["origin"][1] - a["origin"][1]
        if fark > boy * 1.45 or fark < boy * 0.8 or _arada_cizgi(veri["cizgiler"], a, b) \
                or (adim and abs(fark - adim) > boy * 0.2):
            break
        adim = adim or fark
        para.insert(0, a)
        k -= 1
    k = i
    while k < len(aday) - 1:                        # asagi
        a, b = aday[k], aday[k + 1]
        fark = b["origin"][1] - a["origin"][1]
        if fark > boy * 1.45 or fark < boy * 0.8 or _arada_cizgi(veri["cizgiler"], a, b) \
                or (adim and abs(fark - adim) > boy * 0.2):
            break
        adim = adim or fark
        para.append(b)
        k += 1

    tum_spans = [x for s_ in para for x in s_["spans"]]
    bbox = fitz.Rect(para[0]["rect"])
    for s_ in para:
        bbox |= s_["rect"]
    ana = max(tum_spans, key=lambda s_: len(s_["text"].strip()))
    fname = ana["font"].lower()
    kalin = bool(ana["flags"] & 16) or any(k in fname for k in ("bold", "black", "heavy", "semibold"))
    italik = bool(ana["flags"] & 2) or "italic" in fname or "oblique" in fname
    serif = any(k in fname for k in ("times", "serif", "roman", "georgia", "garamond", "cambria", "book antiqua", "century"))
    if any(k in fname for k in ("sans", "arial", "helvet", "calibri", "segoe", "tahoma", "verdana", "trebuchet")):
        serif = False
    elif not serif:
        serif = bool(ana["flags"] & 4)
    gorunmez = ana.get("alpha", 255) == 0 or "glyphless" in fname   # OCR'in saydam katmani
    if gorunmez:
        serif = kalin = italik = False
    # sag sinir: paragrafin sagindaki en yakin dikey cizgi (tablo hucresi kenari)
    sag_sinir = None
    for cx, cy0, cy1 in veri.get("dikeyler", []):
        if cx > bbox.x1 - 1 and cy0 <= bbox.y0 + 2 and cy1 >= bbox.y1 - 2:
            sag_sinir = cx if sag_sinir is None else min(sag_sinir, cx)
    if sag_sinir is None:
        sag_sinir = veri.get("sayfa_genislik", bbox.x1 + 200) - 30
    return {
        "sag_sinir": sag_sinir,
        "bbox": tuple(bbox),
        "metin": "\n".join(s_["metin"] for s_ in para),
        "satirlar": [{"bbox": tuple(s_["rect"]), "metin": s_["metin"], "origin": s_["origin"]} for s_ in para],
        "satir_araligi": adim or boy * 1.2,
        "boyut": round(ana["size"], 2),
        "renk": renk_int(ana["color"]),
        "kalin": kalin,
        "italik": italik,
        "serif": serif,
        "origin": para[0]["origin"],
        "font_adi": ana["font"],
        "gorunmez": gorunmez,
        "aci": tohum.get("aci", 0),
    }


# ------------------------------------------------------------------ font eslestirme
_WIN_FONTLAR = [
    # (ad parcasi, normal, kalin, italik, kalin-italik)
    ("segoe ui semibold", "seguisb.ttf", "seguisb.ttf", "seguisbi.ttf", "seguisbi.ttf"),
    ("segoe ui light", "segoeuil.ttf", "segoeuib.ttf", "segoeuil.ttf", "segoeuiz.ttf"),
    ("segoe", "segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"),
    ("calibri", "calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
    ("cambria", "cambria.ttc", "cambriab.ttf", "cambriai.ttf", "cambriaz.ttf"),
    ("candara", "candara.ttf", "candarab.ttf", "candarai.ttf", "candaraz.ttf"),
    ("tahoma", "tahoma.ttf", "tahomabd.ttf", "tahoma.ttf", "tahomabd.ttf"),
    ("verdana", "verdana.ttf", "verdanab.ttf", "verdanai.ttf", "verdanaz.ttf"),
    ("trebuchet", "trebuc.ttf", "trebucbd.ttf", "trebucit.ttf", "trebucbi.ttf"),
    ("georgia", "georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
    ("garamond", "GARA.TTF", "GARABD.TTF", "GARAIT.TTF", "GARABD.TTF"),
    ("century gothic", "GOTHIC.TTF", "GOTHICB.TTF", "GOTHICI.TTF", "GOTHICBI.TTF"),
    ("bookman", "BOOKOS.TTF", "BOOKOSB.TTF", "BOOKOSI.TTF", "BOOKOSBI.TTF"),
    ("book antiqua", "BKANT.TTF", "ANTQUAB.TTF", "ANTQUAI.TTF", "ANTQUABI.TTF"),
    ("courier", "cour.ttf", "courbd.ttf", "couri.ttf", "courbi.ttf"),
    ("consolas", "consola.ttf", "consolab.ttf", "consolai.ttf", "consolaz.ttf"),
    ("times", "times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    ("arial narrow", "ARIALN.TTF", "ARIALNB.TTF", "ARIALNI.TTF", "ARIALNBI.TTF"),
    ("arial", "arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    ("helvetica", "arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
]


def _gomulu_font(page, font_adi, metin):
    """Belgeye gomulu orijinal fontu dondurur (yeni yazinin tum harfleri icinde varsa)."""
    try:
        doc = page.parent
        for f in page.get_fonts(full=True):
            xref, ext, basefont = f[0], f[1], f[3]
            if ext in ("n/a", "") or not basefont:
                continue
            temiz = basefont.split("+", 1)[-1]
            if temiz != font_adi and basefont != font_adi:
                continue
            ad, uz, tur, buf = doc.extract_font(xref)
            if not buf:
                return None
            font = fitz.Font(fontbuffer=buf)
            if all(c == " " or font.has_glyph(ord(c)) for c in metin):
                font._pdfpro_gomulu = True
                return font
            return None
    except Exception:
        return None
    return None


def _sistem_fontu(font_adi, kalin, italik, serif):
    ad = font_adi.lower().replace("-", " ").replace(",", " ")
    ad = ad.split("+", 1)[-1]
    win = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    yerel = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts")
    sira = 1 + (1 if kalin else 0) + (2 if italik else 0)
    for parca, *dosyalar in _WIN_FONTLAR:
        if parca in ad or parca.replace(" ", "") in ad.replace(" ", ""):
            for k in (dosyalar[sira - 1], dosyalar[0]):
                for klasor in (win, yerel):
                    y = os.path.join(klasor, k)
                    if os.path.isfile(y):
                        try:
                            return fitz.Font(fontfile=y)
                        except Exception:
                            pass
            break
    return None


def font_sec(page, satir, metin, kalin=None):
    """Yeni yazi icin en uygun font: 1) gomulu orijinal 2) ayni isimli sistem fontu 3) benzer."""
    k = satir["kalin"] if kalin is None else kalin
    if not satir.get("gorunmez") and (kalin is None or kalin == satir["kalin"]):
        f = _gomulu_font(page, satir["font_adi"], metin)
        if f is not None:
            return f
    f = _sistem_fontu(satir["font_adi"], k, satir["italik"], satir["serif"])
    if f is not None and all(c == " " or f.has_glyph(ord(c)) for c in metin):
        return f
    return font_al(satir["serif"], k, satir["italik"])


def tw_yaz(page, tw, morph=None):
    """TextWriter'i sayfaya yazar. Kirpilmis (CropBox'i MediaBox'tan farkli) sayfalarda
    PyMuPDF'in TextWriter'i yaziyi dikeyde kaydirir; burada duzeltilir."""
    cb, mb = page.cropbox, page.mediabox
    dy = (mb.y1 - mb.y0) - cb.y1 - cb.y0 + 2 * mb.y0
    if abs(dy) > 0.01:
        T = fitz.Matrix(1, 0, 0, 1, 0, dy)
        morph = (morph[0], morph[1] * T) if morph else (fitz.Point(0, 0), T)
    tw.write_text(page, morph=morph)
    bosluk_duzelt(page)


def _tounicode_bosluk(akis):
    """ToUnicode CMap'te bosluk glifi U+00A0'a (bolunmez bosluk) eslenmisse U+0020 yapar."""
    import re
    satirlar = akis.split(b"\n")
    bolum = None
    degisti = False
    for i, s in enumerate(satirlar):
        st = s.strip()
        if st.endswith(b"beginbfchar"):
            bolum = "char"
            continue
        if st.endswith(b"beginbfrange"):
            bolum = "range"
            continue
        if st.startswith(b"endbf"):
            bolum = None
            continue
        if not bolum:
            continue
        t = re.findall(rb"<([0-9A-Fa-f]+)>", s)
        if bolum == "char" and len(t) == 2 and t[1].lower() == b"00a0":
            satirlar[i] = b"<" + t[0] + b"> <0020>"
            degisti = True
        elif bolum == "range" and len(t) == 3 and t[0].lower() == t[1].lower() and t[2].lower() == b"00a0":
            satirlar[i] = b"<" + t[0] + b"> <" + t[1] + b"> <0020>"
            degisti = True
    return b"\n".join(satirlar) if degisti else None


def bosluk_duzelt(page):
    """Windows'taki Arial gibi fontlarda bosluk ve bolunmez bosluk ayni glif oldugundan, yazilan
    metin kopyalaninca / aranınca bosluklar U+00A0 cikiyordu. Sayfanin Type0 fontlarinda duzeltir."""
    doc = page.parent
    try:
        for f in page.get_fonts():
            if f[2] != "Type0":
                continue
            t, v = doc.xref_get_key(f[0], "ToUnicode")
            if t != "xref":
                continue
            x = int(v.split()[0])
            akis = doc.xref_stream(x)
            if not akis or (b"<00A0>" not in akis and b"<00a0>" not in akis):
                continue
            yeni = _tounicode_bosluk(akis)
            if yeni:
                doc.update_stream(x, yeni)
    except Exception:
        pass


def _yaz(page, x, taban_y, metin, boyut, renk, kalin=False, italik=False, serif=False, font=None):
    font = font or font_al(serif, kalin, italik)
    tw = fitz.TextWriter(page.rect, color=renk)
    tw.append(fitz.Point(x, taban_y), metin, font=font, fontsize=boyut)
    tw_yaz(page, tw)
    return font.text_length(metin, boyut)


def arka_plan_rengi(page, rect):
    """Alanin cevresindeki en yaygin rengi bulur (ortme rengi icin). Beyaza cok yakinsa tam beyaz."""
    try:
        r = fitz.Rect(rect)
        dis = fitz.Rect(r.x0 - 2, r.y0 - 2, r.x1 + 2, r.y1 + 2) & page.rect
        pix = page.get_pixmap(clip=dis, matrix=fitz.Matrix(2, 2), alpha=False, annots=False)
        w, h, n = pix.width, pix.height, pix.n
        veri = pix.samples
        sayac = {}
        for yy in range(h):
            xs = range(w) if yy in (0, 1, h - 2, h - 1) else (0, 1, w - 2, w - 1)
            for xx in xs:
                i = (yy * w + xx) * n
                k = tuple(veri[i:i + 3])
                sayac[k] = sayac.get(k, 0) + 1
        en = max(sayac, key=sayac.get)
        if min(en) >= 245:
            return (1.0, 1.0, 1.0)
        return tuple(v / 255 for v in en)
    except Exception:
        return (1, 1, 1)


# ------------------------------------------------------------------ guvenli silme
def _kelimeler_disari(page, alan):
    """Alanin DISINDA kalan kelimeler (konumlariyla)."""
    sonuc = set()
    for w in page.get_text("words"):
        r = fitz.Rect(w[:4])
        merkez = fitz.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
        if not alan.contains(merkez):
            sonuc.add((round(r.x0), round(r.y0), w[4]))
    return sonuc


def _redaksiyon(page, sil):
    page.add_redact_annot(sil, fill=None, cross_out=False)
    try:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                              graphics=getattr(fitz, "PDF_REDACT_LINE_ART_NONE", 0))
    except TypeError:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)


def _bolge_resmi(page, rect):
    pix = page.get_pixmap(clip=fitz.Rect(rect) & page.rect, matrix=fitz.Matrix(1.5, 1.5), alpha=False, annots=False)
    return pix.samples


def _fark(a, b):
    """Iki goruntu arasinda degisen piksel orani."""
    if len(a) != len(b) or not a:
        return 1.0
    adim = 3
    degisen = sum(1 for i in range(0, len(a), adim) if abs(a[i] - b[i]) > 40)
    return degisen / (len(a) / adim)


def guvenli_sil(page, sil):
    """Alandaki yaziyi siler. Once sayfanin kopyasinda dener.
    Donus: 'tamam'    -> yazi silindi, ekranda da kayboldu
           'gorunmez' -> silinen yazi ekranda gorunen yazi degil (resim/cizim ustunde gizli
                         katman); silindi ama ust ayrica ortulmeli
           'bozar'    -> silmek baska yazilari kaydiriyor; hic dokunulmadi, ust ortulmeli"""
    doc = page.parent
    try:
        once = _kelimeler_disari(page, sil)
        deneme = fitz.open()
        deneme.insert_pdf(doc, from_page=page.number, to_page=page.number)
        dp = deneme[0]
        once_resim = _bolge_resmi(dp, sil)
        _redaksiyon(dp, sil)
        sonra = _kelimeler_disari(dp, sil)
        sonra_resim = _bolge_resmi(dp, sil)
        deneme.close()
        if not once <= sonra:
            return "bozar"
    except Exception:
        return "bozar"
    _redaksiyon(page, sil)
    page.wrap_contents()
    if _fark(once_resim, sonra_resim) < 0.004:
        return "gorunmez"
    return "tamam"


_KAYNAK_TURLERI = ("Font", "XObject", "ExtGState", "ColorSpace", "Pattern", "Shading", "Properties")


def _dict_ici(metin):
    metin = metin.strip()
    if metin.startswith("<<") and metin.endswith(">>"):
        return metin[2:-2].strip()
    return ""


def form_ac(page):
    """Sayfa icerigi 'Form XObject' icine gomuluyse (bazi devlet sistemleri / Jasper / Aspose PDF'leri)
    onu sayfanin kendi icerigine acar. Gorunum ayni kalir; boylece yazi silme diger yazilari kaydirmaz.
    Gorunum degisirse geri alir. True = acildi."""
    import re
    doc = page.parent
    yedek_akislar, yedek_kaynak, icerik_xrefler = {}, None, []
    try:
        icerik_xrefler = page.get_contents()
        if not icerik_xrefler:
            return False
        icerik = b"\n".join(doc.xref_stream(x) or b"" for x in icerik_xrefler)
        # kaynaklar ayri bir nesnedeyse (Resources 12 0 R) once sayfaya kopyala: hem birlestirme
        # hem de geri alma dogru calissin (yoksa geri almada sayfa bos kalabiliyordu)
        rt, rv = doc.xref_get_key(page.xref, "Resources")
        if rt == "xref":
            doc.xref_set_key(page.xref, "Resources", doc.xref_object(int(rv.split()[0]), compressed=True))
        elif rt not in ("dict",):
            return False
        tur, xs = doc.xref_get_key(page.xref, "Resources/XObject")
        if tur == "xref":
            doc.xref_set_key(page.xref, "Resources/XObject", doc.xref_object(int(xs.split()[0]), compressed=True))
            tur, xs = doc.xref_get_key(page.xref, "Resources/XObject")
        if tur != "dict":
            return False
        formlar = {}
        for ad, xref in re.findall(r"/([^\s/<>\[\]()]+)\s+(\d+)\s+0\s+R", xs):
            if doc.xref_get_key(int(xref), "Subtype")[1] == "/Form":
                formlar[ad] = int(xref)
        if not formlar:
            return False
        once = page.get_pixmap(matrix=fitz.Matrix(0.6, 0.6), alpha=False, annots=False).samples
        yedek_akislar = {x: doc.xref_stream(x) for x in icerik_xrefler}
        yedek_kaynak = doc.xref_get_key(page.xref, "Resources")
        yeni = icerik
        for ad, xref in formlar.items():
            desen = ("/" + ad + " Do").encode("latin-1")
            if desen not in yeni:
                continue
            akis = doc.xref_stream(xref) or b""
            onek = b"q\n"
            mt, mv = doc.xref_get_key(xref, "Matrix")
            if mt == "array":
                onek += mv.strip("[]").encode() + b" cm\n"
            bt, bv = doc.xref_get_key(xref, "BBox")
            if bt == "array":
                x0, y0, x1, y1 = [float(v) for v in bv.strip("[]").split()]
                onek += f"{x0} {y0} {x1 - x0} {y1 - y0} re W n\n".encode()
            yeni = yeni.replace(desen, onek + akis + b"\nQ\n")
            # form kaynaklarini sayfaya tasi
            for kt in _KAYNAK_TURLERI:
                ft, fv = doc.xref_get_key(xref, "Resources/" + kt)
                if ft not in ("dict", "xref"):
                    continue
                if ft == "xref":
                    fv = doc.xref_object(int(fv.split()[0]))
                pt, pv = doc.xref_get_key(page.xref, "Resources/" + kt)
                if pt == "xref":
                    pv = doc.xref_object(int(pv.split()[0]))
                birlesik = "<<" + (_dict_ici(pv) if pt in ("dict", "xref") else "") + " " + _dict_ici(fv) + ">>"
                doc.xref_set_key(page.xref, "Resources/" + kt, birlesik)
        if yeni == icerik:
            return False
        doc.update_stream(icerik_xrefler[0], yeni)
        for x in icerik_xrefler[1:]:
            doc.update_stream(x, b"")
        sonra = doc[page.number].get_pixmap(matrix=fitz.Matrix(0.6, 0.6), alpha=False, annots=False).samples
        if _fark(once, sonra) > 0.002:
            # gorunum bozuldu: geri al
            _form_geri_al(doc, page.xref, icerik_xrefler, yedek_akislar, yedek_kaynak)
            return False
        return True
    except Exception:
        try:
            _form_geri_al(doc, page.xref, icerik_xrefler, yedek_akislar, yedek_kaynak)
        except Exception:
            pass
        return False


def _form_geri_al(doc, page_xref, xrefler, akislar, kaynak):
    for x in xrefler:
        doc.update_stream(x, akislar.get(x) or b"")
    if kaynak and kaynak[0] == "dict":
        doc.xref_set_key(page_xref, "Resources", kaynak[1])


def _tirnak_ac(b):
    """Icerik akisindaki  (yazi) '   ve   aw ac (yazi) "   operatorlerini esdegeri olan
    T* (yazi) Tj  bicimine cevirir. (MuPDF'in silme filtresi bu operatorlerde yazilari kaydiriyor.)"""
    import re
    out = bytearray()
    i, n = 0, len(b)
    bosluk = b" \t\r\n\x00\x0c"
    while i < n:
        c = b[i:i + 1]
        tok = None
        if c == b"(":
            j, d = i + 1, 1
            while j < n and d:
                ch = b[j:j + 1]
                if ch == b"\\":
                    j += 2
                    continue
                if ch == b"(":
                    d += 1
                elif ch == b")":
                    d -= 1
                j += 1
            tok = b[i:j]
        elif c == b"<" and b[i + 1:i + 2] != b"<":
            j = b.find(b">", i)
            j = n if j < 0 else j + 1
            tok = b[i:j]
        elif c == b"%":
            j = b.find(b"\n", i)
            j = n if j < 0 else j
            out += b[i:j]
            i = j
            continue
        if tok is None:
            out += c
            i += 1
            continue
        k = j
        while k < n and b[k:k + 1] in bosluk:
            k += 1
        op = b[k:k + 1]
        sonraki = b[k + 1:k + 2]
        if op in (b"'", b'"') and (sonraki == b"" or sonraki in bosluk + b"/[(<%"):
            if op == b"'":
                out += b"T* " + tok + b" Tj"
                i = k + 1
                continue
            m = re.search(rb"([-+.\d]+)\s+([-+.\d]+)\s*$", bytes(out))
            if m:
                del out[m.start():]
                out += m.group(1) + b" Tw " + m.group(2) + b" Tc T* " + tok + b" Tj"
                i = k + 1
                continue
        out += tok
        i = j
    return bytes(out)


def icerik_normallestir(page):
    """Silmenin guvenli calismasi icin sayfa icerigini sadelestirir (gorunum degismez):
    1) Form XObject icine gomulu icerigi sayfaya acar  2) ' ve " yazi operatorlerini cevirir.
    Gorunum degisirse geri alir. True = bir sey degisti."""
    doc = page.parent
    pno = page.number
    degisti = form_ac(page)
    page = doc[pno]
    try:
        xrefler = page.get_contents()
        once = page.get_pixmap(matrix=fitz.Matrix(0.6, 0.6), alpha=False, annots=False).samples
        yedek = {x: doc.xref_stream(x) for x in xrefler}
        yeni_var = False
        for x in xrefler:
            eski = yedek[x] or b""
            yeni = _tirnak_ac(eski)
            if yeni != eski:
                doc.update_stream(x, yeni)
                yeni_var = True
        if yeni_var:
            sonra = doc[pno].get_pixmap(matrix=fitz.Matrix(0.6, 0.6), alpha=False, annots=False).samples
            if _fark(once, sonra) > 0.002:
                for x, v in yedek.items():
                    doc.update_stream(x, v or b"")
            else:
                degisti = True
    except Exception:
        pass
    return degisti


def _ortu_alani(s_, boyut):
    """Bir satirin ekranda kapladigi alan: Ğ, İ, Ü noktalari ve g/y/ş kuyruklari dahil."""
    r = fitz.Rect(s_["bbox"])
    ox, oy = s_["origin"]
    return fitz.Rect(min(r.x0, ox) - boyut * 0.08, min(r.y0, oy - boyut * 1.02),
                     r.x1 + boyut * 0.18, max(r.y1, oy + boyut * 0.27))


def _ortu(page, alanlar):
    for a in alanlar:
        page.draw_rect(a, color=None, fill=arka_plan_rengi(page, a), overlay=True)


def _sar(metin, font, boyut, olcek, sinir):
    """Satiri genislik sinirina gore kelime kelime boler."""
    if sinir is None or font.text_length(metin, boyut) * olcek <= sinir:
        return [metin]
    satirlar, mevcut = [], ""
    for k in metin.split(" "):
        dene = (mevcut + " " + k).strip()
        if mevcut and font.text_length(dene, boyut) * olcek > sinir:
            satirlar.append(mevcut)
            mevcut = k
        else:
            mevcut = dene
    if mevcut:
        satirlar.append(mevcut)
    return satirlar


def satir_degistir(page, satir, yeni_metin, boyut=None, renk=None, kalin=None, font=None, hiza="sol"):
    """Eski yaziyi kaldirir ve ayni yere, ayni yazi tipiyle yenisini yazar.
    - Normal PDF: eski yazi silinir (arka plan, cizgi, resim korunur). Silme baska yazilari
      bozacaksa (karmasik PDF'ler) eski yazinin ustu arka plan rengiyle ortulur.
    - OCR'li taranmis sayfa: eski yazi resmin icinde oldugu icin ustu ortulur.
    - Paragrafsa (hucrede alt alta satirlar) yeni yazi ayni genislikte satirlara bolunur."""
    sayfa_hazirla(page)
    doc, pno = page.parent, page.number
    eski = satir.get("satirlar") or [{"bbox": satir["bbox"], "metin": satir["metin"], "origin": satir["origin"]}]
    b = boyut or satir["boyut"]
    rk = renk or satir["renk"]

    # 1) eskiyi kaldir
    if satir.get("gorunmez"):
        # OCR'li tarama: yazi resmin icinde -> resimden sil (zemin dokusu korunur) ve yeniden yaz
        from . import resim_yazi as R
        r0 = fitz.Rect(satir["bbox"])
        bilgi = R.olc(page, r0, satir["metin"])
        if bilgi is not None:
            R.degistir(page, bilgi, yeni_metin, font=font, boyut=boyut, renk=renk, hiza=hiza)
            return
        for s_ in eski:
            alan = _ortu_alani(s_, b)
            guvenli_sil(page, fitz.Rect(s_["bbox"]))
            _ortu(page, [alan])
    else:
        ust = fitz.Rect(eski[0]["bbox"])
        alt = fitz.Rect(eski[-1]["bbox"])
        tum = fitz.Rect(satir["bbox"])
        if satir.get("aci", 0) in (90, 270):      # yan yazi: kalinlik yatay eksende
            sil = fitz.Rect(tum.x0 + tum.width * 0.15, tum.y0 - 0.5, tum.x1 - tum.width * 0.15, tum.y1 + 0.5)
        else:
            sil = fitz.Rect(tum.x0 - 0.5, ust.y0 + ust.height * 0.15, tum.x1 + 0.5, alt.y1 - alt.height * 0.15)
        sonuc = guvenli_sil(page, sil)
        if sonuc == "bozar" and icerik_normallestir(page):
            page = doc[pno]
            sonuc = guvenli_sil(page, sil)
        if sonuc != "tamam":
            # ekrandaki eski yazi hala gorunuyor: ustunu arka plan rengiyle tamamen ort
            _ortu(page, [_ortu_alani(s_, b) for s_ in eski])

    if not yeni_metin.strip():
        return

    # 2) font ve genislik olcegi (yedek font daha genis/darsa orijinal genislige uydur)
    if font is not None:
        olcek = 1.0
        if satir.get("gorunmez"):
            rk = renk or (0, 0, 0)
    elif satir.get("gorunmez"):
        font = font_al(False, bool(kalin), False)
        olcek = 1.0
        rk = renk or (0, 0, 0)
    else:
        font = font_sec(page, satir, yeni_metin.replace("\n", " "), kalin)
        olcek = 1.0
        if not getattr(font, "_pdfpro_gomulu", False):
            orj = sum(fitz.Rect(s_["bbox"]).width for s_ in eski)
            yed = sum(font.text_length(s_["metin"], b) for s_ in eski)
            if orj > 5 and yed > 5:
                olcek = max(0.72, min(1.08, orj / yed))

    # 3) satirlara bol ve yaz
    sinir = None
    if satir.get("sag_sinir") and len(eski) > 1:
        # hucre / paragraf genisligi: sagdaki cizgiye kadar (biraz bosluk birakarak)
        sinir = max(satir["sag_sinir"] - eski[0]["origin"][0] - 3,
                    max(fitz.Rect(s_["bbox"]).width for s_ in eski))
    yeni_satirlar = []
    for parca in yeni_metin.split("\n"):
        yeni_satirlar += _sar(parca, font, b, olcek, sinir)
    ox, oy = eski[0]["origin"]
    if satir.get("gorunmez"):
        r0 = fitz.Rect(eski[0]["bbox"])
        ox, oy = r0.x0, r0.y1 - b * 0.22
    aralik = satir.get("satir_araligi") or b * 1.2
    aci = satir.get("aci", 0)
    if aci:
        # yan / ters yazi: orijinal baslangic noktasindan ayni yonde yaz
        ox, oy = eski[0]["origin"]
        for i, metin in enumerate(yeni_satirlar[:1] if len(yeni_satirlar) == 1 else yeni_satirlar):
            tw = fitz.TextWriter(page.rect, color=rk)
            tw.append(fitz.Point(ox, oy), metin, font=font, fontsize=b)
            tw_yaz(page, tw, morph=(fitz.Point(ox, oy), fitz.Matrix(olcek, 0, 0, 1, 0, 0) * fitz.Matrix(aci)))
        return
    for i, metin in enumerate(yeni_satirlar):
        x = eski[i]["origin"][0] if (i < len(eski) and not satir.get("gorunmez")) else ox
        if hiza in ("orta", "sag"):
            ref = fitz.Rect(eski[min(i, len(eski) - 1)]["bbox"])
            gen = font.text_length(metin, b) * olcek
            x = (ref.x0 + ref.x1 - gen) / 2 if hiza == "orta" else ref.x1 - gen
        y = oy + i * aralik
        tw = fitz.TextWriter(page.rect, color=rk)
        tw.append(fitz.Point(x, y), metin, font=font, fontsize=b)
        if abs(olcek - 1) > 0.01:
            tw_yaz(page, tw, morph=(fitz.Point(x, y), fitz.Matrix(olcek, 0, 0, 1, 0, 0)))
        else:
            tw_yaz(page, tw)


def yazi_ekle(page, x, taban_y, metin, boyut=11, renk=(0, 0, 0), kalin=False, serif=False):
    if not metin.strip():
        return
    sayfa_hazirla(page)
    satirlar = metin.split("\n")
    for i, s in enumerate(satirlar):
        _yaz(page, x, taban_y + i * boyut * 1.25, s, boyut, renk, kalin, False, serif)


def beyaz_kutu(page, rect, renk=(1, 1, 1)):
    sayfa_hazirla(page)
    page.draw_rect(fitz.Rect(rect), color=None, fill=renk, overlay=True)


def resim_yerlestir(page, rect, png_bayt):
    sayfa_hazirla(page)
    page.insert_image(fitz.Rect(rect), stream=png_bayt, keep_proportion=True, overlay=True)


# ------------------------------------------------------------------ tasinabilir nesneler (imza / kase)
def _benzersiz_png(png):
    """Her yerlestirme ayri resim nesnesi olsun diye PNG'ye benzersiz bir etiket ekler
    (ayni imza iki kez konsa bile her biri ayri tasinabilsin)."""
    import uuid
    import zlib
    if not png.startswith(b"\x89PNG"):
        return png
    veri = b"pdfpro\x00" + uuid.uuid4().hex.encode()
    parca = len(veri).to_bytes(4, "big") + b"tEXt" + veri + zlib.crc32(b"tEXt" + veri).to_bytes(4, "big")
    i = png.rfind(b"IEND") - 4
    return png[:i] + parca + png[i:]


def nesne_ekle(page, rect, png):
    """Resmi sayfaya koyar; resmin xref numarasini dondurur (tasimak / boyutlamak icin kimlik)."""
    sayfa_hazirla(page)
    return page.insert_image(fitz.Rect(rect), stream=_benzersiz_png(png), keep_proportion=False, overlay=True)


def _xobje_adlari(page, xref):
    import re
    doc = page.parent
    tur, deger = doc.xref_get_key(page.xref, "Resources/XObject")
    if tur == "xref":
        deger = doc.xref_object(int(deger.split()[0]))
    elif tur != "dict":
        return []
    return [ad for ad, x in re.findall(r"/([^\s/<>\[\]()]+)\s+(\d+)\s+0\s+R", deger) if int(x) == xref]


def nesne_cizili_mi(page, xref):
    """Bu resim sayfa iceriginde gercekten cizdiriliyor mu?"""
    import re
    doc = page.parent
    for ad in _xobje_adlari(page, xref):
        desen = re.compile(rb"/" + re.escape(ad.encode("latin-1")) + rb"\s+Do\b")
        for cx in page.get_contents():
            if desen.search(doc.xref_stream(cx) or b""):
                return True
    return False


def nesne_konumu(page, xref):
    """Resmin sayfadaki yeri (icerikteki 'a 0 0 d e f cm /Ad Do' komutundan). Yoksa None."""
    import re
    doc = page.parent
    for ad in _xobje_adlari(page, xref):
        desen = re.compile(rb"q\s+((?:[-+.\deE]+\s+){6})cm\s*/" + re.escape(ad.encode("latin-1")) + rb"\s+Do\s+Q")
        for cx in page.get_contents():
            m = desen.search(doc.xref_stream(cx) or b"")
            if m:
                a, b_, c, d, e, f = [float(v) for v in m.group(1).split()]
                tm = page.transformation_matrix
                p0 = fitz.Point(e, f) * tm
                p1 = fitz.Point(e + a + c, f + b_ + d) * tm
                return fitz.Rect(p0, p1).normalize()
    return None


def nesne_kaldir(page, xref):
    """nesne_ekle ile konmus resmi sayfadan kaldirir. True = bulundu."""
    import re
    doc = page.parent
    bulundu = False
    for ad in _xobje_adlari(page, xref):
        desen = re.compile(rb"q\s+(?:[-+.\deE]+\s+){6}cm\s*/" + re.escape(ad.encode("latin-1")) + rb"\s+Do\s+Q")
        for cx in page.get_contents():
            st = doc.xref_stream(cx) or b""
            yeni, n = desen.subn(b"", st)
            if n:
                doc.update_stream(cx, yeni)
                bulundu = True
    return bulundu


def nesne_tasi(page, xref, yeni_rect, png):
    """Resmi yeni yere / boyuta alir. Yeni xref'i dondurur."""
    nesne_kaldir(page, xref)
    return nesne_ekle(page, yeni_rect, png)


def bos_sayfa_ekle(doc, sonra=-1, boyut_ornek=None):
    """sonra: bu sayfadan sonra ekler (-1 = sona). Boyut ornek sayfadan alinir."""
    if boyut_ornek is not None and 0 <= boyut_ornek < doc.page_count:
        r = doc[boyut_ornek].rect
        w, h = r.width, r.height
    else:
        w, h = fitz.paper_size("a4")
    konum = doc.page_count if sonra < 0 else sonra + 1
    doc.new_page(pno=konum, width=w, height=h)
    return konum


def dosyadan_ekle(doc, yol, sonra=-1):
    """Baska PDF/resmin tum sayfalarini araya ekler. Eklenen sayfa sayisini dondurur."""
    from .cekirdek import pdf_ac
    kaynak = pdf_ac(yol)
    n = kaynak.page_count
    konum = doc.page_count if sonra < 0 else sonra + 1
    doc.insert_pdf(kaynak, start_at=konum)
    kaynak.close()
    return n


def sayfa_tasi(doc, kaynaklar, hedef):
    """kaynaklar (0 tabanli liste) sayfalarini hedef konumuna (o sayfanin onune) tasir."""
    n = doc.page_count
    kaynaklar = sorted(set(kaynaklar))
    kalan = [i for i in range(n) if i not in kaynaklar]
    hedef_sira = sum(1 for i in kalan if i < hedef)
    yeni = kalan[:hedef_sira] + kaynaklar + kalan[hedef_sira:]
    if yeni == list(range(n)):
        return None
    doc.select(yeni)
    return [yeni.index(k) for k in kaynaklar]


def kontrol(kosul, mesaj):
    if not kosul:
        raise PdfProHata(mesaj)
