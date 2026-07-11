# contextWhere schedules

Windows 11 is the primary target. Ubuntu is supported. macOS is deferred.

## Windows 11

Preview:

```powershell
contextwhere autostart plan --json
```

Install:

```powershell
contextwhere autostart install
```

This registers a Windows Task Scheduler task named `contextWhereMaintain` that runs `contextwhere maintain --json`. It does not run live provider search and it is not a daemon.

## Ubuntu

Preview and install use the same CLI:

```bash
contextwhere autostart plan --json
contextwhere autostart install
```

Ubuntu uses a user-level systemd timer named `contextwhere-maintain.timer`.

## Principles

- Raw providers stay read-only.
- Automatic execution defaults to `maintain` only.
- `wiki apply` is never automatic.
- Back up `.contextwhere/contextwhere.sqlite3`, `.contextwhere/audit/wiki/`, and `work_wiki/` together.
