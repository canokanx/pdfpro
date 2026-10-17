# -*- coding: utf-8 -*-
"""
PDF PRO - Arac renkleri ve "Tum Araclar" vitrini (iLovePDF tarzi kart izgarasi)
Her aracin kendi rengi vardir; ayni renk hem ust araç cubugunda hem vitrinde kullanilir.
"""
import tkinter as tk

# ---- arac renkleri (kategoriye gore)
KIRMIZI = "#E5322D"     # sayfa duzeni: birlestir, bol, sil
YESIL = "#5BA33B"       # optimize: sikistir, OCR, onar
WORD = "#2B579A"
EXCEL = "#1D7044"
PPT = "#D24726"
SARI = "#E6A700"        # resim / JPG / HTML
MOR = "#A2459A"         # duzenle: yazi, filigran, kirp, form
MAVI = "#2F6FDE"        # imza, guvenlik, karsilastir
LACI = "#3B4A9E"
MENEKSE = "#6D3FE8"     # yapay zeka
TURKUAZ = "#0E9AA7"     # otomasyon
PEMBE = "#E8508A"
GRI = "#5B6577"
TURUNCU = "#F07B1C"

ARAC_RENK = {
    # Dosya
    "Tüm Araçlar": KIRMIZI, "Aç": MAVI, "Kaydet": LACI, "Farklı Kaydet": LACI, "Kapat": GRI, "Tara": TURKUAZ, "Yazdır": GRI,
    "E-posta": MAVI, "Yedekler": TURUNCU, "Klasörde Göster": SARI,
    # Giris
    "Geri Al": GRI, "Yinele": GRI, "Seç": LACI, "Yazı Düzelt": MOR, "Resimde Yazı": PEMBE, "Yazı Ekle": MOR,
    "Beyaz Kutu": GRI, "Ara": MAVI, "Bul-Değiştir": MAVI, "Yakınlaş": TURKUAZ, "Uzaklaş": TURKUAZ,
    "Genişlik": TURKUAZ, "Sayfa": TURKUAZ,
    # Sayfa
    "Sola Döndür": MOR, "Sağa Döndür": MOR, "Sil": KIRMIZI, "Boş Sayfa": KIRMIZI, "Dosyadan Ekle": KIRMIZI,
    "Ayır": KIRMIZI, "Ters Çevir": KIRMIZI, "Birleştir": KIRMIZI, "Böl": KIRMIZI, "Kırp": MOR,
    "A4'e Sığdır": YESIL, "Sayfa No": MAVI,
    # Isaretle
    "Vurgula": SARI, "Not": SARI, "Metin Kutusu": SARI, "Dikdörtgen": PEMBE, "Elips": PEMBE, "Çizgi": PEMBE,
    "Ok": PEMBE, "Karart": "#26303F",
    # Imza
    "İmza / Kaşe": MAVI, "İmza Setleri": MAVI, "Seti Koy": MAVI, "Damga": KIRMIZI, "Antet": LACI, "Filigran": MOR,
    # Form
    "Form Doldur": MOR, "Otomatik Algıla": MENEKSE, "Metin Alanı": MOR, "Onay Kutusu": MOR,
    "Açılır Liste": MOR, "Formu Kilitle": LACI,
    # Donustur
    "Word": WORD, "Excel": EXCEL, "PowerPoint": PPT, "Resim": SARI, "Metin": GRI, "Markdown": MENEKSE,
    "PDF/A": LACI, "Resimden": SARI, "Word'den": WORD, "Excel'den": EXCEL, "PPT'den": PPT, "HTML'den": SARI,
    # Araclar
    "Sıkıştır": YESIL, "OCR": YESIL, "Metni Çıkar": YESIL, "Karşılaştır": MAVI, "QR / Barkod": GRI,
    "Onar": YESIL, "Resimleri Çıkar": SARI,
    # Koruma
    "Şifre Koy": MAVI, "Şifreyi Kaldır": MAVI, "Bilgileri Temizle": GRI,
    # Yapay zeka / otomasyon / yardim
    "Özetle": MENEKSE, "Belgeye Sor": MENEKSE, "Çevir": MENEKSE, "Ayarlar": GRI,
    "Belge Paketi": TURKUAZ, "İş Akışları": PEMBE, "Windows'a Tanıt": MAVI, "Yönetici": LACI, "Kılavuz": MAVI, "Hakkında": GRI, "Hata Kaydı": KIRMIZI,
}

# Office'teki gibi harfli simgeler (emoji yerine)
HARF_SIMGE = {"Word": "W", "Word'den": "W", "Excel": "X", "Excel'den": "X", "PowerPoint": "P", "PPT'den": "P",
              "Markdown": "M↓", "PDF/A": "A", "HTML'den": "</>", "Sayfa No": "1 2", "OCR": "OCR"}


def koyu(renk, oran=0.22):
    r, g, b = (int(renk[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(c * (1 - oran)) for c in (r, g, b))


def acik(renk, oran=0.88):
    r, g, b = (int(renk[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(c + (255 - c) * oran) for c in (r, g, b))


def simge_ciz(cv, x, y, boy, renk, simge, harf=False, emoji_font="Segoe UI Emoji", font="Segoe UI"):
    """Yuvarlak koseli renkli kare + beyaz simge. Dondurur: (kare_id, yazi_id)"""
    r = boy * 0.24
    x0, y0, x1, y1 = x, y, x + boy, y + boy
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
           x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    kare = cv.create_polygon(pts, smooth=True, fill=renk, outline="")
    if harf:
        n = len(simge)
        fb = int(boy * (0.5 if n == 1 else 0.36 if n == 2 else 0.27))
        yazi = cv.create_text(x + boy / 2, y + boy / 2, text=simge, fill="white", font=(font, fb, "bold"))
    else:
        yazi = cv.create_text(x + boy / 2, y + boy / 2 + 1, text=simge, fill="white", font=(emoji_font, int(boy * 0.4)))
    return kare, yazi


# ---- vitrin kartlari: (kategori, simge, baslik, aciklama, metod / callable(app), renk, yeni_mi)
KATEGORILER = ["Tümü", "Düzenle", "Optimize", "Dönüştür", "İmza & Güvenlik", "Yapay Zeka", "Otomasyon"]


def kartlar(u):
    m = u.mod_sec
    return [
        ("Düzenle", "🗂", "PDF Birleştir", "Birden çok PDF ve resmi istediğiniz sırayla tek dosyada birleştirin.", u.birlestir, KIRMIZI, False, False),
        ("Düzenle", "✂", "PDF Böl", "Sayfaları ayrı dosyalara ya da istediğiniz aralıklara bölün.", u.bol, KIRMIZI, False, True),
        ("Düzenle", "🔃", "Sayfaları Düzenle", "Sayfaları sürükleyerek sıralayın, silin, döndürün, araya sayfa ekleyin.", lambda: u.menu_sec("Sayfa"), KIRMIZI, False, True),
        ("Düzenle", "✏", "PDF Düzenle", "PDF'teki ya da taranmış resimdeki yazıya tıklayın, aynı yazı tipiyle değiştirin.", lambda: m("yazi_duzelt"), MOR, False, True),
        ("Düzenle", "🔤", "Yazı Ekle", "Sayfanın istediğiniz yerine yazı yazın; yazı tipi, boyut ve renk seçin.", lambda: m("yazi_ekle"), MOR, False, True),
        ("Düzenle", "⟳", "PDF Döndür", "Seçili ya da tüm sayfaları sağa / sola döndürün.", lambda: u.dondur(90), MOR, False, True),
        ("Düzenle", "✂", "PDF Kırp", "Sayfanın kenar boşluklarını kesin; tek sayfaya ya da tümüne uygulayın.", lambda: m("kirp"), MOR, False, True),
        ("Düzenle", "💧", "Filigran", "GİZLİDİR, TASLAK gibi yazı ya da logo filigranı ekleyin.", u.filigran, MOR, False, True),
        ("Düzenle", "1 2", "Sayfa Numaraları", "Sayfa 1 / 5 gibi numaraları istediğiniz konuma ekleyin.", u.sayfa_no, MAVI, False, True),
        ("Düzenle", "💬", "Not ve Metin Kutusu", "Vurgulayın, not ekleyin, ok ve şekil çizin.", lambda: u.menu_sec("İşaretle"), SARI, False, True),
        ("Optimize", "🗜", "PDF Sıkıştır", "Dosya boyutunu küçültün; hedef MB yazın, kalite korunsun.", u.sikistir, YESIL, False, True),
        ("Optimize", "OCR", "OCR PDF", "Taranmış belgeleri aranabilir ve kopyalanabilir yapın (Türkçe + İngilizce).", u.ocr_aranabilir, YESIL, False, True),
        ("Optimize", "🔧", "PDF Onar", "Bozuk ya da yarım inmiş PDF'ten kurtarılabilen sayfaları çıkarın.", u.onar, YESIL, False, False),
        ("Optimize", "📐", "A4'e Sığdır", "Farklı boyuttaki taramaları tek tip A4 sayfaya getirin.", u.a4e_sigdir, YESIL, False, True),
        ("Dönüştür", "W", "PDF'den Word'e", "PDF'i düzenlenebilir Word (.docx) dosyasına çevirin.", u.word_e, WORD, False, True),
        ("Dönüştür", "P", "PDF'den PowerPoint'e", "Her sayfa bir slayt; yazılar düzenlenebilir kutu olur.", u.pptx_e, PPT, False, True),
        ("Dönüştür", "X", "PDF'den Excel'e", "PDF'teki tabloları doğrudan Excel'e aktarın.", u.excel_e, EXCEL, False, True),
        ("Dönüştür", "🖼", "PDF'den JPG'ye", "Sayfaları JPG / PNG resim olarak kaydedin.", u.resme, SARI, False, True),
        ("Dönüştür", "M↓", "PDF'den Markdown'a", "Başlık, liste ve tabloları koruyarak Markdown'a çevirin.", u.markdown_e, MENEKSE, True, True),
        ("Dönüştür", "A", "PDF'den PDF/A'ya", "Resmi arşiv için uzun süreli saklama biçimine çevirin.", u.pdfa_yap, LACI, False, True),
        ("Dönüştür", "W", "Word'den PDF'e", "Word belgelerini PDF yapın.", u.wordden_pdf, WORD, False, False),
        ("Dönüştür", "P", "PowerPoint'ten PDF'e", "Sunumları PDF yapın.", u.pptden_pdf, PPT, False, False),
        ("Dönüştür", "X", "Excel'den PDF'e", "Excel tablolarını okunaklı PDF yapın.", u.excelden_pdf, EXCEL, False, False),
        ("Dönüştür", "🖼", "JPG'den PDF'e", "Resim ve fotoğrafları tek PDF'te toplayın.", u.resimden_pdf, SARI, False, False),
        ("Dönüştür", "</>", "HTML'den PDF'e", "Web sayfasını ya da HTML dosyasını PDF yapın.", u.htmlden_pdf, SARI, False, False),
        ("İmza & Güvenlik", "✍", "PDF İmzala", "İmza / kaşe resmini koyun; köşeden büyütün, sürükleyip taşıyın.", u.imza_baslat, MAVI, False, True),
        ("İmza & Güvenlik", "🖋", "İmza + Kaşe Seti", "İmza ve kaşeyi birlikte kaydedin, tek tıkla ikisini koyun.", u.imza_setleri, MAVI, True, False),
        ("İmza & Güvenlik", "🔖", "Damga", "ASLI GİBİDİR, ONAYLANDI gibi tarihli kaşe damgası basın.", u.damga_baslat, KIRMIZI, False, True),
        ("İmza & Güvenlik", "🏢", "Antet", "Antetli kağıdınızı (PDF veya resim) sayfalara basın.", u.antet, LACI, False, True),
        ("İmza & Güvenlik", "🔒", "PDF'yi Koru", "Şifre koyun; yetkisiz kişiler açamasın.", u.sifrele, MAVI, False, True),
        ("İmza & Güvenlik", "🔓", "PDF Kilidini Aç", "Şifreyi kaldırıp serbest kopya kaydedin.", u.sifre_kaldir, MAVI, False, True),
        ("İmza & Güvenlik", "⬛", "Karart (Sansür)", "TC no, adres gibi bilgileri kalıcı olarak silin.", lambda: m("karart"), "#26303F", False, True),
        ("İmza & Güvenlik", "⚖", "PDF Karşılaştır", "İki sürümü yan yana koyun; farklar renkli işaretlensin.", u.karsilastir, MAVI, True, True),
        ("İmza & Güvenlik", "▦", "QR / Barkod Oku", "Belgedeki QR kod ve barkodları okuyun, linki açın.", u.qr_oku, GRI, True, True),
        ("İmza & Güvenlik", "📋", "PDF Formları", "Boş çizgileri otomatik doldurulabilir alana çevirin, formu doldurun.", lambda: u.menu_sec("Form"), MOR, True, True),
        ("Yapay Zeka", "🧠", "Yapay Zeka Özetleyici", "Belgeyi Türkçe özetleyin; tarih, tutar, ad ve numaralar çıkarılsın.", u.ozetle, MENEKSE, True, True),
        ("Yapay Zeka", "🌍", "PDF Çevir", "Düzeni bozmadan başka dile çevirin; tablo ve logolar yerinde kalsın.", u.cevir, MENEKSE, True, True),
        ("Yapay Zeka", "💬", "Belgeye Sor", "\"IMO numarası ne?\" gibi sorular sorun, cevap belgeden gelsin.", u.belgeye_sor, MENEKSE, True, True),
        ("Otomasyon", "📦", "Belge Paketi", "Gemi evrakını sırayla tek PDF yapın: yer imi, ad şablonu, MB sınırı.", u.belge_paketi, TURKUAZ, True, False),
        ("Otomasyon", "📠", "Tarayıcıdan Tara", "Tarayıcıdan çok sayfa tarayın, tek PDF olsun.", u.tara, TURKUAZ, True, False),
        ("Otomasyon", "📧", "E-posta ile Gönder", "Outlook'ta PDF ekli yeni ileti açın.", u.eposta, MAVI, True, True),
        ("Otomasyon", "⚙", "Bir iş akışı oluşturun", "Sık kullandığınız araçları sıraya koyun, tek tıkla dosyalara veya tüm klasöre uygulayın.", u.is_akislari, PEMBE, True, False),
    ]


class Vitrin(tk.Frame):
    """Kategori cipleri + kaydirilabilir kart izgarasi."""
    KART_G = 268
    KART_Y = 132

    def __init__(self, ust, u, font="Segoe UI", emoji_font="Segoe UI Emoji", zemin="#FFFFFF"):
        super().__init__(ust, bg=zemin)
        self.u, self.F, self.E, self.Z = u, font, emoji_font, zemin
        self.kategori = "Tümü"
        self._sutun = 0
        ust_ = tk.Frame(self, bg=zemin)
        ust_.pack(fill="x", pady=(14, 6))
        self.ust_ = ust_
        self.cipler = tk.Frame(ust_, bg=zemin)
        self.cipler.pack()
        self._cip_ciz()
        govde = tk.Frame(self, bg=zemin)
        govde.pack(fill="both", expand=True)
        self.tuval = tk.Canvas(govde, bg=zemin, highlightthickness=0, yscrollincrement=24)
        from tkinter import ttk
        sb = ttk.Scrollbar(govde, orient="vertical", command=self.tuval.yview, style="Belge.Vertical.TScrollbar")
        self.tuval.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tuval.pack(side="left", fill="both", expand=True)
        self.ic = tk.Frame(self.tuval, bg=zemin)
        self._pencere = self.tuval.create_window(0, 0, window=self.ic, anchor="n")
        self.ic.bind("<Configure>", lambda e: self.tuval.configure(scrollregion=self.tuval.bbox("all")))
        self.tuval.bind("<Configure>", self._boyut)
        from . import teker as TK
        TK.kaydet(self.tuval, TK.canvas_kaydirici(self.tuval))

    def _teker(self, e):
        self.tuval.yview_scroll(int(-e.delta / 40) or (-1 if e.delta > 0 else 1), "units")

    def _cip_ciz(self):
        for w in self.cipler.winfo_children():
            w.destroy()
        for k in KATEGORILER:
            sec = k == self.kategori
            c = tk.Label(self.cipler, text=k, bg="#26303F" if sec else "white", fg="white" if sec else "#26303F",
                         font=(self.F, 9, "bold" if sec else "normal"), padx=12, pady=4, cursor="hand2",
                         highlightthickness=1, highlightbackground="#26303F" if sec else "#CDD3DE")
            c.pack(side="left", padx=3)
            c.bind("<Button-1>", lambda e, kk=k: self.kategori_sec(kk))
            if not sec:
                c.bind("<Enter>", lambda e, w=c: w.config(highlightbackground="#26303F"))
                c.bind("<Leave>", lambda e, w=c: w.config(highlightbackground="#CDD3DE"))

    def kategori_sec(self, k):
        self.kategori = k
        self._cip_ciz()
        self._sutun = 0
        self._boyut()
        self.tuval.yview_moveto(0)

    def _boyut(self, e=None):
        g = self.tuval.winfo_width()
        sutun = max(1, min(6, (g - 20) // (self.KART_G + 12)))
        self.tuval.coords(self._pencere, g / 2, 0)
        if sutun != self._sutun:
            self._sutun = sutun
            self._kartlari_ciz()

    def _kartlari_ciz(self):
        for w in self.ic.winfo_children():
            w.destroy()
        liste = [k for k in kartlar(self.u) if self.kategori in ("Tümü", k[0])]
        for i, kart in enumerate(liste):
            self._kart(i // self._sutun, i % self._sutun, *kart)

    def _kart(self, r, c, kat, simge, baslik, aciklama, komut, renk, yeni, belge):
        is_akisi = baslik.startswith("Bir iş akışı")
        bg = "#FDE3DF" if is_akisi else "white"
        cer = "#F4B8AE" if is_akisi else "#E1E5EE"
        f = tk.Frame(self.ic, bg=bg, width=self.KART_G, height=self.KART_Y, highlightthickness=1,
                     highlightbackground=cer, cursor="hand2")
        f.grid(row=r, column=c, padx=6, pady=6)
        f.grid_propagate(False)
        f.pack_propagate(False)
        cv = tk.Canvas(f, width=40, height=40, bg=bg, highlightthickness=0)
        cv.place(x=16, y=14)
        harf = simge in ("W", "X", "P", "A", "M↓", "</>", "1 2", "OCR")
        if not is_akisi:
            simge_ciz(cv, 2, 2, 34, renk, simge, harf, self.E, self.F)
        else:
            cv.create_text(20, 20, text="⚙", fill="#E5322D", font=(self.E, 20))
        if yeni:
            tk.Label(f, text="Yeni", bg="#DCE8FF", fg="#2F6FDE", font=(self.F, 7, "bold"), padx=5).place(relx=1, x=-10, y=10, anchor="ne")
        b = tk.Label(f, text=baslik, bg=bg, fg="#1F2430", font=(self.F, 10, "bold"), anchor="w")
        b.place(x=16, y=58)
        a = tk.Label(f, text=aciklama, bg=bg, fg="#5B6577", font=(self.F, 8), anchor="nw", justify="left",
                     wraplength=self.KART_G - 32)
        a.place(x=16, y=80)
        parcalar = (f, cv, b, a)

        def tikla(e=None):
            self.u.vitrin_calistir(komut, belge)

        def uzerinde(e):
            f.config(highlightbackground=renk if not is_akisi else "#E5322D")
            b.config(fg=renk if not is_akisi else "#E5322D")

        def ayrildi(e):
            f.config(highlightbackground=cer)
            b.config(fg="#1F2430")
        for w in parcalar:
            w.bind("<Button-1>", tikla)
            w.bind("<Enter>", uzerinde)
            w.bind("<Leave>", ayrildi)
