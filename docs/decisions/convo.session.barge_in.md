# `convo.session.barge_in`

The reasoning that used to live in the docstrings of `convo/session/barge_in.py`; the code keeps one line per symbol.

## module

A caller who says "vale" while the agent is mid-sentence is agreeing, not
taking the floor. LiveKit's own filter is `InterruptionOptions.min_words`,
which is a word COUNT and runs before the interruption is made — it catches
"vale" and "mm" and lets "vale vale" and "sí sí" straight through. This module
is the second net: it knows WHICH words a Spanish speaker murmurs.

Where each net sits in 1.7.1, verified in `voice/agent_activity.py`:

  `_user_turn_committed` (line ~2461)   `min_words` — BEFORE the interruption.
                                        The turn is discarded whole: no reply,
                                        and the agent never stops talking.
  `_cancel_speech_pause` (line ~2566)   the paused speech is interrupted here.
  `on_user_turn_completed` (line ~2588) our stoplist — StopResponse cancels the
                                        REPLY, and nothing else.

So a multi-word murmur still cuts the agent's audio; what this saves is the
answer to it, which on a phone call is the part the caller actually hears as a
mistake. Upstream has no hook to un-interrupt a speech that was already cut:
the only resume path is `resume_false_interruption`, and `_user_turn_committed`
cancels its timer for any turn that is going to reply. Documented on the card.

Open source note: the list is data. A project sets `Project.backchannels` and
`convo/` never learns another language.

## holds_the_floor

`current_speech` is the handle the activity is playing out. It survives the
interruption that `_cancel_speech_pause` makes just before
`on_user_turn_completed` — the scheduling task nils it later — so a turn
that barged in still sees it, and a turn that arrived into silence sees
None. That ordering is a race we lose on a fast machine, which is exactly
why `min_words=2` stays the primary filter and this one is the second.
