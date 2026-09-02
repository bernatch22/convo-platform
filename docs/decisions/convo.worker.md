# `convo.worker`

The reasoning that used to live in the docstrings of `convo/worker.py`; the code keeps one line per symbol.

## module

`python worker.py console` talks to the agent from the laptop microphone
(`--text` for the keyboard); `python worker.py dev` registers against a
LiveKit server. The VAD is loaded once per process in `prewarm`, inside the
10 s budget, and handed to every job that process runs.

Every real job keeps its audio (ms-17): the stereo OGG lands under
`core.recordings.root()`, keyed by session id, and its path is written into
the log as `audio.start` while the call is still going. `--record` is still
the console's own flag, into the framework's `console-recordings/` folder;
`RECORD=0` switches recording off for a whole deploy, and a project can opt
out on its own with `Project.recording = False`.

## audio_destination

A chat session has nothing to record, a project may opt out, and a whole
deploy can say `RECORD=0`. A console run is left exactly as it always was —
`--record` writes into the framework's own `console-recordings/` folder,
because a laptop is not the box and should not quietly fill a recordings
tree. Every other job records by default: the tap was already running in
every job, and `core.recordings.aim` is the one line that stops the file
from dying with the room.

## _report_filer

It must never raise: a report that cannot be built is a warning in the
worker's log, not a job that dies on the way out and loses the outcome too.
