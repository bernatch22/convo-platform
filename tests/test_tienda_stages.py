"""The three stages of an order call: identify, resolve the order, say goodbye.

Two rings, cheapest first. The adapters, the guard and the saga are
deterministic and run in milliseconds — they are where "nothing is cancelled
without a yes" and "a shipped order cannot be stopped" are actually proved,
because a refusal that depends on a model changing its mind is not a guarantee.
The tests at the bottom put a real Claude Haiku in front of the prompts and
walk the whole call; they are skipped without a key.

The clinic's suite is `tests/test_stages.py` and the two read almost the same,
which is the point of the milestone: one runtime, two businesses, and the only
files that differ are the ones a customer owns.
"""

import importlib

import pytest

from core import confirm
from core.testing import fake_context, run_conversation
from core.tools.contract import SideEffect
from core.tools.guard import ToolRefused
from core.tools.saga import SagaFailed
from tests.conftest import needs_llm

pytestmark = pytest.mark.unit

TENANT, PROJECT = "tienda-sur", "pedidos"
PACKAGE = f"tenants.{TENANT}.projects.{PROJECT}"
project_module = importlib.import_module(f"{PACKAGE}.project")
stages = importlib.import_module(f"{PACKAGE}.stages")
order_desk = importlib.import_module(f"{PACKAGE}.stages.order_desk")
tools_module = importlib.import_module(f"{PACKAGE}.tools")
orderbook = importlib.import_module(f"tenants.{TENANT}.adapters.orderbook")

PREPARING = "TS-10432"  # Marta Alonso Gil, still in the warehouse: cancellable
SHIPPED = "TS-10433"  # Javier Nieto Salas, already with the carrier
DELIVERED = "TS-10434"  # Lucía Ferrer Blanco, already at the customer's door
LANDLINE = "TS-10435"  # cancellable, but the number on it is a landline: the SMS cannot go out


@pytest.fixture
def tc():
    """A session that has already found Marta's order, which is where OrderDesk begins."""
    return identified_context(PREPARING)


def identified_context(order_id: str):
    """A context past the Identify stage: the order is found and known.

    `prev_agent` matters as much as `customer`: what OrderDesk knows about the
    order arrives as the previous stage's `summary()` in its `on_enter`, and a
    stage entered without one opens by asking for the order number again —
    which is the right behaviour and the wrong test.
    """
    context = fake_context(TENANT, PROJECT)
    context.customer = {"order_id": order_id, **context.adapters["orders"].book[order_id]}
    context.prev_agent = stages.Identify(context)
    return context


def desk(tc) -> "stages.OrderDesk":
    """The OrderDesk stage entered the way a real call enters it: after an identification."""
    return stages.OrderDesk(tc)


def writes(orders) -> list[str]:
    """Only what CHANGED the order system: reads are the model's business, writes are ours.

    `find_order` is asked for freely — the order desk re-reads before every
    answer, and how many times it does so in a turn is a prompt matter, not a
    policy one. What a consent test is about is the writes.
    """
    return [name for name, _ in orders.calls if name != "find_order"]


# --- the shop's systems -----------------------------------------------------


def test_an_order_is_found_by_its_number_however_the_customer_reads_it_out() -> None:
    book = orderbook.seeded()

    assert orderbook.lookup(book, "ts 10432", None)["name"] == "Marta Alonso Gil"
    assert orderbook.lookup(book, "10432", None)["order_id"] == PREPARING
    assert orderbook.lookup(book, None, "600 444 555")["order_id"] == SHIPPED
    assert orderbook.lookup(book, "TS-99999", "699000000") is None


async def test_the_order_system_refuses_to_cancel_anything_that_has_already_shipped(tc) -> None:
    """The rule of the whole project, enforced where it cannot be talked around."""
    orders = tc.adapters["orders"]

    with pytest.raises(ValueError, match="enviado"):
        await orders.execute("cancel_order", {"order_id": SHIPPED})
    with pytest.raises(ValueError, match="entregado"):
        await orders.execute("cancel_order", {"order_id": DELIVERED})

    assert orders.book[SHIPPED]["status"] == "enviado"


async def test_a_cancel_is_undone_by_the_restore_the_spec_names_as_its_compensation(tc) -> None:
    orders = tc.adapters["orders"]

    await orders.execute("cancel_order", {"order_id": PREPARING})
    assert orders.book[PREPARING]["status"] == "cancelado"

    await orders.execute("restore_order", {"order_id": PREPARING})
    assert orders.book[PREPARING]["status"] == "preparando"


async def test_the_sms_gateway_only_writes_to_mobiles(tc) -> None:
    """The demo's deterministic failure: a customer who left a landline on the order."""
    with pytest.raises(ValueError, match="mobile"):
        await tc.adapters["sms"].execute("send_sms", {"phone": "910334455", "text": "hola"})


# --- the guard and the saga -------------------------------------------------


async def test_cancel_order_never_reaches_the_shop_without_a_confirmation_token(tc) -> None:
    orders = tc.adapters["orders"]

    with pytest.raises(ToolRefused, match="no confirmation token"):
        await tc.tools.call("cancel_order", {"order_id": PREPARING})

    assert orders.calls == [], "a refused irreversible call must never reach the adapter"


async def test_a_confirmed_cancellation_stops_the_order_and_writes_to_the_customer(tc) -> None:
    orders, sms = tc.adapters["orders"], tc.adapters["sms"]
    args = {"order_id": PREPARING}
    confirm.mint(tc, "cancel_order", args)

    await order_desk._cancellation(tc, tc.customer, args).run()

    assert [c[0] for c in orders.calls] == ["cancel_order"]
    assert orders.book[PREPARING]["status"] == "cancelado"
    assert sms.sent[0]["to"] == "600222333"
    assert "TS-10432 queda cancelado" in sms.sent[0]["text"]
    assert "74,90 euros" in sms.sent[0]["text"]


async def test_an_sms_that_cannot_be_sent_puts_the_order_back_as_it_was() -> None:
    """The shop's own rule: a cancellation the customer has no proof of is not one."""
    tc = identified_context(LANDLINE)
    orders, sms = tc.adapters["orders"], tc.adapters["sms"]
    args = {"order_id": LANDLINE}
    confirm.mint(tc, "cancel_order", args)

    with pytest.raises(SagaFailed) as failure:
        await order_desk._cancellation(tc, tc.customer, args).run()

    assert failure.value.step == "send_sms"
    assert failure.value.compensated == ["cancel_order"]
    assert [c[0] for c in orders.calls] == ["cancel_order", "restore_order"]
    assert orders.book[LANDLINE]["status"] == "preparando", "the customer still has the order"
    assert sms.sent == [], "nobody is told about a cancellation that did not stand"


async def test_a_compensated_cancellation_spends_the_yes_it_was_given() -> None:
    """Where the shop differs from the clinic, and why the difference is right.

    The clinic's saga fails ON the irreversible step, so the token survives and
    the caller can retry the same hour without being asked again. Here the
    irreversible step SUCCEEDED — the order really was cancelled — and only the
    notice failed, so the token is spent and the compensation put the order
    back. Cancelling again is a new irreversible act on an order that is once
    more in preparation, and it asks the customer for a fresh yes. Nothing in
    the platform had to be told any of this: the guard consumes a token after a
    successful call and the rest follows.
    """
    tc = identified_context(LANDLINE)
    args = {"order_id": LANDLINE}
    token = confirm.mint(tc, "cancel_order", args)

    with pytest.raises(SagaFailed):
        await order_desk._cancellation(tc, tc.customer, args).run()

    assert token.used is True
    assert tc.adapters["orders"].book[LANDLINE]["status"] == "preparando"


def test_every_tool_the_project_can_call_declares_what_it_does_to_the_world() -> None:
    catalog = project_module.PROJECT.tools

    assert catalog.names() == ["cancel_order", "find_order", "restore_order", "send_sms"]
    assert catalog.get("cancel_order").side_effect is SideEffect.IRREVERSIBLE
    assert catalog.get("cancel_order").needs_confirmation() is True
    assert catalog.get("cancel_order").compensation == "restore_order"
    assert catalog.get("find_order").needs_confirmation() is False
    assert catalog.get("find_availability") is None, "the shop has no agenda to consult"


# --- what each stage says, and to whom --------------------------------------


def test_the_confirmation_sentence_names_the_order_and_the_money(tc) -> None:
    """It is read out verbatim, so it has to be a sentence and not a summary of one."""
    said = tools_module.confirmation_question(tc.customer)

    assert said == (
        "Te cancelo entonces el pedido TS-10432, el de 74,90 euros, y el importe te vuelve "
        "por donde lo pagaste. ¿Lo cancelo?"
    )


def test_a_shipped_order_is_refused_with_the_shop_s_own_return_policy() -> None:
    """The refusal and the way out are one sentence: «no se puede» alone is not an answer."""
    tc = identified_context(SHIPPED)

    said = tools_module.cannot_cancel(tc.customer)

    assert "ya no se puede cancelar" in said
    assert tools_module.RETURN_POLICY in said
    assert "30 días" in said


def test_identify_hands_the_next_stage_the_order_but_never_its_state(tc) -> None:
    """Identity travels between stages; status does not — OrderDesk reads that itself."""
    summary = stages.Identify(tc).summary()

    assert "TS-10432" in summary
    assert "Marta Alonso Gil" in summary
    assert "preparando" not in summary
    assert "miércoles 2 de septiembre" not in summary


def test_order_desk_hands_the_farewell_the_cancellation_that_now_exists(tc) -> None:
    stage = desk(tc)
    assert "Todavía no" in stage.summary()

    stage.cancelled = tc.customer
    assert "TS-10432 cancelado" in stage.summary()
    assert "74,90 euros" in stage.summary()


# --- the model --------------------------------------------------------------


@needs_llm
async def test_identifying_the_order_hands_the_call_over_to_the_order_desk() -> None:
    """The transition is an event in the run, not a flag: the test can see it happen."""
    context = fake_context(TENANT, PROJECT)

    conversation = await run_conversation(
        context, ["hola, quería saber de un pedido", "es el TS-10432, mi móvil el 600222333"]
    )

    conversation.results[1].expect.contains_agent_handoff(new_agent_type=stages.OrderDesk)
    assert context.customer["order_id"] == PREPARING


@needs_llm
async def test_nothing_reaches_the_order_system_until_the_customer_says_yes(tc) -> None:
    """The customer asks to cancel, is read the order back, and changes their mind."""
    orders, sms = tc.adapters["orders"], tc.adapters["sms"]

    conversation = await run_conversation(
        tc, ["quiero cancelar el pedido", "no, espera, mejor lo dejo"], desk(tc)
    )

    assert writes(orders) == [], "the order system was written to without a yes"
    assert orders.book[PREPARING]["status"] == "preparando"
    assert sms.sent == []
    assert "cancelo" in conversation.reply(0), "the platform reads the order back itself"


@needs_llm
async def test_a_yes_cancels_the_order_and_writes_to_the_customer(tc) -> None:
    orders, sms = tc.adapters["orders"], tc.adapters["sms"]

    await run_conversation(tc, ["quiero cancelar el pedido", "sí, cancélalo"], desk(tc))

    assert writes(orders) == ["cancel_order"]
    assert orders.book[PREPARING]["status"] == "cancelado"
    assert len(sms.sent) == 1 and sms.sent[0]["to"] == "600222333"


@needs_llm
async def test_a_shipped_order_is_never_cancelled_and_the_return_is_offered_instead(
    judge_llm,
) -> None:
    """What is asserted is the writes and the words, never which tool was reached for.

    Twice in three runs the model called `request_cancellation` and read the
    refusal off it; once it answered from the status it had read seconds
    earlier in the same stage, which is a correct answer too. Nothing is at
    risk either way — a cancellation can only happen through the tool, and the
    order system refuses a shipped order regardless — so pinning the call here
    would fail a build for a defensible reply.
    """
    tc = identified_context(SHIPPED)
    orders, sms = tc.adapters["orders"], tc.adapters["sms"]

    conversation = await run_conversation(tc, ["quiero cancelar el pedido"], desk(tc))

    assert writes(orders) == [], "no saga runs for a shipped order"
    assert orders.book[SHIPPED]["status"] == "enviado"
    assert sms.sent == []
    await final_message_of(conversation).judge(
        judge_llm,
        intent="dice que el pedido ya ha salido y no se puede cancelar, y le ofrece devolverlo "
        "gratis en 30 días; en ningún caso dice que lo haya cancelado",
    )


@needs_llm
async def test_the_order_desk_prompt_is_served_from_the_cache_on_its_second_turn(tc) -> None:
    conversation = await run_conversation(
        tc, ["¿por dónde va mi pedido?", "¿y cuándo me llega?"], desk(tc)
    )

    assert conversation.reply(1)
    assert conversation.cached_prompt_tokens() > 0, (
        "Haiku 4.5 caches prefixes of 4096+ tokens: a cache read of 0 means this stage's "
        "prefix shrank below the floor or something in it changes between turns"
    )


def final_message_of(conversation):
    """The last assistant message of the last turn, ready to hand to a judge."""
    from core.testing import final_message

    return final_message(conversation.results[-1])
