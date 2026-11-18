import io
import urllib.error
import pytest
import instagram_api as api

real_volaj=api._volaj


@pytest.mark.parametrize('status',[400,429,500])
def test_graph_error_preserves_http_status_independently_of_meta_code(monkeypatch,status):
    def fail(*args,**kwargs):
        raise urllib.error.HTTPError('https://graph.example/request',status,'failure',{},io.BytesIO(b'{"error":{"code":4,"message":"rate"}}'))
    monkeypatch.setattr(api.urllib.request,'urlopen',fail)
    with pytest.raises(api.InstagramError) as caught:real_volaj('https://graph.example/request')
    assert caught.value.kod==4
    assert caught.value.http_status==status
