// PDF PRO kurulum baslaticisi.
// Bu EXE'nin sonuna eklenmis paketi (PPAK) gecici klasore acar, icindeki Python ile
// kurulum sihirbazini (kurulum.pyw) calistirir, bitince gecici klasoru siler.
#ifndef UNICODE
#define UNICODE
#endif
#include <windows.h>
#include <commctrl.h>
#include <shellapi.h>
#include <stdio.h>
#include <stdint.h>
#include <zlib.h>

static HWND g_pencere, g_cubuk, g_yazi;
static wchar_t g_gecici[MAX_PATH * 2];
static volatile LONG g_bitti = 0;
static volatile int g_hata = 0;
static wchar_t g_hata_metni[512];
static uint64_t g_toplam = 1, g_islenen = 0;

static int oku(HANDLE h, void *buf, DWORD n) {
    DWORD o = 0;
    while (n) {
        DWORD k = 0;
        if (!ReadFile(h, buf, n, &k, NULL) || k == 0) return 0;
        buf = (char *)buf + k; n -= k; o += k;
    }
    return 1;
}

static void klasorleri_olustur(wchar_t *yol) {
    for (wchar_t *p = yol + 3; *p; p++) {
        if (*p == L'\\') { *p = 0; CreateDirectoryW(yol, NULL); *p = L'\\'; }
    }
}

static DWORD WINAPI ac_isi(LPVOID arg) {
    wchar_t exe[MAX_PATH * 2];
    GetModuleFileNameW(NULL, exe, MAX_PATH * 2);
    HANDLE h = CreateFileW(exe, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_FLAG_SEQUENTIAL_SCAN, NULL);
    if (h == INVALID_HANDLE_VALUE) { g_hata = 1; wcscpy(g_hata_metni, L"Kurulum dosyası okunamadı."); goto son; }
    LARGE_INTEGER boy; GetFileSizeEx(h, &boy);
    char iz[16];
    LARGE_INTEGER pos; pos.QuadPart = boy.QuadPart - 16;
    SetFilePointerEx(h, pos, NULL, FILE_BEGIN);
    if (!oku(h, iz, 16) || memcmp(iz, "PDFPROK1", 8) != 0) { g_hata = 1; wcscpy(g_hata_metni, L"Kurulum dosyası bozuk (paket bulunamadı). Dosyayı yeniden indirin."); goto kapat; }
    uint64_t basla; memcpy(&basla, iz + 8, 8);
    pos.QuadPart = (LONGLONG)basla;
    SetFilePointerEx(h, pos, NULL, FILE_BEGIN);
    char bas[12];
    if (!oku(h, bas, 12) || memcmp(bas, "PPAK1\0\0\0", 8) != 0) { g_hata = 1; wcscpy(g_hata_metni, L"Kurulum paketi bozuk."); goto kapat; }
    uint32_t adet; memcpy(&adet, bas + 8, 4);
    g_toplam = (uint64_t)(boy.QuadPart - 16) - basla;
    for (uint32_t i = 0; i < adet; i++) {
        uint16_t ad_boy; uint64_t boyut, sboyut; uint8_t yontem;
        char ad[2048];
        if (!oku(h, &ad_boy, 2) || ad_boy >= sizeof(ad) || !oku(h, ad, ad_boy)) { g_hata = 1; break; }
        ad[ad_boy] = 0;
        if (!oku(h, &boyut, 8) || !oku(h, &sboyut, 8) || !oku(h, &yontem, 1)) { g_hata = 1; break; }
        wchar_t wad[2048];
        MultiByteToWideChar(CP_UTF8, 0, ad, -1, wad, 2048);
        for (wchar_t *p = wad; *p; p++) if (*p == L'/') *p = L'\\';
        if (wcsstr(wad, L"..")) { g_hata = 1; break; }
        wchar_t hedef[MAX_PATH * 4];
        swprintf(hedef, MAX_PATH * 4, L"%ls\\%ls", g_gecici, wad);
        klasorleri_olustur(hedef);
        unsigned char *s = (unsigned char *)HeapAlloc(GetProcessHeap(), 0, sboyut ? sboyut : 1);
        unsigned char *d = yontem ? (unsigned char *)HeapAlloc(GetProcessHeap(), 0, boyut ? boyut : 1) : s;
        if (!s || !d || !oku(h, s, (DWORD)sboyut)) { g_hata = 1; break; }
        if (yontem) {
            uLongf cikan = (uLongf)boyut;
            if (uncompress(d, &cikan, s, (uLong)sboyut) != Z_OK || cikan != boyut) { g_hata = 1; wcscpy(g_hata_metni, L"Kurulum paketi açılamadı (bozuk veri)."); break; }
        }
        HANDLE c = CreateFileW(hedef, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
        if (c == INVALID_HANDLE_VALUE) { g_hata = 1; swprintf(g_hata_metni, 512, L"Dosya yazılamadı:\n%ls", hedef); break; }
        DWORD y = 0;
        if (boyut) WriteFile(c, d, (DWORD)boyut, &y, NULL);
        CloseHandle(c);
        if (yontem) HeapFree(GetProcessHeap(), 0, d);
        HeapFree(GetProcessHeap(), 0, s);
        g_islenen += sboyut + ad_boy + 19;
    }
kapat:
    CloseHandle(h);
son:
    if (g_hata && !g_hata_metni[0]) wcscpy(g_hata_metni, L"Kurulum paketi açılamadı.");
    InterlockedExchange(&g_bitti, 1);
    PostMessageW(g_pencere, WM_APP, 0, 0);
    return 0;
}

static LRESULT CALLBACK pencere_isle(HWND w, UINT m, WPARAM a, LPARAM b) {
    switch (m) {
    case WM_TIMER: {
        int y = (int)(g_islenen * 1000 / (g_toplam ? g_toplam : 1));
        SendMessageW(g_cubuk, PBM_SETPOS, y, 0);
        return 0; }
    case WM_APP: DestroyWindow(w); return 0;
    case WM_CTLCOLORSTATIC: SetBkColor((HDC)a, RGB(255,255,255)); return (LRESULT)GetStockObject(WHITE_BRUSH);
    case WM_CLOSE: return 0;
    case WM_DESTROY: PostQuitMessage(0); return 0;
    }
    return DefWindowProcW(w, m, a, b);
}

static void klasor_sil(const wchar_t *yol) {
    wchar_t cift[MAX_PATH * 2 + 2];
    memset(cift, 0, sizeof(cift));
    wcscpy(cift, yol);
    SHFILEOPSTRUCTW op; memset(&op, 0, sizeof(op));
    op.wFunc = FO_DELETE; op.pFrom = cift;
    op.fFlags = FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT;
    SHFileOperationW(&op);
}

int WINAPI wWinMain(HINSTANCE hi, HINSTANCE hp, PWSTR cmd, int show) {
    {   typedef BOOL (WINAPI *DpiFn)(void);
        DpiFn f = (DpiFn)GetProcAddress(GetModuleHandleW(L"user32.dll"), "SetProcessDPIAware");
        if (f) f(); }
    INITCOMMONCONTROLSEX icc = {sizeof(icc), ICC_PROGRESS_CLASS};
    InitCommonControlsEx(&icc);
    wchar_t tmp[MAX_PATH];
    GetTempPathW(MAX_PATH, tmp);
    swprintf(g_gecici, MAX_PATH * 2, L"%lsPDFPRO_Kurulum_%lu", tmp, GetTickCount());
    CreateDirectoryW(g_gecici, NULL);

    WNDCLASSW wc; memset(&wc, 0, sizeof(wc));
    wc.lpfnWndProc = pencere_isle; wc.hInstance = hi; wc.lpszClassName = L"PDFPROKurulum";
    wc.hbrBackground = (HBRUSH)GetStockObject(WHITE_BRUSH);
    wc.hCursor = LoadCursor(NULL, IDC_WAIT);
    wc.hIcon = LoadIconW(hi, MAKEINTRESOURCEW(1));
    RegisterClassW(&wc);
    int W = 460, H = 150;
    int sx = (GetSystemMetrics(SM_CXSCREEN) - W) / 2, sy = (GetSystemMetrics(SM_CYSCREEN) - H) / 3;
    g_pencere = CreateWindowExW(0, wc.lpszClassName, L"PDF PRO Kurulum", WS_POPUP | WS_CAPTION | WS_VISIBLE,
                                sx, sy, W, H, NULL, NULL, hi, NULL);
    HFONT yaz = CreateFontW(-15, 0, 0, 0, FW_SEMIBOLD, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
    g_yazi = CreateWindowW(L"STATIC", L"PDF PRO kurulumu hazırlanıyor, lütfen bekleyin…", WS_CHILD | WS_VISIBLE,
                           24, 22, 400, 24, g_pencere, NULL, hi, NULL);
    SendMessageW(g_yazi, WM_SETFONT, (WPARAM)yaz, TRUE);
    g_cubuk = CreateWindowW(PROGRESS_CLASSW, NULL, WS_CHILD | WS_VISIBLE | PBS_SMOOTH, 24, 58, 400, 18, g_pencere, NULL, hi, NULL);
    SendMessageW(g_cubuk, PBM_SETRANGE32, 0, 1000);
    SetTimer(g_pencere, 1, 100, NULL);
    CreateThread(NULL, 0, ac_isi, NULL, 0, NULL);
    MSG m;
    while (GetMessageW(&m, NULL, 0, 0) > 0) { TranslateMessage(&m); DispatchMessageW(&m); }

    int sonuc = 0;
    if (g_hata) {
        MessageBoxW(NULL, g_hata_metni, L"PDF PRO Kurulum", MB_ICONERROR);
        sonuc = 1;
    } else {
        wchar_t py[MAX_PATH * 2], betik[MAX_PATH * 2], komut[MAX_PATH * 6];
        swprintf(py, MAX_PATH * 2, L"%ls\\runtime\\pythonw.exe", g_gecici);
        swprintf(betik, MAX_PATH * 2, L"%ls\\app\\kurulum\\kurulum.pyw", g_gecici);
        swprintf(komut, MAX_PATH * 6, L"\"%ls\" \"%ls\" --kaynak \"%ls\"", py, betik, g_gecici);
        SetEnvironmentVariableW(L"PYTHONHOME", NULL);
        SetEnvironmentVariableW(L"PYTHONPATH", NULL);
        STARTUPINFOW si; PROCESS_INFORMATION pi;
        memset(&si, 0, sizeof(si)); si.cb = sizeof(si); memset(&pi, 0, sizeof(pi));
        if (CreateProcessW(py, komut, NULL, NULL, FALSE, 0, NULL, g_gecici, &si, &pi)) {
            AllowSetForegroundWindow(pi.dwProcessId);
            WaitForSingleObject(pi.hProcess, INFINITE);
            DWORD kod = 0; GetExitCodeProcess(pi.hProcess, &kod);
            CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
            sonuc = (int)kod;
        } else {
            wchar_t mm[600];
            swprintf(mm, 600, L"Kurulum sihirbazı başlatılamadı (hata %lu).", GetLastError());
            MessageBoxW(NULL, mm, L"PDF PRO Kurulum", MB_ICONERROR);
            sonuc = 1;
        }
    }
    klasor_sil(g_gecici);
    return sonuc;
}
