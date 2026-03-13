import requests
import netifaces
import logging
import time
import socket

from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

logger = logging.getLogger(__name__)

class GoProRequest():
  def __init__(self, scheme, ip_address, timeout=20, iface=None, root_ca_filepath=None):
    self.scheme = scheme
    self.ip_address = ip_address
    self.iface = iface
    self.timeout = timeout
    self.root_ca_filepath = root_ca_filepath

  class SourceAddressAdapter(HTTPAdapter):
      def __init__(self, iface, **kwargs):
          self.iface = iface
          super().__init__(**kwargs)

      def init_poolmanager(self, *args, **pool_kwargs):
        def _socket_options():
          # 25 is the constant for SO_BINDTODEVICE on most Linux systems
          opt = [(socket.SOL_SOCKET, 25, self.iface.encode())]
          return opt

        pool_kwargs['socket_options'] = _socket_options()
        return super().init_poolmanager(*args, **pool_kwargs)

  def log_request(self, what, content):
    if logging.getLogger().getEffectiveLevel() > logging.DEBUG:
      c = content
      if c.len() > 512:
        c = "length: " + str(c.len())

      logger.error(f"{what}: content:{c}")

  def get(self, url_path: str, expected_response_code: int = 200, max_retries=1, backoff=0.5):
      r = requests.Response()
      r.status_code = 502 # Bad Gateway by default
      for attempt in range(max_retries):
        session = requests
        if self.iface:
          try:
            session = requests.Session()
            adapter = self.SourceAddressAdapter(iface=self.iface)
            session.mount(f"http://", adapter)
            session.mount(f"https://", adapter)
          except Exception as e:
            self.log_request(f"GoProRequest: {url_path} {self.iface} exception in setting session {e}")
            return r

        self.log_request(f"GoProRequest.get: calling {url_path} {self.iface}")
        r = session.get(f"{self.scheme}://{self.ip_address}{url_path}", timeout=self.timeout, verify=self.root_ca_filepath)
        self.log_request(f"GoProRequest.get() {url_path} {self.iface} Response: {r}", r.content)

        if r.status_code == 500:        # for some reason my gopro hero 12 sometimes returns 500 that are actualy 200
          r.status_code = 200
        if r.status_code == expected_response_code:
          return r
        time.sleep(backoff)

      return r
