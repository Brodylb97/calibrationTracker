/*
 * RestartHelper.exe - Stub that reopens Calibration Tracker after an update.
 *
 * Usage:
 *   RestartHelper.exe <exe_path> [<db_path>]  - use these paths (preferred; avoids APPDATA when updater is elevated)
 *   RestartHelper.exe [params_file_path]      - read exe path and db path from file (default: %APPDATA%\CalibrationTracker\restart_params.txt)
 *
 * Build (MinGW): gcc -O2 -o RestartHelper.exe restart_helper.c -mwindows
 * Build (MSVC):  cl /O2 restart_helper.c /link /SUBSYSTEM:WINDOWS /OUT:RestartHelper.exe
 * For a console stub (useful when debugging), omit -mwindows / /SUBSYSTEM:WINDOWS.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PARAMS_BUF_SIZE 2048
#define CMD_BUF_SIZE    4096

static void trim_crlf(char* s) {
    for (; *s; s++)
        if (*s == '\r' || *s == '\n') { *s = '\0'; break; }
}

static const char* default_params_path(char* buf, size_t bufsiz) {
    const char* apd = getenv("APPDATA");
    if (!apd || bufsiz < 32) return NULL;
    snprintf(buf, (int)bufsiz, "%s\\CalibrationTracker\\restart_params.txt", apd);
    return buf;
}

static char* dirname_inplace(char* path) {
    char* last = NULL;
    for (char* p = path; *p; p++) {
        if (*p == '/' || *p == '\\') last = p;
    }
    if (last) { *last = '\0'; return path; }
    return path;
}

int main(int argc, char** argv) {
    char exe_path[PARAMS_BUF_SIZE];
    char db_path[PARAMS_BUF_SIZE];
    exe_path[0] = '\0';
    db_path[0] = '\0';

    /* Prefer explicit args from updater (avoids APPDATA mismatch when updater runs elevated). */
    if (argc >= 2) {
        strncpy(exe_path, argv[1], sizeof exe_path - 1);
        exe_path[sizeof exe_path - 1] = '\0';
        if (argc >= 3) {
            strncpy(db_path, argv[2], sizeof db_path - 1);
            db_path[sizeof db_path - 1] = '\0';
        }
    }

    /* If not enough args, read from params file. */
    if (!exe_path[0]) {
        char params_path_buf[MAX_PATH];
        const char* param_path = (argc >= 2) ? argv[1] : default_params_path(params_path_buf, sizeof params_path_buf);
        if (!param_path) return 1;

        FILE* f = fopen(param_path, "r");
        if (!f) return 1;

        if (!fgets(exe_path, (int)sizeof exe_path, f)) { fclose(f); return 1; }
        if (!fgets(db_path, (int)sizeof db_path, f)) { fclose(f); return 1; }
        fclose(f);

        trim_crlf(exe_path);
        trim_crlf(db_path);
    }

    if (!exe_path[0]) return 1;

    char work_dir[MAX_PATH];
    strncpy(work_dir, exe_path, sizeof work_dir - 1);
    work_dir[sizeof work_dir - 1] = '\0';
    dirname_inplace(work_dir);

    /* cmdline = "exepath" [--db "dbpath"] (quoted so spaces are safe; omit --db if db_path empty) */
    char cmdline[CMD_BUF_SIZE];
    if (db_path[0])
        snprintf(cmdline, sizeof cmdline, "\"%s\" --db \"%s\"", exe_path, db_path);
    else
        snprintf(cmdline, sizeof cmdline, "\"%s\"", exe_path);

    STARTUPINFOA si = { sizeof(si) };
    PROCESS_INFORMATION pi = { 0 };

    if (!CreateProcessA(
            exe_path,           /* lpApplicationName */
            cmdline,            /* lpCommandLine (must be writable; CreateProcess can mutate it) */
            NULL, NULL, FALSE,
            CREATE_NO_WINDOW,   /* dwCreationFlags – no console flash */
            NULL,               /* lpEnvironment – NULL = inherit */
            work_dir[0] ? work_dir : NULL,  /* lpCurrentDirectory */
            &si, &pi)) {
        return 1;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
