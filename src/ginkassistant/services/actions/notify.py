"""Pop a system notification when a reminder/alarm is due.

Desktop platforms get a real OS notification. On Android/iOS this returns
False and the app shows its own in-app dialog instead (see ReminderScheduler).
"""
from .platform_info import current_platform
from ._shell import applescript_str, ps_encoded, ps_str, spawn

WIN_ALARM_WAV = r"C:\Windows\Media\Alarm01.wav"


def notify(title: str, body: str = "", loud: bool = False) -> bool:
    plat = current_platform()
    if plat == "macos":
        sound = "Glass" if not loud else "Sosumi"
        script = (f"display notification {applescript_str(body or title)} "
                  f"with title {applescript_str('Gink')} subtitle {applescript_str(title)} "
                  f"sound name {applescript_str(sound)}")
        return spawn(["osascript", "-e", script])
    if plat == "linux":
        args = ["notify-send", "-a", "Gink"]
        if loud:
            args += ["-u", "critical"]
        return spawn(args + [title, body])
    if plat == "windows":
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$n = New-Object System.Windows.Forms.NotifyIcon;"
            "$n.Icon = [System.Drawing.SystemIcons]::Information;"
            "$n.Visible = $true;"
            f"$n.ShowBalloonTip(10000, {ps_str(title)}, {ps_str(body or title)}, "
            "[System.Windows.Forms.ToolTipIcon]::Info);"
        )
        if loud:
            script += (f"$p = New-Object System.Media.SoundPlayer {ps_str(WIN_ALARM_WAV)};"
                       "$p.PlaySync();")
        script += "Start-Sleep -Seconds 10; $n.Dispose()"
        return spawn(["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                      "-EncodedCommand", ps_encoded(script)])
    return False
