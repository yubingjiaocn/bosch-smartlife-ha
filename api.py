"""Bosch SmartLife API client."""
import hashlib
import json
import logging
import os
import random
import time

import requests

_LOGGER = logging.getLogger(__name__)

ROUTER_ADDRESS = "https://api.bosch-smartlife.com"
MAJOR_DOMAIN = "16"
TOKEN_CACHE_PATH = "/tmp/bosch_token_cache.json"


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
        self._cache_loaded = False

    def _gen_nonce(self, timestamp_s: int, length: int = 16) -> str:
        base = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        rng = random.Random(timestamp_s)
        return ''.join(base[rng.randint(0, 61)] for _ in range(length))

    def _load_token_cache(self):
        """Load cached token from file to avoid re-login (which kicks the phone app)."""
        try:
            if os.path.exists(TOKEN_CACHE_PATH):
                with open(TOKEN_CACHE_PATH, "r") as f:
                    cache = json.load(f)
                if cache.get("account") == self.account:
                    try:
                        expire = float(cache.get("token_expire", 0))
                    except (ValueError, TypeError):
                        expire = 0
                    # Check if token is still valid (with 5 min buffer)
                    if expire > time.time() + 300:
                        self.token = cache["token"]
                        self.user_id = cache["user_id"]
                        self.token_expire = expire
                        _LOGGER.info("Loaded cached token for userId=%s, expires in %.0f min",
                                     self.user_id, (expire - time.time()) / 60)
                    else:
                        _LOGGER.info("Cached token expired or expiring soon, will re-login")
        except Exception as e:
            _LOGGER.warning("Failed to load token cache: %s", e)

    def _save_token_cache(self):
        """Save token to cache file."""
        try:
            cache = {
                "account": self.account,
                "token": self.token,
                "user_id": self.user_id,
                "token_expire": self.token_expire,
                "saved_at": time.time(),
            }
            with open(TOKEN_CACHE_PATH, "w") as f:
                json.dump(cache, f)
            _LOGGER.debug("Saved token cache to %s", TOKEN_CACHE_PATH)
        except Exception as e:
            _LOGGER.warning("Failed to save token cache: %s", e)

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
            try:
                self.token_expire = float(data["tokenExpire"]) if data.get("tokenExpire") else None
            except (ValueError, TypeError):
                self.token_expire = None
            _LOGGER.info("Bosch SmartLife login OK, userId=%s, tokenExpire=%s", self.user_id, self.token_expire)
            self._save_token_cache()
            return True
        _LOGGER.error("Bosch SmartLife login failed: %s", data)
        return False

    def _ensure_auth(self):
        if not self._cache_loaded:
            self._cache_loaded = True
            self._load_token_cache()
        if not self.token:
            self.login()
        elif self.token_expire:
            try:
                if float(self.token_expire) < time.time() + 300:
                    _LOGGER.info("Token expiring soon, re-logging in")
                    self.login()
            except (ValueError, TypeError):
                pass

    def _post(self, path: str, payload: dict) -> dict:
        self._ensure_auth()
        url = f"{ROUTER_ADDRESS}{path}"
        resp = self._session.post(url, json=payload, headers=self._headers(), timeout=15)
        data = resp.json()
        if "errorCode" in data and data.get("errorCode") == 1999:
            # Token expired/kicked, re-login
            _LOGGER.info("Token expired (errorCode 1999), re-logging in")
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
            "SDType": "light",
            "SDName": name,
            "Power": power,
            "Chanel": "1",
        }
        if brightness is not None:
            action["brightness"] = brightness
        return self._control([action])

    def ac_set(self, device_id: str, power: str = None, temp: int = None,
               mode: str = None, fan: int = None, name: str = "") -> dict:
        """Control AC. mode: cold/hot/dry/fan/auto. fan: 1(low)/2(mid)/3(high). power: on/off"""
        is_on = (power != "off") if power else True
        action = {
            "SDId": device_id,
            "SDType": "ac",
            "SDName": name,
            "Online": 1 if is_on else 0,
            "Power": power or "on",
            "Delay": 0,
            "Remain": 0,
            "Mode": mode or "cold",
            "SetTemp": temp or 24,
            "Wind": fan or 1,
        }
        return self._control([action])

    def curtain_set(self, device_id: str, status: str, name: str = "") -> dict:
        """Control curtain (布帘). status: opened/closed/stop"""
        if status == "stopped":
            status = "stop"
        return self._control([{
            "SDId": device_id,
            "SDType": "curtain",
            "SDName": name,
            "Status": status,
            "Chanel": "1",
        }])

    def sheer_set(self, device_id: str, status: str, name: str = "") -> dict:
        """Control sheer (窗纱). status: opened/closed/stop"""
        if status == "stopped":
            status = "stop"
        return self._control([{
            "SDId": device_id,
            "SDType": "curtain",
            "SDName": name,
            "Status1": status,
            "chanel2": "1",
        }])
