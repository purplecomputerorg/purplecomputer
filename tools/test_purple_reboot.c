/* Tests for purple-reboot.c fallback chain and message content.
 *
 * Uses compile-time test hooks (-DTESTING) so the real binary is
 * unmodified in production. All syscalls route to mock implementations
 * that record calls for assertions.
 *
 * Build & run:
 *   gcc -DTESTING -include tools/test_purple_reboot.c \
 *       -o /tmp/test_purple_reboot tools/purple-reboot.c \
 *   && /tmp/test_purple_reboot
 *
 * Or simply:  just test-reboot
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <linux/vt.h>
#include <unistd.h>

/* -----------------------------------------------------------------------
 * Mock infrastructure
 * ----------------------------------------------------------------------- */

#define MAX_CALLS 64
#define MAX_WRITES 32
#define MAX_WRITE_LEN 1024

static struct {
    int reboot_count;
    int sync_count;

    char opened_paths[MAX_CALLS][256];
    int open_count;

    unsigned long ioctl_requests[MAX_CALLS];
    int ioctl_args[MAX_CALLS];
    int ioctl_count;

    int write_fds[MAX_WRITES];
    char write_data[MAX_WRITES][MAX_WRITE_LEN];
    size_t write_lens[MAX_WRITES];
    int write_count;

    char read_char;
    int read_return;

    int sleep_seconds[MAX_CALLS];
    int sleep_count;

    int console_open_fails;
    int reached_pause_loop;

    int ignored_signals[MAX_CALLS];
    int ignored_signal_count;

    int find_xorg_pid;         /* 0 = no Xorg found */
    int kill_pids[MAX_CALLS];
    int kill_sigs[MAX_CALLS];
    int kill_reboot_counts[MAX_CALLS]; /* reboot_count when each kill was sent */
    int kill_count;
    int stat_alive_opens;      /* /proc/<pid>/stat opens that succeed, then ENOENT */
    char stat_state;           /* process state served by /proc/<pid>/stat */
    int reboots_at_first_term; /* reboot_count when SIGTERM was first sent */
} mock;

#define STAT_FD 43

static void mock_reset(void) {
    memset(&mock, 0, sizeof(mock));
    mock.read_return = 1;
    mock.read_char = '\n';
    mock.stat_state = 'S';
    mock.reboots_at_first_term = -1;
}

/* --- Mock implementations called by purple-reboot.c via pr_* macros --- */

int test_reboot(int cmd) {
    (void)cmd;
    mock.reboot_count++;
    return -1; /* Always "fail" so fallback chain runs */
}

void test_sync(void) {
    mock.sync_count++;
}

int test_open(const char *path, int flags) {
    (void)flags;
    if (mock.open_count < MAX_CALLS)
        strncpy(mock.opened_paths[mock.open_count++], path, 255);
    if (strstr(path, "/stat")) {
        if (mock.stat_alive_opens > 0) {
            mock.stat_alive_opens--;
            return STAT_FD;
        }
        return -1; /* process gone */
    }
    if (mock.console_open_fails &&
        (strcmp(path, "/dev/console") == 0 || strcmp(path, "/dev/tty0") == 0 ||
         strcmp(path, "/dev/tty") == 0))
        return -1;
    return 42; /* fake fd */
}

int test_close(int fd) { (void)fd; return 0; }

int test_ioctl(int fd, unsigned long req, int arg) {
    (void)fd;
    if (mock.ioctl_count < MAX_CALLS) {
        mock.ioctl_requests[mock.ioctl_count] = req;
        mock.ioctl_args[mock.ioctl_count] = arg;
        mock.ioctl_count++;
    }
    return 0;
}

ssize_t test_write(int fd, const void *buf, size_t len) {
    if (mock.write_count < MAX_WRITES) {
        mock.write_fds[mock.write_count] = fd;
        size_t copy = len < MAX_WRITE_LEN - 1 ? len : MAX_WRITE_LEN - 1;
        memcpy(mock.write_data[mock.write_count], buf, copy);
        mock.write_data[mock.write_count][copy] = '\0';
        mock.write_lens[mock.write_count] = len;
        mock.write_count++;
    }
    return (ssize_t)len;
}

ssize_t test_read(int fd, void *buf, size_t len) {
    if (fd == STAT_FD) {
        int n = snprintf(buf, len, "123 (Xorg) %c 1 123 123 0 -1",
                         mock.stat_state);
        return n;
    }
    (void)len;
    *(char *)buf = mock.read_char;
    return mock.read_return;
}

unsigned int test_sleep(unsigned int sec) {
    if (mock.sleep_count < MAX_CALLS)
        mock.sleep_seconds[mock.sleep_count++] = (int)sec;
    return 0;
}

void test_pause(void) {
    mock.reached_pause_loop = 1;
    /* longjmp out of the infinite loop */
    extern void test_escape_pause(void);
    test_escape_pause();
}

void test_signal(int sig, void (*handler)(int)) {
    if (handler == SIG_IGN && mock.ignored_signal_count < MAX_CALLS)
        mock.ignored_signals[mock.ignored_signal_count++] = sig;
}

void test_alarm(unsigned int sec) {
    (void)sec;
}

int test_find_xorg(void) {
    return mock.find_xorg_pid;
}

int test_kill(int pid, int sig) {
    if (mock.kill_count < MAX_CALLS) {
        mock.kill_pids[mock.kill_count] = pid;
        mock.kill_sigs[mock.kill_count] = sig;
        mock.kill_reboot_counts[mock.kill_count] = mock.reboot_count;
        mock.kill_count++;
    }
    if (sig == SIGTERM && mock.reboots_at_first_term < 0)
        mock.reboots_at_first_term = mock.reboot_count;
    return 0;
}

void test_msleep(void) {
}

/* -----------------------------------------------------------------------
 * Test harness
 * ----------------------------------------------------------------------- */

#include <setjmp.h>
static jmp_buf pause_escape;

void test_escape_pause(void) {
    longjmp(pause_escape, 1);
}

extern int purple_reboot_main(int argc, char **argv);

static int tests_run = 0;
static int tests_passed = 0;

#define ASSERT(cond, msg) do { \
    if (!(cond)) { \
        printf("  FAIL: %s (line %d): %s\n", __func__, __LINE__, msg); \
        return 0; \
    } \
} while(0)

#define RUN_TEST(fn) do { \
    tests_run++; \
    mock_reset(); \
    printf("  %s ... ", #fn); \
    if (fn()) { tests_passed++; printf("ok\n"); } \
} while(0)

/* Run purple_reboot_main, catching the pause() infinite loop */
static int run_main(int argc, char **argv) {
    if (setjmp(pause_escape) == 0)
        return purple_reboot_main(argc, argv);
    return 99; /* Escaped from pause loop */
}

static int find_write_containing(int fd, const char *substr) {
    for (int i = 0; i < mock.write_count; i++)
        if (mock.write_fds[i] == fd && strstr(mock.write_data[i], substr))
            return 1;
    return 0;
}

static int find_write_anywhere(const char *substr) {
    for (int i = 0; i < mock.write_count; i++)
        if (strstr(mock.write_data[i], substr))
            return 1;
    return 0;
}

static int was_opened(const char *path) {
    for (int i = 0; i < mock.open_count; i++)
        if (strcmp(mock.opened_paths[i], path) == 0)
            return 1;
    return 0;
}

/* -----------------------------------------------------------------------
 * Tests
 * ----------------------------------------------------------------------- */

static int test_no_args_reboots_immediately(void) {
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    ASSERT(mock.reboot_count >= 1, "reboot() should be called");
    ASSERT(mock.sync_count >= 1, "sync() should be called before reboot");
    ASSERT(!find_write_containing(STDOUT_FILENO, "All done"),
           "should not show wait message without --wait");
    return 1;
}

static int test_wait_shows_message(void) {
    char *argv[] = {"purple-reboot", "--wait", NULL};
    run_main(2, argv);
    ASSERT(find_write_containing(STDOUT_FILENO, "All done"),
           "should show 'All done' message");
    ASSERT(find_write_containing(STDOUT_FILENO, "Press Enter to restart"),
           "should show 'Press Enter' prompt");
    ASSERT(find_write_containing(STDOUT_FILENO, "remove the USB"),
           "should mention USB removal");
    ASSERT(find_write_containing(STDOUT_FILENO, "hold the power"),
           "should mention the hold-power fallback");
    return 1;
}

static int test_wait_exits_alternate_screen(void) {
    char *argv[] = {"purple-reboot", "--wait", NULL};
    run_main(2, argv);
    ASSERT(find_write_containing(STDOUT_FILENO, "\033[?1049l"),
           "should exit Textual's alternate screen buffer");
    return 1;
}

static int test_wait_reads_enter(void) {
    mock.read_char = '\n';
    mock.read_return = 1;
    char *argv[] = {"purple-reboot", "--wait", NULL};
    run_main(2, argv);
    ASSERT(mock.reboot_count >= 1, "should reboot after Enter");
    return 1;
}

static int test_wait_reads_eof(void) {
    mock.read_return = 0; /* EOF: PTY died from USB removal */
    char *argv[] = {"purple-reboot", "--wait", NULL};
    run_main(2, argv);
    ASSERT(mock.reboot_count >= 1, "should reboot after EOF (USB removal)");
    return 1;
}

static int test_fallback_retries_reboot(void) {
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    ASSERT(mock.reboot_count >= 2,
           "should retry reboot() after initial failure");
    return 1;
}

static int test_fallback_tries_sysrq(void) {
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    ASSERT(was_opened("/proc/sys/kernel/sysrq"), "should enable sysrq");
    ASSERT(was_opened("/proc/sysrq-trigger"), "should write to sysrq-trigger");
    return 1;
}

static int test_sysrq_writes_correct_commands(void) {
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    ASSERT(find_write_anywhere("1"), "should write '1' to enable sysrq");
    ASSERT(find_write_anywhere("b"), "should write 'b' to trigger reboot");
    return 1;
}

static int test_fallback_writes_to_stdout(void) {
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    ASSERT(find_write_containing(STDOUT_FILENO, "installed successfully"),
           "should write failure message to stdout (Alacritty)");
    ASSERT(find_write_containing(STDOUT_FILENO, "power button"),
           "stdout message should say to use power button");
    return 1;
}

static int test_fallback_switches_to_tty2(void) {
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    ASSERT(mock.reached_pause_loop, "should reach pause loop");
    ASSERT(was_opened("/dev/console") || was_opened("/dev/tty0") || was_opened("/dev/tty"),
           "should open console device for VT switch");
    ASSERT(was_opened("/dev/tty2"), "should open /dev/tty2");
    return 1;
}

static int test_tty2_message_has_support_email(void) {
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    ASSERT(find_write_anywhere("support@purplecomputer.org"),
           "tty2 message should contain support email");
    return 1;
}

static int test_tty2_message_confirms_install(void) {
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    ASSERT(find_write_anywhere("installed successfully"),
           "tty2 message should confirm install succeeded");
    return 1;
}

static int test_tty2_message_says_power_button(void) {
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    ASSERT(find_write_anywhere("power button"),
           "tty2 message should tell user to use power button");
    return 1;
}

static int test_fallback_chain_sleep_order(void) {
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    ASSERT(mock.sleep_count >= 3, "should have 3 sleep delays in fallback chain");
    ASSERT(mock.sleep_seconds[0] == 1, "1s before reboot retry");
    ASSERT(mock.sleep_seconds[1] == 1, "1s before sysrq");
    ASSERT(mock.sleep_seconds[2] == 2, "2s before tty2 fallback");
    return 1;
}

static int test_console_fallback_paths(void) {
    mock.console_open_fails = 1;
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    ASSERT(was_opened("/dev/console"), "should try /dev/console first");
    ASSERT(was_opened("/dev/tty0"), "should try /dev/tty0 second");
    ASSERT(was_opened("/dev/tty"), "should try /dev/tty third");
    return 1;
}

static int test_vt_activate_with_tty2(void) {
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    int found_activate = 0, found_waitactive = 0;
    for (int i = 0; i < mock.ioctl_count; i++) {
        if (mock.ioctl_requests[i] == VT_ACTIVATE && mock.ioctl_args[i] == 2)
            found_activate = 1;
        if (mock.ioctl_requests[i] == VT_WAITACTIVE && mock.ioctl_args[i] == 2)
            found_waitactive = 1;
    }
    ASSERT(found_activate, "should VT_ACTIVATE to tty2");
    ASSERT(found_waitactive, "should VT_WAITACTIVE for tty2");
    return 1;
}

static int was_signal_ignored(int sig) {
    for (int i = 0; i < mock.ignored_signal_count; i++)
        if (mock.ignored_signals[i] == sig)
            return 1;
    return 0;
}

static int test_ignores_terminal_signals(void) {
    char *argv[] = {"purple-reboot", "--wait", NULL};
    run_main(2, argv);
    ASSERT(was_signal_ignored(SIGHUP),  "should ignore SIGHUP (pty hangup on USB removal)");
    ASSERT(was_signal_ignored(SIGPIPE), "should ignore SIGPIPE (write to dead pty)");
    ASSERT(was_signal_ignored(SIGQUIT), "should ignore SIGQUIT (Ctrl+\\)");
    ASSERT(was_signal_ignored(SIGINT),  "should ignore SIGINT (Ctrl+C)");
    ASSERT(was_signal_ignored(SIGTSTP), "should ignore SIGTSTP (Ctrl+Z)");
    return 1;
}

static int sent_signal(int sig) {
    for (int i = 0; i < mock.kill_count; i++)
        if (mock.kill_sigs[i] == sig)
            return 1;
    return 0;
}

static int test_xorg_sigtermed_before_any_reboot(void) {
    mock.find_xorg_pid = 123;
    mock.stat_alive_opens = 2;
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    ASSERT(mock.kill_count >= 1, "should send signals to Xorg");
    ASSERT(mock.kill_pids[0] == 123 && mock.kill_sigs[0] == SIGTERM,
           "first signal should be SIGTERM to the Xorg pid");
    ASSERT(mock.reboots_at_first_term == 0,
           "X teardown must happen before any reboot() call");
    ASSERT(mock.reboot_count >= 1, "should still reboot after teardown");
    return 1;
}

static int test_xorg_polled_until_dead_no_sigkill(void) {
    mock.find_xorg_pid = 123;
    mock.stat_alive_opens = 3;
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    ASSERT(!sent_signal(SIGKILL),
           "no SIGKILL when Xorg exits within the poll window");
    ASSERT(mock.sleep_count >= 1 && mock.sleep_seconds[0] == 1,
           "should settle 1s after Xorg dies, before reboot");
    return 1;
}

static int test_xorg_sigkill_backstop_never_hangs(void) {
    mock.find_xorg_pid = 123;
    mock.stat_alive_opens = 1000000;
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    ASSERT(sent_signal(SIGKILL),
           "should SIGKILL a TERM-immune Xorg after the poll window");
    ASSERT(mock.reboot_count >= 1,
           "must reboot even if Xorg never dies");
    return 1;
}

static int test_zombie_xorg_counts_as_dead(void) {
    /* A wedged parent (USB removal) can't reap Xorg, so it stays a zombie.
     * Its GPU is already released; the poll must not stall 7s on it. */
    mock.find_xorg_pid = 123;
    mock.stat_alive_opens = 1000000;
    mock.stat_state = 'Z';
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    ASSERT(sent_signal(SIGTERM), "should still SIGTERM the zombie's pid");
    ASSERT(!sent_signal(SIGKILL),
           "zombie is dead for our purposes: no SIGKILL, no poll stall");
    ASSERT(mock.reboot_count >= 1, "should reboot promptly");
    return 1;
}

static int test_no_xorg_skips_teardown(void) {
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    ASSERT(mock.kill_count == 0, "no Xorg means no signals sent");
    ASSERT(mock.reboot_count >= 1, "should reboot normally");
    return 1;
}

static int test_retry_reboot_tears_down_respawned_xorg(void) {
    /* purple-x11.service Restart=on-failure can bring X back ~2s after
     * teardown; the retry reboot must kill it again first. */
    mock.find_xorg_pid = 123;
    mock.stat_alive_opens = 1;
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    int term_after_first_reboot = 0;
    for (int i = 0; i < mock.kill_count; i++)
        if (mock.kill_sigs[i] == SIGTERM && mock.kill_reboot_counts[i] >= 1)
            term_after_first_reboot = 1;
    ASSERT(term_after_first_reboot,
           "should SIGTERM Xorg again between reboot attempts");
    return 1;
}

static int test_wait_tears_down_xorg_after_enter(void) {
    mock.find_xorg_pid = 77;
    mock.stat_alive_opens = 1;
    char *argv[] = {"purple-reboot", "--wait", NULL};
    run_main(2, argv);
    ASSERT(mock.kill_pids[0] == 77 && mock.kill_sigs[0] == SIGTERM,
           "--wait path should also tear down Xorg before reboot");
    return 1;
}

static int test_sync_before_every_reboot(void) {
    char *argv[] = {"purple-reboot", NULL};
    run_main(1, argv);
    ASSERT(mock.sync_count >= 2, "should sync before each reboot attempt");
    return 1;
}

/* -----------------------------------------------------------------------
 * Main (replaces purple_reboot_main as the real entry point)
 * ----------------------------------------------------------------------- */

int main(void) {
    printf("purple-reboot tests:\n");

    RUN_TEST(test_no_args_reboots_immediately);
    RUN_TEST(test_wait_shows_message);
    RUN_TEST(test_wait_exits_alternate_screen);
    RUN_TEST(test_wait_reads_enter);
    RUN_TEST(test_wait_reads_eof);
    RUN_TEST(test_fallback_retries_reboot);
    RUN_TEST(test_fallback_tries_sysrq);
    RUN_TEST(test_sysrq_writes_correct_commands);
    RUN_TEST(test_fallback_writes_to_stdout);
    RUN_TEST(test_fallback_switches_to_tty2);
    RUN_TEST(test_tty2_message_has_support_email);
    RUN_TEST(test_tty2_message_confirms_install);
    RUN_TEST(test_tty2_message_says_power_button);
    RUN_TEST(test_fallback_chain_sleep_order);
    RUN_TEST(test_console_fallback_paths);
    RUN_TEST(test_vt_activate_with_tty2);
    RUN_TEST(test_ignores_terminal_signals);
    RUN_TEST(test_xorg_sigtermed_before_any_reboot);
    RUN_TEST(test_xorg_polled_until_dead_no_sigkill);
    RUN_TEST(test_xorg_sigkill_backstop_never_hangs);
    RUN_TEST(test_zombie_xorg_counts_as_dead);
    RUN_TEST(test_no_xorg_skips_teardown);
    RUN_TEST(test_retry_reboot_tears_down_respawned_xorg);
    RUN_TEST(test_wait_tears_down_xorg_after_enter);
    RUN_TEST(test_sync_before_every_reboot);

    printf("\n%d/%d tests passed\n", tests_passed, tests_run);
    return tests_passed == tests_run ? 0 : 1;
}
