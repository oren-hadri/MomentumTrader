import json
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from momentum_trader.config import ExchangeConfig, DEFAULT_EXCHANGE_CONFIG


class APIClient:
    def __init__(
        self,
        base_url: str,
        prefix_endpoint: str,
        config: ExchangeConfig = DEFAULT_EXCHANGE_CONFIG
    ) -> None:
        self.session = requests.Session()
        retries = Retry(
            total=config.max_retries,
            backoff_factor=config.backoff_factor,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"]
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.base_url = base_url
        self.prefix_endpoint = prefix_endpoint
        self.timeout = config.request_timeout_seconds

    def send_request(
        self,
        method: str,
        endpoint: str,
        body: Optional[dict] = None,
        headers: Optional[dict[str, str]] = None
    ) -> dict[str, Any]:
        url = f"{self.base_url}{self.prefix_endpoint}{endpoint}"
        body_str = json.dumps(body) if body else ""
        try:
            response = self.session.request(
                method,
                url,
                headers=headers,
                data=body_str if body else None,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

