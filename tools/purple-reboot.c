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

int main(int argc, char **argv) {
    if (argc > 1 && strcmp(argv[1], "--wait") == 0) {
        /* Clear screen (VT100 escape) and show message */
        const char *msg =
            "\033[2J\033[H"
            "\n"
            "  All done!\n"
            "\n"
            "  Purple Computer is installed.\n"
            "  You can remove the USB drive now.\n"
            "\n"
            "  Press Enter to restart.\n"
            "\n";
        write(STDOUT_FILENO, msg, strlen(msg));

        /* Wait for Enter. Pure syscall, no library pages needed. */
        char c;
        while (read(STDIN_FILENO, &c, 1) > 0)
            if (c == '\n')
                break;
    }

    sync();
    reboot(RB_AUTOBOOT);
    return 1;
}
