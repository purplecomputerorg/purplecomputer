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
 */
#include <sys/reboot.h>
#include <unistd.h>
#include <string.h>
#include <signal.h>

static volatile int timed_out = 0;

static void alarm_handler(int sig) {
    (void)sig;
    timed_out = 1;
}

int main(int argc, char **argv) {
    if (argc > 1 && strcmp(argv[1], "--wait") == 0) {
        /* Exit alternate screen buffer (Textual uses it), then clear */
        const char *msg =
            "\033[?1049l\033[2J\033[H"
            "\n"
            "  All done!\n"
            "\n"
            "  Purple Computer is installed.\n"
            "  You can remove the USB drive now.\n"
            "\n"
            "  Press Enter to restart.\n"
            "\n";
        write(STDOUT_FILENO, msg, strlen(msg));

        /* Safety net: reboot after 15 min if nothing else triggers it.
         * Normally read() returns on Enter or EOF (pty dies from USB removal). */
        signal(SIGALRM, alarm_handler);
        alarm(900);

        char c;
        while (!timed_out) {
            int n = read(STDIN_FILENO, &c, 1);
            if (n <= 0 || c == '\n')
                break;
        }
    }

    sync();
    reboot(RB_AUTOBOOT);
    return 1;
}
