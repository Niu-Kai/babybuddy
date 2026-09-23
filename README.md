<img src="babybuddy/static_src/logo/icon.png" height="150" align="left">

# Baby Buddy — Niu-Kai fork

[![License](https://img.shields.io/badge/License-BSD%202--Clause-orange.svg)](https://opensource.org/licenses/BSD-2-Clause)
[![Gitter](https://img.shields.io/gitter/room/nwjs/nw.js.svg)](https://gitter.im/babybuddy/Lobby)
[![CI Status](https://github.com/Niu-Kai/babybuddy/actions/workflows/ci.yml/badge.svg)](https://github.com/Niu-Kai/babybuddy/actions/workflows/ci.yml)
[![Open in GitHub Codespaces ready-to-code](https://img.shields.io/badge/Codespace-ready--to--code-blue?logo=github)](https://codespaces.new/Niu-Kai/babybuddy?quickstart=1)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

This is a customized fork of [Baby Buddy](https://github.com/babybuddy/babybuddy),
with credit to its original authors and contributors. It retains the
[BSD 2-Clause license](LICENSE).

## What is different in this fork

- Customizable dashboards, shared period filters, and day-by-day care reports.
- Growth charts with unit conversion, WHO references, and corrected-age support.
- Shared household inventory with diaper usage deductions and automatic restock reminders.
- Household pumping, separate left/right amounts, food tracking, and supplemental feedings.
- Calendar appointments, custom activities, child access permissions, and integration APIs.
- Optional browser offline entry and synchronization; a separate phone app is not required.
- Guided CSV imports with a validation preview, plus expanded interface translations.

See [feature details](docs/user-guide/upstream-followup.md),
[import/export instructions](docs/import-export.md), and the
[remaining verification and deferred issues](docs/upstream-remaining-issues-2026-09-22.md).
Physical-phone offline/install testing and several external integrations remain
unverified. Offline access covers supported new entries and limited recent
history, not the entire application. Updated translations still benefit from
native-speaker review.

For installation, browse the [setup guides](docs/setup). Use the
[update and backup workflow](docs/setup/updating.md) when updating an existing
installation. The [upstream integration record](docs/development/upstream-sync-2026-09-23.md)
explains how recent upstream changes were adapted to this fork.

## Original Baby Buddy overview

The screenshots and public demo below show the upstream project, rather than
this fork's redesigned interface.

A buddy for babies! Helps caregivers track sleep, feedings, diaper changes,
tummy time and more to learn about and predict baby's needs without (_as much_)
guess work.

![Baby Buddy desktop view](screenshot.png)

![Baby Buddy mobile views](screenshot_mobile.png)

## 👾 Upstream demo

A [demo of Baby Buddy](https://demo.baby-buddy.net) is available. The demo instance
resets every hour. Login credentials are:

- Username: `admin`
- Password: `admin`

## 📘 Documentation

Visit [https://docs.baby-buddy.net](https://docs.baby-buddy.net) for full documentation.

### Additional documentation

- [Security](/SECURITY.md)
- [License](/LICENSE) (BSD-2 Clause)

## 🗺️ Languages

Baby Buddy is available in a variety of languages thanks to the efforts of numerous
translators. Language can be set on a per-user basis from the user settings page
(`/user/settings/`). See [Contributing](https://docs.baby-buddy.net/contributing/translation/)
for information about how to create/update translations.

### Available languages

:brazil: Brazilian Portuguese, :es: Catalan, :cn: Chinese (simplified), :hong_kong: Chinese (traditional), :taiwan: Chinese (Taiwan), :croatia: Croatian, :czech_republic: Czech, :denmark: Danish, :netherlands: Dutch, :uk: English (U.K.), :us: English (U.S.) (base), :finland: Finnish, :fr: French, :de: German, :israel: Hebrew, :hungary: Hungarian, :it: Italian, :jp: Japanese, :kr: Korean, :norway: Norwegian Bokmål, :poland: Polish, :portugal: Portuguese, :ru: Russian, :serbia: Serbian, :mexico: :es: Spanish, :sweden: Swedish, :tr: Turkish, :ukraine: Ukrainian

## 🌐 Baby Buddy on the Web

This is a non-exhaustive list of neat projects and blog posts that either extend
or use Baby Buddy in fun ways. If you have a project to share please open a PR
adding it here or reach out via GitHub Issues or Discussions or on Gitter!

### AI

- [Baby Buddy MCP server](https://github.com/babybuddy/babybuddy-mcp) - A [Model Context Protocol](https://modelcontextprotocol.io) server for logging and querying Baby Buddy data with AI assistants. See the [MCP documentation](https://docs.baby-buddy.net/mcp/).

### Smart home

- [Home Assistant Addon](https://github.com/OttPeterR/addon-babybuddy) (host Baby Buddy on Home Assistant)
- [Home Assistant integration](https://github.com/jcgoette/baby_buddy_homeassistant) (monitor and use Baby Buddy from Home Assistant)
- [How to Setup Baby Buddy in Home Assistant](https://smarthomescene.com/guides/how-to-setup-baby-buddy-in-home-assistant/)
- [Baby Buddy and Home Assistant](https://martinnoah.com/babybuddy-and-home-assistant.html)
- [Alexa skill](https://github.com/babybuddy/babybuddy-alexa-skill)

### Hardware

- [Bottle Scale for BabyBuddy and Home Assistant with ESPHome](https://github.com/sfgabe/OITProjects/tree/master/BabyBuddy_ESP_HASS)
- [Quick Entry Keypad (ESP8266)](https://github.com/sfgabe/OITProjects/tree/master/Baby_Buddy_Keypad)
- [Baby Buddy Keypad (ESP32)](https://github.com/jeroenterheerdt/Baby-Buddy-Keypad)
- [BabyScout](https://github.com/MikeSchapp/BabyScout) - Keypad for recording diaper changes, feedings and sleep to BabyBuddy
- [BabyPod](https://www.printables.com/model/872095-babypod-a-remote-control-for-baby-buddy-for-new-pa) - A remote control for Baby Buddy for new parents (sources: [hardware](https://github.com/skjdghsdjgsdj/babypod-hardware), [software](https://github.com/skjdghsdjgsdj/babypod-software/))
- [MatrixPortal BabyBuddy](https://github.com/skjdghsdjgsdj/matrixportal-babybuddy)

### Mobile

- [Baby Buddy Companion for iOS](https://apps.apple.com/app/id6788966667) ([Source](https://github.com/kguy18/babybuddyios/))
- [Baby Buddy for Android](https://play.google.com/store/apps/details?id=eu.pkgsoftware.babybuddywidgets) ([Source](https://github.com/babybuddy/babybuddy-for-android))
- [iOS shortcuts](https://github.com/babybuddy/babybuddy/discussions/300)
- [Convert exported data from "Baby tracker - feeding, sleep and diaper" mobile app to Baby Buddy](https://github.com/babybuddy/babybuddy/discussions/424)

### Videos

- [Baby Buddy: Keep Records of Your Child/Baby's Growth and Activities](https://www.youtube.com/watch?v=sO6rjn2s6-k)

### Other

- [Grafana Dashboard](https://github.com/babybuddy/babybuddy/discussions/607)
- [Sandstorm app](https://github.com/babybuddy/babybuddy-sandstorm)
- Newborn parenting software series (API, buttons, LCD information screen!)
  - [part 1](https://lutzky.net/2021/10/03/software-parenting-1/)
  - [part 2](https://lutzky.net/2021/10/05/software-parenting-2/)
  - [part 3](https://lutzky.net/2021/10/10/software-parenting-3/)
- [High Level Developer Documentation (AI-Generated)](https://wiki.mutable.ai/babybuddy/babybuddy)
- [Example custom TypeScript frontend](https://github.com/jkjustjoshing/maddie-buddy) (based on [Remix](https://remix.run/))

## 🔐 Reporting Vulnerabilities

See [SECURITY.md](SECURITY.md) for information about where and how to report
potential Baby Buddy vulnerabilities.

## ❤️ Support

### Contribution and sponsorship

Contribute or sponsor Baby Buddy's contributors using any of the following methods:

- [Sponsor @babybuddy on GitHub](https://github.com/sponsors/babybuddy)
- [Sponsor @cdubz on GitHub](https://github.com/sponsors/cdubz)
- [Contribute on Open Collective](https://opencollective.com/babybuddy)

### Tools and infrastructure

The following organizations and services support Baby Buddy contributors in various ways (software licensing, service credits, etc.).

_Some of the links below use referral codes -- all referral proceeds are treated as contributions to the Baby Buddy project._

[![DigitalOcean Referral Badge](https://web-platforms.sfo2.cdn.digitaloceanspaces.com/WWW/Badge%203.svg)](https://www.digitalocean.com/?refcode=dd79e4cfd7b6&utm_campaign=Referral_Invite&utm_medium=Referral_Program&utm_source=badge)
[<img src="https://resources.jetbrains.com/storage/products/company/brand/logos/jb_beam.png" width="100" alt="JetBrains Logo (Main) logo.">](https://www.jetbrains.com/community/opensource/)
[![POEditor](https://poeditor.com/public/images/ui/logos/logo_dark.svg)](https://poeditor.com/)

## Inventory and diaper changes

Inventory tracks shared household supplies, sizes, stock history, and in-app
restock reminders. Under **Manage children → Sizes & diaper supply**, select a
child's supply or size. Automatic matching uses a unique matching shared supply;
an explicit assignment overrides size and age matching. Track diapers individually,
not as packs. Reminders begin at an estimated 14 days of stock remaining, based on
recorded usage. See [Inventory](inventory/README.md) for forecasting details.

Each new diaper-change entry deducts one diaper, including entries marked both wet
and solid. Editing the same child's entry never deducts twice. Reassigning an entry
to another child returns the original diaper and uses the new child's supply;
deleting an entry reverses its deduction. Removing a child's entire history does
not replenish consumed stock. Existing entries are not charged retroactively.
If stock is missing, ambiguous, unavailable, or empty, the care entry still saves
and the web form shows a warning. Restocking later does not retroactively charge
previously skipped entries. Automatic deduction can be turned off per child.

## Additional care features

[Upstream issue follow-up](docs/user-guide/upstream-followup.md) documents equipment
limit alerts, access restricted to selected children, offline care logging,
custom activities, entry preferences, and dashboard/timer API additions.
