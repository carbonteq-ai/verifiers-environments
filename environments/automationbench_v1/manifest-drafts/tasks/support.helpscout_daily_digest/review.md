# support.helpscout_daily_digest Luna partial manifest review

Luna official outcome: **official_partial**, score **0.846154**. The score is retained as recorded; it is not replaced by this draft's findings.

Coverage: **2/4** expressible task obligations; 2 gaps, 1 out of scope. Status: **not_qualified**.

Native replay: errors=0, rescore_equal=True, reload_equal=True, scalar_unchanged=True, episode_bytes_unchanged=True. Findings: daily-digest=valid:1.0, daily.digest=valid:1.0, daily.digest.coverage=valid:1.0, escalation-digest=valid:1.0, escalation.digest=valid:1.0, escalation.digest.coverage=valid:1.0.

Original Luna assertion misses (inspection aid only; not used to define checks): slack_message_not_in_channel, slack_message_not_in_channel, slack_message_not_in_channel, slack_message_not_in_channel.


Synthetic simulator alternatives used genuine local handlers over the exact retained `task.data.initial_state` and returned tool arguments. They are focused tests of the expressed checks, not new model responses or whole-task qualifications.

- **correct** via `slack_send_channel_message` (operation 3): daily-digest: values=[1.0], statuses={'valid': 2}; escalation-digest: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **harm** via `slack_send_channel_message` (operation 3): daily-digest: values=[0.0], statuses={'valid': 2}; escalation-digest: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **missing_ack** via `slack_send_channel_message` (operation 3): daily-digest: values=none, statuses={'abstained': 2}; escalation-digest: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **gaming** via `slack_send_channel_message` (operation 3): daily-digest: values=[1.0], statuses={'valid': 2}; escalation-digest: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.
- **duplicate** via `slack_send_channel_message` (operation 3): daily-digest: values=[1.0], statuses={'valid': 2}; escalation-digest: values=[1.0], statuses={'valid': 2}; errors=0; scalar rewards unchanged=True.

