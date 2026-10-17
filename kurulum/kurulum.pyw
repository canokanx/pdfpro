# -*- coding: utf-8 -*-
"""
PDF PRO Kurulum Sihirbazi
PDF_PRO_Kurulum.exe paketi gecici klasore acar ve bu dosyayi (paketteki Python ile) calistirir:
    pythonw kurulum.pyw --kaynak <gecici>       -> sihirbaz penceresi
    pythonw kurulum.pyw --isci <ayar.json>      -> asil kurulum (gerekirse yonetici izniyle)
"""
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import time

WINDOWS = sys.platform.startswith("win")
UYGULAMA_ADI = "PDF PRO"
YAYINCI = "IRONHULL"
KALDIR_ANAHTARI = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\PDF PRO"
PORT = 47917


def _arg(ad, varsayilan=None):
    if ad in sys.argv:
        i = sys.argv.index(ad)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return varsayilan


def surum_oku(app):
    try:
        with open(os.path.join(app, "pdfpro", "surum.py"), encoding="utf-8") as f:
            m = re.search(r'SURUM = "([^"]+)"', f.read())
            return m.group(1) if m else "4.0"
    except OSError:
        return "4.0"


def klasor_boyutu(k):
    t = 0
    for d, _, ds in os.walk(k):
        for a in ds:
            try:
                t += os.path.getsize(os.path.join(d, a))
            except OSError:
                pass
    return t


def yonetici_mi():
    if not WINDOWS:
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def varsayilan_yollar():
    yerel = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Programs", UYGULAMA_ADI)
    herkes = os.path.join(os.environ.get("ProgramFiles") or r"C:\Program Files", UYGULAMA_ADI)
    return herkes, yerel


def mevcut_kurulum():
    """Daha once kurulmussa (yol, herkes_mi)."""
    if not WINDOWS:
        return None
    import winreg
    for kok, herkes in ((winreg.HKEY_LOCAL_MACHINE, True), (winreg.HKEY_CURRENT_USER, False)):
        try:
            k = winreg.OpenKey(kok, KALDIR_ANAHTARI)
            yol = winreg.QueryValueEx(k, "InstallLocation")[0]
            winreg.CloseKey(k)
            if yol and os.path.isdir(yol):
                return yol, herkes
        except OSError:
            continue
    return None


def program_acik_mi():
    import socket
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
            return True
    except OSError:
        return False


# =================================================================== ISCI (asil kurulum)
def isci(ayar_yolu):
    with open(ayar_yolu, encoding="utf-8") as f:
        a = json.load(f)
    durum = a["durum_dosyasi"]

    def yaz(**kw):
        with open(durum, "a", encoding="utf-8") as f:
            f.write(json.dumps(kw, ensure_ascii=False) + "\n")

    try:
        _kur(a, yaz)
        yaz(bitti=True)
    except Exception as e:
        import traceback
        yaz(hata=f"{e}", ayrinti=traceback.format_exc()[-1500:])


def _kopyala_agac(kaynak, hedef, il, sayac, toplam, metin, atla=()):
    for d, klasorler, dosyalar in os.walk(kaynak):
        rel = os.path.relpath(d, kaynak)
        hd = os.path.join(hedef, rel) if rel != "." else hedef
        os.makedirs(hd, exist_ok=True)
        for ad in dosyalar:
            if rel == "." and ad in atla:
                continue
            k = os.path.join(d, ad)
            h = os.path.join(hd, ad)
            try:
                shutil.copy2(k, h)
            except PermissionError:
                # calisan dosya (or. eski PDF_PRO.exe): adini degistirip yenisini koy
                eski = h + ".old"
                try:
                    if os.path.exists(eski):
                        os.remove(eski)
                    os.replace(h, eski)
                except OSError:
                    pass
                shutil.copy2(k, h)
            sayac[0] += os.path.getsize(k)
            if sayac[1] + 400 < time.time() * 1000:
                sayac[1] = time.time() * 1000
                il(yuzde=int(sayac[0] * 100 / max(1, toplam)), metin=metin, dosya=h[-90:])


def _kisayol(yol, hedef, klasor, simge, aciklama="", argumanlar=""):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    try:
        import win32com.client
        k = win32com.client.Dispatch("WScript.Shell").CreateShortcut(yol)
        k.TargetPath, k.WorkingDirectory, k.IconLocation, k.Description = hedef, klasor, simge, aciklama
        k.Arguments = argumanlar
        k.Save()
        return
    except Exception:
        pass
    q = lambda x: x.replace("'", "''")
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{q(yol)}');$s.TargetPath='{q(hedef)}';"
          f"$s.Arguments='{q(argumanlar)}';$s.WorkingDirectory='{q(klasor)}';$s.IconLocation='{q(simge)}';"
          f"$s.Description='{q(aciklama)}';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                   creationflags=0x08000000, timeout=60)


def _ozel_klasor(csidl):
    buf = ctypes.create_unicode_buffer(520)
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf)
    return buf.value


def _kur(a, yaz):
    kaynak, hedef = a["kaynak"], a["hedef"]
    app, runtime, tess = (os.path.join(kaynak, x) for x in ("app", "runtime", "tesseract"))
    toplam = klasor_boyutu(app) + klasor_boyutu(runtime) + (klasor_boyutu(tess) if a["ocr"] else 0)
    sayac = [0, 0]
    os.makedirs(hedef, exist_ok=True)

    yaz(adim=0, metin="Program dosyaları kopyalanıyor…")
    _kopyala_agac(app, hedef, yaz, sayac, toplam, "Program dosyaları kopyalanıyor…", atla=())
    yaz(adim=1, metin="Yazı tipleri ve OCR dil dosyaları hazırlanıyor…")

    yaz(adim=2, metin="Python çalışma ortamı kopyalanıyor…")
    rt = os.path.join(hedef, "runtime")
    if os.path.isdir(rt):
        shutil.rmtree(rt, ignore_errors=True)        # eski kutuphaneler kalmasin
    _kopyala_agac(runtime, rt, yaz, sayac, toplam, "Python çalışma ortamı kopyalanıyor…")

    yaz(adim=3, metin="OCR motoru kuruluyor…")
    if a["ocr"] and os.path.isdir(tess):
        _kopyala_agac(tess, os.path.join(hedef, "tesseract"), yaz, sayac, toplam, "OCR motoru kuruluyor…")

    yaz(adim=4, metin="Kısayollar oluşturuluyor…", yuzde=97)
    pyw = os.path.join(rt, "pythonw.exe")
    with open(os.path.join(hedef, "python_yolu.txt"), "w", encoding="utf-8") as f:
        f.write(pyw)
    exe = os.path.join(hedef, "PDF_PRO.exe")
    simge = exe + ",0"
    herkes = a["herkes"]
    if WINDOWS:
        masaustu = _ozel_klasor(0x0019 if herkes else 0x0010)          # COMMON_DESKTOP / DESKTOP
        baslat = _ozel_klasor(0x0017 if herkes else 0x0002)            # COMMON_PROGRAMS / PROGRAMS
        if a["masaustu"]:
            _kisayol(os.path.join(masaustu, "PDF PRO.lnk"), exe, hedef, simge, "PDF düzenleme ve dönüştürme")
        if a["baslat"]:
            bk = os.path.join(baslat, "PDF PRO")
            _kisayol(os.path.join(bk, "PDF PRO.lnk"), exe, hedef, simge, "PDF PRO")
            _kisayol(os.path.join(bk, "PDF PRO'yu Kaldır.lnk"), pyw, hedef, simge, "PDF PRO'yu kaldır",
                     f'"{os.path.join(hedef, "kurulum", "kaldir.pyw")}"')
        # Programlar ve Ozellikler kaydi
        import winreg
        kok = winreg.HKEY_LOCAL_MACHINE if herkes else winreg.HKEY_CURRENT_USER
        k = winreg.CreateKeyEx(kok, KALDIR_ANAHTARI, 0, winreg.KEY_WRITE)
        for ad, deger in (("DisplayName", "PDF PRO"), ("DisplayVersion", a["surum"]), ("Publisher", YAYINCI),
                          ("DisplayIcon", simge), ("InstallLocation", hedef),
                          ("UninstallString", f'"{pyw}" "{os.path.join(hedef, "kurulum", "kaldir.pyw")}"'),
                          ("Comments", "PDF düzenleme, birleştirme, OCR, dönüştürme, imza"),
                          ("URLInfoAbout", "https://github.com/" + a.get("repo", "") if a.get("repo") else "")):
            if deger:
                winreg.SetValueEx(k, ad, 0, winreg.REG_SZ, deger)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, int(toplam / 1024))
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(k)
        if herkes:
            # tum kullanicilar programi guncelleyebilsin (otomatik guncelleme klasore yazar)
            subprocess.run(["icacls", hedef, "/grant", "*S-1-5-32-545:(OI)(CI)M", "/T", "/Q"],
                           creationflags=0x08000000, timeout=300)

    isaret = os.path.join(hedef, "windows_kayit_kapali.txt")
    if a["birlikte_ac"]:
        if os.path.exists(isaret):
            os.remove(isaret)
        if WINDOWS and not herkes:
            os.environ["PDFPRO_PYTHONW"] = pyw
            sys.path.insert(0, hedef)
            try:
                from pdfpro import sistem
                sistem.PROGRAM_KLASORU = hedef
                sistem.BASLATICI = exe
                sistem.kaydet()
            except Exception:
                pass
    else:
        with open(isaret, "w") as f:
            f.write("PDF PRO ile ac kaydi kurulumda kapatildi.")

    yaz(adim=5, metin="Otomatik güncelleme ayarlanıyor…", yuzde=99)
    ga = os.path.join(hedef, "guncelleme_ayar.json")
    if os.path.isfile(ga):
        with open(ga, encoding="utf-8") as f:
            d = json.load(f)
        d["otomatik"] = bool(a["guncelleme"])
        with open(ga, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    yaz(adim=6, yuzde=100, metin="Tamamlandı")


# =================================================================== SIHIRBAZ (pencere)
def sihirbaz(kaynak):
    import tkinter as tk
    from tkinter import filedialog, messagebox

    app = os.path.join(kaynak, "app")
    surum = surum_oku(app)
    F = "Segoe UI" if WINDOWS else "DejaVu Sans"
    KIRMIZI, KOYU = "#E5322D", "#111827"
    GRI, ACIK = "#6B7280", "#F9FAFB"
    if WINDOWS:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("IRONHULL.PDFPRO.Kurulum")
        except Exception:
            pass

    k = tk.Tk()
    k.title(f"PDF PRO {surum} Kurulum")
    olcek = max(1.0, k.winfo_fpixels("1i") / 96.0)
    W, H = int(760 * olcek), int(520 * olcek)
    k.geometry(f"{W}x{H}+{(k.winfo_screenwidth() - W) // 2}+{(k.winfo_screenheight() - H) // 3}")
    k.resizable(False, False)
    k.configure(bg="white")
    simge = os.path.join(app, "simge.ico")
    try:
        if WINDOWS:
            k.iconbitmap(simge)
    except Exception:
        pass
    logo = None
    try:
        from PIL import Image, ImageTk
        im = Image.open(simge)
        im.size = max(im.info.get("sizes", [(256, 256)]))
        im.load()
        logo = ImageTk.PhotoImage(im.convert("RGBA").resize((int(92 * olcek), int(92 * olcek)), Image.LANCZOS))
    except Exception:
        pass

    def px(v):
        return int(v * olcek)

    # ---- sol panel (renk gecisli)
    SOL = px(220)
    sol = tk.Canvas(k, width=SOL, height=H - px(64), highlightthickness=0, bd=0)
    sol.place(x=0, y=0)
    renkler = [(229, 50, 45), (194, 24, 91), (67, 56, 202)]
    hh = H - px(64)
    for y in range(hh):
        t = y / max(1, hh - 1)
        if t < 0.55:
            a, b, u = renkler[0], renkler[1], t / 0.55
        else:
            a, b, u = renkler[1], renkler[2], (t - 0.55) / 0.45
        r = [int(a[i] + (b[i] - a[i]) * u) for i in range(3)]
        sol.create_line(0, y, SOL, y, fill="#%02x%02x%02x" % tuple(r))
    sol.create_oval(SOL - px(140), hh - px(140), SOL + px(60), hh + px(60), outline="", fill="#d0507a", stipple="gray25")
    if logo:
        sol.create_image(px(22), px(26), image=logo, anchor="nw")
    sol.create_text(px(22), px(138), text="PDF PRO", fill="white", font=(F, 20, "bold"), anchor="nw")
    sol.create_text(px(22), px(172), text=f"Sürüm {surum} · {YAYINCI}", fill="#fde2e7", font=(F, 9), anchor="nw")
    ADIMLAR = ["Hoş geldiniz", "Program hakkında", "Yükleme yeri", "Bileşenler", "Kuruluyor", "Tamamlandı"]

    def adimlari_ciz(n):
        sol.delete("adim")
        for i, ad in enumerate(ADIMLAR):
            y = px(214) + i * px(30)
            if i < n:
                sol.create_oval(px(22), y, px(40), y + px(18), fill="white", outline="white", tags="adim")
                sol.create_text(px(31), y + px(9), text="✓", fill="#c2185b", font=(F, 8, "bold"), tags="adim")
                renk, kal = "#fbe4ea", "normal"
            elif i == n:
                sol.create_oval(px(22), y, px(40), y + px(18), fill="#fde047", outline="#fde047", tags="adim")
                sol.create_text(px(31), y + px(9), text=str(i + 1), fill="#4338ca", font=(F, 8, "bold"), tags="adim")
                renk, kal = "white", "bold"
            else:
                sol.create_oval(px(22), y, px(40), y + px(18), outline="#f3c4d2", tags="adim")
                sol.create_text(px(31), y + px(9), text=str(i + 1), fill="#f3c4d2", font=(F, 8), tags="adim")
                renk, kal = "#f3c4d2", "normal"
            sol.create_text(px(50), y + px(9), text=ad, fill=renk, font=(F, 10, kal), anchor="w", tags="adim")

    # ---- sag ve alt
    sag = tk.Frame(k, bg="white")
    sag.place(x=SOL, y=0, width=W - SOL, height=H - px(64))
    alt = tk.Frame(k, bg="#FAFAFA", highlightthickness=1, highlightbackground="#E5E7EB")
    alt.place(x=0, y=H - px(64), width=W, height=px(64))

    def dugme(ust, metin, komut, ana=False):
        bg, fg = (KIRMIZI, "white") if ana else ("white", "#374151")
        b = tk.Label(ust, text=metin, bg=bg, fg=fg, font=(F, 10, "bold"), padx=px(18), pady=px(6), cursor="hand2",
                     highlightthickness=1, highlightbackground=KIRMIZI if ana else "#D1D5DB")
        b.bind("<Button-1>", lambda e: komut() if str(b.cget("state")) != "disabled" else None)
        b.bind("<Enter>", lambda e: b.config(bg="#C42A26" if ana else "#F3F4F6") if str(b.cget("state")) != "disabled" else None)
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    durum = {"sayfa": 0, "kabul": tk.BooleanVar(value=False)}
    onceki = mevcut_kurulum()
    herkes_vars, yerel_vars = varsayilan_yollar()
    secim = {
        "herkes": tk.BooleanVar(value=onceki[1] if onceki else True),
        "yol": tk.StringVar(value=onceki[0] if onceki else herkes_vars),
        "ocr": tk.BooleanVar(value=os.path.isdir(os.path.join(kaynak, "tesseract"))),
        "masaustu": tk.BooleanVar(value=True), "baslat": tk.BooleanVar(value=True),
        "birlikte_ac": tk.BooleanVar(value=True), "varsayilan": tk.BooleanVar(value=True),
        "guncelleme": tk.BooleanVar(value=True), "baslat_simdi": tk.BooleanVar(value=True),
        "kilavuz": tk.BooleanVar(value=False),
    }

    def temizle():
        for w in sag.winfo_children():
            w.destroy()
        for w in alt.winfo_children():
            w.destroy()

    def baslik(h2, alt_metin=""):
        tk.Label(sag, text=h2, bg="white", fg=KOYU, font=(F, 16, "bold"), anchor="w").pack(fill="x", padx=px(32), pady=(px(26), 0))
        if alt_metin:
            tk.Label(sag, text=alt_metin, bg="white", fg=GRI, font=(F, 10), anchor="w", justify="left",
                     wraplength=W - SOL - px(70)).pack(fill="x", padx=px(32), pady=(px(4), 0))
        g = tk.Frame(sag, bg="white")
        g.pack(fill="both", expand=True, padx=px(32), pady=(px(14), 0))
        return g

    def kutu_onay(ust, var, metin, aciklama="", boy="", kilit=False):
        f = tk.Frame(ust, bg="white")
        f.pack(fill="x", pady=px(3))
        c = tk.Canvas(f, width=px(18), height=px(18), bg="white", highlightthickness=0, cursor="hand2")
        c.pack(side="left", anchor="n", pady=px(2))
        m = tk.Frame(f, bg="white")
        m.pack(side="left", fill="x", expand=True, padx=(px(9), 0))
        e1 = tk.Label(m, text=metin, bg="white", fg=KOYU, font=(F, 10, "bold"), anchor="w", cursor="hand2")
        e1.pack(fill="x")
        if aciklama:
            tk.Label(m, text=aciklama, bg="white", fg=GRI, font=(F, 9), anchor="w").pack(fill="x")
        if boy:
            tk.Label(f, text=boy, bg="white", fg=GRI, font=(F, 9)).pack(side="right", anchor="n")

        def ciz():
            c.delete("all")
            on = var.get() if var is not None else True
            renk = "#9CA3AF" if kilit else (KIRMIZI if on else "white")
            c.create_rectangle(1, 1, px(17), px(17), fill=renk, outline=renk if on else "#9CA3AF", width=1.5)
            if on:
                c.create_text(px(9), px(9), text="✓", fill="white", font=(F, 9, "bold"))

        def tikla(e=None):
            if kilit or var is None:
                return
            var.set(not var.get())
            ciz()
        for w in (c, e1):
            w.bind("<Button-1>", tikla)
        ciz()

    # ------------------------------------------------------- sayfalar
    def s_hosgeldin():
        g = baslik("PDF PRO Kurulum Sihirbazına Hoş Geldiniz",
                   f"Bu sihirbaz PDF PRO {surum}'i bilgisayarınıza kuracak. Kurulum yaklaşık 2 dakika sürer ve internet gerektirmez.")
        oz = [("#E5322D", "✎", "Yazı düzeltme (PDF ve taranmış resim)"), ("#5BA33B", "OCR", "Türkçe + İngilizce OCR"),
              ("#2B579A", "W", "Word / Excel / PowerPoint dönüştürme"), ("#2F6FDE", "✍", "İmza, kaşe, damga, antet"),
              ("#6D3FE8", "AI", "Yapay zeka: özet, çeviri, soru"), ("#0E9AA7", "⚙", "Belge paketi ve iş akışları"),
              ("#A2459A", "☐", "Form doldurma ve oluşturma"), ("#F07B1C", "⬆", "Otomatik güncelleme")]
        izgara = tk.Frame(g, bg="white")
        izgara.pack(fill="x")
        for i, (r, s, t) in enumerate(oz):
            f = tk.Frame(izgara, bg="white")
            f.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, px(14)), pady=px(5))
            c = tk.Canvas(f, width=px(24), height=px(24), bg="white", highlightthickness=0)
            c.pack(side="left")
            c.create_rectangle(0, 0, px(24), px(24), fill=r, outline=r)
            c.create_text(px(12), px(12), text=s, fill="white", font=(F, 7 if len(s) > 1 else 10, "bold"))
            tk.Label(f, text=t, bg="white", fg="#374151", font=(F, 9), wraplength=px(190), justify="left").pack(side="left", padx=px(7))
        if program_acik_mi():
            tk.Label(g, text="⚠ PDF PRO şu an açık. Devam etmeden önce lütfen kapatın.", bg="#FEF3C7", fg="#92400E",
                     font=(F, 9), anchor="w", padx=px(12), pady=px(9)).pack(fill="x", pady=(px(16), 0))
        else:
            tk.Label(g, text="💡 Kuruluma başlamadan önce açık olan PDF PRO pencerelerini kapatmanız önerilir.",
                     bg=ACIK, fg="#374151", font=(F, 9), anchor="w", padx=px(12), pady=px(9),
                     highlightthickness=1, highlightbackground="#E5E7EB").pack(fill="x", pady=(px(16), 0))
        dugme(alt, "İptal", iptal).pack(side="right", padx=(px(6), px(22)), pady=px(14))
        dugme(alt, "İleri  ›", lambda: git(1), ana=True).pack(side="right", pady=px(14))

    LISANS = ("PDF PRO — Kullanım Koşulları\n\nPDF PRO, IRONHULL Marine Services tarafından denizcilik acenteliği "
              "işlerinde kullanılmak üzere geliştirilmiştir. Program; PDF görüntüleme ve düzenleme, birleştirme, bölme, "
              "OCR, dönüştürme, imza/kaşe/antet, form, karşılaştırma ve yapay zeka araçlarını içerir.\n\n"
              "1. Program yalnızca yetkili kişilerin bilgisayarlarına kurulabilir.\n"
              "2. Güncellemeler yöneticinin dijital imzasıyla otomatik gelir; imzası doğrulanmayan güncelleme yüklenmez.\n"
              "3. Belgeleriniz bilgisayarınızdan dışarı gönderilmez. Yapay zeka özellikleri yalnızca siz kullandığınızda ve "
              "kendi anahtarınızla çalışır.\n"
              "4. Kurulum; Python çalışma ortamını, Tesseract OCR motorunu ve yazı tiplerini program klasörüne kopyalar. "
              "Bilgisayarınızdaki başka programlara dokunmaz.\n"
              "5. Program, Ayarlar → Uygulamalar'dan ya da Başlat menüsündeki 'PDF PRO'yu Kaldır' ile tamamen kaldırılabilir.\n\n"
              "Program 'olduğu gibi' sunulur. Önemli belgelerinizin yedeğini almanız önerilir.")

    def s_hakkinda():
        g = baslik("Program hakkında ve kullanım koşulları", "Lütfen okuyun ve devam etmek için kabul edin.")
        t = tk.Text(g, height=10, font=(F, 9), bg=ACIK, fg="#4B5563", relief="flat", wrap="word", padx=px(12), pady=px(10),
                    highlightthickness=1, highlightbackground="#E5E7EB")
        t.insert("1.0", LISANS)
        t.tag_add("b", "1.0", "1.end")
        t.tag_configure("b", font=(F, 10, "bold"), foreground=KOYU)
        t.config(state="disabled")
        t.pack(fill="both", expand=True)
        ileri = dugme(alt, "İleri  ›", lambda: git(2) if durum["kabul"].get() else None, ana=True)

        def guncelle():
            ileri.config(bg=KIRMIZI if durum["kabul"].get() else "#F3A6A4")
        f = tk.Frame(g, bg="white")
        f.pack(fill="x", pady=(px(8), px(4)))
        v = durum["kabul"]
        eski = v.trace_add("write", lambda *a: guncelle())
        kutu_onay(f, v, "Kullanım koşullarını okudum ve kabul ediyorum")
        dugme(alt, "İptal", iptal).pack(side="right", padx=(px(6), px(22)), pady=px(14))
        ileri.pack(side="right", pady=px(14))
        dugme(alt, "‹  Geri", lambda: (v.trace_remove("write", eski), git(0))).pack(side="right", padx=px(6), pady=px(14))
        guncelle()

    def s_yer():
        g = baslik("Yükleme yeri", "PDF PRO'nun kurulacağı klasörü seçin. Önerilen yeri kullanmanız tavsiye edilir.")
        tk.Label(g, text="Kurulum klasörü", bg="white", fg=KOYU, font=(F, 10, "bold"), anchor="w").pack(fill="x")
        sat = tk.Frame(g, bg="white")
        sat.pack(fill="x", pady=(px(6), 0))
        e = tk.Entry(sat, textvariable=secim["yol"], font=("Consolas" if WINDOWS else "DejaVu Sans Mono", 10),
                     relief="flat", highlightthickness=2, highlightbackground=KIRMIZI, highlightcolor=KIRMIZI)
        e.pack(side="left", fill="x", expand=True, ipady=px(6))

        def gozat():
            y = filedialog.askdirectory(parent=k, initialdir=os.path.dirname(secim["yol"].get()) or None)
            if y:
                y = os.path.normpath(y)
                if os.path.basename(y).lower() != "pdf pro":
                    y = os.path.join(y, "PDF PRO")
                secim["yol"].set(y)
                disk_yaz()
        dugme(sat, "📁  Gözat…", gozat).pack(side="left", padx=(px(8), 0))
        rf = tk.Frame(g, bg="white")
        rf.pack(fill="x", pady=(px(12), 0))
        kartlar = []

        def kart(herkes, bas, ac):
            f = tk.Frame(rf, bg="white", highlightthickness=2, cursor="hand2", padx=px(10), pady=px(8))
            f.pack(side="left", fill="both", expand=True, padx=(0, px(8)) if herkes else 0)
            l1 = tk.Label(f, bg="white", font=(F, 10, "bold"), anchor="w", cursor="hand2")
            l1.pack(fill="x")
            l2 = tk.Label(f, text=ac, bg="white", fg=GRI, font=(F, 9), anchor="w", justify="left", wraplength=px(210), cursor="hand2")
            l2.pack(fill="x", padx=(px(20), 0))

            def sec(e=None):
                secim["herkes"].set(herkes)
                h, y = varsayilan_yollar()
                mevcut = secim["yol"].get()
                if mevcut in (h, y) or not mevcut:
                    secim["yol"].set(h if herkes else y)
                boya()
                disk_yaz()
            for w in (f, l1, l2):
                w.bind("<Button-1>", sec)
            kartlar.append((herkes, f, l1, l2, bas))

        def boya():
            for herkes, f, l1, l2, bas in kartlar:
                on = secim["herkes"].get() == herkes
                bg = "#FEF2F2" if on else "white"
                f.config(bg=bg, highlightbackground=KIRMIZI if on else "#E5E7EB")
                l1.config(bg=bg, text=("◉  " if on else "○  ") + bas, fg=KIRMIZI if on else KOYU)
                l2.config(bg=bg)
        kart(True, "Bu bilgisayardaki herkes için", "Program Files'a kurulur · yönetici izni ister")
        kart(False, "Sadece benim için", "Kullanıcı klasörüne kurulur · izin gerekmez")
        boya()
        dk = tk.Label(g, bg="white", fg="#4B5563", font=(F, 9), anchor="w")
        dk.pack(fill="x", pady=(px(12), 0))
        gereken = klasor_boyutu(kaynak)

        def disk_yaz():
            try:
                yol = secim["yol"].get()
                kok = os.path.splitdrive(yol)[0] + os.sep if WINDOWS else "/"
                bos = shutil.disk_usage(kok).free
                dk.config(text=f"Gereken alan: {gereken / 1048576:.0f} MB      Boş alan ({os.path.splitdrive(yol)[0] or '/'}): "
                               f"{bos / 1073741824:.1f} GB".replace(".", ","))
            except Exception:
                dk.config(text=f"Gereken alan: {gereken / 1048576:.0f} MB")
        disk_yaz()
        tk.Label(g, text="ℹ️  Kurulum yeniden yapılırsa ya da program güncellenirse ayarlarınız, imza geçmişiniz ve "
                         "yedekleriniz korunur.", bg=ACIK, fg="#374151", font=(F, 9), anchor="w", justify="left",
                 wraplength=W - SOL - px(90), padx=px(12), pady=px(9), highlightthickness=1,
                 highlightbackground="#E5E7EB").pack(fill="x", pady=(px(12), 0))
        dugme(alt, "İptal", iptal).pack(side="right", padx=(px(6), px(22)), pady=px(14))

        def ileri():
            y = secim["yol"].get().strip()
            if not y or not os.path.isabs(y):
                messagebox.showwarning("PDF PRO Kurulum", "Geçerli bir klasör seçin.", parent=k)
                return
            git(3)
        dugme(alt, "İleri  ›", ileri, ana=True).pack(side="right", pady=px(14))
        dugme(alt, "‹  Geri", lambda: git(1)).pack(side="right", padx=px(6), pady=px(14))

    def s_bilesen():
        g = baslik("Bileşenler ve kısayollar", "Kurulacak parçaları ve oluşturulacak kısayolları seçin.")
        rt_boy = klasor_boyutu(os.path.join(kaynak, "runtime")) + klasor_boyutu(app)
        ts_boy = klasor_boyutu(os.path.join(kaynak, "tesseract"))
        kutu_onay(g, None, "PDF PRO programı", "Python çalışma ortamı ve tüm kütüphaneler dahil (zorunlu)",
                  f"{rt_boy / 1048576:.0f} MB", kilit=True)
        if ts_boy:
            kutu_onay(g, secim["ocr"], "OCR motoru (Tesseract)", "Taranmış belgeleri okumak için · Türkçe + İngilizce",
                      f"{ts_boy / 1048576:.0f} MB")
        kutu_onay(g, secim["masaustu"], "Masaüstü kısayolu", "Masaüstüne PDF PRO simgesi")
        kutu_onay(g, secim["baslat"], "Başlat menüsü kısayolu", "Başlat → PDF PRO ve PDF PRO'yu Kaldır")
        kutu_onay(g, secim["birlikte_ac"], "PDF dosyalarına sağ tık → \"PDF PRO ile aç\"", "\"Birlikte aç\" listesine de eklenir")
        kutu_onay(g, secim["varsayilan"], "PDF PRO'yu varsayılan PDF programı yap", "Kurulum sonunda Windows ayarı açılır, siz seçersiniz")
        kutu_onay(g, secim["guncelleme"], "Otomatik güncellemeler", "Yeni sürümler açılışta kendiliğinden yüklenir (önerilir)")
        dugme(alt, "İptal", iptal).pack(side="right", padx=(px(6), px(22)), pady=px(14))
        dugme(alt, "Kur  ›", kur, ana=True).pack(side="right", pady=px(14))
        dugme(alt, "‹  Geri", lambda: git(2)).pack(side="right", padx=px(6), pady=px(14))

    ilerleme = {}

    def s_kuruluyor():
        g = baslik("Kuruluyor…", "PDF PRO kuruluyor, lütfen bekleyin.")
        ust = tk.Frame(g, bg="white")
        ust.pack(fill="x")
        ilerleme["metin"] = tk.Label(ust, text="Hazırlanıyor…", bg="white", fg="#374151", font=(F, 10), anchor="w")
        ilerleme["metin"].pack(side="left")
        ilerleme["yuzde"] = tk.Label(ust, text="%0", bg="white", fg=KOYU, font=(F, 10, "bold"))
        ilerleme["yuzde"].pack(side="right")
        c = tk.Canvas(g, height=px(10), bg="#E5E7EB", highlightthickness=0)
        c.pack(fill="x", pady=(px(6), 0))
        ilerleme["cubuk"] = c
        ilerleme["dosya"] = tk.Label(g, text="", bg="white", fg="#9CA3AF", font=("Consolas" if WINDOWS else "DejaVu Sans Mono", 8), anchor="w")
        ilerleme["dosya"].pack(fill="x", pady=(px(5), 0))
        liste = tk.Frame(g, bg="white")
        liste.pack(fill="x", pady=(px(12), 0))
        satirlar = []
        for ad in ("Program dosyaları", "Yazı tipleri ve OCR dil dosyaları (Türkçe, İngilizce)",
                   "Python çalışma ortamı ve kütüphaneler", "OCR motoru (Tesseract)",
                   "Kısayollar ve \"PDF PRO ile aç\" kaydı", "Otomatik güncelleme ayarı"):
            e = tk.Label(liste, text="○  " + ad, bg="white", fg="#9CA3AF", font=(F, 10), anchor="w")
            e.pack(fill="x", pady=px(2))
            satirlar.append((e, ad))
        ilerleme["satirlar"] = satirlar
        b = dugme(alt, "İleri  ›", lambda: None, ana=True)
        b.config(bg="#F3A6A4")
        b.pack(side="right", padx=(px(6), px(22)), pady=px(14))

    def cubuk_ciz(y):
        c = ilerleme["cubuk"]
        c.delete("all")
        w = c.winfo_width() or px(440)
        en = int(w * y / 100)
        for i in range(0, en, 3):
            t = i / max(1, w)
            r = [int(a + (b - a) * t) for a, b in zip((229, 50, 45), (67, 56, 202))]
            c.create_line(i, 0, i, px(10), fill="#%02x%02x%02x" % tuple(r), width=3)

    def adim_isaretle(n):
        for i, (e, ad) in enumerate(ilerleme["satirlar"]):
            if i < n:
                e.config(text="✓  " + ad, fg="#16A34A", font=(F, 10))
            elif i == n:
                e.config(text="●  " + ad, fg=KOYU, font=(F, 10, "bold"))
            else:
                e.config(text="○  " + ad, fg="#9CA3AF", font=(F, 10))

    def s_son():
        tk.Frame(sag, bg="white", height=px(22)).pack()
        c = tk.Canvas(sag, width=px(64), height=px(64), bg="white", highlightthickness=0)
        c.pack()
        c.create_oval(1, 1, px(63), px(63), fill="#DCFCE7", outline="#DCFCE7")
        c.create_text(px(32), px(33), text="✓", fill="#16A34A", font=(F, 24, "bold"))
        tk.Label(sag, text="PDF PRO kuruldu", bg="white", fg=KOYU, font=(F, 17, "bold")).pack(pady=(px(10), 0))
        tk.Label(sag, text=f"PDF PRO {surum} başarıyla kuruldu. Masaüstündeki PDF PRO simgesinden ya da bir PDF'e "
                           "sağ tıklayıp \"PDF PRO ile aç\"tan başlatabilirsiniz.", bg="white", fg=GRI, font=(F, 10),
                 wraplength=px(420), justify="center").pack(pady=(px(6), 0))
        # imza karti
        kart = tk.Frame(sag, bg="#FFF7ED", highlightthickness=1, highlightbackground="#FED7AA", padx=px(18), pady=px(8))
        kart.pack(pady=(px(14), 0))
        imza_font = ("Segoe Script", 15) if WINDOWS else (F, 14, "italic")
        tk.Label(kart, text="Can Okan AKTAŞ", bg="#FFF7ED", fg="#9A3412", font=imza_font).pack()
        tk.Label(kart, text="İyi Çalışmalar Diler", bg="#FFF7ED", fg="#C2410C", font=(F, 10, "bold")).pack()
        sec = tk.Frame(sag, bg="white")
        sec.pack(pady=(px(12), 0))
        kutu_onay(sec, secim["baslat_simdi"], "PDF PRO'yu şimdi başlat")
        dugme(alt, "Bitir", bitir, ana=True).pack(side="right", padx=px(22), pady=px(14))

    SAYFALAR = [s_hosgeldin, s_hakkinda, s_yer, s_bilesen, s_kuruluyor, s_son]

    def git(n):
        temizle()
        durum["sayfa"] = n
        adimlari_ciz(n)
        SAYFALAR[n]()

    def iptal():
        if durum["sayfa"] == 4:
            return
        if messagebox.askyesno("PDF PRO Kurulum", "Kurulumdan çıkmak istiyor musunuz?", parent=k):
            k.destroy()

    def kur():
        if program_acik_mi():
            messagebox.showwarning("PDF PRO Kurulum", "PDF PRO şu an açık. Lütfen kapatıp tekrar 'Kur'a basın.", parent=k)
            return
        herkes = secim["herkes"].get()
        hedef = os.path.normpath(secim["yol"].get().strip())
        durum_dosyasi = os.path.join(tempfile.gettempdir(), f"pdfpro_kurulum_{os.getpid()}.txt")
        if os.path.exists(durum_dosyasi):
            os.remove(durum_dosyasi)
        ayar = {"kaynak": kaynak, "hedef": hedef, "herkes": herkes, "surum": surum, "durum_dosyasi": durum_dosyasi,
                "ocr": secim["ocr"].get(), "masaustu": secim["masaustu"].get(), "baslat": secim["baslat"].get(),
                "birlikte_ac": secim["birlikte_ac"].get(), "guncelleme": secim["guncelleme"].get()}
        try:
            with open(os.path.join(app, "guncelleme_ayar.json"), encoding="utf-8") as f:
                ayar["repo"] = json.load(f).get("repo", "")
        except Exception:
            pass
        ayar_yolu = os.path.join(kaynak, "kurulum_ayar.json")
        with open(ayar_yolu, "w", encoding="utf-8") as f:
            json.dump(ayar, f, ensure_ascii=False)
        betik = os.path.abspath(__file__)
        if WINDOWS and herkes and not yonetici_mi():
            # yonetici izniyle ayri surec
            sonuc = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable,
                                                        f'"{betik}" --isci "{ayar_yolu}"', kaynak, 0)
            if sonuc <= 32:
                messagebox.showwarning("PDF PRO Kurulum", "Yönetici izni verilmedi.\n\n'Sadece benim için' "
                                       "seçeneğiyle izin gerekmeden kurabilirsiniz.", parent=k)
                git(2)
                return
        else:
            subprocess.Popen([sys.executable, betik, "--isci", ayar_yolu], cwd=kaynak,
                             creationflags=0x08000000 if WINDOWS else 0)
        ayar["_baslangic"] = time.time()
        durum["ayar"] = ayar
        git(4)
        k.after(300, izle)

    def izle():
        a = durum["ayar"]
        satirlar = []
        try:
            with open(a["durum_dosyasi"], encoding="utf-8") as f:
                satirlar = [json.loads(s) for s in f if s.strip()]
        except (OSError, ValueError):
            pass
        for s in satirlar:
            if "adim" in s:
                adim_isaretle(s["adim"])
            if "metin" in s:
                ilerleme["metin"].config(text=s["metin"])
            if "yuzde" in s:
                ilerleme["yuzde"].config(text=f"%{s['yuzde']}")
                cubuk_ciz(s["yuzde"])
            if "dosya" in s:
                ilerleme["dosya"].config(text=s["dosya"])
        son = satirlar[-1] if satirlar else {}
        if son.get("bitti"):
            adim_isaretle(6)
            cubuk_ciz(100)
            k.after(600, lambda: git(5))
            return
        if son.get("hata"):
            messagebox.showerror("PDF PRO Kurulum", "Kurulum tamamlanamadı:\n\n" + son["hata"], parent=k)
            git(3)
            return
        if not satirlar and time.time() - a["_baslangic"] > 90:
            messagebox.showerror("PDF PRO Kurulum", "Kurulum başlatılamadı.", parent=k)
            git(3)
            return
        k.after(250, izle)

    def bitir():
        a = durum.get("ayar", {})
        hedef = a.get("hedef", "")
        exe = os.path.join(hedef, "PDF_PRO.exe")
        if secim["baslat_simdi"].get() and os.path.isfile(exe):
            try:
                subprocess.Popen([exe], cwd=hedef)
            except Exception:
                pass
        if secim["varsayilan"].get() and WINDOWS:
            try:
                os.startfile("ms-settings:defaultapps?registeredAppUser=PDF%20PRO")
            except Exception:
                pass
        k.destroy()

    k.protocol("WM_DELETE_WINDOW", iptal)
    k._git, k._secim, k._durum, k._kur = git, secim, durum, kur      # testler icin
    git(0)
    k.mainloop()


if __name__ == "__main__":
    if "--isci" in sys.argv:
        isci(_arg("--isci"))
    else:
        sihirbaz(os.path.abspath(_arg("--kaynak", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))
