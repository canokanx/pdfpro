# -*- coding: utf-8 -*-
"""
PDF PRO - Cekirdek islemler
Birlestir / bol / dondur / sil / cikar / sikistir
Arayuzden bagimsizdir; her fonksiyon olusturdugu dosya yol(lar)ini dondurur.
"""
import os
import re

try:
    import pymupdf as fitz
except ImportError:  # eski surum
    import fitz

RESIM_UZANTILARI = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif", ".webp")


class PdfProHata(Exception):
    """Kullaniciya aynen gosterilecek hata."""


class BilesenEksik(PdfProHata):
    """Gerekli bir Python paketi kurulu degil; arayuz kurmayi teklif eder."""

    def __init__(self, ad, paket):
        super().__init__(f"{ad} kurulu değil.")
        self.ad, self.paket = ad, paket


# ---------------------------------------------------------------- yardimcilar
def sayfa_araligi_coz(metin, toplam):
    """'1-3, 5, 8-' gibi metni 0 tabanli sayfa listesine cevirir.
    Bos / 'tumu' / 'hepsi' = tum sayfalar.  'son' = son sayfa.  'tek'/'cift' desteklenir."""
    t = (metin or "").strip().lower()
    t = t.replace("ü", "u").replace("ç", "c").replace("ı", "i")
    if t in ("", "tumu", "hepsi", "tum", "all", "*"):
        return list(range(toplam))
    if t == "tek":
        return list(range(0, toplam, 2))
    if t == "cift":
        return list(range(1, toplam, 2))
    sonuc = []
    for parca in re.split(r"[,;\s]+", t):
        if not parca:
            continue
        parca = parca.replace("son", str(toplam))
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)", parca)
        if m:
            bas = int(m.group(1)) if m.group(1) else 1
            bit = int(m.group(2)) if m.group(2) else toplam
            if bas > bit:
                adim = -1
            else:
                adim = 1
            for s in range(bas, bit + adim, adim):
                if 1 <= s <= toplam:
                    sonuc.append(s - 1)
        elif parca.isdigit():
            s = int(parca)
            if 1 <= s <= toplam:
                sonuc.append(s - 1)
        else:
            raise PdfProHata(f"Sayfa aralığı anlaşılamadı: '{parca}'\nÖrnek: 1-3, 5, 8-son")
    if not sonuc:
        raise PdfProHata(f"Belgede {toplam} sayfa var; girilen aralıkta geçerli sayfa yok.")
    return sonuc


def aralik_gruplari(metin, toplam):
    """'1-3, 4-6, 7' -> [[0,1,2],[3,4,5],[6]]  (bolme icin her grup ayri dosya)"""
    gruplar = []
    for parca in re.split(r"[,;]+", metin or ""):
        if parca.strip():
            gruplar.append(sayfa_araligi_coz(parca, toplam))
    if not gruplar:
        raise PdfProHata("Bölmek için en az bir aralık girin. Örnek: 1-3, 4-6, 7-son")
    return gruplar


def pdf_ac(yol, sifre=None):
    if not os.path.isfile(yol):
        raise PdfProHata(f"Dosya bulunamadı:\n{yol}")
    try:
        doc = fitz.open(yol)
    except Exception as e:
        raise PdfProHata(f"Dosya açılamadı:\n{os.path.basename(yol)}\n\n{e}")
    if doc.needs_pass:
        if not sifre or not doc.authenticate(sifre):
            doc.close()
            raise PdfProHata(f"'{os.path.basename(yol)}' şifreli. Şifreyi girip tekrar deneyin.")
    if not doc.is_pdf:
        # resim vb. -> PDF'e cevir
        pdf_bytes = doc.convert_to_pdf()
        doc.close()
        doc = fitz.open("pdf", pdf_bytes)
    return doc


def kaydet(doc, cikti):
    klasor = os.path.dirname(os.path.abspath(cikti))
    os.makedirs(klasor, exist_ok=True)
    try:
        doc.save(cikti, garbage=3, deflate=True)
    except Exception as e:
        if "Permission" in str(e) or "denied" in str(e).lower():
            raise PdfProHata(f"Dosya yazılamadı (açık olabilir mi?):\n{cikti}")
        raise
    return cikti


def benzersiz_yol(yol):
    """Ayni isimde dosya varsa _2, _3 ekler."""
    if not os.path.exists(yol):
        return yol
    kok, uz = os.path.splitext(yol)
    i = 2
    while os.path.exists(f"{kok}_{i}{uz}"):
        i += 1
    return f"{kok}_{i}{uz}"


def sayfa_sayisi(yol):
    with pdf_ac(yol) as d:
        return d.page_count


# ---------------------------------------------------------------- islemler
def birlestir(dosyalar, cikti, ilerleme=None):
    """PDF ve resimleri sirasiyla tek PDF'te birlestirir."""
    if not dosyalar:
        raise PdfProHata("Birleştirilecek dosya seçilmedi.")
    hedef = fitz.open()
    for i, yol in enumerate(dosyalar):
        if ilerleme:
            ilerleme(i, len(dosyalar), os.path.basename(yol))
        kaynak = pdf_ac(yol)
        hedef.insert_pdf(kaynak)
        kaynak.close()
    if ilerleme:
        ilerleme(len(dosyalar), len(dosyalar), "Kaydediliyor")
    kaydet(hedef, cikti)
    hedef.close()
    return cikti


def bol(yol, klasor, mod="her_sayfa", deger=None, ilerleme=None):
    """mod: 'her_sayfa' | 'n_sayfa' (deger=N) | 'araliklar' (deger='1-3, 4-6')"""
    doc = pdf_ac(yol)
    n = doc.page_count
    if mod == "her_sayfa":
        gruplar = [[i] for i in range(n)]
    elif mod == "n_sayfa":
        try:
            adim = int(deger)
            assert adim > 0
        except Exception:
            raise PdfProHata("Kaç sayfada bir bölüneceğini sayı olarak girin.")
        gruplar = [list(range(i, min(i + adim, n))) for i in range(0, n, adim)]
    else:
        gruplar = aralik_gruplari(deger, n)

    ad = os.path.splitext(os.path.basename(yol))[0]
    os.makedirs(klasor, exist_ok=True)
    ciktilar = []
    for gi, grup in enumerate(gruplar):
        if ilerleme:
            ilerleme(gi, len(gruplar), f"Parça {gi + 1}")
        yeni = fitz.open()
        for s in grup:
            yeni.insert_pdf(doc, from_page=s, to_page=s)
        if len(grup) == 1:
            etiket = f"s{grup[0] + 1}"
        else:
            etiket = f"s{grup[0] + 1}-{grup[-1] + 1}"
        c = benzersiz_yol(os.path.join(klasor, f"{ad}_{etiket}.pdf"))
        kaydet(yeni, c)
        yeni.close()
        ciktilar.append(c)
    doc.close()
    return ciktilar


def sayfa_cikar(yol, aralik, cikti):
    """Secilen sayfalari (verilen sirada) yeni PDF'e alir."""
    doc = pdf_ac(yol)
    secim = sayfa_araligi_coz(aralik, doc.page_count)
    yeni = fitz.open()
    for s in secim:
        yeni.insert_pdf(doc, from_page=s, to_page=s)
    kaydet(yeni, cikti)
    yeni.close()
    doc.close()
    return cikti


def sayfa_sil(yol, aralik, cikti):
    doc = pdf_ac(yol)
    secim = sorted(set(sayfa_araligi_coz(aralik, doc.page_count)))
    if len(secim) >= doc.page_count:
        raise PdfProHata("Tüm sayfalar silinemez; en az bir sayfa kalmalı.")
    doc.delete_pages(secim)
    kaydet(doc, cikti)
    doc.close()
    return cikti


def dondur(yol, aralik, aci, cikti):
    """aci: 90 (saga), -90/270 (sola), 180"""
    doc = pdf_ac(yol)
    for s in sayfa_araligi_coz(aralik, doc.page_count):
        p = doc[s]
        p.set_rotation((p.rotation + int(aci)) % 360)
    kaydet(doc, cikti)
    doc.close()
    return cikti


def sirala(yol, yeni_sira, cikti):
    """yeni_sira: 0 tabanli sayfa listesi (ornek: [2,0,1])"""
    doc = pdf_ac(yol)
    doc.select(list(yeni_sira))
    kaydet(doc, cikti)
    doc.close()
    return cikti


SIKISTIRMA_SEVIYELERI = [
    # ad, hedef dpi, jpeg kalitesi
    ("hafif", 200, 85),
    ("orta", 150, 70),
    ("guclu", 110, 55),
    ("en_kucuk", 90, 45),
    ("asiri", 72, 35),
]


def _resimleri_sikistir(doc, hedef_dpi, kalite, gri=False, ilerleme=None, iptal=None):
    """Her resmi gosterildigi boyuta gore hedef dpi'ye indirir ve JPEG olarak yeniden sikistirir.
    Sadece kuculen resimler degistirilir; saydam (maskeli) resimlere dokunulmaz."""
    import io
    from PIL import Image
    goruldu = set()
    n = doc.page_count
    for i, p in enumerate(doc):
        if iptal and iptal():
            raise PdfProHata("İşlem iptal edildi.")
        if ilerleme:
            ilerleme(i, n, f"Sayfa {i + 1}/{n} resimleri")
        for im in p.get_images(full=True):
            xref, smask = im[0], im[1]
            if xref in goruldu:
                continue
            goruldu.add(xref)
            if smask:
                continue
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
                if gri and mod != "L":
                    img = img.convert("L")
                gen_pt = max((r.width for r in p.get_image_rects(xref)), default=0)
                if gen_pt > 0:
                    dpi = pix.width / (gen_pt / 72)
                    if dpi > hedef_dpi * 1.15:
                        o = hedef_dpi / dpi
                        img = img.resize((max(1, int(img.width * o)), max(1, int(img.height * o))), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=kalite, optimize=True, progressive=True)
                yeni = buf.getvalue()
                if len(yeni) < eski_boy * 0.9:
                    p.replace_image(xref, stream=yeni)
            except Exception:
                continue


def _yazilar_ayni(a, b):
    """Iki PDF'teki kelimelerin yerleri ayni mi? (sikistirma sonrasi kayma kontrolu)"""
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


def sikistir(yol, cikti, seviye="orta", hedef_kb=None, gri=False, ilerleme=None, iptal=None):
    """PDF'i kucultur. seviye: hafif | orta | guclu | en_kucuk
    hedef_kb verilirse (or. 1024 = 1 MB) o boyutun altina inene kadar seviyeyi kendisi artirir.
    Donus: (cikti, once_bayt, sonra_bayt, kullanilan_seviye)"""
    once = os.path.getsize(yol)
    adlar = [a for a, _, _ in SIKISTIRMA_SEVIYELERI]
    bas = adlar.index(seviye) if seviye in adlar else 1
    denenecek = SIKISTIRMA_SEVIYELERI[bas:] if hedef_kb else [SIKISTIRMA_SEVIYELERI[bas]]
    os.makedirs(os.path.dirname(os.path.abspath(cikti)), exist_ok=True)
    gecici = cikti + ".tmp"
    en_iyi = None
    for ad, dpi, kalite in denenecek:
        doc = pdf_ac(yol)
        _resimleri_sikistir(doc, dpi, kalite, gri, ilerleme, iptal)
        try:
            doc.subset_fonts()
        except Exception:
            pass
        # DIKKAT: clean=True kullanilmaz; bazi resmi belgelerde (Jasper/iText, ' operatoru)
        # MuPDF'in icerik temizleyicisi yazilari asagi kaydiriyor.
        try:
            doc.save(gecici, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True, use_objstms=1)
        except TypeError:
            doc.save(gecici, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True)
        doc.close()
        if not _yazilar_ayni(yol, gecici):
            # guvenlik: yazi yerleri degistiyse sadece resimleri sikistirilmis, font dokunulmamis hali kaydet
            doc = pdf_ac(yol)
            _resimleri_sikistir(doc, dpi, kalite, gri)
            doc.save(gecici, garbage=3, deflate=True)
            doc.close()
            if not _yazilar_ayni(yol, gecici):
                doc = pdf_ac(yol)
                doc.save(gecici, garbage=3, deflate=True)
                doc.close()
        boy = os.path.getsize(gecici)
        if en_iyi is None or boy < en_iyi[1]:
            os.replace(gecici, cikti)
            en_iyi = (ad, boy)
        if not hedef_kb or boy <= hedef_kb * 1024:
            break
    if os.path.exists(gecici):
        os.remove(gecici)
    return cikti, once, os.path.getsize(cikti), en_iyi[0]


def sifre_kaldir(yol, sifre, cikti):
    doc = pdf_ac(yol, sifre)
    kaydet(doc, cikti)
    doc.close()
    return cikti


def sifre_koy(yol, sifre, cikti):
    if not sifre:
        raise PdfProHata("Şifre boş olamaz.")
    doc = pdf_ac(yol)
    os.makedirs(os.path.dirname(os.path.abspath(cikti)), exist_ok=True)
    doc.save(cikti, garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_AES_256,
             user_pw=sifre, owner_pw=sifre,
             permissions=int(fitz.PDF_PERM_PRINT | fitz.PDF_PERM_COPY | fitz.PDF_PERM_ACCESSIBILITY))
    doc.close()
    return cikti


def sayfa_resmi(yol_veya_doc, sayfa_no, genislik_px=600):
    """Onizleme icin PIL Image dondurur."""
    from PIL import Image
    kapat = False
    doc = yol_veya_doc
    if isinstance(yol_veya_doc, str):
        doc = pdf_ac(yol_veya_doc)
        kapat = True
    p = doc[sayfa_no]
    olcek = genislik_px / p.rect.width
    pix = p.get_pixmap(matrix=fitz.Matrix(olcek, olcek), alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    if kapat:
        doc.close()
    return img
