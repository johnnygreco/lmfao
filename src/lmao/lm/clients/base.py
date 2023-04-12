from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod, abstractstaticmethod
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, List, NamedTuple, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3 import Retry

__all__ = ["ClientResponse", "BaseClient", "ChatHistory", "SUCCESS_STATUS_CODE"]


class APIHeader(NamedTuple):
    key: str
    value: Callable


SUCCESS_STATUS_CODE = 200
API_HEADER_FORMAT_DICT = {
    "x-api-key": APIHeader(key="X-API-Key", value=lambda api_key: api_key),
    "basic authentication": APIHeader(key="Authorization", value=lambda api_key: f"Basic {api_key}"),
    "bearer authentication": APIHeader(key="Authorization", value=lambda api_key: f"Bearer {api_key}"),
}


@dataclass
class ClientResponse:
    text: Optional[str]
    raw_response: dict
    status_code: int

    def __repr__(self):
        repr = "\n".join([f"{k}: {v}" for k, v in self.__dict__.items()])
        repr = re.sub(r"^", " " * 4, repr, 0, re.M)
        return f"{self.__class__.__name__}({{\n{repr}\n}})"


class ChatHistory(ABC):
    human_role: str = "human"
    assistant_role: str = "assistant"

    def __init__(self, max_length: int = 10):
        self.max_length = max_length
        self._messages: Deque = deque(maxlen=max_length)

    @abstractstaticmethod
    def check_message_format(message):
        pass

    @abstractmethod
    def to_request_format(self):
        pass

    def add_assistant_message(self, message: str):
        self.append(role=self.assistant_role, content=message)

    def add_human_message(self, message: str):
        self.append(role=self.human_role, content=message)

    def append(self, role: str, content: str):
        self._messages.append(self.check_message_format({"role": role, "content": content}))

    def clear(self):
        self._messages.clear()

    @property
    def messages(self):
        return list(self._messages)

    @messages.setter
    def messages(self, messages):
        self._messages = [self.check_message_format(m) for m in messages]

    def __iter__(self):
        return iter(self._messages)

    def __len__(self):
        return len(self._messages)

    def __repr__(self):
        repr = "\n".join([str(m) for m in self._messages])
        repr = "\n" + re.sub(r"^", " " * 4, repr, 0, re.M) + "\n" if len(self._messages) > 0 else ""
        return f"{self.__class__.__name__}([{repr}])"


class LM(ABC):
    @abstractmethod
    def complete(self, prompt: str, **kwargs) -> ClientResponse:
        pass


class BaseClient(LM, ABC):
    base_url: str = "none"
    api_env_name: str = "none"
    api_header_format: str = "none"

    #  If the backoff_factor is 0.1, then sleep() will sleep for [0.0s, 0.2s, 0.4s, …] between retries.
    RETRY_BACKOFF_FACTOR: float = 0.1
    RETRY_STATUS_CODES: List[int] = [429, 500, 502, 503, 504]

    def __init__(self, api_key: Optional[str] = None, max_retries: int = 5):
        self.max_retries = max_retries
        self.__api_key = api_key or os.environ.get(self.api_env_name)
        if self.__api_key is None:
            raise ValueError("You must provide an API key or set api_env_name to initialize an LM Client.")
        if self.base_url == "none":
            raise ValueError("Client subclasses must define a base URL attribute.")
        if self.api_header_format not in API_HEADER_FORMAT_DICT:
            raise ValueError(f"Client subclasses must have api_header_format in {list(API_HEADER_FORMAT_DICT.keys())}")
        self._api_header = API_HEADER_FORMAT_DICT[self.api_header_format]

    def _post_request(self, api_path: str, request: dict, extra_headers: Optional[dict] = None) -> Tuple[int, dict]:
        with requests.Session() as session:
            retries = Retry(
                total=self.max_retries,
                backoff_factor=self.RETRY_BACKOFF_FACTOR,
                status_forcelist=self.RETRY_STATUS_CODES,
            )
            session.mount("https://", HTTPAdapter(max_retries=retries))
            session.mount("http://", HTTPAdapter(max_retries=retries))
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                self._api_header.key: self._api_header.value(self.__api_key),
            }
            headers.update(extra_headers or {})
            if self.__api_key not in headers.values():
                headers["Authorization"] = f"Bearer {self.__api_key}"

        response = requests.post(url=f"{self.base_url}/{api_path}", json=request, headers=headers)
        status_code = response.status_code
        try:
            response_dict = response.json()
        except requests.exceptions.JSONDecodeError:
            response_dict = {}
            status_code = 500 if status_code != SUCCESS_STATUS_CODE else status_code
        return status_code, response_dict
