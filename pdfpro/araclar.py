# -*- coding: utf-8 -*-
"""
PDF PRO - Ek araclar
Ara / Bul-Degistir, Vurgula, Karart (kalici sil), Sekiller, Damga, Kirp,
A4'e sigdir, Resimleri cikar, Form alanlari
"""
import datetime
import os

from .cekirdek import fitz, PdfProHata, benzersiz_yol
from . import duzenle as Z


# ------------------------------------------------------------------ ara
def ara(doc, aranan, buyuk_kucuk=False):
    """[(sayfa, Rect), ...] dondurur. Turkce i/İ/ı/I farkini buyuk_kucuk=False iken yok sayar."""
    if not aranan:
        return []
    sonuc = []
    for i, p in enumerate(doc):
        try:
            if buyuk_kucuk:
                bulunan = p.search_for(aranan)
                # search_for buyuk/kucuk duyarsizdir; duyarli ise metinle dogrula
                temiz = []
                for r in bulunan:
                    t = p.get_textbox(r + (-0.5, -0.5, 0.5, 0.5))
                    if aranan in t:
                        temiz.append(r)
                bulunan = temiz
            else:
                bulunan = p.search_for(aranan)
                if not bulunan:
                    for alt in _tr_varyant(aranan):
                        bulunan = p.search_for(alt)
                        if bulunan:
                            break
        except Exception:
            bulunan = []
        sonuc += [(i, fitz.Rect(r)) for r in bulunan]
    return sonuc


def _tr_varyant(s):
    """Turkce buyuk/kucuk donusumleri (i-İ, ı-I) icin alternatifler."""
    tr_ust = s.replace("i", "İ").replace("ı", "I").upper()
    tr_alt = s.replace("İ", "i").replace("I", "ı").lower()
    return [v for v in (tr_ust, tr_alt) if v != s]


def bul_degistir(doc, aranan, yeni, buyuk_kucuk=True, ilerleme=None):
    """Belgedeki tum 'aranan' yazilarini 'yeni' ile degistirir (yazi tipi ve yeri korunarak).
    Degisen yer sayisini dondurur."""
    if not aranan:
        raise PdfProHata("Aranacak yazıyı girin.")
    toplam = 0
    for i in range(doc.page_count):
        if ilerleme:
            ilerleme(i, doc.page_count, f"Sayfa {i + 1}")
        page = doc[i]
        bulunan = page.search_for(aranan)
        if not bulunan:
            continue
        islenen = []
        for r in bulunan:
            page = doc[i]
            veri = Z.metin_verisi(page)
            s = Z.satir_bul(page, (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2, veri=veri)
            if not s:
                continue
            anahtar = tuple(round(v, 1) for v in s["bbox"])
            if anahtar in islenen:
                continue
            if buyuk_kucuk:
                if aranan not in s["metin"]:
                    continue
                yeni_metin = s["metin"].replace(aranan, yeni)
            else:
                import re
                yeni_metin = re.sub(re.escape(aranan), yeni.replace("\\", "\\\\"), s["metin"], flags=re.IGNORECASE)
            if yeni_metin == s["metin"]:
                continue
            adet = s["metin"].count(aranan) or 1
            Z.satir_degistir(page, s, yeni_metin)
            islenen.append(anahtar)
            toplam += adet
    return toplam


# ------------------------------------------------------------------ vurgula / karart / sekil
def vurgula(page, rect, renk=(1, 0.92, 0.2)):
    """Alandaki kelimeleri fosforlu kalemle isaretler; kelime yoksa yari saydam kutu."""
    rect = fitz.Rect(rect)
    kelimeler = [fitz.Rect(w[:4]) for w in page.get_text("words") if fitz.Rect(w[:4]).intersects(rect)]
    if kelimeler:
        a = page.add_highlight_annot([k.quad for k in kelimeler])
    else:
        a = page.add_rect_annot(rect)
        a.set_colors(stroke=None, fill=renk)
        a.set_border(width=0)
        a.set_opacity(0.35)
    a.set_colors(stroke=renk)
    a.update()
    return a


def karart(page, rect, renk=(0, 0, 0)):
    """KALICI siler: alandaki yazi, resim pikselleri ve cizimler silinir, yerine siyah kutu.
    (Kimlik no, adres gibi kisisel bilgileri gizlemek icin - KVKK)"""
    Z.sayfa_hazirla(page)
    Z.icerik_normallestir(page)
    page = page.parent[page.number]
    page.add_redact_annot(fitz.Rect(rect), fill=renk, cross_out=False)
    page.apply_redactions(images=getattr(fitz, "PDF_REDACT_IMAGE_PIXELS", 2),
                          graphics=getattr(fitz, "PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED", 1))


def sekil(page, tur, p0, p1, renk=(0.8, 0.1, 0.1), kalinlik=1.5, dolgu=None):
    """tur: 'dikdortgen' | 'cizgi' | 'ok' | 'elips'"""
    Z.sayfa_hazirla(page)
    a, b = fitz.Point(p0), fitz.Point(p1)
    sh = page.new_shape()
    if tur == "dikdortgen":
        sh.draw_rect(fitz.Rect(a, b).normalize())
    elif tur == "elips":
        sh.draw_oval(fitz.Rect(a, b).normalize())
    else:
        sh.draw_line(a, b)
        if tur == "ok":
            import math
            aci = math.atan2(b.y - a.y, b.x - a.x)
            boy = max(6, kalinlik * 5)
            for d in (0.45, -0.45):
                sh.draw_line(b, fitz.Point(b.x - boy * math.cos(aci + d), b.y - boy * math.sin(aci + d)))
    sh.finish(color=renk, fill=dolgu, width=kalinlik, closePath=False)
    sh.commit()


# ------------------------------------------------------------------ damga
HAZIR_DAMGALAR = ["ASLI GİBİDİR", "ONAYLANDI", "ALINDI", "İPTAL", "ÖDENDİ", "TASLAK", "KOPYADIR",
                  "GÖRÜLDÜ", "REDDEDİLDİ"]


def damga(page, merkez, metin, renk=(0.75, 0.08, 0.08), boyut=16, tarih=True, aci=0):
    """Kenarlikli kase damgasi (vektor, net) basar."""
    Z.sayfa_hazirla(page)
    f = Z.font_al(False, True, False)
    satirlar = [metin]
    if tarih:
        satirlar.append(datetime.date.today().strftime("%d.%m.%Y"))
    boylar = [boyut] + [boyut * 0.6] * (len(satirlar) - 1)
    gen = max(f.text_length(s, b) for s, b in zip(satirlar, boylar)) + boyut * 1.2
    yuk = sum(b * 1.25 for b in boylar) + boyut * 0.5
    cx, cy = merkez
    r = fitz.Rect(cx - gen / 2, cy - yuk / 2, cx + gen / 2, cy + yuk / 2)
    m = fitz.Matrix(aci) if aci else None
    sh = page.new_shape()
    sh.draw_rect(r, radius=0.12)
    sh.finish(color=renk, width=boyut * 0.11, morph=(fitz.Point(cx, cy), m) if m else None)
    ic = r + (boyut * 0.18, boyut * 0.18, -boyut * 0.18, -boyut * 0.18)
    sh.draw_rect(ic, radius=0.1)
    sh.finish(color=renk, width=boyut * 0.04, morph=(fitz.Point(cx, cy), m) if m else None)
    sh.commit()
    tw = fitz.TextWriter(page.rect, color=renk)
    y = r.y0 + boyut * 0.25
    for s, b in zip(satirlar, boylar):
        y += b * 1.05
        tw.append(fitz.Point(cx - f.text_length(s, b) / 2, y), s, font=f, fontsize=b)
        y += b * 0.2
    Z.tw_yaz(page, tw, morph=(fitz.Point(cx, cy), m) if m else None)
    return r


# ------------------------------------------------------------------ kirp / boyut
def kirp(page, rect):
    """Sayfanin gorunen alanini rect ile sinirlar (rect: sayfanin su anki koordinatlarinda)."""
    Z.sayfa_hazirla(page)
    cb = page.cropbox
    r = fitz.Rect(rect) & page.rect
    if r.width < 10 or r.height < 10:
        raise PdfProHata("Kırpma alanı çok küçük.")
    page.set_cropbox(fitz.Rect(r.x0 + cb.x0, r.y0 + cb.y0, r.x1 + cb.x0, r.y1 + cb.y0))


def a4e_sigdir(doc, sayfalar, kenar_mm=0):
    """Secili sayfalari A4'e (yatay sayfalar yatay A4'e) olcekleyerek tasir."""
    w, h = fitz.paper_size("a4")
    k = kenar_mm * 72 / 25.4
    kaynak = fitz.open()
    kaynak.insert_pdf(doc)
    for i in sorted(sayfalar, reverse=True):
        r = kaynak[i].rect
        ww, hh = (h, w) if r.width > r.height else (w, h)
        doc.delete_page(i)
        yeni = doc.new_page(pno=i, width=ww, height=hh)
        yeni.show_pdf_page(fitz.Rect(k, k, ww - k, hh - k), kaynak, i, keep_proportion=True)
    kaynak.close()


# ------------------------------------------------------------------ resimleri cikar
def resimleri_cikar(doc, klasor, en_kucuk=40, ilerleme=None):
    os.makedirs(klasor, exist_ok=True)
    goruldu = set()
    ciktilar = []
    for i, p in enumerate(doc):
        if ilerleme:
            ilerleme(i, doc.page_count, f"Sayfa {i + 1}")
        for im in p.get_images(full=True):
            xref = im[0]
            if xref in goruldu:
                continue
            goruldu.add(xref)
            try:
                v = doc.extract_image(xref)
            except Exception:
                continue
            if not v or v.get("width", 0) < en_kucuk or v.get("height", 0) < en_kucuk:
                continue
            uz = v.get("ext", "png")
            if uz not in ("png", "jpg", "jpeg", "jp2", "tiff", "bmp"):
                try:
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n - pix.alpha >= 4:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    yol = benzersiz_yol(os.path.join(klasor, f"sayfa{i + 1}_resim{len(ciktilar) + 1}.png"))
                    pix.save(yol)
                    ciktilar.append(yol)
                    continue
                except Exception:
                    continue
            yol = benzersiz_yol(os.path.join(klasor, f"sayfa{i + 1}_resim{len(ciktilar) + 1}.{uz}"))
            with open(yol, "wb") as f:
                f.write(v["image"])
            ciktilar.append(yol)
    return ciktilar


# ------------------------------------------------------------------ form alanlari
TUR_ADLARI = {
    getattr(fitz, "PDF_WIDGET_TYPE_TEXT", 7): "Yazı",
    getattr(fitz, "PDF_WIDGET_TYPE_CHECKBOX", 2): "Onay kutusu",
    getattr(fitz, "PDF_WIDGET_TYPE_RADIOBUTTON", 5): "Seçenek",
    getattr(fitz, "PDF_WIDGET_TYPE_COMBOBOX", 3): "Açılır liste",
    getattr(fitz, "PDF_WIDGET_TYPE_LISTBOX", 4): "Liste",
}


def form_alanlari(doc):
    """[{sayfa, ad, tur, deger, secenekler, rect}] dondurur."""
    alanlar = []
    for i, p in enumerate(doc):
        for w in p.widgets() or []:
            if w.field_type in (getattr(fitz, "PDF_WIDGET_TYPE_BUTTON", 1),
                                getattr(fitz, "PDF_WIDGET_TYPE_SIGNATURE", 6)):
                continue
            alanlar.append({"sayfa": i, "ad": w.field_name or f"alan{len(alanlar) + 1}",
                            "tur": w.field_type, "tur_adi": TUR_ADLARI.get(w.field_type, "Alan"),
                            "deger": w.field_value, "secenekler": list(w.choice_values or []),
                            "rect": tuple(w.rect), "xref": w.xref,
                            "acik_deger": w.on_state() if hasattr(w, "on_state") else True})
    return alanlar


def form_doldur(doc, degerler):
    """degerler: {xref: deger}. Onay kutusu icin True/False."""
    adet = 0
    for p in doc:
        for w in p.widgets() or []:
            if w.xref not in degerler:
                continue
            d = degerler[w.xref]
            if w.field_type in (getattr(fitz, "PDF_WIDGET_TYPE_CHECKBOX", 2), getattr(fitz, "PDF_WIDGET_TYPE_RADIOBUTTON", 5)):
                w.field_value = w.on_state() if d else "Off"
            else:
                w.field_value = d
            w.update()
            adet += 1
    return adet


# ------------------------------------------------------------------ PDF KARSILASTIR
def _kelimeler(doc):
    sonuc = []
    for i, p in enumerate(doc):
        for w in p.get_text("words", sort=True):
            t = w[4].strip()
            if t:
                sonuc.append((i, fitz.Rect(w[:4]), t))
    return sonuc


def karsilastir(yol_a, yol_b, cikti, ilerleme=None):
    """Iki PDF'i kelime kelime karsilastirir; yan yana sayfalardan olusan rapor PDF'i uretir.
    Solda ESKI (silinen/degisen kirmizi), sagda YENI (eklenen/degisen yesil).
    Dondurur: (cikti, silinen_kelime, eklenen_kelime, farkli_sayfa_sayisi)"""
    import difflib
    a, b = fitz.open(yol_a), fitz.open(yol_b)
    if a.needs_pass or b.needs_pass:
        raise PdfProHata("Şifreli PDF karşılaştırılamaz; önce şifreyi kaldırın.")
    ka, kb = _kelimeler(a), _kelimeler(b)
    if not ka and not kb:
        raise PdfProHata("İki belgede de okunabilir yazı yok. Önce OCR ile 'Aranabilir Yap' uygulayın.")
    sa = [t.lower() for _, _, t in ka]
    sb = [t.lower() for _, _, t in kb]
    sm = difflib.SequenceMatcher(None, sa, sb, autojunk=False)
    isaret_a, isaret_b = {}, {}
    silinen = eklenen = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        for k in range(i1, i2):
            isaret_a.setdefault(ka[k][0], []).append(ka[k][1])
        for k in range(j1, j2):
            isaret_b.setdefault(kb[k][0], []).append(kb[k][1])
        silinen += i2 - i1
        eklenen += j2 - j1
    cik = fitz.open()
    n = max(a.page_count, b.page_count)
    f = Z.font_al(False, True, False)
    farkli = 0
    for i in range(n):
        if ilerleme:
            ilerleme(i, n, f"Sayfa {i + 1}/{n}")
        ra = a[i].rect if i < a.page_count else None
        rb = b[i].rect if i < b.page_count else None
        g_a = ra.width if ra else rb.width
        g_b = rb.width if rb else ra.width
        yuk = max(r.height for r in (ra, rb) if r) + 28
        bosluk = 16
        p = cik.new_page(width=g_a + g_b + bosluk, height=yuk)
        p.draw_rect(p.rect, color=None, fill=(0.93, 0.94, 0.96))
        sol = fitz.Rect(0, 28, g_a, 28 + (ra.height if ra else rb.height))
        sag = fitz.Rect(g_a + bosluk, 28, g_a + bosluk + g_b, 28 + (rb.height if rb else ra.height))
        if ra:
            p.show_pdf_page(sol, a, i)
        if rb:
            p.show_pdf_page(sag, b, i)
        if (i in isaret_a) or (i in isaret_b) or not ra or not rb:
            farkli += 1
        for rects, kutu, kaynak, renk in ((isaret_a.get(i, []), sol, ra, (0.9, 0.15, 0.15)),
                                          (isaret_b.get(i, []), sag, rb, (0.1, 0.65, 0.25))):
            if not kaynak:
                continue
            sx, sy = kutu.width / kaynak.width, kutu.height / kaynak.height
            sh = p.new_shape()
            for r in rects:
                sh.draw_rect(fitz.Rect(kutu.x0 + r.x0 * sx - 1, kutu.y0 + r.y0 * sy - 1,
                                       kutu.x0 + r.x1 * sx + 1, kutu.y0 + r.y1 * sy + 1))
            sh.finish(color=renk, fill=renk, fill_opacity=0.25, stroke_opacity=0.9, width=0.6)
            sh.commit()
        tw = fitz.TextWriter(p.rect)
        da = os.path.basename(yol_a)[:60] if ra else "(sayfa yok)"
        db = os.path.basename(yol_b)[:60] if rb else "(sayfa yok)"
        tw.append((8, 18), f"ESKİ · {da} · s.{i + 1}", font=f, fontsize=10)
        tw.append((g_a + bosluk + 8, 18), f"YENİ · {db} · s.{i + 1}", font=f, fontsize=10)
        tw.write_text(p, color=(0.12, 0.2, 0.35))
        Z.bosluk_duzelt(p)
    a.close()
    b.close()
    cik.save(cikti, garbage=3, deflate=True)
    cik.close()
    return cikti, silinen, eklenen, farkli


# ------------------------------------------------------------------ QR / BARKOD
def qr_oku(doc, sayfalar=None, dpi=250, ilerleme=None):
    """Sayfalardaki QR kod ve barkodlari okur. [{'sayfa', 'tur', 'metin', 'rect'}]
    zxing-cpp varsa (QR, DataMatrix, PDF417, Code128, Code39, EAN...) onu, yoksa OpenCV'yi kullanir."""
    try:
        import numpy as np
    except Exception:
        from .cekirdek import BilesenEksik
        raise BilesenEksik("QR / barkod okuma bileşeni", "numpy")
    try:
        import zxingcpp
    except Exception:
        zxingcpp = None
    qr = bar = None
    if zxingcpp is None:
        try:
            import cv2
        except Exception:
            from .cekirdek import BilesenEksik
            raise BilesenEksik("QR / barkod okuma bileşeni", "zxing-cpp")
        qr = cv2.QRCodeDetector()
        try:
            bar = cv2.barcode.BarcodeDetector()
        except Exception:
            bar = None
    sayfalar = list(sayfalar) if sayfalar is not None else list(range(doc.page_count))
    sonuc, gorulen = [], set()
    olcek = 72.0 / dpi
    for n, i in enumerate(sayfalar):
        if ilerleme:
            ilerleme(n, len(sayfalar), f"Sayfa {i + 1}")
        pix = doc[i].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width).copy()
        bulunan = []
        if zxingcpp is not None:
            try:
                for r in zxingcpp.read_barcodes(img):
                    p = r.position
                    pts = [(p.top_left.x, p.top_left.y), (p.top_right.x, p.top_right.y),
                           (p.bottom_right.x, p.bottom_right.y), (p.bottom_left.x, p.bottom_left.y)]
                    tur = str(r.format).split(".")[-1].replace("QRCode", "QR")
                    bulunan.append((tur, r.text, pts))
            except Exception:
                pass
        else:
            try:
                ok, metinler, noktalar, _ = qr.detectAndDecodeMulti(img)
                if ok:
                    bulunan += [("QR", m, pts) for m, pts in zip(metinler, noktalar) if m]
            except Exception:
                pass
            if bar is not None:
                try:
                    ok, metinler, turler, noktalar = bar.detectAndDecodeWithType(img)
                    if ok:
                        bulunan += [(str(t or "Barkod"), m, pts) for m, t, pts in zip(metinler, turler, noktalar) if m]
                except Exception:
                    pass
        for tur, m, pts in bulunan:
            if (i, m) in gorulen:
                continue
            gorulen.add((i, m))
            rect = None
            try:
                xs, ys = [float(p[0]) for p in pts], [float(p[1]) for p in pts]
                rect = fitz.Rect(min(xs) * olcek, min(ys) * olcek, max(xs) * olcek, max(ys) * olcek)
            except Exception:
                pass
            sonuc.append({"sayfa": i, "tur": tur, "metin": m, "rect": rect})
    return sonuc


# ------------------------------------------------------------------ NOT / METIN KUTUSU
def not_ekle(page, nokta, metin, yazar="PDF PRO"):
    """Sari yapiskan not (tiklayinca acilan yorum) ekler."""
    a = page.add_text_annot(fitz.Point(nokta), metin, icon="Comment")
    a.set_info(title=yazar, content=metin)
    a.set_colors(stroke=(1, 0.8, 0.1))
    a.update()
    return a


def metin_kutusu(page, rect, metin, boyut=11, renk=(0, 0, 0), font=None, cerceve=(0.2, 0.35, 0.6),
                 dolgu=(1, 1, 0.88), kenar=0.8):
    """Cerceveli, renkli zeminli metin kutusu (Turkce karakterler gomulu fontla). Yazi kutuya sigdirilir."""
    Z.sayfa_hazirla(page)
    rect = fitz.Rect(rect)
    font = font or Z.font_al(False, False, False)
    if cerceve or dolgu:
        sh = page.new_shape()
        sh.draw_rect(rect)
        sh.finish(color=cerceve, fill=dolgu, width=kenar if cerceve else 0)
        sh.commit()
    ic = rect + (4, 3, -4, -3)
    b = boyut
    while b >= 4:
        tw = fitz.TextWriter(page.rect, color=renk)
        artan = tw.fill_textbox(ic, metin, font=font, fontsize=b, warn=None)
        if not artan:
            break
        b *= 0.92
    Z.tw_yaz(page, tw)
    return b


# ------------------------------------------------------------------ FORM ALANI OLUSTUR
FORM_TURLERI = {"metin": "PDF_WIDGET_TYPE_TEXT", "onay": "PDF_WIDGET_TYPE_CHECKBOX",
                "liste": "PDF_WIDGET_TYPE_COMBOBOX"}


def _alan_adlari(doc):
    adlar = set()
    for p in doc:
        for w in p.widgets() or []:
            adlar.add(w.field_name)
    return adlar


def _benzersiz_ad(ad, adlar):
    ad = (ad or "Alan").strip().rstrip(":").strip()[:40] or "Alan"
    if ad not in adlar:
        adlar.add(ad)
        return ad
    k = 2
    while f"{ad} {k}" in adlar:
        k += 1
    adlar.add(f"{ad} {k}")
    return f"{ad} {k}"


def form_alani_ekle(page, rect, tur="metin", ad=None, secenekler=None, adlar=None, boyut=0):
    Z.sayfa_hazirla(page)
    adlar = adlar if adlar is not None else _alan_adlari(page.parent)
    w = fitz.Widget()
    w.field_type = getattr(fitz, FORM_TURLERI.get(tur, "PDF_WIDGET_TYPE_TEXT"))
    w.rect = fitz.Rect(rect)
    w.field_name = _benzersiz_ad(ad or {"metin": "Metin", "onay": "Onay", "liste": "Liste"}.get(tur, "Alan"), adlar)
    w.border_color = (0.45, 0.55, 0.7)
    w.border_width = 0.6
    w.fill_color = (0.93, 0.96, 1.0)
    if tur == "metin":
        w.text_font = "Helv"
        w.text_fontsize = boyut
        w.field_value = ""
    elif tur == "liste":
        w.choice_values = list(secenekler or ["Seçenek 1", "Seçenek 2"])
        w.field_value = w.choice_values[0]
        w.text_font = "Helv"
        w.text_fontsize = 0
    else:
        w.field_value = False
    page.add_widget(w)
    return w.field_name


def _etiket_bul(kelimeler, r, sag_once=False):
    """Alanin solundaki (ayni satirdaki) ya da hemen ustundeki yazi -> alan adi.
    Onay kutularinda once sagdaki yazi (kutu yazinin solunda olur)."""
    if sag_once:
        sag = sorted([w for w in kelimeler if w[0] >= r.x1 - 1
                      and abs((w[1] + w[3]) / 2 - (r.y0 + r.y1) / 2) < max(6, r.height)], key=lambda w: w[0])
        if sag and sag[0][0] - r.x1 < 30:
            secilen = [sag[0]]
            for w in sag[1:4]:
                if w[0] - secilen[-1][2] > 12:
                    break
                secilen.append(w)
            return " ".join(w[4] for w in secilen)
    sol = [w for w in kelimeler if w[2] <= r.x0 + 2 and abs((w[1] + w[3]) / 2 - (r.y0 + r.y1) / 2) < max(6, r.height * 0.7)
           and r.x0 - w[2] < 160]
    if sol:
        sol.sort(key=lambda w: w[0])
        # en sagdaki kelimeden geriye dogru, bosluk buyukse dur
        secilen = [sol[-1]]
        for w in reversed(sol[:-1]):
            if secilen[0][0] - w[2] > 12:
                break
            secilen.insert(0, w)
        return " ".join(w[4] for w in secilen)
    ust = [w for w in kelimeler if 0 < r.y0 - w[3] < 14 and w[0] < r.x1 and w[2] > r.x0]
    if ust:
        return " ".join(w[4] for w in sorted(ust, key=lambda w: w[0]))
    return None


def form_otomatik_algila(doc, sayfalar=None, ilerleme=None):
    """Bos form cizgilerini ( ____ , ...... , alt cizgiler) metin alani, kucuk kareleri onay kutusu yapar.
    Dondurur: eklenen alan sayisi."""
    import re
    adlar = _alan_adlari(doc)
    sayfalar = list(sayfalar) if sayfalar is not None else list(range(doc.page_count))
    toplam = 0
    for n, i in enumerate(sayfalar):
        if ilerleme:
            ilerleme(n, len(sayfalar), f"Sayfa {i + 1}")
        page = doc[i]
        Z.sayfa_hazirla(page)
        mevcut = [fitz.Rect(w.rect) for w in (page.widgets() or [])]
        notlar = [fitz.Rect(a.rect) for a in (page.annots() or [])]
        kelimeler = page.get_text("words")
        adaylar = []
        # 1) alt cizgi / nokta dizileri
        for w in kelimeler:
            t = w[4]
            m = re.search(r"(_{4,}|\.{6,}|…{3,})", t)
            if not m:
                continue
            r = fitz.Rect(w[:4])
            if len(t) > len(m.group(0)):
                # "Adı:______" gibi bitisik: sadece cizgi kismi
                f = r.width / max(1, len(t))
                r = fitz.Rect(r.x0 + m.start() * f, r.y0, r.x0 + m.end() * f, r.y1)
            h = max(10, min(16, r.height))
            adaylar.append(("metin", fitz.Rect(r.x0, r.y1 - h, r.x1, r.y1 + 1)))
        yazili = [fitz.Rect(w[:4]) for w in kelimeler if not re.fullmatch(r"[_.…]+", w[4])]
        # 2) cizilmis yatay cizgiler ve kucuk kareler
        try:
            cizimler = page.get_drawings()
        except Exception:
            cizimler = []
        for d in cizimler:
            for it in d.get("items", []):
                if it[0] == "l":
                    p1, p2 = it[1], it[2]
                    if abs(p1.y - p2.y) < 1 and abs(p2.x - p1.x) > 50:
                        x0, x1 = sorted((p1.x, p2.x))
                        r = fitz.Rect(x0, p1.y - 14, x1, p1.y - 0.5)
                        adaylar.append(("cizgi", r))
                elif it[0] == "re":
                    r = fitz.Rect(it[1])
                    if 5 <= r.width <= 18 and 5 <= r.height <= 18 and abs(r.width - r.height) < 2.5:
                        adaylar.append(("onay", r))
                    elif r.height < 1.5 and r.width > 50:     # ince dikdortgen = cizgi
                        adaylar.append(("cizgi", fitz.Rect(r.x0, r.y0 - 14, r.x1, r.y0 - 0.5)))
        # 3) kutu karakterleri
        for w in kelimeler:
            if w[4] in ("☐", "□", "❑", "❒", "▢", "◻"):
                adaylar.append(("onay", fitz.Rect(w[:4])))
        eklenen = []
        for tur, r in adaylar:
            if r.is_empty or r.width < 4:
                continue
            if tur == "cizgi":
                # ustunde yazi varsa (tablo cizgisi / altı cizili yazi) atla
                if any(fitz.Rect(y).intersects(r + (2, 2, -2, -2)) for y in yazili):
                    continue
                if r.width > page.rect.width * 0.8:      # sayfa boyu cizgi = ayirac
                    continue
                tur = "metin"
            if any((r & m).get_area() > 0.3 * min(r.get_area(), m.get_area()) for m in mevcut + eklenen):
                continue
            if any(r.intersects(a) for a in notlar):
                continue
            ad = _etiket_bul(kelimeler, r, sag_once=(tur == "onay")) or ("Onay" if tur == "onay" else "Metin")
            form_alani_ekle(page, r, tur, ad=ad, adlar=adlar)
            eklenen.append(r)
        toplam += len(eklenen)
    return toplam
