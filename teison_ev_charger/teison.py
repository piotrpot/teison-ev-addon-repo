import os
import json
import sys
import time
import requests
import threading
import paho.mqtt.client as mqtt
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from base64 import b64encode
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
# Config
HA_BASE_URL = "http://homeassistant.local:8123/api/states/"
TEISON_BASE_URL = "https://teison-m3.x-cheng.com/"


# Public key for password encryption
public_key_pem = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDKzH8tu+lGYMkT61r7FCdBZ/ez
lLg22grOvvuQ76NtwGPeAUklREWJqArQgd4U6RCx0vVCT6gtBOtXUK2NkSJvKjUW
BhRp6in5VJikMp1+KxyO2vgjIrKMDWzucuoeozBQ89LhhyoB2Sp3jpxKpb83/Pqu
p0gQXJmL39hJ3O+HlwIDAQAB
-----END PUBLIC KEY-----"""
def debug_print(*args, **kwargs):
    if debug:
        print(*args, **kwargs)
def encrypt_password(password):
    rsa_key = RSA.import_key(public_key_pem)
    cipher = PKCS1_v1_5.new(rsa_key)
    encrypted = cipher.encrypt(password.encode('utf-8'))
    return b64encode(encrypted).decode('utf-8')

config_path = './data/options.json'
try:
    with open(config_path) as f:
        config = json.load(f)
except FileNotFoundError:
    debug_print("⚠️ options.json not found, using defaults.")
    config = {}

username = config.get('username')
password = config.get('password')
mqtt_host = config.get('mqtt_host')
mqtt_port = config.get('mqtt_port')
mqtt_user = config.get('mqtt_user')
mqtt_pass = config.get('mqtt_pass')
device_index = config.get('device_index', 0)
HA_TOKEN = config.get('access_token')
pull_interval = config.get('pull_interval',10)
debug = config.get('is_debug',True)

token = None
device_id = None

def is_hassio():
    return (
        os.environ.get("SUPERVISOR_TOKEN") is not None or
        os.path.exists("/assets")
    )


# Set the file path based on the environment (Windows vs Docker)
if is_hassio():
    # Absolute path in Docker container
    config_path = "assets/currency.json"  # Adjust this to the path inside the container
else:
    # Relative path on Windows or local development environment
    config_path = "./assets/currency.json"  # Adjust this to the path on your host machine

# Check if the file exists before opening
if os.path.exists(config_path):
    try:
        with open(config_path, "r") as f:
            data = json.load(f)
            currency_list = data.get("currencyList", [])
    except json.JSONDecodeError as e:
        debug_print(f"Error decoding JSON: {e}")
else:
    debug_print(f"File not found: {config_path}")


HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json"
}

def post_login(user_name, pass_word):
    url = f'{TEISON_BASE_URL}cpAm2/login?language=en_us&username={user_name}&password={pass_word}'
    response = requests.post(url)
    response_data = response.json()
    token = response_data.get('token')
    return token
def get_device_list(local_token):
    headers = {'token': local_token}
    device_res = requests.get(
        f'{TEISON_BASE_URL}cpAm2/cp/deviceList',
        headers=headers
    )
    return device_res.json()
def get_device_details(local_token, local_device_id):
    headers = {'token': local_token}
    res = requests.get(
        f'{TEISON_BASE_URL}cpAm2/cp/deviceDetail/{local_device_id}',
        headers=headers
    )
    return res.json()
def get_cp_config(local_token, local_device_id):
    headers = {'token': local_token}
    res = requests.get(
        f'{TEISON_BASE_URL}cpAm2/cp/getCpConfig/{local_device_id}',
        headers=headers
    )
    return res.json()
def get_rates(local_token):
    headers = {'token': local_token}
    res = requests.get(
        f'{TEISON_BASE_URL}cpAm2/users/getRates',
        headers=headers
    )
    return res.json()
def login_and_get_device():
    global token, device_id
    token = post_login(username, password)
    
    device_data = get_device_list(token).get('bizData', {})
    device_list = device_data.get('deviceList', [])

    if not device_list:
        debug_print("No devices found.")
        return

    debug_print(f"Found {len(device_list)} devices:")
    for idx, device in enumerate(device_list):
        debug_print(f"  [{idx}] ID: {device.get('id')}, Name: {device.get('name')}, Type: {device.get('type')}")

    if len(device_list) > device_index:
        device_id = device_list[device_index]['id']
        debug_print(f"Using device ID: {device_id}")
    else:
        debug_print(f"Device index {device_index} is out of range. Only {len(device_list)} devices available.")

def post_sensor(sensor_id, state, attributes):
    try:
        url = f"{HA_BASE_URL}sensor.{sensor_id}"
        payload = {
            "state": state,
            "attributes": attributes
        }
        response = requests.post(url, headers=HEADERS, data=json.dumps(payload))
        debug_print(f"Updated {sensor_id}: {response.status_code} - {response.text}")
    except Exception as e:
        debug_print(f"Error updating {sensor_id}: {e}")

def mqtt_publish_status():
    while True:
        if token and device_id:
            status = get_device_details(token, device_id)
            voltage = status.get("bizData", {}).get("voltage")
            debug_print("Voltage:", voltage)
            voltage2 = status.get("bizData", {}).get("voltage2")
            debug_print("Voltage2:", voltage2)
            voltage3 = status.get("bizData", {}).get("voltage3")
            debug_print("Voltage3:", voltage3)

            current = status.get("bizData", {}).get("current")
            debug_print("Current:", current)
            current2 = status.get("bizData", {}).get("current2")
            debug_print("Current2:", current2)
            current3 = status.get("bizData", {}).get("current3")
            debug_print("Current3:", current3)

            connStatus = status.get("bizData", {}).get("connStatus")
            debug_print("connStatus:", connStatus)

            energy = status.get("bizData", {}).get("energy")
            debug_print("energy:", energy)

            temperature = status.get("bizData", {}).get("temperature")
            debug_print("temperature:", temperature)

            spendTime = status.get("bizData", {}).get("spendTime") #convert milisecond to HH:MM:ss
            debug_print("spendTime:", spendTime)
            accEnergy = status.get("bizData", {}).get("accEnergy") #energy in kWh
            debug_print("accEnergy:", accEnergy)
            power = status.get("bizData", {}).get("power")  # power in w
            debug_print("accEnergy:", power)

            getCpConfig = get_cp_config(token,device_id)
            maxCurrent = getCpConfig.get("bizData", {}).get("maxCurrent")

            if connStatus == 0:
                client.publish("teison/charger/state", "stop")
            else:
                client.publish("teison/charger/state", "start")

            # Post each sensor
            post_sensor("ev_charger_status", get_device_status(connStatus), {
                "friendly_name": "EV Charger Status",
                "icon": "mdi:ev-station"
            })

            post_sensor("ev_charger_power", power, {
                "unit_of_measurement": "W",
                "device_class": "power",
                "friendly_name": "EV Charger Power",
                "icon": "mdi:flash"
            })
            post_sensor("ev_charger_accEnergy", accEnergy, {
                "unit_of_measurement": "kWh",
                "device_class": "power",
                "friendly_name": "EV Charger Energy",
                "icon": "mdi:flash"
            })

            post_sensor("ev_charger_spendTime", ms_to_hms(spendTime), {
                "unit_of_measurement": "",
                "device_class": "power",
                "friendly_name": "EV Charger Duration",
                "icon": "mdi:flash"
            })
            post_sensor("ev_charger_temperature", temperature, {
                "unit_of_measurement": "C",
                "device_class": "power",
                "friendly_name": "EV Charger Temperature",
                "icon": "mdi:temperature-celsius"
            })

            post_sensor("ev_charger_voltage", voltage, {
                "unit_of_measurement": "V",
                "device_class": "voltage",
                "friendly_name": "EV Charger Voltage",
                "icon": "mdi:flash-outline"
            })
            post_sensor("ev_charger_voltage2", voltage2, {
                "unit_of_measurement": "V",
                "device_class": "voltage",
                "friendly_name": "EV Charger Voltage2",
                "icon": "mdi:flash-outline"
            })
            post_sensor("ev_charger_voltage3", voltage3, {
                "unit_of_measurement": "V",
                "device_class": "voltage",
                "friendly_name": "EV Charger Voltage3",
                "icon": "mdi:flash-outline"
            })

            post_sensor("ev_charger_current", current, {
                "unit_of_measurement": "A",
                "device_class": "current",
                "friendly_name": "EV Charger Current",
                "icon": "mdi:current-ac"
            })
            post_sensor("ev_charger_current2", current2, {
                "unit_of_measurement": "A",
                "device_class": "current",
                "friendly_name": "EV Charger Current2",
                "icon": "mdi:current-ac"
            })
            post_sensor("ev_charger_current3", current3, {
                "unit_of_measurement": "A",
                "device_class": "current",
                "friendly_name": "EV Charger Current3",
                "icon": "mdi:current-ac"
            })
            client.publish("teison/charger/current/state", maxCurrent, retain=True)
            # client.publish("teison/evcharger/status", json.dumps(status))
        time.sleep(pull_interval)
def ms_to_hms(ms_string):
    if ms_string is not None:
        milliseconds = int(ms_string)
    else:
        milliseconds = 0
    seconds = milliseconds // 1000
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours:02}:{minutes:02}:{seconds:02}"

def on_connect(client, userdata, flags, rc):
    debug_print("Connected to MQTT")
    client.subscribe("teison/evcharger/command")
    debug_print("subscribe - teison/evcharger/command")
    client.subscribe("teison/charger/set")
    debug_print("subscribe - teison/charger/set")
    client.subscribe("teison/charger/current/set")
    debug_print("subscribe - teison/charger/current/set")
    client.subscribe("teison/power_rate/set")
    debug_print("subscribe - teison/power_rate/set")
    client.subscribe("teison/currency/set")
    debug_print("subscribe - teison/currency/set")

def on_message(client, userdata, msg):

    payload = msg.payload.decode()
    debug_print(f"on_message - {payload}")
    if token and device_id:
        headers = {'token': token}
        if msg.topic == "teison/charger/current/set":
            value = int(msg.payload.decode())
            debug_print(f"New current limit: {value}A")
            payload = {
                "key": "VendorMaxWorkCurrent",
                "value": value,
            }
            requests.post(
                f'https://cloud.teison.com/cpAm2/cp/changeCpConfig/{device_id}',
                json=payload,
                headers=headers
            )
        elif msg.topic == "teison/power_rate/set":
            value = float(msg.payload.decode())
            debug_print(f"New power rate: {value}kwh")
            payload = {
                "rates": value,
            }
            requests.post(
                f'{TEISON_BASE_URL}cpAm2/users/setRates',
                json=payload,
                headers=headers
            )
        elif msg.topic == "teison/currency/set":
            value = msg.payload.decode()
            debug_print(f"New currency: {value}")
            payload = {
                "currency": value,
            }
            requests.post(
                f'{TEISON_BASE_URL}cpAm2/users/setRates',
                json=payload,
                headers=headers
            )
        elif payload == "start":
            requests.post(
                f'{TEISON_BASE_URL}cpAm2/cp/startCharge/{device_id}',
                headers=headers
            )
            client.publish("teison/charger/state", "start")
        elif payload == "stop":
            requests.get(
                f'{TEISON_BASE_URL}cpAm2/cp/stopCharge/{device_id}',
                headers=headers
            )
            client.publish("teison/charger/state", "stop")
def get_device_status(status: int) -> str:
    if status == 88:
        return "Faulted"

    status_map = {
        0: "Available",
        1: "Preparing",
        2: "Charging",
        3: "SuspendedEVSE",
        4: "SuspendedEV",
        5: "Finished",
        6: "Reserved",
        7: "Unavailable",
        8: "Faulted",
    }

    return status_map.get(status, "")

login_and_get_device()

client = mqtt.Client(protocol=mqtt.MQTTv311)
client.enable_logger()
client.username_pw_set(mqtt_user, mqtt_pass)
client.on_connect = on_connect
client.on_message = on_message
client.connect(mqtt_host, mqtt_port, 60)

threading.Thread(target=client.loop_forever, daemon=True).start()
threading.Thread(target=mqtt_publish_status, daemon=True).start()

# Publish discovery config
client.publish(
    "homeassistant/switch/teison_charger/config",
    json.dumps({
        "name": "Teison Charger",
        "unique_id": "teison_charger_switch",
        "command_topic": "teison/charger/set",
        "state_topic": "teison/charger/state",
        "payload_on": "start",
        "payload_off": "stop"
    }),
    retain=True
)
client.publish(
    "homeassistant/number/teison_charger_current/config",
    json.dumps({
        "name": "Charging Max Current",
        "unique_id": "teison_charger_max_current",
        "command_topic": "teison/charger/current/set",
        "state_topic": "teison/charger/current/state",
        "min": 6,
        "max": 32,
        "step": 1,
        "unit_of_measurement": "A",
        "mode": "slider",
        "retain": True
    }),
    retain=True
)

client.publish(
    "homeassistant/number/teison_power_limit/config",
    json.dumps({
        "name": "Teison Power Rate",
        "unique_id": "teison_power_rate",
        "command_topic": "teison/power_rate/set",
        "state_topic": "teison/power_rate/state",
        "min": 0.0,
        "max": 9999999.0,
        "step": 0.01,
        "unit_of_measurement": "kWh",
        "mode": "box",
        "retain": True
    }),
    retain=True
)

app = Flask(__name__, static_folder='frontend')
CORS(app)

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_frontend(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

@app.route('/start', methods=['POST'])
def start():
    if token and device_id:
        headers = {'token': token}
        r = requests.post(f'{TEISON_BASE_URL}cpAm2/cp/startCharge/{device_id}', headers=headers)
        return jsonify(r.json())
    return jsonify({"error": "Not ready"}), 400

@app.route('/stop', methods=['POST'])
def stop():
    if token and device_id:
        headers = {'token': token}
        r = requests.post(f'{TEISON_BASE_URL}cpAm2/cp/stopCharge/{device_id}', headers=headers)
        return jsonify(r.json())
    return jsonify({"error": "Not ready"}), 400

@app.route('/status', methods=['GET'])
def status():
    if token and device_id:
        return get_device_details(token,device_id)
    return jsonify({"error": "Not ready"}), 400
@app.route('/token', methods=['GET'])
def get_token():
    if token and device_id:
        json_string = f'{{"token": "{token}", "device_id": {device_id}}}'
        data = json.loads(json_string)
        return jsonify(data)
    return jsonify({"error": "Not ready"}), 400
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    return jsonify(post_login(data.get("username"),data.get("password")))

app.run(host='0.0.0.0', port=5000)
