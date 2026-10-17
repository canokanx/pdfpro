# -*- coding: utf-8 -*-
"""
PDF PRO - Otomatik guncelleme (kullanici tarafi) + ortak yardimcilar

Yayin bicimi (GitHub):
  - Depo (main dalı): programin guncel kaynak dosyalari
  - Surum (Release) "v4.0.3": guncelleme.json + tam paket pdfpro-4.0.3.zip
  - guncelleme.json = {"manifest": "<json metni>", "imza": "<ed25519 hex>"}
    manifest = {"surum", "commit", "tarih", "notlar", "dosyalar": {"yol": "sha256", ...}}
Kullanici:
  1) son surumu sorar, imzayi programdaki acik anahtarla dogrular
  2) sadece degisen dosyalari indirir (her birinin sha256'si imzali listede) -> guncelleme_bekleyen/
  3) program bir sonraki acilisinda (hicbir modul yuklenmeden) dosyalari yerine koyar
  4) yeni surum acilista cokerse otomatik olarak bir onceki surume doner
"""
import hashlib
import json
import os
import shutil
import ssl
import sys
import time
import urllib.parse
import urllib.request

from .surum import SURUM, surum_tuple
from . import ed25519

PROGRAM_KLASORU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AYAR_DOSYASI = os.path.join(PROGRAM_KLASORU, "guncelleme_ayar.json")
BEKLEYEN = os.path.join(PROGRAM_KLASORU, "guncelleme_bekleyen")
ONCEKI = os.path.join(PROGRAM_KLASORU, "onceki_surum")
DENEME_ISARETI = os.path.join(PROGRAM_KLASORU, "guncelleme_deneme.json")
DURUM_DOSYASI = os.path.join(PROGRAM_KLASORU, "guncelleme_durum.json")
API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"

# pakete GIRMEYEN (kullaniciya ozel / gecici) dosya ve klasorler
HARIC_KLASOR = {"__pycache__", "yedekler", "Claude outputs", "guncelleme_bekleyen", "onceki_surum", ".git",
                ".idea", ".vscode", "cikti"}
HARIC_DOSYA = {"ayarlar.json", "fontlar_onbellek.json", "hata_kaydi.txt", "python_yolu.txt", "gomulu_ok.txt",
               "gomulu_deneme.txt", "guncelleme_deneme.json", "guncelleme_durum.json",
               "son_test_sonucu.txt"}
HARIC_UZANTI = (".pyc", ".pyo", ".old", ".tmp", ".pdfpro_tmp", ".log")


class GuncellemeHatasi(Exception):
    pass


# ------------------------------------------------------------------ ortak
def sha256_dosya(yol):
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for parca in iter(lambda: f.read(1 << 20), b""):
            h.update(parca)
    return h.hexdigest()


def paket_dosyalari(klasor=PROGRAM_KLASORU):
    """Pakete girecek dosyalar: {'pdfpro/arayuz.py': tam_yol, ...} (her zaman / ile)"""
    sonuc = {}
    for kok, klasorler, dosyalar in os.walk(klasor):
        klasorler[:] = sorted(k for k in klasorler if k not in HARIC_KLASOR and not k.startswith("."))
        for ad in sorted(dosyalar):
            if ad in HARIC_DOSYA or ad.lower().endswith(HARIC_UZANTI) or ad.startswith("~$"):
                continue
            tam = os.path.join(kok, ad)
            goreli = os.path.relpath(tam, klasor).replace(os.sep, "/")
            sonuc[goreli] = tam
    return sonuc


def ayar_oku():
    try:
        with open(AYAR_DOSYASI, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _durum_oku():
    try:
        with open(DURUM_DOSYASI, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _durum_yaz(d):
    try:
        with open(DURUM_DOSYASI, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def istek(url, veri=None, token=None, yontem=None, basliklar=None, zaman=60, ham=False):
    """GitHub'a HTTP istegi. ham=True -> bayt doner, degilse JSON."""
    b = {"User-Agent": "PDF-PRO", "Accept": "application/vnd.github+json"}
    if token:
        b["Authorization"] = f"Bearer {token}"
    if basliklar:
        b.update(basliklar)
    if isinstance(veri, (dict, list)):
        veri = json.dumps(veri).encode("utf-8")
        b.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(url, data=veri, method=yontem or ("POST" if veri is not None else "GET"), headers=b)
    try:
        with urllib.request.urlopen(r, timeout=zaman, context=ssl.create_default_context()) as y:
            icerik = y.read()
    except urllib.error.HTTPError as e:
        try:
            ayrinti = json.loads(e.read().decode("utf-8", "replace")).get("message", "")
        except Exception:
            ayrinti = ""
        hata = GuncellemeHatasi(f"GitHub hatası {e.code}: {ayrinti or e.reason}")
        hata.kod = e.code
        raise hata
    except urllib.error.URLError as e:
        raise GuncellemeHatasi(f"İnternete / GitHub'a bağlanılamadı: {e.reason}")
    if ham:
        return icerik
    return json.loads(icerik.decode("utf-8")) if icerik else {}


def manifest_dogrula(paket, acik_hex):
    """guncelleme.json icerigini dogrular; manifest sozlugunu dondurur."""
    try:
        metin = paket["manifest"]
        imza = bytes.fromhex(paket["imza"])
        acik = bytes.fromhex(acik_hex)
    except Exception:
        raise GuncellemeHatasi("Güncelleme bilgisi bozuk.")
    if not ed25519.dogrula(acik, metin.encode("utf-8"), imza):
        raise GuncellemeHatasi("Güncellemenin imzası geçersiz — yöneticiden gelmiyor, yüklenmedi.")
    return json.loads(metin)


# ------------------------------------------------------------------ kullanici: kontrol + indirme
def son_surum_bilgisi(ayar=None):
    """GitHub'daki son surumun dogrulanmis manifestini dondurur (yoksa None)."""
    ayar = ayar or ayar_oku()
    repo, acik = ayar.get("repo"), ayar.get("acik_anahtar")
    if not repo or not acik:
        return None
    token = ayar.get("okuma_tokeni") or None
    rel = istek(f"{API}/repos/{repo}/releases/latest", token=token, zaman=20)
    varlik = next((a for a in rel.get("assets", []) if a.get("name") == "guncelleme.json"), None)
    if not varlik:
        return None
    if token:
        ham = istek(varlik["url"], token=token, basliklar={"Accept": "application/octet-stream"}, ham=True)
    else:
        ham = istek(varlik["browser_download_url"], ham=True)
    m = manifest_dogrula(json.loads(ham.decode("utf-8")), acik)
    m["_yayin_adresi"] = rel.get("html_url", "")
    return m


def _dosya_indir(repo, commit, yol, token=None):
    url = f"{RAW}/{repo}/{commit}/{urllib.parse.quote(yol)}"
    return istek(url, token=token, ham=True, zaman=120, basliklar={"Accept": "*/*"})


def guncelleme_indir(manifest, ayar=None, ilerleme=None, klasor=PROGRAM_KLASORU, hedef=BEKLEYEN):
    """Degisen dosyalari 'guncelleme_bekleyen' klasorune indirir. Dondurur: degisen dosya sayisi."""
    ayar = ayar or ayar_oku()
    repo, token = ayar["repo"], ayar.get("okuma_tokeni") or None
    dosyalar = manifest["dosyalar"]
    gerekli = []
    for yol, sha in dosyalar.items():
        if ".." in yol.split("/") or yol.startswith("/") or ":" in yol:
            raise GuncellemeHatasi(f"Geçersiz dosya yolu: {yol}")
        yerel = os.path.join(klasor, *yol.split("/"))
        if not (os.path.isfile(yerel) and sha256_dosya(yerel) == sha):
            gerekli.append(yol)
    # eski surumden kalan ve yeni surumde olmayan program dosyalari (sadece pdfpro/ altindaki .py)
    silinecek = [y for y in paket_dosyalari(klasor) if y.startswith("pdfpro/") and y.endswith(".py") and y not in dosyalar]
    gecici = hedef + "_yeni"
    shutil.rmtree(gecici, ignore_errors=True)
    os.makedirs(gecici, exist_ok=True)
    for k, yol in enumerate(gerekli):
        if ilerleme:
            ilerleme(k, len(gerekli), yol)
        veri = _dosya_indir(repo, manifest["commit"], yol, token)
        if hashlib.sha256(veri).hexdigest() != dosyalar[yol]:
            shutil.rmtree(gecici, ignore_errors=True)
            raise GuncellemeHatasi(f"İndirilen dosya doğrulanamadı: {yol}")
        t = os.path.join(gecici, *yol.split("/"))
        os.makedirs(os.path.dirname(t), exist_ok=True)
        with open(t, "wb") as f:
            f.write(veri)
    with open(os.path.join(gecici, "HAZIR.json"), "w", encoding="utf-8") as f:
        json.dump({"surum": manifest["surum"], "dosyalar": gerekli, "silinecek": silinecek,
                   "notlar": manifest.get("notlar", ""), "onceki": SURUM}, f, ensure_ascii=False)
    shutil.rmtree(hedef, ignore_errors=True)
    os.replace(gecici, hedef)
    return len(gerekli)


def kontrol_et_ve_indir(ilerleme=None):
    """Arka planda cagrilir. Dondurur: None (guncel / ayar yok) veya {'surum', 'notlar', 'dosya'}"""
    ayar = ayar_oku()
    if not ayar.get("repo") or ayar.get("otomatik") is False:
        return None
    bekleyen = bekleyen_bilgi()
    m = son_surum_bilgisi(ayar)
    if not m or surum_tuple(m["surum"]) <= surum_tuple(SURUM):
        return None
    durum = _durum_oku()
    if m["surum"] in durum.get("kotu_surumler", []):
        return None
    if bekleyen and bekleyen.get("surum") == m["surum"]:
        return {"surum": m["surum"], "notlar": m.get("notlar", ""), "dosya": len(bekleyen.get("dosyalar", []))}
    n = guncelleme_indir(m, ayar, ilerleme)
    return {"surum": m["surum"], "notlar": m.get("notlar", ""), "dosya": n}


def bekleyen_bilgi():
    try:
        with open(os.path.join(BEKLEYEN, "HAZIR.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ------------------------------------------------------------------ acilista uygulama / geri alma
def _kopyala(kaynak, hedef):
    os.makedirs(os.path.dirname(hedef), exist_ok=True)
    try:
        shutil.copy2(kaynak, hedef)
    except PermissionError:
        # calisan PDF_PRO.exe uzerine yazilamaz ama adi degistirilebilir
        eski = hedef + ".old"
        try:
            if os.path.exists(eski):
                os.remove(eski)
        except OSError:
            eski = hedef + f".{int(time.time())}.old"
        os.replace(hedef, eski)
        shutil.copy2(kaynak, hedef)


def acilista_calistir():
    """PDF_PRO.pyw en basta cagirir (program modulleri yuklenmeden once).
    1) Onceki guncelleme acilista coktuyse geri al  2) Bekleyen guncellemeyi uygula.
    Dondurur: mesaj metni veya None."""
    mesaj = None
    try:
        # 1) geri alma
        if os.path.isfile(DENEME_ISARETI):
            with open(DENEME_ISARETI, encoding="utf-8") as f:
                deneme = json.load(f)
            # guncellemeden sonraki acilis arayuze ulasamadi (coktu): onceki surume don
            geri_al(deneme)
            mesaj = (f"PDF PRO {deneme.get('surum')} düzgün açılamadı; "
                     f"{deneme.get('onceki')} sürümüne geri dönüldü.")
        # 2) bekleyeni uygula
        bilgi = bekleyen_bilgi()
        if bilgi and not os.path.isfile(DENEME_ISARETI):
            uygula(bilgi)
            mesaj = f"PDF PRO {bilgi['surum']} sürümüne güncellendi."
    except Exception as e:
        try:
            with open(os.path.join(PROGRAM_KLASORU, "hata_kaydi.txt"), "a", encoding="utf-8") as f:
                f.write(f"\n[guncelleme] {e!r}\n")
        except OSError:
            pass
    return mesaj


def uygula(bilgi):
    shutil.rmtree(ONCEKI, ignore_errors=True)
    os.makedirs(ONCEKI, exist_ok=True)
    yedeklenen = []
    for yol in list(bilgi["dosyalar"]) + list(bilgi.get("silinecek", [])):
        mevcut = os.path.join(PROGRAM_KLASORU, *yol.split("/"))
        if os.path.isfile(mevcut):
            hedef = os.path.join(ONCEKI, *yol.split("/"))
            os.makedirs(os.path.dirname(hedef), exist_ok=True)
            shutil.copy2(mevcut, hedef)
            yedeklenen.append(yol)
    with open(DENEME_ISARETI, "w", encoding="utf-8") as f:
        json.dump({"surum": bilgi["surum"], "onceki": bilgi.get("onceki", SURUM), "dosyalar": bilgi["dosyalar"],
                   "yedeklenen": yedeklenen, "silinecek": bilgi.get("silinecek", []), "sayac": 0}, f)
    for yol in bilgi["dosyalar"]:
        _kopyala(os.path.join(BEKLEYEN, *yol.split("/")), os.path.join(PROGRAM_KLASORU, *yol.split("/")))
    for yol in bilgi.get("silinecek", []):
        try:
            os.remove(os.path.join(PROGRAM_KLASORU, *yol.split("/")))
        except OSError:
            pass
    shutil.rmtree(BEKLEYEN, ignore_errors=True)


def geri_al(deneme):
    for yol in deneme.get("dosyalar", []):
        if yol not in deneme.get("yedeklenen", []):
            try:
                os.remove(os.path.join(PROGRAM_KLASORU, *yol.split("/")))      # yeni eklenen dosya
            except OSError:
                pass
    for yol in deneme.get("yedeklenen", []):
        _kopyala(os.path.join(ONCEKI, *yol.split("/")), os.path.join(PROGRAM_KLASORU, *yol.split("/")))
    d = _durum_oku()
    d.setdefault("kotu_surumler", []).append(deneme.get("surum"))
    _durum_yaz(d)
    try:
        os.remove(DENEME_ISARETI)
    except OSError:
        pass


def basarili():
    """Arayuz sorunsuz acilinca cagrilir: guncelleme kalici olur."""
    if os.path.isfile(DENEME_ISARETI):
        try:
            os.remove(DENEME_ISARETI)
        except OSError:
            pass
    # eski .old dosyalarini temizle
    try:
        for ad in os.listdir(PROGRAM_KLASORU):
            if ad.endswith(".old"):
                try:
                    os.remove(os.path.join(PROGRAM_KLASORU, ad))
                except OSError:
                    pass
    except OSError:
        pass


def bagimlilik_gerekli_mi():
    """requirements.txt degistiyse True (yeni kutuphane kurulmali)."""
    yol = os.path.join(PROGRAM_KLASORU, "requirements.txt")
    if not os.path.isfile(yol):
        return False
    h = sha256_dosya(yol)
    d = _durum_oku()
    if d.get("requirements") == h:
        return False
    return h


def bagimlilik_kuruldu(h):
    d = _durum_oku()
    d["requirements"] = h
    _durum_yaz(d)


def python_exe():
    py = sys.executable or "python"
    if py.lower().endswith("pythonw.exe"):
        aday = py[:-len("pythonw.exe")] + "python.exe"
        if os.path.isfile(aday):
            py = aday
    return py


def bagimliliklari_kur(h=None):
    """requirements.txt'deki kutuphaneleri sessizce kurar. True = basarili."""
    import subprocess
    h = h or bagimlilik_gerekli_mi()
    if not h:
        return True
    py = python_exe()
    req = os.path.join(PROGRAM_KLASORU, "requirements.txt")
    bayrak = 0x08000000 if sys.platform.startswith("win") else 0
    for ek in ([], ["--user"]):
        try:
            r = subprocess.run([py, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                                "--no-warn-script-location", "-r", req] + ek,
                               capture_output=True, timeout=900, creationflags=bayrak)
        except Exception:
            return False
        if r.returncode == 0:
            bagimlilik_kuruldu(h)
            return True
    return False


def bagimliliklari_kur_bekle(h):
    """Guncellemeden hemen sonra (arayuz acilmadan) yeni kutuphaneleri kurar; kucuk bir bekleme penceresi gosterir."""
    import threading
    sonuc = {}
    t = threading.Thread(target=lambda: sonuc.update(ok=bagimliliklari_kur(h)), daemon=True)
    t.start()
    try:
        import tkinter as tk
        k = tk.Tk()
        k.title("PDF PRO")
        k.overrideredirect(True)
        k.configure(bg="#312E81")
        tk.Label(k, text="PDF PRO güncelleniyor…\nYeni bileşenler kuruluyor, lütfen bekleyin.", bg="#312E81", fg="white",
                 font=("Segoe UI", 11), padx=30, pady=24).pack()
        k.update_idletasks()
        x = (k.winfo_screenwidth() - k.winfo_width()) // 2
        y = (k.winfo_screenheight() - k.winfo_height()) // 3
        k.geometry(f"+{x}+{y}")

        def bak():
            if t.is_alive():
                k.after(300, bak)
            else:
                k.destroy()
        bak()
        k.mainloop()
    except Exception:
        t.join(900)
    return sonuc.get("ok", False)
