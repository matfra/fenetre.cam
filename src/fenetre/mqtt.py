import json
import logging
import re
import threading
from typing import Dict, Optional, Set


logger = logging.getLogger(__name__)


class MQTTManager:
    def __init__(self, deployment_name: str, mqtt_config: Dict[str, object]):
        self._deployment_name = deployment_name
        self._deployment_name_safe = self._sanitize_for_mqtt(deployment_name)
        self._config = mqtt_config
        self._enabled = bool(mqtt_config.get("enabled"))
        self._client = None
        self._lock = threading.RLock()
        self._discovery_sent: Set[str] = set()
        self._availability_topic: Optional[str] = None
        self._base_topic = str(
            mqtt_config.get("base_topic", f"fenetre/{self._deployment_name_safe}")
        )
        self._discovery_prefix = str(
            mqtt_config.get("discovery_prefix", "homeassistant")
        )
        self._reconnect_delay = int(mqtt_config.get("reconnect_delay", 10))

    def publish_camera_state(self, camera_name: str, online: bool) -> None:
        if not self._ensure_client():
            return
        camera_id = self._normalize_camera_name(camera_name)
        if camera_id not in self._discovery_sent:
            self._publish_discovery(camera_name, camera_id)
        topic = f"{self._base_topic}/{camera_id}/state"
        payload = "ON" if online else "OFF"
        try:
            self._client.publish(topic, payload=payload, retain=True)
        except Exception as exc:
            logger.warning("MQTT publish failed for %s: %s", topic, exc)

    def stop(self) -> None:
        with self._lock:
            if not self._client:
                return
            try:
                if self._availability_topic:
                    self._client.publish(
                        self._availability_topic, payload="offline", retain=True
                    )
            except Exception as exc:
                logger.warning("MQTT availability publish failed during stop: %s", exc)
            try:
                self._client.loop_stop()
            finally:
                try:
                    self._client.disconnect()
                except Exception:
                    pass
            self._client = None
            self._availability_topic = None
            self._discovery_sent.clear()

    def _ensure_client(self) -> bool:
        if not self._enabled:
            return False
        with self._lock:
            if self._client:
                return True
            try:
                import paho.mqtt.client as mqtt_client
            except ImportError:
                logger.error(
                    "paho-mqtt is not available. Install it or disable MQTT integration."
                )
                self._enabled = False
                return False

            client_id = f"fenetre_{self._deployment_name_safe}"
            client = mqtt_client.Client(client_id=client_id, clean_session=True)
            username = self._config.get("username")
            password = self._config.get("password")
            if username:
                client.username_pw_set(
                    str(username),
                    password=str(password) if password is not None else None,
                )
            host = str(self._config.get("host", "localhost"))
            port = int(self._config.get("port", 1883))
            self._availability_topic = f"{self._base_topic}/availability"
            client.will_set(self._availability_topic, payload="offline", retain=True)
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.reconnect_delay_set(self._reconnect_delay)
            client.enable_logger(logger)

            try:
                client.connect(host, port, keepalive=60)
            except Exception as exc:
                logger.error(
                    "Failed to connect to MQTT broker %s:%s: %s", host, port, exc
                )
                return False

            client.loop_start()
            try:
                client.publish(self._availability_topic, payload="online", retain=True)
            except Exception as exc:
                logger.warning("MQTT availability publish failed: %s", exc)
            self._client = client
            return True

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("MQTT connected successfully.")
            try:
                if self._availability_topic:
                    client.publish(self._availability_topic, payload="online", retain=True)
            except Exception as exc:
                logger.warning("MQTT availability publish failed on connect: %s", exc)
        else:
            logger.error(f"MQTT connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            logger.warning(
                "MQTT disconnected with result code %s. Will try to reconnect automatically.",
                rc,
            )

    def _publish_discovery(self, camera_name: str, camera_id: str) -> None:
        if not self._client:
            return
        topic = f"{self._discovery_prefix}/binary_sensor/{self._deployment_name_safe}_{camera_id}/config"
        payload = {
            "name": f"{camera_name} Online",
            "unique_id": f"fenetre_{self._deployment_name_safe}_{camera_id}_online",
            "state_topic": f"{self._base_topic}/{camera_id}/state",
            "availability_topic": self._availability_topic,
            "payload_on": "ON",
            "payload_off": "OFF",
            "payload_available": "online",
            "payload_not_available": "offline",
            "device_class": "connectivity",
            "device": {
                "identifiers": [f"fenetre_{self._deployment_name_safe}"],
                "manufacturer": "fenetre.cam",
                "name": self._deployment_name,
            },
        }
        try:
            self._client.publish(topic, payload=json.dumps(payload), retain=True)
            self._discovery_sent.add(camera_id)
        except Exception as exc:
            logger.warning("MQTT discovery publish failed for %s: %s", topic, exc)

    def _normalize_camera_name(self, camera_name: str) -> str:
        return "".join(
            c if c.isalnum() or c in {"-", "_"} else "_"
            for c in camera_name.strip().lower()
        )

    @staticmethod
    def _sanitize_for_mqtt(value: str) -> str:
        sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", value)
        if not sanitized:
            return "fenetre"
        return sanitized
