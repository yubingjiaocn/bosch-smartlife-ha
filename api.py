"""Bosch SmartLife API client."""
import hashlib
import json
import logging
import random
import time

import requests

_LOGGER = logging.getLogger(__name__)

ROUTER_ADDRESS = "https://api.bosch-smartlife.com"
MAJOR_DOMAIN = "16"


class BoschSmartLifeAPI:
    """API client for Bosch SmartLife (AbleCloud platform)."""

    def __init__(self, account: str, password: str, panel_id: str):
        self.account = account
        self.password = password
        self.panel_id = panel_id
        self.token = None
        self.user_id = None
        self.token_expire = None
        self._session = requests.Session()

    def _gen_nonce(self, timestamp_s: int, length: int = 16) -> str:
        base = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        rng = random.Random(timestamp_s)
        return ''.join(base[rng.randint(0, 61)] for _ in range(length))

    def _sign(self, secret: str, timeout_s: int, timestamp_s: int, nonce: str) -> str:
        raw = f"{timeout_s}{timestamp_s}{nonce}{secret}"
        return hashlib.sha1(raw.encode('utf-8')).hexdigest()

    def _headers(self, authenticated: bool = True) -> dict:
        ts = int(time.time())
        timeout = 300
        nonce = self._gen_nonce(ts)
        h = {
            "Content-Type": "application/json;charset=utf-8",
            "X-Zc-Major-Domain": MAJOR_DOMAIN,
        }
        if authenticated and self.token and self.user_id:
            sig = self._sign(self.token, timeout, ts, nonce)
            h.update({
                "X-Zc-User-Id": str(self.user_id),
                "X-Zc-User-Signature": sig,
                "X-Zc-Timestamp": str(ts),
                "X-Zc-Timeout": str(timeout),
                "X-Zc-Nonce": nonce,
                "X-Zc-Version": "1",
            })
        return h

    def login(self) -> bool:
        url = f"{ROUTER_ADDRESS}/zc-account/v1/login"
        resp = self._session.post(url, json={
            "account": self.account,
            "password": self.password,
        }, headers=self._headers(authenticated=False), timeout=15)
        data = resp.json()
        if resp.status_code == 200 and "token" in data:
            self.token = data["token"]
            self.user_id = data["userId"]
            self.token_expire = data.get("tokenExpire")
            _LOGGER.info("Bosch SmartLife login OK, userId=%s", self.user_id)
            return True
        _LOGGER.error("Bosch SmartLife login failed: %s", data)
        return False

    def _ensure_auth(self):
        if not self.token:
            self.login()

    def _post(self, path: str, payload: dict) -> dict:
        self._ensure_auth()
        url = f"{ROUTER_ADDRESS}{path}"
        resp = self._session.post(url, json=payload, headers=self._headers(), timeout=15)
        data = resp.json()
        if "errorCode" in data and data.get("errorCode") == 1999:
            # Token expired, re-login
            _LOGGER.info("Token expired, re-logging in")
            self.login()
            resp = self._session.post(url, json=payload, headers=self._headers(), timeout=15)
            data = resp.json()
        return data

    # ─── Query ──────────────────────────────────────────

    def get_panels(self) -> list:
        """Get all panels bound to the account via family→device discovery."""
        self._ensure_auth()
        families = self._post("/family/v1/listFamily", {})
        panels = []
        for fam in families.get("result", []):
            fam_id = fam.get("id")
            if not fam_id:
                continue
            devices = self._post("/panelDevice/v1/queryDeviceList", {"familyId": fam_id})
            for dev in devices.get("devices", []):
                dev["familyId"] = fam_id
                dev["familyName"] = fam.get("familyName", "")
                panels.append(dev)
        return panels

    def get_sub_devices(self) -> list:
        data = self._post("/panelDevice/v1/getSubDeviceByPanelId", {"panelId": self.panel_id})
        return data.get("result", [])

    # ─── Control ────────────────────────────────────────

    def _control(self, action_list: list) -> dict:
        return self._post("/panelInstruct/v1/subDeviceController", {
            "deviceId": self.panel_id,
            "action": json.dumps(action_list),
        })

    def light_set(self, device_id: str, power: str, name: str = "", brightness: int = None) -> dict:
        action = {
            "SDId": device_id,
            "SDType": "4",
            "SDName": name,
            "Power": power,
            "Chanel": "1",
        }
        if brightness is not None:
            action["brightness"] = brightness
        return self._control([action])

    def ac_set(self, device_id: str, power: str = None, temp: int = None,
               mode: str = None, fan: int = None, name: str = "") -> dict:
        action = {
            "SDId": device_id,
            "SDType": "1",
            "SDName": name,
            "Chanel": "1",
        }
        if power is not None:
            action["Power"] = power
        if temp is not None:
            action["SetTemp"] = temp
        if mode is not None:
            action["Mode"] = mode
        if fan is not None:
            action["Wind"] = fan
        return self._control([action])

    def curtain_set(self, device_id: str, status: str, name: str = "") -> dict:
        """Control curtain (布帘). status: opened/closed/stopped"""
        return self._control([{
            "SDId": device_id,
            "SDType": "curtain",
            "SDName": name,
            "Status": status,
            "Chanel": "1",
        }])

    def sheer_set(self, device_id: str, status: str, name: str = "") -> dict:
        """Control sheer (窗纱). status: opened/closed/stopped"""
        return self._control([{
            "SDId": device_id,
            "SDType": "curtain",
            "SDName": name,
            "Status1": status,
            "chanel2": "1",
        }])
