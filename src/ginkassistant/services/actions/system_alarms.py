"""Desktop alarms that ring even when Gink is CLOSED.

  macOS   -> a Reminders.app reminder with an alert at that time
  Windows -> a one-shot Task Scheduler task that plays an alarm + shows a box
  Linux   -> a transient systemd --user timer that fires notify-send

Each returns (ok, detail). If it fails, the caller falls back to Gink's own
in-app scheduler (which only rings while Gink is running) and says so.
"""
from datetime import datetime

from .platform_info import current_platform
from ._shell import applescript_str, ps_encoded, ps_str, run
from .notify import WIN_ALARM_WAV


def schedule(item_id: int, title: str, when: datetime, alarm: bool = True):
    plat = current_platform()
    try:
        if plat == "macos":
            return _macos(title, when)
        if plat == "windows":
            return _windows(item_id, title, when, alarm)
        if plat == "linux":
            return _linux(item_id, title, when)
    except Exception as e:
        return False, str(e)
    return False, "no system scheduler on this platform"


def cancel(item_id: int):
    plat = current_platform()
    if plat == "windows":
        return run(["powershell", "-NoProfile", "-Command",
                    f"Unregister-ScheduledTask -TaskName 'Gink_{item_id}' -Confirm:$false"])
    if plat == "linux":
        return run(["systemctl", "--user", "stop", f"gink-{item_id}.timer"])
    return False, "cancel it in the Reminders app"


def _macos(title, when):
    # Build the date field-by-field: date strings are locale-dependent in AppleScript.
    # Day is set to 1 first so changing month can never overflow (e.g. 31 -> Feb).
    script = f"""
set d to current date
set day of d to 1
set year of d to {when.year}
set month of d to {when.month}
set day of d to {when.day}
set hours of d to {when.hour}
set minutes of d to {when.minute}
set seconds of d to 0
tell application "Reminders"
    make new reminder with properties {{name:{applescript_str(title)}, remind me date:d}}
end tell
"""
    ok, out = run(["osascript", "-e", script])
    return ok, ("added to Reminders" if ok else out)


def _windows(item_id, title, when, alarm):
    inner = ""
    if alarm:
        inner += (f"$p = New-Object System.Media.SoundPlayer {ps_str(WIN_ALARM_WAV)};"
                  "$p.PlayLooping();")
    inner += ("Add-Type -AssemblyName PresentationFramework;"
              f"[System.Windows.MessageBox]::Show({ps_str(title)}, 'Gink') | Out-Null;")
    if alarm:
        inner += "$p.Stop();"
    arg = f"-NoProfile -WindowStyle Hidden -EncodedCommand {ps_encoded(inner)}"
    stamp = when.strftime("%Y-%m-%d %H:%M")
    outer = (
        f"$a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument {ps_str(arg)};"
        f"$t = New-ScheduledTaskTrigger -Once -At ([datetime]::ParseExact({ps_str(stamp)}, "
        "'yyyy-MM-dd HH:mm', [Globalization.CultureInfo]::InvariantCulture));"
        "$s = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable;"
        f"Register-ScheduledTask -TaskName 'Gink_{item_id}' -Action $a -Trigger $t "
        "-Settings $s -Force | Out-Null"
    )
    ok, out = run(["powershell", "-NoProfile", "-EncodedCommand", ps_encoded(outer)], timeout=40)
    return ok, ("scheduled in Windows Task Scheduler" if ok else out)


def _linux(item_id, title, when):
    ok, out = run([
        "systemd-run", "--user", f"--unit=gink-{item_id}",
        f"--on-calendar={when:%Y-%m-%d %H:%M:00}", "--timer-property=AccuracySec=1s",
        "notify-send", "-u", "critical", "-a", "Gink", "Gink", title,
    ])
    return ok, ("scheduled with a systemd user timer" if ok else out)
