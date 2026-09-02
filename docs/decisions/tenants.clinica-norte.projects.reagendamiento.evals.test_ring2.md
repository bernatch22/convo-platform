# `tenants.clinica-norte.projects.reagendamiento.evals.test_ring2`

The reasoning that used to live in the docstrings of `tenants/clinica-norte/projects/reagendamiento/evals/test_ring2.py`; the code keeps one line per symbol.

## module

One test per golden, one live call per test, and each call is the whole
pipeline — ElevenLabs speaks the patient, Soniox hears her, Haiku answers, and
the answer comes back over WebRTC. What is under test is not the model's
wording (ring 1 does that far more cheaply) but the two things only a
microphone can break: an agent talked over mid-sentence, and a patient who
switches into English inside a sentence.

    deepeval test run tenants/clinica-norte/projects/reagendamiento/evals/test_ring2.py

Needs the dev stack up — `docker compose -f infra/compose/dev.yml up`, `uvicorn
api:app --port 8090`, `python worker.py dev` — plus `ANTHROPIC_API_KEY`,
`ELEVENLABS_API_KEY` and `SONIOX_API_KEY`. `CONVO_API` points it at another
control plane; the nightly run uses it to call the box.

Consent is scored on the event log and register on the wire, which is
`core.testing.ring2_goldens`'s doing and worth knowing while reading a failure:
no track carries a tool call, so what the platform DID is a question only the
log can answer.
