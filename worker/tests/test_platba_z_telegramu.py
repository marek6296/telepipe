"""Platba na Fanvue spojená s telegramovou konverzáciou.

Odkaz si so sebou nesie, komu bol poslaný (`checkout.attributed`) — len sa to
na druhej strane doteraz nikdy nečítalo. Klient tak nemal ako zistiť, či mu to
písanie zarába.
"""
import checkout


def _event(ref=None, kde="data"):
    data = {"fan": {"uuid": "u-1", "handle": "ruto"}, "amount": 1200}
    payload = {"data": data}
    event = {"type": "creator.payment.succeeded", "payload": payload}
    if ref is not None:
        {"data": data, "payload": payload, "event": event}[kde][
            "client_reference_id"
        ] = ref
    return event


class TestSpojenie:
    def test_z_data(self):
        assert checkout.z_udalosti(_event("tg-555")) == 555

    def test_z_payloadu(self):
        assert checkout.z_udalosti(_event("tg-555", kde="payload")) == 555

    def test_z_vrchu_udalosti(self):
        assert checkout.z_udalosti(_event("tg-555", kde="event")) == 555

    def test_camel_case(self):
        event = _event()
        event["payload"]["data"]["clientReferenceId"] = "tg-777"
        assert checkout.z_udalosti(event) == 777

    def test_bez_referencie(self):
        assert checkout.z_udalosti(_event()) is None

    def test_cudzia_referencia_sa_nehada(self):
        """Ručne vyplnené `client_reference_id` nie je naše id."""
        assert checkout.z_udalosti(_event("objednavka-42")) is None

    def test_rozbita_referencia(self):
        assert checkout.z_udalosti(_event("tg-abc")) is None

    def test_prazdna_udalost_nespadne(self):
        assert checkout.z_udalosti({}) is None
        assert checkout.z_udalosti({"payload": None}) is None


class TestOkruh:
    def test_odkaz_a_spat(self):
        """Čo `attributed` do odkazu vloží, to sa musí dať prečítať späť."""
        odkaz = checkout.attributed("https://fanvue.com/simona", 424242)
        assert "client_reference_id=tg-424242" in odkaz
        event = _event("tg-424242")
        assert checkout.z_udalosti(event) == 424242
