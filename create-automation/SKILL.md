---
name: create-automation
description: >
  Create a scheduled automation (periodic task) for the current HappyCapy session.
  Use this skill when the user asks to schedule a recurring task, set up an automatic
  reminder, create a daily/interval job, automate a workflow on a schedule, or says things
  like "run this every day", "remind me every morning", "do this automatically", "set up a
  cron job", "schedule this", "automate this task", "make this happen every X hours".
  This skill translates the user's intent into a structured automation config and signals
  the HappyCapy UI to open a pre-filled "Create Automation" dialog for the user to review
  and confirm — the user always has the final say before saving.
---

# Create Automation

Help the user set up a recurring scheduled task in HappyCapy by pre-filling the automation
creation dialog with parameters inferred from the conversation.

## What this skill does

1. Understand the user's intent: what to run, how often, when
2. Infer sensible defaults for any missing parameters
3. Call the `create_automation` Bash command to signal the frontend
4. The UI opens a pre-filled dialog — user reviews and clicks Save

The skill does NOT execute the automation itself. It only configures and launches the dialog.

## Step-by-step procedure

### 1. Extract parameters from the conversation

Identify these fields from what the user said:

| Field | Description | Default |
|---|---|---|
| `name` | Short display name | Derive from the task description |
| `message` | The full prompt that will be sent to the agent when the automation runs | Derive from context |
| `schedule_type` | `daily` or `interval` | `daily` if user mentions a specific time; `interval` if they say "every N hours/minutes" |
| `time_of_day` | HH:mm in 24h format (for `daily`) | `09:00` |
| `interval_minutes` | Integer minutes between runs (for `interval`, min 5) | 60 |
| `days_of_week` | JSON array of weekday numbers: 0=Sun, 1=Mon … 6=Sat | `[0,1,2,3,4,5,6]` (every day) |

**Inference rules:**
- "every day at 9am" → `schedule_type=daily`, `time_of_day=09:00`
- "every morning" → `schedule_type=daily`, `time_of_day=09:00`
- "every hour" → `schedule_type=interval`, `interval_minutes=60`
- "every 30 minutes" → `schedule_type=interval`, `interval_minutes=30`
- "weekdays only" → `days_of_week=[1,2,3,4,5]`
- "once a day" with no time mentioned → `schedule_type=daily`, `time_of_day=09:00`
- The `message` should be a complete, standalone prompt — as if the user typed it fresh. Include
  enough context so the agent can act on it without this conversation.

### 2. Call the create_automation command

```bash
create_automation \
  --name "<name>" \
  --message "<message>" \
  --schedule-type "<daily|interval>" \
  --time-of-day "<HH:mm>" \
  --interval-minutes <N> \
  --days-of-week '<[0,1,2,3,4,5,6]>'
```

Only pass `--time-of-day` for `daily` schedules; only pass `--interval-minutes` for `interval` schedules.

**Example — daily at 9am every weekday:**
```bash
create_automation \
  --name "Daily Standup Summary" \
  --message "Summarize yesterday's git commits and open issues, then suggest today's priorities." \
  --schedule-type "daily" \
  --time-of-day "09:00" \
  --days-of-week '[1,2,3,4,5]'
```

**Example — every 2 hours, all days:**
```bash
create_automation \
  --name "Hourly Health Check" \
  --message "Check service health endpoints and report any degraded or down services." \
  --schedule-type "interval" \
  --interval-minutes 120 \
  --days-of-week '[0,1,2,3,4,5,6]'
```

### 3. Confirm to the user

After running the command, tell the user:
- The automation dialog has been opened in the UI with the settings pre-filled
- They should review the details and click **Save** to confirm
- They can adjust any field (name, schedule, message) before saving
- The automation will start running on the next scheduled cycle after saving

Example response:
> I've pre-filled the automation dialog with:
> - **Name:** Daily Standup Summary
> - **Schedule:** Daily at 09:00, Mon–Fri
> - **Prompt:** "Summarize yesterday's git commits..."
>
> Please review the details in the dialog and click **Save** to create it.

## Important notes

- The user must be on a **paid plan** — automations are not available on the Free plan.
  If the user mentions they can't create automations, tell them to upgrade their plan.
- Each session can have at most **one automation**. If the session already has one, the dialog
  will open in edit mode.
- Users can have up to **10 automations** across all sessions.
- The automation runs in the background even when the user is not connected. Results appear
  in the session history when they reconnect.
- Timezone is automatically set to the user's local browser timezone.
