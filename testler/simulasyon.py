# -*- coding: utf-8 -*-
"""
PDF PRO - Ileride cikabilecek sorunlarin simulasyonu
Calistir:  python testler/simulasyon.py   (sonuc: her senaryo icin TAMAM / HATA)
"""
import os
import sys
import tempfile
import time
import traceback

KLASOR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KLASOR)

from pdfpro.cekirdek import fitz, PdfProHata               # noqa: E402
from pdfpro import duzenle as Z, araclar as AR, gorunum as G  # noqa: E402

TMP = tempfile.mkdtemp(prefix="pdfpro_sim_")
FONT = os.path.join(KLASOR, "fonts", "DejaVuSans.ttf")
sonuclar = []


def senaryo(ad):
    def sar(f):
        def calis():
            t = time.time()
            try:
                notu = f() or ""
                sonuclar.append((ad, "TAMAM", f"{time.time() - t:.2f}s {notu}"))
            except Exception as e:
                sonuclar.append((ad, "HATA", f"{e}\n{traceback.format_exc(limit=3)}"))
        calis.ad = ad
        return calis
    return sar


def ornek(metinler, dondur=0, kaydet=None):
    d = fitz.open()
    p = d.new_page()
    p.insert_font(fontname="dv", fontfile=FONT)
    for (x, y), t, b in metinler:
        p.insert_text((x, y), t, fontname="dv", fontsize=b)
    if dondur:
        p.set_rotation(dondur)
    if kaydet:
        d.save(kaydet)
    return d


def degistir_ve_dogrula(d, i, x, y, yeni, eski_parca):
    p = d[i]
    s = Z.satir_bul(p, x, y)
    assert s, "satir bulunamadi"
    assert eski_parca in s["metin"], f"yanlis satir: {s['metin']}"
    Z.satir_degistir(p, s, yeni)
    t = d[i].get_text()
    assert yeni.split("\n")[0] in t, f"yeni yazi yok: {t[:200]}"
    assert eski_parca not in t, "eski yazi duruyor"


# ---------------------------------------------------------------------------
@senaryo("Döndürülmüş sayfalarda yazı düzeltme (90/180/270)")
def t_dondurme():
    for aci in (90, 180, 270):
        d = ornek([((72, 100), "ESKI METIN 123", 12), ((72, 140), "DOKUNMA", 12)], dondur=aci)
        # gorunen koordinat: once duzlestir (program da tiklayinca boyle yapar)
        Z.sayfa_hazirla(d[0])
        w = [x for x in d[0].get_text("words") if x[4] == "ESKI"][0]
        degistir_ve_dogrula(d, 0, (w[0] + w[2]) / 2, (w[1] + w[3]) / 2, "YENI METIN 456", "ESKI")
        assert "DOKUNMA" in d[0].get_text()


@senaryo("Şifreli PDF açma (doğru / yanlış şifre)")
def t_sifre():
    yol = os.path.join(TMP, "sifreli.pdf")
    d = ornek([((72, 100), "GIZLI", 12)])
    d.save(yol, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="1234", owner_pw="1234")
    sorulan = iter(["yanlis", "1234"])
    b = G.Belge(yol, sifre_sor=lambda ad, n: next(sorulan))
    assert "GIZLI" in b.doc[0].get_text()
    try:
        G.Belge(yol, sifre_sor=lambda ad, n: None)
        raise AssertionError("sifresiz acildi!")
    except PdfProHata:
        pass


@senaryo("Bozuk / yarım inmiş PDF")
def t_bozuk():
    yol = os.path.join(TMP, "bozuk.pdf")
    d = ornek([((72, 100), "YARIM", 12)])
    veri = d.tobytes()
    with open(yol, "wb") as f:
        f.write(veri[: int(len(veri) * 0.7)])
    try:
        b = G.Belge(yol)
        return f"onarilarak acildi ({b.doc.page_count} sayfa)"
    except PdfProHata as e:
        return f"anlasilir hata verdi: {str(e).splitlines()[0]}"


@senaryo("Türkçe karakterli klasör ve dosya adı")
def t_turkce_yol():
    kl = os.path.join(TMP, "Gemi Şirketi Öğrenci Çalışma")
    os.makedirs(kl, exist_ok=True)
    yol = os.path.join(kl, "Ağır Yük İşlemleri.pdf")
    ornek([((72, 100), "ŞĞÜİÖÇ ışğüöç", 12)], kaydet=yol)
    b = G.Belge(yol)
    s = Z.satir_bul(b.doc[0], 100, 96)
    Z.satir_degistir(b.doc[0], s, "DÜZELTİLDİ ĞÜŞİÖÇ")
    b.kaydet()
    assert "DÜZELTİLDİ" in fitz.open(yol)[0].get_text()


@senaryo("Bağlı yazılar (ﬁ ﬂ ligatür) ve gömülü fontta olmayan harf")
def t_ligatur():
    d = ornek([((72, 100), "office ﬁle ﬂow", 12)])
    s = Z.satir_bul(d[0], 100, 96)
    assert s and "ﬁ" not in s["metin"], f"ligatur cozulmedi: {s['metin']}"
    Z.satir_degistir(d[0], s, "ÇĞŞ ofis dosyası")
    assert "ÇĞŞ" in d[0].get_text()


@senaryo("Yazıyı tamamen silme (boş bırakma)")
def t_bos():
    d = ornek([((72, 100), "SILINECEK", 12), ((72, 130), "KALACAK", 12)])
    s = Z.satir_bul(d[0], 100, 96)
    Z.satir_degistir(d[0], s, "")
    t = d[0].get_text()
    assert "SILINECEK" not in t and "KALACAK" in t


@senaryo("Çok uzun yeni yazı (tablo hücresinde satıra bölünme)")
def t_uzun():
    d = fitz.open()
    p = d.new_page()
    p.draw_rect(fitz.Rect(60, 80, 300, 160), color=(0, 0, 0))
    p.draw_line((180, 80), (180, 160))
    p.insert_font(fontname="dv", fontfile=FONT)
    p.insert_text((185, 100), "KISA", fontname="dv", fontsize=10)
    p.insert_text((185, 112), "IKINCI", fontname="dv", fontsize=10)
    s = Z.satir_bul(p, 195, 97)
    Z.satir_degistir(p, s, "COK UZUN BIR ACENTE ADI DENIZCILIK LIMITED SIRKETI")
    for w in p.get_text("words"):
        if w[4] in ("COK", "UZUN", "SIRKETI", "LIMITED"):
            assert w[2] <= 301, f"hucreden tasti: {w}"


@senaryo("Kırpılmış (cropbox) sayfada konum doğruluğu")
def t_crop():
    d = ornek([((150, 300), "HEDEF YAZI", 14)])
    d[0].set_cropbox(fitz.Rect(100, 200, 500, 600))
    w = [x for x in d[0].get_text("words") if x[4] == "HEDEF"][0]
    degistir_ve_dogrula(d, 0, (w[0] + w[2]) / 2, (w[1] + w[3]) / 2, "YENI YAZI", "HEDEF")
    w2 = [x for x in d[0].get_text("words") if x[4] == "YENI"][0]
    assert abs(w2[0] - w[0]) < 1.5 and abs(w2[3] - w[3]) < 2.5, f"kaydi: {w[:4]} -> {w2[:4]}"


@senaryo("Not / vurgu (annotation) olan sayfada düzeltme")
def t_annot():
    d = ornek([((72, 100), "NOTLU SAYFA", 12)])
    d[0].add_text_annot((300, 100), "not")
    s = Z.satir_bul(d[0], 100, 96)
    Z.satir_degistir(d[0], s, "DEGISTI")
    assert len(list(d[0].annots())) == 1, "not kayboldu"


@senaryo("Geri al: 30 düzeltme + bellek sınırı")
def t_geri_al():
    d = ornek([((72, 100), "SAYI 0", 12)])
    b = G.Belge(doc=d, ad="t.pdf")
    for k in range(30):
        b.anlik()
        s = Z.satir_bul(b.doc[0], 90, 96)
        Z.satir_degistir(b.doc[0], s, f"SAYI {k + 1}")
        b.degisiklik()
    assert len(b.geri) <= G.GERI_AL_SINIRI
    for _ in range(5):
        b.geri_al()
    assert "SAYI 25" in b.doc[0].get_text(), b.doc[0].get_text()


@senaryo("Büyük belge: 400 sayfa açma + düzen hesabı")
def t_buyuk():
    yol = os.path.join(TMP, "buyuk.pdf")
    d = fitz.open()
    for i in range(400):
        p = d.new_page()
        p.insert_text((72, 72), f"Sayfa {i + 1} - Konşimento / Manifesto", fontsize=12)
    d.save(yol)
    t = time.time()
    b = G.Belge(yol)
    rects = [p.rect for p in b.doc]
    acilis = time.time() - t
    t = time.time()
    for i in range(0, 400, 40):
        b.doc[i].get_pixmap(matrix=fitz.Matrix(1.33, 1.33), alpha=False)
    cizim = (time.time() - t) / 10
    t = time.time()
    n = len(AR.ara(b.doc, "Manifesto"))
    arama = time.time() - t
    assert n == 400
    return f"acilis {acilis:.2f}s, sayfa cizimi {cizim * 1000:.0f}ms, 400 sayfada arama {arama:.2f}s ({len(rects)})"


@senaryo("Bul-değiştir (Türkçe büyük/küçük)")
def t_bul_degistir():
    d = ornek([((72, 100), "Acente: GULF AGENCY", 12), ((72, 130), "GULF AGENCY ISTANBUL", 12)])
    n = AR.bul_degistir(d, "GULF", "IRONHULL")
    t = d[0].get_text()
    assert n == 2 and "GULF" not in t and t.count("IRONHULL") == 2, t
    assert len(AR.ara(d, "ıronhull")) == 2


@senaryo("Karart: altındaki yazı gerçekten siliniyor")
def t_karart():
    d = ornek([((72, 100), "TC 12345678901", 12), ((72, 130), "AD SOYAD", 12)])
    AR.karart(d[0], fitz.Rect(70, 88, 200, 104))
    t = d[0].get_text()
    assert "12345678901" not in t and "AD SOYAD" in t


@senaryo("Form alanı doldurma")
def t_form():
    d = fitz.open()
    p = d.new_page()
    w = fitz.Widget()
    w.field_name, w.field_type, w.rect = "ad", fitz.PDF_WIDGET_TYPE_TEXT, fitz.Rect(100, 100, 300, 120)
    p.add_widget(w)
    al = AR.form_alanlari(d)
    AR.form_doldur(d, {al[0]["xref"]: "ÇAĞRI ŞİŞMAN"})
    assert AR.form_alanlari(d)[0]["deger"] == "ÇAĞRI ŞİŞMAN"


@senaryo("Resim üzerindeki yazı (OCR + inpaint), yatay ve yan yazı")
def t_resim():
    from pdfpro import resim_yazi as R
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (1200, 700), (205, 225, 245))
    dr = ImageDraw.Draw(im)
    for k in range(0, 1200, 9):
        dr.line([(k, 0), (k - 300, 700)], fill=(190, 212, 238), width=2)
    f = ImageFont.truetype(FONT, 46)
    dr.text((80, 120), "SOYADI: KARADENIZ", font=f, fill=(25, 25, 60))
    yan = Image.new("RGB", (520, 70), (205, 225, 245))
    ImageDraw.Draw(yan).text((10, 8), "GEMI: ATLAS", font=f, fill=(25, 25, 60))
    im.paste(yan.rotate(90, expand=True), (1050, 120))
    yol = os.path.join(TMP, "kart.png")
    im.save(yol)
    d = fitz.open()
    p = d.new_page(width=600, height=350)
    p.insert_image(p.rect, filename=yol)
    b = R.bul(p, 230, 80)
    assert b and "KARADEN" in b["metin"].replace(" ", ""), b and b["metin"]
    R.degistir(p, b, "AKDENIZ")
    b2 = R.bul(p, 548, 230)
    assert b2 and b2["yon_aci"] in (90, 270), b2
    R.degistir(p, b2, "GEMI: ZEUS")
    p.get_pixmap(dpi=72).save(os.path.join(TMP, "kart_sonuc.png"))
    return f"yatay '{b['metin']}' yan '{b2['metin']}' (aci {b2['yon_aci']})  cv2={'var' if R.cv2_var() else 'YOK'}"


@senaryo("Sıkıştırma: tarama resmi küçülür, yazı korunur, hedef boyut")
def t_sikistir():
    from pdfpro import cekirdek as C
    from PIL import Image
    import numpy as np
    yol = os.path.join(TMP, "tarama_buyuk.pdf")
    resim = os.path.join(TMP, "tarama.png")
    a = (np.random.default_rng(1).random((3508, 2480, 3)) * 40 + 200).astype("uint8")
    Image.fromarray(a).save(resim)
    d = fitz.open()
    p = d.new_page()
    p.insert_image(p.rect, filename=resim)
    p.insert_text((72, 72), "OKUNMALI 2026", fontsize=14)
    d.save(yol)
    once = os.path.getsize(yol)
    _, _, sonra, _ = C.sikistir(yol, os.path.join(TMP, "k.pdf"), "orta")
    assert sonra < once * 0.5, (once, sonra)
    assert "OKUNMALI" in fitz.open(os.path.join(TMP, "k.pdf"))[0].get_text()
    _, _, h, sev = C.sikistir(yol, os.path.join(TMP, "k2.pdf"), "hafif", hedef_kb=sonra / 1024 * 0.8)
    return f"{once // 1024} KB -> {sonra // 1024} KB (orta), hedefli: {h // 1024} KB ({sev})"


@senaryo("Sıkıştırma resmi belgede (' operatörü) yazıları kaydırmamalı")
def t_sikistir_kayma():
    from pdfpro import cekirdek as C
    yol = os.path.join(TMP, "tirnak.pdf")
    d = fitz.open()
    p = d.new_page()
    p.insert_font(fontname="F1", fontfile=FONT)
    akis = b"BT /F1 12 Tf 20 TL 72 770 Td (BIRINCI SATIR) Tj (IKINCI SATIR)' (UCUNCU SATIR)' ET"
    xref = d.get_new_xref()
    d.update_object(xref, "<<>>")
    d.update_stream(xref, akis)
    d.xref_set_key(p.xref, "Contents", f"{xref} 0 R")
    d.save(yol)
    C.sikistir(yol, os.path.join(TMP, "tirnak_k.pdf"), "orta", hedef_kb=1)
    assert C._yazilar_ayni(yol, os.path.join(TMP, "tirnak_k.pdf")), "yazilar kaydi"


@senaryo("Yazı olmayan yere tıklama (çökmemeli)")
def t_bos_tik():
    d = ornek([((72, 100), "X", 12)])
    assert Z.satir_bul(d[0], 400, 600) is None
    from pdfpro import resim_yazi as R
    assert R.bul(d[0], 400, 600) is None


@senaryo("Karşılaştır: aynı belge 0 fark, değişen kelime bulunur")
def t_karsilastir():
    from pdfpro import araclar as AR
    a, b = os.path.join(TMP, "k_a.pdf"), os.path.join(TMP, "k_b.pdf")
    ornek([((72, 100), "Gemi adı ATLAS liman Mersin", 12)], kaydet=a)
    _, s, e, _ = AR.karsilastir(a, a, os.path.join(TMP, "k0.pdf"))
    assert s == e == 0, (s, e)
    ornek([((72, 100), "Gemi adı ORION liman Mersin", 12)], kaydet=b)
    _, s, e, f = AR.karsilastir(a, b, os.path.join(TMP, "k1.pdf"))
    assert s == 1 and e == 1 and f == 1, (s, e, f)


@senaryo("QR kod okuma")
def t_qr():
    from pdfpro import araclar as AR
    try:
        import cv2
        import numpy as np
    except Exception:
        return "atlandi (cv2 yok)"
    enc = cv2.QRCodeEncoder.create()
    img = cv2.resize(enc.encode("https://ornek.gov.tr/dogrula?no=123"), None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
    ok, png = cv2.imencode(".png", img)
    d = fitz.open()
    p = d.new_page()
    p.insert_image(fitz.Rect(100, 100, 250, 250), stream=png.tobytes())
    r = AR.qr_oku(d)
    assert r and r[0]["metin"].endswith("no=123"), r


@senaryo("Form: boş çizgi ve kutucuk otomatik alana dönüşür")
def t_form_algila():
    from pdfpro import araclar as AR
    d = ornek([((50, 100), "Adı Soyadı: ______________", 11), ((50, 130), "Gemi Adı:", 11), ((66, 160), "Kabul ediyorum", 11)])
    p = d[0]
    p.draw_line((110, 132), (300, 132))
    p.draw_rect(fitz.Rect(50, 151, 60, 161))
    n = AR.form_otomatik_algila(d)
    adlar = sorted(w.field_name for w in d[0].widgets())
    assert n == 3 and "Kabul ediyorum" in adlar and "Gemi Adı" in adlar, (n, adlar)
    assert AR.form_otomatik_algila(d) == 0      # ikinci kez ayni alanlar eklenmez


@senaryo("Çeviri: düzen korunur, eski yazı silinir (sahte yapay zeka)")
def t_ceviri():
    import json
    from pdfpro import yapay_zeka as Y
    eski = Y.sor
    Y.sor = lambda ayar, istem, **k: json.dumps(["Ship name: ATLAS" for _ in json.loads(istem)])
    try:
        a = os.path.join(TMP, "c_a.pdf")
        ornek([((72, 100), "Gemi adı: ATLAS", 12), ((72, 300), "Liman: Mersin", 12)], kaydet=a)
        _, n, _ = Y.pdf_cevir({}, a, os.path.join(TMP, "c_b.pdf"), "İngilizce")
        t = fitz.open(os.path.join(TMP, "c_b.pdf"))[0].get_text()
        assert "Gemi" not in t and t.count("Ship name") == 2, f"n={n} metin={t!r}"
    finally:
        Y.sor = eski


@senaryo("İş akışı + belge paketi + yedek (son 10)")
def t_otomasyon():
    from pdfpro import otomasyon as OT, yedek as YD
    a = os.path.join(TMP, "o_a.pdf")
    ornek([((72, 100), "Crew List", 12)], kaydet=a)
    c = os.path.join(TMP, "o_b.pdf")
    OT.akisi_uygula([{"tur": "damga", "ayar": {"metin": "ASLI GİBİDİR"}},
                     {"tur": "sayfa_no", "ayar": {}}, {"tur": "sikistir", "ayar": {"seviye": "hafif"}}], a, c)
    import unicodedata
    t = fitz.open(c)[0].get_text()
    n_ = unicodedata.normalize("NFKC", t).replace("\u0307", "").upper().replace("İ", "I")
    assert "ASLI GIBIDIR" in n_ and "SAYFA 1 / 1" in n_, repr(t)
    pk, n, eksik = OT.paket_olustur([{"ad": "Crew", "dosyalar": [a]}, {"ad": "Bos", "dosyalar": []},
                                     {"ad": "Damgali", "dosyalar": [c]}], os.path.join(TMP, "paket.pdf"))
    assert n == 2 and eksik == ["Bos"] and len(fitz.open(pk).get_toc()) == 2
    YD.YEDEK_KLASORU = os.path.join(TMP, "yedekler")
    for _ in range(12):
        YD.yedekle(a)
    assert len(YD.liste(a)) == 10



@senaryo("A4'e sığdır / antet sonrası karart: sayfa boş kalmamalı")
def t_form_sonrasi():
    from pdfpro import araclar as AR
    d = ornek([((72, 100), "Gemi adı ATLAS", 14), ((72, 400), "Liman Mersin", 14)])
    AR.a4e_sigdir(d, [0])
    p = d[0]
    Z.sayfa_hazirla(p)
    AR.karart(d[0], fitz.Rect(60, 80, 300, 110))
    t = d[0].get_text()
    assert "Liman Mersin" in t and "ATLAS" not in t, t
    pix = d[0].get_pixmap(dpi=40)
    assert any(b < 100 for b in pix.samples), "sayfa bos kaldi"



@senaryo("Windows fontlarında boşluk: kopyalanan yazıda bölünmez boşluk (\\xa0) çıkmamalı")
def t_nbsp():
    cmap = b"begincmap\n2 beginbfchar\n<0003> <00A0>\n<00a0> <0041>\nendbfchar\n1 beginbfrange\n<0005> <0005> <00A0>\nendbfrange\nendcmap"
    y = Z._tounicode_bosluk(cmap)
    assert y and b"<0003> <0020>" in y and b"<00a0> <0041>" in y and b"<0005> <0005> <0020>" in y, y


def main():
    testler = [v for k, v in globals().items() if k.startswith("t_") and callable(v)]
    for t in testler:
        t()
    gen = max(len(a) for a, _, _ in sonuclar)
    hata = 0
    for ad, durum, notu in sonuclar:
        print(f"{'✔' if durum == 'TAMAM' else '✖'} {ad.ljust(gen)}  {durum}  {notu.splitlines()[0] if durum == 'TAMAM' else ''}")
        if durum != "TAMAM":
            hata += 1
            print("   " + notu.replace("\n", "\n   "))
    print(f"\n{len(sonuclar) - hata}/{len(sonuclar)} senaryo geçti. Geçici dosyalar: {TMP}")
    return hata


if __name__ == "__main__":
    sys.exit(main())
