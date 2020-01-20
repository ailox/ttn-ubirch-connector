import base64
import ttn


class MQTTConnection():
    def __init__(self, context):
        self.context = context
        self.connection_failed = False
        self.connect()

    def __uplinkcb(self, msg, client):
        try:
            self.context.uplinkCB(self.extract_payload(msg), msg.dev_id)
        except Exception as e:
            self.context.log.exception(e)

    def connect(self):
        try:
            self.handler = ttn.HandlerClient(
                self.context.config["TTNAppConfig"]["appID"], self.context.config["TTNAppConfig"]["appAccessKey"])
            self.app_client = self.handler.application()
            self.mqtt_client = self.handler.data()

            self.mqtt_client.set_uplink_callback(self.__uplinkcb)
            self.mqtt_client.connect()
        except Exception as e:
            self.connection_failed = True
            self.context.log.exception(e)

    def send(self, deviceID, data):
        try:
            self.mqtt_client.send(deviceID, str(
                base64.b64encode(data), "UTF-8"), 1, False, "replace")
        except Exception as e:
            self.context.log.exception(e)

    def extract_payload(self, msg):
        raw_payload = msg.payload_raw

        if not raw_payload:
            return None

        return base64.decodebytes(bytes(raw_payload, "utf8"))
