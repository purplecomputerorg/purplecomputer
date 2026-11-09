# Mac speakers: patched codec drivers for 2016-2017 Macs

On two Mac families the stock Ubuntu drivers bind the codec and accept audio, but never switch on the speaker amplifiers, so the speakers stay silent while ALSA reports success (`guides/boot-hang-debugging.md`, "The silent-but-not-hanging case").

| Models | Codec | Stock driver | Patched driver |
|---|---|---|---|
| MacBook9,1, MacBook10,1 (12", 2016-2017) | CS4208 | Headphone jack only | [leifliddy/macbook12-audio-driver](https://github.com/leifliddy/macbook12-audio-driver): speakers, jack, switching, mic |
| MacBookPro13,1-3, MacBookPro14,1-3 (2016-2017) | CS8409 | Silent | [davidjo/snd_hda_macbookpro](https://github.com/davidjo/snd_hda_macbookpro): speakers, headphones; amps MAX98706, SSM3515, TAS5764L |

Not covered: MacBook8,1 (2015 12", unsupported upstream), T2 Macs (audio goes through `apple-bce` on the t2 kernel), Dells with CS8409 (stock driver, Secure Boot on).

## Why unsigned modules are safe here

The patched modules are unsigned. Intel Macs before the T2 chip have no Secure Boot, so the kernel is not in lockdown and loads them (it logs a taint). Every Secure Boot machine runs only signed code, because the modules load solely on the listed models. Same reasoning as the t2 kernel (`guides/hardware-coverage-plan.md`, "Why two kernels").

## How it fits

- **Build** (`install_mac_audio` in `00-build-golden-image.sh`, amd64 only): both drivers are pinned by commit and tarball sha256, built inside the chroot against the image's exact kernel using Ubuntu's `linux-source-6.8.0` at the same version (not kernel.org: Ubuntu backports change HDA structs, and a mismatch can crash rather than fail to load). Output goes to `/opt/purple/modules/$KVER/`, outside `/lib/modules`, so depmod and udev never pick them up on their own. The build fails if either module is missing or has the wrong vermagic.
- **Load** (`scripts/purple-mac-audio.sh`, called by the `install` rules in `config/modprobe/purple-mac-audio.conf`): when the kernel asks for `snd_hda_codec_cirrus` or `snd_hda_codec_cs8409`, the script checks the DMI model against `purple_cs4208mac_models` / `purple_cs8409mac_models` in `config/grub/purple-variants.cfg` (the single model list, also read by the router and `install.sh`), loads the dependencies and `insmod`s the patched build. Any other machine, a missing file, a different kernel (the t2 kernel has no folder) or a failed load runs `modprobe --ignore-install`, the stock module. It reads DMI itself instead of a GRUB argument so the UKI path works. Decisions are logged to the kernel log (`purple-mac-audio:`).
- **Initrd:** sound modules must load after the pivot, where the hook lives. The build fails if the stock initrd ever carries a Cirrus codec module.
- **Volume:** the patched CS8409 driver exposes no mixer controls, so Pulse uses software volume by itself. The patched CS4208 driver's `Master` reaches only the headphone amp, so `config/udev/91-purple-mac-audio.rules` gives that card (and only that card: its codec must be CS4208) `config/pulse/purple-softvol.conf` (mappings without mixer paths, so every Pulse volume change is software) and unmutes `Master` at 80%, below full headphone gain. Purple's volume steps and Volume Lock then scale both speakers and jack. If noble's `alsa-ucm-conf` claims the card, Pulse ignores profile sets; `pactl list cards` on hardware shows which one won.
- **Detection** (`purple_tui/mixer.py`): out-of-tree modules carry `O` in `/sys/module/<name>/taint`. The CS8409 "known silent" veto only applies on the stock module, and a 12" MacBook on the stock module reports "headphone jack only" on the Support screen.

## Updating

Kernel bumps rebuild both modules automatically; a patch that stops applying fails the build. To move a driver forward, update its URL and sha256 together (`curl -fsSL <url> | sha256sum`). The drivers choose code paths from the kernel version number, which Ubuntu's backports can contradict; the build rewrites `struct snd_pci_quirk` to `struct hda_quirk` when the headers define the latter (6.8.0-149 does).

## Hardware checks still open

On each model: speakers play, headphones switch both ways mid-session, volume steps and Volume Lock change speaker loudness, the startup chime and mic check behave, sound returns after lid close and open, and the 2016 MBP no longer hangs in `snd_pcm_open()` (the mixer timeout guard stays regardless).
