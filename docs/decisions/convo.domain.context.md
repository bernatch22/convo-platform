# `convo.domain.context`

The reasoning that used to live in the docstrings of `convo/domain/context.py`; the code keeps one line per symbol.

## module

One definition, built once per job by `core.router.resolve`, carried as the
session's `userdata` and reachable from every tool as `ctx.userdata`.

## Tenant.build_adapters

A tenant that has none keeps the default: it simply cannot run tools.
Subclasses in `tenants/<id>/tenant.py` override it — core never imports
a customer's code, so the factory has to travel on the tenant itself.

## Project

`messages` overrides the platform's user-facing tool-failure sentences
(`core.tools.messages`) in the project's own register and language.
`backchannels` overrides the murmurs a barge-in filter ignores
(`core.barge_in.SPANISH_BACKCHANNELS`) — data, so core knows one language.
`stt_gate` overrides how much voiced audio a transcript must have behind it
to be believed (`core.stt_gate.GateOptions`), for a tenant on a noisier line.

The fields named in `core.state.overrides.OVERRIDABLE` are the ones a
supervisor may change from the console without a deploy: `core.state.overrides`
replaces them on the way out of the router (`core.state.store.PipelineOverride`).
`llm_model` is which model answers for this project. The LLM is a swappable
interface driver, so it is project data like the voice and not a constant in
`core/providers`, and an eval can measure a second model on the same goldens
(`core.testing.report --model`) without editing one of them.
`scoring` is the post-call score's opt-out (ms-13). A project that sets it
to False is never judged after a call ends and its sessions show a dash
where the others show a chip — which is a business decision (a queue whose
calls are two sentences long, a tenant that has not agreed to it), so it
lives with the project's data and not in an environment variable.
`transfer_number` is where the agent hands a call when the caller asks for a
person (ms-20). It is project data and overridable, like the voice: which
phone a reception overflows to changes far more often than a deploy does.
Empty means the model is never offered `transfer_to_human` at all — the
tool that cannot work is not offered, `core.telephony.human`.
`recording` is the same shape of decision about the call's AUDIO (ms-17):
False and no OGG is ever written for this project, so its sessions show no
player. It is deliberately not one flag with `scoring` — a tenant may want
its calls judged without keeping a recording of the caller's voice.

## Project.knowledge

Git is the seed every deploy carries; a row in `project_versions` can
override it without a deploy, and the version the session ran with is
in its first log event either way.

## TenantContext

`today` is the calendar day the conversation happens on. It lives here and
never in the system prompt: Haiku 4.5 only caches a prefix of 4096+ tokens
and only while that prefix is byte-identical, so a date in the instructions
would throw the cache away on every new day. Tools that read "el jueves"
resolve it against this instead.

`pii_values` is the session's own PII, learned by the executor from the
`pii_scope` arguments of every tool call and from `customer`. It is what
lets a log line mask a name that arrived inside a free-text argument no
contract describes — see `core.tools.guard.mask`.
