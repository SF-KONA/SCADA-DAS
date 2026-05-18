"""
MQTT 시뮬레이터 - 포토(TRACK) / 금속배선(SPTT) / 테스트(PROBE) 9대
- 1초마다 9개 토픽 발행
- 분포: 정상 90% / WARN 7% / ERR 3%
- topic: smartfactory/{code}/{equipment_id}
- payload: { timestamp, TRACK_01_SPIN_RPM, ..., TRACK_01_STATUS, ... }
"""
import time, json, random
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

# ──────────────────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────────────────
BROKER = "localhost"       # 로컬 Mosquitto (사용자 PC에서 실행)
PORT = 1883
PUBLISH_INTERVAL = 1.0     # 초

# 분포
P_ERR  = 0.03
P_WARN = 0.07
# 나머지 0.90 = 정상

# ──────────────────────────────────────────────────────────
# 설비 11 태그 스펙 (DB의 normal_min/max에서 발췌, alarm은 임계 밖)
# ──────────────────────────────────────────────────────────
SPECS = {
    "TRACK": {
        "SPIN_RPM":   {"normal": (1500, 4000),  "alarm": (1000, 4500),  "type": "int"},
        "PR_THICK":   {"normal": (0.8, 2.0),    "alarm": (0.5, 2.5),    "type": "float"},
        "BAKE_TEMP":  {"normal": (90, 120),     "alarm": (80, 130),     "type": "float"},
        "DEV_TIME":   {"normal": (30, 90),      "alarm": (20, 100),     "type": "int"},
        "N2_PURGE":   {"normal": (50, 200),     "alarm": (30, 250),     "type": "float"},
        "DEFECT":     {"normal": (0, 5),        "alarm": (0, 10),       "type": "int"},
    },
    "SPTT": {
        "PRESS":      {"normal": (1, 10),       "alarm": (0.5, 15),     "type": "float"},
        "DC_PWR":     {"normal": (500, 3000),   "alarm": (300, 3500),   "type": "float"},
        "AR_FLOW":    {"normal": (20, 100),     "alarm": (10, 150),     "type": "float"},
        "TEMP":       {"normal": (150, 350),    "alarm": (100, 400),    "type": "float"},
        "FILM_THICK": {"normal": (500, 5000),   "alarm": (300, 6000),   "type": "float"},
        "DEP_RATE":   {"normal": (5, 50),       "alarm": (3, 70),       "type": "float"},
    },
    "PROBE": {
        "VOLT":       {"normal": (0, 5),        "alarm": (0, 6),        "type": "float"},
        "CURR":       {"normal": (0.1, 1000),   "alarm": (0.05, 1200),  "type": "float"},
        "RESIST":     {"normal": (10, 10000),   "alarm": (5, 15000),    "type": "float"},
        "BV":         {"normal": (3, 20),       "alarm": (2, 25),       "type": "float"},
        "YIELD":      {"normal": (90, 100),     "alarm": (85, 100),     "type": "float"},
        "CONTACT":    {"normal": (1, 50),       "alarm": (1, 80),       "type": "float"},
    },
}


# ──────────────────────────────────────────────────────────
# 설비 인스턴스
# ──────────────────────────────────────────────────────────
class Equipment:
    def __init__(self, code, num):
        self.code = code
        self.num = num
        self.equipment_id = f"{code}_0{num}"
        self.spec = SPECS[code]
        self.status = 1                              # 0=idle, 1=run, 2=alarm, 3=PM
        self.alarm = 0
        self.prod_count = random.randint(100, 5000)
        self.ng_count   = random.randint(0, 50)

    def gen_value(self, tag, severity):
        s = self.spec[tag]
        if severity == "ERR":
            # 알람 범위 밖 (양/음방향 50:50)
            if random.random() < 0.5:
                lo = s["alarm"][0]
                val = lo - random.uniform(0.05, max(abs(lo), 1) * 0.2 + 0.5)
            else:
                hi = s["alarm"][1]
                val = hi * (1 + random.uniform(0.05, 0.2))
        elif severity == "WARN":
            # normal 밖 alarm 안 (boundary)
            if random.random() < 0.5:
                val = random.uniform(s["alarm"][0], s["normal"][0])
            else:
                val = random.uniform(s["normal"][1], s["alarm"][1])
        else:
            val = random.uniform(s["normal"][0], s["normal"][1])

        return int(val) if s["type"] == "int" else round(val, 3)

    def step(self):
        # 알람 분포
        r = random.random()
        if r < P_ERR:
            severity = "ERR"
            self.status = 2
            self.alarm = 1
        elif r < P_ERR + P_WARN:
            severity = "WARN"
            self.status = 1
            self.alarm = 0
        else:
            severity = None
            self.status = 1 if random.random() < 0.95 else random.choice([0, 1])
            self.alarm = 0

        # 페이로드
        eid = self.equipment_id
        payload = {"timestamp": datetime.now(timezone.utc).isoformat()}
        for tag in self.spec:
            payload[f"{eid}_{tag}"] = self.gen_value(tag, severity)
        payload[f"{eid}_STATUS"] = self.status
        payload[f"{eid}_ALARM"] = self.alarm

        # OEE
        if random.random() < 0.2:
            self.prod_count += 1
            if severity == "ERR" or random.random() < 0.02:
                self.ng_count += 1
        payload[f"{eid}_CYCLE_TIME"] = random.randint(30, 300)
        payload[f"{eid}_PROD_COUNT"] = self.prod_count
        payload[f"{eid}_NG_COUNT"]   = self.ng_count

        return payload


# ──────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────
def main():
    equipments = [Equipment(code, num)
                  for code in ["TRACK", "SPTT", "PROBE"]
                  for num in [1, 2, 3]]

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(BROKER, PORT, 60)
    client.loop_start()

    print(f"✅ MQTT 시뮬 시작 — {BROKER}:{PORT}")
    print(f"   설비 9대: TRACK×3, SPTT×3, PROBE×3")
    print(f"   주기: {PUBLISH_INTERVAL}초")
    print(f"   분포: 정상 {(1-P_ERR-P_WARN)*100:.0f}% / WARN {P_WARN*100:.0f}% / ERR {P_ERR*100:.0f}%")
    print()

    cnt = 0
    try:
        while True:
            for eq in equipments:
                payload = eq.step()
                topic = f"smartfactory/{eq.code.lower()}/{eq.equipment_id}"
                client.publish(topic, json.dumps(payload), qos=1)

            cnt += 1
            if cnt % 5 == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 발행 {cnt}회 × 9대 = {cnt*9}건")
            time.sleep(PUBLISH_INTERVAL)
    except KeyboardInterrupt:
        print("\n⏹ 중단")
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
