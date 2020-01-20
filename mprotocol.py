## Contains functions for a little communication protocol used between the sensor and the ttn_connector ##
# This only contains functions needed by the ttn_connector

import struct

# The structure of a message
# MP_MSG_TEMPLATE = {
#    "MSG_CTRL_B": 0,  # control bytes: describes message content/command receiver to do something
#    "MSG_DATA": 0,  # contains the data - not all messages carry data, depends on MSG_CTRL_B
# }

# List of possible control bytes
MP_CTRL_B_TYPES = {
    # Can be received by this program #
    "MSG_ACK": 0x10,  # Acknowledge a CTRL message - No data
    "MSG_NACK": 0x11,  # Not-Acknowledge a CTRL message - No data
    "MSG_MEASUREMENTS": 0x12,  # Send measurements - Contains the current measurements
    "MSG_CFG_VAL_RESP": 0x13,  # Responding a requested config value - a config value
    "MSG_REGISTER_KEY_PART": 0x19, # Send a part of the key registration sequence - termination flag(first bit)/reset flag(second bit)/counter(6 bits), part
    "MSG_PING": 0xff, # Sends a ping - makes ttn pass trough downlink messages - No data

    # Can be sent by this program #
    "MSG_CTRL_TIMESYNC": 0x14,  # Synchronize the sensors clock - unix time
    "MSG_CTRL_RESTART": 0x15,  # Restart the sensor - No Data
    "MSG_CTRL_READ_CFG_VAL": 0x16,  # Read a config value - ID of the value
    "MSG_CTRL_SET_CFG_VAL": 0x17,  # Set a config value - ID of the value, value
    "MSG_CTRL_RESTORE_ORIG_CONFIG": 0x18  # Load config from original_config.json
}

# List of config value IDs
MP_CTRL_CFGVAL_IDs = {
    "MEASURE_INTERVAL": 0x00,  # the measurement interval
    "SEND_INTERVAL": 0x01,  # the send interval
    "PING_INTERVAL": 0x02,  # the ping interval
    "TEMP_CH_TRIGGER": 0x03,  # the temperature change triggering a measurement-send
    "HUMID_CH_TRIGGER": 0x04,  # the humidiy change triggering a measurement-send
    "VOLT_CH_TRIGGER": 0x05,  # the voltage change triggering a measurement-send
    "WATER_CH_TRIGGER": 0x06,  # the water change triggering a measurement-send
    "TIME": 0xff  # the current time - CAN ONLY BE CHANGED VIA MSG_CTRL_TIMESYNC
}


# These functions only contain code to create/unpack messages that should be sent by this program
def mk_mp_msg(mp_msg_j):
    # Single-Byte messages
    if mp_msg_j["MSG_CTRL_B"] == MP_CTRL_B_TYPES["MSG_CTRL_RESTART"]\
            or mp_msg_j["MSG_CTRL_B"] == MP_CTRL_B_TYPES["MSG_CTRL_RESTORE_ORIG_CONFIG"]:
        return bytes([mp_msg_j["MSG_CTRL_B"]])

    # Multi-Byte messages
    elif mp_msg_j["MSG_CTRL_B"] == MP_CTRL_B_TYPES["MSG_CTRL_TIMESYNC"]:
        return bytes([mp_msg_j["MSG_CTRL_B"]]) + struct.pack("I", mp_msg_j["MSG_DATA"])
    elif mp_msg_j["MSG_CTRL_B"] == mp_msg_j["MSG_CTRL_READ_CFG_VAL"]:
        return bytes([mp_msg_j["MSG_CTRL_B"], mp_msg_j["MSG_DATA"]])
    elif mp_msg_j["MSG_CTRL_B"] == mp_msg_j["MSG_CTRL_SET_CFG_VAL"]:
        return bytes([mp_msg_j["MSG_CTRL_B"], mp_msg_j["MSG_DATA"][0]]) + struct.pack("f", mp_msg_j["MSG_DATA"][1])


def unpack_mp_msg(mp_msg_b):
    retval = {}

    # All message contains a control byte
    retval["MSG_CTRL_B"] = mp_msg_b[0]

    if retval["MSG_CTRL_B"] == MP_CTRL_B_TYPES["MSG_MEASUREMENTS"]\
            or retval["MSG_CTRL_B"] == MP_CTRL_B_TYPES["MSG_CFG_VAL_RESP"]\
            or retval["MSG_CTRL_B"] == MP_CTRL_B_TYPES["MSG_REGISTER_KEY_PART"]:
        retval["MSG_DATA"] = mp_msg_b[1:]

    return retval
