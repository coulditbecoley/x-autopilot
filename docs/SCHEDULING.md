# Scheduling

Replace `PYTHON` with the absolute path to Python (`where.exe python` on Windows, `which python3` elsewhere) and `REPO` with the absolute path to this folder. Times are the machine's local time.

## Windows (Task Scheduler)

Run in PowerShell as the user who will own the tasks:

```powershell
$py   = "PYTHON"
$repo = "REPO"
function Add-XTask($name, $jobArgs, $trigger) {
  $action = New-ScheduledTaskAction -Execute $py -Argument "`"$repo\run.py`" $jobArgs" -WorkingDirectory $repo
  $set = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
  Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $set -Force | Out-Null
}
# news: every 2 hours from 08:15 to 20:15
$t = New-ScheduledTaskTrigger -Daily -At 08:15
$t.Repetition = (New-ScheduledTaskTrigger -Once -At 08:15 -RepetitionInterval (New-TimeSpan -Hours 2) -RepetitionDuration (New-TimeSpan -Hours 12)).Repetition
Add-XTask "x-autopilot news"    "news"    $t
Add-XTask "x-autopilot replies" "replies" (New-ScheduledTaskTrigger -Daily -At 08:00)
Add-XTask "x-autopilot build"   "build"   (New-ScheduledTaskTrigger -Daily -At 13:00)
Add-XTask "x-autopilot long"    "long"    (New-ScheduledTaskTrigger -Daily -At 09:15)
```

Only register the jobs that are enabled in `config.json`. `StartWhenAvailable` runs a missed job once the PC wakes; the posting-hours check stops a late news post. To pause, disable the task in Task Scheduler.

To run without a console window flashing, use `pythonw.exe` instead of `python.exe` (logs still go to `state/run.log`).

## macOS and Linux (cron)

`crontab -e`, then (keep the quotes if a path has spaces):

```cron
15 8-20/2 * * *  cd "REPO" && "PYTHON" run.py news    >> state/cron.log 2>&1
0  8      * * *  cd "REPO" && "PYTHON" run.py replies >> state/cron.log 2>&1
0  13     * * *  cd "REPO" && "PYTHON" run.py build   >> state/cron.log 2>&1
15 9      * * *  cd "REPO" && "PYTHON" run.py long    >> state/cron.log 2>&1
```

cron has a minimal PATH. With `llm.provider` `claude-cli`, add a `PATH=` line at the top of the crontab that includes the folder where `claude` lives (`which claude`). On macOS, cron may need Full Disk Access to read notes in protected folders, or use a launchd agent instead.

## A server

Any always-on Linux box works with the cron lines above. Use `anthropic` or `openai` as the provider there, since CLI logins expire. Copy `.env` with `scp`, never through git.

## Not recommended: GitHub Actions

The jobs keep state (`state/covered.json` stops the same story posting twice, `state/build_log.json` stops angles repeating). A fresh Actions runner loses it every run, and scheduled Actions on a private repo bill minutes. Use a machine you own.
