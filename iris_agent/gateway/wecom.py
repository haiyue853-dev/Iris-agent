"""WeCom (企业微信) adapter: active push + callback reception.

Receiving messages requires the WeCom self-built app callback URL, which WeCom
only delivers to a publicly reachable HTTPS endpoint.  The adapter therefore
implements the full callback protocol (signature verification + AES-256-CBC
decryption) so it works the moment a public/forwarded URL is configured, while
*active push* (``message/send``) works from a local machine with no public
address.  Replies are delivered by active push, not the synchronous callback
response, because the agent may take longer than WeCom's 5-second window.
"""

from __future__ import annotations

import base64
import hashlib
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import httpx
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from iris_agent.gateway.base import InboundMessage
from iris_agent.gateway.service import GatewayService

_WECOM_API = "https://qyapi.weixin.qq.com/cgi-bin"


class WeComCryptError(ValueError):
    """Callback signature verification or decryption failed."""


@dataclass(slots=True)
class WeComCrypt:
    """Sign/verify and AES-decrypt WeCom callback payloads (PKCS#7, CBC)."""

    token: str
    aes_key: str  # 43-char EncodingAESKey
    corp_id: str
    _key: bytes = field(init=False, repr=False)

    def __post_init__(self) -> None:
        key = self.aes_key + "=" * (4 - len(self.aes_key) % 4 if len(self.aes_key) % 4 else 0)
        self._key = base64.b64decode(key)
        if len(self._key) != 32:
            raise WeComCryptError("EncodingAESKey 必须解码为 32 字节")

    def verify_signature(self, signature: str, timestamp: str, nonce: str, encrypt: str) -> bool:
        items = sorted([self.token, timestamp, nonce, encrypt])
        digest = hashlib.sha1("".join(items).encode("utf-8")).hexdigest()
        return digest == signature

    def decrypt(self, encrypt: str) -> str:
        try:
            cipher = AES.new(self._key, AES.MODE_CBC, self._key[:16])
            plaintext = unpad(cipher.decrypt(base64.b64decode(encrypt)), AES.block_size)
        except (ValueError, KeyError) as exc:
            raise WeComCryptError("回调消息解密失败") from exc
        if len(plaintext) < 20:
            raise WeComCryptError("回调消息长度非法")
        message_len = int.from_bytes(plaintext[16:20], "big")
        message = plaintext[20 : 20 + message_len].decode("utf-8")
        received_corp = plaintext[20 + message_len :].decode("utf-8")
        if received_corp != self.corp_id:
            raise WeComCryptError("回调消息 corp_id 不匹配")
        return message


class WeComAdapter:
    name = "wecom"

    def __init__(
        self,
        gateway: GatewayService,
        corp_id: str,
        agent_id: int,
        secret: str,
        token: str,
        aes_key: str,
    ) -> None:
        self.gateway = gateway
        self.corp_id = corp_id
        self.agent_id = agent_id
        self.secret = secret
        self.crypt = WeComCrypt(token, aes_key, corp_id)
        self._access_token: str | None = None
        self._token_expires_at = 0.0

    # ---- callback protocol ----------------------------------------------

    def verify_url(self, signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        """Return the decrypted ``echostr`` for WeCom's URL verification GET."""
        if not self.crypt.verify_signature(signature, timestamp, nonce, echostr):
            raise WeComCryptError("回调 URL 验签失败")
        return self.crypt.decrypt(echostr)

    def parse_callback(self, signature: str, timestamp: str, nonce: str, body: bytes) -> tuple[str, str] | None:
        """Decrypt a callback POST and return ``(user_id, text)`` for text messages."""
        encrypt = self._extract_encrypt(body)
        if not encrypt or not self.crypt.verify_signature(signature, timestamp, nonce, encrypt):
            raise WeComCryptError("回调消息验签失败")
        xml_text = self.crypt.decrypt(encrypt)
        root = ET.fromstring(xml_text)
        if (root.findtext("MsgType") or "") != "text":
            return None
        user_id = (root.findtext("FromUserName") or "").strip()
        content = (root.findtext("Content") or "").strip()
        if not user_id or not content:
            return None
        return user_id, content

    def reply(self, user_id: str, text: str) -> str:
        """Run the agent for an inbound message and push the reply back."""
        try:
            reply = self.gateway.handle(InboundMessage("wecom", user_id, text))
        except Exception as exc:  # noqa: BLE001 - surface a friendly error to the user
            reply = f"抱歉，处理你的消息时出错了：{exc}"
        if reply:
            self.send_text(user_id, reply)
        return reply

    # ---- active push ----------------------------------------------------

    def send_text(self, user_id: str, text: str) -> None:
        token = self._access_token_now()
        for chunk in _chunk_bytes(text):
            payload = {"touser": user_id, "msgtype": "text", "agentid": self.agent_id, "text": {"content": chunk}}
            response = httpx.post(f"{_WECOM_API}/message/send", params={"access_token": token}, json=payload, timeout=10)
            data = response.json()
            if data.get("errcode") != 0:
                raise RuntimeError(f"企业微信消息推送失败: {data}")

    # ---- internals ------------------------------------------------------

    @staticmethod
    def _extract_encrypt(body: bytes) -> str:
        root = ET.fromstring(body)
        return (root.findtext("Encrypt") or "").strip()

    def _access_token_now(self) -> str:
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token
        response = httpx.get(
            f"{_WECOM_API}/gettoken",
            params={"corpid": self.corp_id, "corpsecret": self.secret},
            timeout=10,
        )
        data = response.json()
        if data.get("errcode") != 0:
            raise RuntimeError(f"获取企业微信 access_token 失败: {data}")
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + float(data.get("expires_in", 7200)) - 300
        return self._access_token


def _chunk_bytes(text: str, max_bytes: int = 1900) -> list[str]:
    """Split text into byte-bounded chunks without breaking UTF-8 sequences."""
    if len(text.encode("utf-8")) <= max_bytes:
        return [text]
    chunks: list[str] = []
    current = ""
    for char in text:
        if len((current + char).encode("utf-8")) > max_bytes:
            chunks.append(current)
            current = char
        else:
            current += char
    if current:
        chunks.append(current)
    return chunks
