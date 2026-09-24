# First run: this fork on your Windows computer

This guide runs the customized Baby Buddy locally, with no paid service. It is
for trying the app on one computer before configuring household network access.
The computer must stay on for other devices to reach it later.

## If it is already installed

Do not reinstall or create another database. Open the existing Baby Buddy address
and follow the [getting-started guide](../user-guide/getting-started.md). For new
code, use the [backup and update instructions](updating.md).

## Easy Windows installation

1. Download this fork's ZIP from **Code → Download ZIP** on the
   [fix/local-bugs branch](https://github.com/Niu-Kai/babybuddy/tree/fix/local-bugs).
2. Extract the entire ZIP into a folder you will keep. Do not run it inside the ZIP.
3. Double-click **Setup Baby Buddy.cmd**.
4. If Python 3.14 is missing, accept the prompt to install it through Windows
   Package Manager. If that is unavailable, install Python 3.14 from
   [python.org](https://www.python.org/downloads/) and run Setup again.
5. Wait for the dependency installation, then choose your own username and
   password. Passwords must be at least ten characters and pass common-password
   checks. There is no default account or demo data.
6. Double-click **Start Baby Buddy.cmd**. Your browser opens when the app is ready.

Git, Node.js, Docker, a cloud account, and billing are not required for this local
installation. The ZIP includes the built interface. Setup installs hash-verified
Python dependencies into a private `.venv` folder; it does not replace system
Python packages. Internet access is needed for the initial downloads.

The Python bootstrap uses the official Windows Package Manager
[Python 3.14 package](https://github.com/microsoft/winget-pkgs/tree/master/manifests/p/Python/Python/3/14).
Its install prompt applies only when Python is missing. An organization-managed
computer may require its administrator to install prerequisites.

## Starting and stopping

Use **Start Baby Buddy.cmd** on subsequent runs. Keep its window open while using
Baby Buddy. Press **Ctrl+C** to stop. The address is normally
**http://127.0.0.1:8000**; if that port is in use, the launcher finds another free
local port and opens that address instead. It does not stop other programs.

The launcher listens only on this computer and hides development error pages.
This is a local setup, not an internet-facing hosting service or Windows service.
It does not start automatically when Windows boots.

## Interrupted setup or an existing installation

If a download fails or you cancel account creation, keep the folder and run Setup
again. It resumes without deleting the database. Running Setup after completion
leaves the account and data unchanged. A missing database after completed setup
requires restoring a backup; it is not silently replaced.

Setup refuses an existing database it did not create, a `.env` file, or a custom
database configuration. It is **not an upgrade tool**. Keep using the existing
installation and follow [backup and update instructions](updating.md). Never
extract a new ZIP over your only copy of household data.

Keep `.development-secret-key`, `data/`, and any uploaded `media/` private and
backed up. `data/local-setup.json` records setup progress, not passwords. The
signing key is generated separately for each installation.

For developers, the launchers call `scripts/setup_app.py` using
`babybuddy.settings.local`. New installations use Django's standard migrations
rather than the legacy command that creates `admin/admin`. Changes to application
source still require the normal developer build and testing workflow.

## Set up your household

1. Add a child through **Manage children** in the account menu. Add any siblings.
2. In **Settings**, choose your timezone, 12/24-hour format, and separate units
   for liquids, length, weight, and temperature.
3. Use **Edit dashboard** to choose the panels you want. The child selector can
   show one child or compare children side by side.
4. Create a separate account for each caregiver and choose their permissions.
5. If using inventory, add the shared diaper supply and assign a supply or size
   to each child. A diaper change consumes one diaper, even when wet and solid.
6. For offline entry, connect the device to your server first, then enable
   **Settings → Offline access → Enable on this device**.

## Phones and tablets

No separate phone app is required. The address above works only on the computer
running the server; `127.0.0.1` on a phone means the phone itself.

Before phone access, configure a household server address and HTTPS using the
[deployment](deployment.md), [proxy](proxy.md), and [HTTPS](ssl.md) guides. Browser
offline support requires a secure origin (HTTPS, with a localhost exception on
the server computer). A plain HTTP home-network address is not sufficient for
installable/offline browser features. Reopening the app when the server is
reachable triggers pending-entry sync.

The local server is for use on this computer, not internet-facing hosting. The LinuxServer image and upstream demo in other guides run upstream Baby
Buddy and do not automatically include this fork's changes. The Windows launchers install this fork locally; a hosted service is not included.
