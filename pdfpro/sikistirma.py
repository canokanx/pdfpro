# -*- coding: utf-8 -*-
"""
PDF PRO - Sikistirma

Hedef boyut verilmezse secilen seviye uygulanir. Hedef verilirse (or. 2 MB):
  1) Kalite merdiveninde ikili arama: hedefe sigan EN KALITELI ayar bulunur
     (gereksiz yere bulaniklastirilmaz).
  2) Sigmazsa ve belgedeki agirlik resim degil de cizim / yazi tipi ise sayfalar resme cevrilir
     (gorunmez yazi katmani eklenir: arama ve kopyalama calismaya devam eder).
  3) Kullanici izin verdiyse: gri tonlama, en sonda siyah-beyaz (faks gibi; yazi net kalir).
Her durumda:
  * 1 bitlik (siyah-beyaz) taramalar JPEG'e cevrilmez; CCITT G4 ile kayipsiz ve cok kucuk saklanir.
  * Renkli taranmis ama aslinda siyah-beyaz olan sayfalar fark edilmeden griye cevrilir
    (mavi kase / imza gibi renkli bir sey varsa dokunulmaz).
"""
import io
import os

from .cekirdek import fitz, pdf_ac, PdfProHata

# (hedef dpi, jpeg kalitesi) - iyiden kucuge
MERDIVEN = [(220, 82), (200, 80), (175, 76), (150, 72), (150, 64), (135, 60), (120, 56), (110, 52),
            (100, 48), (90, 44), (80, 40), (72, 36), (60, 32)]
SEVIYE = {"hafif": 1, "orta": 3, "guclu": 7, "en_kucuk": 9, "asiri": 11}
SEVIYE_ADI = {"hafif": "Hafif", "orta": "Orta", "guclu": "Güçlü", "en_kucuk": "En küçük", "asiri": "Aşırı"}


def _renkli_mi(img):
    """Resimde gercekten renkli bolge (kase, imza, logo, fotograf) var mi?"""
    k = img.copy()
    k.thumbnail((400, 400))
    try:
        import numpy as np
        a = np.asarray(k.convert("RGB")).astype(np.int16)
        yayilim = a.max(axis=2) - a.min(axis=2)
        return float((yayilim > 40).mean()) > 0.0003
    except Exception:
        px = list(k.convert("RGB").getdata())
        renkli = sum(1 for r, g, b in px if max(r, g, b) - min(r, g, b) > 40)
        return renkli / max(1, len(px)) > 0.0003


def _siyah_beyaz(img):
    """Belge taramasini 1 bit'e cevirir (golge / zemin rengi temizlenerek)."""
    from PIL import Image
    g = img.convert("L")
    try:
        import cv2
        import numpy as np
        a = np.asarray(g)
        blok = max(15, (min(a.shape) // 40) | 1)
        b = cv2.adaptiveThreshold(a, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, blok, 12)
        return Image.fromarray(b).convert("1")
    except Exception:
        return g.point(lambda v: 255 if v > 160 else 0).convert("1")


def _resimler(doc, hedef_dpi, kalite, gri=False, siyah_beyaz=False, ilerleme=None, iptal=None, etiket=""):
    """Resimleri gosterildikleri boyuta gore hedef dpi'ye indirip yeniden sikistirir."""
    from PIL import Image
    goruldu = set()
    n = doc.page_count
    for i, p in enumerate(doc):
        if iptal and iptal():
            raise PdfProHata("İşlem iptal edildi.")
        if ilerleme:
            ilerleme(i, n, f"{etiket}sayfa {i + 1}/{n}")
        for im in p.get_images(full=True):
            xref, smask, bpc = im[0], im[1], im[4]
            if xref in goruldu:
                continue
            goruldu.add(xref)
            if smask or (bpc == 1 and not siyah_beyaz):
                continue        # saydam resim / zaten siyah-beyaz tarama (asagida CCITT ile)
            try:
                eski_boy = len(doc.xref_stream_raw(xref) or b"")
                pix = fitz.Pixmap(doc, xref)
                if pix.n - pix.alpha >= 4:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                if pix.alpha:
                    pix = fitz.Pixmap(pix, 0)
                if pix.width * pix.height < 64 * 64:
                    continue
                mod = "RGB" if pix.n >= 3 else "L"
                img = Image.frombytes(mod, (pix.width, pix.height), pix.samples)
                if mod == "RGB" and (gri or siyah_beyaz or not _renkli_mi(img)):
                    img = img.convert("L")
                rects = p.get_image_rects(xref)
                gen_pt = max((r.width for r in rects), default=0) or p.rect.width
                yuk_pt = max((r.height for r in rects), default=0) or p.rect.height
                dpi = min(img.width / (gen_pt / 72), img.height / (yuk_pt / 72))
                hedef = hedef_dpi if not siyah_beyaz else max(hedef_dpi, 200)
                if dpi > hedef * 1.15:
                    o = hedef / dpi
                    img = img.resize((max(1, int(img.width * o)), max(1, int(img.height * o))), Image.LANCZOS)
                buf = io.BytesIO()
                if siyah_beyaz:
                    _siyah_beyaz(img).save(buf, "PNG", optimize=True)
                else:
                    img.save(buf, "JPEG", quality=kalite, optimize=True, progressive=True)
                yeni = buf.getvalue()
                if len(yeni) < eski_boy * 0.92:
                    p.replace_image(xref, stream=yeni)
            except Exception:
                continue
    # 1 bitlik resimler: kayipsiz CCITT G4 (cok kucuk, yazilar keskin)
    try:
        doc.rewrite_images(lossy=True, lossless=True, bitonal=True, color=False, gray=False)
    except Exception:
        pass


def _kaydet(doc, yol, guvenli=False):
    if not guvenli:
        try:
            doc.subset_fonts()
        except Exception:
            pass
        try:
            doc.scrub(metadata=False, xml_metadata=True, thumbnails=True, attached_files=False,
                      embedded_files=False, javascript=True, clean_pages=False, hidden_text=False,
                      redactions=False, remove_links=False, reset_fields=False, reset_responses=False)
        except Exception:
            pass
    # DIKKAT: clean=True kullanilmaz; bazi resmi belgelerde (Jasper/iText) yazilar kayiyor.
    try:
        doc.save(yol, garbage=4 if not guvenli else 3, deflate=True, deflate_images=True,
                 deflate_fonts=True, use_objstms=1)
    except TypeError:
        doc.save(yol, garbage=3, deflate=True)


def _yazilar_ayni(a, b):
    try:
        da, db = fitz.open(a), fitz.open(b)
        if da.page_count != db.page_count:
            return False
        for pa, pb in zip(da, db):
            ka = sorted((round(w[0]), round(w[1]), w[4]) for w in pa.get_text("words"))
            kb = sorted((round(w[0]), round(w[1]), w[4]) for w in pb.get_text("words"))
            if ka != kb:
                return False
        return True
    except Exception:
        return False


def _deneme(yol, cikti, dpi, kalite, gri=False, siyah_beyaz=False, ilerleme=None, iptal=None, etiket=""):
    doc = pdf_ac(yol)
    _resimler(doc, dpi, kalite, gri, siyah_beyaz, ilerleme, iptal, etiket)
    _kaydet(doc, cikti)
    doc.close()
    if not _yazilar_ayni(yol, cikti):
        # guvenlik: yazi yerleri kaydiysa yazi tiplerine dokunmadan tekrar
        doc = pdf_ac(yol)
        _resimler(doc, dpi, kalite, gri, siyah_beyaz)
        _kaydet(doc, cikti, guvenli=True)
        doc.close()
    return os.path.getsize(cikti)


def _resim_payi(yol):
    """Dosyadaki resimlerin toplam boyutunun dosyaya orani."""
    try:
        with fitz.open(yol) as d:
            toplam, gor = 0, set()
            for p in d:
                for im in p.get_images(full=True):
                    if im[0] not in gor:
                        gor.add(im[0])
                        toplam += len(d.xref_stream_raw(im[0]) or b"")
        return toplam / max(1, os.path.getsize(yol))
    except Exception:
        return 1.0


def rasterla(yol, cikti, dpi, kalite, gri=False, ilerleme=None, iptal=None):
    """Her sayfayi tek resme cevirir; gorunmez yazi katmani ekler (arama / kopyalama calisir)."""
    from PIL import Image
    from . import duzenle as Z
    from . import ocr as O
    kaynak = pdf_ac(yol)
    hedef = fitz.open()
    n = kaynak.page_count
    for i in range(n):
        if iptal and iptal():
            raise PdfProHata("İşlem iptal edildi.")
        if ilerleme:
            ilerleme(i, n, f"Sayfalar resme çevriliyor ({dpi} dpi): {i + 1}/{n}")
        p = kaynak[i]
        Z.sayfa_hazirla(p)
        pix = p.get_pixmap(dpi=dpi, alpha=False, colorspace=fitz.csGRAY if gri else fitz.csRGB)
        img = Image.frombytes("L" if gri else "RGB", (pix.width, pix.height), pix.samples)
        if not gri and not _renkli_mi(img):
            img = img.convert("L")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=kalite, optimize=True, progressive=True)
        yeni = hedef.new_page(width=p.rect.width, height=p.rect.height)
        yeni.insert_image(yeni.rect, stream=buf.getvalue())
        kelimeler = [(w[4], (w[0], w[1], w[2], w[3]), 100, (0, 0, 0)) for w in p.get_text("words")]
        if kelimeler:
            O.metin_katmani_ekle(yeni, kelimeler, 1.0)
    try:
        hedef.set_toc(kaynak.get_toc())
    except Exception:
        pass
    _kaydet(hedef, cikti)
    hedef.close()
    kaynak.close()
    return os.path.getsize(cikti)


def sikistir(yol, cikti, seviye="orta", hedef_kb=None, gri=False, ilerleme=None, iptal=None,
             renk_izni=False):
    """Donus: (cikti, once_bayt, sonra_bayt, aciklama)
    renk_izni: hedefe inilemezse griye / siyah-beyaza cevirmeye izin"""
    once = os.path.getsize(yol)
    os.makedirs(os.path.dirname(os.path.abspath(cikti)), exist_ok=True)
    il = ilerleme or (lambda *a: None)
    gecici = cikti + ".deneme"
    en_iyi = {"boy": None, "aciklama": ""}

    def sakla(boy, aciklama):
        if en_iyi["boy"] is None or boy < en_iyi["boy"]:
            os.replace(gecici, cikti)
            en_iyi.update(boy=boy, aciklama=aciklama)
        elif os.path.exists(gecici):
            os.remove(gecici)

    try:
        if not hedef_kb:
            dpi, q = MERDIVEN[SEVIYE.get(seviye, 3)]
            boy = _deneme(yol, gecici, dpi, q, gri, False, il, iptal)
            sakla(boy, f"{SEVIYE_ADI.get(seviye, seviye)} ({dpi} dpi)" + (" · gri" if gri else ""))
            return cikti, once, os.path.getsize(cikti), en_iyi["aciklama"]

        sinir = hedef_kb * 1024
        sonuc = {}

        def dene(i, gri_=gri):
            if (i, gri_) not in sonuc:
                dpi, q = MERDIVEN[i]
                boy = _deneme(yol, gecici, dpi, q, gri_, False, il, iptal,
                              etiket=f"Deneme {len(sonuc) + 1} ({dpi} dpi, kalite {q}): ")
                sonuc[(i, gri_)] = boy
                if boy <= sinir:
                    # hedefe uyanlar arasinda en kalitelisi (en kucuk indeks) saklanir
                    if en_iyi["boy"] is None or en_iyi["boy"] > sinir or i < en_iyi.get("i", 99):
                        os.replace(gecici, cikti)
                        en_iyi.update(boy=boy, i=i, aciklama=f"{dpi} dpi, kalite {q}" + (" · gri" if gri_ else ""))
                    elif os.path.exists(gecici):
                        os.remove(gecici)
                else:
                    if en_iyi["boy"] is None or (en_iyi["boy"] > sinir and boy < en_iyi["boy"]):
                        os.replace(gecici, cikti)
                        en_iyi.update(boy=boy, i=i, aciklama=f"{dpi} dpi, kalite {q}" + (" · gri" if gri_ else ""))
                    elif os.path.exists(gecici):
                        os.remove(gecici)
            return sonuc[(i, gri_)]

        def ara(gri_):
            """Hedefe sigan en kaliteli basamak (ikili arama). Bulunamazsa None."""
            son = len(MERDIVEN) - 1
            if dene(son, gri_) > sinir:
                return None
            alt, ust = 0, son
            while alt < ust:
                orta = (alt + ust) // 2
                if dene(orta, gri_) <= sinir:
                    ust = orta
                else:
                    alt = orta + 1
            return alt

        if ara(gri) is not None:
            return cikti, once, os.path.getsize(cikti), en_iyi["aciklama"]
        # 2) agirlik resim degilse: sayfalari resme cevir
        if _resim_payi(yol) < 0.6:
            for dpi, q in ((150, 70), (120, 60), (100, 50), (80, 42), (72, 36)):
                boy = rasterla(yol, gecici, dpi, q, gri, il, iptal)
                sakla(boy, f"sayfalar resme çevrildi ({dpi} dpi, yazılar aranabilir)")
                if boy <= sinir:
                    break
            if en_iyi["boy"] <= sinir:
                return cikti, once, os.path.getsize(cikti), en_iyi["aciklama"]
        # 3) izin varsa renkten vazgec
        if renk_izni and not gri:
            if ara(True) is not None:
                return cikti, once, os.path.getsize(cikti), en_iyi["aciklama"]
        if renk_izni:
            for dpi in (200, 150):
                il(0, 1, f"Siyah-beyaz deneniyor ({dpi} dpi)")
                boy = _deneme(yol, gecici, dpi, 60, True, True, il, iptal, etiket="Siyah-beyaz: ")
                sakla(boy, f"siyah-beyaz tarama ({dpi} dpi, yazılar net)")
                if boy <= sinir:
                    break
        return cikti, once, os.path.getsize(cikti), en_iyi["aciklama"]
    finally:
        if os.path.exists(gecici):
            try:
                os.remove(gecici)
            except OSError:
                pass
