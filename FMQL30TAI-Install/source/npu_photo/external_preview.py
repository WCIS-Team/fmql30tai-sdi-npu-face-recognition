"""Small status requests plus direct browser redirects; no image proxying."""
import ipaddress
import json
from urllib.parse import urlsplit
from urllib.request import build_opener,HTTPRedirectHandler,ProxyHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*_args,**_kwargs):
        return None


def lan_origin(url):
    value=urlsplit(url)
    if (value.scheme!='http' or value.username is not None or value.password is not None
            or value.path not in ('','/') or value.query or value.fragment):
        raise ValueError('PL preview needs an HTTP origin with no credentials or path')
    address=ipaddress.IPv4Address(value.hostname)
    if not address.is_private or address.is_unspecified or address.is_multicast:
        raise ValueError('PL preview must use an explicit LAN IPv4 address')
    port=value.port
    if port is None or not 1<=port<=65535:raise ValueError('PL preview port is required')
    return f'http://{address}:{port}'


class ExternalPreview:
    def __init__(self,url,*,browser_url=None):
        self.origin=lan_origin(url)
        # The PS may reach a LAN address while a remote browser uses a tunnel.
        # Image bytes still travel directly from the receiver to that browser.
        self.browser_origin=lan_origin(browser_url) if browser_url else self.origin
        self.opener=build_opener(ProxyHandler({}),NoRedirect())

    def stream(self):return self.browser_origin+'/stream.mjpg'
    def snapshot(self):return self.browser_origin+'/snapshot.jpg'

    def read_status(self):
        with self.opener.open(self.origin+'/api/status',timeout=1) as response:
            if response.status!=200:raise ValueError('PL preview status unavailable')
            data=response.read(16385)
        if len(data)>16384:raise ValueError('PL preview status is too large')
        value=json.loads(data)
        if (not isinstance(value,dict) or value.get('transport')!='PL_JPEG_WJP1_UDP'
                or (value.get('width'),value.get('height'))!=(1920,1080)
                or value.get('transcoding') is not False or not isinstance(value.get('ready'),bool)):
            raise ValueError('PL preview source has the wrong contract')
        return value
