#!/usr/bin/env python3
"""Summarize a customer's PURPLE-LOG (or diag.txt) into what matters for a
diagnosis: where boot got to, what failed or is stuck, and the kernel and
journal errors, without the megabytes of padding and repeated logs.

Usage: just read-log <path>
"""
import importlib.util
import re
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("stick_log", Path(__file__).with_name("purple-stick-log.py"))
_stick = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_stick)

REPORT_END = "\n===== end of"  # purple-stick-log and the initramfs word the rest differently
SECTION = re.compile(r"^===== (.+?) =====$", re.M)
TROUBLE = re.compile(
    r"I/O error|blk_update_request|critical medium|Buffer I/O|reset (high|full|super)-speed|USB disconnect|"
    r"squashfs.*error|SQUASHFS error|EXT4-fs error|segfault|Out of memory|oom-kill|hung_task|blocked for more than|"
    r"GPU HANG|\*ERROR\*|failed to load firmware|firmware: failed|Call Trace|BUG:|WARNING:|panic|timed out|"
    r"Failed to start|Dependency failed|core dumped|Traceback|(?-i:WATCHDOG)|\[ERROR\]|\[WARN\]|not found",
    re.I)
NOISE = re.compile(r"Could not resolve keysym|This will ERASE ALL DATA|supply \w+ not found, using dummy regulator")
PROGRESS = re.compile(r"^\[PURPLE-PV")
BOOT_MILESTONES = re.compile(r"=== |Display ready|No connected|Launching|launcher\] exec|watchdog armed|main loop|"
                             r"first render|WATCHDOG|mixer|Squashfs|Low RAM|USB safe")
CASPER = re.compile(r"purple|" + TROUBLE.pattern, re.I)


def split_regions(text):
    report, _, rest = text.partition(REPORT_END)
    kmsg = ""
    if _stick.KMSG_HEAD.decode() in rest:
        kmsg = rest.split(_stick.KMSG_HEAD.decode(), 1)[1]
        seam = _stick.SEAM.decode()
        kmsg = kmsg.split(seam, 1)[0] if seam in kmsg else kmsg.rstrip("\n")
    return report, kmsg


def sections(report):
    parts = SECTION.split(report)
    out = {"header": parts[0]}
    for name, body in zip(parts[1::2], parts[2::2]):
        out[name] = body.strip("\n")
    return out


def find(secs, prefix):
    return next((body for name, body in secs.items() if name.startswith(prefix)), "")


def matching(text, pattern, limit):
    """Lines matching `pattern`, repeats collapsed, the last `limit` of them."""
    seen, hits = {}, []
    for line in text.splitlines():
        if pattern.search(line) and not NOISE.search(line):
            key = re.sub(r"^\[[^]]*\]\s*|\d+", "", line)
            seen[key] = seen.get(key, 0) + 1
            if seen[key] == 1:
                hits.append((key, line))
    return [line + (f"  (x{seen[key]})" if seen[key] > 1 else "") for key, line in hits[-limit:]]


def show(title, lines):
    lines = [line for line in lines if line.strip()]
    if lines:
        print(f"\n## {title}")
        print("\n".join(lines))


def summarize(text):
    report, kmsg = split_regions(text)
    secs = sections(report)
    header = secs["header"].strip().splitlines()
    boot_log = secs.get("boot log", "")
    stuck = [line for line in find(secs, "processes").splitlines()[1:] if re.match(r"\s*\d+\s+\d+\s+D", line)]

    show("Report", header[:12])
    if header and header[0].startswith("purple-initramfs:"):
        show("Verdict", ["Only the initramfs report: boot never reached Purple's own services (see its first line)."])
    else:
        ui = "first render reached" in boot_log
        show("Verdict", [f"Purple {'reached' if ui else 'NEVER reached'} its first screen."])
    show("Memory", find(secs, "memory").splitlines())
    show("Failed units and pending jobs", find(secs, "systemd: failed").splitlines())
    show("Processes stuck in disk wait (D state)", stuck)
    show("Boot log milestones", matching(boot_log, BOOT_MILESTONES, 25))
    show("Boot log tail", boot_log.splitlines()[-8:])
    show("Casper (initramfs) lines", matching(find(secs, "casper log"), CASPER, 20))
    show("Install log problems", matching(secs.get("install log", ""), TROUBLE, 20))
    show("Install log tail", [line for line in secs.get("install log", "").splitlines() if not PROGRESS.match(line)][-6:])
    show("Power log tail", secs.get("power log", "").splitlines()[-8:])
    show("Xorg errors", [line for line in find(secs, "Xorg log").splitlines() if "(EE)" in line][-10:])
    show("Journal problems", matching(find(secs, "journal"), TROUBLE, 30))
    source = "live kernel log" if kmsg else "dmesg tail in the report"
    klog = kmsg or find(secs, "dmesg")
    if _stick.WRAP.decode().strip() in klog:
        show("Note", ["The kernel log wrapped: its earliest lines were overwritten."])
    show(f"Kernel problems ({source})", matching(klog, TROUBLE, 40))
    show(f"Last kernel lines ({source})", klog.splitlines()[-25:])


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__.strip().splitlines()[-1])
    summarize(Path(sys.argv[1]).read_bytes().decode("utf-8", errors="replace"))


if __name__ == "__main__":
    main()
