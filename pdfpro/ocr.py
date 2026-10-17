# -*- coding: utf-8 -*-
"""
PDF PRO - OCR ve metin cikarma (Tesseract)
Turkce/Ingilizce dil verisi programin kendi 'tessdata' klasorunden okunur,
boylece Tesseract kurulumunda dil secmeye gerek kalmaz.
"""
import os
import shutil

from .cekirdek import fitz, pdf_ac, kaydet, PdfProHata

PROGRAM_KLASORU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YEREL_TESSDATA = os.path.join(PROGRAM_KLASORU, "tessdata")

_TESS_ADAYLARI = [
    os.path.join(PROGRAM_KLASORU, "Tesseract-OCR", "tesseract.exe"),
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
]


def tesseract_bul():
    """tesseract calistirilabilir yolunu dondurur, yoksa None."""
    yol = shutil.which("tesseract")
    if yol:
        return yol
    for aday in _TESS_ADAYLARI:
        if aday and os.path.isfile(aday):
            return aday
    return None


def _ascii_mi(yol):
    try:
        yol.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _guvenli_klasor():
    """Tesseract Windows'ta Turkce karakterli (s, i, g...) yollari acamaz.
    Program klasoru boyleyse ASCII bir calisma klasoru dondurur."""
    adaylar = [os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "PDFPRO"),
               os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "PDFPRO"),
               r"C:\PDFPRO"]
    for a in adaylar:
        if not _ascii_mi(a):
            continue
        try:
            os.makedirs(a, exist_ok=True)
            deneme = os.path.join(a, ".yazma_testi")
            with open(deneme, "w") as f:
                f.write("1")
            os.remove(deneme)
            return a
        except Exception:
            continue
    return None


def _tessdata_hazirla():
    """Dil dosyalarinin bulundugu (ASCII) klasoru dondurur."""
    if not os.path.isdir(YEREL_TESSDATA):
        return None
    if _ascii_mi(YEREL_TESSDATA):
        return YEREL_TESSDATA
    kok = _guvenli_klasor()
    if not kok:
        return YEREL_TESSDATA
    hedef = os.path.join(kok, "tessdata")
    for dizin, _, dosyalar in os.walk(YEREL_TESSDATA):
        alt = os.path.relpath(dizin, YEREL_TESSDATA)
        hd = os.path.normpath(os.path.join(hedef, alt))
        os.makedirs(hd, exist_ok=True)
        for ad in dosyalar:
            k, h = os.path.join(dizin, ad), os.path.join(hd, ad)
            if not os.path.isfile(h) or os.path.getsize(h) != os.path.getsize(k):
                shutil.copy2(k, h)
    return hedef


def _hazirla():
    try:
        import pytesseract
    except ImportError:
        raise PdfProHata("OCR modülü (pytesseract) kurulu değil.\nKURULUM.bat dosyasını tekrar çalıştırın.")
    yol = tesseract_bul()
    if not yol:
        raise PdfProHata("Tesseract OCR programı bulunamadı.\n\n"
                         "KURULUM.bat dosyasını tekrar çalıştırın; Tesseract'ı otomatik kurar.")
    pytesseract.pytesseract.tesseract_cmd = yol
    td = _tessdata_hazirla()
    if td:
        os.environ["TESSDATA_PREFIX"] = td
    # gecici dosyalar da Turkce karakterli kullanici klasorune (Temp) dusmesin
    import tempfile
    if not _ascii_mi(tempfile.gettempdir()):
        kok = _guvenli_klasor()
        if kok:
            tmp = os.path.join(kok, "tmp")
            os.makedirs(tmp, exist_ok=True)
            tempfile.tempdir = tmp
    return pytesseract


SON_HATA = ""


def mevcut_diller():
    global SON_HATA
    try:
        pyt = _hazirla()
        return sorted(set(pyt.get_languages(config="")) - {"osd"})
    except Exception as e:
        SON_HATA = str(e)
        return []


def ocr_durumu():
    """(hazir_mi, aciklama)"""
    if not tesseract_bul():
        return False, "OCR kapalı (Tesseract yok)"
    diller = mevcut_diller()
    if "tur" in diller:
        return True, "OCR hazır (Türkçe + İngilizce)"
    if diller:
        return True, "OCR hazır (" + ", ".join(diller) + ")"
    try:
        from .arayuz import hata_kaydet
        hata_kaydet(f"OCR dil kontrolu: tesseract={tesseract_bul()} "
                    f"TESSDATA_PREFIX={os.environ.get('TESSDATA_PREFIX')} hata={SON_HATA}")
    except Exception:
        pass
    return False, "OCR dil dosyası yok"


def _sayfa_goruntu(page, dpi):
    from PIL import Image
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def sayfa_metin_var_mi(page, esik=25):
    return len(page.get_text("text").strip()) >= esik


def aranabilir_pdf(yol, cikti, dil="tur+eng", dpi=300, sadece_taranmis=True, ilerleme=None, iptal=None):
    """Taranmis PDF'i, gorunumu ayni kalan ama metni secilip aranabilen PDF'e cevirir.
    sadece_taranmis=True ise zaten metni olan sayfalara dokunmaz."""
    pyt = _hazirla()
    kaynak = pdf_ac(yol)
    hedef = fitz.open()
    n = kaynak.page_count
    islenen = 0
    for i in range(n):
        if iptal and iptal():
            raise PdfProHata("İşlem iptal edildi.")
        page = kaynak[i]
        if ilerleme:
            ilerleme(i, n, f"Sayfa {i + 1}/{n} okunuyor")
        if sadece_taranmis and sayfa_metin_var_mi(page):
            hedef.insert_pdf(kaynak, from_page=i, to_page=i)
            continue
        img = _sayfa_goruntu(page, dpi)
        pdf_bayt = pyt.image_to_pdf_or_hocr(img, lang=dil, extension="pdf")
        tek = fitz.open("pdf", pdf_bayt)
        # tesseract sayfasini orijinal sayfa olcusune getir
        yeni = hedef.new_page(width=page.rect.width, height=page.rect.height)
        yeni.show_pdf_page(yeni.rect, tek, 0)
        tek.close()
        islenen += 1
    if ilerleme:
        ilerleme(n, n, "Kaydediliyor")
    kaydet(hedef, cikti)
    hedef.close()
    kaynak.close()
    return cikti, islenen


def metin_cikar(yol, dil="tur+eng", dpi=300, ocr_kullan=True, ilerleme=None, iptal=None):
    """Tum sayfalarin metnini dondurur. Metni olmayan sayfalar OCR ile okunur."""
    kaynak = pdf_ac(yol)
    pyt = None
    parcalar = []
    n = kaynak.page_count
    for i in range(n):
        if iptal and iptal():
            raise PdfProHata("İşlem iptal edildi.")
        if ilerleme:
            ilerleme(i, n, f"Sayfa {i + 1}/{n}")
        page = kaynak[i]
        metin = page.get_text("text", sort=True).strip()
        if len(metin) < 25 and ocr_kullan:
            if pyt is None:
                pyt = _hazirla()
            metin = pyt.image_to_string(_sayfa_goruntu(page, dpi), lang=dil).strip()
        parcalar.append(f"========== Sayfa {i + 1} ==========\n{metin}\n")
    kaynak.close()
    return "\n".join(parcalar)


def resim_metni(resim_yolu, dil="tur+eng"):
    from PIL import Image
    pyt = _hazirla()
    return pyt.image_to_string(Image.open(resim_yolu), lang=dil)
