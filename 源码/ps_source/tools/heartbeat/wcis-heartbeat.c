#define _POSIX_C_SOURCE 200809L
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define LOGDIR "/var/log/wcis-heartbeat"
#define LOGFILE LOGDIR "/heartbeat.log"
#define MAX_BYTES (1024 * 1024)
static volatile sig_atomic_t stopping;
static void stop_handler(int sig) { (void)sig; stopping = 1; }
static int read_text(const char *path, char *buf, size_t size) {
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    size_t n = fread(buf, 1, size - 1, f);
    buf[n] = 0;
    fclose(f);
    return n ? 0 : -1;
}
static long memory_kb(const char *buf, const char *key) {
    size_t n = strlen(key);
    const char *p = buf;
    while (p && *p) {
        if (!strncmp(p, key, n) && p[n] == ':') return strtol(p+n+1, NULL, 10);
        p = strchr(p, '\n');
        if (p) ++p;
    }
    return -1;
}
static int proc_stat(char *buf, char *comm, char *state, long *rss) {
    char *l = strchr(buf, '('), *r = strrchr(buf, ')');
    if (!l || !r || r <= l) return -1;
    size_t n = (size_t)(r-l-1);
    if (n > 63) n = 63;
    memcpy(comm, l+1, n); comm[n] = 0;
    /* Fields after ')' start at field 3 (state); RSS is field 24. */
    char *save = NULL, *t = strtok_r(r+1, " \n", &save);
    for (int field = 3; t; ++field, t = strtok_r(NULL, " \n", &save)) {
        if (field == 3) *state = *t;
        if (field == 24) { *rss = strtol(t, NULL, 10); return 0; }
    }
    return -1;
}
static int open_log(void) {
    int fd = open(LOGFILE, O_WRONLY|O_CREAT|O_APPEND|O_CLOEXEC|O_NOFOLLOW, 0640);
    if (fd < 0) perror("open heartbeat log");
    return fd;
}
static int rotate(int fd) {
    struct stat st;
    if (fstat(fd, &st) || st.st_size < MAX_BYTES) return fd;
    if (fdatasync(fd)) return -1;
    close(fd);
    if (rename(LOGFILE ".1", LOGFILE ".2") && errno != ENOENT) return -1;
    if (rename(LOGFILE, LOGFILE ".1")) return -1;
    return open_log();
}
static int sample(int fd, const char *boot_id) {
    char mem[8192], uptime[128], load[128];
    if (read_text("/proc/meminfo", mem, sizeof(mem)) ||
        read_text("/proc/uptime", uptime, sizeof(uptime)) ||
        read_text("/proc/loadavg", load, sizeof(load))) return -1;
    long dcount = 0, top_rss = 0; int top_pid = 0;
    char top_comm[64] = "-", targets[1024] = "";
    DIR *dir = opendir("/proc");
    if (!dir) return -1;
    struct dirent *entry;
    while ((entry = readdir(dir))) {
        char *end; long pid = strtol(entry->d_name, &end, 10);
        if (*end || pid <= 0) continue;
        char path[80], buf[2048], comm[64], state = '?'; long rss = 0;
        snprintf(path, sizeof(path), "/proc/%ld/stat", pid);
        if (read_text(path, buf, sizeof(buf)) || proc_stat(buf, comm, &state, &rss)) continue;
        rss = rss * sysconf(_SC_PAGESIZE) / 1024;
        if (rss > top_rss) { top_rss = rss; top_pid = (int)pid; strcpy(top_comm, comm); }
        if (state == 'D') ++dcount;
        if (state == 'D' || !strncmp(comm, "wcis_sdi", 8) || !strncmp(comm, "sdicamera", 9)) {
            char wchan[96] = "?"; size_t used = strlen(targets);
            snprintf(path, sizeof(path), "/proc/%ld/wchan", pid);
            if (read_text(path, wchan, sizeof(wchan))) strcpy(wchan, "?");
            wchan[strcspn(wchan, "\n")] = 0;
            if (used < sizeof(targets)-128)
                snprintf(targets+used, sizeof(targets)-used, "%ld/%s/%c/%ldkB/%s,", pid, comm, state, rss, wchan);
        }
    }
    closedir(dir);
    time_t now = time(NULL); struct tm utc; char ts[40];
    gmtime_r(&now, &utc); strftime(ts, sizeof(ts), "%Y-%m-%dT%H:%M:%SZ", &utc);
    double up = strtod(uptime, NULL), load1 = strtod(load, NULL);
    return dprintf(fd, "ts=%s boot=%s uptime=%.2f load1=%.2f avail_kb=%ld swapfree_kb=%ld cmafree_kb=%ld dstate=%ld top=%d/%s/%ldkB targets=%s\n",
        ts, boot_id, up, load1, memory_kb(mem,"MemAvailable"), memory_kb(mem,"SwapFree"),
        memory_kb(mem,"CmaFree"), dcount, top_pid, top_comm, top_rss, *targets ? targets : "-") < 0 ? -1 : 0;
}
int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--self-test")) {
        char line[] = "9 (name with ) paren) D 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23000 24 25";
        char comm[64], state = '?'; long rss = 0;
        if (proc_stat(line, comm, &state, &rss) || rss != 24 || state != 'D' ||
            strcmp(comm, "name with ) paren") || memory_kb("X: 12\nMemAvailable: 456 kB\n", "MemAvailable") != 456) return 1;
        puts("PASS proc-stat field parsing and memory units"); return 0;
    }
    if (argc != 1) { fputs("Usage: wcis-heartbeat [--self-test]\n", stderr); return 2; }
    char boot_id[80];
    if (read_text("/proc/sys/kernel/random/boot_id", boot_id, sizeof(boot_id))) return 1;
    boot_id[strcspn(boot_id, "\n")] = 0;
    signal(SIGTERM, stop_handler); signal(SIGINT, stop_handler);
    int fd = open_log(); if (fd < 0) return 1;
    int kmsg = open("/dev/kmsg", O_RDONLY|O_NONBLOCK|O_CLOEXEC);
    if (kmsg >= 0) lseek(kmsg, 0, SEEK_END);
    dprintf(fd, "event=start boot=%s interval_s=10 kernel_capture=%s\n", boot_id, kmsg >= 0 ? "enabled" : "unavailable");
    while (!stopping) {
        fd = rotate(fd);
        if (fd < 0 || sample(fd, boot_id)) return 1;
        if (kmsg >= 0) for (int n = 0; n < 32; ++n) {
            char buf[4096]; ssize_t got = read(kmsg, buf, sizeof(buf)-1);
            if (got < 0 && errno == EPIPE) { dprintf(fd, "kernel_event=ring_overrun boot=%s\n", boot_id); continue; }
            if (got <= 0) break;
            buf[got] = 0; dprintf(fd, "kernel boot=%s %s", boot_id, buf);
        }
        if (fdatasync(fd)) { perror("sync heartbeat log"); return 1; }
        struct timespec remaining = {10, 0};
        while (!stopping && nanosleep(&remaining, &remaining) && errno == EINTR) {}
    }
    dprintf(fd, "event=stop boot=%s\n", boot_id); fdatasync(fd); close(fd);
    if (kmsg >= 0) close(kmsg);
    return 0;
}
