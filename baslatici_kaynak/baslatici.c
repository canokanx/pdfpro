// PDF PRO baslatici.
// Python'u (python3XX.dll) bu EXE'nin icine yukler; boylece Gorev Yoneticisi'nde, gorev cubugunda ve
// "Birlikte ac" listesinde "PDF PRO" adi ve simgesi gorunur. Yukleyemezse eski yolla pythonw'yu calistirir.
#ifndef UNICODE
#define UNICODE
#endif
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>

typedef int (*PyMainFn)(int, wchar_t **);

static void kirp(wchar_t *s) {
    size_t n = wcslen(s);
    while (n && (s[n-1] == L'\r' || s[n-1] == L'\n' || s[n-1] == L' ' || s[n-1] == L'\t' || s[n-1] == L'"')) s[--n] = 0;
    wchar_t *b = s;
    while (*b == 0xFEFF || *b == L' ' || *b == L'"') b++;
    if (b != s) memmove(s, b, (wcslen(b) + 1) * sizeof(wchar_t));
}

static int dosya_oku(const wchar_t *yol, wchar_t *cikti, int boy) {
    HANDLE h = CreateFileW(yol, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE) return 0;
    char tampon[4096]; DWORD okunan = 0;
    BOOL ok = ReadFile(h, tampon, sizeof(tampon) - 1, &okunan, NULL);
    CloseHandle(h);
    if (!ok || !okunan) return 0;
    tampon[okunan] = 0;
    if (MultiByteToWideChar(CP_UTF8, 0, tampon, -1, cikti, boy) <= 0) return 0;
    kirp(cikti);
    return GetFileAttributesW(cikti) != INVALID_FILE_ATTRIBUTES;
}

// pythonw yolunu bul (python_yolu.txt > PATH)
static int python_bul(const wchar_t *klasor, wchar_t *py, wchar_t *ek) {
    wchar_t ayar[MAX_PATH * 2];
    swprintf(ayar, MAX_PATH * 2, L"%ls\\python_yolu.txt", klasor);
    ek[0] = 0;
    if (dosya_oku(ayar, py, MAX_PATH * 2)) return 1;
    py[0] = 0;
    if (SearchPathW(NULL, L"pythonw.exe", NULL, MAX_PATH * 2, py, NULL)) return 1;
    if (SearchPathW(NULL, L"pyw.exe", NULL, MAX_PATH * 2, py, NULL)) { wcscpy(ek, L"-3 "); return 2; }
    return 0;
}

// Python'u bu surecin icinde calistir. Basarisizsa -1.
static int gomulu_calistir(const wchar_t *py, const wchar_t *betik) {
    wchar_t pydir[MAX_PATH * 2];
    wcscpy(pydir, py);
    wchar_t *s = wcsrchr(pydir, L'\\');
    if (!s) return -1;
    *s = 0;

    // standart Python kurulumu mu? (degilse eski yolla calistir)
    wchar_t kontrol[MAX_PATH * 2];
    swprintf(kontrol, MAX_PATH * 2, L"%ls\\Lib\\encodings\\__init__.py", pydir);
    if (GetFileAttributesW(kontrol) == INVALID_FILE_ATTRIBUTES) return -1;
    swprintf(kontrol, MAX_PATH * 2, L"%ls\\Lib\\os.py", pydir);
    if (GetFileAttributesW(kontrol) == INVALID_FILE_ATTRIBUTES) return -1;

    // python3XX.dll (python3.dll degil)
    wchar_t desen[MAX_PATH * 2], dll[MAX_PATH * 2] = L"";
    swprintf(desen, MAX_PATH * 2, L"%ls\\python3*.dll", pydir);
    WIN32_FIND_DATAW fd;
    HANDLE f = FindFirstFileW(desen, &fd);
    if (f == INVALID_HANDLE_VALUE) return -1;
    size_t en = 0;
    do {
        size_t n = wcslen(fd.cFileName);
        if (n > en && _wcsicmp(fd.cFileName, L"python3.dll") != 0) {
            en = n;
            swprintf(dll, MAX_PATH * 2, L"%ls\\%ls", pydir, fd.cFileName);
        }
    } while (FindNextFileW(f, &fd));
    FindClose(f);
    if (!dll[0]) return -1;

    SetDllDirectoryW(pydir);
    HMODULE k32 = GetModuleHandleW(L"kernel32.dll");
    typedef void *(WINAPI *AddDirFn)(PCWSTR);
    AddDirFn add = (AddDirFn)GetProcAddress(k32, "AddDllDirectory");
    if (add) add(pydir);
    HMODULE h = LoadLibraryExW(dll, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!h) return -1;
    PyMainFn py_main = (PyMainFn)GetProcAddress(h, "Py_Main");
    if (!py_main) return -1;

    SetEnvironmentVariableW(L"PYTHONHOME", pydir);
    SetEnvironmentVariableW(L"PDFPRO_PYTHONW", py);
    SetEnvironmentVariableW(L"PDFPRO_GOMULU", L"1");

    int argc = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    wchar_t **yeni = (wchar_t **)HeapAlloc(GetProcessHeap(), 0, (argc + 3) * sizeof(wchar_t *));
    int n = 0;
    yeni[n++] = argv ? argv[0] : (wchar_t *)L"PDF_PRO.exe";
    yeni[n++] = (wchar_t *)betik;
    for (int i = 1; argv && i < argc; i++) yeni[n++] = argv[i];
    yeni[n] = NULL;
    return py_main(n, yeni);
}

static int ayri_surecte_calistir(const wchar_t *py, const wchar_t *ek, const wchar_t *betik, const wchar_t *klasor) {
    wchar_t *satir = GetCommandLineW();
    if (*satir == L'"') { satir++; while (*satir && *satir != L'"') satir++; if (*satir) satir++; }
    else { while (*satir && *satir != L' ' && *satir != L'\t') satir++; }
    while (*satir == L' ' || *satir == L'\t') satir++;
    size_t boy = wcslen(py) + wcslen(betik) + wcslen(satir) + 64;
    wchar_t *komut = (wchar_t *)HeapAlloc(GetProcessHeap(), 0, boy * sizeof(wchar_t));
    swprintf(komut, boy, L"\"%ls\" %ls\"%ls\" %ls", py, ek, betik, satir);
    SetEnvironmentVariableW(L"PDFPRO_AYRI_SUREC", L"1");   // PDF_PRO.pyw tekrar EXE'ye yonlendirmesin
    STARTUPINFOW si; PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si)); si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));
    if (!CreateProcessW(py, komut, NULL, NULL, FALSE, 0, NULL, klasor, &si, &pi)) {
        wchar_t m[1024];
        swprintf(m, 1024, L"PDF PRO başlatılamadı (hata %lu).\n\n%ls", GetLastError(), py);
        MessageBoxW(NULL, m, L"PDF PRO", MB_ICONERROR);
        return 1;
    }
    AllowSetForegroundWindow(pi.dwProcessId);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}

int WINAPI wWinMain(HINSTANCE hi, HINSTANCE hp, PWSTR cmd, int show) {
    wchar_t klasor[MAX_PATH * 2];
    GetModuleFileNameW(NULL, klasor, MAX_PATH * 2);
    wchar_t *son = wcsrchr(klasor, L'\\');
    if (son) *son = 0;
    SetCurrentDirectoryW(klasor);
    {   // gorev cubugu kimligi (Python degil PDF PRO)
        typedef HRESULT (WINAPI *AumFn)(PCWSTR);
        HMODULE sh = LoadLibraryW(L"shell32.dll");
        AumFn aum = sh ? (AumFn)GetProcAddress(sh, "SetCurrentProcessExplicitAppUserModelID") : NULL;
        if (aum) aum(L"IRONHULL.PDFPRO");
    }

    wchar_t betik[MAX_PATH * 2];
    swprintf(betik, MAX_PATH * 2, L"%ls\\PDF_PRO.pyw", klasor);
    wchar_t py[MAX_PATH * 2], ek[8];
    int bulundu = python_bul(klasor, py, ek);
    if (!bulundu) {
        MessageBoxW(NULL, L"Python bulunamadı.\n\nPDF PRO klasöründeki KURULUM.bat dosyasını bir kez çalıştırın.",
                    L"PDF PRO", MB_ICONERROR);
        return 1;
    }
    wchar_t ortam[8] = L"";
    GetEnvironmentVariableW(L"PDFPRO_AYRI_SUREC", ortam, 8);
    // guvenlik: onceki gomulu deneme hic basarili olmadiysa (Python acilista coktuyse) eski yolu kullan
    wchar_t deneme[MAX_PATH * 2], ok[MAX_PATH * 2];
    swprintf(deneme, MAX_PATH * 2, L"%ls\\gomulu_deneme.txt", klasor);
    swprintf(ok, MAX_PATH * 2, L"%ls\\gomulu_ok.txt", klasor);
    int onceki_basarisiz = GetFileAttributesW(deneme) != INVALID_FILE_ATTRIBUTES &&
                           GetFileAttributesW(ok) == INVALID_FILE_ATTRIBUTES;
    if (bulundu == 1 && ortam[0] != L'1' && !onceki_basarisiz) {
        HANDLE h = CreateFileW(deneme, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
        if (h != INVALID_HANDLE_VALUE) CloseHandle(h);
        int r = gomulu_calistir(py, betik);
        if (r != -1) return r;
    }
    return ayri_surecte_calistir(py, ek, betik, klasor);
}
