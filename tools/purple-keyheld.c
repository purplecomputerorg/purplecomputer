/* Exit 0 when any of the given key codes is held on any keyboard.
 *
 * Runs in the initramfs for "hold P while turning it on". EVIOCGKEY reads the
 * current state, so a key pressed before the keyboard driver loaded counts,
 * unlike waiting for press events. Static, no libc dependencies at runtime.
 *
 * Usage: purple-keyheld <keycode>...   (KEY_P is 25)
 */
#include <dirent.h>
#include <fcntl.h>
#include <linux/input.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    unsigned char bits[KEY_MAX / 8 + 1];
    char path[300];
    struct dirent *e;
    DIR *d = opendir("/dev/input");
    if (!d)
        return 1;
    while ((e = readdir(d))) {
        if (strncmp(e->d_name, "event", 5))
            continue;
        snprintf(path, sizeof path, "/dev/input/%s", e->d_name);
        int fd = open(path, O_RDONLY | O_NONBLOCK);
        if (fd < 0)
            continue;
        memset(bits, 0, sizeof bits);
        if (ioctl(fd, EVIOCGKEY(sizeof bits), bits) >= 0) {
            for (int i = 1; i < argc; i++) {
                int k = atoi(argv[i]);
                if (k > 0 && k <= KEY_MAX && (bits[k / 8] >> (k % 8) & 1)) {
                    close(fd);
                    closedir(d);
                    return 0;
                }
            }
        }
        close(fd);
    }
    closedir(d);
    return 1;
}
