import time
import sys
import datetime
import requests
import json
import struct
import msgpack
import logging
import json_logging
import base64
import mprotocol
import ttn_device
import mqtt_connection

CONFIGFILE = "config.json"

# disbale insecure connection warning
# TODO remove when requests modules is fixed
requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

class TTNConnector():
    def __init__(self):
        # Get the configuration and initialize the logger
        self.config = self.getConfig()
        self.log = self.setupLog(self.config["LogConfig"]["logFile"],
                                 self.config["LogConfig"]["logLevel"],
                                 self.config["LogConfig"]["logFormat"])
        self.devices = []

        self.log.info("Initialising ...")

        # Check config for logfile and disableUbirch and disableDatabase + init db
        if self.config["LogConfig"]["logFile"] == "/dev/null":
            self.log.warning("Logging to /dev/null - effectively not logging!")

        if self.config["OPConfig"]["disableUbirch"]:
            self.log.warning("Not verifying any data with Ubirch!")

        # Set up MQTT connection
        while True:
            self.log.info("Setting up MQTT connection to TTN ...")
            self.mqtt = mqtt_connection.MQTTConnection(self)

            if self.mqtt.connection_failed:
                # Retry every five sconds
                self.log.error("Setting up MQTT connection failed!")
                time.sleep(5)
            else:
                break

        # Setup device
        self.setupDevices()

        # Loop
        while True:
            # Make a tick in all device objects
            for deviceObj in self.devices:
                deviceObj["device"].tick(noTimesync=True)

            time.sleep(self.config["OPConfig"]["tickPeriod"])

    # Loads the config from CONFIGFILE
    def getConfig(self):
        try:
            return json.loads(open(CONFIGFILE, "r").read())
        except Exception as e:
            print("ERROR opening configfile (%s)!" % CONFIGFILE)
            raise(e)

    # Sets up the logger
    def setupLog(self, logfile, level, format):
        json_logging.ENABLE_JSON_LOGGING = self.config["LogConfig"]["enableJSON"]
        json_logging.init_non_web()

        # Create a logger
        log = logging.getLogger("log")
        log.setLevel(level)

        # Install a file handler
        try:
            fh = logging.FileHandler(logfile)
        except Exception as e:
            print("ERROR opening logfile (%s)!" % logfile)
            raise(e)

        fh.setLevel(level)

        if self.config["LogConfig"]["enableJSON"] == False:
            # Create a format
            fmt = logging.Formatter(format)
            fh.setFormatter(fmt)

        log.addHandler(fh)

        return log

    # Setup devices
    def setupDevices(self):
        devs = self.mqtt.app_client.devices()
        # Go trough the list of device IDs and create device objects
        for dev in devs:
            self.log.info("creating device instance: %s" % dev.dev_id)
            self.devices.append({
                "ID": dev.dev_id,
                "device": ttn_device.TTNDevice(self, dev.dev_id)
            })

    # Get a device object from the self.devices[] array by its it
    def getDeviceObjByID(self, dev_id):
        for deviceObj in self.devices:
            if deviceObj["ID"] == dev_id:
                return deviceObj

    # Function to be called on mqtt messages
    def uplinkCB(self, msg, dev_id):
        # Check if there are any devices
        if len(self.devices) < 1:
            return

        # Try to unpack and process the message
        try:
            # Get the payload
            mp_msg_unpacked = mprotocol.unpack_mp_msg(msg)

            # Handle the message
            if mp_msg_unpacked["MSG_CTRL_B"] == mprotocol.MP_CTRL_B_TYPES["MSG_MEASUREMENTS"]:
                upp = mp_msg_unpacked["MSG_DATA"]

                if not upp:
                    self.log.error("[DEV:%s] measurement does not contain a payload!" % dev_id)
                else:
                    unpacked_upp = msgpack.unpackb(upp)
                    unpacked_measurements = self.unpack_measurements(unpacked_upp)

                    # Payload (UPP) layout:
                    #   [0] = UPP Version
                    #   [1] = Device UUID
                    #   [2] = Previous UPP signature
                    #   [3] = UPP Type
                    #   [4] = UPP Payload
                    #   [5] = UPP Signature

                    # Transmit the received measurement to the current device object and tick it
                    self.getDeviceObjByID(dev_id)["device"].setMeasurement(unpacked_measurements)
                    time.sleep(0.1)
                    self.getDeviceObjByID(dev_id)["device"].tick(noTimesync=False)

                    # Send it to ubirch
                    if not self.config["OPConfig"]["disableUbirch"]:
                        self.verifiy_data(upp, unpacked_upp[1])
                        self.send_measurements(unpacked_measurements, unpacked_upp[4], unpacked_upp[1])
            elif mp_msg_unpacked["MSG_CTRL_B"] == mprotocol.MP_CTRL_B_TYPES["MSG_PING"]:
                # Transmit the ping to the current device and tick it
                self.getDeviceObjByID(dev_id)["device"].ping()
                time.sleep(0.1)
                self.getDeviceObjByID(dev_id)["device"].tick(noTimesync=True)
            elif mp_msg_unpacked["MSG_CTRL_B"] == mprotocol.MP_CTRL_B_TYPES["MSG_ACK"]:
                # Transmit the acknowledge to the current device and tick it
                self.getDeviceObjByID(dev_id)["device"].setAckReceived()
                time.sleep(0.1)
                self.getDeviceObjByID(dev_id)["device"].tick(noTimesync=True)
            elif mp_msg_unpacked["MSG_CTRL_B"] == mprotocol.MP_CTRL_B_TYPES["MSG_NACK"]:
                # Transmit the NOT-acknowledge to the current device and tick it
                self.getDeviceObjByID(dev_id)["device"].setNackReceived()
                time.sleep(0.1)
                self.getDeviceObjByID(dev_id)["device"].tick(noTimesync=True)
            elif mp_msg_unpacked["MSG_CTRL_B"] == mprotocol.MP_CTRL_B_TYPES["MSG_CFG_VAL_RESP"]:
                # Pass the information to the device object and tick it
                payload = mp_msg_unpacked["MSG_DATA"]

                if not payload:
                    self.log.error("[DEV:%s] cfg val response does not contain a payload!" % dev_id)
                else:
                    self.getDeviceObjByID(dev_id)["device"].setDataResponseReceived(mp_msg_unpacked["MSG_DATA"])
                    time.sleep(0.1)
                    self.getDeviceObjByID(dev_id)["device"].tick(noTimesync=True)
            elif mp_msg_unpacked["MSG_CTRL_B"] == mprotocol.MP_CTRL_B_TYPES["MSG_REGISTER_KEY_PART"]:
                # Transmit the part to the device object and tick it
                self.getDeviceObjByID(dev_id)["device"].setRegistrationPartReceived(mp_msg_unpacked["MSG_DATA"])
                time.sleep(0.1)
                self.getDeviceObjByID(dev_id)["device"].tick(noTimesync=True)
            else:
                self.log.warning("[DEV:%s] unhandled MSG_CTRL_B: %d" % (dev_id, mp_msg_unpacked["MSG_CTRL_B"]))
        except Exception as e:
            self.log.exception(e)

    def unpack_measurements(self, unpacked_upp):
        try:
            # the unpacked_upp has to contain at least five elements - the fith element contains the relevent data
            if not unpacked_upp or len(unpacked_upp) < 5:
                return None

            # Replace measurement data struct with the unpacked measurements
            return struct.unpack(self.config["DataConfig"]["structFormat"], bytes(unpacked_upp[4]))
        except Exception as e:
            self.log.error("Received invalid UPP: %s" % str(list(unpacked_upp)))
            self.log.exception(e)

    def uuidbin2str(self, uuidbin):
        # from 16 byte bin to str: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        # get the raw number
        tmp = struct.unpack('>QQ', uuidbin)

        # but every hex-digit into a single element
        tmpl = list(hex(tmp[0]).split('x')[1]) + list(hex(tmp[1]).split('x')[1])

        tmpl.insert(8, '-')
        tmpl.insert(13, '-')
        tmpl.insert(18, '-')
        tmpl.insert(23, '-')

        # put it into a string
        uuidstr = ""
        for e in tmpl:
            uuidstr += e

        return uuidstr

    def verifiy_data(self, payload, uuid):
        attempts_left = self.config["UbirchHTTPConfig"]["HTTPPostAttempts"]

        uuidstr = self.uuidbin2str(uuid)

        self.log.debug("verifying payload via post-request with UBIRCH")

        while True:
            try:
                passwordB64 = base64.encodebytes(bytes(self.config["UbirchHTTPConfig"]["UbirchPASS"], "UTF-8")).decode("utf-8").rstrip('\n')
                r = requests.post((self.config["UbirchHTTPConfig"]["UbirchNIOMON"] % self.config["UbirchHTTPConfig"]["UbirchENV"]),
                                  headers={"X-Ubirch-Hardware-Id": uuidstr,
                                            "X-Ubirch-Auth-Type": "ubirch",
                                            "X-Ubirch-Credential": passwordB64},
                                  timeout=self.config["UbirchHTTPConfig"]["HTTPPostTimeout"],
                                  data=payload,
                                  verify=False)
            except Exception as e:
                self.log.exception(e)
            else:
                # Will exit loop here when message sent
                break

            attempts_left -= 1

            if attempts_left > 0:
                self.log.error("HTTP POST request failed - trying again %d more times in %d seconds"
                               % (attempts_left, 3))
                time.sleep(3)
            else:
                self.log.error("HTTP POST request finally failed")
                return

        if r.status_code == requests.codes.OK:
            self.log.debug("payload validation succeeded")
        else:
            self.log.error("payload validation failed (STATUS_CODE: %d/%s)" % (r.status_code, r.reason))

    def send_measurements(self, measurements, data_struct, uuid):
        attempts_left = self.config["UbirchHTTPConfig"]["HTTPPostAttempts"]

        # put the UUID from binary into standard str format
        uuidstr = self.uuidbin2str(uuid)

        # create the data object
        data = {
            "uuid": uuidstr,
            "msg_type": 77,
            "data": {},
            "hash": base64.b64encode(data_struct).decode()
        }

        # put measurements into the data object
        for i in range(0, len(self.config["DataConfig"]["dataLayout"])):
            if i >= len(measurements):
                break

            # the "timestamp" field is a special case
            if self.config["DataConfig"]["dataLayout"][i] == "time":
                data["timestamp"] = datetime.datetime.utcfromtimestamp(measurements[i]).isoformat()
            else:
                data["data"].update({
                    self.config["DataConfig"]["dataLayout"][i]: measurements[i]
                })

        print(data)

        self.log.info("sending data to ubirch")

        while True:
            try:
                passwordB64 = base64.encodebytes(bytes(self.config["UbirchHTTPConfig"]["UbirchPASS"], "UTF-8")).decode("utf-8").rstrip('\n')
                r = requests.post((self.config["UbirchHTTPConfig"]["UbirchDATA"] % self.config["UbirchHTTPConfig"]["UbirchENV"]),
                                    headers={"X-Ubirch-Hardware-Id": uuidstr,
                                            "X-Ubirch-Auth-Type": "ubirch",
                                            "X-Ubirch-Credential": passwordB64,
                                            "Content-Type": "application/json"},
                                    timeout=self.config["UbirchHTTPConfig"]["HTTPPostTimeout"],
                                    json=data,
                                    verify=False)
            except Exception as e:
                self.log.exception(e)
            else:
                # Will exit loop here when message sent
                break

            attempts_left -= 1

            if attempts_left > 0:
                self.log.error("HTTP POST request failed - trying again %d more times in %d seconds"
                               % (attempts_left, 3))
                time.sleep(3)
            else:
                self.log.error("HTTP POST request finally failed")
                return

        if r.status_code == requests.codes.OK:
            self.log.debug("data successfully sent to ubirch")
        else:
            self.log.error("sending data to ubirch failed (STATUS_CODE: %d/%s)" % (r.status_code, r.reason))


# Start it
if __name__ == "__main__":
    TTNConnector()
