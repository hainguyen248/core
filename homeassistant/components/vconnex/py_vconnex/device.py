"""Vconnex integration"""

from abc import ABCMeta, abstractmethod
import json
import logging
import random
import time
import threading
from types import SimpleNamespace
from typing import Any, NamedTuple
from urllib.parse import urlsplit
from collections.abc import Callable

import paho.mqtt.client as mqtt

from .api import VconnexAPI, ReturnCode

logger = logging.getLogger(__name__)

MQTTCLIENT_SUCCESS = 0


class VconnexDevice(SimpleNamespace):
    """Device info."""

    deviceId: str
    name: str
    status: int
    version: str
    topicContent: str
    topicNotify: str

    params: list[dict[str, Any]] = []

    online: bool
    data: dict[str, Any] = {}

    createdTimeStr: str = ""
    modifiedTimeStr: str = ""


class DeviceValue(NamedTuple):
    """Device value."""

    param: str
    value: Any


class DeviceMessage(SimpleNamespace):
    """Device message."""

    name: str
    devExtAddr: str
    devT: int
    batteryPercent: float
    timeStamp: int
    devV: list[dict[str, Any]]


class MqConfig(SimpleNamespace):
    """Message queue config."""

    url: str
    user: str
    password: str


class VconnexDeviceListener(metaclass=ABCMeta):
    """Device listener."""

    @abstractmethod
    def on_device_update(
        self, new_device: VconnexDevice, old_device: VconnexDevice = None
    ):
        """Update device info."""

    @abstractmethod
    def on_device_added(self, device: VconnexDevice):
        """Device Added."""

    @abstractmethod
    def on_device_removed(self, device: VconnexDevice):
        """Device removed."""


class Uninitialized(RuntimeError):
    """Error to indicate object is uninitialized"""


class ReadOnlyDict(dict):

    __readonly = False

    def readonly(self, allow=1):
        """Allow or deny modifying dictionary"""
        self.__readonly = bool(allow)

    def __setitem__(self, key, value):

        if self.__readonly:
            raise TypeError("__setitem__ is not supported")
        return dict.__setitem__(self, key, value)

    def __delitem__(self, key):

        if self.__readonly:
            raise TypeError("__delitem__ is not supported")
        return dict.__delitem__(self, key)


class VconnexDeviceManager(threading.Thread):
    """Device manager."""

    __initialized: bool = False

    def __init__(self, api: VconnexAPI) -> None:
        """Contructor"""
        threading.Thread.__init__(self)
        self.__initialized = False
        self.api = api
        self.mq_client = None
        self.mq_config: dict[str, Any] = None

        self.device_map: dict[str, VconnexDevice] = {}
        self.topic_device_map: dict[str, VconnexDevice] = {}
        self.message_listeners: set[Callable[[str, str], None]] = set()
        self.device_listeners: set[VconnexDeviceListener] = set()

        self.prv_message_handler: self.DeviceMessageHanlderPrv = None
        self.prv_device_listener: self.DeviceListenerPrv = None

    def __del__(self):
        """Destructor"""
        if self.__initialized:
            self.release()

    def run(self):
        self.__update_device_list()

    ###############################################################################
    ## Init
    ###############################################################################
    def __init_mq(self):
        mq_config = self.__get_mq_config()
        if mq_config is None:
            logger.error("error while get mqtt config")
            return

        mqttc = mqtt.Client(
            f"hass_client_{int(time.time() *1000)}_{random.randint(0, 1000)}"
        )
        mqttc.username_pw_set(mq_config.user, mq_config.password)
        mqttc.user_data_set({"mq_config": mq_config})

        mqttc.on_connect = self._on_mq_connect
        mqttc.on_message = self._on_mq_message
        mqttc.on_disconnect = self._on_mq_disconnect
        mqttc.on_subscribe = self._on_mq_subscribe
        mqttc.on_log = self._on_mq_log

        url = urlsplit(mq_config.url)
        if url.scheme == "ssl":
            mqttc.tls_set()

        mqttc.connect(url.hostname, url.port)

        mqttc.loop_start()
        self.mq_client = mqttc

        self.prv_message_handler = self.DeviceMessageHanlderPrv(self)
        self.prv_message_handler.start()
        self.add_message_listener(self._on_message)

    def __release_mq(self):
        mqttc = self.mq_client
        if mqttc is not None:
            mqttc.disconnect()
        self.mq_client = None
        self.prv_message_handler.stop()
        self.prv_message_handler = None
        self.remove_message_listener(self._on_message)

    def __get_mq_config(self):
        config_dict = self.__get_access_config("mqtt", "device")
        return MqConfig(**config_dict) if config_dict is not None else None

    def __init_device_map(self):
        device_list = self.__get_device_list()
        if len(device_list) > 0:
            device_map = {}
            for device in device_list:
                device_map[device.deviceId] = device
            self.device_map = device_map

    def __init_device_data_listener(self):
        if len(self.device_map) > 0 and self.mq_client is not None:
            for device in self.device_map.values():
                self.mq_client.subscribe(device.topicContent)

    def __init_device(self):
        self.__init_device_map()

        self.prv_device_listener = self.DeviceListenerPrv(self)
        self.add_device_listener(self.prv_device_listener)

        for device in self.device_map.values():
            self.prv_device_listener.on_device_added(device)

    def __release_device(self):
        self.device_map.clear()
        self.remove_device_listener(self.prv_device_listener)
        self.prv_device_listener = None

    def __check_initialize(self):
        if not self.is_initialized():
            raise Uninitialized("Object should be initital first")

    def _on_message(self, topic, message):
        logger.debug("topic=%s, msg=%s", topic, message)
        self.prv_message_handler.add_device_message(topic, message)

    ###############################################################################
    ## Message queue callback
    ###############################################################################
    def _on_mq_connect(self, mqttc: mqtt.Client, user_data: Any, flags, rc):
        logger.debug(f"connect flags->{flags}, rc->{rc}")
        if rc == 0 and self.device_map is not None:
            for device in self.device_map.values():
                if device.topicContent is not None:
                    mqttc.subscribe(device.topicContent)

        elif rc != MQTTCLIENT_SUCCESS:
            self.__init_mq()

    def _on_mq_disconnect(self, client: mqtt.Client, userdata: Any, rc):
        if rc != 0:
            logger.error("Unexpected disconnection. code=%d", rc)
        else:
            logger.debug("disconnect!")

    def _on_mq_subscribe(self, mqttc: mqtt.Client, user_data: Any, mid, granted_qos):
        logger.debug("_on_subscribe: mid=%s", mid)

    def _on_mq_message(self, mqttc: mqtt.Client, user_data: Any, msg: mqtt.MQTTMessage):
        logger.debug("payload-> %s", msg.payload)

        payload_str = msg.payload.decode("utf8")

        logger.debug("on_message: %s", msg)

        for listener in self.message_listeners:
            listener(msg.topic, payload_str)

    def _on_mq_log(self, mqttc: mqtt.Client, user_data: Any, level, string):
        logger.debug("_on_log: %s", string)

    ###############################################################################
    ## Private method
    ###############################################################################

    def __get_access_config(self, res_type: str, res_target: str) -> dict[str, Any]:
        resp = self.api.get("/access-config", {"type": res_type, "target": res_target})
        if resp.code == ReturnCode.SUCCESS:
            return resp.data
        return None

    def __get_device_list(self):
        device_list = []
        resp = self.api.get("/devices")
        if resp.code == ReturnCode.SUCCESS:
            raw_list = resp.data
            if raw_list is not None:
                for raw in raw_list:
                    device_list.append(VconnexDevice(**raw))
        return device_list

    def _update_device_listener(
        self, new_device: VconnexDevice, old_device: VconnexDevice
    ):
        for listener in self.device_listeners:
            listener.on_device_update(new_device, old_device)

    def __update_device_list(self):
        while self.is_initialized():
            time.sleep(900)  # 15mins
            if not self.is_initialized():
                break

            device_list = self.__get_device_list()

            new_device_map = {}
            for device in device_list:
                new_device_map[device.deviceId] = device
            old_device_map = self.device_map
            self.device_map = new_device_map

            new_device_id_list = new_device_map.keys()
            old_device_id_list = old_device_map.keys()

            # Check removed device
            removed_device_id_list = list(
                filter(
                    lambda device_id: device_id not in new_device_id_list,
                    old_device_id_list,
                )
            )
            if len(removed_device_id_list) > 0:
                for device_id in removed_device_id_list:
                    device = old_device_map.get(device_id)
                    for listener in self.device_listeners:
                        listener.on_device_removed(device)

            # Check added device
            added_device_id_list = list(
                filter(
                    lambda device_id: device_id not in old_device_id_list,
                    new_device_id_list,
                )
            )
            if len(added_device_id_list) > 0:
                for device_id in added_device_id_list:
                    device = new_device_map.get(device_id)
                    for listener in self.device_listeners:
                        listener.on_device_added(device)

            # Check modified device
            modified_device_tuple_list: list[tuple[VconnexDevice, VconnexDevice]] = []
            for device_id in old_device_id_list:
                if device_id in new_device_id_list:
                    old_device = old_device_map[device_id]
                    new_device = new_device_map[device_id]
                    if (
                        old_device.createdTimeStr != new_device.createdTimeStr
                        and old_device.modifiedTimeStr != old_device.modifiedTimeStr
                    ):
                        modified_device_tuple_list.append((new_device, old_device))
            if len(modified_device_tuple_list) > 0:
                for device_tuple in modified_device_tuple_list:
                    self._update_device_listener(*device_tuple)

    ###############################################################################
    ## Public method
    ###############################################################################
    def initialize(self) -> bool:
        """Init resource."""
        self.__init_mq()
        self.__init_device()
        self.__initialized = True
        self.start()
        return self.__initialized

    def release(self):
        """Release resource."""
        self.__release_mq()
        self.__release_device()
        self.__initialized = False

    def is_initialized(self) -> bool:
        """Check initialized"""
        return self.__initialized

    def add_message_listener(self, listener: Callable[[str, str], None]):
        """Add message listener."""
        self.message_listeners.add(listener)

    def remove_message_listener(self, listener: Callable[[str, str], None]):
        """Remove message listener."""
        self.message_listeners.discard(listener)

    def add_device_listener(self, listener: VconnexDeviceListener):
        """Add device listener."""
        self.device_listeners.add(listener)

    def remove_device_listener(self, listener: VconnexDeviceListener):
        """Remove device listener."""
        self.device_listeners.discard(listener)

    def get_device(self, device_id: str):
        """Get device info by device id."""
        self.__check_initialize()
        return self.device_map.get(device_id, None)

    def get_device_data(self, device_id: str) -> dict[str, Any]:
        """Get device data by device id."""
        self.__check_initialize()
        if device_id in self.device_map:
            return ReadOnlyDict(self.device_map[device_id].data)
        return None

    def send_commands(self, device_id, command: str, values: dict[str, Any]) -> int:
        """Send device command."""
        self.__check_initialize()
        if device_id in self.device_map:

            body = {"deviceId": device_id, "command": command}
            body["values"] = values

            resp = self.api.post("/commands/execute", body)
            return resp.code if resp is not None else ReturnCode.ERROR
        else:
            logger.warning("Device is not exist")
            return ReturnCode.ERROR

    class DeviceMessageHanlderPrv(threading.Thread):
        """DeviceMessageListenerPrv impl for VconnexDeviceManager."""

        __running = False
        queue = []

        def __init__(self, outer):
            threading.Thread.__init__(self)
            self.outer = outer

        def start(self) -> None:
            self.__running = True
            return super().start()

        def stop(self) -> None:
            """Stop threading"""
            self.__running = False

        def add_device_message(self, topic: str, message: str):
            """add device message to list"""
            self.queue.append((topic, message))

        def handle_device_message(self, topic: str, message: str):
            """Handle device message"""
            try:
                msg_dict = json.loads(message)
                if "name" in msg_dict and "devExtAddr" in msg_dict:
                    device = self.outer.get_device(msg_dict["devExtAddr"])
                    if device is not None:
                        device.data[msg_dict["name"]] = msg_dict
                        self.outer._update_device_listener(device, device)

            except Exception:
                logger.exception("Something went wrong!!!")

        def run(self) -> None:
            while self.__running:
                queue_len = len(self.queue)
                handle_queue = []
                for x in range(queue_len):
                    handle_queue.append(self.queue.pop(0))

                for (topic, message) in handle_queue:
                    self.handle_device_message(topic, message)

                time.sleep(0.05)

    class DeviceListenerPrv(VconnexDeviceListener):
        """DeviceListener impl for VconnexDeviceManager."""

        def __init__(self, outer):
            self.outer = outer

        def on_device_added(self, device: VconnexDevice):
            self.outer.mq_client.subscribe(device.topicContent)
            if hasattr(device, "topicNotify"):
                self.outer.mq_client.unsubscribe(device.topicNotify)

        def on_device_removed(self, device: VconnexDevice):
            self.outer.mq_client.unsubscribe(device.topicContent)
            if hasattr(device, "topicNotify"):
                self.outer.mq_client.unsubscribe(device.topicNotify)

        def on_device_update(
            self, new_device: VconnexDevice, old_device: VconnexDevice = None
        ):
            if old_device is None or old_device.topicContent != new_device.topicContent:
                if old_device is not None:
                    self.outer.mq_client.unsubscribe(old_device.topicContent)
                self.outer.mq_client.subscribe(new_device.topicContent)
