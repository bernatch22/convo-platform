# `convo.providers`

The reasoning that used to live in the docstrings of `convo/providers/__init__.py`; the code keeps one line per symbol.

## module

One module per capability — `llm`, `stt`, `tts`, `turn` — each exposing a
single factory that reads the project's data and the environment and returns
a configured plugin, or None when the key for it is absent so a text-only
session keeps working on a laptop with nothing but an Anthropic key.

Open source note: swapping a vendor is one file here; nothing in `convo/session`
or in a tenant names a plugin.
