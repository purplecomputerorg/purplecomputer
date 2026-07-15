# Contributing to Purple Computer

[Tavi](https://github.com/tavinathanson) here, thank you so much for your interest in Purple!

Please note that Purple Computer is **source available, not open source**. The full code is public so you can see exactly what runs on your kid's laptop, and so you can change anything about your own copy. This page explains more about this.

## What you can do

Tinker as much as you like! Add words, change colors, remap keys, build your own content packs, put your weird experiment on your own Purple Key. The [LICENSE](LICENSE) permits all of it for personal use. The one firm ask: please don't redistribute the code, modified versions, or add-ons built on it.

If you want to share a private modification with a specific friend, just ask (email below); the answer is usually yes. What we do ask is that changes never be shared publicly, and that anyone who uses Purple for more than testing and tinkering pays for it to support the project. Honor code, of course.

Bug reports and feature ideas are very welcome! Just email tavi@purplecomputer.org.

## Why we don't take pull requests

Purple doesn't accept pull requests, as much as we appreciate anyone who wants to contribute code back to the repo.

Two honest reasons:

- **Purple Computer is a small family business.** Open source maintenance is a second full-time job, and the burnout stories are everywhere ([this HN thread](https://news.ycombinator.com/item?id=48620462) is a good sample). Every PR deserves a careful review, a thoughtful reply, and a years-long maintenance commitment. That's hard to offer while also building the product, shipping physical packages, and supporting issues people run into.
- **Purple is fundamentally about removing things.** No internet, no apps, no points, no login, no errors, etc. The pitch on the site is literally "Calm by design: Purple never grabs for their attention. It can even be a little boring!" Nearly every contribution is an addition, and an open roadmap pulls a project toward more when the whole point is to hold the line at less.

Maybe at some point there will be a way to share modifications, add-ons, and so on. In the meantime, I'd love to hear about modifications you make to your own version!

## Why there's no dual-boot, VM, or app version

People sometimes ask about running Purple in a dual-boot setup, in a VM, or as an app inside another OS. I've shied away from those for a few reasons:

- **Compatibility.** It was difficult getting things working across as many computers as possible, and dual-boot would add complexity and compatibility issues.
- **Ownership.** The intended use is for kids to have full ownership of the machine. Dual-boot or running within an existing OS breaks that story a bit.
- **Support.** More configurations would also make supporting the product more complex.

You're still welcome to make private modifications like these for your own use, per above.

## Working on your own copy

The Quick Start in [README.md](README.md#quick-start) covers local setup (`just setup`, `just run`), and [MANUAL.md](docs/MANUAL.md) covers building a full installer image. Everything you need to run and modify Purple for yourself is in this repo.
