# How Purple Computer Is Delivered and Updated

How the Purple Key reaches you, why we flash raw ISOs instead of using a multi-boot tool, and how updates work.

---

## Summary

- **How you receive Purple:** most customers get a pre-flashed USB drive ("Purple Key") that boots on any supported laptop right out of the envelope. No flashing required.
- **Self-service option:** technically comfortable users can download the ISO and write it to their own USB using [balenaEtcher](https://etcher.balena.io/).
- **Updates:** receive a freshly prepared USB, or re-flash the existing one with a new ISO using Etcher.

---

## Why Not Ventoy

Ventoy is a popular multi-boot tool: install it once on a USB, then drop new `.iso` files onto the stick to update. For a product that releases new versions on a cadence, this looks ideal.

**We do not use Ventoy because it does not work reliably on the laptops Purple Computer targets.** Purple is designed to run on older hardware, including 2013–2015 Intel MacBooks, and those machines sit in Ventoy's known-bad zone.

### Documented failure modes on 2013–2015 MacBooks

| Model | Failure | Source |
|-------|---------|--------|
| MacBook Pro 2015 | "Not a Secure Boot Platform 14" when chainloading any ISO. Unresolved. | [Ventoy #394](https://github.com/ventoy/Ventoy/issues/394) |
| MacBook Air A1466 (2013–2017) | Ventoy menu loads, ISO selection results in a black screen with a non-blinking cursor. The same ISO flashed raw with Etcher or Rufus boots fine. Closed as "not planned." | [Ventoy #1056](https://github.com/ventoy/Ventoy/issues/1056) |
| MacBook Pro 2012 | Ventoy fails to load any OS. | [Ventoy #52](https://github.com/ventoy/Ventoy/issues/52) |
| MacBook Pro/Air generally | "Incompatibility with MacBook's EFI." | [Ventoy #204](https://github.com/ventoy/Ventoy/issues/204) |

Even on MacBooks where Ventoy happens to work, results are inconsistent across units of the same model, which is not acceptable for a product shipped to families.

### Why this settles the decision

Two facts, together:

1. **Ventoy upstream has declined to address Mac EFI compatibility.** The relevant issues are closed "not planned," so this is not a problem that will be patched out over time.
2. **The same MacBooks that fail under Ventoy boot fine with a raw-flashed ISO.** Issue #1056 is the clearest example: same USB stick, same ISO, raw-flashed with Etcher boots successfully, while Ventoy chainloading does not. The failure lives in Ventoy's boot layer, not in the operating system.

Adopting Ventoy would mean trading a boot method that works on our target hardware for one that is known to fail on it.

### What about raw-flashing reliability?

Raw ISO flashing is not magic either: some USB brands occasionally need a second try, or benefit from a different flashing tool. **balenaEtcher's write-and-verify flow is what we recommend and what we use for drives we ship.** If you're self-flashing and a stick does not boot on the first try, re-flashing with Etcher or using a different USB drive usually resolves it.

---

## How We Prepare Purple Keys

Every Purple Key we ship is:

1. Built from the current Purple Computer release.
2. Written using **balenaEtcher**, which verifies the copy and safely re-enumerates the drive.
3. Boot-tested on a representative Intel Mac (2013–2015 MacBook Air or Pro) before being packaged.
4. Shipped with the printed installation card and guide card in the package.

---

## Updates

Since Ventoy is not an option, updating a Purple Key uses one of these paths:

### A new Purple Key in the mail

For major updates we can send a freshly prepared USB. Zero technical effort on your end: unwrap, plug in, boot. This is the default we recommend for families who prefer not to touch flashing tools.

### Re-flashing the existing USB

If you're comfortable with a desktop app: download the latest ISO from the Purple website, open balenaEtcher, select the ISO and your Purple Key, and click Flash. When it finishes, the key is updated.

### In-place updates (on the roadmap)

Eventually Purple will be able to update itself without involving the USB at all. We're working on it. Until then, the two options above are how updates happen.

---

If a Purple Key won't boot, or you have any questions about updates, reach out to [support@purplecomputer.org](mailto:support@purplecomputer.org) and we'll sort it out.
