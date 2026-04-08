---
name: create-automation
description: >
  Suggest a scheduled automation (periodic task) for the current HappyCapy session.
  Use this skill when the user asks to schedule a recurring task, set up an automatic
  reminder, create a daily/interval job, automate a workflow on a schedule, or says things
  like "run this every day", "remind me every morning", "do this automatically", "set up a
  cron job", "schedule this", "automate this task", "make this happen every X hours".
  This skill outputs an <automation /> tag that the UI renders as a preview card with a
  "Create" button — the user always confirms before the automation is saved.
---

# Create Automation

Help the user set up a recurring scheduled task in HappyCapy by outputting an `<automation />`
tag in your reply. The UI renders it as a card with a **Create** button — the user clicks it
to open a pre-filled dialog and confirm. You do NOT create the automation directly.

## What this skill does

1. Understand the user's intent: what to run, how often, when
2. Infer sensible defaults for any missing parameters
3. Output an `<automation />` tag inline in your conversational reply
4. The UI shows a preview card — user clicks **Create** to open the dialog and save

## Step-by-step procedure

### 1. Extract parameters from the conversation

Identify these fields from what the user said:

| Field | Description | Default |
|---|---|---|
| `name` | Short display name | Derive from the task description |
| `message` | The full prompt sent when the automation runs (must be self-contained) | Derive from context |
| `schedule-type` | `daily` or `interval` | `daily` if user mentions a specific time; `interval` if they say "every N hours/minutes" |
| `time-of-day` | HH:MM in 24h format (for `daily`) | `09:00` |
| `interval-minutes` | Integer minutes between runs (for `interval`) | `60` |
| `days-of-week` | Comma-separated day numbers: 0=Sun, 1=Mon … 6=Sat | Omit for every day |

**Inference rules:**
- "every day at 9am" → `schedule-type="daily"` `time-of-day="09:00"`
- "every morning" → `schedule-type="daily"` `time-of-day="09:00"`
- "every hour" → `schedule-type="interval"` `interval-minutes="60"`
- "every 30 minutes" → `schedule-type="interval"` `interval-minutes="30"`
- "weekdays only" → `days-of-week="1,2,3,4,5"`
- `message` must be complete and standalone — enough context to run without this conversation.

### 2. Output the `<automation />` tag

Include the tag inline in your reply:

```
<automation name="..." message="..." schedule-type="daily|interval" time-of-day="HH:MM" days-of-week="1,2,3,4,5" interval-minutes="60" />
```

Only include `time-of-day` for `daily` schedules; only include `interval-minutes` for `interval` schedules.

**Example — daily at 9am every weekday:**

```
Sure! Here's a weekday morning automation:

<automation name="Daily Standup Summary" message="Summarize yesterday's git commits and open issues, then suggest today's priorities." schedule-type="daily" time-of-day="09:00" days-of-week="1,2,3,4,5" />

Click **Create** on the card above to review the settings and save it.
```

**Example — every 2 hours:**

```
I'll set that up as an interval automation:

<automation name="Hourly Health Check" message="Check service health endpoints and report any degraded or down services." schedule-type="interval" interval-minutes="120" />

Click **Create** on the card above to save it.
```

### 3. Guide the user

After outputting the tag, tell the user:
- Click the **Create** button on the preview card to open the automation dialog
- They can review and adjust any field before saving
- The automation will start running on the next scheduled cycle after saving

## Important notes

- The user must be on a **paid plan** — automations are not available on the Free plan.
- Users can have up to **10 automations** across all sessions.
- The automation runs in the background even when the user is not connected.
- Timezone is automatically set to the user's local browser timezone.
