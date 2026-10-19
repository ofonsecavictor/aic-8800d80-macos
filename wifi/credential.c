/* Root-only PMK storage. The system keychain rejects writes from this
 * non-interactive daemon on this macOS installation, so use a root-owned,
 * mode-0600 local store. Only the derived 32-byte WPA2 key is persisted. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define STORE_DIR "/Library/Application Support/AIC88M80Driver/wifi/credentials"

static void clear_secret(void *bytes, size_t size) {
    volatile unsigned char *p = bytes;
    while (size--) *p++ = 0;
}

static int path_for_ssid(const char *ssid, char *path, size_t path_size) {
    static const char digits[] = "0123456789abcdef";
    char encoded[65];
    size_t length = strlen(ssid);
    if (length < 1 || length > 32) return -1;
    for (size_t i = 0; i < length; ++i) {
        unsigned char byte = (unsigned char)ssid[i];
        encoded[i * 2] = digits[byte >> 4];
        encoded[i * 2 + 1] = digits[byte & 15];
    }
    encoded[length * 2] = '\0';
    return snprintf(path, path_size, "%s/%s", STORE_DIR, encoded) >= (int)path_size ? -1 : 0;
}

static int ensure_store(void) {
    if (mkdir(STORE_DIR, 0700) && errno != EEXIST) return -1;
    struct stat info;
    if (lstat(STORE_DIR, &info) || !S_ISDIR(info.st_mode) || info.st_uid != 0) return -1;
    return chmod(STORE_DIR, 0700);
}

static int read_key(const char *path, unsigned char key[32]) {
    struct stat info;
    int fd = open(path, O_RDONLY | O_NOFOLLOW);
    if (fd < 0) return -1;
    int ok = !fstat(fd, &info) && S_ISREG(info.st_mode) && info.st_uid == 0 &&
        (info.st_mode & 077) == 0 && read(fd, key, 32) == 32 && read(fd, key, 1) == 0;
    close(fd);
    if (!ok) { clear_secret(key, 32); errno = EIO; return -1; }
    return 0;
}

static int write_key(const char *path, const unsigned char key[32]) {
    char temporary[512];
    if (snprintf(temporary, sizeof(temporary), "%s.tmp.%ld", path, (long)getpid()) >= (int)sizeof(temporary)) return -1;
    int fd = open(temporary, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
    if (fd < 0) return -1;
    int written = write(fd, key, 32) == 32;
    int synced = written && fsync(fd) == 0;
    int closed = close(fd) == 0;
    int ok = synced && closed && rename(temporary, path) == 0;
    if (!ok) { int saved = errno; unlink(temporary); errno = saved; return -1; }
    return 0;
}

int main(int argc, char **argv) {
    unsigned char key[32] = {0};
    char path[448];
    if (geteuid() != 0 || argc != 3 || path_for_ssid(argv[2], path, sizeof(path)) ||
        (strcmp(argv[1], "--store") && strcmp(argv[1], "--read") && strcmp(argv[1], "--delete"))) {
        fputs("Root, mode and valid SSID required.\n", stderr);
        return 2;
    }
    if (ensure_store()) { perror("AIC credential store"); return 1; }
    if (!strcmp(argv[1], "--store")) {
        size_t total = 0;
        while (total < sizeof(key)) { ssize_t n = read(STDIN_FILENO, key + total, sizeof(key) - total); if (n <= 0) break; total += (size_t)n; }
        if (total != sizeof(key) || write_key(path, key)) { clear_secret(key, sizeof(key)); perror("AIC credential store"); return 1; }
    } else if (!strcmp(argv[1], "--read")) {
        if (read_key(path, key) || fwrite(key, 1, sizeof(key), stdout) != sizeof(key)) { clear_secret(key, sizeof(key)); return 1; }
    } else if (unlink(path) && errno != ENOENT) {
        perror("AIC credential store"); return 1;
    }
    clear_secret(key, sizeof(key));
    return 0;
}
