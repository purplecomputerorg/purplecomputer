/* Static reboot binary for post-install restart.
 *
 * Compiled statically (zero shared lib dependencies) during golden image
 * build. install.sh copies it to a dedicated tmpfs mount with setuid root.
 *
 * With --wait: clears screen, shows success message, waits for Enter, reboots.
 * Without: reboots immediately.
 *
 * Before reboot(2) it kills Xorg and waits for it to actually die. Raw
 * reboot with X holding a live hardware-GL context can wedge some GPUs'
 * kernel shutdown path into a black screen that never POSTs (seen on
 * i915 Surface). systemd reboots never hit this because the X unit is
 * stopped first; this mirrors that.
 *
 * This binary is the ONLY thing that reliably runs after USB removal.
 * /bin/sh, Python, sudo all SIGBUS because their code pages fault on the
 * dead overlayfs. This binary is fully on tmpfs and statically linked.
 *
 * If reboot fails (setuid issue, security module, etc.), falls back through:
 *   1. Retry reboot() syscall
 *   2. sysrq 'b' (hard reboot via /proc/sysrq-trigger)
 *   3. Switch to tty2 with troubleshooting message
 */
#include <sys/reboot.h>
#include <sys/ioctl.h>
#include <linux/vt.h>
#include <unistd.h>
#include <string.h>
#include <signal.h>
#include <fcntl.h>

/* Test hooks: when TESTING is defined, these are provided by the test harness.
 * In production, they're just the real syscalls. */
#ifdef TESTING
extern int  test_reboot(int cmd);
extern void test_sync(void);
extern int  test_open(const char *path, int flags);
extern int  test_close(int fd);
extern int  test_ioctl(int fd, unsigned long req, int arg);
extern ssize_t test_write(int fd, const void *buf, size_t len);
extern ssize_t test_read(int fd, void *buf, size_t len);
extern unsigned int test_sleep(unsigned int sec);
extern void test_pause(void);
extern void test_signal(int sig, void (*handler)(int));
extern void test_alarm(unsigned int sec);
extern int  test_find_xorg(void);
extern int  test_kill(int pid, int sig);
extern void test_msleep(void);
#define pr_reboot(cmd)         test_reboot(cmd)
#define pr_sync()              test_sync()
#define pr_open(p, f)          test_open(p, f)
#define pr_close(fd)           test_close(fd)
#define pr_ioctl(fd, req, arg) test_ioctl(fd, req, arg)
#define pr_write(fd, buf, len) test_write(fd, buf, len)
#define pr_read(fd, buf, len)  test_read(fd, buf, len)
#define pr_sleep(s)            test_sleep(s)
#define pr_pause()             test_pause()
#define pr_signal(s, h)        test_signal(s, h)
#define pr_alarm(s)            test_alarm(s)
#define pr_find_xorg()         test_find_xorg()
#define pr_kill(p, s)          test_kill(p, s)
#define pr_msleep()            test_msleep()
#else
#define pr_reboot(cmd)         reboot(cmd)
#define pr_sync()              sync()
#define pr_open(p, f)          open(p, f)
#define pr_close(fd)           close(fd)
#define pr_ioctl(fd, req, arg) ioctl(fd, req, arg)
#define pr_write(fd, buf, len) write(fd, buf, len)
#define pr_read(fd, buf, len)  read(fd, buf, len)
#define pr_sleep(s)            sleep(s)
#define pr_pause()             pause()
#define pr_signal(s, h)        signal(s, h)
#define pr_alarm(s)            alarm(s)
#define pr_kill(p, s)          kill(p, s)

#include <dirent.h>
#include <stdlib.h>
#include <time.h>

static int pr_find_xorg(void) {
    DIR *d = opendir("/proc");
    struct dirent *e;
    int found = -1;
    if (!d)
        return -1;
    while (found < 0 && (e = readdir(d)) != NULL) {
        if (e->d_name[0] < '1' || e->d_name[0] > '9')
            continue;
        char path[300] = "/proc/";
        char comm[16] = {0};
        strcat(path, e->d_name);
        strcat(path, "/comm");
        int fd = open(path, O_RDONLY);
        if (fd < 0)
            continue;
        ssize_t n = read(fd, comm, sizeof(comm) - 1);
        close(fd);
        if (n > 0 && comm[n - 1] == '\n')
            comm[n - 1] = '\0';
        if (strcmp(comm, "Xorg") == 0)
            found = atoi(e->d_name);
    }
    closedir(d);
    return found;
}

static void pr_msleep(void) {
    struct timespec ts = {0, 100 * 1000 * 1000};
    nanosleep(&ts, NULL);
}
#endif

static volatile int timed_out = 0;

static void alarm_handler(int sig) {
    (void)sig;
    timed_out = 1;
}

/* Messages (shared between production code and tests) */
static const char WAIT_MSG[] =
    "\033[?1049l\033[2J\033[H"
    "\n"
    "  All done!\n"
    "\n"
    "  Purple Computer is installed.\n"
    "  You can remove the USB drive now.\n"
    "\n"
    "  Press Enter to restart.\n"
    "\n"
    "  If nothing happens, hold the power button down\n"
    "  for about ten seconds, until the screen turns\n"
    "  off. Then press it once to start up again.\n"
    "\n";

static const char FAIL_MSG[] =
    "\033[2J\033[H"  /* clear screen, cursor home */
    "\n"
    "  Purple Computer was installed successfully,\n"
    "  but automatic restart did not work on this computer.\n"
    "\n"
    "  Please hold the power button down for about\n"
    "  ten seconds, until the screen turns off.\n"
    "  Then press it once to start up again.\n"
    "\n"
    "  If you need help: support@purplecomputer.org\n"
    "\n";

/* Alive means still holding resources. A zombie has already released its
 * DRM master, so it counts as dead: kill(pid, 0) would say alive and stall
 * the whole poll window when a wedged parent (USB removal) can't reap. */
static int xorg_alive(int pid) {
    char path[40] = "/proc/";
    char digits[12];
    char buf[128];
    int len = 6, n = 0;

    for (int v = pid; v > 0; v /= 10)
        digits[n++] = (char)('0' + v % 10);
    while (n > 0)
        path[len++] = digits[--n];
    strcpy(path + len, "/stat");

    int fd = pr_open(path, O_RDONLY);
    if (fd < 0)
        return 0;
    ssize_t r = pr_read(fd, buf, sizeof(buf) - 1);
    pr_close(fd);
    if (r <= 0)
        return 0;
    buf[r] = '\0';
    char *p = strrchr(buf, ')');  /* state field follows "(comm) " */
    return !(p && p[1] == ' ' && p[2] == 'Z');
}

/* Kill Xorg and wait for real process death (DRM master released) before
 * reboot(2), so the GPU driver is not mid-render during kernel shutdown.
 * Deterministic poll, not a fixed sleep; bounded at ~7s, then reboot
 * proceeds regardless. No X found means nothing to do. */
static void stop_xorg(void) {
    int pid = pr_find_xorg();
    if (pid <= 0)
        return;
    pr_kill(pid, SIGTERM);
    for (int i = 0; i < 50 && xorg_alive(pid); i++)
        pr_msleep();
    if (xorg_alive(pid)) {
        pr_kill(pid, SIGKILL);
        for (int i = 0; i < 10 && xorg_alive(pid); i++)
            pr_msleep();
    }
    pr_sleep(1);  /* let the driver finish DRM teardown */
}

/* Try sysrq 'b' (immediate hard reboot, no sync). */
static void try_sysrq_reboot(void) {
    int fd;

    /* Enable sysrq first */
    fd = pr_open("/proc/sys/kernel/sysrq", O_WRONLY);
    if (fd >= 0) {
        pr_write(fd, "1", 1);
        pr_close(fd);
    }

    fd = pr_open("/proc/sysrq-trigger", O_WRONLY);
    if (fd >= 0) {
        pr_write(fd, "b", 1);
        pr_close(fd);
    }
}

/* Show reboot-failed message via every available channel.
 *
 * The user might be looking at:
 *   (a) Alacritty on tty1 (X11) — if it's still alive, stdout works
 *   (b) The X11 root window (purple) — if Alacritty died
 *   (c) A text VT — unlikely but possible
 *
 * Strategy: write to stdout first (covers case a, the most common),
 * then try to switch to tty2 and write there (covers case b).
 * SIGPIPE is already ignored so stdout writes are safe even if
 * Alacritty is dead. */
static void show_reboot_failed(void) {
    int fd;

    /* 1. Write to stdout (Alacritty PTY, if still alive).
     *    This is the most likely way the user will see the message:
     *    they just pressed Enter, Alacritty is probably still up. */
    pr_write(STDOUT_FILENO, FAIL_MSG, strlen(FAIL_MSG));

    /* 2. Try to switch to tty2 and write there too.
     *    If stdout failed (Alacritty dead), this is the fallback.
     *    Try multiple device paths for the VT switch ioctl. */
    int switched = 0;
    static const char *console_paths[] = {
        "/dev/console", "/dev/tty0", "/dev/tty", NULL
    };
    for (const char **p = console_paths; *p && !switched; p++) {
        fd = pr_open(*p, O_RDWR);
        if (fd >= 0) {
            if (pr_ioctl(fd, VT_ACTIVATE, 2) == 0)
                switched = 1;
            pr_ioctl(fd, VT_WAITACTIVE, 2);
            pr_close(fd);
        }
    }

    /* Write message to tty2 regardless of whether VT switch worked.
     * If we switched, user sees it. If not, it's there for when they
     * eventually get to tty2 (e.g., via SSH or hardware reset). */
    fd = pr_open("/dev/tty2", O_WRONLY);
    if (fd >= 0) {
        pr_write(fd, FAIL_MSG, strlen(FAIL_MSG));
        pr_close(fd);
    }

    /* Stay alive so the message remains visible.
     * The user will power-cycle manually. */
    for (;;)
        pr_pause();
}

#ifndef TESTING
int main(int argc, char **argv) {
#else
int purple_reboot_main(int argc, char **argv) {
#endif
    timed_out = 0;

    /* Ignore terminal signals. After execv from the Python app, the evdev
     * grab is released and keypresses flow through X → Alacritty → pty.
     * Without these, USB removal kills us: Alacritty SIGBUSes on dead
     * overlayfs → pty master closes → kernel sends SIGHUP → we die before
     * reaching reboot(). Ctrl+\ (SIGQUIT) and Ctrl+C (SIGINT) from the
     * pty would also kill us. */
    pr_signal(SIGHUP, SIG_IGN);
    pr_signal(SIGPIPE, SIG_IGN);
    pr_signal(SIGQUIT, SIG_IGN);
    pr_signal(SIGINT, SIG_IGN);
    pr_signal(SIGTSTP, SIG_IGN);

    if (argc > 1 && strcmp(argv[1], "--wait") == 0) {
        pr_write(STDOUT_FILENO, WAIT_MSG, strlen(WAIT_MSG));

        /* Safety net: reboot after 15 min if nothing else triggers it.
         * Normally read() returns on Enter or EOF (pty dies from USB removal). */
        pr_signal(SIGALRM, alarm_handler);
        pr_alarm(900);

        char c;
        while (!timed_out) {
            int n = pr_read(STDIN_FILENO, &c, 1);
            if (n <= 0 || c == '\n')
                break;
        }
    }

    stop_xorg();
    pr_sync();
    pr_reboot(RB_AUTOBOOT);

    /* reboot() should never return on success.
     * If we're here, something went wrong. Try harder. Kill X again first:
     * purple-x11.service (Restart=on-failure, RestartSec=2) may have
     * respawned it with a fresh GL context during the failed attempt. */
    pr_sleep(1);
    stop_xorg();
    pr_sync();
    pr_reboot(RB_AUTOBOOT);

    /* Still alive: try sysrq hard reboot */
    pr_sleep(1);
    try_sysrq_reboot();

    /* Still alive: give up on reboot, show manual instructions */
    pr_sleep(2);
    show_reboot_failed();

    return 1;
}
