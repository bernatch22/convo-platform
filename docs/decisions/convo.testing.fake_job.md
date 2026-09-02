# `convo.testing.fake_job`

The reasoning that used to live in the docstrings of `convo/testing/fake_job.py`; the code keeps one line per symbol.

## module

`core.router.resolve` reads five things — the job's `id`, `metadata` and
dispatch `attributes`, the SIP `participant.attributes`, and the participants
already in the room — and nothing else. This builds exactly those, as plain
objects, so a test can say "a call to this number on this fleet" in one line.

A real phone call is a **room** job: `job.participant` is empty and the caller
is in the room. `room_participants=` builds that shape; `participant_attributes=`
builds the participant-job shape. Both are real, so both are testable.
