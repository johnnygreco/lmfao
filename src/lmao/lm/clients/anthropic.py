from typing import NamedTuple, Optional

from lmao.lm.clients.base import SUCCESS_STATUS_CODE, BaseClient, ChatHistory, ClientResponse
from lmao.lm.schemas.anthropic import AnthropicCompleteSchema

__all__ = ["AnthropicClient", "AnthropicChatHistory"]


class Schema(NamedTuple):
    complete: dict


class AnthropicChatHistory(ChatHistory):
    def append(self, role: str, content: str):
        self._messages.append(self.check_message_format({"role": role, "content": content}))

    @staticmethod
    def check_message_format(message):
        if not isinstance(message, dict):
            raise ValueError(f"Message must be a dict, not {type(message)}.")
        if "role" not in message:
            raise ValueError("Message must have a 'role' key.")
        if "content" not in message:
            raise ValueError("Message must have a 'content' key.")
        return message

    def to_prompt(self, end_with_assistant_prompt: bool = True) -> str:
        chat = "\n\n".join([f"{message['role'].title()}: {message['content']}" for message in self._messages])
        if end_with_assistant_prompt:
            chat += "\n\nAssistant:"
        return chat

    def to_request_format(self):
        return self.to_prompt(end_with_assistant_prompt=True)


class AnthropicClient(BaseClient):
    base_url = "https://api.anthropic.com"
    api_env_name = "ANTHROPIC_API_KEY"
    api_header_format = "x-api-key"

    schema = Schema(complete=AnthropicCompleteSchema.schema()["properties"])

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key)

    def complete(self, prompt: str, **kwargs) -> ClientResponse:
        status_code, response = self._post_request(
            "v1/complete",
            AnthropicCompleteSchema(prompt=prompt, **kwargs).to_request_dict(),
        )
        return ClientResponse(
            text=response["completion"] if status_code == SUCCESS_STATUS_CODE else None,
            raw_response=response,
            status_code=status_code,
        )
