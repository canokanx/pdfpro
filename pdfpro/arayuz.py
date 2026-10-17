# -*- coding: utf-8 -*-
"""
PDF PRO - Ana pencere (PDF duzenleyici duzeni)
Ust: menu seridi + arac cubugu · Belge sekmeleri · Sol: sayfa kucuk resimleri ·
Orta: belge gorunumu · Alt: sayfa / yakinlastirma cubugu
"""
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from . import cekirdek as C
from . import ocr as O
from . import donustur as D
from . import damga as M
from . import duzenle as Z
from . import diyaloglar as DG
from .cekirdek import PdfProHata, fitz
from .gorunum import Belge, BelgeGorunumu, KucukResimler, PT_PX
from . import araclar as AR
from . import resim_yazi as R
from . import fontlar
from .ek_arayuz import EkIslemler
from . import vitrin as V
from . import teker as TK

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND = True
except Exception:
    DND = False

from .surum import SURUM
PROGRAM_KLASORU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AYAR_DOSYASI = os.path.join(PROGRAM_KLASORU, "ayarlar.json")
HATA_KAYDI = os.path.join(PROGRAM_KLASORU, "hata_kaydi.txt")
WINDOWS = sys.platform.startswith("win")

# ---- renkler (canli tema)
R_MENU = "#FFFFFF"            # beyaz menu seridi
R_MENU_SECILI = "#F3F4F6"
R_MENU_YAZI = "#374151"
R_LOGO = "#F97316"            # turuncu logo
R_ARAC = "#FFFFFF"
R_ARAC_UZERI = "#F3F4F6"
R_MOD_SECILI = "#E5E7EB"
R_SEKME = "#F3F4F6"
R_ZEMIN = "#FFFFFF"
R_KART = "#FFFFFF"
R_BASLIK = "#312E81"
R_VURGU = "#4F46E5"
R_VURGU_KOYU = "#4338CA"
R_BASARI = "#059669"
R_TEHLIKE = "#E11D48"
R_YAZI = "#1E293B"
R_SOLUK = "#64748B"
R_CIZGI = "#E5E7EB"
# her menunun kendi rengi
MENU_RENKLERI = {"Dosya": "#2563EB", "Giriş": "#7C3AED", "Sayfa": "#0891B2", "İşaretle": "#EAB308",
                 "İmza & Damga": "#DC2626", "Form": "#9333EA", "Dönüştür": "#16A34A", "Araçlar": "#EA580C",
                 "Koruma": "#475569", "Yapay Zeka": "#DB2777", "Otomasyon": "#0D9488", "Yardım": "#2563EB"}
# arac dugmesi simge renkleri (sirayla kullanilir)
SIMGE_RENKLERI = ["#2563EB", "#E11D48", "#16A34A", "#F59E0B", "#7C3AED", "#0891B2", "#EA580C",
                  "#DB2777", "#0D9488", "#4F46E5", "#65A30D", "#C026D3"]


def koyu_ton(renk, oran=0.25):
    r, g, b = (int(renk[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(c * (1 - oran)) for c in (r, g, b))


def acik_ton(renk, oran=0.86):
    """Rengi beyaza dogru acar (zemin tonu)."""
    r, g, b = (int(renk[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(c + (255 - c) * oran) for c in (r, g, b))


FONT = "Segoe UI" if WINDOWS else "DejaVu Sans"
EMOJI_FONT = "Segoe UI Emoji" if WINDOWS else "DejaVu Sans"

PDF_TUR = [("PDF dosyası", "*.pdf"), ("Tüm dosyalar", "*.*")]
ACILIR_TUR = [("PDF, resim, Word, Excel", "*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.docx *.doc *.xlsx *.xls"),
              ("Tüm dosyalar", "*.*")]
RESIM_TUR = [("Resim", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.gif *.webp"), ("Tüm dosyalar", "*.*")]
WORD_TUR = [("Word", "*.docx *.doc *.rtf *.odt"), ("Tüm dosyalar", "*.*")]
EXCEL_TUR = [("Excel", "*.xlsx *.xls *.xlsm *.csv *.ods"), ("Tüm dosyalar", "*.*")]

YAZI_RENKLERI = {"Siyah": (0, 0, 0), "Lacivert": (0.12, 0.23, 0.37), "Mavi": (0.1, 0.3, 0.8),
                 "Kırmızı": (0.75, 0.1, 0.1), "Yeşil": (0.1, 0.5, 0.25), "Gri": (0.4, 0.4, 0.4)}


# ================================================================== yardimcilar
def ayar_oku():
    try:
        with open(AYAR_DOSYASI, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def ayar_yaz(ayar):
    try:
        temiz = {k: v for k, v in ayar.items() if not k.startswith("_")}
        with open(AYAR_DOSYASI, "w", encoding="utf-8") as f:
            json.dump(temiz, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def dosya_ac(yol):
    try:
        if WINDOWS:
            os.startfile(yol)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", yol])
        else:
            subprocess.Popen(["xdg-open", yol])
    except Exception as e:
        messagebox.showerror("PDF PRO", f"Açılamadı:\n{e}")


def klasorde_goster(yol):
    try:
        if WINDOWS:
            if os.path.isfile(yol):
                subprocess.Popen(f'explorer /select,"{os.path.normpath(yol)}"')
            else:
                os.startfile(yol)
        else:
            dosya_ac(yol if os.path.isdir(yol) else os.path.dirname(yol))
    except Exception as e:
        messagebox.showerror("PDF PRO", f"Açılamadı:\n{e}")


def boyut_yaz(b):
    for birim in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.0f} {birim}" if birim == "B" else f"{b:.1f} {birim}"
        b /= 1024
    return f"{b:.1f} TB"


def hata_kaydet(metin):
    try:
        import datetime
        with open(HATA_KAYDI, "a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} =====\n{metin}\n")
    except Exception:
        pass


class IpucuBalonu:
    """Fare dugmenin uzerinde durunca kucuk aciklama."""

    def __init__(self, w, metin):
        self.w, self.metin, self.pen, self.zaman = w, metin, None, None
        w.bind("<Enter>", self._bekle, add="+")
        w.bind("<Leave>", self._gizle, add="+")
        w.bind("<ButtonPress>", self._gizle, add="+")

    def _bekle(self, e):
        self.zaman = self.w.after(600, self._goster)

    def _goster(self):
        if self.pen:
            return
        try:
            x = self.w.winfo_rootx() + 10
            y = self.w.winfo_rooty() + self.w.winfo_height() + 4
            self.pen = tk.Toplevel(self.w)
        except tk.TclError:
            return
        self.pen.wm_overrideredirect(True)
        self.pen.geometry(f"+{x}+{y}")
        tk.Label(self.pen, text=self.metin, bg="#FFFFE6", fg="#222", relief="solid", bd=1,
                 font=(FONT, 9), padx=6, pady=3, justify="left").pack()

    def _gizle(self, e=None):
        if self.zaman:
            try:
                self.w.after_cancel(self.zaman)
            except tk.TclError:
                pass
            self.zaman = None
        if self.pen:
            self.pen.destroy()
            self.pen = None


# ================================================================== ana pencere
_TemelTk = TkinterDnD.Tk if DND else tk.Tk


class Uygulama(EkIslemler, _TemelTk):
    def __init__(self, acilacaklar=(), sok=None):
        super().__init__()
        self.ayar = ayar_oku()
        self.title(f"PDF PRO {SURUM}")
        self.configure(bg=R_ZEMIN)
        self._pencere_boyutu()
        try:
            simge = os.path.join(PROGRAM_KLASORU, "simge.ico")
            if WINDOWS and os.path.isfile(simge):
                self.iconbitmap(simge)
        except Exception:
            pass
        self._stil()

        self.belgeler = []
        self.belge = None
        self.kuyruk = queue.Queue()
        self.mesgul = False
        self.mesgul_render = False
        self.iptal_istegi = False
        self.imza_ayar = None
        self.damga_ayar = None
        self.set_ayar = None
        self._form_onbellek = {}
        self._cv2_soruldu = False
        self.mod = "sec"
        fontlar.baslat()
        self._mod_dugmeleri = {}

        TK.kur(self)                       # tekerlek + touchpad yonlendirici
        self._menu_seridi()
        self._menu_seridi_alt = tk.Frame(self, bg=R_VURGU, height=3)
        self._menu_seridi_alt.pack(fill="x")
        self._arac_cubugu = tk.Frame(self, bg=R_ARAC, height=76)
        self._arac_cubugu.pack(fill="x")
        self._arac_cubugu.pack_propagate(False)
        tk.Frame(self, bg=R_CIZGI, height=1).pack(fill="x")
        self._sekme_cubugu()
        self._durum_cubugu()
        self._orta_alan()

        self.menu_sec(self.ayar.get("menu", "Giriş"))
        self._kisayollar()
        self.protocol("WM_DELETE_WINDOW", self.kapat)
        self.after(100, self._kuyruk_isle)
        self.after(400, self._ocr_kontrol)
        self.after(150, lambda: self.karsilama_goster(not self.belgeler))
        if acilacaklar:
            self.after(250, lambda: self.ac(list(acilacaklar)))
        self._sok = sok
        self._yeniden = False
        if sok is not None:
            from . import sistem
            sistem.dinle(sok, lambda yollar: self.kuyruk.put(("dis_ac", yollar)))
        self.after(3000, self._guncelleme_baslangic)
        if WINDOWS:
            from . import sistem
            threading.Thread(target=sistem.gerekiyorsa_kaydet, daemon=True).start()

    # ---------------------------------------------------------- pencere ve stil
    def _pencere_boyutu(self):
        try:
            olcek = max(1.0, self.winfo_fpixels("1i") / 96.0)
        except Exception:
            olcek = 1.0
        ew, eh = self.winfo_screenwidth(), self.winfo_screenheight()
        gen, yuk = min(int(1360 * olcek), int(ew * 0.95)), min(int(860 * olcek), int(eh * 0.9))
        self.geometry(self.ayar.get("pencere") or f"{gen}x{yuk}+{(ew - gen) // 2}+{max(0, (eh - yuk) // 4)}")
        self.minsize(min(int(980 * olcek), ew - 40), min(int(600 * olcek), eh - 80))
        if self.ayar.get("tam_ekran", True):
            try:
                self.state("zoomed")
            except Exception:
                pass

    def _stil(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except Exception:
            pass
        self.option_add("*TCombobox*Listbox.Font", (FONT, 10))
        s.configure(".", background=R_ZEMIN, foreground=R_YAZI, font=(FONT, 10))
        s.configure("TFrame", background=R_ZEMIN)
        s.configure("Kart.TFrame", background=R_KART)
        s.configure("Kart.TLabel", background=R_KART, foreground=R_YAZI)
        s.configure("Soluk.TLabel", background=R_KART, foreground=R_SOLUK, font=(FONT, 9))
        s.configure("Kart.TCheckbutton", background=R_KART)
        s.configure("Kart.TRadiobutton", background=R_KART)
        s.map("Kart.TCheckbutton", background=[("active", R_KART)])
        s.map("Kart.TRadiobutton", background=[("active", R_KART)])
        s.configure("Arac.TCheckbutton", background=R_ARAC, font=(FONT, 9))
        s.map("Arac.TCheckbutton", background=[("active", R_ARAC)])
        s.configure("Ana.TButton", background=R_VURGU, foreground="white", font=(FONT, 10, "bold"),
                    padding=(14, 7), borderwidth=0, focuscolor=R_VURGU)
        s.map("Ana.TButton", background=[("active", "#6366F1"), ("pressed", R_VURGU_KOYU), ("disabled", "#A5B4FC")])
        s.configure("Ikincil.TButton", background="#F3F4F6", foreground=R_YAZI, padding=(8, 5), borderwidth=0,
                    focuscolor="#F3F4F6")
        s.map("Ikincil.TButton", background=[("active", "#E5E7EB"), ("pressed", "#D1D5DB")])
        s.configure("TCombobox", fieldbackground="white", background="#F3F4F6", arrowcolor=R_VURGU)
        s.configure("TSpinbox", arrowcolor=R_VURGU, background="#F3F4F6")
        s.configure("TScale", background=R_ZEMIN, troughcolor="#E5E7EB")
        s.configure("Alt.Horizontal.TScale", background=R_LOGO, troughcolor="#E5E7EB", bordercolor="#E5E7EB",
                    lightcolor=R_LOGO, darkcolor="#EA580C")
        s.configure("TEntry", padding=3)
        s.configure("Horizontal.TProgressbar", background="#10B981", troughcolor="#E5E7EB", borderwidth=0)
        for yon in ("Vertical", "Horizontal"):
            s.configure(f"Belge.{yon}.TScrollbar", gripcount=0, background="#C4C7CC", troughcolor="#FFFFFF",
                        bordercolor="#FFFFFF", arrowcolor="#6B7280", arrowsize=16, relief="flat")
            s.map(f"Belge.{yon}.TScrollbar", background=[("pressed", "#6B7280"), ("active", "#9CA3AF")])

    # ---------------------------------------------------------- menu seridi
    MENULER = ["Dosya", "Giriş", "Sayfa", "İşaretle", "İmza & Damga", "Form", "Dönüştür", "Araçlar",
               "Koruma", "Yapay Zeka", "Otomasyon", "Yardım"]

    def _menu_seridi(self):
        m = tk.Frame(self, bg=R_MENU, height=30)
        m.pack(fill="x")
        m.pack_propagate(False)
        tk.Label(m, text=" ◆ PDF PRO ", bg=R_LOGO, fg="white", font=(FONT, 10, "bold")).pack(side="left", fill="y")
        self._menu_etiketleri = {}
        self._secili_menu = None
        for ad in self.MENULER:
            e = tk.Label(m, text=ad, bg=R_MENU, fg=R_MENU_YAZI, font=(FONT, 10), padx=14, cursor="hand2")
            e.pack(side="left", fill="y")
            e.bind("<Button-1>", lambda ev, a=ad: self.menu_sec(a))
            e.bind("<Enter>", lambda ev, w=e, a=ad: w.config(fg="white", bg=MENU_RENKLERI.get(a, R_VURGU))
                   if a != self._secili_menu else None)
            e.bind("<Leave>", lambda ev, w=e, a=ad: w.config(fg="white" if a == self._secili_menu else R_MENU_YAZI,
                                                            bg=MENU_RENKLERI.get(a, R_VURGU) if a == self._secili_menu else R_MENU))
            self._menu_etiketleri[ad] = e
        self.ocr_etiket = tk.Label(m, text="", bg=R_MENU, fg=R_SOLUK, font=(FONT, 9))
        self.ocr_etiket.pack(side="right", padx=10)

    def menu_sec(self, ad):
        if ad not in self.MENULER:
            ad = "Giriş"
        self._secili_menu = ad
        for a, e in self._menu_etiketleri.items():
            e.config(bg=MENU_RENKLERI.get(a, R_VURGU) if a == ad else R_MENU, fg="white" if a == ad else R_MENU_YAZI,
                     font=(FONT, 10, "bold") if a == ad else (FONT, 10))
        if hasattr(self, "_menu_seridi_alt"):
            self._menu_seridi_alt.config(bg=MENU_RENKLERI.get(ad, R_VURGU))
        self._arac_doldur(ad)
        self.ayar["menu"] = ad

    def _arac_doldur(self, ad):
        c = self._arac_cubugu
        for w in c.winfo_children():
            w.destroy()
        ana = MENU_RENKLERI.get(ad, R_VURGU)
        self._arac_bg = R_ARAC
        c.config(bg=self._arac_bg)
        try:
            st = ttk.Style(self)
            st.configure("Arac.TCheckbutton", background=self._arac_bg)
            st.map("Arac.TCheckbutton", background=[("active", self._arac_bg)])
        except Exception:
            pass
        self._mod_dugmeleri = {}
        self._simge_sira = list(MENU_RENKLERI).index(ad) if ad in MENU_RENKLERI else 0
        for gi, grup in enumerate(self._menu_icerigi(ad)):
            if gi:
                tk.Frame(c, bg=R_CIZGI, width=1).pack(side="left", fill="y", pady=12, padx=6)
            if callable(grup):
                grup(c)
                continue
            for oge in grup:
                self._arac_dugmesi(c, *oge)

    def _arac_dugmesi(self, ust, simge, etiket, komut, ipucu=None, mod=None):
        renk_ = V.ARAC_RENK.get(etiket) or MENU_RENKLERI.get(self._secili_menu, R_VURGU)
        harf = etiket in V.HARF_SIMGE
        if harf:
            simge = V.HARF_SIMGE[etiket]
        zemin_bg = getattr(self, "_arac_bg", R_ARAC)
        f = tk.Frame(ust, bg=zemin_bg, cursor="hand2")
        f.pack(side="left", fill="y", padx=1, pady=3)
        K = 40
        cv = tk.Canvas(f, width=K, height=K, bg=zemin_bg, highlightthickness=0, bd=0)
        cv.pack(pady=(5, 1))
        kare, yazi = V.simge_ciz(cv, 4, 4, 32, renk_, simge, harf, EMOJI_FONT, FONT)
        e = tk.Label(f, text=etiket, bg=zemin_bg, fg="#2A3140", font=(FONT, 9), padx=7)
        e.pack()
        parcalar = (f, cv, e)

        def boya(durum):
            # durum: "normal" | "uzerinde" | "secili"
            if durum == "normal":
                cv.itemconfig(kare, fill=renk_)
                e.config(fg="#2A3140", font=(FONT, 9))
                bg = zemin_bg
            elif durum == "uzerinde":
                cv.itemconfig(kare, fill=V.koyu(renk_, 0.12))
                e.config(fg=V.koyu(renk_, 0.1), font=(FONT, 9))
                bg = "#F1F3F8"
            else:
                cv.itemconfig(kare, fill=V.koyu(renk_, 0.22))
                e.config(fg=V.koyu(renk_, 0.15), font=(FONT, 9, "bold"))
                bg = V.acik(renk_, 0.88)
            for w in parcalar:
                w.config(bg=bg)

        def secili_mi():
            return bool(mod) and self.mod == mod

        for w in parcalar:
            w.bind("<Enter>", lambda ev: boya("secili" if secili_mi() else "uzerinde"))
            w.bind("<Leave>", lambda ev: boya("secili" if secili_mi() else "normal"))
            w.bind("<Button-1>", lambda ev: komut())
        if ipucu:
            IpucuBalonu(f, ipucu)
        if mod:
            self._mod_dugmeleri[mod] = lambda sec: boya("secili" if sec else "normal")
            if self.mod == mod:
                boya("secili")

    def _menu_icerigi(self, ad):
        m = self.mod_sec
        if ad == "Dosya":
            return [
                [("🧰", "Tüm Araçlar", self.tum_araclar, "Bütün araçları kartlar halinde göster"),
                 ("📂", "Aç", self.ac, "PDF, resim, Word, Excel, PowerPoint aç (Ctrl+O)"),
                 ("💾", "Kaydet", self.kaydet, "Ctrl+S · Eski hali otomatik yedeklenir"),
                 ("📝", "Farklı Kaydet", self.farkli_kaydet, "Ctrl+Shift+S"),
                 ("✖", "Kapat", lambda: self.belge_kapat(self.belge), "Açık belgeyi kapat (Ctrl+W)")],
                [("📠", "Tara", self.tara, "Tarayıcıdan tara → PDF (çok sayfa)"),
                 ("🖨", "Yazdır", self.yazdir, "Varsayılan PDF programıyla yazdır"),
                 ("📧", "E-posta", self.eposta, "Outlook'ta PDF ekli yeni ileti aç")],
                [("🕘", "Yedekler", self.yedekler, "Kaydetmeden önceki hallere dön (dosya başına son 10)"),
                 ("📁", "Klasörde Göster", self.klasorde, "Dosyanın bulunduğu klasörü aç")],
            ]
        if ad == "Giriş":
            return [
                [("↶", "Geri Al", self.geri_al, "Ctrl+Z"), ("↷", "Yinele", self.yinele, "Ctrl+Y")],
                [("🖐", "Seç", lambda: m("sec"), "Kaydır, imza / kaşe seç-taşı, form alanı doldur (Esc)", "sec"),
                 ("✏", "Yazı Düzelt", lambda: m("yazi_duzelt"),
                  "PDF'teki VEYA resimdeki (tarama, kimlik, ehliyet) yazıya tıklayın, değiştirin, Enter", "yazi_duzelt"),
                 ("🔎", "Resimde Yazı", lambda: m("resim_yazi"),
                  "Resimdeki yazının etrafına kutu çizin: okunur, düzeltilir (tıklama yetmezse)", "resim_yazi"),
                 ("🔤", "Yazı Ekle", lambda: m("yazi_ekle"), "Sayfada yazmak istediğiniz yere tıklayın", "yazi_ekle"),
                 ("⬜", "Beyaz Kutu", lambda: m("beyaz_kutu"), "Silmek istediğiniz alanın üstüne kutu çizin", "beyaz_kutu")],
                self._yazi_ayar_grubu,
                [("🔍", "Ara", self.arama_ac, "Belgede ara (Ctrl+F)"),
                 ("🔁", "Bul-Değiştir", lambda: self.arama_ac(degistir=True), "Bir yazıyı tüm belgede değiştir (Ctrl+H)")],
                [("➕", "Yakınlaş", lambda: self.gorunum.zoom_adim(1), "Ctrl + fare tekeri"),
                 ("➖", "Uzaklaş", lambda: self.gorunum.zoom_adim(-1)),
                 ("↔", "Genişlik", lambda: self.gorunum.zoom_ayarla("genislik"), "Sayfa genişliğine sığdır"),
                 ("▣", "Sayfa", lambda: self.gorunum.zoom_ayarla("sayfa"), "Tüm sayfayı göster")],
            ]
        if ad == "Sayfa":
            return [
                [("⟲", "Sola Döndür", lambda: self.dondur(-90), "Seçili sayfaları sola döndür"),
                 ("⟳", "Sağa Döndür", lambda: self.dondur(90), "Seçili sayfaları sağa döndür"),
                 ("🗑", "Sil", self.sayfa_sil, "Seçili sayfaları sil (Delete)")],
                [("📄", "Boş Sayfa", self.bos_sayfa, "Seçili sayfadan sonra boş sayfa ekle"),
                 ("📥", "Dosyadan Ekle", self.dosyadan_ekle, "Başka PDF/resmin sayfalarını araya ekle"),
                 ("📤", "Ayır", self.sayfalari_ayir, "Seçili sayfaları yeni belge olarak aç"),
                 ("🔃", "Ters Çevir", self.ters_cevir, "Sayfa sırasını tersine çevir")],
                [("🗂", "Birleştir", self.birlestir, "Birden çok PDF / resmi tek belgede birleştir"),
                 ("✂", "Böl", self.bol, "Belgeyi parçalara ayırıp klasöre kaydet")],
                [("✂", "Kırp", lambda: m("kirp"), "Sayfada kalacak alanı kutu ile seçin", "kirp"),
                 ("📐", "A4'e Sığdır", self.a4e_sigdir, "Farklı boyuttaki taramaları A4 yap"),
                 ("#", "Sayfa No", self.sayfa_no, "Sayfa 1 / 5 gibi numara ekle")],
            ]
        if ad == "İşaretle":
            return [
                [("🖍", "Vurgula", lambda: m("vurgula"), "Fosforlu kalem: yazının üstüne kutu çizin", "vurgula"),
                 ("💬", "Not", lambda: m("not"), "Sayfaya yapışkan not / yorum ekle (tıklayın)", "not"),
                 ("🗨", "Metin Kutusu", lambda: m("metin_kutusu"), "Çerçeveli açıklama kutusu (kutu çizin)", "metin_kutusu")],
                [("▭", "Dikdörtgen", lambda: m("sekil_dikdortgen"), "Çerçeve çiz", "sekil_dikdortgen"),
                 ("◯", "Elips", lambda: m("sekil_elips"), "Daire / elips çiz", "sekil_elips"),
                 ("╱", "Çizgi", lambda: m("sekil_cizgi"), "Çizgi çiz", "sekil_cizgi"),
                 ("➚", "Ok", lambda: m("sekil_ok"), "Ok çiz", "sekil_ok")],
                [("⬛", "Karart", lambda: m("karart"),
                  "KALICI gizle (TC no, adres vb.): alttaki yazı ve resim tamamen silinir", "karart")],
            ]
        if ad == "İmza & Damga":
            return [
                [("✍", "İmza / Kaşe", self.imza_baslat, "Resmi seçip sayfada yerine tıklayın", "imza"),
                 ("🖋", "İmza Setleri", self.imza_setleri, "İmza + kaşeyi birlikte kaydet, tek tıkla ikisini koy"),
                 ("⚡", "Seti Koy", lambda: self.set_baslat(), "Son kullanılan imza + kaşe setini sayfaya koy", "set")],
                [("🔖", "Damga", self.damga_baslat, "ASLI GİBİDİR, ONAYLANDI vb. tarihli kaşe damgası", "damga"),
                 ("🏢", "Antet", self.antet, "Antetli kağıt (PDF veya resim) bas"),
                 ("💧", "Filigran", self.filigran, "GİZLİDİR, TASLAK vb. veya logo")],
            ]
        if ad == "Form":
            return [
                [("📋", "Form Doldur", self.form_doldur, "Tüm form alanlarını liste halinde doldur "
                                                         "(veya Seç modunda alana tıklayın)")],
                [("✨", "Otomatik Algıla", self.form_otomatik, "Boş çizgileri ( ____ ) ve kutucukları forma çevir"),
                 ("▭", "Metin Alanı", lambda: m("form_metin"), "Doldurulabilir yazı alanı: kutu çizin", "form_metin"),
                 ("☑", "Onay Kutusu", lambda: m("form_onay"), "İşaretlenebilir kutu: tıklayın", "form_onay"),
                 ("☰", "Açılır Liste", lambda: m("form_liste"), "Seçenek listesi: kutu çizin", "form_liste")],
                [("🔏", "Formu Kilitle", self.form_kilitle, "Doldurulmuş değerleri sayfaya kalıcı işle (düzleştir)")],
            ]
        if ad == "Dönüştür":
            return [
                [("📝", "Word", self.word_e, "PDF → düzenlenebilir Word (.docx)"),
                 ("📊", "Excel", self.excel_e, "PDF tabloları → Excel"),
                 ("📽", "PowerPoint", self.pptx_e, "PDF → PowerPoint (her sayfa bir slayt)"),
                 ("🖼", "Resim", self.resme, "Sayfaları PNG / JPG kaydet"),
                 ("📃", "Metin", self.metin_cikar, "Tüm yazıyı çıkar (gerekirse OCR)"),
                 ("Ⓜ", "Markdown", self.markdown_e, "PDF → Markdown (.md), başlık ve tablolar korunur"),
                 ("🗄", "PDF/A", self.pdfa_yap, "Uzun süreli arşiv biçimi (resmi kurumlar için)")],
                [("🖼", "Resimden", self.resimden_pdf, "Resimler → PDF"),
                 ("📝", "Word'den", self.wordden_pdf, "Word → PDF"),
                 ("📊", "Excel'den", self.excelden_pdf, "Excel → PDF"),
                 ("📽", "PPT'den", self.pptden_pdf, "PowerPoint → PDF"),
                 ("🌐", "HTML'den", self.htmlden_pdf, "Web sayfası / HTML → PDF")],
            ]
        if ad == "Araçlar":
            return [
                [("🗜", "Sıkıştır", self.sikistir, "Dosya boyutunu küçült (e-posta / sistem yüklemesi, hedef MB seçilebilir)")],
                [("🔍", "OCR", self.ocr_aranabilir, "Taranmış sayfaların yazısını okunur / aranabilir yap"),
                 ("📃", "Metni Çıkar", self.metin_cikar, "Tüm yazıyı pencerede göster")],
                [("⚖", "Karşılaştır", self.karsilastir, "İki PDF arasındaki farkları yan yana renkli göster"),
                 ("▦", "QR / Barkod", self.qr_oku, "Belgedeki QR kod ve barkodları oku (doğrulama linki vb.)")],
                [("🔧", "Onar", self.onar, "Bozuk / açılmayan PDF'i kurtar"),
                 ("🖼", "Resimleri Çıkar", self.resimleri_cikar, "Belgedeki tüm resimleri klasöre kaydet")],
            ]
        if ad == "Koruma":
            return [
                [("🔒", "Şifre Koy", self.sifrele, "Şifreli kopya kaydet"),
                 ("🔓", "Şifreyi Kaldır", self.sifre_kaldir, "Şifresiz kopya kaydet")],
                [("⬛", "Karart", lambda: m("karart"), "KALICI gizle: alttaki bilgi tamamen silinir", "karart"),
                 ("🧹", "Bilgileri Temizle", self.bilgileri_temizle, "Yazar, program, tarih gibi gizli belge bilgilerini sil")],
            ]
        if ad == "Yapay Zeka":
            return [
                [("🧠", "Özetle", self.ozetle, "Belgeyi Türkçe özetle; tarih, tutar, ad ve numaraları çıkar"),
                 ("💬", "Belgeye Sor", self.belgeye_sor, "Belge hakkında soru sor, cevabı belgeden bulsun"),
                 ("🌍", "Çevir", self.cevir, "Sayfa düzenini koruyarak başka dile çevir")],
                [("⚙", "Ayarlar", self.yz_ayarlar, "Yapay zeka anahtarı (Gemini / Groq ücretsiz)")],
            ]
        if ad == "Otomasyon":
            return [
                [("📦", "Belge Paketi", self.belge_paketi, "Gemi evrakını sırasıyla tek PDF yap (ad şablonu + hedef MB)"),
                 ("⚙", "İş Akışları", self.is_akislari, "Kayıtlı adımları tek tıkla uygula · klasördeki tüm PDF'lere toplu işlem")],
            ]
        return [[("🛡", "Yönetici", self.yonetici_ac, "Yönetici girişi: güncelleme yayınlama, sürümler, kaynak dosyalar"),
                 ("🪟", "Windows'a Tanıt", self.windows_tanit,
                  "PDF'e sağ tıklayınca 'Birlikte aç' listesinde ve 'PDF PRO ile aç' olarak görünsün; varsayılan yapılabilsin; "
                  "klasörlerde PDF'lerin ilk sayfası önizleme olarak görünsün")],
                [("❓", "Kılavuz", self.kilavuz, "F1"), ("ℹ", "Hakkında", self.hakkinda),
                 ("🧾", "Hata Kaydı", self.hata_kaydi_ac)]]

    def _yazi_ayar_grubu(self, ust):
        abg = getattr(self, "_arac_bg", R_ARAC)
        f = tk.Frame(ust, bg=abg)
        f.pack(side="left", fill="y", padx=4, pady=6)
        tk.Label(f, text="Yazı ekleme ayarı", bg=abg, fg=R_SOLUK, font=(FONT, 8)).grid(row=0, column=0, columnspan=2, sticky="w")
        if not hasattr(self, "_ya_boyut"):
            self._ya_aile = tk.StringVar(value=self.ayar.get("yazi_aile", "Arial" if WINDOWS else "DejaVu Sans"))
            self._ya_boyut = tk.StringVar(value=str(self.ayar.get("yazi_boyut", 11)))
            self._ya_renk = tk.StringVar(value=self.ayar.get("yazi_renk", "Siyah"))
            self._ya_kalin = tk.BooleanVar(value=self.ayar.get("yazi_kalin", False))
            self._ya_serif = tk.BooleanVar(value=self.ayar.get("yazi_serif", False))
        aile_kutu = ttk.Combobox(f, textvariable=self._ya_aile, state="readonly", width=17,
                                 values=fontlar.aileler() if fontlar.hazir() else fontlar.ONERILEN)
        aile_kutu.grid(row=1, column=2, rowspan=1, padx=(6, 0), sticky="w")
        aile_kutu.bind("<Button-1>", lambda e: aile_kutu.configure(values=fontlar.aileler()) if fontlar.hazir() else None)
        tk.Label(f, text="Yazı tipi", bg=abg, fg=R_SOLUK, font=(FONT, 8)).grid(row=2, column=2, sticky="w", padx=(6, 0))
        ttk.Spinbox(f, from_=6, to=72, width=4, textvariable=self._ya_boyut).grid(row=1, column=0, padx=(0, 4), sticky="w")
        ttk.Combobox(f, values=list(YAZI_RENKLERI), textvariable=self._ya_renk, state="readonly", width=8).grid(row=1, column=1, sticky="w")
        ttk.Checkbutton(f, text="Kalın", variable=self._ya_kalin, style="Arac.TCheckbutton").grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(f, text="Tırnaklı", variable=self._ya_serif, style="Arac.TCheckbutton").grid(row=2, column=1, sticky="w")

    def yazi_ayar(self):
        if not hasattr(self, "_ya_boyut"):
            return {"boyut": 11.0, "renk": (0, 0, 0), "kalin": False, "serif": False, "italik": False}
        try:
            boyut = max(4.0, min(120.0, float(self._ya_boyut.get().replace(",", "."))))
        except Exception:
            boyut = 11.0
        return {"boyut": boyut, "renk": YAZI_RENKLERI.get(self._ya_renk.get(), (0, 0, 0)),
                "kalin": self._ya_kalin.get(), "serif": self._ya_serif.get(), "italik": False,
                "aile": self._ya_aile.get()}

    def yazi_ayar_kaydet(self, st):
        """Yazi ekle'de stil cubugunda secilenleri sonraki yazilar icin hatirla."""
        if not hasattr(self, "_ya_boyut"):
            return
        try:
            self._ya_boyut.set(f"{st.get('boyut', 11):g}")
            self._ya_kalin.set(bool(st.get("kalin")))
            a = st.get("aile") or ""
            if a and not a.startswith("Otomatik") and not a.startswith("─"):
                self._ya_aile.set(a)
        except tk.TclError:
            pass

    # ---------------------------------------------------------- belge sekmeleri
    def _sekme_cubugu(self):
        self._sekmeler = tk.Frame(self, bg="white", height=34)
        self._sekmeler.pack(fill="x")
        self._sekmeler.pack_propagate(False)

    def sekmeleri_ciz(self):
        c = self._sekmeler
        for w in c.winfo_children():
            w.destroy()
        vitrin_acik = hasattr(self, "_karsilama") and bool(self._karsilama.winfo_ismapped())
        ev = tk.Label(c, text="⌂  Tüm Araçlar", bg="#E5322D" if vitrin_acik else "white",
                      fg="white" if vitrin_acik else "#E5322D", font=(FONT, 9, "bold"), padx=10, cursor="hand2")
        ev.pack(side="left", fill="y", padx=(4, 0), pady=(4, 0))
        ev.bind("<Button-1>", lambda e: self.tum_araclar())
        IpucuBalonu(ev, "Tüm araçları kartlar halinde göster / gizle")
        for k, b in enumerate(self.belgeler):
            aktif = b is self.belge and not vitrin_acik
            renk_ = SIMGE_RENKLERI[k % len(SIMGE_RENKLERI)]
            bg = "white" if aktif else R_SEKME
            dis = tk.Frame(c, bg=renk_ if aktif else R_SEKME)
            dis.pack(side="left", fill="y", padx=(4, 0), pady=(4, 0))
            f = tk.Frame(dis, bg=bg)
            f.pack(fill="both", expand=True, pady=(3, 0))
            ad = b.baslik if len(b.baslik) < 42 else b.baslik[:39] + "…"
            nokta = tk.Label(f, text="●", bg=bg, fg=renk_, font=(FONT, 9))
            nokta.pack(side="left", padx=(8, 0))
            et = tk.Label(f, text=ad, bg=bg, fg=R_BASLIK if aktif else R_SOLUK,
                          font=(FONT, 9, "bold" if aktif else "normal"), padx=6, cursor="hand2")
            et.pack(side="left", fill="y")
            for w in (nokta, et):
                w.bind("<Button-1>", lambda e, bb=b: (self.karsilama_goster(False), self.sekme_sec(bb)))
                w.bind("<Button-2>", lambda e, bb=b: self.belge_kapat(bb))
            x = tk.Label(f, text="✕", bg=bg, fg=R_SOLUK, font=(FONT, 9), padx=6, cursor="hand2")
            x.pack(side="left", fill="y")
            x.bind("<Button-1>", lambda e, bb=b: self.belge_kapat(bb))
            x.bind("<Enter>", lambda e, w=x: w.config(fg="white", bg=R_TEHLIKE))
            x.bind("<Leave>", lambda e, w=x, bb=bg: w.config(fg=R_SOLUK, bg=bb))
            if b.yol:
                IpucuBalonu(et, b.yol)
        self.title(f"{self.belge.baslik} — PDF PRO {SURUM}" if self.belge else f"PDF PRO {SURUM}")

    # ---------------------------------------------------------- orta alan
    def _orta_alan(self):
        orta = tk.PanedWindow(self, orient="horizontal", sashwidth=5, bg=R_CIZGI, bd=0)
        orta.pack(fill="both", expand=True)
        z = KucukResimler.ZEMIN
        sol = tk.Frame(orta, bg=z)
        ust = tk.Frame(sol, bg=z)
        ust.pack(fill="x")
        tk.Label(ust, text="SAYFALAR", bg=z, fg=R_VURGU, font=(FONT, 8, "bold")).pack(side="left", padx=8, pady=(5, 0))
        d = tk.Frame(sol, bg=z)
        d.pack(fill="x", padx=4, pady=2)
        for simge, ipucu, k in (("⟲", "Sola döndür", lambda: self.dondur(-90)),
                                ("⟳", "Sağa döndür", lambda: self.dondur(90)),
                                ("🗑", "Seçili sayfaları sil", self.sayfa_sil),
                                ("📄", "Boş sayfa ekle", self.bos_sayfa),
                                ("📥", "Dosyadan sayfa ekle", self.dosyadan_ekle),
                                ("📤", "Seçili sayfaları ayır (yeni belge)", self.sayfalari_ayir)):
            rk = SIMGE_RENKLERI[len(d.winfo_children()) % len(SIMGE_RENKLERI)]
            b = tk.Label(d, text=simge, bg=z, fg=rk, font=(EMOJI_FONT, 12), padx=4, cursor="hand2")
            b.pack(side="left")
            b.bind("<Button-1>", lambda e, kk=k: kk())
            b.bind("<Enter>", lambda e, w=b, r=rk: w.config(bg=r, fg="white"))
            b.bind("<Leave>", lambda e, w=b, r=rk: w.config(bg=z, fg=r))
            IpucuBalonu(b, ipucu)
        tk.Frame(sol, bg=R_CIZGI, height=1).pack(fill="x")
        self.kucuk = KucukResimler(sol, self)
        self.kucuk.pack(fill="both", expand=True)
        orta.add(sol, minsize=150, width=190)

        self.sag = tk.Frame(orta, bg=BelgeGorunumu.ZEMIN)
        self._arama_cubugu_olustur()
        self.gorunum = BelgeGorunumu(self.sag, self)
        self.gorunum.pack(fill="both", expand=True)
        orta.add(self.sag, minsize=400)
        self._karsilama_olustur()

        if DND:
            for w in (self.gorunum.tuval, self.kucuk.tuval, self._karsilama):
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", lambda e: (self.ac(list(self.tk.splitlist(e.data))), e.action)[1])
                except Exception:
                    pass

    def _karsilama_olustur(self):
        Z_ = "#FFFFFF"
        k = tk.Frame(self.sag, bg=Z_)
        self._karsilama = k
        ust = tk.Frame(k, bg=Z_)
        ust.pack(fill="x", padx=20, pady=(16, 0))
        baslik = tk.Frame(ust, bg=Z_)
        baslik.pack()
        tk.Label(baslik, text="◆ ", bg=Z_, fg=R_LOGO, font=(FONT, 22, "bold")).pack(side="left")
        tk.Label(baslik, text="PDF", bg=Z_, fg="#E5322D", font=(FONT, 22, "bold")).pack(side="left")
        tk.Label(baslik, text=" PRO", bg=Z_, fg="#26303F", font=(FONT, 22, "bold")).pack(side="left")
        tk.Label(ust, text="İhtiyacınız olan tüm PDF araçları tek yerde · Dosyayı buraya sürükleyip bırakabilirsiniz",
                 bg=Z_, fg=R_SOLUK, font=(FONT, 10)).pack(pady=(0, 10))
        d = tk.Frame(ust, bg=Z_)
        d.pack()
        ac = tk.Label(d, text="  📂  PDF Dosyası Seç  ", bg="#E5322D", fg="white", font=(FONT, 11, "bold"),
                      padx=14, pady=8, cursor="hand2")
        ac.pack(side="left")
        ac.bind("<Button-1>", lambda e: self.ac())
        ac.bind("<Enter>", lambda e: ac.config(bg="#C42A26"))
        ac.bind("<Leave>", lambda e: ac.config(bg="#E5322D"))
        self._son_cerceve = tk.Frame(ust, bg=Z_)
        self._son_cerceve.pack(pady=(10, 0))
        self.vitrin = V.Vitrin(k, self, FONT, EMOJI_FONT, Z_)
        self.vitrin.pack(fill="both", expand=True)

    def tum_araclar(self):
        acik = bool(self._karsilama.winfo_ismapped())
        if acik and self.belge:
            self.karsilama_goster(False)
        else:
            self._vitrin_elle = bool(self.belge)
            self.karsilama_goster(True)
        self.sekmeleri_ciz()

    def vitrin_calistir(self, komut, belge_gerekli):
        if belge_gerekli:
            if not self.belge:
                self.ac()
                if not self.belge:
                    return
            self.karsilama_goster(False)
            self.sekmeleri_ciz()
            self.after(50, komut)
        else:
            komut()

    def _son_dosyalar_ciz(self):
        f = self._son_cerceve
        for w in f.winfo_children():
            w.destroy()
        son = [y for y in self.ayar.get("son_dosyalar", []) if os.path.isfile(y)][:5]
        if not son:
            return
        Z_ = f["bg"]
        tk.Label(f, text="Son açılanlar:", bg=Z_, fg=R_SOLUK, font=(FONT, 9)).pack(side="left", padx=(0, 4))
        for y in son:
            ad = os.path.basename(y)
            e = tk.Label(f, text="📄 " + (ad if len(ad) < 28 else ad[:25] + "…"), bg="white", fg="#26303F",
                         font=(FONT, 9), cursor="hand2", padx=8, pady=2, highlightthickness=1, highlightbackground="#E1E5EE")
            e.pack(side="left", padx=3)
            e.bind("<Button-1>", lambda ev, yy=y: self.ac([yy]))
            e.bind("<Enter>", lambda ev, w=e: w.config(highlightbackground="#E5322D", fg="#E5322D"))
            e.bind("<Leave>", lambda ev, w=e: w.config(highlightbackground="#E1E5EE", fg="#26303F"))
            IpucuBalonu(e, y)

    def karsilama_goster(self, goster, otomatik=False):
        if not hasattr(self, "_karsilama"):
            return
        if otomatik and not goster and getattr(self, "_vitrin_elle", False):
            return          # kullanici "Tum Araclar"i acti: yeniden cizim kapatmasin
        if not goster:
            self._vitrin_elle = False
        onceki = bool(self._karsilama.winfo_ismapped())
        if goster:
            self._son_dosyalar_ciz()
            self._karsilama.place(x=0, y=0, relwidth=1, relheight=1)
            self._karsilama.lift()
        else:
            self._karsilama.place_forget()
        if onceki != goster and hasattr(self, "_sekmeler"):
            self.after_idle(self.sekmeleri_ciz)

    # ---------------------------------------------------------- alt cubuk
    def _alt_dugme(self, ust, simge, komut, ipucu=None, boyut=11):
        b = tk.Label(ust, text=simge, bg=R_MENU, fg="#374151", font=(FONT, boyut, "bold"), padx=5, cursor="hand2")
        b.pack(side="left")
        b.bind("<Button-1>", lambda e: komut())
        b.bind("<Enter>", lambda e: b.config(bg=R_LOGO, fg="white"))
        b.bind("<Leave>", lambda e: b.config(bg=R_MENU, fg="#374151"))
        if ipucu:
            IpucuBalonu(b, ipucu)
        return b

    def _durum_cubugu(self):
        a = tk.Frame(self, bg=R_MENU, height=34)
        a.pack(fill="x", side="bottom")
        a.pack_propagate(False)
        tk.Frame(self, bg=R_LOGO, height=3).pack(fill="x", side="bottom")
        self._alt = a

        z = tk.Frame(a, bg=R_MENU)
        z.pack(side="right", padx=8)
        self._alt_dugme(z, "↔", lambda: self.gorunum.zoom_ayarla("genislik"), "Genişliğe sığdır", 12)
        self._alt_dugme(z, "▣", lambda: self.gorunum.zoom_ayarla("sayfa"), "Sayfaya sığdır", 12)
        self._alt_dugme(z, "−", lambda: self.gorunum.zoom_adim(-1), "Uzaklaş", 13)
        self._zoom_var = tk.DoubleVar(value=100)
        self._zoom_kaydirici = ttk.Scale(z, style="Alt.Horizontal.TScale", from_=25, to=400, variable=self._zoom_var, length=130,
                                         command=lambda v: self._zoom_etiket.config(text=f"%{float(v):.0f}"))
        self._zoom_kaydirici.pack(side="left")
        self._zoom_kaydirici.bind("<ButtonRelease-1>", lambda e: self.belge and self.gorunum.zoom_ayarla(self._zoom_var.get() / 100))
        self._alt_dugme(z, "+", lambda: self.gorunum.zoom_adim(1), "Yakınlaş", 13)
        self._zoom_etiket = tk.Label(z, text="", bg=R_MENU, fg=R_YAZI, font=(FONT, 9, "bold"), width=5)
        self._zoom_etiket.pack(side="left")

        self.iptal_dugme = ttk.Button(a, text="✖ İptal", style="Ikincil.TButton", command=self._iptal)
        self.ilerleme = ttk.Progressbar(a, length=180, mode="determinate")

        self.durum = tk.Label(a, text="Hazır.", bg=R_MENU, fg=R_SOLUK, font=(FONT, 9), anchor="w")
        self.durum.pack(side="left", padx=10, fill="x", expand=True)

        g = tk.Frame(a, bg=R_MENU)
        g.place(relx=0.5, rely=0.5, anchor="center")
        self._alt_dugme(g, "⏮", lambda: self.git(0), "İlk sayfa")
        self._alt_dugme(g, "◀", lambda: self.git_adim(-1), "Önceki sayfa (Page Up)")
        self._sayfa_var = tk.StringVar(value="")
        e = ttk.Entry(g, textvariable=self._sayfa_var, width=5, justify="center")
        e.pack(side="left", padx=4)
        e.bind("<Return>", self._sayfa_girildi)
        self._toplam_etiket = tk.Label(g, text="/ 0", bg=R_MENU, fg=R_YAZI, font=(FONT, 9))
        self._toplam_etiket.pack(side="left")
        self._alt_dugme(g, "▶", lambda: self.git_adim(1), "Sonraki sayfa (Page Down)")
        self._alt_dugme(g, "⏭", lambda: self.git(10 ** 6), "Son sayfa")
        g.lift()

    def durum_yaz(self, metin, hata=False, basari=False):
        self.durum.config(text=metin, fg=R_TEHLIKE if hata else (R_BASARI if basari else R_SOLUK))

    def zoom_guncelle(self):
        z = self.gorunum.olcek / PT_PX * 100
        self._zoom_var.set(z)
        self._zoom_etiket.config(text=f"%{z:.0f}")

    def _sayfa_girildi(self, e=None):
        try:
            self.git(int(self._sayfa_var.get()) - 1)
        except ValueError:
            self.sayfa_degisti()
        self.gorunum.tuval.focus_set()

    def git(self, i):
        if self.belge:
            self.gorunum.sayfaya_git(max(0, min(self.belge.doc.page_count - 1, i)))

    def git_adim(self, a):
        if self.belge:
            self.git(self.belge.aktif + a)

    def sayfa_degisti(self, kaydir_kucuk=False):
        b = self.belge
        if not b:
            self._sayfa_var.set("")
            self._toplam_etiket.config(text="/ 0")
            self.kucuk.cerceve_ciz()
            return
        self._sayfa_var.set(str(b.aktif + 1))
        self._toplam_etiket.config(text=f"/ {b.doc.page_count}")
        self.kucuk.cerceve_ciz()
        if kaydir_kucuk:
            self.kucuk.aktif_gorunur_yap()

    # ---------------------------------------------------------- kisayollar
    def _kisayollar(self):
        def k(tus, f, giris_disinda=False):
            def calis(e):
                if giris_disinda and isinstance(self.focus_get(), (tk.Entry, ttk.Entry, tk.Text, ttk.Spinbox, ttk.Combobox)):
                    return None
                f()
                return "break"
            self.bind_all(tus, calis)

        k("<Control-o>", self.ac)
        k("<Control-O>", self.ac)
        k("<Control-s>", self.kaydet)
        k("<Control-S>", self.farkli_kaydet)
        k("<Control-z>", self.geri_al, True)
        k("<Control-y>", self.yinele, True)
        k("<Control-w>", lambda: self.belge_kapat(self.belge))
        k("<Control-plus>", lambda: self.gorunum.zoom_adim(1))
        k("<Control-equal>", lambda: self.gorunum.zoom_adim(1))
        k("<Control-minus>", lambda: self.gorunum.zoom_adim(-1))
        k("<Control-0>", lambda: self.gorunum.zoom_ayarla("genislik"))
        k("<Next>", lambda: self.git_adim(1), True)
        k("<Prior>", lambda: self.git_adim(-1), True)
        k("<F1>", self.kilavuz)
        k("<Control-f>", self.arama_ac)
        k("<Control-h>", lambda: self.arama_ac(degistir=True))
        k("<F3>", lambda: self.arama_git(1))
        k("<Shift-F3>", lambda: self.arama_git(-1))

        def esc(e):
            if not self.gorunum._duzenleyici and self.mod != "sec":
                self.mod_sec("sec")
        self.bind_all("<Escape>", esc, add="+")

    # ---------------------------------------------------------- modlar
    def _mod_renkleri(self):
        for m, renk in list(self._mod_dugmeleri.items()):
            try:
                renk(m == self.mod)
            except tk.TclError:
                pass

    def mod_sec(self, mod):
        if mod != "sec" and not self._belge_gerekli():
            return
        if mod != "imza":
            self.imza_ayar = None
        if mod != "damga":
            self.damga_ayar = None
        if mod != "set":
            self.set_ayar = None
        self.mod = mod
        self.gorunum.mod_ayarla(mod)
        self._mod_renkleri()
        self.durum_yaz({
            "sec": "Hazır.  İpucu: Yazıya çift tıklayınca düzeltme açılır.",
            "yazi_duzelt": "✏ YAZI DÜZELT: Değiştirmek istediğiniz yazının üzerine tıklayın. (Esc = çık)",
            "yazi_ekle": "🔤 YAZI EKLE: Yazmak istediğiniz yere tıklayın. Boyut/renk araç çubuğunda. (Esc = çık)",
            "beyaz_kutu": "⬜ BEYAZ KUTU: Silinecek alanın üzerine fareyle kutu çizin. (Esc = çık)",
            "resim_yazi": "🔎 RESİMDE YAZI: Resimdeki yazının etrafına fareyle kutu çizin; okunup düzenlenebilir. (Esc = çık)",
            "vurgula": "🖍 VURGULA: İşaretlemek istediğiniz yazının üstüne kutu çizin. (Esc = çık)",
            "karart": "⬛ KARART: Gizlenecek alanın üstüne kutu çizin. Alttaki bilgi KALICI silinir. (Esc = çık)",
            "kirp": "✂ KIRP: Sayfada KALACAK alanı kutu ile seçin. (Esc = çık)",
            "sekil_dikdortgen": "▭ Dikdörtgen: Fareyle sürükleyin. Renk = Giriş'teki yazı rengi.",
            "sekil_elips": "◯ Elips: Fareyle sürükleyin.",
            "sekil_cizgi": "╱ Çizgi: Başlangıçtan bitişe sürükleyin.",
            "sekil_ok": "➚ Ok: Kuyruktan uca doğru sürükleyin.",
            "not": "💬 NOT: Notun duracağı yere tıklayın. (Esc = çık)",
            "metin_kutusu": "🗨 METİN KUTUSU: Fareyle kutu çizin (ya da tıklayın). (Esc = çık)",
            "form_metin": "▭ METİN ALANI: Doldurulacak alanın üzerine kutu çizin. (Esc = çık)",
            "form_onay": "☑ ONAY KUTUSU: Kutunun olacağı yere tıklayın. (Esc = çık)",
            "form_liste": "☰ AÇILIR LİSTE: Alanın üzerine kutu çizin. (Esc = çık)",
        }.get(mod, ""))

    # ---------------------------------------------------------- belge acma / kapama
    def _belge_gerekli(self):
        if not self.belge:
            messagebox.showinfo("PDF PRO", "Önce bir PDF açın.")
            return None
        return self.belge

    def _sifre_sor(self, ad, deneme):
        s = DG.SifreSorDiyalog(self, ad, deneme).ac()
        return s["sifre"] if s else None

    def ac(self, yollar=None):
        if not yollar:
            yollar = filedialog.askopenfilenames(title="Aç", filetypes=ACILIR_TUR,
                                                 initialdir=self.ayar.get("son_klasor"))
        son = None
        for y in yollar or []:
            y = os.path.normpath(y)
            if os.path.isdir(y):
                continue
            mevcut = next((b for b in self.belgeler if b.yol and os.path.normcase(b.yol) == os.path.normcase(y)), None)
            if mevcut:
                son = mevcut
                continue
            uz = os.path.splitext(y)[1].lower()
            if uz in (".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".rtf", ".odt", ".ods", ".csv"):
                self._office_ac(y)
                continue
            try:
                b = Belge(y, sifre_sor=self._sifre_sor)
            except PdfProHata as e:
                messagebox.showerror("PDF PRO", str(e))
                continue
            self.belgeler.append(b)
            son = b
            self.ayar["son_klasor"] = os.path.dirname(y)
            if uz == ".pdf":
                ls = [x for x in self.ayar.get("son_dosyalar", []) if os.path.normcase(x) != os.path.normcase(y)]
                self.ayar["son_dosyalar"] = [y] + ls[:14]
        if son:
            self.sekme_sec(son)

    def belge_ekle(self, belge):
        self.belgeler.append(belge)
        self.sekme_sec(belge)

    def sekme_sec(self, belge):
        if belge is self.belge and belge is not None:
            return
        self.gorunum.kaydirma_kaydet()
        self.belge = belge
        self.arama_sonuclari = []
        self.gorunum.arama_ciz([], -1)
        self.mod_sec("sec")
        self.gorunum.goster(belge)
        self.kucuk.goster(belge)
        self.sekmeleri_ciz()
        self.sayfa_degisti(kaydir_kucuk=True)

    def belge_kapat(self, belge):
        if not belge:
            return True
        if belge.degisti:
            self.sekme_sec(belge)
            c = messagebox.askyesnocancel("PDF PRO", f"'{belge.ad}' içinde kaydedilmemiş değişiklikler var.\n\n"
                                                     "Kaydetmek ister misiniz?")
            if c is None:
                return False
            if c and not self.kaydet():
                return False
        i = self.belgeler.index(belge)
        self.belgeler.remove(belge)
        belge.kapat()
        if belge is self.belge:
            self.belge = None
            yeni = self.belgeler[min(i, len(self.belgeler) - 1)] if self.belgeler else None
            if yeni:
                self.sekme_sec(yeni)
            else:
                self.gorunum.goster(None)
                self.kucuk.goster(None)
                self.sekmeleri_ciz()
                self.sayfa_degisti()
        else:
            self.sekmeleri_ciz()
        return True

    def kaydet(self):
        b = self._belge_gerekli()
        if not b:
            return False
        if not b.yol:
            return self.farkli_kaydet()
        self.yedek_al(b.yol)
        try:
            b.kaydet()
        except PdfProHata as e:
            messagebox.showerror("PDF PRO", str(e))
            return False
        except Exception as e:
            hata_kaydet(traceback.format_exc())
            messagebox.showerror("PDF PRO", f"Kaydedilemedi:\n{e}")
            return False
        self.sekmeleri_ciz()
        self.durum_yaz(f"✔ Kaydedildi: {b.yol}", basari=True)
        return True

    def farkli_kaydet(self):
        b = self._belge_gerekli()
        if not b:
            return False
        klasor = os.path.dirname(b.yol) if b.yol else self.ayar.get("son_klasor") or os.path.expanduser("~")
        ad = b.ad if b.ad.lower().endswith(".pdf") else b.ad + ".pdf"
        y = filedialog.asksaveasfilename(title="Farklı Kaydet", initialdir=klasor, initialfile=ad,
                                         defaultextension=".pdf", filetypes=PDF_TUR)
        if not y:
            return False
        if os.path.isfile(y):
            self.yedek_al(os.path.normpath(y))
        try:
            b.kaydet(os.path.normpath(y))
        except PdfProHata as e:
            messagebox.showerror("PDF PRO", str(e))
            return False
        except Exception as e:
            hata_kaydet(traceback.format_exc())
            messagebox.showerror("PDF PRO", f"Kaydedilemedi:\n{e}")
            return False
        ls = [x for x in self.ayar.get("son_dosyalar", []) if os.path.normcase(x) != os.path.normcase(b.yol)]
        self.ayar["son_dosyalar"] = [b.yol] + ls[:14]
        self.ayar["son_klasor"] = os.path.dirname(b.yol)
        self.sekmeleri_ciz()
        self.durum_yaz(f"✔ Kaydedildi: {b.yol}", basari=True)
        return True

    def klasorde(self):
        b = self._belge_gerekli()
        if b and b.yol:
            klasorde_goster(b.yol)
        elif b:
            messagebox.showinfo("PDF PRO", "Bu belge henüz kaydedilmedi.")

    def yazdir(self):
        b = self._belge_gerekli()
        if not b:
            return
        yol = b.yol if (b.yol and not b.degisti) else b.gecici_kopya()
        try:
            if WINDOWS:
                os.startfile(yol, "print")
                self.durum_yaz("Yazıcıya gönderildi.", basari=True)
            else:
                dosya_ac(yol)
        except Exception as e:
            messagebox.showerror("PDF PRO", f"Yazdırılamadı (bilgisayarda varsayılan bir PDF programı olmalı):\n{e}")

    # ---------------------------------------------------------- degisiklik altyapisi
    def icerik_degisti(self):
        self.gorunum.yenile()
        self.kucuk.yenile()
        self.sekmeleri_ciz()
        self.sayfa_degisti()

    def duzenle_islem(self, ad, fonk, sayfa=None):
        """Belge uzerinde hizli degisiklik (ana is parcaciginda); geri alinabilir."""
        b = self._belge_gerekli()
        if not b:
            return False
        if self.mesgul:
            messagebox.showinfo("PDF PRO", "Bir işlem sürüyor; bitince tekrar deneyin.")
            return False
        b.anlik()
        try:
            fonk(b.doc)
        except PdfProHata as e:
            b.geri_yukle(b.geri.pop())
            self.icerik_degisti()
            if str(e) != "__degisiklik_yok__":
                messagebox.showwarning("PDF PRO", str(e))
            return False
        except Exception as e:
            hata_kaydet(traceback.format_exc())
            b.geri_yukle(b.geri.pop())
            self.icerik_degisti()
            messagebox.showerror("PDF PRO", f"{ad} yapılamadı:\n{e}")
            return False
        b.degisiklik()
        self.icerik_degisti()
        self.durum_yaz(f"✔ {ad} yapıldı · Geri almak için Ctrl+Z", basari=True)
        return True

    def dosya_islem(self, ad, fonk, arka_plan=False, bitince=None):
        """Dosya tabanli islevi fonk(kaynak, cikti, ilerleme, iptal) acik belgeye uygular."""
        b = self._belge_gerekli()
        if not b:
            return
        if self.mesgul:
            messagebox.showinfo("PDF PRO", "Bir işlem sürüyor; bitince tekrar deneyin.")
            return
        kaynak = b.gecici_kopya()
        cikti = kaynak[:-4] + "_sonuc.pdf"

        def uygula(sonuc):
            with open(cikti, "rb") as f:
                bayt = f.read()
            for y in (kaynak, cikti):
                try:
                    os.remove(y)
                except Exception:
                    pass
            if b not in self.belgeler:
                return
            b.yeni_icerik(bayt)
            if b is self.belge:
                self.icerik_degisti()
            else:
                self.sekmeleri_ciz()
            self.durum_yaz(f"✔ {ad} uygulandı · Geri almak için Ctrl+Z", basari=True)
            if bitince:
                bitince(sonuc)

        if arka_plan:
            self.calistir(ad, lambda il, ip: fonk(kaynak, cikti, il, ip), uygula, iptal_edilebilir=True)
            return
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            uygula(fonk(kaynak, cikti, None, lambda: False))
        except PdfProHata as e:
            messagebox.showwarning("PDF PRO", str(e))
        except Exception as e:
            hata_kaydet(traceback.format_exc())
            messagebox.showerror("PDF PRO", f"{ad} yapılamadı:\n{e}")
        finally:
            self.config(cursor="")

    def kaynak_dosya(self):
        """Donusturme icin belgenin guncel halinin dosya yolu."""
        b = self.belge
        if b.yol and not b.degisti:
            return b.yol
        return b.gecici_kopya()

    def cikti_yolu(self, ek, uzanti=".pdf", klasor_mu=False):
        b = self.belge
        if b.yol:
            klasor = os.path.dirname(b.yol)
        else:
            klasor = self.ayar.get("son_klasor") or os.path.join(os.path.expanduser("~"), "Desktop")
        ad = os.path.splitext(b.ad)[0]
        if klasor_mu:
            return C.benzersiz_yol(os.path.join(klasor, f"{ad}_{ek}"))
        return C.benzersiz_yol(os.path.join(klasor, f"{ad}_{ek}{uzanti}"))

    # ---------------------------------------------------------- geri al
    def geri_al(self):
        b = self._belge_gerekli()
        if not b:
            return
        if b.geri_al():
            self.icerik_degisti()
            self.durum_yaz("↶ Geri alındı.")
        else:
            self.durum_yaz("Geri alınacak işlem yok.")

    def yinele(self):
        b = self._belge_gerekli()
        if b and b.yinele():
            self.icerik_degisti()
            self.durum_yaz("↷ Yinelendi.")

    # ---------------------------------------------------------- sayfa islemleri
    def _secili(self):
        b = self.belge
        return sorted(b.secili) if b.secili else [b.aktif]

    def dondur(self, aci):
        if not self._belge_gerekli():
            return
        self.nesneleri_unut()
        sec = self._secili()

        def f(doc):
            for i in sec:
                doc[i].set_rotation((doc[i].rotation + aci) % 360)
        self.duzenle_islem(f"{len(sec)} sayfa döndürme", f)

    def sayfa_sil(self):
        b = self._belge_gerekli()
        if not b:
            return
        self.nesneleri_unut()
        sec = self._secili()
        if len(sec) >= b.doc.page_count:
            messagebox.showwarning("PDF PRO", "Tüm sayfalar silinemez; en az bir sayfa kalmalı.")
            return
        liste = ", ".join(str(i + 1) for i in sec[:12]) + ("…" if len(sec) > 12 else "")
        if not messagebox.askyesno("PDF PRO", f"{len(sec)} sayfa silinsin mi?  (Sayfa: {liste})\n\n"
                                              "Ctrl+Z ile geri alabilirsiniz."):
            return
        b.secili = {max(0, sec[0] - 1)}
        self.duzenle_islem("Sayfa silme", lambda doc: doc.delete_pages(sec))

    def bos_sayfa(self):
        b = self._belge_gerekli()
        if not b:
            return
        self.nesneleri_unut()
        a = max(self._secili())
        if self.duzenle_islem("Boş sayfa ekleme", lambda doc: Z.bos_sayfa_ekle(doc, a, a)):
            b.secili = {a + 1}
            self.git(a + 1)

    def dosyadan_ekle(self):
        b = self._belge_gerekli()
        if not b:
            return
        self.nesneleri_unut()
        ys = filedialog.askopenfilenames(title="Eklenecek dosyalar", filetypes=ACILIR_TUR,
                                         initialdir=self.ayar.get("son_klasor"))
        if not ys:
            return
        a = max(self._secili())

        def f(doc):
            konum = a
            for y in ys:
                konum += Z.dosyadan_ekle(doc, y, konum)
        if self.duzenle_islem("Dosyadan sayfa ekleme", f):
            b.secili = {a + 1}
            self.git(a + 1)

    def sayfalari_ayir(self):
        b = self._belge_gerekli()
        if not b:
            return
        sec = self._secili()
        yeni = fitz.open()
        for i in sec:
            yeni.insert_pdf(b.doc, from_page=i, to_page=i)
        etiket = "-".join(str(i + 1) for i in sec[:4]) + ("_vb" if len(sec) > 4 else "")
        ad = os.path.splitext(b.ad)[0] + f"_s{etiket}.pdf"
        self.belge_ekle(Belge(doc=yeni, ad=ad))
        self.durum_yaz(f"✔ {len(sec)} sayfa yeni sekmede açıldı. Kaydetmek için Ctrl+S.", basari=True)

    def sayfa_tasi(self, kaynaklar, hedef):
        b = self.belge
        self.nesneleri_unut()
        sonuc = {}

        def f(doc):
            r = Z.sayfa_tasi(doc, kaynaklar, hedef)
            if r is None:
                raise PdfProHata("__degisiklik_yok__")
            sonuc["yeni"] = r
        if self.duzenle_islem("Sayfa taşıma", f) and sonuc.get("yeni"):
            b.secili = set(sonuc["yeni"])
            b.aktif = sonuc["yeni"][0]
            self.kucuk.cerceve_ciz()
            self.git(b.aktif)

    def ters_cevir(self):
        self.nesneleri_unut()
        if self._belge_gerekli():
            self.duzenle_islem("Sayfa sırası ters çevirme",
                               lambda doc: doc.select(list(range(doc.page_count - 1, -1, -1))))

    def sayfa_menusu(self, x, y):
        m = tk.Menu(self, tearoff=0, font=(FONT, 10))
        m.add_command(label="⟲  Sola döndür", command=lambda: self.dondur(-90))
        m.add_command(label="⟳  Sağa döndür", command=lambda: self.dondur(90))
        m.add_separator()
        m.add_command(label="📄  Sonrasına boş sayfa ekle", command=self.bos_sayfa)
        m.add_command(label="📥  Sonrasına dosyadan ekle…", command=self.dosyadan_ekle)
        m.add_command(label="📤  Yeni belge olarak ayır", command=self.sayfalari_ayir)
        m.add_separator()
        m.add_command(label="🗑  Sil", command=self.sayfa_sil)
        m.tk_popup(x, y)

    def bol(self):
        b = self._belge_gerekli()
        if not b:
            return
        s = DG.BolDiyalog(self, b.doc.page_count).ac()
        if not s:
            return
        kaynak = self.kaynak_dosya()
        klasor = self.cikti_yolu("bolunmus", klasor_mu=True)
        self.calistir("Bölünüyor", lambda il, ip: C.bol(kaynak, klasor, s["mod"], s["deger"], il),
                      lambda r: self.sonuc_goster(f"{len(r)} parça oluşturuldu.", klasor=klasor))

    def _gecici_belge(self, yol, ad):
        """Gecici dosyadaki PDF'i kaydedilmemis yeni belge olarak acar."""
        with open(yol, "rb") as f:
            doc = fitz.open("pdf", f.read())
        try:
            os.remove(yol)
        except Exception:
            pass
        self.belge_ekle(Belge(doc=doc, ad=ad))

    def birlestir(self):
        ilk = [self.belge.yol] if (self.belge and self.belge.yol) else []
        s = DG.BirlestirDiyalog(self, self.ayar, ilk).ac()
        if not s:
            return
        gecici = os.path.join(tempfile.gettempdir(), "pdfpro_birlesik.pdf")

        def bitti(r):
            ad = os.path.splitext(os.path.basename(s["yollar"][0]))[0] + "_birlesik.pdf"
            self._gecici_belge(r, ad)
            self.durum_yaz(f"✔ {len(s['yollar'])} dosya birleştirildi. Kaydetmek için Ctrl+S.", basari=True)

        self.calistir("Birleştiriliyor", lambda il, ip: C.birlestir(s["yollar"], gecici, il), bitti)

    # ---------------------------------------------------------- imza / antet / filigran
    def imza_baslat(self):
        if not self._belge_gerekli():
            return
        s = DG.ImzaDiyalog(self, self.ayar).ac()
        if not s:
            if self.mod == "imza":
                self.mod_sec("sec")
            return
        try:
            rw, rh, png = M.resim_hazirla(s["resim"], 1.0, s["beyaz"])
        except PdfProHata as e:
            messagebox.showerror("PDF PRO", str(e))
            return
        self.mod_sec("sec")
        self.imza_ayar = dict(s, png=png, oran=rh / rw, _pil=None)
        self.mod = "imza"
        self.gorunum.mod_ayarla("imza")
        self._mod_renkleri()
        self.durum_yaz("✍ İMZA: Sayfada yerine tıklayın ya da fareyle kutu çizin. (Esc = vazgeç)")

    def imza_onizleme_resmi(self, w, h):
        try:
            from PIL import Image, ImageTk
            import io
            if self.imza_ayar.get("_pil") is None:
                self.imza_ayar["_pil"] = Image.open(io.BytesIO(self.imza_ayar["png"])).convert("RGBA")
            im = self.imza_ayar["_pil"].resize((max(1, w), max(1, h)))
            im.putalpha(im.split()[3].point(lambda v: int(v * 0.6)))
            return ImageTk.PhotoImage(im)
        except Exception:
            return None

    def imza_yerlestir(self, i, rect, merkez):
        a = self.imza_ayar
        if not a:
            return
        oran_hw = a["oran"]
        if rect is None:
            gen = a["genislik_mm"] * 72 / 25.4
            yuk = gen * oran_hw
            rect = fitz.Rect(merkez[0] - gen / 2, merkez[1] - yuk / 2, merkez[0] + gen / 2, merkez[1] + yuk / 2)
        else:   # cizilen kutuya oranini bozmadan sigdir
            gen = min(rect.width, rect.height / oran_hw)
            yuk = gen * oran_hw
            cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
            rect = fitz.Rect(cx - gen / 2, cy - yuk / 2, cx + gen / 2, cy + yuk / 2)
        png = a["png"]
        b = self.belge
        r0 = b.doc[i].rect
        oran = (rect.x0 / r0.width, rect.y0 / r0.height, rect.x1 / r0.width, rect.y1 / r0.height)
        sayfalar = list(range(b.doc.page_count)) if a.get("tum") else [i]
        secilecek = {}

        def f(doc):
            for s_ in sayfalar:
                r = doc[s_].rect
                kutu = fitz.Rect(oran[0] * r.width, oran[1] * r.height, oran[2] * r.width, oran[3] * r.height)
                xref = Z.nesne_ekle(doc[s_], kutu, png)
                if xref:
                    nid = self._yeni_nesne_id()
                    b.nesneler.append({"id": nid, "sayfa": s_, "xref": xref, "rect": tuple(kutu), "png": png})
                    if s_ == i:
                        secilecek["id"] = nid
        self.duzenle_islem("İmza / kaşe yerleştirme", f)
        self.mod_sec("sec")
        if secilecek.get("id"):
            self.gorunum.nesne_sec(secilecek["id"])
            self.durum_yaz("✔ Yerleştirildi. Köşelerden büyütüp küçültebilir, sürükleyip taşıyabilirsiniz. "
                           "Delete = sil · Yön tuşları = ince ayar", basari=True)

    # ---------------------------------------------------------- tasinabilir nesneler (imza / kase)
    def _yeni_nesne_id(self):
        self._nesne_sayac = getattr(self, "_nesne_sayac", 0) + 1
        return self._nesne_sayac

    def _nesne(self, nid):
        b = self.belge
        return next((n for n in b.nesneler if n["id"] == nid), None) if b else None

    def nesne_guncelle(self, nid, yeni_rect, ad_="İmza / kaşe taşıma"):
        n = self._nesne(nid)
        if not n:
            return
        yeni_rect = fitz.Rect(yeni_rect)
        if yeni_rect.width < 4 or yeni_rect.height < 4:
            return

        def f(doc):
            page = doc[n["sayfa"]]
            if not Z.nesne_kaldir(page, n["xref"]):
                self.belge.nesneleri_esle()          # numarasi degismis olabilir: konumundan bul
                if self._nesne(nid) is None or not Z.nesne_kaldir(doc[n["sayfa"]], n["xref"]):
                    raise PdfProHata("Bu imza / kaşe artık taşınamıyor (belge yapısı değişmiş). "
                                     "Ctrl+Z ile geri alıp tekrar yerleştirebilirsiniz.")
            n["xref"] = Z.nesne_ekle(doc[n["sayfa"]], yeni_rect, n["png"])
            n["rect"] = tuple(yeni_rect)
        self.duzenle_islem(ad_, f, n["sayfa"])
        if self._nesne(nid):
            self.gorunum.nesne_sec(nid)

    def nesne_sil(self, nid):
        n = self._nesne(nid)
        if not n:
            return
        b = self.belge

        def f(doc):
            Z.nesne_kaldir(doc[n["sayfa"]], n["xref"])
            b.nesneler[:] = [x for x in b.nesneler if x["id"] != nid]
        self.duzenle_islem("İmza / kaşe silme", f, n["sayfa"])
        self.gorunum.nesne_sec(None)

    def nesneleri_unut(self):
        """Sayfa yapisi degisince (sil, tasi, dondur...) tasinabilir nesne kaydi gecersiz olur."""
        if self.belge:
            self.belge.nesneler = []
        self.gorunum.nesne_sec(None)

    def antet(self):
        if not self._belge_gerekli():
            return
        s = DG.AntetDiyalog(self, self.ayar).ac()
        if s:
            self.dosya_islem("Antet", lambda k, c, il, ip: M.antet_ekle(
                k, c, s["antet"], s["sayfalar"], s["yerlesim"], s["onde"], s["devam"], il))

    def filigran(self):
        if not self._belge_gerekli():
            return
        s = DG.FiligranDiyalog(self, self.ayar).ac()
        if not s:
            return
        if s["tur"] == "resim":
            self.dosya_islem("Filigran", lambda k, c, il, ip: M.resim_filigran_ekle(
                k, c, s["resim"], s["sayfalar"], s["opaklik"], ilerleme=il))
        else:
            self.dosya_islem("Filigran", lambda k, c, il, ip: M.filigran_ekle(
                k, c, s["metin"], s["sayfalar"], s["aci"], s["opaklik"], 0, s["renk"], True, s["desen"], il))

    def sayfa_no(self):
        if not self._belge_gerekli():
            return
        s = DG.SayfaNoDiyalog(self).ac()
        if s:
            self.dosya_islem("Sayfa numarası", lambda k, c, il, ip: M.sayfa_no_ekle(
                k, c, s["bicim"], s["konum"], s["boyut"], s["baslangic"], s["sayfalar"], ilerleme=il))

    # ---------------------------------------------------------- ARA / BUL-DEGISTIR
    def _arama_cubugu_olustur(self):
        c = tk.Frame(self.sag, bg="#FFF8DC", highlightthickness=1, highlightbackground="#E6D9A8")
        self._arama = c
        self._arama_var = tk.StringVar()
        self._degistir_var = tk.StringVar()
        self._arama_bk = tk.BooleanVar(value=False)
        tk.Label(c, text="🔍", bg="#FFF8DC", font=(EMOJI_FONT, 11)).pack(side="left", padx=(8, 2))
        e = ttk.Entry(c, textvariable=self._arama_var, width=28)
        e.pack(side="left", pady=4)
        e.bind("<Return>", lambda ev: self.arama_git(-1 if ev.state & 1 else 1))
        self._arama_giris = e
        for t, k in (("▲", lambda: self.arama_git(-1)), ("▼", lambda: self.arama_git(1))):
            ttk.Button(c, text=t, width=3, style="Ikincil.TButton", command=k).pack(side="left", padx=1)
        self._arama_sayi = tk.Label(c, text="", bg="#FFF8DC", fg=R_SOLUK, font=(FONT, 9), width=12)
        self._arama_sayi.pack(side="left")
        ttk.Checkbutton(c, text="Büyük/küçük harf", variable=self._arama_bk,
                        command=self.arama_yap).pack(side="left", padx=6)
        self._degistir_alani = tk.Frame(c, bg="#FFF8DC")
        tk.Label(self._degistir_alani, text="→", bg="#FFF8DC", font=(FONT, 11)).pack(side="left", padx=4)
        ttk.Entry(self._degistir_alani, textvariable=self._degistir_var, width=24).pack(side="left")
        ttk.Button(self._degistir_alani, text="Tümünü Değiştir", style="Ana.TButton",
                   command=self.tumunu_degistir).pack(side="left", padx=6)
        x = tk.Label(c, text="✕", bg="#FFF8DC", fg=R_SOLUK, font=(FONT, 11), cursor="hand2", padx=8)
        x.pack(side="right")
        x.bind("<Button-1>", lambda ev: self.arama_kapat())
        e.bind("<Escape>", lambda ev: self.arama_kapat())
        self._arama_zaman = None
        self._arama_var.trace_add("write", lambda *a: self._arama_gecikmeli())
        self.arama_sonuclari = []
        self.arama_indeks = -1

    def arama_ac(self, degistir=False):
        if not self._belge_gerekli():
            return
        if not self._arama.winfo_ismapped():
            self._arama.pack(side="top", fill="x", before=self.gorunum)
        if degistir:
            self._degistir_alani.pack(side="left", padx=(6, 0))
        else:
            self._degistir_alani.pack_forget()
        self._arama_giris.focus_set()
        self._arama_giris.select_range(0, "end")
        if self._arama_var.get():
            self.arama_yap()

    def arama_kapat(self):
        self._arama.pack_forget()
        self.arama_sonuclari = []
        self.gorunum.arama_ciz([], -1)
        self.gorunum.tuval.focus_set()

    def _arama_gecikmeli(self):
        if self._arama_zaman:
            self.after_cancel(self._arama_zaman)
        self._arama_zaman = self.after(300, self.arama_yap)

    def arama_yap(self):
        self._arama_zaman = None
        b = self.belge
        if not b:
            return
        t = self._arama_var.get()
        self.arama_sonuclari = AR.ara(b.doc, t, self._arama_bk.get()) if len(t) >= 1 else []
        self.arama_indeks = -1
        if self.arama_sonuclari:
            # bulunduğu sayfadan itibaren ilk sonuca git
            self.arama_indeks = next((k for k, (i, _) in enumerate(self.arama_sonuclari) if i >= b.aktif), 0)
            self._arama_goster()
        else:
            self._arama_sayi.config(text="bulunamadı" if t else "", fg=R_TEHLIKE if t else R_SOLUK)
            self.gorunum.arama_ciz([], -1)

    def arama_git(self, yon):
        if not self.arama_sonuclari:
            self.arama_yap()
            return
        self.arama_indeks = (self.arama_indeks + yon) % len(self.arama_sonuclari)
        self._arama_goster()

    def _arama_goster(self):
        n = len(self.arama_sonuclari)
        self._arama_sayi.config(text=f"{self.arama_indeks + 1} / {n}", fg=R_YAZI)
        i, r = self.arama_sonuclari[self.arama_indeks]
        self.gorunum.arama_ciz(self.arama_sonuclari, self.arama_indeks)
        self.gorunum.alana_git(i, r)

    def tumunu_degistir(self):
        b = self._belge_gerekli()
        if not b:
            return
        a, y = self._arama_var.get(), self._degistir_var.get()
        if not a:
            return
        bulunan = AR.ara(b.doc, a, True)
        if not bulunan:
            messagebox.showinfo("PDF PRO", f"'{a}' bulunamadı.")
            return
        if not messagebox.askyesno("PDF PRO", f"'{a}' → '{y}'\n\n{len(bulunan)} yer değiştirilsin mi?\n"
                                              "(Ctrl+Z ile geri alabilirsiniz)"):
            return
        sonuc = {}
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            self.duzenle_islem("Bul-değiştir", lambda doc: sonuc.update(n=AR.bul_degistir(doc, a, y, True)))
        finally:
            self.config(cursor="")
        self.durum_yaz(f"✔ {sonuc.get('n', 0)} yer değiştirildi · Geri almak için Ctrl+Z", basari=True)
        self.arama_yap()

    # ---------------------------------------------------------- RESIMDEKI YAZI
    def _cv2_kontrol(self):
        """OpenCV yoksa bir kez kurmayi teklif eder (doku koruyan silme icin)."""
        if R.cv2_var() or self._cv2_soruldu:
            return
        self._cv2_soruldu = True
        if messagebox.askyesno("PDF PRO", "Resimdeki yazıyı arka planı bozmadan silmek için küçük bir bileşen "
                                          "(OpenCV, ~40 MB) gerekli.\n\nŞimdi internetten kurulsun mu?\n"
                                          "(Kurulmazsa yazının arkası düz renkle örtülür.)"):
            self.bilesen_kur(["opencv-python-headless"], "OpenCV")

    def bilesen_kur(self, paketler, ad):
        py = sys.executable
        if py.lower().endswith("pythonw.exe"):
            py = py[:-len("pythonw.exe")] + "python.exe"

        def is_(il, ip):
            il(0, 1, f"{ad} indiriliyor…")
            r = subprocess.run([py, "-m", "pip", "install", "--disable-pip-version-check", "-q"] + paketler,
                               capture_output=True, text=True, creationflags=0x08000000 if WINDOWS else 0)
            if r.returncode != 0:
                r = subprocess.run([py, "-m", "pip", "install", "--user", "--disable-pip-version-check", "-q"] + paketler,
                                   capture_output=True, text=True, creationflags=0x08000000 if WINDOWS else 0)
            if r.returncode != 0:
                raise PdfProHata(f"{ad} kurulamadı:\n{(r.stderr or r.stdout)[-600:]}")
            return True

        def bitti(_):
            import importlib
            import site
            try:
                importlib.reload(site)
                R.cv2 = importlib.import_module("cv2")
                self.durum_yaz(f"✔ {ad} kuruldu.", basari=True)
            except Exception as e:
                messagebox.showwarning("PDF PRO", f"{ad} kuruldu ama yüklenemedi; programı yeniden başlatın.\n{e}")
        self.calistir(f"{ad} kuruluyor", is_, bitti)

    def resimde_yazi_bul(self, i, px, py, yedek=None, alan=None):
        """Tiklanan noktadaki (veya kutudaki) resim yazisini OCR ile okuyup duzenleyiciyi acar."""
        b = self._belge_gerekli()
        if not b or self.mesgul:
            return
        hazir, _ = O.ocr_durumu() if not hasattr(self, "_ocr_hazir") else (self._ocr_hazir, "")
        if not hazir:
            messagebox.showwarning("PDF PRO", "Resimdeki yazıyı okumak için OCR gerekli (Tesseract).\n"
                                              "KURULUM.bat'ı tekrar çalıştırın.")
            return
        self._cv2_kontrol()
        if self.mesgul:          # bilesen kuruluyor
            return
        tek = fitz.open()
        tek.insert_pdf(b.doc, from_page=i, to_page=i)
        surum = b.surum

        def is_(il, ip):
            il(0, 1, "Resimdeki yazı okunuyor")
            try:
                return R.bul(tek[0], px, py, alan=alan)
            finally:
                pass

        def bitti(bilgi):
            tek.close()
            if b is not self.belge or b.surum != surum:
                return
            if bilgi is None:
                if yedek is not None:
                    self.gorunum._vurgu_temizle()
                    stil = {"aile": "Otomatik (orijinal)", "boyut": yedek["boyut"], "kalin": False, "italik": False,
                            "serif": False, "renk": (0, 0, 0), "hiza": "sol"}
                    self.gorunum._duzenleyici_ac("duzelt", i, yedek, yedek["bbox"], yedek["metin"], stil)
                    return
                self.durum_yaz("Burada okunabilir yazı bulunamadı. 'Resimde Yazı' ile yazının etrafına kutu "
                               "çizerek tekrar deneyin ya da 'Beyaz Kutu' + 'Yazı Ekle' kullanın.", hata=True)
                return
            self.gorunum.resim_duzenleyici_ac(i, bilgi)
        self.calistir("Resimdeki yazı okunuyor", is_, bitti)

    # ---------------------------------------------------------- SURUKLEYEREK SECILEN ALAN
    def alan_secildi(self, mod, i, rect, p0, p1):
        b = self.belge
        if mod == "beyaz_kutu":
            self.duzenle_islem("Beyaz kutu", lambda d: Z.beyaz_kutu(d[i], rect), i)
        elif mod == "resim_yazi":
            self.resimde_yazi_bul(i, None, None, alan=rect)
        elif mod == "vurgula":
            self.duzenle_islem("Vurgulama", lambda d: AR.vurgula(d[i], rect), i)
        elif mod == "karart":
            self.duzenle_islem("Karartma (kalıcı silme)", lambda d: AR.karart(d[i], rect), i)
        elif mod == "kirp":
            if b.doc.page_count > 1:
                c = messagebox.askyesnocancel("PDF PRO", "Kırpma TÜM sayfalara uygulansın mı?\n\n"
                                                         "Evet = tüm sayfalar   ·   Hayır = sadece bu sayfa")
                if c is None:
                    return
            else:
                c = False
            sayfalar = range(b.doc.page_count) if c else [i]

            def kirp(d):
                r0 = d[i].rect
                oran = (rect.x0 / r0.width, rect.y0 / r0.height, rect.x1 / r0.width, rect.y1 / r0.height)
                for s in sayfalar:
                    r = d[s].rect
                    AR.kirp(d[s], fitz.Rect(oran[0] * r.width, oran[1] * r.height, oran[2] * r.width, oran[3] * r.height))
            self.nesneleri_unut()
            self.duzenle_islem("Kırpma", kirp, i)
            self.mod_sec("sec")
        elif mod in ("metin_kutusu", "form_metin", "form_onay", "form_liste"):
            self._ek_alan_secildi(mod, i, rect)
        elif mod.startswith("sekil_"):
            ayar = self.yazi_ayar()
            tur = mod.split("_", 1)[1]
            renk = ayar["renk"] if ayar["renk"] != (0, 0, 0) else (0.8, 0.1, 0.1)
            self.duzenle_islem("Şekil", lambda d: AR.sekil(d[i], tur, p0, p1, renk=renk,
                                                          kalinlik=1.5 if not ayar["kalin"] else 3), i)

    # ---------------------------------------------------------- DAMGA
    def damga_baslat(self):
        if not self._belge_gerekli():
            return
        d = DG.Diyalog(self, "🔖 Damga", "Damgayı seçin, sonra sayfada koymak istediğiniz yere tıklayın.",
                       dugme="Sayfaya Koy →")
        metin = ttk.Combobox(d.govde, values=AR.HAZIR_DAMGALAR, width=26)
        metin.set(self.ayar.get("damga_metin", "ASLI GİBİDİR"))
        d.satir("Yazı:", metin, "Listeden seçin veya kendiniz yazın")
        renk = ttk.Combobox(d.govde, values=["Kırmızı", "Mavi", "Yeşil", "Siyah"], state="readonly", width=12)
        renk.set(self.ayar.get("damga_renk", "Kırmızı"))
        d.satir("Renk:", renk)
        boy = ttk.Spinbox(d.govde, from_=8, to=48, width=6)
        boy.set(self.ayar.get("damga_boy", 16))
        d.satir("Boyut:", boy)
        tarih = tk.BooleanVar(value=self.ayar.get("damga_tarih", True))
        d.tam_satir(ttk.Checkbutton(d.govde, text="Altına bugünün tarihini yaz", variable=tarih, style="Kart.TCheckbutton"))

        def topla():
            try:
                b_ = float(boy.get())
            except ValueError:
                raise ValueError("Boyut sayı olmalı.")
            if not metin.get().strip():
                raise ValueError("Damga yazısını girin.")
            return {"metin": metin.get().strip(), "renk": renk.get(), "boyut": b_, "tarih": tarih.get()}
        d.topla = topla
        s = d.ac()
        if not s:
            return
        self.ayar.update(damga_metin=s["metin"], damga_renk=s["renk"], damga_boy=s["boyut"], damga_tarih=s["tarih"])
        renkler = {"Kırmızı": (0.75, 0.08, 0.08), "Mavi": (0.1, 0.25, 0.7), "Yeşil": (0.1, 0.5, 0.2), "Siyah": (0, 0, 0)}
        f = Z.font_al(False, True, False)
        gen = f.text_length(s["metin"], s["boyut"]) + s["boyut"] * 1.2
        self.mod_sec("sec")
        self.damga_ayar = dict(s, renk_rgb=renkler.get(s["renk"], (0.75, 0.08, 0.08)),
                               boyut_pt=(gen, s["boyut"] * (2.4 if s["tarih"] else 1.75)))
        self.mod = "damga"
        self.gorunum.mod_ayarla("damga")
        self._mod_renkleri()
        self.durum_yaz("🔖 DAMGA: Sayfada koymak istediğiniz yere tıklayın. (Esc = vazgeç)")

    def damga_bas(self, i, px, py):
        a = self.damga_ayar
        if not a:
            return
        self.duzenle_islem("Damga", lambda d: AR.damga(d[i], (px, py), a["metin"], a["renk_rgb"], a["boyut"], a["tarih"]), i)
        self.mod_sec("sec")

    # ---------------------------------------------------------- FORM
    def form_alani_tikla(self, i, px, py):
        """Secim modunda form alanina tiklaninca degerini sorar. Alan yoksa False."""
        b = self.belge
        k = (id(b), b.surum, i)
        if k not in self._form_onbellek:
            self._form_onbellek = {k: [w for w in (b.doc[i].widgets() or [])]}
            self._form_onbellek[k] = [(fitz.Rect(w.rect), w.xref) for w in self._form_onbellek[k]]
        hedef = next((x for r, x in self._form_onbellek[k] if r.contains(fitz.Point(px, py))), None)
        if hedef is None:
            return False
        self.form_doldur(sadece=hedef)
        return True

    def form_doldur(self, sadece=None):
        b = self._belge_gerekli()
        if not b:
            return
        alanlar = AR.form_alanlari(b.doc)
        if sadece is not None:
            alanlar = [a for a in alanlar if a["xref"] == sadece]
        if not alanlar:
            messagebox.showinfo("PDF PRO", "Bu belgede doldurulabilir form alanı yok.\n"
                                           "Yazmak için 'Yazı Ekle' kullanabilirsiniz.")
            return
        d = DG.Diyalog(self, "📋 Form Doldur", f"{len(alanlar)} alan", dugme="Kaydet", genislik=520)
        kap = tk.Frame(d.govde, bg="white")
        kap.grid(row=0, column=0, columnspan=2, sticky="nsew")
        tuval = tk.Canvas(kap, bg="white", highlightthickness=0, width=480, height=min(420, 34 * len(alanlar) + 10))
        sb = ttk.Scrollbar(kap, orient="vertical", command=tuval.yview)
        ic = tk.Frame(tuval, bg="white")
        ic.bind("<Configure>", lambda e: tuval.configure(scrollregion=tuval.bbox("all")))
        tuval.create_window(0, 0, window=ic, anchor="nw")
        tuval.configure(yscrollcommand=sb.set)
        tuval.pack(side="left", fill="both", expand=True)
        if len(alanlar) > 12:
            sb.pack(side="left", fill="y")
        degiskenler = {}
        for r, a in enumerate(alanlar):
            tk.Label(ic, text=f"{a['ad']}  ", bg="white", fg=R_YAZI, font=(FONT, 9), anchor="w", width=24).grid(row=r, column=0, sticky="w", pady=2)
            if a["tur_adi"] in ("Onay kutusu", "Seçenek"):
                v = tk.BooleanVar(value=a["deger"] not in (None, "", "Off", False))
                ttk.Checkbutton(ic, variable=v).grid(row=r, column=1, sticky="w")
            elif a["secenekler"]:
                v = tk.StringVar(value=a["deger"] or "")
                ttk.Combobox(ic, textvariable=v, values=a["secenekler"], width=32).grid(row=r, column=1, sticky="w")
            else:
                v = tk.StringVar(value=a["deger"] or "")
                ttk.Entry(ic, textvariable=v, width=36).grid(row=r, column=1, sticky="w")
            degiskenler[a["xref"]] = v
        d.topla = lambda: {x: v.get() for x, v in degiskenler.items()}
        s = d.ac()
        if s is None:
            return
        sonuc = {}
        self.duzenle_islem("Form doldurma", lambda doc: sonuc.update(n=AR.form_doldur(doc, s)))
        self.durum_yaz(f"✔ {sonuc.get('n', 0)} alan dolduruldu.", basari=True)

    # ---------------------------------------------------------- DIGER ARACLAR
    def a4e_sigdir(self):
        b = self._belge_gerekli()
        if not b:
            return
        sec = self._secili() if len(b.secili) > 1 else list(range(b.doc.page_count))
        if not messagebox.askyesno("PDF PRO", f"{len(sec)} sayfa A4 boyutuna getirilsin mi?\n"
                                              "(Yatay sayfalar yatay A4 olur, oran korunur)"):
            return
        self.nesneleri_unut()
        self.duzenle_islem("A4'e sığdırma", lambda d: AR.a4e_sigdir(d, sec))

    def resimleri_cikar(self):
        if not self._belge_gerekli():
            return
        k, klasor = self.kaynak_dosya(), self.cikti_yolu("resimler", klasor_mu=True)

        def is_(il, ip):
            d = fitz.open(k)
            try:
                return AR.resimleri_cikar(d, klasor, ilerleme=il)
            finally:
                d.close()
        self.calistir("Resimler çıkarılıyor", is_,
                      lambda r: self.sonuc_goster(f"{len(r)} resim kaydedildi.", klasor=klasor) if r
                      else messagebox.showinfo("PDF PRO", "Belgede çıkarılacak resim yok."))

    # ---------------------------------------------------------- OCR
    def ocr_aranabilir(self):
        if not self._belge_gerekli():
            return
        s = DG.OcrDiyalog(self).ac()
        if not s:
            return

        def bitti(r):
            if r[1] == 0:
                messagebox.showinfo("PDF PRO", "Tüm sayfalarda zaten yazı vardı; OCR gerekmedi.\n"
                                               "Yine de okutmak için 'Zaten yazısı olan sayfalara dokunma' işaretini kaldırın.")
            else:
                self.durum_yaz(f"✔ {r[1]} sayfa OCR ile okundu. Artık 'Yazı Düzelt' ve arama kullanılabilir.", basari=True)
        self.dosya_islem("OCR", lambda k, c, il, ip: O.aranabilir_pdf(k, c, s["dil"], s["dpi"], s["sadece"], il, ip),
                         arka_plan=True, bitince=bitti)

    def metin_cikar(self):
        b = self._belge_gerekli()
        if not b:
            return
        kaynak = self.kaynak_dosya()

        def bitti(metin):
            def kaydet_sor(tur):
                return filedialog.asksaveasfilename(defaultextension="." + tur,
                                                    initialfile=os.path.splitext(b.ad)[0] + "_metin." + tur,
                                                    initialdir=os.path.dirname(b.yol) if b.yol else None,
                                                    filetypes=[(tur.upper(), "*." + tur)])
            DG.MetinPenceresi(self, metin, b.ad, kaydet_sor)
        self.calistir("Metin çıkarılıyor", lambda il, ip: O.metin_cikar(kaynak, "tur+eng", 300, True, il, ip),
                      bitti, iptal_edilebilir=True)

    # ---------------------------------------------------------- donusturme
    def word_e(self):
        if not self._belge_gerekli():
            return
        k, c = self.kaynak_dosya(), self.cikti_yolu("word", ".docx")
        self.calistir("Word'e çevriliyor", lambda il, ip: D.pdf_to_word(k, c, il),
                      lambda r: self.sonuc_goster("Word dosyası hazır.", r[0], uyari=r[1]))

    def excel_e(self):
        if not self._belge_gerekli():
            return
        k, c = self.kaynak_dosya(), self.cikti_yolu("excel", ".xlsx")
        self.calistir("Excel'e çevriliyor", lambda il, ip: D.pdf_to_excel(k, c, True, il),
                      lambda r: self.sonuc_goster(f"Excel hazır: {r[1]} tablo aktarıldı.", r[0], uyari=r[2]))

    def resme(self):
        b = self._belge_gerekli()
        if not b:
            return
        d = DG.Diyalog(self, "🖼 Resme Dönüştür", "Sayfalar resim olarak yeni bir klasöre kaydedilir.", dugme="Dönüştür")
        bic = ttk.Combobox(d.govde, values=["png", "jpg"], state="readonly", width=8)
        bic.current(0)
        d.satir("Biçim:", bic)
        dpi = ttk.Combobox(d.govde, values=["100", "150", "200", "300"], state="readonly", width=8)
        dpi.set("200")
        d.satir("Çözünürlük:", dpi, "200 = ekran/e-posta · 300 = baskı")
        ar = d.sayfa_alani(",".join(str(i + 1) for i in self._secili()) if len(b.secili) > 1 else "")
        d.topla = lambda: {"bicim": bic.get(), "dpi": int(dpi.get()), "aralik": ar.get()}
        s = d.ac()
        if not s:
            return
        k, klasor = self.kaynak_dosya(), self.cikti_yolu("resimler", klasor_mu=True)
        self.calistir("Resimler oluşturuluyor", lambda il, ip: D.pdf_to_resim(k, klasor, s["bicim"], s["dpi"], s["aralik"], il),
                      lambda r: self.sonuc_goster(f"{len(r)} resim kaydedildi.", klasor=klasor))

    def resimden_pdf(self):
        ys = filedialog.askopenfilenames(title="Resimleri seçin", filetypes=RESIM_TUR,
                                         initialdir=self.ayar.get("son_klasor"))
        if not ys:
            return
        self.ayar["son_klasor"] = os.path.dirname(ys[0])
        gecici = os.path.join(tempfile.gettempdir(), "pdfpro_resimler.pdf")

        def bitti(r):
            self._gecici_belge(r, os.path.splitext(os.path.basename(ys[0]))[0] + ".pdf")
            self.durum_yaz(f"✔ {len(ys)} resim PDF yapıldı. Kaydetmek için Ctrl+S.", basari=True)

        self.calistir("PDF oluşturuluyor", lambda il, ip: D.resim_to_pdf(list(ys), gecici, "A4 otomatik", 5, il), bitti)

    def _office_ac(self, y):
        c = C.benzersiz_yol(os.path.splitext(y)[0] + ".pdf")
        fonk = D.word_to_pdf if y.lower().endswith((".doc", ".docx", ".rtf", ".odt")) else D.excel_to_pdf
        self.calistir("PDF'e çevriliyor", lambda il, ip: fonk(y, c, ilerleme=il), lambda r: self.ac([r]))

    def wordden_pdf(self):
        self._office_toplu(WORD_TUR, D.word_to_pdf, "Word")

    def excelden_pdf(self):
        self._office_toplu(EXCEL_TUR, D.excel_to_pdf, "Excel")

    def _office_toplu(self, turler, fonk, ad):
        ys = filedialog.askopenfilenames(title=f"{ad} dosyalarını seçin", filetypes=turler,
                                         initialdir=self.ayar.get("son_klasor"))
        if not ys:
            return
        self.ayar["son_klasor"] = os.path.dirname(ys[0])
        hedefler = [C.benzersiz_yol(os.path.splitext(y)[0] + ".pdf") for y in ys]

        def is_(il, ip):
            hatalar, tamam = [], []
            for i, (y, h) in enumerate(zip(ys, hedefler)):
                if ip():
                    break
                il(i, len(ys), os.path.basename(y))
                try:
                    fonk(y, h)
                    tamam.append(h)
                except Exception as e:
                    hatalar.append(f"{os.path.basename(y)}: {e}")
            return tamam, hatalar

        def bitti(r):
            tamam, hatalar = r
            if tamam:
                self.ac(tamam[:5])
            if hatalar:
                messagebox.showwarning("PDF PRO", "Dönüştürülemeyenler:\n\n" + "\n".join(hatalar))
            self.durum_yaz(f"✔ {len(tamam)} dosya PDF yapıldı (aynı klasöre kaydedildi).", basari=True)

        self.calistir(f"{ad} → PDF", is_, bitti, iptal_edilebilir=True)

    # ---------------------------------------------------------- koruma
    def sikistir(self):
        b = self._belge_gerekli()
        if not b:
            return
        k = self.kaynak_dosya()
        try:
            mevcut = boyut_yaz(os.path.getsize(k))
        except Exception:
            mevcut = None
        s = DG.SikistirDiyalog(self, mevcut).ac()
        if not s:
            return
        c = self.cikti_yolu("kucuk")
        adlar = {"hafif": "Hafif", "orta": "Orta", "guclu": "Güçlü", "en_kucuk": "En küçük", "asiri": "Aşırı"}

        def bitti(r):
            yol, once, sonra, sev = r
            ek = f"\nKullanılan seviye: {adlar.get(sev, sev)}"
            uyari = None
            if s["hedef_kb"] and sonra > s["hedef_kb"] * 1024:
                uyari = (f"Hedeflenen {s['hedef_kb'] / 1024:g} MB'a inilemedi (en küçük hali bu). "
                         "Siyah-beyaz seçeneğini deneyin ya da belgeyi 'Böl' ile parçalayın.")
            if sonra >= once * 0.97:
                self.sonuc_goster(f"Dosya zaten küçük; daha fazla sıkıştırılamadı.\n{boyut_yaz(once)} → {boyut_yaz(sonra)}", yol, uyari=uyari)
            else:
                self.sonuc_goster(f"{boyut_yaz(once)} → {boyut_yaz(sonra)}   (%{(1 - sonra / once) * 100:.0f} küçüldü){ek}", yol, uyari=uyari)
        self.calistir("Sıkıştırılıyor", lambda il, ip: C.sikistir(k, c, s["seviye"], s["hedef_kb"], s["gri"], il, ip),
                      bitti, iptal_edilebilir=True)

    def sifrele(self):
        b = self._belge_gerekli()
        if not b:
            return
        s = DG.SifreDiyalog(self).ac()
        if not s:
            return
        c = self.cikti_yolu("sifreli")
        try:
            b.doc.save(c, garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_AES_256,
                       user_pw=s["sifre"], owner_pw=s["sifre"],
                       permissions=int(fitz.PDF_PERM_PRINT | fitz.PDF_PERM_COPY | fitz.PDF_PERM_ACCESSIBILITY))
            self.sonuc_goster("Şifreli kopya kaydedildi. Şifreyi unutmayın — kurtarılamaz.", c)
        except Exception as e:
            messagebox.showerror("PDF PRO", f"Şifrelenemedi:\n{e}")

    def sifre_kaldir(self):
        b = self._belge_gerekli()
        if not b:
            return
        c = self.cikti_yolu("sifresiz")
        try:
            b.doc.save(c, garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE)
            self.sonuc_goster("Şifresiz kopya kaydedildi.", c)
        except Exception as e:
            messagebox.showerror("PDF PRO", f"Kaydedilemedi:\n{e}")

    # ---------------------------------------------------------- arka plan isleri
    def _ocr_kontrol(self):
        def is_():
            hazir, metin = O.ocr_durumu()
            self.kuyruk.put(("ocr", hazir, metin))
        threading.Thread(target=is_, daemon=True).start()

    def calistir(self, baslik, fonk, bitince=None, iptal_edilebilir=False):
        if self.mesgul:
            messagebox.showinfo("PDF PRO", "Bir işlem zaten sürüyor, lütfen bitmesini bekleyin.")
            return
        self.mesgul = True
        self.mesgul_render = True
        self.iptal_istegi = False
        self.durum_yaz(f"⏳ {baslik}…")
        self.ilerleme.config(value=0, maximum=100)
        if iptal_edilebilir:
            self.iptal_dugme.pack(side="right", padx=(0, 4), before=self.durum)
        self.ilerleme.pack(side="right", padx=8, before=self.durum)
        self.config(cursor="watch")

        def ilerleme(i, n, metin=""):
            self.kuyruk.put(("ilerleme", i, n, metin, baslik))

        def is_():
            try:
                self.kuyruk.put(("bitti", bitince, fonk(ilerleme, lambda: self.iptal_istegi)))
            except PdfProHata as e:
                self.kuyruk.put(("hata", str(e), None))
            except Exception as e:
                hata_kaydet(traceback.format_exc())
                self.kuyruk.put(("hata", f"Beklenmeyen hata:\n{e}", None))

        threading.Thread(target=is_, daemon=True).start()

    def _iptal(self):
        self.iptal_istegi = True
        self.durum_yaz("İptal ediliyor…")

    def _serbest(self):
        self.mesgul = False
        self.mesgul_render = False
        self.config(cursor="")
        self.ilerleme.pack_forget()
        self.iptal_dugme.pack_forget()

    def _kuyruk_isle(self):
        try:
            while True:
                m = self.kuyruk.get_nowait()
                if m[0] == "ilerleme":
                    _, i, n, metin, baslik = m
                    self.ilerleme.config(value=(i / n * 100) if n else 0)
                    self.durum_yaz(f"⏳ {baslik}: {metin}")
                elif m[0] == "bitti":
                    self._serbest()
                    self.durum_yaz("✔ Tamamlandı.", basari=True)
                    if m[1]:
                        try:
                            m[1](m[2])
                        except Exception as e:
                            hata_kaydet(traceback.format_exc())
                            messagebox.showerror("PDF PRO", str(e))
                    self.gorunum.ciz()
                    self.kucuk.ciz()
                elif m[0] == "hata":
                    self._serbest()
                    self.durum_yaz("✖ " + m[1].split("\n")[0], hata=True)
                    messagebox.showerror("PDF PRO", m[1])
                    self.gorunum.ciz()
                    self.kucuk.ciz()
                elif m[0] == "guncelleme_hazir":
                    self._guncelleme_etiketi(m[1])
                elif m[0] == "dis_ac":
                    self.one_getir()
                    if m[1]:
                        self.ac(m[1])
                elif m[0] == "ocr":
                    self._ocr_hazir = m[1]
                    self.ocr_etiket.config(text=("✔ " if m[1] else "⚠ ") + m[2],
                                           fg=R_BASARI if m[1] else R_TEHLIKE)
        except queue.Empty:
            pass
        self.after(100, self._kuyruk_isle)

    # ---------------------------------------------------------- sonuc penceresi
    def sonuc_goster(self, mesaj, yol=None, klasor=None, uyari=None):
        p = tk.Toplevel(self)
        p.title("İşlem tamam")
        p.configure(bg=R_KART)
        p.transient(self)
        p.resizable(False, False)
        tk.Frame(p, bg=R_BASARI, height=6).pack(fill="x")
        tk.Label(p, text="✔", bg="#D1FAE5", fg=R_BASARI, font=(FONT, 22, "bold"), width=3).pack(pady=(16, 4))
        tk.Label(p, text=mesaj, bg=R_KART, fg=R_YAZI, font=(FONT, 11), wraplength=440, justify="center").pack(padx=24, pady=4)
        if yol:
            tk.Label(p, text=yol, bg=R_KART, fg=R_SOLUK, font=(FONT, 9), wraplength=440).pack(padx=24)
        if uyari:
            tk.Label(p, text="⚠ " + uyari, bg="#FFF4E5", fg="#8A4B00", font=(FONT, 9), wraplength=440,
                     justify="left", padx=10, pady=8).pack(padx=20, pady=(10, 0), fill="x")
        d = ttk.Frame(p, style="Kart.TFrame")
        d.pack(pady=16)
        if yol and os.path.isfile(yol):
            if yol.lower().endswith(".pdf"):
                ttk.Button(d, text="📄 PDF PRO'da Aç", style="Ana.TButton",
                           command=lambda: (p.destroy(), self.ac([yol]))).pack(side="left", padx=4)
            else:
                ttk.Button(d, text="📄 Dosyayı Aç", style="Ana.TButton",
                           command=lambda: (dosya_ac(yol), p.destroy())).pack(side="left", padx=4)
        hedef = yol or klasor
        if hedef:
            ttk.Button(d, text="📁 Klasörde Göster", style="Ikincil.TButton",
                       command=lambda: (klasorde_goster(hedef), p.destroy())).pack(side="left", padx=4)
        ttk.Button(d, text="Tamam", style="Ikincil.TButton", command=p.destroy).pack(side="left", padx=4)
        p.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - p.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - p.winfo_height()) // 3
        p.geometry(f"+{max(0, x)}+{max(0, y)}")
        p.grab_set()
        p.bind("<Escape>", lambda e: p.destroy())

    # ---------------------------------------------------------- yardim
    def kilavuz(self):
        p = tk.Toplevel(self)
        p.title("PDF PRO - Kullanım Kılavuzu")
        p.geometry("780x660")
        t = scrolledtext.ScrolledText(p, wrap="word", font=(FONT, 10), relief="flat", padx=16, pady=12)
        t.pack(fill="both", expand=True)
        t.insert("1.0", KILAVUZ)
        t.tag_configure("b", font=(FONT, 12, "bold"), foreground=R_BASLIK, spacing1=10)
        for n, s in enumerate(KILAVUZ.split("\n"), start=1):
            if s.startswith("■"):
                t.tag_add("b", f"{n}.0", f"{n}.end")
        t.config(state="disabled")

    def hakkinda(self):
        messagebox.showinfo("PDF PRO", f"PDF PRO {SURUM}\n\nPDF görüntüleme ve düzenleme, birleştirme, OCR,\n"
                                       "dönüştürme, imza / antet / filigran, form,\n"
                                       "karşılaştırma, yapay zeka (özet, çeviri),\n"
                                       "belge paketi ve iş akışları.")

    def one_getir(self):
        """Pencereyi simge durumundan cikarip one getirir."""
        try:
            if self.state() == "iconic":
                self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.after(300, lambda: self.attributes("-topmost", False))
            self.focus_force()
        except Exception:
            pass

    def windows_tanit(self):
        from . import sistem
        if not WINDOWS:
            messagebox.showinfo("PDF PRO", "Bu özellik Windows içindir.")
            return
        try:
            sistem.kaydet()
        except Exception as e:
            hata_kaydet(traceback.format_exc())
            messagebox.showerror("PDF PRO", f"Windows'a tanıtılamadı:\n{e}")
            return
        if messagebox.askyesno("PDF PRO", "PDF PRO Windows'a tanıtıldı.\n\n"
                                          "• PDF'e sağ tık → 'Birlikte aç' listesinde PDF PRO var\n"
                                          "• Sağ tık menüsünde 'PDF PRO ile aç' var (Windows 11'de 'Diğer seçenekleri göster')\n"
                                          "• Klasörlerde PDF simgesi yerine ilk sayfa görünür; Dosya Gezgini'nde Alt+P ile "
                                          "sağda önizleme açılır\n\n"
                                          "PDF'lere ÇİFT TIKLAYINCA da PDF PRO açılsın mı?\n"
                                          "(Evet derseniz Windows ayarları açılır; orada PDF PRO'yu seçin.)"):
            sistem.varsayilan_ayarlari_ac()

    def hata_kaydi_ac(self):
        if os.path.isfile(HATA_KAYDI):
            dosya_ac(HATA_KAYDI)
        else:
            messagebox.showinfo("PDF PRO", "Hata kaydı yok.")

    def kapat(self):
        for b in list(self.belgeler):
            if b.degisti and not self.belge_kapat(b):
                return
        try:
            if self.state() == "zoomed":
                self.ayar["tam_ekran"] = True
            else:
                self.ayar["tam_ekran"] = False
                self.ayar["pencere"] = self.geometry()
            if hasattr(self, "_ya_boyut"):
                self.ayar.update(yazi_aile=self._ya_aile.get(), yazi_boyut=self._ya_boyut.get(), yazi_renk=self._ya_renk.get(),
                                 yazi_kalin=self._ya_kalin.get(), yazi_serif=self._ya_serif.get())
        except Exception:
            pass
        ayar_yaz(self.ayar)
        for b in self.belgeler:
            b.kapat()
        self.destroy()
        if self._yeniden:
            self._yeniden_ac()

    # ---------------------------------------------------------- otomatik guncelleme
    def _guncelleme_baslangic(self):
        from . import guncelleme as GN
        GN.basarili()                     # arayuz acildi: son guncelleme kalici
        mesaj = os.environ.pop("PDFPRO_GUNCELLEME_MESAJI", "")
        if mesaj:
            self.durum_yaz("⬆ " + mesaj, basari="güncellendi" in mesaj, hata="geri dönüldü" in mesaj)
            if "geri dönüldü" in mesaj:
                messagebox.showwarning("PDF PRO", mesaj)

        def is_():
            try:
                h = GN.bagimlilik_gerekli_mi()
                if h:
                    GN.bagimliliklari_kur(h)
            except Exception:
                pass
            try:
                bilgi = GN.kontrol_et_ve_indir()
            except Exception:
                bilgi = None
            if bilgi:
                self.kuyruk.put(("guncelleme_hazir", bilgi))
        threading.Thread(target=is_, daemon=True).start()
        self.after(6 * 3600 * 1000, self._guncelleme_baslangic)

    def _guncelleme_etiketi(self, bilgi):
        if getattr(self, "_gun_etiket", None) is not None:
            try:
                self._gun_etiket.destroy()
            except tk.TclError:
                pass
        e = tk.Label(self.ocr_etiket.master, text=f"  ⬆ {bilgi['surum']} hazır · Güncelle  ",
                     bg="#F97316", fg="white", font=(FONT, 9, "bold"), cursor="hand2")
        self.ocr_etiket.pack_forget()          # yer acilsin
        e.pack(side="right", fill="y")
        e.bind("<Button-1>", lambda ev: self.yeniden_baslat())
        IpucuBalonu(e, (bilgi.get("notlar") or "Yenilikler ve düzeltmeler")[:400] +
                    "\n\nTıklayın: program kapanıp yeni sürümle açılır. Tıklamazsanız bir sonraki açılışta yüklenir.")
        self._gun_etiket = e
        self.durum_yaz(f"⬆ PDF PRO {bilgi['surum']} indirildi; program yeniden açılınca yüklenecek.", basari=True)

    def yeniden_baslat(self):
        self._yeniden = True
        self.kapat()
        try:
            if self.winfo_exists():
                self._yeniden = False      # kullanici kapatmaktan vazgecti (kaydedilmemis belge)
        except tk.TclError:
            pass

    def _yeniden_ac(self):
        try:
            if self._sok is not None:
                self._sok.close()
        except Exception:
            pass
        exe = os.path.join(PROGRAM_KLASORU, "PDF_PRO.exe")
        try:
            if WINDOWS and os.path.isfile(exe):
                subprocess.Popen([exe], cwd=PROGRAM_KLASORU)
            else:
                subprocess.Popen([sys.executable, os.path.join(PROGRAM_KLASORU, "PDF_PRO.pyw")], cwd=PROGRAM_KLASORU)
        except Exception:
            pass

    def yonetici_ac(self):
        from . import yonetici
        try:
            yonetici.paneli_ac(self)
        except Exception as e:
            hata_kaydet(traceback.format_exc())
            messagebox.showerror("PDF PRO", f"Yönetici paneli açılamadı:\n{e}")


# ================================================================== kilavuz
KILAVUZ = """PDF PRO — Kullanım Kılavuzu

Ekran düzeni
• Üstte menüler: Dosya · Giriş · Sayfa · İşaretle · İmza & Damga · Form · Dönüştür · Araçlar · Koruma · Yapay Zeka · Otomasyon · Yardım. Menüye tıklayınca altında o menünün düğmeleri çıkar. Düğmenin üzerinde durunca kısa açıklama görünür.
• Altında açık belgelerin sekmeleri. Birden çok PDF aynı anda açık olabilir; ✕ ile kapatılır. Kaydedilmemiş belgenin adının başında ● olur.
• Solda sayfaların küçük resimleri, ortada belge, altta sayfa numarası ve yakınlaştırma.
• Dosyaları pencereye sürükleyip bırakarak da açabilirsiniz.

■ Açma ve kaydetme
• Ctrl+O: Aç  ·  Ctrl+S: Kaydet  ·  Ctrl+Shift+S: Farklı Kaydet  ·  Ctrl+W: Kapat
• Kaydet, açtığınız dosyanın üzerine yazar. Orijinali korumak istiyorsanız "Farklı Kaydet" kullanın.
• Ctrl+Z: Geri Al  ·  Ctrl+Y: Yinele (son 20 işlem)
• Word veya Excel dosyası açarsanız önce PDF'e çevrilir (Microsoft Office gerekir).

■ Görüntüleme
• Fare tekeriyle kaydırın; Ctrl + fare tekeri ile yakınlaştırın, Shift + teker yatay kaydırır. Orta tuşla sürükleyerek de kaydırabilirsiniz.
• Yön tuşları, Boşluk (sayfa aşağı) ve Page Up / Page Down çalışır.
• Alttaki ↔ genişliğe, ▣ tek sayfaya sığdırır. Page Up / Page Down ile sayfa değiştirin.
• Soldaki küçük resme tıklayınca o sayfaya gider.

■ Yazı Düzelt (Giriş menüsü)
• "✏ Yazı Düzelt"e basın, değiştirmek istediğiniz yazının üzerine gelin — turuncu çerçeve çıkar. Tıklayın, yazıyı değiştirin, Enter'a basın.
• Yazı aynı yerde, aynı boyutta, aynı renkte ve kalınlıkta yeniden yazılır; arka plan, çizgiler ve resimler bozulmaz.
• Normal moddayken yazıya ÇİFT TIKLAMAK da düzeltmeyi açar.
• Taranmış (resim) belgede de yazı düzeltilebilir: aşağıdaki "Resimdeki yazıyı düzeltme" bölümüne bakın.

■ Resimdeki yazıyı düzeltme (tarama, kimlik, ehliyet, pasaport)
• "✏ Yazı Düzelt" açıkken resmin üzerindeki yazıya tıklayın. Program yazıyı okur (yan veya ters duran yazıları da), yeşil çerçeveyle gösterir ve düzenleme kutusunu açar.
• Enter'a basınca eski yazı resimden silinir, arka plandaki desen/renk yeniden oluşturulur ve yeni yazı aynı yerde, aynı renk ve boyda, aynı yönde yazılır.
• Tıklama ile bulunamazsa "🔎 Resimde Yazı" ile yazının etrafına fareyle kutu çizin.
• İlk kullanımda arka planı bozmadan silmek için küçük bir bileşen (OpenCV) kurulması istenebilir; "Evet" deyin.

■ Yazı tipi, boyut, renk, hizalama
• Düzenleme kutusu açılınca üstünde koyu bir çubuk çıkar: yazı tipi, boyut, K (kalın), renk kutusu, hizalama (⇤ sola, ⇔ ortala, ⇥ sağa), ✔ uygula, ✖ vazgeç.
• "Otomatik (orijinal)" belgenin kendi yazı tipini kullanır. Listede bilgisayarınızdaki tüm yazı tipleri vardır (Arial, Calibri, Segoe UI, Times New Roman…).
• "Yazı Ekle" için varsayılan yazı tipi / boyut / renk Giriş menüsündeki "Yazı ekleme ayarı"ndan seçilir.

■ Ara / İşaretle
• 🔍 Ara (Ctrl+F): Yazar yazmaz bulur, sarı ile işaretler; Enter / F3 sonraki, Shift+Enter önceki. Türkçe İ/ı farkını otomatik yakalar.
• 🔁 Bul-Değiştir (Ctrl+H): Bir yazıyı tüm belgede, yazı tipini ve yerini koruyarak değiştirir (ör. eski acente adı → yeni acente adı).
• 🖍 Vurgula: Fosforlu kalem. ⬛ Karart: Kimlik no, adres gibi bilgileri KALICI gizler (alttaki yazı ve resim gerçekten silinir).
• ▭ ◯ ╱ ➚ Şekiller: Dikdörtgen, elips, çizgi, ok. Renk, Giriş'teki yazı rengidir.
• ✂ Kırp: Sayfada kalacak alanı seçin (taramaların kenar boşluklarını atmak için). 📐 A4'e Sığdır: Farklı boyuttaki taramaları A4 yapar.
• 💬 Not: Sayfaya yapışkan not / yorum. 🗨 Metin Kutusu: Çerçeveli açıklama kutusu (Türkçe karakterli).
• 🔖 Damga (İmza & Damga menüsü): "ASLI GİBİDİR", "ONAYLANDI"… tarihli kaşe damgası; tıkladığınız yere basılır.

■ Yazı Ekle / Beyaz Kutu
• "🔤 Yazı Ekle": Araç çubuğundan boyut, renk, kalın seçin; sayfada yazacağınız yere tıklayın, yazın, Enter.
• "⬜ Beyaz Kutu": Silmek istediğiniz alanın üstüne fareyle kutu çizin; o alan beyazla örtülür.

■ İmza / Kaşe
• "✍ İmza / Kaşe" → resmi seçin (son kullandıklarınız hatırlanır), genişliği ayarlayın, "Sayfaya Yerleştir".
• Fareyi sayfanın üstünde gezdirince imzanın gölgesi görünür; tıkladığınız yere konur. İsterseniz fareyle kutu çizin, imza o kutuya sığdırılır.
• "Beyaz arka planı kaldır" kağıdın beyazını siler, sadece mürekkep kalır. "Tüm sayfalarda aynı yere" seçeneği de var.
• "Son kullanılanlar"daki imzaya tıklamak yeterli: pencere kapanır, doğrudan sayfaya koyarsınız.
• Konulan imza / kaşe seçili gelir: KÖŞELERDEN sürükleyerek büyütüp küçültün (oran bozulmaz), İÇİNDEN tutup istediğiniz yere taşıyın.
• Sonradan değiştirmek için normal modda imzanın üstüne tıklayın. Yön tuşları 1 nokta, Shift + yön tuşu 10 nokta kaydırır. Delete siler.
• Not: Taşıma / boyutlama belge açıkken çalışır; belge kapatılıp yeniden açılınca imza sayfanın parçası olur (Ctrl+Z ile geri almak gibi).

■ Sayfa işlemleri (Sayfa menüsü ve soldaki küçük resimler)
• Küçük resimde Ctrl+tık birden çok sayfa seçer, Shift+tık aralık seçer.
• Küçük resmi sürükleyip başka yere bırakarak sayfa sırasını değiştirin (turuncu çizgi yeni yeri gösterir).
• Sağ tık: döndür, sil, boş sayfa / dosyadan sayfa ekle, yeni belge olarak ayır.
• Böl: Belgeyi her sayfa ayrı, her N sayfada bir veya "1-3, 4-son" gibi aralıklarla parçalara ayırır.
• Birleştir: Birden çok PDF ve resmi sıraya koyup tek belge yapar; sonuç yeni sekmede açılır.

■ Antet, Filigran, Sayfa No (İmza & Damga menüsü)
• Antet: Word'deki antetli boş kağıdınızı PDF olarak kaydedip seçin. 2 sayfalı antette 2. sayfa devam sayfaları için kullanılır.
• Filigran: GİZLİDİR, TASLAK, ASLI GİBİDİR… veya logo. Koyuluk %10-20 önerilir.
• Sayfa No: "Sayfa 1 / 5" gibi.
• Sonuç hemen ekranda görünür; beğenmezseniz Ctrl+Z.

■ OCR (Araçlar menüsü)
• "OCR": Taranmış sayfaların yazısını okur. Sonra kopyalama ve "Yazı Düzelt" kullanılabilir.
• "Metni Çıkar": Tüm yazıyı pencerede gösterir; kopyalayın veya TXT/Word kaydedin.

■ Koruma
• Şifre Koy, Şifreyi Kaldır: Açık belge değişmez, yanına ayrı bir kopya kaydedilir.
• ⬛ Karart ve 🧹 Bilgileri Temizle (yazar, program, tarih gibi gizli belge bilgileri).

■ Güncellemeler ve Yönetici
• PDF PRO açılışta yeni sürüm olup olmadığına bakar. Varsa sadece değişen dosyaları arka planda indirir; üst çubukta turuncu "⬆ … hazır · Güncelle" çıkar. Tıklarsanız hemen, tıklamazsanız bir sonraki açılışta güncellenir.
• Her güncelleme yöneticinin imzasını taşır; imza tutmazsa yüklenmez. Yeni sürüm açılamazsa program kendiliğinden önceki sürüme döner.
• Yardım → 🛡 Yönetici: kullanıcı adı ve şifreyle girilir. Yeni sürüm yayınlama, sürüm geçmişi, kaynak arşivi ve yeni bilgisayar için kurulum dosyası buradadır.
• Kurulum dosyası (PDF_PRO_Kurulum.exe): Yönetici → Kaynak Dosyalar → "Kurulum dosyası oluştur". Tek dosya; Python, kütüphaneler ve OCR içinde. Karşı taraf çift tıklayıp sihirbazı izler. "GitHub'a da yükle" seçilirse herkes aynı linkten indirebilir.

■ Dosya menüsü (yeni)
• 📠 Tara: Tarayıcıdan sayfa sayfa tarar, tek PDF yapar (isterseniz otomatik OCR).
• 📧 E-posta: Outlook'ta PDF ekli yeni ileti açar (10 MB üstüyse önce sıkıştırabilir).
• 🕘 Yedekler: Her "Kaydet"te dosyanın eski hali saklanır (son 10). Buradan eski hali açın veya dosyayı geri döndürün.

■ İmza + Kaşe Setleri
• "🖋 İmza Setleri": imzanızı ve kaşenizi bir set olarak kaydedin (genişlikleriyle). "⚡ Seti Koy" ile tek tıkla ikisi yan yana gelir; her biri ayrıca taşınıp boyutlanabilir.

■ Form
• 📋 Form Doldur: Doldurulabilir alanları liste halinde gösterir. Seç modunda alana tıklamak da açar.
• ✨ Otomatik Algıla: "Adı: ______", "Tarih ......", alt çizgiler ve küçük kutucuklar otomatik doldurulabilir alana çevrilir.
• ▭ Metin Alanı, ☑ Onay Kutusu, ☰ Açılır Liste: Elle alan ekleyin. 🔏 Formu Kilitle: değerleri kalıcı yapar.

■ Dönüştür
• PDF → Word, Excel, PowerPoint, Resim, Metin, Markdown, PDF/A (arşiv).
• Resim, Word, Excel, PowerPoint, HTML / web adresi → PDF.

■ Araçlar
• 🗜 Sıkıştır (hedef MB yazılabilir) · 🔍 OCR / Metni Çıkar.
• ⚖ Karşılaştır: İki PDF yan yana; solda silinen (kırmızı), sağda eklenen (yeşil) yazılar.
• ▦ QR / Barkod: Belgedeki kodları okur, doğrulama linkini tek tıkla açar.
• 🔧 Onar: Bozuk / yarım inmiş PDF'ten kurtarılabilen sayfaları çıkarır.

■ Yapay Zeka
• İlk kullanımda ⚙ Ayarlar'dan ücretsiz bir anahtar girin (Google Gemini veya Groq; linki pencerede). Anahtar sadece bu bilgisayarda durur.
• 🧠 Özetle: Türkçe özet + tarih, tutar, ad, numara listesi. Anahtar yoksa internetsiz basit özet çıkarılır.
• 💬 Belgeye Sor: "IMO numarası ne?", "Son tarih hangisi?" gibi sorular.
• 🌍 Çevir: Yazılar sayfadaki yerlerinde çevrilir; tablo, logo, imza aynen kalır. Sonuç yeni sekmede açılır.

■ Otomasyon
• 📦 Belge Paketi: Gemi geliş evrakı gibi sıralı listeye dosyaları sürükleyin; tek PDF, yer imli, istenen ada (ör. GEMİ_GELIS_tarih) ve MB sınırına göre.
• ⚙ İş Akışları: OCR, damga, sayfa no, imza seti, filigran, antet, sıkıştır, PDF/A, şifre adımlarını kaydedin; açık belgeye, seçilen dosyalara veya bir klasördeki tüm PDF'lere tek tıkla uygulayın.

Sorun olursa
• Beklenmeyen hatalar program klasöründeki hata_kaydi.txt dosyasına yazılır (Yardım → Hata Kaydı).
"""


def calistir(acilacaklar=(), sok=None):
    try:
        uyg = Uygulama(acilacaklar, sok)
        uyg.mainloop()
    except Exception:
        hata_kaydet(traceback.format_exc())
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("PDF PRO", "Program başlatılamadı:\n\n" + traceback.format_exc()[-1500:])
        except Exception:
            pass
        raise
