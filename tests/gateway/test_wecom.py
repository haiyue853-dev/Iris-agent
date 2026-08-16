import base64
import hashlib
import os

import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from iris_agent.gateway.wecom import WeComAdapter, WeComCrypt, WeComCryptError, _chunk_bytes

AES_KEY = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"  # 43 chars
CORP_ID = "test_corp"
TOKEN = "test_token"


def _crypt() -> WeComCrypt:
    return WeComCrypt(TOKEN, AES_KEY, CORP_ID)


def _encrypt(plaintext: str, corp_id: str = CORP_ID) -> str:
    key = base64.b64decode(AES_KEY + "=")
    data = os.urandom(16) + len(plaintext.encode("utf-8")).to_bytes(4, "big") + plaintext.encode("utf-8") + corp_id.encode("utf-8")
    cipher = AES.new(key, AES.MODE_CBC, key[:16])
    return base64.b64encode(cipher.encrypt(pad(data, AES.block_size))).decode()


def _signature(encrypt: str, token: str = TOKEN) -> str:
    items = sorted([token, "1234567890", "nonce123", encrypt])
    return hashlib.sha1("".join(items).encode("utf-8")).hexdigest()


def test_decrypt_roundtrip():
    crypt = _crypt()
    encrypt = _encrypt("你好，agent")

    assert crypt.decrypt(encrypt) == "你好，agent"


def test_verify_signature_ok_and_mismatch():
    crypt = _crypt()
    encrypt = _encrypt("hi")

    assert crypt.verify_signature(_signature(encrypt), "1234567890", "nonce123", encrypt) is True
    assert crypt.verify_signature("bad", "1234567890", "nonce123", encrypt) is False


def test_decrypt_rejects_wrong_corp_id():
    crypt = _crypt()
    encrypt = _encrypt("hi", corp_id="other_corp")

    with pytest.raises(WeComCryptError):
        crypt.decrypt(encrypt)


def _callback_body(content: str, corp_id: str = CORP_ID) -> bytes:
    encrypt = _encrypt(content, corp_id)
    return (
        f"<xml><ToUserName><![CDATA[{corp_id}]]></ToUserName>"
        f"<Encrypt><![CDATA[{encrypt}]]></Encrypt></xml>"
    ).encode("utf-8")


def _text_message_xml(user_id: str, content: str) -> str:
    return (
        f"<xml><ToUserName><![CDATA[{CORP_ID}]]></ToUserName>"
        f"<FromUserName><![CDATA[{user_id}]]></FromUserName>"
        f"<CreateTime>1700000000</CreateTime><MsgType><![CDATA[text]]></MsgType>"
        f"<Content><![CDATA[{content}]]></Content><MsgId>1</MsgId><AgentID>1</AgentID></xml>"
    )


def test_parse_callback_returns_user_and_text():
    adapter = WeComAdapter(None, CORP_ID, 1, "secret", TOKEN, AES_KEY)
    body = _callback_body(_text_message_xml("userA", "问个问题"))
    encrypt = body.decode("utf-8").split("<Encrypt><![CDATA[")[1].split("]]>")[0]

    result = adapter.parse_callback(_signature(encrypt), "1234567890", "nonce123", body)

    assert result == ("userA", "问个问题")


def test_parse_callback_returns_none_for_non_text():
    adapter = WeComAdapter(None, CORP_ID, 1, "secret", TOKEN, AES_KEY)
    non_text = (
        f"<xml><FromUserName><![CDATA[userA]]></FromUserName><MsgType><![CDATA[event]]></MsgType>"
        f"<Event><![CDATA[subscribe]]></Event></xml>"
    )
    body = _callback_body(non_text)
    encrypt = body.decode("utf-8").split("<Encrypt><![CDATA[")[1].split("]]>")[0]

    assert adapter.parse_callback(_signature(encrypt), "1234567890", "nonce123", body) is None


def test_parse_callback_rejects_bad_signature():
    adapter = WeComAdapter(None, CORP_ID, 1, "secret", TOKEN, AES_KEY)
    body = _callback_body(_text_message_xml("userA", "hi"))

    with pytest.raises(WeComCryptError):
        adapter.parse_callback("wrong-signature", "1234567890", "nonce123", body)


def test_chunk_bytes_short_text_unchanged():
    assert _chunk_bytes("短文本") == ["短文本"]


def test_chunk_bytes_splits_long_text():
    text = "字" * 3000  # > 1900 bytes in UTF-8
    chunks = _chunk_bytes(text, max_bytes=1900)

    assert len(chunks) > 1
    assert all(len(chunk.encode("utf-8")) <= 1900 for chunk in chunks)
    assert "".join(chunks) == text
