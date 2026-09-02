# `convo.session.router`

The reasoning that used to live in the docstrings of `convo/session/router.py`; the code keeps one line per symbol.

## module

Four places can name the tenant, read in this order and the first that
answers wins:

1. `ctx.job.metadata` — the dispatcher's JSON (`SessionMeta`): a web token or
   an explicit dispatch names tenant, project and channel outright.
2. `ctx.job.attributes` — `convo.tenant` / `convo.project` (`convo.channel`)
   set on the dispatch by the control plane.
3. the SIP caller's attributes — `sip.trunkPhoneNumber` (the number the
   caller dialled) looked up in the `routes` table for this fleet; a phone
   number is a route, never a project. A call is a *room* job, so the caller
   is found in the room, not on `ctx.job.participant` (`core/sip.py`).
4. the environment — `TENANT` / `PROJECT`, the console's way of choosing. It
   also shortens step 3: with `TENANT` set there is nobody to wait for, so a
   caller already in the room still wins but no budget is spent looking.

The channel travels with the session (voice for SIP, chat when the attributes
say so), never with the project. A tenant whose import failed is simply not in
the registry: unroutable, not fatal.

## resolve

Wired means the tenant's adapters are built, an executor sits over them and
the session log is open: a context handed to a session must be able to run
the tools its project declares, or the model calls into a void.
