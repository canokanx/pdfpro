# -*- coding: utf-8 -*-
"""
PDF PRO - Kolay kullanim (ana pencereye karisim sinifi olarak eklenir)
  * Sik kullanilanlar seridi (kullandikca ogrenir, sag tikla sabitlenir)
  * "▾" acilir arac menuleri (az kullanilan araclar)
  * Belgede sag tik menusu (yaziya / sayfaya gore)
  * Ilk acilis tanitim turu, klavye kisayollari penceresi (F1)
  * Gorunum ayarlari (acik / koyu tema, arayuz buyuklugu)
  * Son acilan dosyalar: ilk sayfa resimli kartlar
"""
import base64
import hashlib
import os
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from . import tema as TM
from . import vitrin as V

VARSAYILAN_SIK = ["Birleştir", "Sıkıştır", "Word", "İmza / Kaşe", "Yazı Düzelt", "OCR"]
SIK_ADET = 6

KISAYOLLAR = [
    ("Dosya", [("Ctrl + O", "Aç"), ("Ctrl + S", "Kaydet"), ("Ctrl + Shift + S", "Farklı kaydet"),
               ("Ctrl + P", "Yazdır"), ("Ctrl + W", "Belgeyi kapat")]),
    ("Düzenleme", [("Ctrl + Z", "Geri al"), ("Ctrl + Y", "Yinele"), ("Çift tık", "Yazıyı düzelt"),
                   ("Enter", "Düzeltmeyi uygula"), ("Esc", "Vazgeç / Seç moduna dön"),
                   ("Delete", "Seçili sayfayı / imzayı sil"), ("Yön tuşları", "Seçili imzayı kaydır")]),
    ("Gezinme", [("Page Up / Page Down", "Önceki / sonraki sayfa"), ("Fare tekerleği", "Aşağı / yukarı"),
                 ("Shift + tekerlek", "Sağa / sola"), ("Ctrl + tekerlek", "Yakınlaş / uzaklaş"),
                 ("Ctrl + +  /  Ctrl + -", "Yakınlaş / uzaklaş"), ("Ctrl + 0", "Genişliğe sığdır")]),
    ("Arama", [("Ctrl + F", "Belgede ara"), ("Ctrl + H", "Bul ve değiştir"), ("F3 / Shift + F3", "Sonraki / önceki sonuç")]),
    ("Fare", [("Sağ tık (belgede)", "Düzelt, kopyala, vurgula, not, sayfa işlemleri"),
              ("Sağ tık (araç düğmesi)", "Sık kullanılanlara sabitle"),
              ("Sürükle-bırak", "Dosyayı pencereye bırakınca açılır")]),
    ("Yardım", [("F1", "Bu liste")]),
]


def _A():
    from . import arayuz
    return arayuz


class KolaylikIslemleri:
    # ================================================================ arac kaydi / sayac
    def _arac_kaydi(self):
        """etiket -> (simge, etiket, komut, ipucu, mod)  (tum sekmeler + ? menusu)"""
        kayit = {}

        def ekle(oge):
            if not oge or callable(oge):
                return
            if isinstance(oge, tuple) and len(oge) >= 3:
                if isinstance(oge[2], (list, tuple)):
                    for alt in oge[2]:
                        ekle(alt)
                    return
                if oge[1] not in kayit:
                    kayit[oge[1]] = (oge + (None, None))[:5]
        for ad in self.MENULER:
            for grup in self._menu_icerigi(ad):
                if callable(grup):
                    continue
                for oge in grup:
                    ekle(oge)
        for oge in self.yardim_ogeleri():
            ekle(oge)
        return kayit

    def _sayarak(self, etiket, komut):
        def f():
            try:
                k = self.ayar.setdefault("kullanim", {})
                k[etiket] = k.get(etiket, 0) + 1
                if self._sik_degisir_mi(etiket):
                    self.after(400, self._sik_yenile)
            except Exception:
                pass
            return komut()
        return f

    # ================================================================ sik kullanilanlar
    def sik_liste(self):
        kayit = self._arac_kaydi()
        sabit = [e for e in self.ayar.get("sik_sabit", []) if e in kayit]
        gizli = set(self.ayar.get("sik_gizli", []))
        kullanim = self.ayar.get("kullanim", {})
        sonuc = list(sabit)
        for e, n in sorted(kullanim.items(), key=lambda x: -x[1]):
            if len(sonuc) >= SIK_ADET:
                break
            if n >= 2 and e in kayit and e not in sonuc and e not in gizli:
                sonuc.append(e)
        for e in VARSAYILAN_SIK:
            if len(sonuc) >= SIK_ADET:
                break
            if e in kayit and e not in sonuc and e not in gizli:
                sonuc.append(e)
        return [kayit[e] for e in sonuc[:SIK_ADET]]

    def _sik_degisir_mi(self, etiket):
        if etiket in getattr(self, "_sik_gosterilen", ()):
            return False
        n = self.ayar.get("kullanim", {}).get(etiket, 0)
        return n == 2 or (n > 2 and n % 5 == 0)

    def _sik_kullanilanlar_ciz(self, ust):
        A = _A()
        bg = getattr(self, "_arac_bg", A.R_ARAC)
        f = tk.Frame(ust, bg=bg)
        f.pack(side="left", fill="y", padx=(6, 0), pady=(3, 1))
        self._sik_cerceve = f
        self._sik_doldur()

    def _sik_yenile(self):
        try:
            if getattr(self, "_sik_cerceve", None) is not None and self._sik_cerceve.winfo_exists():
                self._sik_doldur()
        except tk.TclError:
            pass

    def _sik_doldur(self):
        A = _A()
        f = self._sik_cerceve
        for w in f.winfo_children():
            w.destroy()
        bg = f["bg"]
        tk.Label(f, text="★ Sık kullanılan", bg=bg, fg="#B45309", font=(A.FONT, 8, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=2)
        liste = self.sik_liste()
        self._sik_gosterilen = {o[1] for o in liste}
        K = TM.px(27)
        for n, (simge, etiket, komut, ipucu, mod) in enumerate(liste):
            renk = V.ARAC_RENK.get(etiket) or A.R_VURGU
            harf = etiket in V.HARF_SIMGE
            if harf:
                simge = V.HARF_SIMGE[etiket]
            cv = tk.Canvas(f, width=K, height=K, bg=bg, highlightthickness=0, cursor="hand2")
            cv.grid(row=1 + n // 3, column=n % 3, padx=2, pady=1)
            kare, _ = V.simge_ciz(cv, 2, 2, K - 4, renk, simge, harf, A.EMOJI_FONT, A.FONT)
            calis = self._sayarak(etiket, komut)
            cv.bind("<Button-1>", lambda e, c=calis: c())
            cv.bind("<Enter>", lambda e, c=cv, k=kare, r=renk: c.itemconfig(k, fill=V.koyu(r, 0.18)))
            cv.bind("<Leave>", lambda e, c=cv, k=kare, r=renk: c.itemconfig(k, fill=r))
            cv.bind("<Button-3>", lambda e, et=etiket: self.arac_sag_tik(e, et, sik=True))
            A.IpucuBalonu(cv, etiket + (f"\n{ipucu}" if ipucu else "") + "\n(Sağ tık: sabitle / kaldır)")

    def arac_sag_tik(self, e, etiket, sik=False):
        kayit = self._arac_kaydi()
        if etiket not in kayit:
            return
        A = _A()
        sabit = self.ayar.setdefault("sik_sabit", [])
        m = tk.Menu(self, tearoff=0, font=(A.FONT, 10))
        if etiket in sabit:
            m.add_command(label="☆  Sabitlemeyi kaldır", command=lambda: self._sik_sabitle(etiket, False))
        else:
            m.add_command(label="★  Sık kullanılanlara sabitle", command=lambda: self._sik_sabitle(etiket, True))
        if sik and etiket not in sabit:
            m.add_command(label="✕  Bu listeden çıkar", command=lambda: self._sik_gizle(etiket))
        m.tk_popup(e.x_root, e.y_root)

    def _sik_sabitle(self, etiket, sabitle):
        sabit = self.ayar.setdefault("sik_sabit", [])
        gizli = self.ayar.setdefault("sik_gizli", [])
        if sabitle:
            if etiket not in sabit:
                sabit.insert(0, etiket)
                del sabit[SIK_ADET:]
            if etiket in gizli:
                gizli.remove(etiket)
            self.durum_yaz(f"★ '{etiket}' sık kullanılanlara sabitlendi.", basari=True)
        elif etiket in sabit:
            sabit.remove(etiket)
            self.durum_yaz(f"'{etiket}' sabitlemesi kaldırıldı.")
        self._sik_yenile()

    def _sik_gizle(self, etiket):
        gizli = self.ayar.setdefault("sik_gizli", [])
        if etiket not in gizli:
            gizli.append(etiket)
        self.ayar.setdefault("kullanim", {}).pop(etiket, None)
        self._sik_yenile()

    # ================================================================ acilir arac menusu
    def acilir_arac_menusu(self, w, liste):
        A = _A()
        m = tk.Menu(self, tearoff=0, font=(A.FONT, 10))
        for oge in liste:
            if oge is None:
                m.add_separator()
                continue
            simge, etiket, komut = oge[:3]
            mod = oge[4] if len(oge) > 4 else None
            isaret = "✓ " if mod and getattr(self, "mod", None) == mod else ""
            m.add_command(label=f"{simge}   {isaret}{etiket}", command=self._sayarak(etiket, komut))
        try:
            m.tk_popup(w.winfo_rootx(), w.winfo_rooty() + w.winfo_height())
        finally:
            m.grab_release()

    # ================================================================ sag ust: tema + yardim
    def _sag_menu_dugmeleri(self, m):
        A = _A()

        def dugme(metin, komut, ipucu):
            b = tk.Label(m, text=metin, bg=A.R_MENU, fg=A.R_MENU_YAZI, font=(A.FONT, 11, "bold"), padx=10,
                         cursor="hand2")
            b.pack(side="right", fill="y")
            b.bind("<Button-1>", lambda e: komut(b))
            b.bind("<Enter>", lambda e: b.config(bg="#E5E7EB"))
            b.bind("<Leave>", lambda e: b.config(bg=A.R_MENU))
            A.IpucuBalonu(b, ipucu)
            return b
        self._yardim_dugme = dugme("?", lambda b: self.acilir_arac_menusu(b, self.yardim_ogeleri()),
                                   "Yardım: kılavuz, klavye kısayolları (F1), tanıtım turu, görünüm, yönetici")
        self._tema_dugme = dugme("☀" if TM.KOYU else "🌙", lambda b: self.tema_degistir(),
                                 "Açık tema" if TM.KOYU else "Koyu tema (gece modu)")

    # ================================================================ gorunum ayarlari
    def tema_degistir(self):
        yeni = "acik" if TM.KOYU else "koyu"
        self._gorunum_uygula(yeni, self.ayar.get("arayuz_olcek", 1.0))

    def _gorunum_uygula(self, tema, olcek):
        eski = (self.ayar.get("tema", "acik"), float(self.ayar.get("arayuz_olcek", 1.0)))
        self.ayar["tema"] = tema
        self.ayar["arayuz_olcek"] = olcek
        if (tema, float(olcek)) == eski:
            return
        try:
            _A().ayar_yaz(self.ayar)
        except Exception:
            pass
        if messagebox.askyesno("PDF PRO", "Görünüm değişikliği PDF PRO yeniden başlatılınca uygulanır.\n\n"
                                          "Şimdi yeniden başlatılsın mı?\n(Açık belgeler yeniden açılır; "
                                          "kaydedilmemiş değişiklik varsa önce sorulur.)"):
            self.ayar["yeniden_ac"] = [b.yol for b in self.belgeler if b.yol]
            self.yeniden_baslat()

    def gorunum_ayarlari(self):
        A = _A()
        p = tk.Toplevel(self)
        p.title("Görünüm")
        p.configure(bg=A.R_KART)
        p.transient(self)
        p.resizable(False, False)
        bant = tk.Frame(p, bg="#4F46E5")
        bant.pack(fill="x")
        tk.Label(bant, text="🎨  Görünüm", bg="#4F46E5", fg="white", font=(A.FONT, 13, "bold")).pack(
            anchor="w", padx=16, pady=9)
        g = tk.Frame(p, bg=A.R_KART)
        g.pack(fill="both", padx=18, pady=12)
        tema = tk.StringVar(value=self.ayar.get("tema", "acik"))
        olcek = tk.DoubleVar(value=float(self.ayar.get("arayuz_olcek", 1.0)))
        tk.Label(g, text="Tema", bg=A.R_KART, fg=A.R_YAZI, font=(A.FONT, 10, "bold")).pack(anchor="w")
        t = tk.Frame(g, bg=A.R_KART)
        t.pack(anchor="w", pady=(4, 12))
        for ad, deger, zemin, yazi, cizgi in (("Açık", "acik", "#FFFFFF", "#111827", "#D1D5DB"),
                                              ("Koyu", "koyu", "#1A1C22", "#E5E7EB", "#3A3F4B")):
            k = tk.Frame(t, bg=A.R_KART)
            k.pack(side="left", padx=(0, 14))
            on = tk.Canvas(k, width=TM.px(120), height=TM.px(74), highlightthickness=0, bg=A.R_KART, cursor="hand2")
            on.pack()
            # onizleme kendi renkleriyle kalsin (tema cevirmesin)
            on.create_rectangle(1, 1, TM.px(119), TM.px(73), fill=TM.KAGIT if deger == "acik" else zemin,
                                outline="#9CA3AF")
            on.create_rectangle(1, 1, TM.px(119), TM.px(16), fill=TM.KAGIT if deger == "acik" else "#22252D",
                                outline="")
            for i, r in enumerate(("#2563EB", "#DC2626", "#16A34A", "#EA580C")):
                x = TM.px(8) + i * TM.px(26)
                on.create_rectangle(x, TM.px(24), x + TM.px(20), TM.px(44), fill=r, outline="")
            on.create_rectangle(TM.px(40), TM.px(50), TM.px(80), TM.px(70), fill=TM.KAGIT, outline=cizgi)
            on.bind("<Button-1>", lambda e, d=deger: tema.set(d))
            tk.Radiobutton(k, text=ad, value=deger, variable=tema, bg=A.R_KART, fg=A.R_YAZI, activebackground=A.R_KART,
                           selectcolor=A.R_KART, highlightthickness=0, font=(A.FONT, 10)).pack()
        tk.Label(g, text="Yazı ve simge büyüklüğü", bg=A.R_KART, fg=A.R_YAZI, font=(A.FONT, 10, "bold")).pack(anchor="w")
        b = tk.Frame(g, bg=A.R_KART)
        b.pack(anchor="w", pady=(4, 6))
        for ad, deger in TM.BUYUKLUKLER:
            tk.Radiobutton(b, text=ad, value=deger, variable=olcek, bg=A.R_KART, fg=A.R_YAZI,
                           activebackground=A.R_KART, selectcolor=A.R_KART, highlightthickness=0,
                           font=(A.FONT, int(10 * deger))).pack(side="left", padx=(0, 12))
        tk.Label(g, text="Değişiklik PDF PRO yeniden başlatılınca uygulanır.", bg=A.R_KART, fg=A.R_SOLUK,
                 font=(A.FONT, 8)).pack(anchor="w", pady=(6, 0))
        alt = tk.Frame(p, bg=A.R_KART)
        alt.pack(fill="x", padx=18, pady=(0, 14))

        def uygula():
            p.destroy()
            self._gorunum_uygula(tema.get(), olcek.get())
        ttk.Button(alt, text="Uygula", style="Ana.TButton", command=uygula).pack(side="right")
        ttk.Button(alt, text="Vazgeç", style="Ikincil.TButton", command=p.destroy).pack(side="right", padx=6)
        p.bind("<Escape>", lambda e: p.destroy())
        self._ortala(p)

    def _ortala(self, p):
        p.update_idletasks()
        try:
            x = self.winfo_rootx() + (self.winfo_width() - p.winfo_width()) // 2
            y = self.winfo_rooty() + (self.winfo_height() - p.winfo_height()) // 3
            p.geometry(f"+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            pass

    # ================================================================ klavye kisayollari (F1)
    def kisayol_listesi(self):
        A = _A()
        if getattr(self, "_kisayol_pen", None) is not None:
            try:
                self._kisayol_pen.lift()
                self._kisayol_pen.focus_force()
                return
            except tk.TclError:
                pass
        p = tk.Toplevel(self)
        self._kisayol_pen = p
        p.bind("<Destroy>", lambda e: setattr(self, "_kisayol_pen", None) if e.widget is p else None)
        p.title("Klavye Kısayolları")
        p.configure(bg=A.R_KART)
        p.transient(self)
        bant = tk.Frame(p, bg="#2563EB")
        bant.pack(fill="x")
        tk.Label(bant, text="⌨  Klavye Kısayolları", bg="#2563EB", fg="white", font=(A.FONT, 13, "bold")).pack(
            side="left", padx=16, pady=9)
        g = tk.Frame(p, bg=A.R_KART)
        g.pack(fill="both", expand=True, padx=16, pady=10)
        sutunlar = [tk.Frame(g, bg=A.R_KART), tk.Frame(g, bg=A.R_KART)]
        sutunlar[0].pack(side="left", fill="y", anchor="n", padx=(0, 24))
        sutunlar[1].pack(side="left", fill="y", anchor="n")
        for n, (grup, liste) in enumerate(KISAYOLLAR):
            s = sutunlar[0 if n in (0, 1, 5) else 1]
            tk.Label(s, text=grup, bg=A.R_KART, fg="#2563EB", font=(A.FONT, 10, "bold")).pack(anchor="w", pady=(8, 3))
            for tus, ne in liste:
                r = tk.Frame(s, bg=A.R_KART)
                r.pack(fill="x", pady=1)
                tk.Label(r, text=tus, bg="#F3F4F6", fg="#111827", font=(A.FONT, 9, "bold"), padx=6, pady=1,
                         width=20, anchor="w").pack(side="left")
                tk.Label(r, text=ne, bg=A.R_KART, fg=A.R_YAZI, font=(A.FONT, 9), padx=8).pack(side="left")
        alt = tk.Frame(p, bg=A.R_KART)
        alt.pack(fill="x", padx=16, pady=(0, 12))
        ttk.Button(alt, text="Kapat", style="Ana.TButton", command=p.destroy).pack(side="right")
        ttk.Button(alt, text="Kılavuzu Aç", style="Ikincil.TButton",
                   command=lambda: (p.destroy(), self.kilavuz())).pack(side="right", padx=6)
        ttk.Button(alt, text="Tanıtım Turu", style="Ikincil.TButton",
                   command=lambda: (p.destroy(), self.tur_baslat(True))).pack(side="left")
        p.bind("<Escape>", lambda e: p.destroy())
        p.bind("<F1>", lambda e: p.destroy())
        self._ortala(p)

    # ================================================================ tanitim turu
    def tur_gerekirse(self):
        if not self.ayar.get("tur_goruldu"):
            self.tur_baslat()

    def _tur_adimlari(self):
        ilk_sekme = next(iter(self._menu_etiketleri.values()), None)
        return [
            (lambda: ilk_sekme.master if ilk_sekme else None, "Sekmeler sadeleşti",
             "Araçlar 7 sekmede: Ana Sayfa, Düzenle, Sayfalar, İşaretle & İmza, Dönüştür, Araçlar, Yapay Zeka.\n"
             "Aradığınızı bulamazsanız soldaki ⌂ Tüm Araçlar'a bakın: her şey kartlar halinde orada."),
            (lambda: getattr(self, "_sik_cerceve", None), "★ Sık kullanılanlar",
             "En çok kullandığınız araçlar her sekmede burada durur; program kullandıkça öğrenir.\n"
             "Herhangi bir araç düğmesine SAĞ TIKLAYIP sabitleyebilirsiniz."),
            (lambda: self._arac_cubugu, "▾ işaretli düğmeler",
             "Az kullanılan araçlar 'Diğer ▾', 'Şekiller ▾' gibi düğmelerin içinde.\nTıklayınca liste açılır."),
            (lambda: self.sag, "Belgede sağ tık",
             "Yazıya sağ tıklayın: Düzelt, Kopyala, Vurgula, Karart.\nBoş yere sağ tık: yazı / not / imza ekle, "
             "sayfayı döndür veya sil.\nCtrl + tekerlek yakınlaştırır; dosyaları pencereye sürükleyip bırakabilirsiniz."),
            (lambda: getattr(self, "_yardim_dugme", None), "Yardım ve görünüm",
             "? menüsünde: klavye kısayolları (F1), kılavuz, bu tur.\n🌙 düğmesi koyu temayı açar; "
             "yazı büyüklüğü 'Görünüm'de."),
        ]

    def tur_baslat(self, elle=False):
        self._tur_bitir()
        self._tur = {"adim": 0, "liste": self._tur_adimlari(), "pen": None, "vurgu": None}
        self._tur_goster()

    def _tur_bitir(self, tamamlandi=False):
        t = getattr(self, "_tur", None)
        if not t:
            return
        self._tur_vurgu_kaldir()
        if t.get("pen") is not None:
            try:
                t["pen"].destroy()
            except tk.TclError:
                pass
        self._tur = None
        self.ayar["tur_goruldu"] = True

    def _tur_vurgu_kaldir(self):
        t = getattr(self, "_tur", None)
        if t and t.get("vurgu"):
            for w in t["vurgu"]:
                try:
                    w.destroy()
                except tk.TclError:
                    pass
            t["vurgu"] = None

    def _tur_goster(self):
        A = _A()
        t = self._tur
        if not t:
            return
        if t["adim"] >= len(t["liste"]):
            self._tur_bitir(True)
            self.durum_yaz("Tanıtım bitti. Tekrar görmek için: ? → Tanıtım Turu", basari=True)
            return
        if t.get("pen") is not None:
            try:
                t["pen"].destroy()
            except tk.TclError:
                pass
        self._tur_vurgu_kaldir()
        hedef_al, baslik, metin = t["liste"][t["adim"]]
        hedef = None
        try:
            hedef = hedef_al()
            if hedef is not None and not hedef.winfo_ismapped():
                hedef = None
        except tk.TclError:
            hedef = None
        self.update_idletasks()
        # hedefin etrafina turuncu cerceve (4 ince pencere)
        if hedef is not None:
            x, y = hedef.winfo_rootx(), hedef.winfo_rooty()
            w, h = hedef.winfo_width(), hedef.winfo_height()
            parcalar = []
            for gx, gy, gw, gh in ((x - 3, y - 3, w + 6, 3), (x - 3, y + h, w + 6, 3),
                                   (x - 3, y - 3, 3, h + 6), (x + w, y - 3, 3, h + 6)):
                c = tk.Toplevel(self)
                c.overrideredirect(True)
                c.configure(bg="#F97316")
                c.geometry(f"{max(1, gw)}x{max(1, gh)}+{gx}+{gy}")
                try:
                    c.attributes("-topmost", True)
                except tk.TclError:
                    pass
                parcalar.append(c)
            t["vurgu"] = parcalar
        p = tk.Toplevel(self)
        t["pen"] = p
        p.overrideredirect(True)
        try:
            p.attributes("-topmost", True)
        except tk.TclError:
            pass
        KOYU_ZEMIN = "#1F2937"
        p.configure(bg=KOYU_ZEMIN, highlightthickness=2, highlightbackground="#F97316")
        ic = tk.Frame(p, bg=KOYU_ZEMIN)
        ic.pack(padx=16, pady=12)
        tk.Label(ic, text=f"{t['adim'] + 1} / {len(t['liste'])}", bg=KOYU_ZEMIN, fg="#FDBA74",
                 font=(A.FONT, 8, "bold")).pack(anchor="w")
        tk.Label(ic, text=baslik, bg=KOYU_ZEMIN, fg="white", font=(A.FONT, 12, "bold")).pack(anchor="w", pady=(2, 4))
        tk.Label(ic, text=metin, bg=KOYU_ZEMIN, fg="#E5E7EB", font=(A.FONT, 10), justify="left",
                 wraplength=TM.px(380)).pack(anchor="w")
        d = tk.Frame(ic, bg=KOYU_ZEMIN)
        d.pack(fill="x", pady=(10, 0))

        def dugme(metin_, komut, ana=False):
            b = tk.Label(d, text=metin_, bg="#F97316" if ana else KOYU_ZEMIN, fg="white", font=(A.FONT, 9, "bold"),
                         padx=12, pady=4, cursor="hand2")
            b.pack(side="right", padx=(6, 0))
            b.bind("<Button-1>", lambda e: komut())
            return b
        son = t["adim"] == len(t["liste"]) - 1
        dugme("Bitir ✓" if son else "İleri →", self._tur_ileri, ana=True)
        if t["adim"]:
            dugme("← Geri", self._tur_geri)
        atla = tk.Label(d, text="Turu atla", bg=KOYU_ZEMIN, fg="#9CA3AF", font=(A.FONT, 9), cursor="hand2")
        atla.pack(side="left")
        atla.bind("<Button-1>", lambda e: self._tur_bitir())
        p.bind("<Escape>", lambda e: self._tur_bitir())
        p.update_idletasks()
        pw, ph = p.winfo_reqwidth(), p.winfo_reqheight()
        ew, eh = self.winfo_screenwidth(), self.winfo_screenheight()
        if hedef is not None:
            x = hedef.winfo_rootx() + min(40, hedef.winfo_width() // 3)
            y = hedef.winfo_rooty() + hedef.winfo_height() + 10
            if y + ph > eh - 40:
                y = max(0, hedef.winfo_rooty() + hedef.winfo_height() // 2 - ph // 2)
                x = hedef.winfo_rootx() + hedef.winfo_width() // 2 - pw // 2
        else:
            x = self.winfo_rootx() + (self.winfo_width() - pw) // 2
            y = self.winfo_rooty() + (self.winfo_height() - ph) // 2
        x = max(0, min(x, ew - pw - 10))
        p.geometry(f"+{x}+{max(0, y)}")
        p.focus_force()

    def _tur_ileri(self):
        if getattr(self, "_tur", None):
            self._tur["adim"] += 1
            self._tur_goster()

    def _tur_geri(self):
        if getattr(self, "_tur", None) and self._tur["adim"]:
            self._tur["adim"] -= 1
            self._tur_goster()

    # ================================================================ belgede sag tik
    def belge_sag_tik(self, e, n):
        """n = (sayfa, pdf_x, pdf_y)"""
        A = _A()
        from . import duzenle as Z
        b = self.belge
        if not b:
            return
        i, px, py = n
        g = self.gorunum
        if g._duzenleyici:
            g._duzenleyici_kapat(uygula=True)
        m = tk.Menu(self, tearoff=0, font=(A.FONT, 10))
        # imza / kase
        v = g._nesne_vurusu(e) if b.nesneler else None
        if v:
            nid = v[1]
            g.nesne_sec(nid)
            m.add_command(label="🗑   İmza / kaşeyi sil", command=lambda: self.nesne_sil(nid))
            m.add_command(label="✥   Taşı / boyutlandır (sürükleyin)", command=lambda: self.mod_sec("sec"))
            m.add_separator()
        satir = None
        try:
            if b.doc[i].rotation == 0:
                satir = Z.satir_bul(b.doc[i], px, py, veri=g._metin_verisi(i))
        except Exception:
            satir = None
        if satir and not satir.get("gorunmez"):
            kisa = satir["metin"].strip().replace("\n", " ")
            kisa = kisa if len(kisa) <= 40 else kisa[:37] + "…"
            m.add_command(label=f"“{kisa}”", state="disabled")
            m.add_command(label="✏   Bu yazıyı düzelt", command=lambda: self._sag_duzelt(i, px, py))
            m.add_command(label="📋   Yazıyı kopyala", command=lambda: self._panoya(satir["metin"]))
            rect = A.fitz.Rect(satir["bbox"])
            m.add_command(label="🖍   Vurgula", command=lambda: self.alan_secildi("vurgula", i, rect, (px, py), (px, py)))
            m.add_command(label="⬜   Beyaz kutuyla sil", command=lambda: self.alan_secildi("beyaz_kutu", i, rect, (px, py), (px, py)))
            m.add_command(label="⬛   Karart (kalıcı gizle)", command=lambda: self.alan_secildi("karart", i, rect, (px, py), (px, py)))
            m.add_separator()
        elif satir is not None or self._sayfada_resim_var(i):
            m.add_command(label="🔎   Resimdeki yazıyı oku / düzelt", command=lambda: self._sag_duzelt(i, px, py))
            m.add_separator()
        m.add_command(label="🔤   Buraya yazı ekle", command=lambda: self._sag_yazi_ekle(i, px, py))
        m.add_command(label="💬   Buraya not ekle", command=lambda: self.not_bas(i, px, py))
        m.add_command(label="✍   İmza / kaşe koy…", command=self.imza_baslat)
        m.add_command(label="📋   Sayfanın tüm yazısını kopyala",
                      command=lambda: self._panoya(b.doc[i].get_text()))
        m.add_separator()
        s = tk.Menu(m, tearoff=0, font=(A.FONT, 10))

        def sayfa(f):
            def calis():
                b.secili = {i}
                b.aktif = i
                f()
            return calis
        s.add_command(label="⟲   Sola döndür", command=sayfa(lambda: self.dondur(-90)))
        s.add_command(label="⟳   Sağa döndür", command=sayfa(lambda: self.dondur(90)))
        s.add_command(label="📄   Sonrasına boş sayfa", command=sayfa(self.bos_sayfa))
        s.add_command(label="📤   Yeni belge olarak ayır", command=sayfa(self.sayfalari_ayir))
        s.add_separator()
        s.add_command(label="🗑   Sayfayı sil", command=sayfa(self.sayfa_sil))
        m.add_cascade(label=f"📄   Sayfa {i + 1}", menu=s)
        m.add_separator()
        m.add_command(label="🔍   Ara…   (Ctrl+F)", command=self.arama_ac)
        m.add_command(label="🖨   Yazdır…   (Ctrl+P)", command=self.yazdir)
        m.add_command(label="↔   Genişliğe sığdır", command=lambda: g.zoom_ayarla("genislik"))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _sayfada_resim_var(self, i):
        try:
            return bool(self.belge.doc[i].get_images())
        except Exception:
            return False

    def _sag_duzelt(self, i, px, py):
        self.mod_sec("yazi_duzelt")
        self.gorunum._yazi_duzelt_baslat(i, px, py)

    def _sag_yazi_ekle(self, i, px, py):
        self.mod_sec("yazi_ekle")
        self.gorunum._yazi_ekle_baslat(i, px, py)

    def _panoya(self, metin):
        self.clipboard_clear()
        self.clipboard_append(metin or "")
        self.durum_yaz("Panoya kopyalandı.", basari=True)

    # ================================================================ son dosyalar (resimli)
    def _son_dosyalar_ciz(self):
        A = _A()
        f = self._son_cerceve
        for w in f.winfo_children():
            w.destroy()
        son = [y for y in self.ayar.get("son_dosyalar", []) if os.path.isfile(y)][:6]
        if not son:
            return
        Z_ = f["bg"]
        tk.Label(f, text="Son açılanlar", bg=Z_, fg=A.R_SOLUK, font=(A.FONT, 9, "bold")).pack(anchor="w", padx=4)
        satir = tk.Frame(f, bg=Z_)
        satir.pack()
        self._son_resimler = {}
        GW, GH = TM.px(72), TM.px(96)
        for y in son:
            kart = tk.Frame(satir, bg="white", highlightthickness=1, highlightbackground="#E1E5EE", cursor="hand2")
            kart.pack(side="left", padx=5, pady=4)
            cv = tk.Canvas(kart, width=GW + 8, height=GH + 8, bg="white", highlightthickness=0, cursor="hand2")
            cv.pack(padx=8, pady=(8, 2))
            cv.create_rectangle(4, 4, GW + 4, GH + 4, fill="#F3F4F6", outline="#E5E7EB", tags="yer")
            uz = os.path.splitext(y)[1].lower().lstrip(".")[:4].upper() or "?"
            cv.create_text(GW / 2 + 4, GH / 2 + 4, text=uz, fill="#9CA3AF", font=(A.FONT, 10, "bold"), tags="yer")
            ad = os.path.basename(y)
            ad_k = ad if len(ad) <= 18 else ad[:16] + "…"
            et = tk.Label(kart, text=ad_k, bg="white", fg="#26303F", font=(A.FONT, 8, "bold"), cursor="hand2")
            et.pack(padx=6)
            kl = os.path.basename(os.path.dirname(y)) or y[:3]
            kl = kl if len(kl) <= 20 else kl[:18] + "…"
            k2 = tk.Label(kart, text="📁 " + kl, bg="white", fg="#9CA3AF", font=(A.FONT, 7), cursor="hand2")
            k2.pack(padx=6, pady=(0, 6))
            x = tk.Label(kart, text="✕", bg="white", fg="#9CA3AF", font=(A.FONT, 8), cursor="hand2")
            parcalar = (kart, cv, et, k2)

            def gir(e, k=kart, xx=x, e_=et):
                k.config(highlightbackground="#E5322D")
                e_.config(fg="#E5322D")
                xx.place(relx=1, x=-2, y=1, anchor="ne")

            def cik(e, k=kart, xx=x, e_=et):
                w = k.winfo_containing(e.x_root, e.y_root)
                if w is not None and str(w).startswith(str(k)):
                    return
                k.config(highlightbackground="#E1E5EE")
                e_.config(fg="#26303F")
                xx.place_forget()
            for w in parcalar:
                w.bind("<Button-1>", lambda ev, yy=y: self.ac([yy]))
                w.bind("<Enter>", gir)
                w.bind("<Leave>", cik)
            x.bind("<Button-1>", lambda ev, yy=y: self._son_cikar(yy))
            A.IpucuBalonu(cv, y)
            self._son_resim_yukle(y, cv, GW, GH)

    def _son_cikar(self, yol):
        liste = self.ayar.get("son_dosyalar", [])
        if yol in liste:
            liste.remove(yol)
        self._son_dosyalar_ciz()

    def _son_resim_yukle(self, yol, cv, gw, gh):
        try:
            anahtar = hashlib.md5(f"{yol}|{os.path.getmtime(yol)}|{gw}".encode("utf-8")).hexdigest()
        except OSError:
            return
        klasor = os.path.join(tempfile.gettempdir(), "pdfpro_son")
        dosya = os.path.join(klasor, anahtar + ".png")

        def goster(png):
            try:
                if not cv.winfo_exists():
                    return
                img = tk.PhotoImage(master=cv, data=base64.b64encode(png).decode())
                self._son_resimler[yol] = img
                cv.delete("yer")
                w, h = img.width(), img.height()
                x, y = 4 + (gw - w) // 2, 4 + (gh - h) // 2
                cv.create_rectangle(x + 2, y + 2, x + w + 2, y + h + 2, fill="#D1D5DB", outline="")
                cv.create_image(x, y, image=img, anchor="nw")
                cv.create_rectangle(x, y, x + w, y + h, outline="#D1D5DB")
            except tk.TclError:
                pass

        if os.path.isfile(dosya):
            try:
                with open(dosya, "rb") as f:
                    goster(f.read())
                return
            except OSError:
                pass

        def is_():
            try:
                from .cekirdek import fitz
                with fitz.open(yol) as d:
                    if d.needs_pass or not d.page_count:
                        return
                    s = d[0]
                    olcek = min(gw / s.rect.width, gh / s.rect.height)
                    pix = s.get_pixmap(matrix=fitz.Matrix(olcek, olcek), alpha=False)
                    png = pix.tobytes("png")
                try:
                    os.makedirs(klasor, exist_ok=True)
                    with open(dosya, "wb") as f:
                        f.write(png)
                except OSError:
                    pass
                self.after(0, lambda: goster(png))
            except Exception:
                pass
        threading.Thread(target=is_, daemon=True).start()
