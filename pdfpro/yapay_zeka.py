# -*- coding: utf-8 -*-
"""
PDF PRO - Yapay zeka araclari
- Ozetle: belgeyi Turkce ozetler (anahtar yoksa cevrimdisi "onemli cumleler" ozeti)
- Cevir: sayfa duzenini koruyarak belgeyi baska dile cevirir (yazilar yerinde degisir)
- Belgeye sor: belge hakkinda soru-cevap
Saglayicilar: Google Gemini, Groq, OpenRouter veya OpenAI uyumlu herhangi bir adres.
Sadece Python standart kutuphanesi (urllib) kullanilir.
"""
import json
import re
import ssl
import time
import urllib.error
import urllib.request
from collections import Counter

from .cekirdek import fitz, PdfProHata
from . import duzenle as Z

SAGLAYICILAR = {
    "Google Gemini": {"tur": "gemini", "model": "gemini-flash-latest",
                      "adres": "https://generativelanguage.googleapis.com/v1beta",
                      "anahtar_adresi": "https://aistudio.google.com/apikey", "sinir": 400000},
    "Groq": {"tur": "openai", "model": "llama-3.3-70b-versatile",
             "adres": "https://api.groq.com/openai/v1", "anahtar_adresi": "https://console.groq.com/keys",
             "sinir": 14000},
    "OpenRouter": {"tur": "openai", "model": "meta-llama/llama-3.3-70b-instruct:free",
                   "adres": "https://openrouter.ai/api/v1", "anahtar_adresi": "https://openrouter.ai/keys",
                   "sinir": 40000},
    "Özel (OpenAI uyumlu)": {"tur": "openai", "model": "", "adres": "http://localhost:8000/v1",
                             "anahtar_adresi": "", "sinir": 30000},
}

DILLER = ["İngilizce", "Türkçe", "Almanca", "Fransızca", "İspanyolca", "İtalyanca", "Rusça", "Arapça",
          "Yunanca", "Ukraynaca", "Çince", "Japonca", "Felemenkçe", "Portekizce", "Bulgarca", "Romence"]


class YZHata(PdfProHata):
    pass


def ayar_tam(ayar):
    """Kayitli ayardan eksiksiz saglayici bilgisi."""
    ad = (ayar or {}).get("saglayici") or "Google Gemini"
    temel = dict(SAGLAYICILAR.get(ad, SAGLAYICILAR["Google Gemini"]))
    anahtarlar = (ayar or {}).get("anahtarlar", {})
    temel["ad"] = ad
    temel["anahtar"] = (anahtarlar.get(ad) or "").strip()
    temel["model"] = ((ayar or {}).get("modeller", {}).get(ad) or temel["model"]).strip()
    if ad.startswith("Özel"):
        temel["adres"] = ((ayar or {}).get("ozel_adres") or temel["adres"]).strip().rstrip("/")
    return temel


def hazir_mi(ayar):
    a = ayar_tam(ayar)
    return bool(a["anahtar"]) or (a["ad"].startswith("Özel") and bool(a["adres"]) and bool(a["model"]))


# ------------------------------------------------------------------ HTTP
def _post(url, govde, basliklar, zaman=120):
    veri = json.dumps(govde).encode("utf-8")
    istek = urllib.request.Request(url, data=veri, method="POST",
                                   headers=dict({"Content-Type": "application/json"}, **basliklar))
    son_hata = None
    for deneme in range(3):
        try:
            with urllib.request.urlopen(istek, timeout=zaman, context=ssl.create_default_context()) as y:
                return json.loads(y.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                ayrinti = e.read().decode("utf-8", "replace")[:400]
            except Exception:
                ayrinti = ""
            if e.code in (429, 500, 502, 503, 504) and deneme < 2:
                time.sleep(4 * (deneme + 1))
                son_hata = e
                continue
            if e.code in (401, 403):
                raise YZHata("Yapay zeka anahtarı geçersiz veya yetkisiz.\nYapay Zeka → Ayarlar'dan anahtarı kontrol edin."
                             + (f"\n\nSunucu: {_kisa_hata(ayrinti)}" if ayrinti else ""))
            if e.code == 404:
                raise YZHata(f"Model bulunamadı. Yapay Zeka → Ayarlar'dan model adını kontrol edin.\n{ayrinti[:200]}")
            if e.code == 429:
                raise YZHata("Yapay zeka kullanım sınırı doldu (çok sık istek). Birkaç dakika sonra tekrar deneyin "
                             "ya da Ayarlar'dan başka bir sağlayıcı seçin.")
            raise YZHata(f"Yapay zeka hatası ({e.code}):\n{ayrinti}")
        except urllib.error.URLError as e:
            son_hata = e
            if deneme < 2:
                time.sleep(2)
                continue
            raise YZHata(f"Yapay zeka sunucusuna bağlanılamadı. İnternet bağlantısını kontrol edin.\n({e.reason})")
        except TimeoutError:
            son_hata = "zaman aşımı"
            if deneme < 2:
                continue
            raise YZHata("Yapay zeka yanıt vermedi (zaman aşımı). Tekrar deneyin.")
    raise YZHata(f"Yapay zeka isteği başarısız: {son_hata}")


VERTEX_ADRES = "https://aiplatform.googleapis.com/v1/publishers/google/models"


def _vertex_model(model):
    # Vertex AI'da "-latest" takma adlari yok
    return {"gemini-flash-latest": "gemini-2.5-flash", "gemini-pro-latest": "gemini-2.5-pro",
            "gemini-flash-lite-latest": "gemini-2.5-flash-lite"}.get(model, model)


def _gemini_gonder(a, govde):
    """Google AI Studio anahtari (AIza...) -> generativelanguage; Vertex AI Express anahtari (AQ. ...) ->
    aiplatform. Biri reddederse digeri denenir."""
    import urllib.parse
    anahtar = a["anahtar"]
    studio = (f"{a['adres']}/models/{a['model']}:generateContent", {"x-goog-api-key": anahtar})
    vertex = (f"{VERTEX_ADRES}/{_vertex_model(a['model'])}:generateContent?key={urllib.parse.quote(anahtar)}", {})
    sira = [vertex, studio] if anahtar.startswith("AQ.") else [studio, vertex]
    son = None
    for k, (url, bas) in enumerate(sira):
        try:
            return _post(url, govde, bas)
        except YZHata as e:
            son = e
            metin = str(e)
            if k == 0 and ("geçersiz" in metin or "(400)" in metin or "bulunamadı" in metin):
                continue
            raise
    raise son


def _kisa_hata(ayrinti):
    try:
        return json.loads(ayrinti).get("error", {}).get("message", ayrinti)[:250]
    except Exception:
        return ayrinti[:250]


def sor(ayar, istem, sistem=None, sicaklik=0.2, json_cikti=False):
    """Tek bir istem gonderir, yaniti metin olarak dondurur."""
    a = ayar_tam(ayar)
    if not hazir_mi(ayar):
        raise YZHata("Yapay zeka anahtarı girilmemiş.\nYapay Zeka → Ayarlar'dan ücretsiz bir anahtar ekleyin.")
    if a["tur"] == "gemini":
        govde = {"contents": [{"role": "user", "parts": [{"text": istem}]}],
                 "generationConfig": {"temperature": sicaklik}}
        if sistem:
            govde["systemInstruction"] = {"parts": [{"text": sistem}]}
        if json_cikti:
            govde["generationConfig"]["responseMimeType"] = "application/json"
        y = _gemini_gonder(a, govde)
        try:
            parcalar = y["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parcalar).strip()
        except (KeyError, IndexError):
            neden = (y.get("promptFeedback") or {}).get("blockReason") or json.dumps(y)[:300]
            raise YZHata(f"Yapay zeka yanıt üretmedi: {neden}")
    mesajlar = ([{"role": "system", "content": sistem}] if sistem else []) + [{"role": "user", "content": istem}]
    govde = {"model": a["model"], "messages": mesajlar, "temperature": sicaklik}
    if json_cikti and a["ad"] == "Groq":
        govde["response_format"] = {"type": "json_object"}
    basliklar = {"Authorization": f"Bearer {a['anahtar']}"} if a["anahtar"] else {}
    if a["ad"] == "OpenRouter":
        basliklar.update({"HTTP-Referer": "https://pdfpro.local", "X-Title": "PDF PRO"})
    y = _post(f"{a['adres']}/chat/completions", govde, basliklar)
    try:
        return (y["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError):
        raise YZHata(f"Yapay zeka yanıt üretmedi: {json.dumps(y)[:300]}")


def baglanti_testi(ayar):
    return sor(ayar, "Sadece 'Tamam' yaz.", sicaklik=0)


# ------------------------------------------------------------------ belge metni
def belge_metni(doc, ocr_yol=None, ilerleme=None, iptal=None):
    """Sayfa sayfa metin; yazisi olmayan (taranmis) sayfalar OCR ile okunur (Tesseract varsa)."""
    parcalar = []
    ocr_hazir = None
    for i, p in enumerate(doc):
        if iptal and iptal():
            break
        if ilerleme:
            ilerleme(i, doc.page_count, f"Sayfa {i + 1} okunuyor")
        t = p.get_text("text").strip()
        if len(t) < 25:
            if ocr_hazir is None:
                try:
                    from . import ocr as O
                    ocr_hazir = O.ocr_durumu()[0]
                except Exception:
                    ocr_hazir = False
            if ocr_hazir:
                try:
                    from . import ocr as O
                    import pytesseract
                    from PIL import Image
                    O._hazirla()
                    pix = p.get_pixmap(dpi=250, colorspace=fitz.csGRAY)
                    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
                    t = pytesseract.image_to_string(img, lang="tur+eng").strip()
                except Exception:
                    pass
        parcalar.append(f"--- Sayfa {i + 1} ---\n{t}")
    return "\n\n".join(parcalar)


# ------------------------------------------------------------------ cevrimdisi ozet
_DUR = set("""ve veya ile de da ki bu şu o bir için gibi olan olarak daha çok en ama fakat ancak
ise ne mi mı mu mü her hem kadar sonra önce göre ait üzere tarafından the of and to in a is for on
that with as by at from be are this or an it was which""".split())


def cevrimdisi_ozet(metin, cumle_sayisi=8):
    temiz = re.sub(r"--- Sayfa \d+ ---", " ", metin)
    cumleler = [c.strip() for c in re.split(r"(?<=[.!?])\s+|\n{2,}", temiz) if 30 <= len(c.strip()) <= 400]
    if not cumleler:
        return temiz.strip()[:1500]
    kelime = lambda s: [k for k in re.findall(r"\w+", s.lower()) if k not in _DUR and len(k) > 2 and not k.isdigit()]
    sayac = Counter(k for c in cumleler for k in kelime(c))
    if not sayac:
        return "\n".join(cumleler[:cumle_sayisi])
    en = max(sayac.values())
    puan = []
    for i, c in enumerate(cumleler):
        ks = kelime(c)
        if not ks:
            continue
        p = sum(sayac[k] / en for k in ks) / (len(ks) ** 0.6)
        if i < 3:
            p *= 1.15
        puan.append((p, i, c))
    secilen = sorted(sorted(puan, reverse=True)[:cumle_sayisi], key=lambda x: x[1])
    ozet = "\n".join("• " + c.replace("\n", " ") for _, _, c in secilen)
    # one cikan bilgiler
    bilgi = []
    tarihler = sorted(set(re.findall(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", temiz)))[:8]
    if tarihler:
        bilgi.append("Tarihler: " + ", ".join(tarihler))
    tutarlar = re.findall(r"(?:(?:USD|EUR|TRY|TL|\$|€|₺)\s?\d[\d.,]*|\d[\d.,]*\s?(?:USD|EUR|TRY|TL|\$|€|₺))", temiz)
    if tutarlar:
        bilgi.append("Tutarlar: " + ", ".join(dict.fromkeys(t.strip() for t in tutarlar[:10])))
    imo = sorted(set(re.findall(r"IMO\s*(?:No\.?|Number)?\s*:?\s*(\d{7})", temiz, re.I)))
    if imo:
        bilgi.append("IMO: " + ", ".join(imo))
    epostalar = sorted(set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", temiz)))[:5]
    if epostalar:
        bilgi.append("E-posta: " + ", ".join(epostalar))
    return ozet + ("\n\nÖne çıkan bilgiler:\n" + "\n".join("• " + b for b in bilgi) if bilgi else "")


# ------------------------------------------------------------------ ozet
OZET_SISTEM = ("Sen bir belge analiz asistanısın. Kullanıcı bir denizcilik acentesinde çalışıyor. "
               "Yanıtlarını her zaman Türkçe, açık ve düzenli ver. Uydurma bilgi ekleme; belgede olmayanı yazma.")


def ozetle(ayar, metin, uzunluk="orta", ilerleme=None, iptal=None):
    a = ayar_tam(ayar)
    sinir = a.get("sinir", 30000)
    boy = {"kisa": "3-5 madde", "orta": "kısa bir giriş paragrafı ve 6-10 madde", "uzun": "ayrıntılı, başlıklı bir özet"}[uzunluk]
    istem_kalip = ("Aşağıdaki belgeyi Türkçe olarak özetle ({boy}). Sonunda 'Önemli bilgiler' başlığı altında "
                   "varsa tarihleri, tutarları, kişi/firma/gemi adlarını, belge numaralarını ve yapılması gerekenleri listele.\n\n"
                   "BELGE:\n{metin}")
    if len(metin) <= sinir:
        if ilerleme:
            ilerleme(1, 2, "Yapay zeka özetliyor")
        return sor(ayar, istem_kalip.format(boy=boy, metin=metin), sistem=OZET_SISTEM)
    # uzun belge: parca parca ozetle, sonra birlestir
    parcalar = [metin[i:i + sinir] for i in range(0, len(metin), sinir)]
    ara = []
    for k, p in enumerate(parcalar):
        if iptal and iptal():
            raise PdfProHata("İptal edildi.")
        if ilerleme:
            ilerleme(k, len(parcalar) + 1, f"Bölüm {k + 1}/{len(parcalar)} özetleniyor")
        ara.append(sor(ayar, "Bu belge bölümünü Türkçe maddeler halinde özetle; tarih, tutar, ad ve numaraları koru:\n\n" + p,
                       sistem=OZET_SISTEM))
        if a["ad"] == "Groq":
            time.sleep(2)
    if ilerleme:
        ilerleme(len(parcalar), len(parcalar) + 1, "Bölümler birleştiriliyor")
    return sor(ayar, istem_kalip.format(boy=boy, metin="\n\n".join(ara)), sistem=OZET_SISTEM)


def belgeye_sor(ayar, metin, soru):
    a = ayar_tam(ayar)
    m = metin[:a.get("sinir", 30000)]
    return sor(ayar, f"BELGE:\n{m}\n\nSORU: {soru}\n\nSadece belgedeki bilgilere dayanarak Türkçe yanıtla. "
                     "Belgede yoksa 'Belgede bu bilgi yok' de. Mümkünse sayfa numarasını belirt.", sistem=OZET_SISTEM)


# ------------------------------------------------------------------ ceviri
def _json_liste(yanit, n):
    t = yanit.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        v = json.loads(t)
    except Exception:
        m = re.search(r"\[.*\]", t, re.S)
        if not m:
            return None
        try:
            v = json.loads(m.group(0))
        except Exception:
            return None
    if isinstance(v, dict):
        v = next((x for x in v.values() if isinstance(x, list)), None)
    if not isinstance(v, list) or len(v) != n:
        return None
    return [str(x) for x in v]


def metinleri_cevir(ayar, metinler, hedef_dil, ilerleme=None, iptal=None, etiket=""):
    """Metin listesini cevirir (sirasi ve sayisi korunur)."""
    a = ayar_tam(ayar)
    paket_sinir = min(6000, a.get("sinir", 30000) // 2)
    sonuc = list(metinler)
    paketler, cur, boy = [], [], 0
    for i, m in enumerate(metinler):
        if cur and (boy + len(m) > paket_sinir or len(cur) >= 60):
            paketler.append(cur)
            cur, boy = [], 0
        cur.append(i)
        boy += len(m) + 8
    if cur:
        paketler.append(cur)
    sistem = (f"Profesyonel bir çevirmensin. Verilen JSON dizisindeki her metni {hedef_dil} diline çevir. "
              "Sayıları, tarihleri, kodları, e-posta/web adreslerini, gemi ve firma adlarını aynen bırak. "
              "Kısa ve resmi belge diline uygun çevir. Çıktı SADECE aynı uzunlukta bir JSON dizisi olsun.")
    for k, pk in enumerate(paketler):
        if iptal and iptal():
            raise PdfProHata("İptal edildi.")
        if ilerleme:
            ilerleme(k, len(paketler), f"{etiket}çeviri {k + 1}/{len(paketler)}")
        girdi = [metinler[i] for i in pk]
        cikti = None
        for deneme in range(3):
            y = sor(ayar, json.dumps(girdi, ensure_ascii=False), sistem=sistem, sicaklik=0.1, json_cikti=(a["tur"] == "gemini"))
            cikti = _json_liste(y, len(girdi))
            if cikti is not None:
                break
            if deneme == 1 and len(girdi) > 1:
                # tek tek cevir
                cikti = [sor(ayar, f"Şu metni {hedef_dil} diline çevir, sadece çeviriyi yaz:\n{m}", sicaklik=0.1) for m in girdi]
                break
        if cikti is None:
            raise YZHata("Yapay zeka çeviriyi beklenen biçimde döndürmedi. Tekrar deneyin.")
        for i, c in zip(pk, cikti):
            sonuc[i] = c
    return sonuc


def _paragraflar(page):
    """Sayfadaki yazilari paragraf gruplari halinde dondurur (satir_bul ile ayni mantik)."""
    veri = Z.metin_verisi(page)
    satirlar = Z._birlesik_satirlar(veri["bloklar"])
    veri["_birlesik"] = satirlar
    goruldu, sonuc = set(), []
    for s_ in satirlar:
        r = s_["rect"]
        anahtar = (round(r.x0, 1), round(r.y0, 1))
        if anahtar in goruldu:
            continue
        p = Z.satir_bul(page, (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2, veri=veri)
        if not p:
            goruldu.add(anahtar)
            continue
        uyeler = p.get("satirlar") or [p]
        yeni = False
        for u in uyeler:
            ub = fitz.Rect(u["bbox"])
            k = (round(ub.x0, 1), round(ub.y0, 1))
            if k not in goruldu:
                yeni = True
            goruldu.add(k)
        goruldu.add(anahtar)
        if yeni:
            sonuc.append(p)
    return sonuc


def _cevrilecek_mi(t):
    t = t.strip()
    return len(t) >= 2 and re.search(r"[^\W\d_]{2,}", t) is not None and not re.fullmatch(r"[\w.+-]+@[\w.-]+|https?://\S+|www\.\S+", t)


def pdf_cevir(ayar, yol, cikti, hedef_dil, ilerleme=None, iptal=None):
    """Sayfa duzenini koruyarak ceviri: eski yazilar silinir, ceviri ayni kutuya sigdirilarak yazilir.
    Dondurur: (cikti, cevrilen_paragraf, taranmis_sayfa_sayisi)"""
    doc = fitz.open(yol)
    if doc.needs_pass:
        raise PdfProHata("Şifreli PDF çevrilemez.")
    n = doc.page_count
    toplam, taranmis = 0, 0
    for i in range(n):
        if iptal and iptal():
            raise PdfProHata("İptal edildi.")
        page = doc[i]
        Z.sayfa_hazirla(page)
        etiket = f"Sayfa {i + 1}/{n}: "
        if ilerleme:
            ilerleme(i, n, etiket + "yazılar okunuyor")
        _paragraflar_cache = _paragraflar(page)
        paras = [p for p in _paragraflar_cache if p.get("aci", 0) == 0 and not p.get("gorunmez")]
        paras = [p for p in paras if _cevrilecek_mi(p["metin"])]
        if not paras:
            if len(page.get_text("text").strip()) < 25:
                taranmis += _taranmis_cevir(ayar, page, hedef_dil, ilerleme, iptal, etiket)
            continue
        metinler = [re.sub(r"-\n(?=\w)", "", p["metin"]).replace("\n", " ") for p in paras]
        ceviriler = metinleri_cevir(ayar, metinler, hedef_dil,
                                    (lambda k, m, t: ilerleme(i + k / max(1, m), n, etiket + t)) if ilerleme else None,
                                    iptal, "")
        # eski yazilari tek seferde sil
        Z.icerik_normallestir(page)
        page = doc[i]
        for p in paras:
            for u in (p.get("satirlar") or [p]):
                b = fitz.Rect(u["bbox"])
                page.add_redact_annot(fitz.Rect(b.x0 - 0.3, b.y0 + b.height * 0.18, b.x1 + 0.3, b.y1 - b.height * 0.18))
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        # cevirileri yaz
        rectler = [fitz.Rect(p["bbox"]) for p in _paragraflar_cache]
        for p, c in zip(paras, ceviriler):
            _kutuya_yaz(page, p, c, [r for r in rectler if r != fitz.Rect(p["bbox"])])
            toplam += 1
    doc.save(cikti, garbage=3, deflate=True)
    doc.close()
    return cikti, toplam, taranmis


def _kutuya_yaz(page, p, metin, engeller=()):
    uyeler = p.get("satirlar") or [p]
    tum = fitz.Rect(p["bbox"])
    boy = p.get("boyut") or 10
    # cevirinin uzamasina pay: kutuyu saga dogru genislet; hucre cizgisi, sayfa kenari
    # ya da ayni hizadaki diger yazilar sinirdir
    sag = min(p.get("sag_sinir") or page.rect.x1, page.rect.x1 - 6)
    for e in engeller:
        if e.x0 >= tum.x1 - 1 and e.y1 > tum.y0 + 1 and e.y0 < tum.y1 - 1:
            sag = min(sag, e.x0 - 3)
    if (p.get("sag_sinir") or 0) >= page.rect.x1 - 31:      # gercek hucre cizgisi yok: az genislet
        sag = min(sag, tum.x1 + max(tum.width * 0.08, 8))
    sag = max(sag, tum.x1)
    x0 = uyeler[0]["origin"][0] if uyeler[0].get("origin") else tum.x0
    kutu = fitz.Rect(x0, tum.y0 - boy * 0.05, sag, tum.y1 + boy * 0.35)
    try:
        font = Z.font_sec(page, p, metin)
    except Exception:
        font = Z.font_al(p.get("serif", False), p.get("kalin", False), p.get("italik", False))
    if not all(c in " \n\t" or font.has_glyph(ord(c)) for c in metin):
        font = Z.font_al(p.get("serif", False), p.get("kalin", False), p.get("italik", False))
    renk = p.get("renk") or (0, 0, 0)
    aralik = (p.get("satir_araligi") or boy * 1.2) / boy
    b = boy
    tw = None
    while b >= boy * 0.45:
        tw = fitz.TextWriter(page.rect, color=renk)
        artan = tw.fill_textbox(kutu, metin, font=font, fontsize=b, lineheight=aralik, warn=None)
        if not artan:
            break
        b *= 0.93
    if tw is not None:
        Z.tw_yaz(page, tw)


def _taranmis_cevir(ayar, page, hedef_dil, ilerleme, iptal, etiket):
    """Taranmis sayfa: OCR satirlari -> ceviri -> eski yazinin ustu zemin rengiyle ortulur, ceviri yazilir."""
    try:
        from . import ocr as O
        if not O.ocr_durumu()[0]:
            return 0
        import pytesseract
        from PIL import Image
        O._hazirla()
    except Exception:
        return 0
    dpi = 250
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    d = pytesseract.image_to_data(img, lang="tur+eng", output_type=pytesseract.Output.DICT)
    olcek = 72.0 / dpi
    satirlar = {}
    for k in range(len(d["text"])):
        t = (d["text"][k] or "").strip()
        try:
            guven = float(d["conf"][k])
        except Exception:
            guven = -1
        if not t or guven < 40:
            continue
        anahtar = (d["block_num"][k], d["par_num"][k], d["line_num"][k])
        r = fitz.Rect(d["left"][k], d["top"][k], d["left"][k] + d["width"][k], d["top"][k] + d["height"][k]) * olcek
        s = satirlar.setdefault(anahtar, {"metin": [], "rect": fitz.Rect(r)})
        s["metin"].append(t)
        s["rect"] |= r
    ls = [s for s in satirlar.values() if _cevrilecek_mi(" ".join(s["metin"]))]
    if not ls:
        return 0
    if ilerleme:
        ilerleme(0, 1, etiket + "taranmış sayfa çevriliyor")
    cev = metinleri_cevir(ayar, [" ".join(s["metin"]) for s in ls], hedef_dil, None, iptal)
    font = Z.font_al(False, False, False)
    for s, c in zip(ls, cev):
        r = s["rect"]
        zemin = Z.arka_plan_rengi(page, r)
        page.draw_rect(r + (-1, -1, 1, 1), color=None, fill=zemin, overlay=True)
        b = r.height * 0.85
        while b > 4 and font.text_length(c, b) > max(r.width * 1.15, 20):
            b *= 0.94
        tw = fitz.TextWriter(page.rect, color=(0, 0, 0))
        tw.append(fitz.Point(r.x0, r.y1 - r.height * 0.2), c, font=font, fontsize=b)
        Z.tw_yaz(page, tw)
    return 1
