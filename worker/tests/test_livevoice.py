"""Hlasovka na mieru — smie zlyhať, nesmie zdržať ani poslať nezmysel."""
import random

import livevoice as L


class TestCoSaOplatiPovedat:
    def test_bezna_odpoved_ano(self):
        assert L.worth_speaking("haha thats so true, i was just thinking about that all day honestly")

    def test_prilis_kratke_nie(self):
        assert not L.worth_speaking("haha yeah")

    def test_prilis_dlhe_nie(self):
        assert not L.worth_speaking("a" * 400)

    def test_odkaz_sa_nehovori_nahlas(self):
        assert not L.worth_speaking("check my page here https://www.fanvue.com/sima.sima babe love")
        assert not L.worth_speaking("the good stuff is all on my fanvue if u wanna see more of me")


class TestAkoCasto:
    def test_nie_na_kazdu_spravu(self):
        nikdy = random.Random(); nikdy.random = lambda: 0.99
        assert not L.should_speak("haha thats so true i was thinking about it all day", nikdy)

    def test_obcas_ano(self):
        vzdy = random.Random(); vzdy.random = lambda: 0.0
        assert L.should_speak("haha thats so true i was thinking about it all day", vzdy)
