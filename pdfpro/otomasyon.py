# -*- coding: utf-8 -*-
"""
PDF PRO - Otomasyon
- Is akisi (toplu islem): kayitli adim dizisini (OCR, sikistir, filigran, sayfa no, damga, imza seti,
  antet, A4, PDF/A, sifre) bir veya cok dosyaya / bir klasore uygular.
- Belge paketi: sirali belge listesi (or. Crew List, Ship Particulars, ISPS...) -> tek PDF,
  ad sablonu (GEMI_LIMAN_TARIH) ve hedef boyut.
- Imza + kase setleri: birden cok resmi tek seferde ayri ayri tasinabilir nesne olarak koyma.
"""
import datetime
import os
import re
import shutil
import tempfile

from .cekirdek import fitz, PdfProHata, benzersiz_yol, sayfa_araligi_coz
from . import cekirdek as C

# adim turu -> (gorunen ad, varsayilan ayar)
ADIMLAR = {
    "ocr": ("OCR - aranabilir yap", {"dil": "tur+eng"}),
    "a4": ("A4'e sığdır", {}),
    "sayfa_no": ("Sayfa numarası", {"bicim": "Sayfa {n} / {N}", "konum": "Orta alt"}),
    "filigran": ("Filigran", {"metin": "KOPYADIR", "opaklik": 0.15}),
    "damga": ("Damga", {"metin": "ASLI GİBİDİR", "renk": "Kırmızı", "sayfalar": "tümü", "konum": "Sağ üst", "tarih": True}),
    "antet": ("Antet", {"yol": "", "sayfalar": ""}),
    "imza_seti": ("İmza / kaşe seti", {"set": "", "sayfalar": "son", "konum": "Sağ alt"}),
    "sikistir": ("Sıkıştır", {"seviye": "orta", "hedef_mb": 0}),
    "pdfa": ("PDF/A (arşiv)", {}),
    "sifre": ("Şifre koy", {"sifre": ""}),
}

DAMGA_RENK = {"Kırmızı": (0.75, 0.08, 0.08), "Mavi": (0.1, 0.25, 0.7), "Yeşil": (0.1, 0.5, 0.2), "Siyah": (0, 0, 0)}

HAZIR_AKISLAR = [
    {"ad": "E-posta için hazırla (OCR + sıkıştır 5 MB)",
     "adimlar": [{"tur": "ocr", "ayar": {"dil": "tur+eng"}}, {"tur": "sikistir", "ayar": {"seviye": "orta", "hedef_mb": 5}}]},
    {"ad": "Aslı gibidir + sayfa no",
     "adimlar": [{"tur": "damga", "ayar": {"metin": "ASLI GİBİDİR", "renk": "Mavi", "sayfalar": "tümü", "konum": "Sağ üst", "tarih": True}},
                 {"tur": "sayfa_no", "ayar": {"bicim": "Sayfa {n} / {N}", "konum": "Orta alt"}}]},
    {"ad": "Taramaları düzenle (A4 + OCR + sıkıştır)",
     "adimlar": [{"tur": "a4", "ayar": {}}, {"tur": "ocr", "ayar": {"dil": "tur+eng"}},
                 {"tur": "sikistir", "ayar": {"seviye": "orta", "hedef_mb": 0}}]},
]


def adim_ozeti(adim):
    tur, a = adim["tur"], adim.get("ayar", {})
    ad = ADIMLAR.get(tur, (tur,))[0]
    if tur == "filigran":
        return f"{ad}: {a.get('metin', '')}"
    if tur == "damga":
        return f"{ad}: {a.get('metin', '')} ({a.get('sayfalar', 'tümü')})"
    if tur == "sikistir":
        return f"{ad}: {a.get('seviye', 'orta')}" + (f", en fazla {a['hedef_mb']:g} MB" if a.get("hedef_mb") else "")
    if tur == "antet":
        return f"{ad}: {os.path.basename(a.get('yol', '')) or '(seçilmedi)'}"
    if tur == "imza_seti":
        return f"{ad}: {a.get('set', '')} ({a.get('sayfalar', 'son')})"
    if tur == "sayfa_no":
        return f"{ad}: {a.get('bicim', '')}"
    if tur == "sifre":
        return f"{ad}: {'•' * len(a.get('sifre', ''))}"
    return ad


def _sayfalar(metin, n):
    m = (metin or "").strip().lower()
    if m in ("", "tümü", "tumu", "hepsi"):
        return list(range(n))
    if m in ("ilk",):
        return [0]
    return sayfa_araligi_coz(m, n)


# ------------------------------------------------------------------ imza seti yerlestirme
def set_rectleri(sayfa_rect, ogeler, konum="Sağ alt"):
    """Set ogelerini (yan yana) sayfadaki kutularina yerlestirir. ogeler: [{'yol','genislik_mm'}] + (w,h)"""
    from .damga import konum_hesapla, MM
    olculer = []
    for o in ogeler:
        g = o.get("genislik_mm", 40) * MM
        olculer.append((g, g * o["_h"] / o["_w"]))
    aralik = 6 * MM
    toplam_g = sum(g for g, _ in olculer) + aralik * (len(olculer) - 1)
    yuk = max(h for _, h in olculer)
    kutu = konum_hesapla(sayfa_rect, konum, toplam_g, yuk)
    rectler, x = [], kutu.x0
    for g, h in olculer:
        rectler.append(fitz.Rect(x, kutu.y1 - h, x + g, kutu.y1))
        x += g + aralik
    return rectler


def set_hazirla(set_):
    """Set ogelerinin resimlerini hazirlar: [{'png', '_w', '_h', ...}]"""
    from .damga import resim_hazirla
    ogeler = []
    for o in set_.get("ogeler", []):
        if not os.path.isfile(o.get("yol", "")):
            raise PdfProHata(f"Set resmi bulunamadı:\n{o.get('yol')}")
        w, h, png = resim_hazirla(o["yol"], o.get("opaklik", 1.0), o.get("beyazi_sil", True))
        ogeler.append(dict(o, png=png, _w=w, _h=h))
    if not ogeler:
        raise PdfProHata("Set boş.")
    return ogeler


# ------------------------------------------------------------------ is akisi
def akisi_uygula(adimlar, girdi, cikti, setler=None, ilerleme=None, iptal=None):
    """Adimlari sirayla tek dosyaya uygular."""
    from . import damga as M
    from . import araclar as AR
    from . import donustur as D
    from . import ocr as O
    from . import duzenle as Z
    setler = setler or {}
    gecici = tempfile.mkdtemp(prefix="pdfpro_akis_")
    try:
        cur = os.path.join(gecici, "0.pdf")
        shutil.copyfile(girdi, cur)
        notlar = []
        for k, adim in enumerate(adimlar):
            if iptal and iptal():
                raise PdfProHata("İptal edildi.")
            tur, a = adim["tur"], adim.get("ayar", {})
            if ilerleme:
                ilerleme(k, len(adimlar), ADIMLAR.get(tur, (tur,))[0])
            sonraki = os.path.join(gecici, f"{k + 1}.pdf")
            if tur == "ocr":
                if not O.ocr_durumu()[0]:
                    notlar.append("OCR atlandı (Tesseract kurulu değil)")
                    continue
                O.aranabilir_pdf(cur, sonraki, a.get("dil", "tur+eng"), 300, True, None, iptal)
            elif tur == "sikistir":
                hk = int(float(a.get("hedef_mb") or 0) * 1024) or None
                C.sikistir(cur, sonraki, a.get("seviye", "orta"), hk, bool(a.get("gri")), None, iptal)
            elif tur == "filigran":
                M.filigran_ekle(cur, sonraki, metin=a.get("metin", "KOPYADIR"), opaklik=float(a.get("opaklik", 0.15)))
            elif tur == "sayfa_no":
                M.sayfa_no_ekle(cur, sonraki, bicim=a.get("bicim", "Sayfa {n} / {N}"), konum=a.get("konum", "Orta alt"))
            elif tur == "antet":
                if not os.path.isfile(a.get("yol", "")):
                    raise PdfProHata("İş akışındaki antet dosyası bulunamadı.")
                M.antet_ekle(cur, sonraki, a["yol"], sayfalar=a.get("sayfalar", ""))
            elif tur == "pdfa":
                _, n_ = D.pdf_a(cur, sonraki)
                notlar += n_ or []
            elif tur == "sifre":
                C.sifre_koy(cur, a.get("sifre", ""), sonraki)
            elif tur in ("damga", "a4", "imza_seti"):
                doc = fitz.open(cur)
                if tur == "a4":
                    AR.a4e_sigdir(doc, list(range(doc.page_count)))
                elif tur == "damga":
                    renk = DAMGA_RENK.get(a.get("renk", "Kırmızı"), (0.75, 0.08, 0.08))
                    f = Z.font_al(False, True, False)
                    boy = float(a.get("boyut", 16))
                    gen = f.text_length(a.get("metin", ""), boy) + boy * 1.2
                    yuk = boy * (2.4 if a.get("tarih", True) else 1.75)
                    for s in _sayfalar(a.get("sayfalar"), doc.page_count):
                        page = doc[s]
                        Z.sayfa_hazirla(page)
                        r = M.konum_hesapla(page.rect, a.get("konum", "Sağ üst"), gen, yuk)
                        AR.damga(page, ((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2), a.get("metin", ""), renk, boy,
                                 a.get("tarih", True))
                else:
                    set_ = setler.get(a.get("set", ""))
                    if not set_:
                        raise PdfProHata(f"'{a.get('set')}' adlı imza/kaşe seti bulunamadı.")
                    ogeler = set_hazirla(set_)
                    for s in _sayfalar(a.get("sayfalar", "son"), doc.page_count):
                        page = doc[s]
                        Z.sayfa_hazirla(page)
                        for o, r in zip(ogeler, set_rectleri(page.rect, ogeler, a.get("konum", "Sağ alt"))):
                            page.insert_image(r, stream=o["png"], overlay=True)
                doc.save(sonraki, garbage=3, deflate=True)
                doc.close()
            else:
                continue
            cur = sonraki
        os.makedirs(os.path.dirname(os.path.abspath(cikti)), exist_ok=True)
        shutil.copyfile(cur, cikti)
        return cikti, notlar
    finally:
        shutil.rmtree(gecici, ignore_errors=True)


def dosyalari_topla(kaynaklar, alt_klasorler=False):
    """Dosya ve klasor listesinden PDF dosyalari."""
    sonuc = []
    for k in kaynaklar:
        if os.path.isdir(k):
            if alt_klasorler:
                for kok, _, adlar in os.walk(k):
                    sonuc += [os.path.join(kok, a) for a in sorted(adlar) if a.lower().endswith(".pdf")]
            else:
                sonuc += [os.path.join(k, a) for a in sorted(os.listdir(k)) if a.lower().endswith(".pdf")]
        elif os.path.isfile(k) and k.lower().endswith(".pdf"):
            sonuc.append(k)
    return sonuc


def ad_uret(sablon, kaynak_yol=None, sayac=1, alanlar=None):
    """{ad} {tarih} {saat} {sayac} {GEMI} gibi alanlari doldurur, gecersiz karakterleri temizler."""
    simdi = datetime.datetime.now()
    deg = {"ad": os.path.splitext(os.path.basename(kaynak_yol))[0] if kaynak_yol else "belge",
           "tarih": simdi.strftime("%d.%m.%Y"), "tarih2": simdi.strftime("%Y%m%d"),
           "saat": simdi.strftime("%H%M"), "sayac": f"{sayac:02d}"}
    for k, v in (alanlar or {}).items():
        deg[k] = v
        deg[k.lower()] = v
        deg[k.upper()] = v

    def yer(m):
        return str(deg.get(m.group(1), m.group(0)))
    ad = re.sub(r"\{([^{}]+)\}", yer, sablon or "{ad}_islenmis")
    ad = re.sub(r'[\\/:*?"<>|]+', "_", ad).strip(" .") or "belge"
    return ad if ad.lower().endswith(".pdf") else ad + ".pdf"


def toplu_isle(adimlar, dosyalar, cikti_klasoru=None, sablon="{ad}_islenmis", ustune_yaz=False,
               setler=None, ilerleme=None, iptal=None):
    """Is akisini dosya listesine uygular. Dondurur: (tamam_listesi, hata_listesi, notlar)"""
    from . import yedek
    tamam, hatalar, notlar = [], [], []
    for i, y in enumerate(dosyalar):
        if iptal and iptal():
            break
        if ilerleme:
            ilerleme(i, len(dosyalar), os.path.basename(y))
        try:
            if ustune_yaz:
                hedef = y
                yedek.yedekle(y)
            else:
                kl = cikti_klasoru or os.path.dirname(y)
                hedef = benzersiz_yol(os.path.join(kl, ad_uret(sablon, y, i + 1)))
            gecici = hedef + ".pdfpro_tmp.pdf"
            _, n = akisi_uygula(adimlar, y, gecici, setler, None, iptal)
            os.replace(gecici, hedef)
            tamam.append(hedef)
            notlar += [f"{os.path.basename(y)}: {x}" for x in n]
        except Exception as e:
            hatalar.append(f"{os.path.basename(y)}: {e}")
            try:
                os.remove(hedef + ".pdfpro_tmp.pdf")
            except Exception:
                pass
    return tamam, hatalar, notlar


# ------------------------------------------------------------------ belge paketi
HAZIR_PAKETLER = [
    {"ad": "Gemi geliş evrakı", "sablon": "{GEMI}_GELIS_{tarih}", "hedef_mb": 10,
     "yuvalar": ["Arrival Notice / Geliş Bildirimi", "Crew List", "Passenger List", "Ship Particulars",
                 "Last 10 Ports", "ISPS / Security Declaration", "Maritime Declaration of Health",
                 "Cargo Manifest", "Ship Stores Declaration"]},
    {"ad": "Personel / GBT dosyası", "sablon": "{AD}_GBT_{tarih}", "hedef_mb": 5,
     "yuvalar": ["Kimlik", "Fotoğraf", "Sabıka kaydı", "İkametgah", "Diploma", "Başvuru formu"]},
]


def paket_olustur(yuvalar, cikti, hedef_mb=0, ayrac_sayfasi=False, yer_imleri=True, ilerleme=None, iptal=None):
    """yuvalar: [{'ad': 'Crew List', 'dosyalar': [yol, ...]}] sirasiyla birlestirilir.
    Bos yuvalar atlanir. Her yuva bir yer imi (bookmark) olur. Dondurur: (cikti, sayfa, eksik_yuvalar)"""
    from .donustur import herhangi_to_pdf
    from . import duzenle as Z
    sonuc = fitz.open()
    toc, eksik = [], []
    gecici = tempfile.mkdtemp(prefix="pdfpro_paket_")
    try:
        toplam = sum(len(y.get("dosyalar", [])) for y in yuvalar) or 1
        k = 0
        for y in yuvalar:
            ds = [d for d in y.get("dosyalar", []) if os.path.isfile(d)]
            if not ds:
                eksik.append(y["ad"])
                continue
            bas = sonuc.page_count
            if ayrac_sayfasi:
                p = sonuc.new_page(width=595, height=842)
                f = Z.font_al(False, True, False)
                tw = fitz.TextWriter(p.rect)
                tw.append((60, 400), y["ad"], font=f, fontsize=24)
                tw.write_text(p, color=(0.12, 0.23, 0.37))
                Z.bosluk_duzelt(p)
            for d in ds:
                if iptal and iptal():
                    raise PdfProHata("İptal edildi.")
                if ilerleme:
                    ilerleme(k, toplam, f"{y['ad']}: {os.path.basename(d)}")
                k += 1
                if d.lower().endswith(".pdf"):
                    src = fitz.open(d)
                    if src.needs_pass:
                        raise PdfProHata(f"Şifreli dosya pakete eklenemez:\n{os.path.basename(d)}")
                else:
                    pdf = os.path.join(gecici, f"{k}.pdf")
                    herhangi_to_pdf(d, pdf)
                    src = fitz.open(pdf)
                sonuc.insert_pdf(src)
                src.close()
            if yer_imleri:
                toc.append([1, y["ad"], bas + 1])
        if sonuc.page_count == 0:
            raise PdfProHata("Pakete hiç dosya eklenmedi.")
        if yer_imleri and toc:
            sonuc.set_toc(toc)
        n = sonuc.page_count
        if hedef_mb:
            ara = os.path.join(gecici, "paket.pdf")
            sonuc.save(ara, garbage=3, deflate=True)
            sonuc.close()
            if os.path.getsize(ara) > hedef_mb * 1024 * 1024:
                if ilerleme:
                    ilerleme(toplam, toplam + 1, "Sıkıştırılıyor")
                C.sikistir(ara, cikti, "hafif", int(hedef_mb * 1024), False, None, iptal)
            else:
                shutil.copyfile(ara, cikti)
        else:
            sonuc.save(cikti, garbage=3, deflate=True)
            sonuc.close()
        return cikti, n, eksik
    finally:
        shutil.rmtree(gecici, ignore_errors=True)
