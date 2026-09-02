# `convo.agents.confirm_task`

The reasoning that used to live in the docstrings of `convo/agents/confirm_task.py`; the code keeps one line per symbol.

## module

An `AgentTask` takes the conversation over for as long as it needs: it asks
one question with its own tiny prompt and two tools, and returns a result to
the tool that awaited it. This one returns True or False; on True it has
already minted a `ConfirmationToken` for exactly the call the stage is about
to make, so the guard lets that call — and only that call — through.

A new instance per use: an AgentTask is not re-entrant, and neither is a yes.

Open source note: the question and the two tool docstrings are the only
Spanish in this file; a project in another language passes its own
`instructions` and the tools' behaviour is unchanged.

## ConfirmTask.on_enter

`say`, never `generate_reply`: the task's own chat context is empty
when it starts, and asked to "generate" from nothing the model once
opened with "Disculpe, he recibido una llamada sin contenido…" instead
of the question (ms-4 demo recording, seq 20). The platform rendered
the sentence — day, spoken hour, professional — so it is read as is;
the model's only job here is to classify the answer.
