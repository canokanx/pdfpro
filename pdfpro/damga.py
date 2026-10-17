# -*- coding: utf-8 -*-
"""
PDF PRO - Imza / Kase, Antet, Filigran, Sayfa numarasi
Tum konumlar sayfanin GORUNEN haline gore hesaplanir (dondurulmus sayfalar once duzeltilir).
"""
import io
import os

from .cekirdek import fitz, pdf_ac, kaydet, PdfProHata, sayfa_araligi_coz, RESIM_UZANTILARI
from .duzenle import tw_yaz

PROGRAM_KLASORU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MM = 72 / 25.4

KONUMLAR = ["Sağ alt", "Orta alt", "Sol alt", "Sağ üst", "Orta üst", "Sol üst", "Orta", "Özel (önizlemede tıkla)"]


# ------------------------------------------------------------------ yardimci
def font_yolu(kalin=False):
    adaylar = []
    win = os.environ.get("WINDIR", r"C:\Windows")
    if kalin:
        adaylar += [os.path.join(win, "Fonts", "arialbd.ttf"),
                    os.path.join(PROGRAM_KLASORU, "fonts", "DejaVuSans-Bold.ttf")]
    adaylar += [os.path.join(win, "Fonts", "arial.ttf"),
                os.path.join(PROGRAM_KLASORU, "fonts", "DejaVuSans.ttf"),
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for a in adaylar:
        if os.path.isfile(a):
            return a
    return None


def _font(kalin=False):
    y = font_yolu(kalin)
    return fitz.Font(fontfile=y) if y else fitz.Font("helv")


def renk_cevir(renk):
    """'#RRGGBB' -> (r,g,b) 0-1"""
    if isinstance(renk, (tuple, list)):
        return tuple(renk)
    r = renk.lstrip("#")
    return tuple(int(r[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _rotasyonu_kaldir(page):
    """Dondurulmus sayfayi gorunumu degistirmeden 0 dereceye getirir ve
    icerigi q/Q ile sarar (aksi halde eklenen yazi kayabilir/kaybolabilir)."""
    if page.rotation:
        try:
            page.remove_rotation()
        except Exception:
            pass
    try:
        page.wrap_contents()
    except Exception:
        pass


def resim_hazirla(yol, opaklik=1.0, beyazi_sil=False, esik=225):
    """Resmi PNG baytina cevirir; istenirse beyaz arka plani saydam yapar, opaklik uygular.
    (genislik, yukseklik, png_bayt) dondurur."""
    from PIL import Image
    try:
        img = Image.open(yol)
    except Exception:
        raise PdfProHata(f"Resim açılamadı:\n{yol}")
    img = img.convert("RGBA")
    if beyazi_sil:
        import numpy as np
        a = np.array(img).astype("float32")
        parlaklik = a[..., :3].min(axis=2)  # en koyu kanal: renkli murekkebi korur
        # esik ustu tamamen saydam, esik-40 arasi yumusak gecis
        alfa = np.clip((esik - parlaklik) / 40.0, 0, 1)
        a[..., 3] = a[..., 3] * alfa
        img = Image.fromarray(a.astype("uint8"), "RGBA")
    if opaklik < 1:
        r, g, b, al = img.split()
        al = al.point(lambda v: int(v * opaklik))
        img = Image.merge("RGBA", (r, g, b, al))
    bbox = img.getbbox()  # bos kenarlari kirp
    if bbox:
        img = img.crop(bbox)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return img.width, img.height, buf.getvalue()


def konum_hesapla(sayfa_rect, konum, gen, yuk, ozel=None, kenar_mm=15):
    """Yerlestirilecek kutuyu (fitz.Rect) dondurur. ozel=(x_oran, y_oran) -> kutunun merkezi."""
    W, H = sayfa_rect.width, sayfa_rect.height
    k = kenar_mm * MM
    if konum.startswith("Özel") and ozel:
        cx, cy = ozel[0] * W, ozel[1] * H
    else:
        yatay = "sag" if "Sağ" in konum else "sol" if "Sol" in konum else "orta"
        dikey = "alt" if "alt" in konum else "ust" if "üst" in konum else "orta"
        cx = {"sol": k + gen / 2, "orta": W / 2, "sag": W - k - gen / 2}[yatay]
        cy = {"ust": k + yuk / 2, "orta": H / 2, "alt": H - k - yuk / 2}[dikey]
    return fitz.Rect(cx - gen / 2, cy - yuk / 2, cx + gen / 2, cy + yuk / 2)


# ------------------------------------------------------------------ imza / kase
def imza_ekle(yol, cikti, resim, sayfalar="son", konum="Sağ alt", ozel=None,
              genislik_mm=45, beyazi_sil=True, opaklik=1.0, ilerleme=None):
    """Imza / kase resmini secilen sayfalara basar. ozel: (x_oran, y_oran) merkez."""
    doc = pdf_ac(yol)
    rw, rh, png = resim_hazirla(resim, opaklik, beyazi_sil)
    secim = sayfa_araligi_coz(sayfalar, doc.page_count)
    for k, s in enumerate(secim):
        if ilerleme:
            ilerleme(k, len(secim), f"Sayfa {s + 1}")
        page = doc[s]
        _rotasyonu_kaldir(page)
        gen = genislik_mm * MM
        yuk = gen * rh / rw
        kutu = konum_hesapla(page.rect, konum, gen, yuk, ozel)
        page.insert_image(kutu, stream=png, keep_proportion=True, overlay=True)
    kaydet(doc, cikti)
    doc.close()
    return cikti


def imza_kutusu_onizleme(sayfa_rect, resim, konum, ozel, genislik_mm):
    """Onizlemede cerceve cizmek icin kutuyu dondurur."""
    from PIL import Image
    with Image.open(resim) as im:
        rw, rh = im.size
    gen = genislik_mm * MM
    return konum_hesapla(sayfa_rect, konum, gen, gen * rh / rw, ozel)


# ------------------------------------------------------------------ filigran
def filigran_ekle(yol, cikti, metin="GİZLİDİR", sayfalar="", aci=45, opaklik=0.15,
                  boyut=0, renk="#C0392B", kalin=True, desen=False, ilerleme=None):
    """Metin filigrani. boyut=0 -> sayfaya gore otomatik. desen=True -> tum sayfaya dosenmis tekrar."""
    if not metin.strip():
        raise PdfProHata("Filigran metni boş.")
    doc = pdf_ac(yol)
    font = _font(kalin)
    rgb = renk_cevir(renk)
    secim = sayfa_araligi_coz(sayfalar, doc.page_count)
    for k, s in enumerate(secim):
        if ilerleme:
            ilerleme(k, len(secim), f"Sayfa {s + 1}")
        page = doc[s]
        _rotasyonu_kaldir(page)
        r = page.rect
        if desen:
            fs = boyut or max(14, min(r.width, r.height) / 18)
        else:
            if boyut:
                fs = boyut
            else:  # kosegene sigacak boyut
                kosegen = (r.width ** 2 + r.height ** 2) ** 0.5
                fs = min(kosegen * 0.6 / max(font.text_length(metin, 1), 0.1), r.height / 4)
        tw = fitz.TextWriter(r, opacity=opaklik, color=rgb)
        uz = font.text_length(metin, fs)
        merkezler = []
        if desen:
            adim_x, adim_y = uz + fs * 3, fs * 5
            y = -r.height * 0.2
            satir = 0
            while y < r.height * 1.2:
                x = -r.width * 0.3 + (satir % 2) * adim_x / 2
                while x < r.width * 1.3:
                    merkezler.append(fitz.Point(x, y))
                    x += adim_x
                y += adim_y
                satir += 1
        else:
            merkezler.append(fitz.Point(r.width / 2, r.height / 2))
        for m in merkezler:
            tw.append(fitz.Point(m.x - uz / 2, m.y + fs * 0.35), metin, font=font, fontsize=fs)
        merkez = fitz.Point(r.width / 2, r.height / 2)
        tw_yaz(page, tw, morph=(merkez, fitz.Matrix(aci)))
    kaydet(doc, cikti)
    doc.close()
    return cikti


def resim_filigran_ekle(yol, cikti, resim, sayfalar="", opaklik=0.15, genislik_orani=0.6, ilerleme=None):
    doc = pdf_ac(yol)
    rw, rh, png = resim_hazirla(resim, opaklik, beyazi_sil=False)
    secim = sayfa_araligi_coz(sayfalar, doc.page_count)
    for k, s in enumerate(secim):
        if ilerleme:
            ilerleme(k, len(secim), f"Sayfa {s + 1}")
        page = doc[s]
        _rotasyonu_kaldir(page)
        gen = page.rect.width * genislik_orani
        kutu = konum_hesapla(page.rect, "Orta", gen, gen * rh / rw)
        page.insert_image(kutu, stream=png, overlay=True)
    kaydet(doc, cikti)
    doc.close()
    return cikti


# ------------------------------------------------------------------ antet
def antet_ekle(yol, cikti, antet, sayfalar="", yerlesim="Tam sayfa", onde=False,
               ikinci_sayfa_devam=True, ilerleme=None):
    """antet: PDF veya resim.
    PDF antet: sayfanin tamamina basilir. Antet PDF'i 2 sayfaliysa ve ikinci_sayfa_devam=True ise
               1. sayfaya antetin 1. sayfasi, digerlerine 2. sayfasi basilir.
    Resim antet: yerlesim = 'Tam sayfa' | 'Üst bilgi' | 'Alt bilgi'
    onde=False -> antet yazilarin ARKASINA basilir (beyaz arka planli taramalarda gorunmez, o zaman onde=True)."""
    doc = pdf_ac(yol)
    secim = sayfa_araligi_coz(sayfalar, doc.page_count)
    uz = os.path.splitext(antet)[1].lower()
    if uz == ".pdf":
        src = pdf_ac(antet)
        for k, s in enumerate(secim):
            if ilerleme:
                ilerleme(k, len(secim), f"Sayfa {s + 1}")
            page = doc[s]
            _rotasyonu_kaldir(page)
            kaynak_sayfa = 1 if (ikinci_sayfa_devam and src.page_count > 1 and k > 0) else 0
            page.show_pdf_page(page.rect, src, kaynak_sayfa, keep_proportion=False, overlay=onde)
        src.close()
    elif uz in RESIM_UZANTILARI:
        rw, rh, png = resim_hazirla(antet)
        for k, s in enumerate(secim):
            if ilerleme:
                ilerleme(k, len(secim), f"Sayfa {s + 1}")
            page = doc[s]
            _rotasyonu_kaldir(page)
            r = page.rect
            if yerlesim == "Üst bilgi":
                kutu = fitz.Rect(0, 0, r.width, r.width * rh / rw)
            elif yerlesim == "Alt bilgi":
                h = r.width * rh / rw
                kutu = fitz.Rect(0, r.height - h, r.width, r.height)
            else:
                kutu = r
            page.insert_image(kutu, stream=png, keep_proportion=(yerlesim != "Tam sayfa"), overlay=onde)
    else:
        raise PdfProHata("Antet dosyası PDF veya resim (PNG/JPG) olmalı.")
    kaydet(doc, cikti)
    doc.close()
    return cikti


# ------------------------------------------------------------------ sayfa numarasi
def sayfa_no_ekle(yol, cikti, bicim="Sayfa {n} / {N}", konum="Orta alt", boyut=10,
                  baslangic=1, sayfalar="", renk="#333333", ilerleme=None):
    doc = pdf_ac(yol)
    font = _font(False)
    rgb = renk_cevir(renk)
    secim = sayfa_araligi_coz(sayfalar, doc.page_count)
    toplam = len(secim) + baslangic - 1
    for k, s in enumerate(secim):
        if ilerleme:
            ilerleme(k, len(secim), f"Sayfa {s + 1}")
        page = doc[s]
        _rotasyonu_kaldir(page)
        yazi = bicim.replace("{n}", str(k + baslangic)).replace("{N}", str(toplam))
        uz = font.text_length(yazi, boyut)
        kutu = konum_hesapla(page.rect, konum, uz, boyut, kenar_mm=10)
        tw = fitz.TextWriter(page.rect, color=rgb)
        tw.append(fitz.Point(kutu.x0, kutu.y1 - boyut * 0.2), yazi, font=font, fontsize=boyut)
        tw_yaz(page, tw)
    kaydet(doc, cikti)
    doc.close()
    return cikti
