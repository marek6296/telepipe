"""Owner inbox: durable, independent cards; opening never sends to a contact."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from control_bot import ControlBot, KLAVESNICA_AKCIE
from datetime import datetime, timedelta, timezone
from instagram_delivery import InstagramDelivery


def row(n, channel="instagram", contact=None, status="awaiting"):
    contact = contact or str(n)
    return dict(id=f"p{n}", channel=channel,
                conv_key=f"{contact}:a{n}" if channel == "instagram" else contact,
                display_name=f"Contact {contact}", status=status,
                chosen_text="completed" if status == "sent" else None,
                control_msg_id=n, created_at=f"2026-11-16T20:{n:02}:00Z",
                suggestions=[f"reply {n}"], incoming_preview=f"question {n}", hint="")


class Db:
    def __init__(self, rows):
        self.rows = {r["id"]: deepcopy(r) for r in rows}

    async def awaiting_pending(self, channel=""):
        return [deepcopy(r) for r in self.rows.values() if r["status"] == "awaiting"
                and (not channel or r["channel"] == channel)]

    async def get_pending(self, pid):
        return deepcopy(self.rows.get(pid))

    async def resolve_pending(self, pid, status):
        r = self.rows.get(pid)
        if not r or r["status"] != "awaiting":
            return []
        r["status"] = status
        return [deepcopy(r)]

    async def move_pending_card(self, pid, old_mid, new_mid):
        r = self.rows[pid]
        if r["status"] != "awaiting" or r.get("control_msg_id") != old_mid:
            return False
        r["control_msg_id"] = new_mid
        return True

    async def claim_pending(self, pid):
        return bool(await self.resolve_pending(pid, "sent"))

    async def mark_pending(self, pid, status, **fields):
        self.rows[pid].update(status=status, **fields)

    async def replace_suggestions(self, pid, suggestions, hint):
        if self.rows[pid]["status"] == "awaiting":
            self.rows[pid].update(suggestions=suggestions, hint=hint)

    async def incomplete_instagram_claims(self):
        return [deepcopy(r) for r in self.rows.values() if r["channel"] == "instagram"
                and r["status"] == "sent" and r.get("chosen_text") is None]

    async def restore_pending_claim(self, pid, updated_at):
        r = self.rows[pid]
        if r["status"] == "sent" and r.get("chosen_text") is None:
            r["status"] = "awaiting"
            return True
        return False


class Event:
    chat_id = 1
    message_id = 90
    raw_text = "hello"
    reply_to_msg_id = None

    def __init__(self, mid=90, reply_to=None):
        self.message_id, self.reply_to_msg_id = mid, reply_to
        self.edit, self.respond, self.reply, self.answer = (AsyncMock() for _ in range(4))


def bot(rows):
    b = ControlBot.__new__(ControlBot)
    b._db, b._cfg = Db(rows), SimpleNamespace(owner_chat_id=1, name="Model")
    b._cards = {r["control_msg_id"]: r["id"] for r in rows}
    b._chat_ctx, b._wizard, b._awaiting, b._input_prompts = {}, {}, {}, {}
    b._pinned = set()
    b._skuska = SimpleNamespace(bezi=lambda _: False)
    b._client = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(id=100)),
                                edit_message=AsyncMock(), unpin_message=AsyncMock())
    b._pinning_on = AsyncMock(return_value=False)
    b._senders = {c: SimpleNamespace(deliver_text=AsyncMock(return_value=True))
                  for c in ("telegram", "instagram", "fanvue")}
    b._senders["instagram"].approval_state = AsyncMock(return_value="awaiting")
    return b


def data(call):
    return [button.data for line in call.kwargs["buttons"] for button in line]


def choice(n):
    return "0:" + ControlBot._suggestions_version(row(n)["suggestions"])


@pytest.mark.asyncio
async def test_inbox_latest_three_distinct_contacts_and_older_page():
    b = bot([row(1), row(2, "telegram"), row(3, "fanvue"), row(4), row(5, contact="4")])
    ev = Event()
    await b._active_chats(ev)
    buttons = data(ev.edit.call_args)
    assert [x for x in buttons if x.startswith(b"ao:")] == [b"ao:p5", b"ao:p3", b"ao:p2"]
    assert b"aq:1" in buttons
    await b._active_chats(ev, "1")
    assert b"ao:p1" in data(ev.edit.call_args)
    for sender in b._senders.values():
        sender.deliver_text.assert_not_called()


@pytest.mark.asyncio
async def test_inbox_cleans_orphaned_instagram_action_but_keeps_other_contact():
    b = bot([row(1), row(2), row(3, status="sent")])
    b._senders["instagram"].approval_state.side_effect = lambda key: "superseded" if key == "1:a1" else "awaiting"
    ev = Event()
    await b._active_chats(ev)
    assert b._db.rows["p1"]["status"] == "superseded"
    assert b"ao:p2" in data(ev.edit.call_args)
    assert b"ao:p1" not in data(ev.edit.call_args)
    assert b"ao:p3" not in data(ev.edit.call_args)


@pytest.mark.asyncio
async def test_open_restores_current_card_after_restart_and_does_not_send():
    b = bot([row(1)])
    b._cards.clear()
    ev = Event()
    await b._open_active(ev, "p1")
    assert b._db.rows["p1"]["control_msg_id"] == 100
    assert b._cards[100] == "p1"
    assert b._chat_ctx[100]["conv_key"] == "1:a1"
    assert any(x.startswith(b"ap:0") for x in data(b._client.send_message.call_args))
    b._senders["instagram"].deliver_text.assert_not_called()
    # The other card remains independently usable after one is answered.
    await b._route_approval(Event(100), "ap", choice(1))
    b._senders["instagram"].deliver_text.assert_awaited_once_with("1:a1", "reply 1")


@pytest.mark.asyncio
async def test_stale_list_opens_new_version_of_same_contact_only():
    b = bot([row(1, contact="42", status="superseded"), row(2, contact="42"), row(3)])
    await b._open_active(Event(), "p1")
    assert b._cards[100] == "p2"
    assert b._db.rows["p3"]["control_msg_id"] == 3


@pytest.mark.asyncio
async def test_concurrent_claim_prevents_reopening_completed_reply():
    b = bot([row(1)])
    async def send(*args, **kwargs):
        await b._db.claim_pending("p1")
        return SimpleNamespace(id=100)
    b._client.send_message.side_effect = send
    await b._open_active(Event(), "p1")
    assert b._db.rows["p1"]["control_msg_id"] == 1
    assert 100 not in b._cards
    b._senders["instagram"].deliver_text.assert_not_called()


@pytest.mark.asyncio
async def test_two_direct_cards_remain_independent():
    b = bot([row(1), row(2)])
    await b._route_approval(Event(1), "ap", choice(1))
    await b._route_approval(Event(2), "ap", choice(2))
    assert [c.args for c in b._senders["instagram"].deliver_text.await_args_list] == [
        ("1:a1", "reply 1"), ("2:a2", "reply 2")]


@pytest.mark.asyncio
async def test_stale_card_is_closed_instead_of_claimed_or_sent():
    b = bot([row(1)])
    b._senders["instagram"].approval_state.return_value = "superseded"
    await b._route_approval(Event(1), "ap", choice(1))
    b._senders["instagram"].deliver_text.assert_not_called()
    assert b._db.rows["p1"]["status"] == "superseded"


@pytest.mark.asyncio
async def test_input_completion_does_not_clear_second_contact_started_during_llm():
    b = bot([])
    b._awaiting[1] = ("semi_brief", "10")
    async def apply(*args):
        b._awaiting[1] = ("semi_custom", "20")
    b._apply_semi = apply
    await b._on_value(Event())
    assert b._awaiting[1] == ("semi_custom", "20")


@pytest.mark.asyncio
async def test_explicit_reply_to_other_prompt_never_sends_to_last_selected_contact():
    b = bot([])
    b._input_prompts[70] = ("semi_custom", "10")
    b._awaiting[1] = ("semi_custom", "20")
    b._apply_semi = AsyncMock()
    await b._on_value(Event(reply_to=70))
    assert b._apply_semi.await_args.args[1:3] == ("semi_custom", "10")
    assert b._awaiting[1] == ("semi_custom", "20")


@pytest.mark.asyncio
async def test_unknown_explicit_reply_does_not_fall_through_to_other_contact():
    b = bot([])
    b._awaiting[1] = ("semi_custom", "20")
    b._apply_semi = AsyncMock()
    await b._on_value(Event(reply_to=999))
    b._apply_semi.assert_not_called()
    assert b._awaiting[1] == ("semi_custom", "20")


@pytest.mark.asyncio
async def test_recovery_rebuilds_context_and_cleans_stale_cards():
    b = bot([row(1), row(2, "telegram")])
    b._cards.clear()
    b._senders["instagram"].approval_state.return_value = "superseded"
    await b.recover_cards()
    assert 1 not in b._cards
    assert b._chat_ctx[2]["conv_key"] == "2"


def test_keyboard_exposes_active_chats():
    assert KLAVESNICA_AKCIE["📥 Active chats"] == "aq"


@pytest.mark.asyncio
@pytest.mark.parametrize("state,expected", [("approval", "awaiting"), ("cancelled", "superseded"),
                                           ("ready", "sent"), ("sent", "sent"), ("uncertain", "sent")])
async def test_instagram_inbox_checks_durable_action(state, expected):
    db = AsyncMock()
    db.action.return_value = dict(id="a", igsid="42", state=state, source_mid="source",
                                 source_at=datetime.now(timezone.utc).isoformat())
    db.settings.return_value = dict(enabled=True, connected=True, reply_mode="semi")
    db.user.return_value = dict(last_source_mid="source")
    delivery = InstagramDelivery(db, AsyncMock())
    assert await delivery.approval_state("42:a") == expected
    db.change_action.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["expired", "new_source", "wrong_contact"])
async def test_instagram_old_input_is_never_active(change):
    db = AsyncMock()
    action = dict(id="a", igsid="42", state="approval", source_mid="source",
                  source_at=datetime.now(timezone.utc).isoformat())
    if change == "expired":
        action["source_at"] = (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
    if change == "wrong_contact":
        action["igsid"] = "other"
    db.action.return_value = action
    db.settings.return_value = dict(enabled=True, connected=True, reply_mode="semi")
    db.user.return_value = dict(last_source_mid="new" if change == "new_source" else "source")
    assert await InstagramDelivery(db, AsyncMock()).approval_state("42:a") == "superseded"


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["pending", "leased"])
async def test_approved_action_remains_handled_while_worker_defers_or_leases_it(state):
    db = AsyncMock()
    db.action.return_value = dict(id="a", igsid="42", state=state, source_mid="source",
                                 payload={"approved_source_mid": "source"})
    assert await InstagramDelivery(db, AsyncMock()).approval_state("42:a") == "sent"


@pytest.mark.asyncio
async def test_ig_completion_returns_to_inbox_not_same_action_composer():
    b = bot([row(1)])
    ev = Event(1)
    await b._route_approval(ev, "ap", choice(1))
    assert b"an" not in data(ev.edit.call_args)
    assert b"aq" in data(ev.edit.call_args)


@pytest.mark.asyncio
async def test_ig_approval_exception_recovers_only_after_reading_action_state():
    b = bot([row(1)])
    b._senders["instagram"].deliver_text.side_effect = RuntimeError("database temporarily unavailable")
    ev = Event(1)
    await b._route_approval(ev, "ap", choice(1))
    assert b._db.rows["p1"]["status"] == "awaiting"
    assert 1 in b._cards


@pytest.mark.asyncio
async def test_ig_approval_unknown_result_does_not_get_replayed():
    b = bot([row(1)])
    b._senders["instagram"].deliver_text.side_effect = RuntimeError("response lost")
    b._senders["instagram"].approval_state.side_effect = ["awaiting", "sent"]
    await b._route_approval(Event(1), "ap", choice(1))
    assert b._db.rows["p1"]["status"] == "sent"
    b._senders["instagram"].deliver_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_navigation_cancels_explicit_input_prompt_too():
    b = bot([])
    b._awaiting[1] = ("semi_custom", "20")
    b._input_prompts[70] = ("semi_custom", "20")
    await b._active_chats(Event())
    b._apply_semi = AsyncMock()
    await b._on_value(Event(reply_to=70))
    b._apply_semi.assert_not_called()


@pytest.mark.asyncio
async def test_explicit_reply_still_works_for_regular_setting():
    b = bot([])
    b._awaiting[1] = ("persona", "name")
    b._apply_value = AsyncMock(return_value="saved")
    await b._on_value(Event(reply_to=70))
    b._apply_value.assert_awaited_once_with("persona", "name", "hello")


@pytest.mark.asyncio
async def test_old_number_button_never_sends_a_regenerated_different_text():
    b = bot([row(1)])
    await b._open_active(Event(), "p1")
    callback = next(x for x in data(b._client.send_message.call_args) if x.startswith(b"ap:0"))
    b._db.rows["p1"]["suggestions"] = ["a different reply"]
    await b._route(Event(100), callback.decode())
    b._senders["instagram"].deliver_text.assert_not_called()
    assert b._db.rows["p1"]["status"] == "awaiting"


@pytest.mark.asyncio
async def test_say_this_does_not_resurrect_a_concurrently_approved_card():
    b = bot([row(1)])
    b._senders["instagram"].regenerate = AsyncMock(return_value={"suggestions": ["new"]})
    async def send(*args, **kwargs):
        await b._db.claim_pending("p1")
        return SimpleNamespace(id=100)
    b._client.send_message.side_effect = send
    await b._new_suggestions(1, "p1", row(1), brief="hi", nova_sprava=True)
    assert b._db.rows["p1"]["status"] == "sent"
    assert b._db.rows["p1"]["control_msg_id"] == 1
    assert 100 not in b._cards


@pytest.mark.asyncio
async def test_temporary_db_outage_does_not_permanently_hide_unapproved_card():
    b = bot([row(1)])
    sender = b._senders["instagram"]
    sender.deliver_text.side_effect = RuntimeError("outage")
    sender.approval_state.side_effect = ["awaiting", RuntimeError("outage")]
    with pytest.raises(RuntimeError):
        await b._route_approval(Event(1), "ap", choice(1))
    assert b._db.rows["p1"]["status"] == "sent"
    # The grace period has passed and the database is healthy again.
    sender.approval_state.side_effect = None
    sender.approval_state.return_value = "awaiting"
    assert [r["id"] for r in await b._active_rows()] == ["p1"]
    sender.deliver_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_incomplete_claim_with_approved_action_is_never_restored():
    b = bot([row(1, status="sent")])
    b._db.rows["p1"]["chosen_text"] = None
    b._senders["instagram"].approval_state.return_value = "sent"
    assert await b._active_rows() == []
    assert b._db.rows["p1"]["status"] == "sent"


@pytest.mark.asyncio
async def test_two_prompt_responses_can_finish_in_reverse_order():
    b = bot([])
    a, second = Event(10), Event(20)
    gate = asyncio.Event()
    async def delayed(*args, **kwargs):
        await gate.wait()
        return SimpleNamespace(id=70)
    a.respond.side_effect = delayed
    second.respond.return_value = SimpleNamespace(id=71)
    task = asyncio.create_task(b._ask_semi(a, "semi_custom", 10, "write"))
    await asyncio.sleep(0)
    await b._ask_semi(second, "semi_custom", 20, "write")
    gate.set()
    await task
    assert b._input_prompts[70] == ("semi_custom", "10")
    assert b._input_prompts[71] == ("semi_custom", "20")


@pytest.mark.asyncio
async def test_cancelled_prompt_cannot_reappear_after_slow_telegram_response():
    b = bot([])
    event = Event()
    gate = asyncio.Event()
    async def delayed(*args, **kwargs):
        await gate.wait()
        return SimpleNamespace(id=70)
    event.respond.side_effect = delayed
    task = asyncio.create_task(b._ask_semi(event, "semi_custom", 10, "write"))
    await asyncio.sleep(0)
    await b._active_chats(Event())
    gate.set()
    await task
    assert b._input_prompts == {}
    assert b._awaiting == {}


@pytest.mark.asyncio
async def test_legacy_number_button_refreshes_before_any_send():
    b = bot([row(1)])
    ev = Event(1)
    await b._route_approval(ev, "ap", "0")
    b._senders["instagram"].deliver_text.assert_not_called()
    assert ("ap:" + choice(1)).encode() in data(ev.edit.call_args)
    await b._route_approval(ev, "ap", choice(1))
    b._senders["instagram"].deliver_text.assert_awaited_once_with("1:a1", "reply 1")
