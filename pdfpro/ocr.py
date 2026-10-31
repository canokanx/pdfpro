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
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tesseract", "tesseract.exe"),
    os.path.join(PROGRAM_KLASORU, "Tesseract-OCR", "tesseract.exe"),
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
]


def tesseract_bul():
    """tesseract calistirilabilir yolunu dondurur, yoksa None. Kurulumla gelen (program klasorundeki) once."""
    if os.path.isfile(_TESS_ADAYLARI[0]):
        return _TESS_ADAYLARI[0]
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


def _hazirla(hizli=False):
    """pytesseract'i hazirlar. hizli=True: 'hizli' (fast) dil modelleri, yoksa en dogru (best) modeller."""
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
        alt = os.path.join(td, "hizli")
        os.environ["TESSDATA_PREFIX"] = alt if (hizli and os.path.isfile(os.path.join(alt, "tur.traineddata"))) else td
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


# ================================================================== goruntu iyilestirme
def _cv():
    try:
        import cv2
        import numpy as np
        return cv2, np
    except Exception:
        return None, None


class OnIsleme:
    """Okumadan once: sayfa yonu (90/180/270), egim duzeltme, golge / soluk zemin temizligi.
    geri(x, y): islenmis resimdeki noktayi orijinal resimdeki yerine cevirir."""

    def __init__(self, img, pyt=None, yon_bul=True, iyilestir=True):
        self.orj_boyut = img.size
        self.notlar = []
        self.k = 0                 # np.rot90 sayisi
        self.M_ters = None         # egim duzeltmenin tersi (2x3)
        cv2, np = _cv()
        if not iyilestir or cv2 is None:
            self.resim = img.convert("L")
            return
        gri = np.asarray(img.convert("L"))
        # 0) golge / soluk zemin (yon ve egim bulmayi da kolaylastirir)
        gri = self._zemin(gri)
        # 1) yon (ters / yan sayfa)
        if yon_bul and pyt is not None:
            k = self._yon(gri, pyt)
            if k:
                gri = np.ascontiguousarray(np.rot90(gri, k))
                self.k = k
                self.notlar.append(f"sayfa {k * 90}° çevrildi")
        self.ara_boyut = (gri.shape[1], gri.shape[0])
        # 2) egim
        aci = self._egim(gri)
        if abs(aci) >= 0.25:
            h, w = gri.shape
            M = cv2.getRotationMatrix2D((w / 2, h / 2), aci, 1.0)
            cos, sin = abs(M[0, 0]), abs(M[0, 1])
            yw, yh = int(h * sin + w * cos), int(h * cos + w * sin)
            M[0, 2] += yw / 2 - w / 2
            M[1, 2] += yh / 2 - h / 2
            gri = cv2.warpAffine(gri, M, (yw, yh), flags=cv2.INTER_CUBIC, borderValue=255)
            self.M_ters = cv2.invertAffineTransform(M)
            self.notlar.append(f"eğim {aci:+.1f}° düzeltildi")
        from PIL import Image
        self.resim = Image.fromarray(gri)

    # --- adimlar
    @staticmethod
    def _yon(gri, pyt):
        import re
        cv2, np = _cv()
        h, w = gri.shape
        o = min(1.0, 2600.0 / max(h, w))
        kucuk = cv2.resize(gri, (int(w * o), int(h * o)), interpolation=cv2.INTER_AREA) if o < 1 else gri
        onceki = os.environ.get("TESSDATA_PREFIX")
        try:
            from PIL import Image
            if onceki and os.path.basename(onceki.rstrip("/\\")) == "hizli":
                os.environ["TESSDATA_PREFIX"] = os.path.dirname(onceki.rstrip("/\\"))   # osd ana klasorde
            cikti = pyt.image_to_osd(Image.fromarray(kucuk), config="--psm 0")
        except Exception:
            return OnIsleme._yon_yedek(kucuk, pyt)
        finally:
            if onceki is not None:
                os.environ["TESSDATA_PREFIX"] = onceki
        aci = re.search(r"Rotate:\s*(\d+)", cikti)
        guven = re.search(r"Orientation confidence:\s*([\d.]+)", cikti)
        if not aci or not guven or float(guven.group(1)) < 2.0:
            return OnIsleme._yon_yedek(kucuk, pyt)
        derece = int(aci.group(1)) % 360
        # Tesseract "Rotate: 90" = saat yonunde 90 cevir; np.rot90 saat yonunun tersine
        return {90: 3, 180: 2, 270: 1}.get(derece, 0)

    @staticmethod
    def _yon_yedek(gri, pyt):
        """Az yazili sayfada OSD karar veremezse: satirlar dikey mi? Oyleyse 90 / 270 icin
        hangisinde daha iyi okunduguna bakilir."""
        cv2, np = _cv()
        try:
            h, w = gri.shape
            o = min(1.0, 1200.0 / max(h, w))
            k = cv2.resize(gri, (int(w * o), int(h * o)), interpolation=cv2.INTER_AREA)
            _, ikili = cv2.threshold(k, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            # yatay / dikey yazi: harfleri satir yonunde birlestirip uzun parcalarin yonune bak
            yatay = cv2.morphologyEx(ikili, cv2.MORPH_CLOSE, np.ones((1, 25), np.uint8))
            dikey = cv2.morphologyEx(ikili, cv2.MORPH_CLOSE, np.ones((25, 1), np.uint8))
            ry = cv2.morphologyEx(yatay, cv2.MORPH_OPEN, np.ones((1, 60), np.uint8)).sum()
            rd = cv2.morphologyEx(dikey, cv2.MORPH_OPEN, np.ones((60, 1), np.uint8)).sum()
            if rd <= ry * 1.5:
                return 0
            from PIL import Image
            en, en_guven = 0, -1.0
            for kk in (1, 3):
                r = np.ascontiguousarray(np.rot90(gri, kk))
                d = pyt.image_to_data(Image.fromarray(r), config="--oem 1 --psm 3", output_type=pyt.Output.DICT)
                g = [float(c) for c, t in zip(d["conf"], d["text"]) if (t or "").strip() and float(c) >= 0]
                ort = sum(g) / len(g) if len(g) >= 3 else 0
                if ort > en_guven:
                    en, en_guven = kk, ort
            return en if en_guven >= 40 else 0
        except Exception:
            return 0

    @staticmethod
    def _egim(gri):
        cv2, np = _cv()
        h, w = gri.shape
        o = min(1.0, 1000.0 / max(h, w))
        k = cv2.resize(gri, (int(w * o), int(h * o)), interpolation=cv2.INTER_AREA)
        _, ikili = cv2.threshold(k, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        if ikili.mean() < 1.0:          # neredeyse bos sayfa
            return 0.0
        kh, kw = ikili.shape
        merkez = (kw / 2, kh / 2)

        def puan(a):
            M = cv2.getRotationMatrix2D(merkez, a, 1.0)
            r = cv2.warpAffine(ikili, M, (kw, kh), flags=cv2.INTER_NEAREST, borderValue=0)
            satir = r.sum(axis=1, dtype=np.float64)
            return float(np.var(satir))
        en, en_puan = 0.0, puan(0.0)
        for a in np.arange(-8.0, 8.01, 0.5):
            p = puan(float(a))
            if p > en_puan * 1.0005:
                en, en_puan = float(a), p
        for a in np.arange(en - 0.5, en + 0.51, 0.1):
            p = puan(float(a))
            if p > en_puan:
                en, en_puan = float(a), p
        return round(en, 2)

    @staticmethod
    def _zemin(gri):
        cv2, np = _cv()
        h, w = gri.shape
        # zemin tahmini: yazilari "eritecek" kadar genis bir pencereyle (yazi zemine karismasin, hale olusmasin)
        o = min(1.0, 1200.0 / max(h, w))
        kucuk = cv2.resize(gri, (max(1, int(w * o)), max(1, int(h * o))), interpolation=cv2.INTER_AREA)
        cekirdek = max(9, (min(kucuk.shape) // 45) | 1)
        zemin = cv2.medianBlur(cv2.dilate(kucuk, np.ones((cekirdek, cekirdek), np.uint8)), (cekirdek * 2) | 1)
        zemin = cv2.resize(zemin, (w, h), interpolation=cv2.INTER_LINEAR)
        p5, p95 = np.percentile(zemin, (5, 95))
        if not (p95 - p5 < 30 and np.median(zemin) > 200):
            gri = 255 - cv2.absdiff(gri, zemin)          # golge / renkli zemin temizligi
        # soluk yazi: koyu tonlari tam siyaha yay
        alt, ust = np.percentile(gri, (0.5, 99.5))
        if ust - alt > 10 and (alt > 40 or ust < 230):
            gri = np.clip((gri.astype(np.float32) - alt) * 255.0 / (ust - alt), 0, 255).astype(np.uint8)
        return gri


def _geri_rot90(x, y, k, orj_w, orj_h):
    """np.rot90(a, k) uygulanmis resimdeki (x,y) -> orijinal resimdeki (x,y)."""
    k %= 4
    if k == 0:
        return x, y
    if k == 1:          # saat yonunun tersine 90
        return orj_w - 1 - y, x
    if k == 2:
        return orj_w - 1 - x, orj_h - 1 - y
    return y, orj_h - 1 - x


def _kelimeler(pyt, on, dil, psm=3):
    """Islenmis resimden kelimeler: [(metin, (x0,y0,x1,y1), guven, satir_anahtari)]
    Koordinatlar 'duz' cercevede: egim geri alinmis, ama sayfa yonu (on.k) duzeltilmis haliyle
    (yazi bu cercevede hep yataydir). metin_katmani_ekle() bunu sayfaya cevirir."""
    d = pyt.image_to_data(on.resim, lang=dil, config=f"--oem 1 --psm {psm}", output_type=pyt.Output.DICT)
    sonuc = []
    for i, t in enumerate(d["text"]):
        t = (t or "").strip()
        try:
            guven = float(d["conf"][i])
        except (TypeError, ValueError):
            guven = -1
        if not t or guven < 0:
            continue
        x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
        koseler = []
        for px, py in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)):
            if on.M_ters is not None:
                m = on.M_ters
                px, py = m[0, 0] * px + m[0, 1] * py + m[0, 2], m[1, 0] * px + m[1, 1] * py + m[1, 2]
            koseler.append((px, py))
        xs, ys = [c[0] for c in koseler], [c[1] for c in koseler]
        sonuc.append((t, (min(xs), min(ys), max(xs), max(ys)), guven,
                      (d["block_num"][i], d["par_num"][i], d["line_num"][i])))
    return sonuc


def _metin_fontu():
    for ad in ("DejaVuSans.ttf", "Carlito-Regular.ttf"):
        y = os.path.join(PROGRAM_KLASORU, "fonts", ad)
        if os.path.isfile(y):
            try:
                return fitz.Font(fontfile=y)
            except Exception:
                pass
    return fitz.Font("helv")


def _metin_fontu_yolu():
    for ad in ("DejaVuSans.ttf", "Carlito-Regular.ttf"):
        y = os.path.join(PROGRAM_KLASORU, "fonts", ad)
        if os.path.isfile(y):
            return y
    return None


def metin_katmani_ekle(page, kelimeler, olcek, k=0):
    """Gorunmez (secilebilir / aranabilir) yazi katmani. kelimeler: _kelimeler() ciktisi (piksel);
    olcek = piksel / punto; k = sayfa yonu duzeltmesi (OnIsleme.k): yazi sayfada yan / ters ise
    katman da ayni yonde yazilir."""
    from . import duzenle as Z
    if not kelimeler:
        return 0
    Z.sayfa_hazirla(page)
    font = _metin_fontu()
    W, H = page.rect.width, page.rect.height
    k %= 4
    tw = fitz.TextWriter(page.rect) if k == 0 else None
    yol = _metin_fontu_yolu()
    n = 0
    for metin, (x0, y0, x1, y1), _g, _s in kelimeler:
        r = fitz.Rect(x0 / olcek, y0 / olcek, x1 / olcek, y1 / olcek)      # 'duz' cercevede
        if r.is_empty or r.width < 0.5 or r.height < 0.5:
            continue
        boy = r.height * 0.85
        uzun = font.text_length(metin, boy)
        if uzun > 0:
            boy = max(r.height * 0.4, min(r.height * 1.3, boy * r.width / uzun))
        bx, by = r.x0, r.y1 - r.height * 0.18                              # taban cizgisi baslangici
        try:
            metin_ = metin + " "                 # kopyalanan / aranan yazida kelimeler bitisik olmasin
            if k == 0:
                tw.append(fitz.Point(bx, by), metin_, font=font, fontsize=boy)
            else:
                nokta, aci = {1: ((W - by, bx), 270), 2: ((W - bx, H - by), 180), 3: ((by, H - bx), 90)}[k]
                page.insert_text(nokta, metin_, fontsize=boy, rotate=aci, render_mode=3,
                                 fontname="PPOCR", fontfile=yol) if yol else \
                    page.insert_text(nokta, metin_, fontsize=boy, rotate=aci, render_mode=3)
            n += 1
        except Exception:
            continue
    if n and tw is not None:
        Z.tw_yaz(page, tw, render_mode=3)
    elif n:
        Z.bosluk_duzelt(page)
    return n


# ================================================================== yapay zeka ile okuma
def _yz_sayfa_resmi(page, dpi=200):
    import io
    img = _sayfa_goruntu(page, dpi)
    if max(img.size) > 2400:
        o = 2400 / max(img.size)
        img = img.resize((int(img.width * o), int(img.height * o)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue(), img.size


def yz_satirlar(yz_ayar, page):
    """Gemini ile sayfadaki satirlar ve yerleri. [(metin, Rect sayfa koordinati)]"""
    from . import yapay_zeka as YZ
    jpg, _ = _yz_sayfa_resmi(page)
    istem = ("Bu bir belge sayfasının görüntüsü. Sayfadaki TÜM yazıyı satır satır oku (el yazısı, kaşe ve "
             "damga yazıları dahil). Türkçe karakterleri (ç ğ ı İ ö ş ü) doğru yaz, uydurma. Her satır için "
             "JSON nesnesi ver: {\"text\": satır metni, \"box_2d\": [ymin, xmin, ymax, xmax]} (0-1000 arası, "
             "sayfaya göre). Sadece JSON listesi döndür.")
    yanit = YZ.sor_resimle(yz_ayar, istem, jpg, json_cikti=True)
    import json
    try:
        veri = json.loads(yanit)
    except Exception:
        import re
        m = re.search(r"\[.*\]", yanit, re.S)
        veri = json.loads(m.group(0)) if m else []
    r = page.rect
    sonuc = []
    for v in veri if isinstance(veri, list) else []:
        try:
            t = str(v.get("text", "")).strip()
            y0, x0, y1, x1 = (float(a) for a in v.get("box_2d"))
        except Exception:
            continue
        if t:
            sonuc.append((t, fitz.Rect(r.x0 + x0 / 1000 * r.width, r.y0 + y0 / 1000 * r.height,
                                       r.x0 + x1 / 1000 * r.width, r.y0 + y1 / 1000 * r.height)))
    return sonuc


def yz_metin(yz_ayar, page):
    """Gemini ile sayfa metni (tablolar Markdown)."""
    from . import yapay_zeka as YZ
    jpg, _ = _yz_sayfa_resmi(page)
    istem = ("Bu belge sayfasındaki tüm yazıyı eksiksiz ve aynen yaz (el yazısı, kaşe ve damga yazıları dahil). "
             "Türkçe karakterleri doğru yaz, emin olmadığın yeri [?] ile işaretle, uydurma. Tabloları Markdown "
             "tablo olarak ver. Açıklama ekleme, sadece sayfadaki metni döndür.")
    return YZ.sor_resimle(yz_ayar, istem, jpg)


def _yz_katmani(page, satirlar):
    from . import duzenle as Z
    Z.sayfa_hazirla(page)
    font = _metin_fontu()
    tw = fitz.TextWriter(page.rect)
    n = 0
    for metin, r in satirlar:
        if r.is_empty or r.width < 1 or r.height < 1:
            continue
        boy = min(r.height * 0.8, 40)
        uzun = font.text_length(metin, boy)
        if uzun > 0:
            boy = max(2, min(boy, boy * r.width / uzun))
        try:
            tw.append(fitz.Point(r.x0, r.y1 - r.height * 0.2), metin, font=font, fontsize=boy)
            n += 1
        except Exception:
            continue
    if n:
        Z.tw_yaz(page, tw, render_mode=3)
    return n


# ================================================================== PDF'i aranabilir yapma
MOTORLAR = ("tesseract", "otomatik", "yz")


def aranabilir_pdf(yol, cikti, dil="tur+eng", dpi=300, sadece_taranmis=True, ilerleme=None, iptal=None,
                   iyilestir=True, hizli=False, motor="tesseract", yz_ayar=None, yz_esik=70):
    """Taranmis sayfalara gorunmez yazi katmani ekler: gorunum hic degismez (resim yeniden
    sikistirilmaz), yazi secilip aranabilir ve 'Yazi Duzelt' ile duzeltilebilir.
    motor: tesseract | otomatik (zayif okunan sayfalar yapay zekaya) | yz (hepsi yapay zekayla)
    Dondurur: (cikti, islenen_sayfa, notlar)"""
    pyt = _hazirla(hizli) if motor != "yz" else None
    doc = pdf_ac(yol)
    n = doc.page_count
    islenen, notlar, yz_sayfalar = 0, [], []
    for i in range(n):
        if iptal and iptal():
            raise PdfProHata("İşlem iptal edildi.")
        page = doc[i]
        if sadece_taranmis and sayfa_metin_var_mi(page):
            continue
        if ilerleme:
            ilerleme(i, n, f"Sayfa {i + 1}/{n} okunuyor")
        if motor == "yz":
            satirlar = yz_satirlar(yz_ayar, page)
            if _yz_katmani(page, satirlar):
                islenen += 1
                yz_sayfalar.append(i + 1)
            continue
        img = _sayfa_goruntu(page, dpi)
        on = OnIsleme(img, pyt, yon_bul=True, iyilestir=iyilestir)
        kel = _kelimeler(pyt, on, dil)
        guven = sum(k[2] for k in kel) / len(kel) if kel else 0
        if motor == "otomatik" and yz_ayar and (len(kel) < 5 or guven < yz_esik):
            try:
                if ilerleme:
                    ilerleme(i, n, f"Sayfa {i + 1}/{n}: zor sayfa, yapay zekayla okunuyor")
                satirlar = yz_satirlar(yz_ayar, page)
                if satirlar and _yz_katmani(page, satirlar):
                    islenen += 1
                    yz_sayfalar.append(i + 1)
                    continue
            except Exception as e:
                notlar.append(f"Sayfa {i + 1}: yapay zeka okuyamadı ({str(e).splitlines()[0][:80]})")
        if metin_katmani_ekle(page, kel, dpi / 72.0, on.k):
            islenen += 1
        if on.notlar:
            notlar.append(f"Sayfa {i + 1}: " + ", ".join(on.notlar))
    if yz_sayfalar:
        notlar.insert(0, "Yapay zekayla okunan sayfalar: " + ", ".join(map(str, yz_sayfalar)))
    if ilerleme:
        ilerleme(n, n, "Kaydediliyor")
    if islenen:
        try:
            doc.subset_fonts()          # gomulen yazi tipi sadece kullanilan harfler kadar yer kaplasin
        except Exception:
            pass
    kaydet(doc, cikti)
    doc.close()
    return cikti, islenen, notlar


def metin_cikar(yol, dil="tur+eng", dpi=300, ocr_kullan=True, ilerleme=None, iptal=None,
                iyilestir=True, hizli=False, motor="tesseract", yz_ayar=None, yz_esik=70):
    """Tum sayfalarin metnini dondurur. Metni olmayan sayfalar OCR (veya yapay zeka) ile okunur."""
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
            if motor == "yz":
                metin = yz_metin(yz_ayar, page).strip()
            else:
                if pyt is None:
                    pyt = _hazirla(hizli)
                on = OnIsleme(_sayfa_goruntu(page, dpi), pyt, iyilestir=iyilestir)
                d = pyt.image_to_data(on.resim, lang=dil, config="--oem 1 --psm 3", output_type=pyt.Output.DICT)
                gv = [float(c) for c, t in zip(d["conf"], d["text"]) if (t or "").strip() and float(c) >= 0]
                guven = sum(gv) / len(gv) if gv else 0
                if motor == "otomatik" and yz_ayar and (len(gv) < 5 or guven < yz_esik):
                    try:
                        metin = "[yapay zekayla okundu]\n" + yz_metin(yz_ayar, page).strip()
                    except Exception:
                        metin = pyt.image_to_string(on.resim, lang=dil, config="--oem 1 --psm 3").strip()
                else:
                    metin = pyt.image_to_string(on.resim, lang=dil, config="--oem 1 --psm 3").strip()
        parcalar.append(f"========== Sayfa {i + 1} ==========\n{metin}\n")
    kaynak.close()
    return "\n".join(parcalar)


def ocr_gerekli_mi(yol):
    """Belgede yazisi olmayan (taranmis) sayfa var mi?"""
    try:
        with fitz.open(yol) as d:
            return any(not sayfa_metin_var_mi(p) for p in d)
    except Exception:
        return True


def resim_metni(resim_yolu, dil="tur+eng"):
    from PIL import Image
    pyt = _hazirla()
    on = OnIsleme(Image.open(resim_yolu).convert("RGB"), pyt)
    return pyt.image_to_string(on.resim, lang=dil)
