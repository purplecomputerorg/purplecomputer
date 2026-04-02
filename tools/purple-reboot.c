/* Static reboot binary for post-install restart.
 *
 * Copied to /run (tmpfs) with setuid by install.sh. Survives USB removal
 * because it's on tmpfs with zero shared library dependencies (static build).
 * Called by Python's _trigger_reboot() after user presses Enter.
 */
#include <sys/reboot.h>
#include <unistd.h>

int main(void) {
    sync();
    reboot(RB_AUTOBOOT);
    return 1;
}
