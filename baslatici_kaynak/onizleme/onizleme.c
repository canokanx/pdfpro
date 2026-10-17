// PDF PRO - Windows Dosya Gezgini eklentisi
//  * Kucuk resim (thumbnail): PDF simgesi yerine ilk sayfa gorunur
//  * Onizleme bolmesi (Alt+P): sayfalar kaydirilarak okunur
// Sayfalari PDF PRO cizer:  PDF_PRO.exe --onizle <pdf> <klasor> <piksel> <en_fazla> <mod>
// Program klasoru: HKCU\Software\IRONHULL\PDFPRO  "Program"
#ifndef UNICODE
#define UNICODE
#endif
#define COBJMACROS
#include <windows.h>
#include <ole2.h>
#include <shlobj.h>
#include <shobjidl.h>
#include <thumbcache.h>
#include <wchar.h>
#include <stdio.h>

// ---------------------------------------------------------------- GUID'ler
static const GUID CLSID_Kucuk   = {0x4f2266af, 0x4870, 0x4ad7, {0xb0, 0x02, 0xf5, 0x07, 0x53, 0x53, 0x5a, 0x14}};
static const GUID CLSID_Onizle  = {0x099b1e91, 0x513e, 0x4084, {0x93, 0x51, 0x35, 0x84, 0x06, 0xa5, 0x21, 0x66}};
static const GUID IID_Unk       = {0x00000000, 0x0000, 0x0000, {0xc0, 0, 0, 0, 0, 0, 0, 0x46}};
static const GUID IID_CF        = {0x00000001, 0x0000, 0x0000, {0xc0, 0, 0, 0, 0, 0, 0, 0x46}};
static const GUID IID_Thumb     = {0xe357fccd, 0xa995, 0x4576, {0xb0, 0x1f, 0x23, 0x46, 0x30, 0x15, 0x4e, 0x96}};
static const GUID IID_InitStrm  = {0xb824b49d, 0x22ac, 0x4161, {0xac, 0x8a, 0x99, 0x16, 0xe8, 0xfa, 0x3f, 0x7f}};
static const GUID IID_InitFile  = {0xb7d14566, 0x0509, 0x4cce, {0xa7, 0x1f, 0x0a, 0x55, 0x42, 0x33, 0xbd, 0x9b}};
static const GUID IID_Preview   = {0x8895b1c6, 0xb41f, 0x4c1c, {0xa5, 0x62, 0x0d, 0x56, 0x42, 0x50, 0x83, 0x6f}};
static const GUID IID_ObjSite   = {0xfc4801a3, 0x2ba9, 0x11cf, {0xa2, 0x29, 0x00, 0xaa, 0x00, 0x3d, 0x73, 0x52}};
static const GUID IID_Cerceve   = {0xfec87aaf, 0x35f9, 0x447a, {0xad, 0xb7, 0x20, 0x23, 0x44, 0x91, 0x40, 0x1a}};
static const GUID IID_OleWin    = {0x00000114, 0x0000, 0x0000, {0xc0, 0, 0, 0, 0, 0, 0, 0x46}};

static HINSTANCE g_hinst;
static volatile LONG g_ref = 0;
#define ESIT(a, b) IsEqualGUID((a), (b))
#define KAP(tip, uye, p) ((tip *)((char *)(p) - offsetof(tip, uye)))

// ---------------------------------------------------------------- yardimcilar
static int program_exe(wchar_t *exe) {
    wchar_t k[MAX_PATH * 2]; DWORD boy = sizeof(k);
    if (RegGetValueW(HKEY_CURRENT_USER, L"Software\\IRONHULL\\PDFPRO", L"Program", RRF_RT_REG_SZ, NULL, k, &boy) != ERROR_SUCCESS)
        return 0;
    swprintf(exe, MAX_PATH * 2, L"%ls\\PDF_PRO.exe", k);
    return GetFileAttributesW(exe) != INVALID_FILE_ATTRIBUTES;
}

static int gecici_klasor(wchar_t *yol) {
    wchar_t taban[MAX_PATH * 2];
    GUID g; wchar_t gs[64];
    CoCreateGuid(&g);
    StringFromGUID2(&g, gs, 64);
    gs[37] = 0;                         // {} isaretlerini at
    if (GetTempPathW(MAX_PATH, taban)) {
        wchar_t ana[MAX_PATH * 2];
        swprintf(ana, MAX_PATH * 2, L"%lsPDFPRO_onizleme", taban);
        CreateDirectoryW(ana, NULL);
        swprintf(yol, MAX_PATH * 2, L"%ls\\%ls", ana, gs + 1);
        if (CreateDirectoryW(yol, NULL)) return 1;
    }
    // dusuk butunluk seviyesinde calisiyorsak LocalLow
    PWSTR ll = NULL;
    if (SUCCEEDED(SHGetKnownFolderPath(&FOLDERID_LocalAppDataLow, 0, NULL, &ll))) {
        wchar_t ana[MAX_PATH * 2];
        swprintf(ana, MAX_PATH * 2, L"%ls\\PDFPRO_onizleme", ll);
        CoTaskMemFree(ll);
        CreateDirectoryW(ana, NULL);
        swprintf(yol, MAX_PATH * 2, L"%ls\\%ls", ana, gs + 1);
        if (CreateDirectoryW(yol, NULL)) return 1;
    }
    return 0;
}

static void klasor_sil(const wchar_t *k) {
    wchar_t desen[MAX_PATH * 2], y[MAX_PATH * 2];
    swprintf(desen, MAX_PATH * 2, L"%ls\\*", k);
    WIN32_FIND_DATAW fd;
    HANDLE f = FindFirstFileW(desen, &fd);
    if (f != INVALID_HANDLE_VALUE) {
        do {
            if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) continue;
            swprintf(y, MAX_PATH * 2, L"%ls\\%ls", k, fd.cFileName);
            DeleteFileW(y);
        } while (FindNextFileW(f, &fd));
        FindClose(f);
    }
    RemoveDirectoryW(k);
}

static int akisi_yaz(IStream *s, const wchar_t *yol) {
    LARGE_INTEGER sifir; sifir.QuadPart = 0;
    IStream_Seek(s, sifir, STREAM_SEEK_SET, NULL);
    HANDLE h = CreateFileW(yol, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_TEMPORARY, NULL);
    if (h == INVALID_HANDLE_VALUE) return 0;
    char *tampon = (char *)HeapAlloc(GetProcessHeap(), 0, 1 << 16);
    if (!tampon) { CloseHandle(h); return 0; }
    ULONG n = 0; int ok = 1;
    for (;;) {
        HRESULT hr = IStream_Read(s, tampon, 1 << 16, &n);
        if (FAILED(hr)) { ok = 0; break; }
        if (!n) break;
        DWORD yazilan;
        if (!WriteFile(h, tampon, n, &yazilan, NULL) || yazilan != n) { ok = 0; break; }
        if (hr == S_FALSE) break;
    }
    HeapFree(GetProcessHeap(), 0, tampon);
    CloseHandle(h);
    return ok;
}

static int var_mi(const wchar_t *yol) { return GetFileAttributesW(yol) != INVALID_FILE_ATTRIBUTES; }

static HANDLE ciziciyi_baslat(const wchar_t *pdf, const wchar_t *klasor, int piksel, int en_fazla, const wchar_t *mod) {
    wchar_t exe[MAX_PATH * 2];
    if (!program_exe(exe)) return NULL;
    wchar_t calisma[MAX_PATH * 2];
    wcscpy(calisma, exe);
    wchar_t *s = wcsrchr(calisma, L'\\'); if (s) *s = 0;
    size_t boy = wcslen(exe) + wcslen(pdf) + wcslen(klasor) + 128;
    wchar_t *komut = (wchar_t *)HeapAlloc(GetProcessHeap(), 0, boy * sizeof(wchar_t));
    swprintf(komut, boy, L"\"%ls\" --onizle \"%ls\" \"%ls\" %d %d %ls", exe, pdf, klasor, piksel, en_fazla, mod);
    STARTUPINFOW si; PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si)); si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW; si.wShowWindow = SW_HIDE;
    ZeroMemory(&pi, sizeof(pi));
    BOOL ok = CreateProcessW(exe, komut, NULL, NULL, FALSE, CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS,
                             NULL, calisma, &si, &pi);
    HeapFree(GetProcessHeap(), 0, komut);
    if (!ok) return NULL;
    CloseHandle(pi.hThread);
    return pi.hProcess;
}

// sNNNN.bin -> 24 bit BGR, satirlar 4'un kati (StretchDIBits icin hazir)
typedef struct { int w, h, satir; BYTE *veri; } Sayfa;

static int sayfa_oku(const wchar_t *yol, Sayfa *s) {
    HANDLE h = CreateFileW(yol, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_DELETE, NULL, OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE) return 0;
    DWORD n; BYTE bas[16]; int ok = 0;
    if (ReadFile(h, bas, 16, &n, NULL) && n == 16 && memcmp(bas, "PPV1", 4) == 0) {
        int w = *(UINT32 *)(bas + 4), hh = *(UINT32 *)(bas + 8), satir = *(UINT32 *)(bas + 12);
        if (w > 0 && hh > 0 && w < 20000 && hh < 30000 && satir >= w * 3 && satir == ((w * 3 + 3) & ~3)) {
            SIZE_T boy = (SIZE_T)satir * hh;
            BYTE *v = (BYTE *)HeapAlloc(GetProcessHeap(), 0, boy);
            if (v && ReadFile(h, v, (DWORD)boy, &n, NULL) && n == boy) {
                for (int y = 0; y < hh; y++) {          // RGB -> BGR
                    BYTE *p = v + (SIZE_T)y * satir;
                    for (int x = 0; x < w; x++, p += 3) { BYTE t = p[0]; p[0] = p[2]; p[2] = t; }
                }
                s->w = w; s->h = hh; s->satir = satir; s->veri = v; ok = 1;
            } else if (v) HeapFree(GetProcessHeap(), 0, v);
        }
    }
    CloseHandle(h);
    return ok;
}

static void sayfa_bosalt(Sayfa *s) { if (s->veri) HeapFree(GetProcessHeap(), 0, s->veri); s->veri = NULL; }

// ================================================================ KUCUK RESIM
typedef struct {
    IThumbnailProviderVtbl *thumb;
    IInitializeWithStreamVtbl *akis;
    LONG ref;
    IStream *s;
} Kucuk;

static HRESULT STDMETHODCALLTYPE K_QI(Kucuk *k, REFIID r, void **pp) {
    if (ESIT(r, &IID_Unk) || ESIT(r, &IID_Thumb)) *pp = &k->thumb;
    else if (ESIT(r, &IID_InitStrm)) *pp = &k->akis;
    else { *pp = NULL; return E_NOINTERFACE; }
    InterlockedIncrement(&k->ref);
    return S_OK;
}
static ULONG K_Rel(Kucuk *k) {
    LONG r = InterlockedDecrement(&k->ref);
    if (!r) { if (k->s) IStream_Release(k->s); HeapFree(GetProcessHeap(), 0, k); InterlockedDecrement(&g_ref); }
    return r;
}
static HRESULT STDMETHODCALLTYPE KT_QI(IThumbnailProvider *p, REFIID r, void **pp) { return K_QI(KAP(Kucuk, thumb, p), r, pp); }
static ULONG STDMETHODCALLTYPE KT_Add(IThumbnailProvider *p) { return InterlockedIncrement(&KAP(Kucuk, thumb, p)->ref); }
static ULONG STDMETHODCALLTYPE KT_Rel(IThumbnailProvider *p) { return K_Rel(KAP(Kucuk, thumb, p)); }
static HRESULT STDMETHODCALLTYPE KA_QI(IInitializeWithStream *p, REFIID r, void **pp) { return K_QI(KAP(Kucuk, akis, p), r, pp); }
static ULONG STDMETHODCALLTYPE KA_Add(IInitializeWithStream *p) { return InterlockedIncrement(&KAP(Kucuk, akis, p)->ref); }
static ULONG STDMETHODCALLTYPE KA_Rel(IInitializeWithStream *p) { return K_Rel(KAP(Kucuk, akis, p)); }

static HRESULT STDMETHODCALLTYPE KA_Init(IInitializeWithStream *p, IStream *s, DWORD mod) {
    Kucuk *k = KAP(Kucuk, akis, p);
    if (k->s) return HRESULT_FROM_WIN32(ERROR_ALREADY_INITIALIZED);
    k->s = s; IStream_AddRef(s);
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE KT_Get(IThumbnailProvider *p, UINT cx, HBITMAP *bmp, WTS_ALPHATYPE *alfa) {
    Kucuk *k = KAP(Kucuk, thumb, p);
    *bmp = NULL;
    if (!k->s) return E_UNEXPECTED;
    wchar_t klasor[MAX_PATH * 2], pdf[MAX_PATH * 2], yol[MAX_PATH * 2];
    if (!gecici_klasor(klasor)) return E_FAIL;
    swprintf(pdf, MAX_PATH * 2, L"%ls\\belge.pdf", klasor);
    HRESULT sonuc = E_FAIL;
    if (akisi_yaz(k->s, pdf)) {
        HANDLE pr = ciziciyi_baslat(pdf, klasor, cx ? (int)cx : 256, 1, L"kucuk");
        if (pr) {
            wchar_t bitti[MAX_PATH * 2];
            swprintf(yol, MAX_PATH * 2, L"%ls\\s0001.bin", klasor);
            swprintf(bitti, MAX_PATH * 2, L"%ls\\bitti.txt", klasor);
            for (int t = 0; t < 600 && !var_mi(yol) && !var_mi(bitti); t++) Sleep(50);   // en fazla 30 sn
            Sayfa s = {0};
            if (sayfa_oku(yol, &s)) {
                BITMAPINFO bi; ZeroMemory(&bi, sizeof(bi));
                bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
                bi.bmiHeader.biWidth = s.w; bi.bmiHeader.biHeight = -s.h;
                bi.bmiHeader.biPlanes = 1; bi.bmiHeader.biBitCount = 32; bi.bmiHeader.biCompression = BI_RGB;
                BYTE *bits = NULL;
                HBITMAP h = CreateDIBSection(NULL, &bi, DIB_RGB_COLORS, (void **)&bits, NULL, 0);
                if (h && bits) {
                    for (int y = 0; y < s.h; y++) {
                        BYTE *a = s.veri + (SIZE_T)y * s.satir, *b = bits + (SIZE_T)y * s.w * 4;
                        for (int x = 0; x < s.w; x++, a += 3, b += 4) { b[0] = a[0]; b[1] = a[1]; b[2] = a[2]; b[3] = 255; }
                    }
                    *bmp = h; *alfa = WTSAT_RGB; sonuc = S_OK;
                }
                sayfa_bosalt(&s);
            }
            for (int t = 0; t < 40 && !var_mi(bitti); t++) Sleep(50);
            CloseHandle(pr);
        }
    }
    klasor_sil(klasor);
    return sonuc;
}

static IThumbnailProviderVtbl vt_kucuk = {KT_QI, KT_Add, KT_Rel, KT_Get};
static IInitializeWithStreamVtbl vt_kucuk_akis = {KA_QI, KA_Add, KA_Rel, KA_Init};

// ================================================================ ONIZLEME BOLMESI
#define ONIZLEME_PIKSEL 760
#define ONIZLEME_SAYFA 30
#define WM_YENI (WM_APP + 7)
#define KENAR 14

typedef struct {
    IPreviewHandlerVtbl *prev;
    IInitializeWithStreamVtbl *akis;
    IInitializeWithFileVtbl *dosya;
    IObjectWithSiteVtbl *site_vt;
    IOleWindowVtbl *pencere_vt;
    LONG ref;
    IStream *s;
    wchar_t dosya_yolu[MAX_PATH * 2];
    IUnknown *site;
    HWND ust, hwnd;
    RECT rc;
    HANDLE is, dur, surec;
    CRITICAL_SECTION kilit;
    Sayfa sayfalar[ONIZLEME_SAYFA];
    int adet, toplam, durum;      // durum: 0 hazirlaniyor, 1 bitti, 2 sifreli, 3 hata
    int kaydirma, yukseklik;
    int teker_birikim;
    wchar_t klasor[MAX_PATH * 2];
} Onizle;

static void O_temizle(Onizle *o) {
    if (o->dur) SetEvent(o->dur);
    if (o->is) { WaitForSingleObject(o->is, 3000); CloseHandle(o->is); o->is = NULL; }
    if (o->surec) { TerminateProcess(o->surec, 0); CloseHandle(o->surec); o->surec = NULL; }
    if (o->dur) { CloseHandle(o->dur); o->dur = NULL; }
    if (o->hwnd) { SetWindowLongPtrW(o->hwnd, GWLP_USERDATA, 0); DestroyWindow(o->hwnd); o->hwnd = NULL; }
    EnterCriticalSection(&o->kilit);
    for (int i = 0; i < o->adet; i++) sayfa_bosalt(&o->sayfalar[i]);
    o->adet = 0; o->toplam = 0; o->durum = 0; o->kaydirma = 0;
    LeaveCriticalSection(&o->kilit);
    if (o->klasor[0]) { Sleep(100); klasor_sil(o->klasor); o->klasor[0] = 0; }
}

static HRESULT O_QI(Onizle *o, REFIID r, void **pp) {
    if (ESIT(r, &IID_Unk) || ESIT(r, &IID_Preview)) *pp = &o->prev;
    else if (ESIT(r, &IID_InitStrm)) *pp = &o->akis;
    else if (ESIT(r, &IID_InitFile)) *pp = &o->dosya;
    else if (ESIT(r, &IID_ObjSite)) *pp = &o->site_vt;
    else if (ESIT(r, &IID_OleWin)) *pp = &o->pencere_vt;
    else { *pp = NULL; return E_NOINTERFACE; }
    InterlockedIncrement(&o->ref);
    return S_OK;
}
static ULONG O_Rel(Onizle *o) {
    LONG r = InterlockedDecrement(&o->ref);
    if (!r) {
        O_temizle(o);
        if (o->s) IStream_Release(o->s);
        if (o->site) IUnknown_Release(o->site);
        DeleteCriticalSection(&o->kilit);
        HeapFree(GetProcessHeap(), 0, o);
        InterlockedDecrement(&g_ref);
    }
    return r;
}

// --- yerlesim ve cizim
static int sayfa_yuksekligi(Sayfa *s, int gen) { return (int)((double)s->h * gen / s->w + 0.5); }

static void yerlesim(Onizle *o, int *gen_out) {
    RECT r; GetClientRect(o->hwnd, &r);
    int gen = r.right - 2 * KENAR; if (gen < 40) gen = 40;
    int y = KENAR;
    for (int i = 0; i < o->adet; i++) y += sayfa_yuksekligi(&o->sayfalar[i], gen) + KENAR;
    if (o->durum == 1 && o->toplam > o->adet) y += 40;
    o->yukseklik = y;
    int en = o->yukseklik - r.bottom; if (en < 0) en = 0;
    if (o->kaydirma > en) o->kaydirma = en;
    if (o->kaydirma < 0) o->kaydirma = 0;
    SCROLLINFO si; si.cbSize = sizeof(si); si.fMask = SIF_RANGE | SIF_PAGE | SIF_POS;
    si.nMin = 0; si.nMax = o->yukseklik > 0 ? o->yukseklik - 1 : 0; si.nPage = r.bottom; si.nPos = o->kaydirma;
    SetScrollInfo(o->hwnd, SB_VERT, &si, TRUE);
    if (gen_out) *gen_out = gen;
}

static void yazi(HDC dc, RECT *r, const wchar_t *m, COLORREF renk) {
    SetTextColor(dc, renk); SetBkMode(dc, TRANSPARENT);
    DrawTextW(dc, m, -1, r, DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS);
}

static void ciz(Onizle *o, HDC hedef) {
    RECT r; GetClientRect(o->hwnd, &r);
    HDC dc = CreateCompatibleDC(hedef);
    HBITMAP bm = CreateCompatibleBitmap(hedef, r.right ? r.right : 1, r.bottom ? r.bottom : 1);
    HGDIOBJ eski = SelectObject(dc, bm);
    HBRUSH zemin = CreateSolidBrush(RGB(0xEE, 0xEF, 0xF1));
    FillRect(dc, &r, zemin); DeleteObject(zemin);
    HFONT f = CreateFontW(-15, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
    HGDIOBJ ef = SelectObject(dc, f);
    EnterCriticalSection(&o->kilit);
    int gen; yerlesim(o, &gen);
    if (o->adet == 0) {
        const wchar_t *m = o->durum == 2 ? L"Bu PDF parola korumalı — önizleme yok" :
                           o->durum == 3 ? L"Önizleme oluşturulamadı" :
                           o->durum == 1 ? L"Bu PDF'te sayfa yok" : L"PDF PRO önizlemeyi hazırlıyor…";
        yazi(dc, &r, m, RGB(0x6B, 0x72, 0x80));
    } else {
        SetStretchBltMode(dc, HALFTONE); SetBrushOrgEx(dc, 0, 0, NULL);
        HBRUSH golge = CreateSolidBrush(RGB(0xC9, 0xCD, 0xD3));
        int y = KENAR - o->kaydirma;
        for (int i = 0; i < o->adet; i++) {
            Sayfa *s = &o->sayfalar[i];
            int h = sayfa_yuksekligi(s, gen);
            if (y + h >= 0 && y <= r.bottom) {
                RECT g = {KENAR + 2, y + 2, KENAR + gen + 2, y + h + 2};
                FillRect(dc, &g, golge);
                BITMAPINFO bi; ZeroMemory(&bi, sizeof(bi));
                bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
                bi.bmiHeader.biWidth = s->w; bi.bmiHeader.biHeight = -s->h;
                bi.bmiHeader.biPlanes = 1; bi.bmiHeader.biBitCount = 24; bi.bmiHeader.biCompression = BI_RGB;
                StretchDIBits(dc, KENAR, y, gen, h, 0, 0, s->w, s->h, s->veri, &bi, DIB_RGB_COLORS, SRCCOPY);
            }
            y += h + KENAR;
        }
        DeleteObject(golge);
        if (o->durum == 1 && o->toplam > o->adet) {
            wchar_t m[200];
            swprintf(m, 200, L"İlk %d sayfa gösteriliyor (toplam %d) — tamamı için PDF PRO ile açın",
                     o->adet, o->toplam);
            RECT t = {0, y, r.right, y + 30};
            yazi(dc, &t, m, RGB(0x6B, 0x72, 0x80));
        } else if (o->durum == 0) {
            RECT t = {0, y, r.right, y + 30};
            yazi(dc, &t, L"Sayfalar yükleniyor…", RGB(0x6B, 0x72, 0x80));
        }
    }
    LeaveCriticalSection(&o->kilit);
    BitBlt(hedef, 0, 0, r.right, r.bottom, dc, 0, 0, SRCCOPY);
    SelectObject(dc, ef); DeleteObject(f);
    SelectObject(dc, eski); DeleteObject(bm); DeleteDC(dc);
}

static void kaydir(Onizle *o, int yeni) {
    RECT r; GetClientRect(o->hwnd, &r);
    int en = o->yukseklik - r.bottom; if (en < 0) en = 0;
    if (yeni > en) yeni = en;
    if (yeni < 0) yeni = 0;
    if (yeni == o->kaydirma) return;
    o->kaydirma = yeni;
    SetScrollPos(o->hwnd, SB_VERT, yeni, TRUE);
    InvalidateRect(o->hwnd, NULL, FALSE);
}

static LRESULT CALLBACK pencere_isle(HWND h, UINT m, WPARAM w, LPARAM l) {
    Onizle *o = (Onizle *)GetWindowLongPtrW(h, GWLP_USERDATA);
    if (!o) return DefWindowProcW(h, m, w, l);
    switch (m) {
    case WM_PAINT: { PAINTSTRUCT ps; HDC dc = BeginPaint(h, &ps); ciz(o, dc); EndPaint(h, &ps); return 0; }
    case WM_ERASEBKGND: return 1;
    case WM_SIZE: EnterCriticalSection(&o->kilit); yerlesim(o, NULL); LeaveCriticalSection(&o->kilit);
                  InvalidateRect(h, NULL, FALSE); return 0;
    case WM_YENI: InvalidateRect(h, NULL, FALSE); return 0;
    case WM_MOUSEWHEEL: {
        o->teker_birikim += GET_WHEEL_DELTA_WPARAM(w);
        int adim = o->teker_birikim * 100 / WHEEL_DELTA;         // centik basina 100 piksel (touchpad'de kucuk adimlar)
        if (adim) { o->teker_birikim -= adim * WHEEL_DELTA / 100; kaydir(o, o->kaydirma - adim); }
        return 0;
    }
    case WM_VSCROLL: {
        RECT r; GetClientRect(h, &r);
        SCROLLINFO si; si.cbSize = sizeof(si); si.fMask = SIF_TRACKPOS; GetScrollInfo(h, SB_VERT, &si);
        int y = o->kaydirma;
        switch (LOWORD(w)) {
        case SB_LINEUP: y -= 60; break;      case SB_LINEDOWN: y += 60; break;
        case SB_PAGEUP: y -= r.bottom; break; case SB_PAGEDOWN: y += r.bottom; break;
        case SB_TOP: y = 0; break;           case SB_BOTTOM: y = o->yukseklik; break;
        case SB_THUMBTRACK: case SB_THUMBPOSITION: y = si.nTrackPos; break;
        }
        kaydir(o, y);
        return 0;
    }
    case WM_KEYDOWN: {
        RECT r; GetClientRect(h, &r);
        if (w == VK_DOWN) kaydir(o, o->kaydirma + 60);
        else if (w == VK_UP) kaydir(o, o->kaydirma - 60);
        else if (w == VK_NEXT || w == VK_SPACE) kaydir(o, o->kaydirma + r.bottom - 40);
        else if (w == VK_PRIOR) kaydir(o, o->kaydirma - r.bottom + 40);
        else if (w == VK_HOME) kaydir(o, 0);
        else if (w == VK_END) kaydir(o, o->yukseklik);
        return 0;
    }
    case WM_LBUTTONDOWN: SetFocus(h); return 0;
    case WM_MOUSEACTIVATE: return MA_ACTIVATE;
    }
    return DefWindowProcW(h, m, w, l);
}

static DWORD WINAPI cizim_isi(LPVOID p) {
    Onizle *o = (Onizle *)p;
    wchar_t yol[MAX_PATH * 2], bitti[MAX_PATH * 2];
    swprintf(bitti, MAX_PATH * 2, L"%ls\\bitti.txt", o->klasor);
    int bekleme = 0;
    while (WaitForSingleObject(o->dur, 60) == WAIT_TIMEOUT) {
        int sira = o->adet + 1;
        swprintf(yol, MAX_PATH * 2, L"%ls\\s%04d.bin", o->klasor, sira);
        if (sira <= ONIZLEME_SAYFA && var_mi(yol)) {
            Sayfa s = {0};
            if (sayfa_oku(yol, &s)) {
                EnterCriticalSection(&o->kilit);
                o->sayfalar[o->adet++] = s;
                LeaveCriticalSection(&o->kilit);
                DeleteFileW(yol);
                if (o->hwnd) PostMessageW(o->hwnd, WM_YENI, 0, 0);
                bekleme = 0;
                continue;
            }
        }
        if (var_mi(bitti)) {
            // bitti.txt'den once yazilmis tum sayfalar alindi mi?
            swprintf(yol, MAX_PATH * 2, L"%ls\\s%04d.bin", o->klasor, o->adet + 1);
            if (var_mi(yol)) continue;
            char t[256] = {0}; DWORD n = 0;
            HANDLE h = CreateFileW(bitti, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
            if (h != INVALID_HANDLE_VALUE) { ReadFile(h, t, sizeof(t) - 1, &n, NULL); CloseHandle(h); }
            EnterCriticalSection(&o->kilit);
            int a = 0, top = 0;
            if (strncmp(t, "tamam", 5) == 0 && sscanf(t + 5, "%d %d", &a, &top) == 2) { o->toplam = top; o->durum = 1; }
            else if (strncmp(t, "sifreli", 7) == 0) o->durum = 2;
            else o->durum = 3;
            LeaveCriticalSection(&o->kilit);
            if (o->hwnd) PostMessageW(o->hwnd, WM_YENI, 0, 0);
            break;
        }
        if (++bekleme > 1500) {             // ~90 sn hic ilerleme yok
            EnterCriticalSection(&o->kilit); o->durum = 3; LeaveCriticalSection(&o->kilit);
            if (o->hwnd) PostMessageW(o->hwnd, WM_YENI, 0, 0);
            break;
        }
    }
    return 0;
}

static ATOM pencere_sinifi(void) {
    static ATOM a = 0;
    if (a) return a;
    WNDCLASSW wc; ZeroMemory(&wc, sizeof(wc));
    wc.lpfnWndProc = pencere_isle; wc.hInstance = g_hinst;
    wc.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW);
    wc.lpszClassName = L"PDFPRO_Onizleme";
    a = RegisterClassW(&wc);
    if (!a && GetLastError() == ERROR_CLASS_ALREADY_EXISTS) a = 1;
    return a;
}

// --- IPreviewHandler
#define OP(p) KAP(Onizle, prev, p)
static HRESULT STDMETHODCALLTYPE P_QI(IPreviewHandler *p, REFIID r, void **pp) { return O_QI(OP(p), r, pp); }
static ULONG STDMETHODCALLTYPE P_Add(IPreviewHandler *p) { return InterlockedIncrement(&OP(p)->ref); }
static ULONG STDMETHODCALLTYPE P_Rel(IPreviewHandler *p) { return O_Rel(OP(p)); }
static HRESULT STDMETHODCALLTYPE P_SetWindow(IPreviewHandler *p, HWND ust, const RECT *rc) {
    Onizle *o = OP(p);
    if (!ust || !rc) return E_INVALIDARG;
    o->ust = ust; o->rc = *rc;
    if (o->hwnd) {
        SetParent(o->hwnd, ust);
        SetWindowPos(o->hwnd, NULL, rc->left, rc->top, rc->right - rc->left, rc->bottom - rc->top, SWP_NOZORDER | SWP_NOACTIVATE);
    }
    return S_OK;
}
static HRESULT STDMETHODCALLTYPE P_SetRect(IPreviewHandler *p, const RECT *rc) {
    Onizle *o = OP(p);
    if (!rc) return E_INVALIDARG;
    o->rc = *rc;
    if (o->hwnd)
        SetWindowPos(o->hwnd, NULL, rc->left, rc->top, rc->right - rc->left, rc->bottom - rc->top, SWP_NOZORDER | SWP_NOACTIVATE);
    return S_OK;
}
static HRESULT STDMETHODCALLTYPE P_DoPreview(IPreviewHandler *p) {
    Onizle *o = OP(p);
    if (o->hwnd) return E_FAIL;
    if (!o->s && !o->dosya_yolu[0]) return E_UNEXPECTED;
    if (!pencere_sinifi()) return E_FAIL;
    o->hwnd = CreateWindowExW(0, L"PDFPRO_Onizleme", L"", WS_CHILD | WS_VSCROLL | WS_VISIBLE | WS_CLIPSIBLINGS,
                              o->rc.left, o->rc.top, o->rc.right - o->rc.left, o->rc.bottom - o->rc.top,
                              o->ust, NULL, g_hinst, NULL);
    if (!o->hwnd) return HRESULT_FROM_WIN32(GetLastError());
    SetWindowLongPtrW(o->hwnd, GWLP_USERDATA, (LONG_PTR)o);
    InvalidateRect(o->hwnd, NULL, FALSE);
    if (!gecici_klasor(o->klasor)) { o->klasor[0] = 0; o->durum = 3; return S_OK; }
    wchar_t pdf[MAX_PATH * 2];
    if (o->s) {
        swprintf(pdf, MAX_PATH * 2, L"%ls\\belge.pdf", o->klasor);
        if (!akisi_yaz(o->s, pdf)) { o->durum = 3; return S_OK; }
    } else wcscpy(pdf, o->dosya_yolu);
    o->surec = ciziciyi_baslat(pdf, o->klasor, ONIZLEME_PIKSEL, ONIZLEME_SAYFA, L"genislik");
    if (!o->surec) { o->durum = 3; InvalidateRect(o->hwnd, NULL, FALSE); return S_OK; }
    o->dur = CreateEventW(NULL, TRUE, FALSE, NULL);
    o->is = CreateThread(NULL, 0, cizim_isi, o, 0, NULL);
    return S_OK;
}
static HRESULT STDMETHODCALLTYPE P_Unload(IPreviewHandler *p) {
    Onizle *o = OP(p);
    O_temizle(o);
    if (o->s) { IStream_Release(o->s); o->s = NULL; }
    o->dosya_yolu[0] = 0;
    return S_OK;
}
static HRESULT STDMETHODCALLTYPE P_SetFocus(IPreviewHandler *p) {
    Onizle *o = OP(p);
    if (o->hwnd) SetFocus(o->hwnd);
    return S_OK;
}
static HRESULT STDMETHODCALLTYPE P_QueryFocus(IPreviewHandler *p, HWND *h) {
    if (!h) return E_INVALIDARG;
    *h = GetFocus();
    return *h ? S_OK : HRESULT_FROM_WIN32(GetLastError());
}
static HRESULT STDMETHODCALLTYPE P_Translate(IPreviewHandler *p, MSG *m) {
    Onizle *o = OP(p);
    IPreviewHandlerFrame *cerceve = NULL;
    HRESULT hr = S_FALSE;
    if (o->site && SUCCEEDED(IUnknown_QueryInterface(o->site, &IID_Cerceve, (void **)&cerceve)) && cerceve) {
        hr = IPreviewHandlerFrame_TranslateAccelerator(cerceve, m);
        IPreviewHandlerFrame_Release(cerceve);
    }
    return hr;
}
static IPreviewHandlerVtbl vt_onizle = {P_QI, P_Add, P_Rel, P_SetWindow, P_SetRect, P_DoPreview, P_Unload,
                                       P_SetFocus, P_QueryFocus, P_Translate};

// --- IInitializeWithStream / IInitializeWithFile
#define OA(p) KAP(Onizle, akis, p)
static HRESULT STDMETHODCALLTYPE OA_QI(IInitializeWithStream *p, REFIID r, void **pp) { return O_QI(OA(p), r, pp); }
static ULONG STDMETHODCALLTYPE OA_Add(IInitializeWithStream *p) { return InterlockedIncrement(&OA(p)->ref); }
static ULONG STDMETHODCALLTYPE OA_Rel(IInitializeWithStream *p) { return O_Rel(OA(p)); }
static HRESULT STDMETHODCALLTYPE OA_Init(IInitializeWithStream *p, IStream *s, DWORD mod) {
    Onizle *o = OA(p);
    if (o->s) IStream_Release(o->s);
    o->s = s; IStream_AddRef(s);
    return S_OK;
}
static IInitializeWithStreamVtbl vt_onizle_akis = {OA_QI, OA_Add, OA_Rel, OA_Init};

#define OD(p) KAP(Onizle, dosya, p)
static HRESULT STDMETHODCALLTYPE OD_QI(IInitializeWithFile *p, REFIID r, void **pp) { return O_QI(OD(p), r, pp); }
static ULONG STDMETHODCALLTYPE OD_Add(IInitializeWithFile *p) { return InterlockedIncrement(&OD(p)->ref); }
static ULONG STDMETHODCALLTYPE OD_Rel(IInitializeWithFile *p) { return O_Rel(OD(p)); }
static HRESULT STDMETHODCALLTYPE OD_Init(IInitializeWithFile *p, LPCWSTR yol, DWORD mod) {
    Onizle *o = OD(p);
    if (!yol || wcslen(yol) >= MAX_PATH * 2) return E_INVALIDARG;
    wcscpy(o->dosya_yolu, yol);
    return S_OK;
}
static IInitializeWithFileVtbl vt_onizle_dosya = {OD_QI, OD_Add, OD_Rel, OD_Init};

// --- IObjectWithSite
#define OS(p) KAP(Onizle, site_vt, p)
static HRESULT STDMETHODCALLTYPE OS_QI(IObjectWithSite *p, REFIID r, void **pp) { return O_QI(OS(p), r, pp); }
static ULONG STDMETHODCALLTYPE OS_Add(IObjectWithSite *p) { return InterlockedIncrement(&OS(p)->ref); }
static ULONG STDMETHODCALLTYPE OS_Rel(IObjectWithSite *p) { return O_Rel(OS(p)); }
static HRESULT STDMETHODCALLTYPE OS_Set(IObjectWithSite *p, IUnknown *site) {
    Onizle *o = OS(p);
    if (o->site) IUnknown_Release(o->site);
    o->site = site;
    if (site) IUnknown_AddRef(site);
    return S_OK;
}
static HRESULT STDMETHODCALLTYPE OS_Get(IObjectWithSite *p, REFIID r, void **pp) {
    Onizle *o = OS(p);
    if (!o->site) { *pp = NULL; return E_FAIL; }
    return IUnknown_QueryInterface(o->site, r, pp);
}
static IObjectWithSiteVtbl vt_onizle_site = {OS_QI, OS_Add, OS_Rel, OS_Set, OS_Get};

// --- IOleWindow
#define OW(p) KAP(Onizle, pencere_vt, p)
static HRESULT STDMETHODCALLTYPE OW_QI(IOleWindow *p, REFIID r, void **pp) { return O_QI(OW(p), r, pp); }
static ULONG STDMETHODCALLTYPE OW_Add(IOleWindow *p) { return InterlockedIncrement(&OW(p)->ref); }
static ULONG STDMETHODCALLTYPE OW_Rel(IOleWindow *p) { return O_Rel(OW(p)); }
static HRESULT STDMETHODCALLTYPE OW_Get(IOleWindow *p, HWND *h) {
    if (!h) return E_INVALIDARG;
    *h = OW(p)->ust;
    return S_OK;
}
static HRESULT STDMETHODCALLTYPE OW_Ctx(IOleWindow *p, BOOL b) { return E_NOTIMPL; }
static IOleWindowVtbl vt_onizle_pencere = {OW_QI, OW_Add, OW_Rel, OW_Get, OW_Ctx};

// ================================================================ sinif fabrikasi
typedef struct { IClassFactoryVtbl *vt; int tur; } Fabrika;

static HRESULT STDMETHODCALLTYPE F_QI(IClassFactory *p, REFIID r, void **pp) {
    if (ESIT(r, &IID_Unk) || ESIT(r, &IID_CF)) { *pp = p; InterlockedIncrement(&g_ref); return S_OK; }
    *pp = NULL; return E_NOINTERFACE;
}
static ULONG STDMETHODCALLTYPE F_Add(IClassFactory *p) { InterlockedIncrement(&g_ref); return 2; }
static ULONG STDMETHODCALLTYPE F_Rel(IClassFactory *p) { InterlockedDecrement(&g_ref); return 1; }
static HRESULT STDMETHODCALLTYPE F_Create(IClassFactory *p, IUnknown *dis, REFIID r, void **pp) {
    Fabrika *f = (Fabrika *)p;
    *pp = NULL;
    if (dis) return CLASS_E_NOAGGREGATION;
    HRESULT hr;
    if (f->tur == 0) {
        Kucuk *k = (Kucuk *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(Kucuk));
        if (!k) return E_OUTOFMEMORY;
        k->thumb = &vt_kucuk; k->akis = &vt_kucuk_akis; k->ref = 1;
        InterlockedIncrement(&g_ref);
        hr = K_QI(k, r, pp);
        K_Rel(k);
    } else {
        Onizle *o = (Onizle *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(Onizle));
        if (!o) return E_OUTOFMEMORY;
        o->prev = &vt_onizle; o->akis = &vt_onizle_akis; o->dosya = &vt_onizle_dosya;
        o->site_vt = &vt_onizle_site; o->pencere_vt = &vt_onizle_pencere; o->ref = 1;
        InitializeCriticalSection(&o->kilit);
        InterlockedIncrement(&g_ref);
        hr = O_QI(o, r, pp);
        O_Rel(o);
    }
    return hr;
}
static HRESULT STDMETHODCALLTYPE F_Lock(IClassFactory *p, BOOL k) {
    if (k) InterlockedIncrement(&g_ref); else InterlockedDecrement(&g_ref);
    return S_OK;
}
static IClassFactoryVtbl vt_fabrika = {F_QI, F_Add, F_Rel, F_Create, F_Lock};
static Fabrika fab_kucuk = {&vt_fabrika, 0}, fab_onizle = {&vt_fabrika, 1};

__declspec(dllexport) HRESULT WINAPI DllGetClassObject(REFCLSID c, REFIID r, void **pp) {
    *pp = NULL;
    Fabrika *f = ESIT(c, &CLSID_Kucuk) ? &fab_kucuk : ESIT(c, &CLSID_Onizle) ? &fab_onizle : NULL;
    if (!f) return CLASS_E_CLASSNOTAVAILABLE;
    return F_QI((IClassFactory *)f, r, pp);
}
__declspec(dllexport) HRESULT WINAPI DllCanUnloadNow(void) { return g_ref > 0 ? S_FALSE : S_OK; }

BOOL WINAPI DllMain(HINSTANCE h, DWORD neden, LPVOID r) {
    if (neden == DLL_PROCESS_ATTACH) { g_hinst = h; DisableThreadLibraryCalls(h); }
    return TRUE;
}
