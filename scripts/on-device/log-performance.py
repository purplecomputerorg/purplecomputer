#!/usr/bin/env python3
"""Capture up to 2 minutes of performance data, then explain it.

Run from the parent-menu terminal on any ISO:
    log-performance           start a capture, then go use Purple normally
    log-performance           run again later: prints the analyzed report
    log-performance start     force a fresh capture
    log-performance report    analyze now (works mid-capture on partial data)
    log-performance status    is a capture running?
    log-performance stop      end a capture early

Raw data stays in /tmp/purple-perf/ for deeper digging.
"""

import glob
import json
import os
import re
import subprocess
import sys
import time

DIR = os.environ.get("PURPLE_PERF_DIR", "/tmp/purple-perf")
SAMPLES = os.path.join(DIR, "samples.jsonl")
CONTEXT = os.path.join(DIR, "context.json")
PIDFILE = os.path.join(DIR, "sampler.pid")
LOG = os.path.join(DIR, "sampler.log")
DURATION = int(os.environ.get("PURPLE_PERF_SECONDS", "120"))
INTERVAL = 1.0

RED, GREEN, YELLOW, BLUE, BOLD, NC = (
    "\033[0;31m", "\033[0;32m", "\033[1;33m", "\033[1;34m", "\033[1m", "\033[0m")


def ok(msg):
    print(f"{GREEN}[  OK  ]{NC} {msg}")


def warn(msg):
    print(f"{YELLOW}[ WARN ]{NC} {msg}")


def bad(msg):
    print(f"{RED}[ SLOW ]{NC} {msg}")


def info(msg):
    print(f"         {msg}")


def section(title):
    print(f"\n{BLUE}--- {title} ---{NC}")


def read_file(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def run_cmd(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


# --------------------------------------------------------------------------
# Sampling
# --------------------------------------------------------------------------

def cpu_snapshot():
    total, cores = None, []
    for line in read_file("/proc/stat").splitlines():
        parts = line.split()
        if not parts or not parts[0].startswith("cpu"):
            break
        nums = [int(x) for x in parts[1:]]
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
        entry = [sum(nums) - idle, sum(nums)]
        if parts[0] == "cpu":
            total = entry
        else:
            cores.append(entry)
    return {"total": total, "cores": cores}


def proc_snapshot():
    procs = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        stat = read_file(f"/proc/{pid}/stat")
        rp = stat.rfind(")")
        if rp < 0:
            continue
        name = stat[stat.find("(") + 1:rp]
        fields = stat[rp + 2:].split()
        ticks = int(fields[11]) + int(fields[12])
        if ticks:
            procs[pid] = [name, ticks]
    return procs


def freqs_khz():
    vals = []
    for p in glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq"):
        v = read_file(p).strip()
        if v.isdigit():
            vals.append(int(v))
    return vals


def max_temp_c():
    nums = []
    for p in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        v = read_file(p).strip()
        if v.lstrip("-").isdigit():
            nums.append(int(v))
    return round(max(nums) / 1000, 1) if nums else None


def psi_avg10():
    out = {}
    for res in ("cpu", "io", "memory"):
        m = re.search(r"some avg10=([\d.]+)", read_file(f"/proc/pressure/{res}"))
        if m:
            out[res] = float(m.group(1))
    return out


def meminfo_kb(keys):
    text = read_file("/proc/meminfo")
    out = {}
    for key in keys:
        m = re.search(rf"^{key}:\s+(\d+)", text, re.M)
        if m:
            out[key] = int(m.group(1))
    return out


def disk_sectors():
    out = {}
    for line in read_file("/proc/diskstats").splitlines():
        f = line.split()
        if len(f) > 9 and os.path.exists(f"/sys/block/{f[2]}"):
            out[f[2]] = [int(f[5]), int(f[9])]
    return out


def pids_of(name):
    return [p for p in os.listdir("/proc") if p.isdigit()
            and read_file(f"/proc/{p}/comm").strip() == name]


def proc_env_var(name, var):
    for pid in pids_of(name):
        for item in read_file(f"/proc/{pid}/environ").split("\0"):
            if item.startswith(var + "="):
                return item.split("=", 1)[1]
    return None


def proc_cmdline(name):
    for pid in pids_of(name):
        return read_file(f"/proc/{pid}/cmdline").replace("\0", " ").strip()
    return None


def boot_disk():
    for line in read_file("/proc/mounts").splitlines():
        f = line.split()
        if len(f) > 1 and f[1] == "/cdrom" and f[0].startswith("/dev/"):
            part = os.path.basename(f[0])
            parent = os.path.dirname(os.path.realpath(f"/sys/class/block/{part}"))
            return os.path.basename(parent) if "/block/" in parent else part
    return None


def usb_speed_mbps(disk):
    p = os.path.realpath(f"/sys/block/{disk}/device")
    for _ in range(10):
        v = read_file(os.path.join(p, "speed")).strip()
        if v:
            return v
        p = os.path.dirname(p)
    return None


def write_context():
    cpuinfo = read_file("/proc/cpuinfo")
    model = re.search(r"model name\s*:\s*(.+)", cpuinfo)
    max_khz = read_file("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq").strip()
    disk = boot_disk()
    ctx = {
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cpu_model": model.group(1).strip() if model else "unknown",
        "ncpu": os.cpu_count() or 1,
        "mem_total_mb": meminfo_kb(["MemTotal"]).get("MemTotal", 0) // 1024,
        "swap_total_kb": meminfo_kb(["SwapTotal"]).get("SwapTotal", 0),
        "max_freq_mhz": int(max_khz) // 1000 if max_khz.isdigit() else None,
        "debug_iso": os.path.exists("/opt/purple/debug"),
        "boot_disk": disk,
        "usb_speed_mbps": usb_speed_mbps(disk) if disk else None,
        "alacritty_software_gl": proc_env_var("alacritty", "LIBGL_ALWAYS_SOFTWARE"),
        "picom_cmdline": proc_cmdline("picom"),
        "sinks": run_cmd(["pactl", "list", "short", "sinks"]),
        "sink_inputs": run_cmd(["pactl", "list", "short", "sink-inputs"]),
    }
    with open(CONTEXT, "w") as f:
        json.dump(ctx, f, indent=2)


def sample_loop():
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    write_context()
    start = time.monotonic()
    with open(SAMPLES, "w") as out:
        while time.monotonic() - start < DURATION:
            rec = {
                "t": round(time.monotonic() - start, 1),
                "cpu": cpu_snapshot(),
                "procs": proc_snapshot(),
                "freq": freqs_khz(),
                "temp": max_temp_c(),
                "psi": psi_avg10(),
                "mem": meminfo_kb(["MemAvailable", "SwapFree"]),
                "disk": disk_sectors(),
            }
            out.write(json.dumps(rec) + "\n")
            out.flush()
            elapsed = time.monotonic() - start
            time.sleep(max(0.1, INTERVAL - (elapsed % INTERVAL)))
    os.unlink(PIDFILE)


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------

def load_samples():
    recs = []
    for line in read_file(SAMPLES).splitlines():
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return recs


def machine_series(recs):
    out = []
    for a, b in zip(recs, recs[1:]):
        d_busy = b["cpu"]["total"][0] - a["cpu"]["total"][0]
        d_total = b["cpu"]["total"][1] - a["cpu"]["total"][1]
        if d_total <= 0:
            continue
        cores = [100 * (bc[0] - ac[0]) / max(1, bc[1] - ac[1])
                 for ac, bc in zip(a["cpu"]["cores"], b["cpu"]["cores"])]
        out.append({"pct": 100 * d_busy / d_total,
                    "maxcore": max(cores, default=0)})
    return out


def agg_name(name):
    return "kworker/*" if name.startswith("kworker") else name


def proc_stats(recs, ncpu):
    stats, n = {}, 0
    for a, b in zip(recs, recs[1:]):
        d_total = b["cpu"]["total"][1] - a["cpu"]["total"][1]
        if d_total <= 0:
            continue
        n += 1
        core_ticks = d_total / ncpu
        agg = {}
        for pid, (name, ticks) in b["procs"].items():
            prev = a["procs"].get(pid)
            if prev and ticks > prev[1]:
                key = agg_name(name)
                agg[key] = agg.get(key, 0) + 100 * (ticks - prev[1]) / core_ticks
        for name, pct in agg.items():
            st = stats.setdefault(name, {"sum": 0.0, "peak": 0.0})
            st["sum"] += pct
            st["peak"] = max(st["peak"], pct)
    return sorted(((name, st["sum"] / max(1, n), st["peak"])
                   for name, st in stats.items()), key=lambda x: -x[1])


def series_stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return {"avg": sum(vals) / len(vals), "max": max(vals), "min": min(vals)}


def frac_above(vals, threshold):
    vals = [v for v in vals if v is not None]
    return sum(1 for v in vals if v > threshold) / len(vals) if vals else 0


def audio_rates(ctx):
    sink = re.findall(r"(\d+)\s*Hz", ctx.get("sinks") or "")
    streams = re.findall(r"(\d+)\s*Hz", ctx.get("sink_inputs") or "")
    return sink, streams


def report_machine(ctx, recs):
    section("Machine")
    max_mhz = ctx.get("max_freq_mhz")
    info(f"CPU:  {ctx['cpu_model']} ({ctx['ncpu']} cores"
         + (f", max {max_mhz} MHz)" if max_mhz else ")"))
    avail = series_stats([r["mem"].get("MemAvailable") for r in recs])
    low = f", lowest available {avail['min'] // 1024:.0f} MB" if avail else ""
    info(f"RAM:  {ctx['mem_total_mb']} MB total{low}")
    info(f"ISO:  {'debug' if ctx['debug_iso'] else 'standard'}")
    speed = ctx.get("usb_speed_mbps")
    if ctx.get("boot_disk") and speed:
        if speed in ("1.5", "12", "480"):
            warn(f"Boot USB ({ctx['boot_disk']}) linked at {speed} Mbps (USB 2.0 or slower). "
                 "If this machine has a USB 3.0 port, try booting from it.")
        else:
            ok(f"Boot USB ({ctx['boot_disk']}) linked at {speed} Mbps")


def report_pipelines(ctx):
    section("Display and audio pipeline")
    if ctx.get("alacritty_software_gl") == "1":
        warn("Alacritty draws every frame on the CPU (LIBGL_ALWAYS_SOFTWARE=1). "
             "Heavy on weak CPUs; A/B by flipping it to 0 in /home/purple/.xinitrc.")
    elif ctx.get("alacritty_software_gl") is not None:
        ok("Alacritty uses hardware GL")
    picom = ctx.get("picom_cmdline")
    if picom:
        backend = (re.search(r"--backend (\w+)", picom) or [None, "?"])[1]
        (ok if backend == "glx" else warn)(f"Compositor: picom, backend {backend}")
    else:
        info("Compositor: not running")
    sink, streams = audio_rates(ctx)
    mismatched = [s for s in streams if s not in sink]
    if mismatched:
        warn(f"Audio streams at {'/'.join(set(mismatched))}Hz but the sink runs at "
             f"{'/'.join(set(sink))}Hz: PulseAudio resamples continuously, even for silence.")
    elif streams:
        ok(f"Audio stream rate matches the sink ({'/'.join(set(sink))}Hz), no resampling")
    elif sink:
        info("No audio streams were open when the capture started")


def report_cpu(ctx, recs):
    section("CPU load (whole machine = 100%)")
    series = machine_series(recs)
    total = series_stats([s["pct"] for s in series])
    if not total:
        warn("Not enough samples to measure CPU load")
        return [], []
    info(f"Average {total['avg']:.0f}%, peak {total['max']:.0f}%")
    sat = frac_above([s["pct"] for s in series], 85)
    single = frac_above([s["maxcore"] for s in series], 90)
    if sat > 0.25:
        bad(f"Machine saturated (>85% busy) {sat:.0%} of the time: CPU is the bottleneck")
    elif single > 0.25 and total["avg"] < 75:
        bad(f"One core pinned (>90%) {single:.0%} of the time while others idle: "
            "a single-threaded task is the ceiling (see table below)")
    else:
        ok(f"CPU rarely saturated ({sat:.0%} of samples above 85%)")

    procs = proc_stats(recs, ctx["ncpu"])
    section("Top CPU consumers (100% = one full core)")
    shown = [p for p in procs[:10] if p[1] >= 0.5]
    if shown:
        print("           avg     peak   process")
        for name, avg, peak in shown:
            print(f"         {avg:5.1f}%  {peak:6.1f}%  {name}")
    else:
        info("(no process averaged even 0.5% of a core)")
    return series, procs


def report_freq(ctx, recs):
    section("CPU frequency and heat")
    series = machine_series(recs)
    busy_freqs, all_freqs = [], []
    for s, r in zip(series, recs[1:]):
        if r.get("freq"):
            mhz = sum(r["freq"]) / len(r["freq"]) / 1000
            all_freqs.append(mhz)
            if s["pct"] > 60:
                busy_freqs.append(mhz)
    throttled = False
    max_mhz = ctx.get("max_freq_mhz")
    if all_freqs:
        line = f"Average {sum(all_freqs) / len(all_freqs):.0f} MHz"
        if busy_freqs:
            line += f", {sum(busy_freqs) / len(busy_freqs):.0f} MHz while busy"
        if max_mhz:
            line += f" (hardware max {max_mhz} MHz)"
        info(line)
        if max_mhz and busy_freqs and sum(busy_freqs) / len(busy_freqs) < 0.75 * max_mhz:
            throttled = True
            warn("Running well below max speed while busy: thermal or power throttling "
                 "(fanless laptops slow down as they heat up)")
    temp = series_stats([r.get("temp") for r in recs])
    if temp:
        (warn if temp["max"] > 85 else info)(f"Peak temperature {temp['max']:.0f}C")
    return throttled


def report_stalls(recs):
    section("Waiting (pressure stall info)")
    out = {}
    for res, label in (("cpu", "runnable tasks waited for a CPU"),
                       ("io", "tasks stalled on disk/USB reads"),
                       ("memory", "tasks stalled on memory")):
        st = series_stats([r.get("psi", {}).get(res) for r in recs])
        if not st:
            continue
        out[res] = st
        msg = f"{label}: avg {st['avg']:.0f}%, peak {st['max']:.0f}% of the time"
        (warn if st["avg"] > 15 or st["max"] > 40 else info)(msg)
    if not out:
        info("Pressure stall info not available on this kernel")
    return out


def report_disk(recs):
    section("Disk reads during capture")
    first, last = recs[0].get("disk", {}), recs[-1].get("disk", {})
    for dev in sorted(last):
        if dev in first:
            mb = (last[dev][0] - first[dev][0]) * 512 / 1e6
            if mb >= 1:
                label = " (squashfs: decompressed reads from the boot USB)" if dev.startswith("loop") else ""
                info(f"{dev}: {mb:.0f} MB read{label}")


def verdicts(ctx, series, procs, throttled, psi):
    section("Likely bottlenecks, strongest first")
    top = {name: avg for name, avg, _ in procs[:10]}
    findings = []
    sat = frac_above([s["pct"] for s in series], 85)
    single = frac_above([s["maxcore"] for s in series], 90)
    if ctx.get("alacritty_software_gl") == "1" and top.get("alacritty", 0) > 25:
        findings.append("Software GL rendering: alacritty is a top CPU consumer and it is "
                        "rasterizing on the CPU. Flip LIBGL_ALWAYS_SOFTWARE to 0 in "
                        "/home/purple/.xinitrc and restart to A/B this.")
    if sat > 0.25:
        heavy = ", ".join(n for n, a in list(top.items())[:3] if a > 15) or "see table above"
        findings.append(f"The CPU is simply out of headroom {sat:.0%} of the time. "
                        f"Heaviest processes: {heavy}.")
    elif single > 0.25:
        culprit = next((n for n, a, peak in procs if peak > 80), None)
        who = f"{culprit} pins one core" if culprit else "a single-threaded task pins one core"
        findings.append(f"{who} while others idle: single-thread CPU speed is the "
                        "ceiling on this machine.")
    if throttled:
        findings.append("The CPU is throttling below its rated speed under load, "
                        "compounding everything else.")
    sink, streams = audio_rates(ctx)
    if any(s not in sink for s in streams) and top.get("pulseaudio", 0) > 5:
        findings.append("PulseAudio burns CPU resampling audio nonstop because the app's "
                        "sample rate does not match the sound card's.")
    if psi.get("io", {}).get("avg", 0) > 10:
        findings.append("Tasks regularly stall on disk/USB reads: a slow stick or USB 2.0 "
                        "port is adding wait time.")
    if not findings:
        findings.append("Nothing stood out. If the machine felt slow anyway, make sure you "
                        "were actively using Purple during the capture, then try again.")
    for i, f in enumerate(findings, 1):
        print(f"      {i}. {f}")


def report():
    ctx = json.loads(read_file(CONTEXT) or "{}")
    recs = load_samples()
    if not ctx or len(recs) < 3:
        print("No usable capture yet. Start one with: log-performance start")
        return
    running = sampler_running()
    print("===========================================================")
    print("  Purple Performance Report")
    print(f"  captured {ctx.get('started_at', '?')}, {len(recs)} seconds of data"
          + (" (capture still running)" if running else ""))
    print("===========================================================")
    report_machine(ctx, recs)
    report_pipelines(ctx)
    series, procs = report_cpu(ctx, recs)
    throttled = report_freq(ctx, recs)
    psi = report_stalls(recs)
    report_disk(recs)
    if series:
        verdicts(ctx, series, procs, throttled, psi)
    print(f"\nRaw data: {DIR}/   Fresh capture: log-performance start")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def sampler_running():
    pid = read_file(PIDFILE).strip()
    return pid if pid.isdigit() and os.path.exists(f"/proc/{pid}") else None


def start():
    if sampler_running():
        status()
        return
    os.makedirs(DIR, exist_ok=True)
    for f in (SAMPLES, CONTEXT):
        if os.path.exists(f):
            os.unlink(f)
    with open(LOG, "w") as log:
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "_sample"],
                         stdout=log, stderr=log, start_new_session=True)
    mins = f"{DURATION // 60} minutes" if DURATION >= 120 else f"{DURATION} seconds"
    print(f"Recording performance for {mins} (it stops by itself).")
    print("Close this terminal and use Purple normally: play, type, switch rooms.")
    print("Come back any time and run:  log-performance")


def status():
    pid = sampler_running()
    if pid:
        recs = load_samples()
        elapsed = recs[-1]["t"] if recs else 0
        print(f"Capture running: {elapsed:.0f}s of {DURATION}s recorded.")
        print("Report so far:  log-performance report")
    elif os.path.exists(SAMPLES):
        print("Capture finished. Report:  log-performance report")
    else:
        print("No capture running. Start one:  log-performance start")


def stop():
    pid = sampler_running()
    if pid:
        os.kill(int(pid), 15)
        os.unlink(PIDFILE)
        print("Capture stopped. Report:  log-performance report")
    else:
        print("No capture running.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "_sample":
        sample_loop()
    elif cmd == "start":
        start()
    elif cmd == "report":
        report()
    elif cmd == "status":
        status()
    elif cmd == "stop":
        stop()
    elif cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
    elif cmd == "":
        if sampler_running():
            status()
        elif os.path.exists(SAMPLES):
            report()
        else:
            start()
    else:
        print(__doc__.strip())
        sys.exit(1)


if __name__ == "__main__":
    main()
