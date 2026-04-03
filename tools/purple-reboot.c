/* Static reboot binary for post-install restart.
 *
 * Compiled statically (zero shared lib dependencies) during golden image
 * build. install.sh copies it to a dedicated tmpfs mount with setuid root.
 *
 * With --wait: clears screen, shows success message, waits for Enter, reboots.
 * Without: reboots immediately.
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
    "\n";

static const char TTY2_MSG[] =
    "\033[2J\033[H"  /* clear screen, cursor home */
    "\n"
    "  Purple Computer was installed successfully,\n"
    "  but automatic restart did not work on this computer.\n"
    "\n"
    "  Please hold the power button to turn off,\n"
    "  then turn it back on.\n"
    "\n"
    "  If you need help: support@purplecomputer.org\n"
    "\n";

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

/* Switch to tty2 and print a troubleshooting message.
 * This is the last resort when reboot fails entirely. */
static void fallback_to_tty2(void) {
    int console_fd, tty2_fd;

    /* Switch display to tty2 via VT_ACTIVATE ioctl */
    console_fd = pr_open("/dev/console", O_RDWR);
    if (console_fd < 0)
        console_fd = pr_open("/dev/tty0", O_RDWR);
    if (console_fd >= 0) {
        pr_ioctl(console_fd, VT_ACTIVATE, 2);
        pr_ioctl(console_fd, VT_WAITACTIVE, 2);
        pr_close(console_fd);
    }

    /* Write message directly to tty2 */
    tty2_fd = pr_open("/dev/tty2", O_WRONLY);
    if (tty2_fd >= 0) {
        pr_write(tty2_fd, TTY2_MSG, strlen(TTY2_MSG));
        pr_close(tty2_fd);
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

    pr_sync();
    pr_reboot(RB_AUTOBOOT);

    /* reboot() should never return on success.
     * If we're here, something went wrong. Try harder. */
    pr_sleep(1);
    pr_sync();
    pr_reboot(RB_AUTOBOOT);

    /* Still alive: try sysrq hard reboot */
    pr_sleep(1);
    try_sysrq_reboot();

    /* Still alive: give up on reboot, show manual instructions on tty2 */
    pr_sleep(2);
    fallback_to_tty2();

    return 1;
}
