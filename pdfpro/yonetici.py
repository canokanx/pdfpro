# -*- coding: utf-8 -*-
"""
PDF PRO - Yonetici paneli
- Kullanici adi + sifre ile giris (sifre PBKDF2 ile ozetlenir, kendisi saklanmaz)
- GitHub ayarlari, imza anahtari (gizli anahtar ve GitHub tokeni yonetici sifresiyle sifrelenir)
- Yayinla: testler -> surum numarasi -> kaynak dosyalar GitHub deposuna (main) -> imzali surum (Release)
- Surum gecmisi, kaynak arsivi, yeni kullanici icin kurulum paketi
Gizli bilgiler sadece yoneticinin bilgisayarinda (%APPDATA%\\PDFPRO) durur, pakete girmez.
"""
import base64
import datetime
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import webbrowser
import zipfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

from . import ed25519
from . import guncelleme as GN
from .surum import SURUM, surum_tuple

WINDOWS = sys.platform.startswith("win")
VERI_KLASORU = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "PDFPRO")
VERI_DOSYASI = os.path.join(VERI_KLASORU, "yonetici.json")
ARSIV = os.path.join(VERI_KLASORU, "arsiv")
ITER = 240000

# Varsayilan yonetici kimligi (sifrenin PBKDF2 ozeti; sifrenin kendisi degil).
# Sifre panelden degistirilince yeni ozet bu bilgisayarda %APPDATA%\PDFPRO\yonetici.json'a yazilir.
VARSAYILAN_KIMLIK = None


# ------------------------------------------------------------------ sifre / sifreleme
def sifre_ozeti(sifre, tuz, iterasyon=ITER):
    return hashlib.pbkdf2_hmac("sha256", sifre.encode("utf-8"), tuz, iterasyon).hex()


def kimlik_olustur(kullanici, sifre):
    tuz = os.urandom(16)
    return {"kullanici": kullanici, "tuz": tuz.hex(), "ozet": sifre_ozeti(sifre, tuz), "iter": ITER}


def _anahtar(sifre, tuz):
    return hashlib.pbkdf2_hmac("sha256", ("kasa:" + sifre).encode("utf-8"), tuz, ITER)


def _akis(anahtar, nonce, n):
    cikti = b""
    sayac = 0
    while len(cikti) < n:
        cikti += hashlib.sha256(anahtar + nonce + sayac.to_bytes(8, "big")).digest()
        sayac += 1
    return cikti[:n]


def kasa_kilitle(sifre, veri):
    """veri (dict) -> sifreli sozluk"""
    tuz, nonce = os.urandom(16), os.urandom(16)
    k = _anahtar(sifre, tuz)
    duz = json.dumps(veri).encode("utf-8")
    sifreli = bytes(a ^ b for a, b in zip(duz, _akis(k, nonce, len(duz))))
    mac = hmac.new(k, nonce + sifreli, hashlib.sha256).hexdigest()
    return {"tuz": tuz.hex(), "nonce": nonce.hex(), "veri": sifreli.hex(), "mac": mac}


def kasa_ac(sifre, kasa):
    if not kasa:
        return {}
    k = _anahtar(sifre, bytes.fromhex(kasa["tuz"]))
    nonce, sifreli = bytes.fromhex(kasa["nonce"]), bytes.fromhex(kasa["veri"])
    if not hmac.compare_digest(hmac.new(k, nonce + sifreli, hashlib.sha256).hexdigest(), kasa["mac"]):
        raise ValueError("Kasa açılamadı (şifre değişmiş olabilir).")
    return json.loads(bytes(a ^ b for a, b in zip(sifreli, _akis(k, nonce, len(sifreli)))).decode("utf-8"))


class Veri:
    """Yoneticinin yerel bilgileri (APPDATA)."""

    def __init__(self):
        try:
            with open(VERI_DOSYASI, encoding="utf-8") as f:
                self.d = json.load(f)
        except Exception:
            self.d = {}

    def kaydet(self):
        os.makedirs(VERI_KLASORU, exist_ok=True)
        gecici = VERI_DOSYASI + ".tmp"
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(self.d, f, ensure_ascii=False, indent=1)
        os.replace(gecici, VERI_DOSYASI)

    def kimlik(self):
        return self.d.get("kimlik") or VARSAYILAN_KIMLIK

    def dogrula(self, kullanici, sifre):
        k = self.kimlik()
        if not k:
            return False
        ozet = sifre_ozeti(sifre, bytes.fromhex(k["tuz"]), k.get("iter", ITER))
        return (hmac.compare_digest(ozet, k["ozet"])
                and kullanici.strip().casefold() == k["kullanici"].strip().casefold())


# ------------------------------------------------------------------ GitHub
def _gh(yol, token, **kw):
    return GN.istek(f"{GN.API}{yol}", token=token, **kw)


def git_blob_sha(veri):
    return hashlib.sha1(b"blob %d\0" % len(veri) + veri).hexdigest()


def baglanti_dene(repo, token):
    kullanici = _gh("/user", token)["login"]
    try:
        r = _gh(f"/repos/{repo}", token)
    except GN.GuncellemeHatasi as e:
        if getattr(e, "kod", 0) == 404:
            return kullanici, None
        raise
    return kullanici, r


def depo_olustur(token, ad, gizli=False):
    return _gh("/user/repos", token, veri={"name": ad, "private": gizli, "auto_init": True,
                                           "description": "PDF PRO - kaynak dosyalar ve otomatik güncellemeler"})


def surumleri_listele(repo, token=None):
    return _gh(f"/repos/{repo}/releases?per_page=30", token)


def surum_paketi(repo, rel, token=None):
    """Bir surumun guncelleme.json'unu indirir (dogrulanmamis ham sozluk)."""
    v = next((a for a in rel.get("assets", []) if a.get("name") == "guncelleme.json"), None)
    if not v:
        raise GN.GuncellemeHatasi("Bu sürümde güncelleme bilgisi yok.")
    if token:
        ham = GN.istek(v["url"], token=token, basliklar={"Accept": "application/octet-stream"}, ham=True)
    else:
        ham = GN.istek(v["browser_download_url"], ham=True)
    return json.loads(ham.decode("utf-8"))


def _surum_dosyasina_yaz(surum):
    yol = os.path.join(GN.PROGRAM_KLASORU, "pdfpro", "surum.py")
    with open(yol, encoding="utf-8") as f:
        metin = f.read()
    metin = re.sub(r'^SURUM = ".*?"', f'SURUM = "{surum}"', metin, count=1, flags=re.M)
    with open(yol, "w", encoding="utf-8") as f:
        f.write(metin)


def guncelleme_ayarini_yaz(repo, acik_hex, okuma_tokeni=None):
    d = GN.ayar_oku()
    d.update({"repo": repo, "acik_anahtar": acik_hex, "otomatik": True})
    if okuma_tokeni:
        d["okuma_tokeni"] = okuma_tokeni
    else:
        d.pop("okuma_tokeni", None)
    with open(GN.AYAR_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def paket_zip(hedef, dosyalar=None, ilerleme=None):
    dosyalar = dosyalar or GN.paket_dosyalari()
    with zipfile.ZipFile(hedef, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for k, (goreli, tam) in enumerate(sorted(dosyalar.items())):
            if ilerleme and k % 10 == 0:
                ilerleme(k, len(dosyalar), goreli)
            z.write(tam, "PDF_PRO/" + goreli)
    return hedef


def degisen_dosyalar(son_manifest):
    """Son yayindan bu yana degisen / eklenen / silinen dosyalar."""
    simdi = {y: GN.sha256_dosya(t) for y, t in GN.paket_dosyalari().items()
             if y not in ("pdfpro/surum.py", "guncelleme_ayar.json")}
    eski = {y: s for y, s in (son_manifest or {}).get("dosyalar", {}).items()
            if y not in ("pdfpro/surum.py", "guncelleme_ayar.json")}
    eklenen = sorted(y for y in simdi if y not in eski)
    degisen = sorted(y for y in simdi if y in eski and simdi[y] != eski[y])
    silinen = sorted(y for y in eski if y not in simdi)
    return eklenen, degisen, silinen


def testleri_calistir():
    yol = os.path.join(GN.PROGRAM_KLASORU, "testler", "simulasyon.py")
    if not os.path.isfile(yol):
        return True, "Test dosyası yok."
    r = subprocess.run([GN.python_exe(), "-X", "utf8", yol], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1200, cwd=GN.PROGRAM_KLASORU,
                       creationflags=0x08000000 if WINDOWS else 0)
    cikti = (r.stdout or "") + (r.stderr or "")
    try:   # tam sonuc dosyaya (hata ayiklamak icin)
        with open(os.path.join(GN.PROGRAM_KLASORU, "testler", "son_test_sonucu.txt"), "w", encoding="utf-8") as f:
            f.write(cikti)
    except OSError:
        pass
    if r.returncode != 0:
        # once ozet: sadece basarisiz senaryolarin adlari
        hatali = [s.strip() for s in cikti.splitlines() if s.strip().startswith("✖")]
        cikti = "Başarısız senaryolar:\n" + "\n".join(hatali) + "\n\n(Ayrıntı: testler\\son_test_sonucu.txt)\n\n" + cikti[-1500:]
    return r.returncode == 0, cikti[-3000:]


def yayinla(repo, token, gizli, surum, notlar, ilerleme=None, iptal=None):
    """Kaynaklari GitHub'a gonderir ve imzali surum yayinlar. Dondurur: (manifest, release_url, zip_yolu)"""
    il = ilerleme or (lambda *a: None)
    acik_hex = ed25519.acik_anahtar(gizli).hex()
    eski_surum = SURUM
    _surum_dosyasina_yaz(surum)
    try:
        guncelleme_ayarini_yaz(repo, acik_hex, GN.ayar_oku().get("okuma_tokeni"))
        dosyalar = GN.paket_dosyalari()
        bilgiler = {}
        for k, (y, t) in enumerate(dosyalar.items()):
            with open(t, "rb") as f:
                veri = f.read()
            bilgiler[y] = (hashlib.sha256(veri).hexdigest(), git_blob_sha(veri), t)
        il(1, 10, "GitHub deposu okunuyor")
        bilgi = _gh(f"/repos/{repo}", token)
        dal = bilgi.get("default_branch") or "main"
        try:
            ref = _gh(f"/repos/{repo}/git/ref/heads/{dal}", token)
        except GN.GuncellemeHatasi as e:
            if getattr(e, "kod", 0) not in (404, 409):
                raise
            _gh(f"/repos/{repo}/contents/README.md", token, yontem="PUT",
                veri={"message": "İlk kayıt", "content": base64.b64encode(b"# PDF PRO\n").decode()})
            ref = _gh(f"/repos/{repo}/git/ref/heads/{dal}", token)
        ust_sha = ref["object"]["sha"]
        ust = _gh(f"/repos/{repo}/git/commits/{ust_sha}", token)
        agac = _gh(f"/repos/{repo}/git/trees/{ust['tree']['sha']}?recursive=1", token)
        mevcut = {o["path"]: o["sha"] for o in agac.get("tree", []) if o.get("type") == "blob"}
        gonderilecek = [y for y, (_, gs, _) in bilgiler.items() if mevcut.get(y) != gs]
        for k, y in enumerate(gonderilecek):
            if iptal and iptal():
                raise GN.GuncellemeHatasi("İptal edildi.")
            il(1 + k * 6 // max(1, len(gonderilecek)), 10, f"Yükleniyor: {y}")
            with open(bilgiler[y][2], "rb") as f:
                icerik = base64.b64encode(f.read()).decode()
            _gh(f"/repos/{repo}/git/blobs", token, veri={"content": icerik, "encoding": "base64"}, zaman=300)
        girdiler = [{"path": y, "mode": "100755" if y.endswith((".bat", ".exe")) else "100644", "type": "blob",
                     "sha": gs} for y, (_, gs, _) in sorted(bilgiler.items())]
        if "README.md" in mevcut and "README.md" not in bilgiler:
            girdiler.append({"path": "README.md", "mode": "100644", "type": "blob", "sha": mevcut["README.md"]})
        il(7, 10, "Kayıt (commit) oluşturuluyor")
        yeni_agac = _gh(f"/repos/{repo}/git/trees", token, veri={"tree": girdiler}, zaman=300)
        tarih = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        commit = _gh(f"/repos/{repo}/git/commits", token,
                     veri={"message": f"PDF PRO {surum}\n\n{notlar}".strip(), "tree": yeni_agac["sha"], "parents": [ust_sha]})
        _gh(f"/repos/{repo}/git/refs/heads/{dal}", token, yontem="PATCH", veri={"sha": commit["sha"]})
        manifest = {"surum": surum, "commit": commit["sha"], "tarih": tarih, "notlar": notlar,
                    "dosyalar": {y: b[0] for y, b in sorted(bilgiler.items())}}
        metin = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
        imza = ed25519.imzala(gizli, metin.encode("utf-8")).hex()
        paket = json.dumps({"manifest": metin, "imza": imza}, ensure_ascii=False).encode("utf-8")
        il(8, 10, "Sürüm yayınlanıyor")
        rel = _gh(f"/repos/{repo}/releases", token, veri={"tag_name": f"v{surum}", "target_commitish": commit["sha"],
                                                           "name": f"PDF PRO {surum}", "body": notlar or f"PDF PRO {surum}"})
        yukle = rel["upload_url"].split("{")[0]
        GN.istek(f"{yukle}?name=guncelleme.json", veri=paket, token=token,
                 basliklar={"Content-Type": "application/json"}, zaman=120)
        os.makedirs(ARSIV, exist_ok=True)
        zip_yolu = os.path.join(ARSIV, f"pdfpro-{surum}.zip")
        il(9, 10, "Tam paket hazırlanıyor")
        paket_zip(zip_yolu, dosyalar)
        with open(zip_yolu, "rb") as f:
            GN.istek(f"{yukle}?name=pdfpro-{surum}.zip", veri=f.read(), token=token,
                     basliklar={"Content-Type": "application/zip"}, zaman=900)
        return manifest, rel.get("html_url", ""), zip_yolu
    except Exception:
        _surum_dosyasina_yaz(eski_surum)          # yayin olmadi: surum numarasini geri al
        raise


def sonraki_surum(s):
    a, b, c = surum_tuple(s)
    return f"{a}.{b}.{c + 1}"


# ================================================================== ARAYUZ
class GirisPenceresi(tk.Toplevel):
    def __init__(self, u, veri, ilk=False):
        super().__init__(u)
        from .diyaloglar import baslik_rengi
        self.u, self.veri, self.ilk, self.sonuc = u, veri, ilk, None
        self.title("Yönetici Girişi")
        self.configure(bg="white")
        self.transient(u)
        self.resizable(False, False)
        renk = baslik_rengi(u)
        bant = tk.Frame(self, bg=renk)
        bant.pack(fill="x")
        tk.Label(bant, text="🛡  Yönetici " + ("Hesabı Oluştur" if ilk else "Girişi"), bg=renk, fg="white",
                 font=(u_font(), 13, "bold")).pack(anchor="w", padx=18, pady=(12, 10))
        g = tk.Frame(self, bg="white", padx=22, pady=14)
        g.pack(fill="both")
        if ilk:
            tk.Label(g, text="Bu bilgisayarda henüz yönetici hesabı yok. Kullanıcı adı ve şifre belirleyin.",
                     bg="white", fg="#64748B", font=(u_font(), 9), wraplength=330, justify="left").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        tk.Label(g, text="Kullanıcı adı:", bg="white", font=(u_font(), 10)).grid(row=1, column=0, sticky="w", pady=4)
        self.k = ttk.Entry(g, width=28)
        self.k.grid(row=1, column=1, pady=4)
        tk.Label(g, text="Şifre:", bg="white", font=(u_font(), 10)).grid(row=2, column=0, sticky="w", pady=4)
        self.s = ttk.Entry(g, width=28, show="•")
        self.s.grid(row=2, column=1, pady=4)
        if ilk:
            tk.Label(g, text="Şifre (tekrar):", bg="white", font=(u_font(), 10)).grid(row=3, column=0, sticky="w", pady=4)
            self.s2 = ttk.Entry(g, width=28, show="•")
            self.s2.grid(row=3, column=1, pady=4)
        self.hata = tk.Label(g, text="", bg="white", fg="#E11D48", font=(u_font(), 9))
        self.hata.grid(row=4, column=0, columnspan=2, sticky="w")
        d = tk.Frame(self, bg="white", padx=22, pady=12)
        d.pack(fill="x")
        ttk.Button(d, text="Vazgeç", style="Ikincil.TButton", command=self.destroy).pack(side="right")
        ttk.Button(d, text="Giriş" if not ilk else "Oluştur", style="Ana.TButton", command=self._tamam).pack(side="right", padx=8)
        self.bind("<Return>", lambda e: self._tamam())
        self.bind("<Escape>", lambda e: self.destroy())
        self._deneme = 0
        self.update_idletasks()
        x = u.winfo_rootx() + (u.winfo_width() - self.winfo_width()) // 2
        y = u.winfo_rooty() + (u.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.k.focus_set()

    def _tamam(self):
        k, s = self.k.get().strip(), self.s.get()
        if self.ilk:
            if len(k) < 3 or len(s) < 6:
                self.hata.config(text="Kullanıcı adı en az 3, şifre en az 6 karakter olmalı.")
                return
            if s != self.s2.get():
                self.hata.config(text="Şifreler aynı değil.")
                return
            self.veri.d["kimlik"] = kimlik_olustur(k, s)
            self.veri.kaydet()
            self.sonuc = (k, s)
            self.destroy()
            return
        self.hata.config(text="Kontrol ediliyor…")
        self.update_idletasks()
        if self.veri.dogrula(k, s):
            self.sonuc = (k, s)
            self.destroy()
            return
        self._deneme += 1
        self.s.delete(0, "end")
        self.hata.config(text="Kullanıcı adı veya şifre yanlış.")
        if self._deneme >= 5:
            self.after(200, self.destroy)

    def ac(self):
        self.grab_set()
        self.wait_window()
        return self.sonuc


def u_font():
    return "Segoe UI" if WINDOWS else "DejaVu Sans"


class YoneticiPaneli(tk.Toplevel):
    def __init__(self, u, kullanici, sifre, veri):
        super().__init__(u)
        from .diyaloglar import baslik_rengi
        self.u, self.kullanici, self.sifre, self.veri = u, kullanici, sifre, veri
        try:
            self.gizli = kasa_ac(sifre, veri.d.get("kasa"))
        except Exception:
            self.gizli = {}
        self.title("PDF PRO — Yönetici Paneli")
        self.configure(bg="white")
        self.geometry("900x640")
        self.transient(u)
        F = u_font()
        renk = baslik_rengi(u)
        bant = tk.Frame(self, bg=renk)
        bant.pack(fill="x")
        tk.Label(bant, text="🛡  Yönetici Paneli", bg=renk, fg="white", font=(F, 14, "bold")).pack(side="left", padx=18, pady=10)
        tk.Label(bant, text=f"{kullanici}  ·  PDF PRO {SURUM}", bg=renk, fg="#E0E7FF", font=(F, 10)).pack(side="right", padx=18)
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=12, pady=10)
        self._genel()
        self._yayin()
        self._surumler()
        self._kaynak()
        self._ayarlar()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # -------------------------------------------------- yardimcilar
    def _sekme(self, ad):
        f = tk.Frame(self.nb, bg="white", padx=16, pady=12)
        self.nb.add(f, text=f"  {ad}  ")
        return f

    def _etiket(self, ust, metin, kalin=False, soluk=False, **kw):
        return tk.Label(ust, text=metin, bg="white", fg="#64748B" if soluk else "#1E293B", justify="left",
                        font=(u_font(), 10 if not soluk else 9, "bold" if kalin else "normal"), **kw)

    def repo(self):
        return self.veri.d.get("repo") or GN.ayar_oku().get("repo", "")

    def token(self):
        return self.gizli.get("token", "")

    def gizli_anahtar(self):
        h = self.gizli.get("imza_anahtari")
        return bytes.fromhex(h) if h else None

    def _kasa_kaydet(self):
        self.veri.d["kasa"] = kasa_kilitle(self.sifre, self.gizli)
        self.veri.kaydet()

    def _arka(self, baslik, fonk, bitince):
        from .cekirdek import PdfProHata

        def sarmal(il, ip):
            try:
                return fonk(il, ip)
            except GN.GuncellemeHatasi as e:
                raise PdfProHata(str(e))
        self.u.calistir(baslik, sarmal, bitince, iptal_edilebilir=True)

    # -------------------------------------------------- GENEL
    def _genel(self):
        f = self._sekme("Genel")
        self._etiket(f, "Bu bilgisayar", kalin=True).pack(anchor="w")
        self._etiket(f, f"Sürüm: {SURUM}\nProgram klasörü: {GN.PROGRAM_KLASORU}", soluk=True).pack(anchor="w", pady=(2, 10))
        self._etiket(f, "Güncelleme sunucusu (GitHub)", kalin=True).pack(anchor="w")
        self.genel_durum = self._etiket(f, "—", soluk=True)
        self.genel_durum.pack(anchor="w", pady=(2, 8))
        d = tk.Frame(f, bg="white")
        d.pack(anchor="w")
        ttk.Button(d, text="🔄 Sunucudaki sürümü kontrol et", style="Ikincil.TButton", command=self._kontrol).pack(side="left")
        ttk.Button(d, text="📁 Program klasörü", style="Ikincil.TButton",
                   command=lambda: _ac(GN.PROGRAM_KLASORU)).pack(side="left", padx=6)
        ttk.Button(d, text="🌐 GitHub'da aç", style="Ikincil.TButton",
                   command=lambda: self.repo() and webbrowser.open(f"https://github.com/{self.repo()}")).pack(side="left")
        tk.Frame(f, bg="#E2E8F0", height=1).pack(fill="x", pady=14)
        self._etiket(f, "Nasıl çalışır?", kalin=True).pack(anchor="w")
        self._etiket(f, "1) Programda değişiklik yapılır (kaynak dosyalar bu bilgisayarda).\n"
                        "2) 'Yayınla' sekmesinden yeni sürüm yayınlanır: dosyalar GitHub'a gider, sürüm imzalanır.\n"
                        "3) Diğer bilgisayarlardaki PDF PRO açılışta yeni sürümü görür, sadece değişen dosyaları indirir,\n"
                        "   bir sonraki açılışta kendini günceller. İmza tutmazsa güncellemeyi reddeder.\n"
                        "4) Yeni sürüm açılmazsa program otomatik olarak bir önceki sürüme döner.",
                     soluk=True).pack(anchor="w", pady=4)
        self._durum_guncelle()

    def _durum_guncelle(self):
        r = self.repo()
        if not r:
            self.genel_durum.config(text="Ayarlanmadı → 'Ayarlar' sekmesinden GitHub deposunu ve anahtarı girin.")
        else:
            imza = "var" if self.gizli_anahtar() else "YOK (Ayarlar'dan oluşturun)"
            self.genel_durum.config(text=f"Depo: {r}\nİmza anahtarı: {imza}")

    def _kontrol(self):
        def is_(il, ip):
            return GN.son_surum_bilgisi()

        def bitti(m):
            if not m:
                messagebox.showinfo("PDF PRO", "Sunucuda yayınlanmış sürüm yok (ya da ayarlar eksik).", parent=self)
            else:
                messagebox.showinfo("PDF PRO", f"Sunucudaki son sürüm: {m['surum']}  ({m.get('tarih', '')})\n"
                                               f"Bu bilgisayar: {SURUM}\nİmza: geçerli ✔", parent=self)
        self._arka("Sunucu kontrol ediliyor", is_, bitti)

    # -------------------------------------------------- YAYINLA
    def _yayin(self):
        f = self._sekme("Yayınla")
        ust = tk.Frame(f, bg="white")
        ust.pack(fill="x")
        self._etiket(ust, "Yeni sürüm:").pack(side="left")
        self.yeni_surum = ttk.Entry(ust, width=10)
        self.yeni_surum.insert(0, sonraki_surum(SURUM))
        self.yeni_surum.pack(side="left", padx=6)
        self._etiket(ust, f"(şu an {SURUM})", soluk=True).pack(side="left")
        self.test_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ust, text="Önce testleri çalıştır (önerilir)", variable=self.test_var).pack(side="right")
        self._etiket(f, "Değişiklik notları (kullanıcılar görür):").pack(anchor="w", pady=(10, 2))
        self.notlar = tk.Text(f, height=6, font=(u_font(), 10), relief="solid", bd=1, wrap="word")
        self.notlar.pack(fill="x")
        self._etiket(f, "Son yayından bu yana değişen dosyalar:").pack(anchor="w", pady=(10, 2))
        self.degisen = scrolledtext.ScrolledText(f, height=9, font=("Consolas" if WINDOWS else "DejaVu Sans Mono", 9),
                                                 relief="solid", bd=1, state="disabled")
        self.degisen.pack(fill="both", expand=True)
        d = tk.Frame(f, bg="white")
        d.pack(fill="x", pady=(10, 0))
        ttk.Button(d, text="🔍 Değişiklikleri yenile", style="Ikincil.TButton", command=self._degisenleri_goster).pack(side="left")
        ttk.Button(d, text="🚀 Yayınla", style="Ana.TButton", command=self._yayinla).pack(side="right")
        self.after(300, self._degisenleri_goster)

    def _degisenleri_goster(self):
        ek, deg, sil = degisen_dosyalar(self.veri.d.get("son_manifest"))
        metin = []
        if not self.veri.d.get("son_manifest"):
            metin.append("(Bu bilgisayardan henüz yayın yapılmadı — ilk yayında tüm dosyalar gönderilir.)\n")
        metin += [f"+ {y}" for y in ek] + [f"~ {y}" for y in deg] + [f"- {y}" for y in sil]
        if not (ek or deg or sil) and self.veri.d.get("son_manifest"):
            metin.append("Değişiklik yok.")
        self.degisen.config(state="normal")
        self.degisen.delete("1.0", "end")
        self.degisen.insert("1.0", "\n".join(metin))
        self.degisen.config(state="disabled")

    def _yayinla(self):
        repo, token, gizli = self.repo(), self.token(), self.gizli_anahtar()
        if not (repo and token and gizli):
            messagebox.showwarning("PDF PRO", "Önce 'Ayarlar' sekmesinde GitHub deposu, token ve imza anahtarını ayarlayın.", parent=self)
            self.nb.select(4)
            return
        surum = self.yeni_surum.get().strip()
        if not re.fullmatch(r"\d+\.\d+\.\d+", surum):
            messagebox.showwarning("PDF PRO", "Sürüm 4.0.1 biçiminde olmalı.", parent=self)
            return
        if surum_tuple(surum) <= surum_tuple(SURUM):
            messagebox.showwarning("PDF PRO", f"Yeni sürüm şu ankinden ({SURUM}) büyük olmalı.", parent=self)
            return
        notlar = self.notlar.get("1.0", "end").strip()
        if not messagebox.askyesno("PDF PRO", f"PDF PRO {surum} yayınlansın mı?\n\n"
                                              "Tüm kullanıcılar bir sonraki açılışta bu sürüme güncellenecek.", parent=self):
            return
        testler = self.test_var.get()

        def is_(il, ip):
            if testler:
                il(0, 10, "Testler çalışıyor (birkaç dakika)")
                ok, cikti = testleri_calistir()
                if not ok:
                    raise GN.GuncellemeHatasi("Testler BAŞARISIZ — yayın yapılmadı.\n\n" + cikti[:2500])
            return yayinla(repo, token, gizli, surum, notlar, il, ip)

        def bitti(r):
            manifest, url, zip_yolu = r
            self.veri.d["son_manifest"] = manifest
            self.veri.kaydet()
            self.u.sonuc_goster(f"PDF PRO {surum} yayınlandı. Kullanıcılar bir sonraki açılışta güncellenecek.\n"
                                "(Kendi bilgisayarınızın sürüm numarası da güncellendi; programı yeniden başlatın.)",
                                zip_yolu)
            self._degisenleri_goster()

        self._arka("Yayınlanıyor", is_, bitti)

    # -------------------------------------------------- SURUMLER
    def _surumler(self):
        f = self._sekme("Sürümler")
        self._etiket(f, "GitHub'da yayınlanmış sürümler (en yeni üstte):").pack(anchor="w")
        self.surum_lst = tk.Listbox(f, font=(u_font(), 10), height=10, activestyle="none", selectbackground="#4F46E5")
        self.surum_lst.pack(fill="x", pady=4)
        self.surum_not = scrolledtext.ScrolledText(f, height=8, font=(u_font(), 9), relief="solid", bd=1, wrap="word")
        self.surum_not.pack(fill="both", expand=True)
        d = tk.Frame(f, bg="white")
        d.pack(fill="x", pady=(8, 0))
        ttk.Button(d, text="🔄 Listele", style="Ikincil.TButton", command=self._surumleri_getir).pack(side="left")
        ttk.Button(d, text="🌐 GitHub'da aç", style="Ikincil.TButton", command=self._surum_ac).pack(side="left", padx=6)
        ttk.Button(d, text="⬇ Kaynak zip'ini indir", style="Ikincil.TButton", command=self._surum_zip).pack(side="left")
        ttk.Button(d, text="↩ Bu sürümü bu bilgisayara kur", style="Ana.TButton", command=self._surum_kur).pack(side="right")
        self._rels = []
        self.surum_lst.bind("<<ListboxSelect>>", self._surum_sec)

    def _surumleri_getir(self):
        repo = self.repo()
        if not repo:
            return

        def bitti(rels):
            self._rels = rels
            self.surum_lst.delete(0, "end")
            for r in rels:
                tarih = (r.get("published_at") or "")[:10]
                self.surum_lst.insert("end", f"  {r.get('tag_name')}    {tarih}    {r.get('name', '')}")
        self._arka("Sürümler alınıyor", lambda il, ip: surumleri_listele(repo, self.token() or None), bitti)

    def _secili_rel(self):
        s = self.surum_lst.curselection()
        return self._rels[s[0]] if s else None

    def _surum_sec(self, e=None):
        r = self._secili_rel()
        self.surum_not.delete("1.0", "end")
        if r:
            self.surum_not.insert("1.0", r.get("body") or "(not yok)")

    def _surum_ac(self):
        r = self._secili_rel()
        if r:
            webbrowser.open(r.get("html_url", ""))

    def _surum_zip(self):
        r = self._secili_rel()
        if not r:
            return
        v = next((a for a in r.get("assets", []) if a.get("name", "").endswith(".zip")), None)
        if v:
            webbrowser.open(v["browser_download_url"])
        else:
            webbrowser.open(r.get("zipball_url", ""))

    def _surum_kur(self):
        r = self._secili_rel()
        if not r:
            messagebox.showinfo("PDF PRO", "Listeden bir sürüm seçin.", parent=self)
            return
        if not messagebox.askyesno("PDF PRO", f"{r.get('tag_name')} bu bilgisayara kurulsun mu?\n"
                                              "(Sadece bu bilgisayar; diğer kullanıcılar etkilenmez. "
                                              "Program yeniden başlatılınca uygulanır.)", parent=self):
            return
        repo, token = self.repo(), self.token() or None
        acik = GN.ayar_oku().get("acik_anahtar") or (ed25519.acik_anahtar(self.gizli_anahtar()).hex() if self.gizli_anahtar() else "")

        def is_(il, ip):
            m = GN.manifest_dogrula(surum_paketi(repo, r, token), acik)
            ayar = dict(GN.ayar_oku(), repo=repo)
            if token:
                ayar["okuma_tokeni"] = token
            GN.guncelleme_indir(m, ayar, il)
            return m

        def bitti(m):
            if messagebox.askyesno("PDF PRO", f"{m['surum']} hazır. Program şimdi yeniden başlatılsın mı?", parent=self):
                self.destroy()
                self.u.yeniden_baslat()
        self._arka("Sürüm indiriliyor", is_, bitti)

    # -------------------------------------------------- KAYNAK
    def _kaynak(self):
        f = self._sekme("Kaynak Dosyalar")
        dosyalar = GN.paket_dosyalari()
        boyut = sum(os.path.getsize(t) for t in dosyalar.values())
        self._etiket(f, "Kaynak dosyaların en güncel hali", kalin=True).pack(anchor="w")
        self._etiket(f, f"Program klasöründe {len(dosyalar)} dosya ({boyut / 1048576:.1f} MB) pakete giriyor.\n"
                        "Her yayında tüm kaynak GitHub deposuna (sürüm geçmişiyle) gönderilir ve tam paket\n"
                        f"bu bilgisayarda arşivlenir: {ARSIV}", soluk=True).pack(anchor="w", pady=(2, 10))
        d = tk.Frame(f, bg="white")
        d.pack(anchor="w")
        ttk.Button(d, text="💾 Şimdi kaynak yedeği al (zip)", style="Ikincil.TButton", command=self._yedek_al).pack(side="left")
        ttk.Button(d, text="🗄 Arşiv klasörü", style="Ikincil.TButton",
                   command=lambda: (os.makedirs(ARSIV, exist_ok=True), _ac(ARSIV))).pack(side="left", padx=6)
        tk.Frame(f, bg="#E2E8F0", height=1).pack(fill="x", pady=14)
        self._etiket(f, "Yeni kullanıcı için kurulum paketi", kalin=True).pack(anchor="w")
        self._etiket(f, "Tek bir zip dosyası hazırlar. Yeni bilgisayarda zip'i açıp KURULUM.bat'ı çalıştırmak yeterli;\n"
                        "o bilgisayar da bundan sonra otomatik güncellenir.", soluk=True).pack(anchor="w", pady=(2, 8))
        ttk.Button(f, text="📦 Kurulum paketi oluştur", style="Ana.TButton", command=self._kurulum_paketi).pack(anchor="w")
        tk.Frame(f, bg="#E2E8F0", height=1).pack(fill="x", pady=14)
        self._etiket(f, "Pakete GİRMEYENLER (kişisel): ayarlar.json (yapay zeka anahtarı dahil), yedekler, hata kaydı, "
                        "önbellekler.", soluk=True).pack(anchor="w")

    def _yedek_al(self):
        os.makedirs(ARSIV, exist_ok=True)
        hedef = os.path.join(ARSIV, f"kaynak_{SURUM}_{datetime.datetime.now():%Y%m%d_%H%M}.zip")
        self._arka("Kaynak yedeği alınıyor", lambda il, ip: paket_zip(hedef, None, il),
                   lambda r: self.u.sonuc_goster("Kaynak yedeği alındı.", r))

    def _kurulum_paketi(self):
        if not GN.ayar_oku().get("repo"):
            if not messagebox.askyesno("PDF PRO", "Güncelleme ayarı yapılmamış; bu paketle kurulan bilgisayar otomatik "
                                                  "güncellenmez. Yine de oluşturulsun mu?", parent=self):
                return
        masaustu = os.path.join(os.path.expanduser("~"), "Desktop")
        y = filedialog.asksaveasfilename(parent=self, initialdir=masaustu, initialfile=f"PDF_PRO_Kurulum_{SURUM}.zip",
                                         defaultextension=".zip", filetypes=[("Zip", "*.zip")])
        if not y:
            return
        self._arka("Kurulum paketi hazırlanıyor", lambda il, ip: paket_zip(os.path.normpath(y), None, il),
                   lambda r: self.u.sonuc_goster("Kurulum paketi hazır. Yeni bilgisayarda zip'i açıp KURULUM.bat'ı çalıştırın.", r))

    # -------------------------------------------------- AYARLAR
    def _ayarlar(self):
        f = self._sekme("Ayarlar")
        g = tk.Frame(f, bg="white")
        g.pack(fill="x")
        self._etiket(g, "GitHub deposu:").grid(row=0, column=0, sticky="w", pady=4)
        self.repo_e = ttk.Entry(g, width=40)
        self.repo_e.insert(0, self.repo() or "kullaniciadi/pdfpro")
        self.repo_e.grid(row=0, column=1, sticky="w", pady=4)
        self._etiket(g, "kullanıcıadı/depoadı", soluk=True).grid(row=0, column=2, sticky="w", padx=6)
        self._etiket(g, "GitHub token:").grid(row=1, column=0, sticky="w", pady=4)
        self.token_e = ttk.Entry(g, width=40, show="•")
        self.token_e.insert(0, self.token())
        self.token_e.grid(row=1, column=1, sticky="w", pady=4)
        bag = tk.Label(g, text="🔑 Token oluştur", bg="white", fg="#4F46E5", cursor="hand2", font=(u_font(), 9, "underline"))
        bag.grid(row=1, column=2, sticky="w", padx=6)
        bag.bind("<Button-1>", lambda e: webbrowser.open(
            "https://github.com/settings/tokens/new?scopes=repo&description=PDF%20PRO%20yayin"))
        self.gizli_depo = tk.BooleanVar(value=bool(GN.ayar_oku().get("okuma_tokeni")))
        ttk.Checkbutton(g, text="Depo GİZLİ (kullanıcılar okuma tokeniyle indirir)", variable=self.gizli_depo).grid(
            row=2, column=1, columnspan=2, sticky="w")
        self._etiket(g, "Okuma tokeni:").grid(row=3, column=0, sticky="w", pady=4)
        self.okuma_e = ttk.Entry(g, width=40, show="•")
        self.okuma_e.insert(0, GN.ayar_oku().get("okuma_tokeni", ""))
        self.okuma_e.grid(row=3, column=1, sticky="w", pady=4)
        self._etiket(g, "sadece gizli depoda; yalnızca 'okuma' izinli olmalı", soluk=True).grid(row=3, column=2, sticky="w", padx=6)
        d = tk.Frame(f, bg="white")
        d.pack(anchor="w", pady=8)
        ttk.Button(d, text="💾 Kaydet", style="Ana.TButton", command=self._ayar_kaydet).pack(side="left")
        ttk.Button(d, text="🔌 Bağlantıyı dene", style="Ikincil.TButton", command=self._baglanti).pack(side="left", padx=6)
        ttk.Button(d, text="➕ Depoyu oluştur", style="Ikincil.TButton", command=self._depo_olustur).pack(side="left")
        tk.Frame(f, bg="#E2E8F0", height=1).pack(fill="x", pady=12)
        self._etiket(f, "İmza anahtarı", kalin=True).pack(anchor="w")
        self.imza_durum = self._etiket(f, "", soluk=True)
        self.imza_durum.pack(anchor="w", pady=(2, 6))
        ttk.Button(f, text="🔐 İmza anahtarı oluştur", style="Ikincil.TButton", command=self._anahtar_olustur).pack(anchor="w")
        tk.Frame(f, bg="#E2E8F0", height=1).pack(fill="x", pady=12)
        self._etiket(f, "Yönetici hesabı", kalin=True).pack(anchor="w")
        ttk.Button(f, text="🔑 Şifre / kullanıcı adı değiştir", style="Ikincil.TButton", command=self._sifre_degistir).pack(anchor="w", pady=4)
        self._imza_durumu()

    def _imza_durumu(self):
        g = self.gizli_anahtar()
        if g:
            acik = ed25519.acik_anahtar(g).hex()
            dagitilan = GN.ayar_oku().get("acik_anahtar")
            uyum = "✔ programdaki anahtarla aynı" if dagitilan == acik else "⚠ programdaki anahtardan FARKLI (ilk yayında güncellenir)"
            self.imza_durum.config(text=f"Var · {acik[:16]}…  {uyum}")
        else:
            self.imza_durum.config(text="Yok. Yayın yapmadan önce bir kez oluşturun. Gizli kısmı sadece bu bilgisayarda, "
                                        "yönetici şifrenizle şifreli durur.")

    def _ayar_kaydet(self, sessiz=False):
        repo = self.repo_e.get().strip().strip("/")
        repo = re.sub(r"^https?://github\.com/", "", repo).removesuffix(".git")
        if repo and not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            messagebox.showwarning("PDF PRO", "Depo 'kullanıcıadı/depoadı' biçiminde olmalı.", parent=self)
            return False
        self.veri.d["repo"] = repo
        self.gizli["token"] = self.token_e.get().strip()
        self._kasa_kaydet()
        g = self.gizli_anahtar()
        if repo and g:
            okuma = self.okuma_e.get().strip() if self.gizli_depo.get() else None
            guncelleme_ayarini_yaz(repo, ed25519.acik_anahtar(g).hex(), okuma)
        self._durum_guncelle()
        self._imza_durumu()
        if not sessiz:
            messagebox.showinfo("PDF PRO", "Kaydedildi.", parent=self)
        return True

    def _baglanti(self):
        if not self._ayar_kaydet(sessiz=True):
            return
        repo, token = self.repo(), self.token()

        def bitti(r):
            kullanici, depo = r
            if depo is None:
                messagebox.showinfo("PDF PRO", f"Token geçerli (GitHub: {kullanici}).\nAma '{repo}' deposu yok → "
                                               "'Depoyu oluştur'a basın.", parent=self)
            else:
                yetki = depo.get("permissions", {}).get("push")
                messagebox.showinfo("PDF PRO", f"Bağlantı başarılı ✔\nGitHub: {kullanici}\nDepo: {repo} "
                                               f"({'gizli' if depo.get('private') else 'herkese açık'})\n"
                                               f"Yazma izni: {'var' if yetki else 'YOK'}", parent=self)
        self._arka("GitHub deneniyor", lambda il, ip: baglanti_dene(repo, token), bitti)

    def _depo_olustur(self):
        if not self._ayar_kaydet(sessiz=True):
            return
        repo, token = self.repo(), self.token()
        if not repo or not token:
            return
        ad = repo.split("/")[1]
        gizli = self.gizli_depo.get()
        self._arka("Depo oluşturuluyor", lambda il, ip: depo_olustur(token, ad, gizli),
                   lambda r: messagebox.showinfo("PDF PRO", f"Depo oluşturuldu: {r.get('full_name')}", parent=self))

    def _anahtar_olustur(self):
        if self.gizli_anahtar() and not messagebox.askyesno(
                "PDF PRO", "Zaten bir imza anahtarı var. YENİSİ oluşturulursa, eski sürümü kullanan bilgisayarlar\n"
                           "yeni imzalı güncellemeleri KABUL ETMEZ (yeni kurulum paketi gerekir).\n\nYine de oluşturulsun mu?",
                parent=self):
            return
        g, a = ed25519.anahtar_uret()
        self.gizli["imza_anahtari"] = g.hex()
        self._kasa_kaydet()
        if self.repo():
            guncelleme_ayarini_yaz(self.repo(), a.hex(), GN.ayar_oku().get("okuma_tokeni"))
        self._imza_durumu()
        self._durum_guncelle()
        messagebox.showinfo("PDF PRO", "İmza anahtarı oluşturuldu ve şifreli olarak saklandı.", parent=self)

    def _sifre_degistir(self):
        p = GirisPenceresi(self.u, self.veri, ilk=True)
        p.title("Şifre değiştir")
        eski_kimlik = self.veri.d.get("kimlik")
        s = p.ac()
        if not s:
            if eski_kimlik is not None:
                self.veri.d["kimlik"] = eski_kimlik
            return
        self.kullanici, self.sifre = s
        self._kasa_kaydet()          # gizli bilgiler yeni sifreyle yeniden sifrelenir
        messagebox.showinfo("PDF PRO", "Yönetici bilgileri değiştirildi.", parent=self)


def _ac(yol):
    try:
        if WINDOWS:
            os.startfile(yol)
        else:
            subprocess.Popen(["xdg-open", yol])
    except Exception:
        pass


def paneli_ac(u):
    veri = Veri()
    ilk = veri.kimlik() is None
    s = GirisPenceresi(u, veri, ilk=ilk).ac()
    if not s:
        return None
    return YoneticiPaneli(u, s[0], s[1], veri)
