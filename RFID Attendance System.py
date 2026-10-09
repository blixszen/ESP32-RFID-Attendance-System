from machine import Pin, SPI, SoftI2C, PWM, RTC
import network
import urequests
import time
import gc
import ntptime
from mfrc522 import MFRC522
from ssd1306 import SSD1306_I2C
from umqtt.simple import MQTTClient

# ================= CONFIGURATION =================
ssid = "wifi123"
password = "000000"

URL = "https://script.google.com"

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
CLIENT_ID = b"ESP32_RFID_001"

# MQTT Topics
TOPIC_ATTENDANCE = b"school/attendance"
TOPIC_STATUS = b"school/status"
TOPIC_TOTAL = b"school/total"

students_count = 0

# ================= HARDWARE SETUP =================
i2c = SoftI2C(scl=Pin(22), sda=Pin(21))
oled = SSD1306_I2C(128, 64, i2c)

buzzer = PWM(Pin(25))
buzzer.duty(0)

spi = SPI(
    1,
    baudrate=1000000,
    polarity=0,
    phase=0,
    sck=Pin(18),
    mosi=Pin(23),
    miso=Pin(19)
)

rfid = MFRC522(spi=spi, gpioRst=4, gpioCs=5)

# ================= HELPERS =================
def beep(freq, duration):
    buzzer.freq(freq)
    buzzer.duty(512)
    time.sleep(duration)
    buzzer.duty(0)


def show_message(l1="", l2="", l3="", l4=""):
    oled.fill(0)

    lines = [l for l in [l1, l2, l3, l4] if l]
    start_y = (64 - len(lines) * 16) // 2

    for i, line in enumerate(lines):
        x = max(0, (128 - len(line) * 8) // 2)
        oled.text(line, x, start_y + i * 16)

    oled.show()


# ================= WIFI =================
wifi = network.WLAN(network.STA_IF)
wifi.active(True)


def connect_wifi():
    if not wifi.isconnected():
        print("Connecting WiFi...")
        wifi.connect(ssid, password)

        for _ in range(15):
            if wifi.isconnected():
                break
            time.sleep(1)

        if wifi.isconnected():
            print("WiFi Connected:", wifi.ifconfig()[0])
            sync_time()
            return True

        return False

    return True


def sync_time():
    try:
        ntptime.settime()

        current_sec = time.mktime(time.localtime())
        ph_sec = current_sec + (8 * 3600)

        tm = time.localtime(ph_sec)

        RTC().datetime((
            tm[0],
            tm[1],
            tm[2],
            0,
            tm[3],
            tm[4],
            tm[5],
            0
        ))

        print("Time Synced!")

    except:
        print("Time Sync Failed")


# ================= MQTT =================
client = None


def mqtt_connect():
    global client

    try:
        client = MQTTClient(
            CLIENT_ID,
            MQTT_BROKER,
            port=MQTT_PORT,
            keepalive=60
        )

        client.connect()
        client.publish(TOPIC_STATUS, "1")

        print("MQTT Connected")
        return True

    except:
        print("MQTT Failed")
        return False


# ================= STARTUP =================
connect_wifi()
mqtt_connect()

# ================= MAIN LOOP =================
while True:
    try:
        connect_wifi()

        # MQTT heartbeat
        try:
            if client:
                client.ping()
                client.publish(TOPIC_STATUS, "1")
            else:
                mqtt_connect()

        except:
            mqtt_connect()

        show_message("TAP YOUR", " CARD")

        (status, tag_type) = rfid.request(rfid.REQIDL)

        if status == rfid.OK:

            (status, uid) = rfid.anticoll()

            if status == rfid.OK:

                beep(2000, 0.1)

                uid_str = "0x" + "".join("{:02x}".format(i) for i in uid)

                show_message("CARD FOUND", uid_str)

                gc.collect()

                raw_response = "Unknown"

                try:
                    res = urequests.get(URL + "?uid=" + uid_str)
                    raw_response = res.text.strip()
                    res.close()

                except:
                    raw_response = "Server Error"

                clean_name = raw_response.replace(
                    "TIME IN:",
                    ""
                ).replace(
                    "TIME OUT:",
                    ""
                ).strip()

                status_label = (
                    "Time In"
                    if "TIME IN" in raw_response
                    else "Time Out"
                )

                t = time.localtime()
                h = t[3]

                am_pm = "AM" if h < 12 else "PM"
                display_h = 12 if h in (0, 12) else h % 12

                time_str = "{:d}:{:02d}{}".format(
                    display_h,
                    t[4],
                    am_pm
                )

                mqtt_msg = "Name: {}\n{}: {}\nUID: {}".format(
                    clean_name,
                    status_label,
                    time_str,
                    uid_str
                )

                # FIXED: no global keyword needed
                students_count += 1

                try:
                    client.publish(TOPIC_ATTENDANCE, mqtt_msg)
                    client.publish(TOPIC_TOTAL, str(students_count))

                    print("Published successfully")

                except:
                    print("Publish Failed")

                beep(2500, 0.3)

                show_message(
                    clean_name[:16],
                    time_str,
                    "LOGGED SUCCESS"
                )

                time.sleep(3)

    except Exception as e:
        print("Error:", e)

        try:
            if client:
                client.publish(TOPIC_STATUS, "0")

        except:
            pass

        time.sleep(1)

    time.sleep(0.2)
