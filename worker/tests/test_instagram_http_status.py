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


def test_graph_error_retains_safe_quota_and_retry_metadata(monkeypatch):
    headers={'Retry-After':'900','X-App-Usage':'{"call_count":97,"total_cputime":24}',
             'X-Business-Use-Case-Usage':'{"account":[{"call_count":23,"total_time":100,"estimated_time_to_regain_access":20}]}'}
    def fail(*a,**kw):
        raise urllib.error.HTTPError('https://graph.example/request',400,'failure',headers,io.BytesIO(b'{"error":{"code":4,"message":"rate"}}'))
    monkeypatch.setattr(api.urllib.request,'urlopen',fail)
    with pytest.raises(api.InstagramError) as caught:real_volaj('https://graph.example/request')
    assert caught.value.retry_after_seconds==1200
    assert caught.value.usage=={'call_count':97,'total_cputime':24,'total_time':100}


def test_delivery_freshness_reads_bound_history_but_background_keeps_full_context(monkeypatch):
    from urllib.parse import urlparse,parse_qs
    urls=[]
    monkeypatch.setattr(api,'_volaj',lambda url:urls.append(url) or {})
    api.conversation('test','thread',recent_only=True)
    api.conversation('test','thread')
    fields=[parse_qs(urlparse(u).query)['fields'][0] for u in urls]
    assert 'messages.limit(5)' in fields[0]
    assert 'messages.limit(20)' in fields[1]
    assert all('attachments' in f for f in fields)
