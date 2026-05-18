"""
==============================================================
통합 시뮬레이터 — Modbus + OPC UA + MQTT + BMS
2조 SFaaS 프로젝트 / SCADA-DAS / 김완택
==============================================================

4개 서버를 하나의 프로세스로 구동:

  [1] Modbus TCP :5020   산화공정      FURN_01·02·03      (equip_sim_v02)
  [2] OPC UA    :4840   박막증착      PECVD_01·02·03     (equip_sim_v02)
                         식각공정      ETCH_01·02·03
  [3] MQTT      :1883   포토·배선·검사 TRACK/SPTT/PROBE   (mqtt_sim_v01)
  [4] Modbus TCP :5021   환경 BMS      18센서 (6타입×3구역) (env_sim_v01)

★ 다중 주기 구조 ★
  1초 루프  : STATUS, ALARM, TIME, MQTT publish
  5초 루프  : 공정 파라미터, 환경 측정값
  30초 루프 : PARTICLE 카운트
  이벤트    : 사이클 완료 시 lot 단위 태그

설치:
    pip install pymodbus asyncua paho-mqtt

실행:
    python integrated_sim.py

종료:
    Ctrl+C
==============================================================
"""

import asyncio
import json
import random
import sys
from datetime import datetime, timezone

from asyncua import Server as OPCUAServer
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import StartAsyncTcpServer
import paho.mqtt.client as mqtt


# ============================================================
# 공통 설정
# ============================================================
MODBUS_HOST     = "0.0.0.0"
MODBUS_EQP_PORT = 5020          # 설비 Modbus
MODBUS_ENV_PORT = 5021          # 환경 Modbus
OPCUA_HOST      = "0.0.0.0"
OPCUA_PORT      = 4840
OPCUA_NAMESPACE = "http://team2.factory"
MQTT_BROKER     = "localhost"
MQTT_PORT       = 1883

FAST_INTERVAL     = 1           # 1초
SLOW_INTERVAL     = 5           # 5초
PARTICLE_INTERVAL = 30          # 30초
PRINT_INTERVAL    = 30          # 30초

# 알람/복구 확률
EQP_ALARM_RATE    = 0.002       # 설비: ~8분에 1번
EQP_RECOVERY_RATE = 0.01        # 설비: ~100초 평균
ENV_ALARM_RATE    = 0.001       # 환경: ~16분에 1번
ENV_RECOVERY_RATE = 0.02        # 환경: ~50초 평균
NG_PROB           = 0.03        # lot당 불량 확률

# MQTT 분포
MQTT_P_ERR  = 0.03
MQTT_P_WARN = 0.07


# ############################################################
#  PART 1 — 설비 시뮬레이터 (Modbus + OPC UA)
# ############################################################

# ─── 설비 초기 상태 ───
def initial_furn():
    return {
        "TEMP": 1000.0, "PRESS": 5.0, "O2_FLOW": 1250.0, "N2_FLOW": 600.0,
        "TIME": 0, "OX_THICK": 1250.0, "STATUS": 1, "ALARM": 0,
        "CYCLE_TIME": 60, "PROD_COUNT": 0, "NG_COUNT": 0,
        "_cycle_elapsed": 0,
    }

def initial_pecvd():
    return {
        "TEMP": 375.0, "PRESS": 2.5, "RF_PWR": 300.0,
        "SIH4_FLOW": 300.0, "N2O_FLOW": 600.0,
        "DEP_THICK": 1750.0, "STATUS": 1, "ALARM": 0,
        "CYCLE_TIME": 90, "PROD_COUNT": 0, "NG_COUNT": 0,
        "_cycle_elapsed": 0,
    }

def initial_etch():
    return {
        "PRESS": 25.0, "RF_PWR": 500.0, "CF4_FLOW": 60.0,
        "O2_FLOW": 17.0, "TEMP": 50.0, "ETCH_DEP": 900.0,
        "STATUS": 1, "ALARM": 0,
        "CYCLE_TIME": 75, "PROD_COUNT": 0, "NG_COUNT": 0,
        "_cycle_elapsed": 0,
    }

FURNS  = {f"FURN_0{i}":  initial_furn()  for i in (1, 2, 3)}
PECVDS = {f"PECVD_0{i}": initial_pecvd() for i in (1, 2, 3)}
ETCHES = {f"ETCH_0{i}":  initial_etch()  for i in (1, 2, 3)}


# ─── Fast 갱신 (1초) ───
def eqp_update_fast_common(state, has_time=False):
    if state["STATUS"] == 1:
        if random.random() < EQP_ALARM_RATE:
            state["STATUS"] = 2
            state["ALARM"]  = 1
        elif has_time:
            state["TIME"] = min(state["TIME"] + 1, 120)
    elif state["STATUS"] == 2:
        if random.random() < EQP_RECOVERY_RATE:
            state["STATUS"] = 1
            state["ALARM"]  = 0

def eqp_update_all_fast():
    for s in FURNS.values():
        eqp_update_fast_common(s, has_time=True)
    for s in PECVDS.values():
        eqp_update_fast_common(s)
    for s in ETCHES.values():
        eqp_update_fast_common(s)


# ─── Slow 갱신 (5초) ───
def _random_walk(state, deltas, bounds):
    for tag, delta in deltas.items():
        state[tag] += random.uniform(-delta, delta)
        lo, hi = bounds[tag]
        state[tag] = max(lo, min(hi, state[tag]))

def _advance_cycle(state, lot_targets):
    state["_cycle_elapsed"] += SLOW_INTERVAL
    if state["_cycle_elapsed"] >= state["CYCLE_TIME"]:
        state["PROD_COUNT"] += 1
        if random.random() < NG_PROB:
            state["NG_COUNT"] += 1
        for tag, (lo, hi) in lot_targets.items():
            state[tag] = random.uniform(lo, hi)
        state["_cycle_elapsed"] = 0
        if "TIME" in state:
            state["TIME"] = 0

def eqp_update_all_slow():
    for s in FURNS.values():
        if s["STATUS"] != 1: continue
        _random_walk(s,
            {"TEMP": 3, "PRESS": 0.1, "O2_FLOW": 20, "N2_FLOW": 10},
            {"TEMP": (900,1100), "PRESS": (0.1,10), "O2_FLOW": (500,2000), "N2_FLOW": (200,1000)})
        _advance_cycle(s, {"OX_THICK": (500, 2000)})

    for s in PECVDS.values():
        if s["STATUS"] != 1: continue
        _random_walk(s,
            {"TEMP": 2, "PRESS": 0.05, "RF_PWR": 5, "SIH4_FLOW": 5, "N2O_FLOW": 10},
            {"TEMP": (300,450), "PRESS": (0.5,5), "RF_PWR": (100,500), "SIH4_FLOW": (100,500), "N2O_FLOW": (200,1000)})
        _advance_cycle(s, {"DEP_THICK": (500, 3000)})

    for s in ETCHES.values():
        if s["STATUS"] != 1: continue
        _random_walk(s,
            {"PRESS": 1, "RF_PWR": 10, "CF4_FLOW": 2, "O2_FLOW": 0.5, "TEMP": 1},
            {"PRESS": (5,50), "RF_PWR": (200,800), "CF4_FLOW": (20,100), "O2_FLOW": (5,30), "TEMP": (20,80)})
        _advance_cycle(s, {"ETCH_DEP": (300, 1500)})


# ─── Modbus 설비 (:5020) ───
FURN_FAST_LAYOUT = [("STATUS", 1), ("ALARM", 1), ("TIME", 1)]
FURN_SLOW_LAYOUT = [
    ("TEMP", 10), ("PRESS", 100), ("O2_FLOW", 1), ("N2_FLOW", 1),
    ("OX_THICK", 1), ("CYCLE_TIME", 1), ("PROD_COUNT", 1), ("NG_COUNT", 1),
]
FURN_REG_BASES = {"FURN_01": 0, "FURN_02": 20, "FURN_03": 40}

class ModbusEquipSim:
    def __init__(self):
        self.slave = ModbusSlaveContext(
            hr=ModbusSequentialDataBlock(0, [0] * 100), zero_mode=True)
        self.context = ModbusServerContext(slaves=self.slave, single=True)

    def _write(self, addr, value, scale):
        self.slave.setValues(3, addr, [int(value * scale) & 0xFFFF])

    def sync_fast(self):
        for eq_id, base in FURN_REG_BASES.items():
            state = FURNS[eq_id]
            for i, (tag, scale) in enumerate(FURN_FAST_LAYOUT):
                self._write(base + i, state[tag], scale)

    def sync_slow(self):
        for eq_id, base in FURN_REG_BASES.items():
            state = FURNS[eq_id]
            for i, (tag, scale) in enumerate(FURN_SLOW_LAYOUT):
                self._write(base + 3 + i, state[tag], scale)

    async def start(self):
        await StartAsyncTcpServer(
            context=self.context, address=(MODBUS_HOST, MODBUS_EQP_PORT))


# ─── OPC UA (:4840) ───
PECVD_FAST_TAGS = ("STATUS", "ALARM")
PECVD_SLOW_TAGS = ("TEMP", "PRESS", "RF_PWR", "SIH4_FLOW", "N2O_FLOW",
                   "DEP_THICK", "CYCLE_TIME", "PROD_COUNT", "NG_COUNT")
ETCH_FAST_TAGS  = ("STATUS", "ALARM")
ETCH_SLOW_TAGS  = ("PRESS", "RF_PWR", "CF4_FLOW", "O2_FLOW", "TEMP",
                   "ETCH_DEP", "CYCLE_TIME", "PROD_COUNT", "NG_COUNT")

class OPCUASim:
    def __init__(self):
        self.server = OPCUAServer()
        self.vars = {}

    async def setup(self):
        await self.server.init()
        self.server.set_endpoint(f"opc.tcp://{OPCUA_HOST}:{OPCUA_PORT}/team2/server/")
        self.server.set_server_name("Team2 SCADA Simulator")
        idx = await self.server.register_namespace(OPCUA_NAMESPACE)
        objects = self.server.nodes.objects

        thinfilm = await objects.add_folder(idx, "ThinFilm")
        for eq_id, state in PECVDS.items():
            obj = await thinfilm.add_object(idx, eq_id)
            self.vars[eq_id] = {}
            for tag, val in state.items():
                if tag.startswith("_"): continue
                var = await obj.add_variable(idx, tag, float(val))
                await var.set_writable()
                self.vars[eq_id][tag] = var

        etching = await objects.add_folder(idx, "Etching")
        for eq_id, state in ETCHES.items():
            obj = await etching.add_object(idx, eq_id)
            self.vars[eq_id] = {}
            for tag, val in state.items():
                if tag.startswith("_"): continue
                var = await obj.add_variable(idx, tag, float(val))
                await var.set_writable()
                self.vars[eq_id][tag] = var

    async def sync_fast(self):
        for eq_id, state in PECVDS.items():
            for tag in PECVD_FAST_TAGS:
                await self.vars[eq_id][tag].write_value(float(state[tag]))
        for eq_id, state in ETCHES.items():
            for tag in ETCH_FAST_TAGS:
                await self.vars[eq_id][tag].write_value(float(state[tag]))

    async def sync_slow(self):
        for eq_id, state in PECVDS.items():
            for tag in PECVD_SLOW_TAGS:
                await self.vars[eq_id][tag].write_value(float(state[tag]))
        for eq_id, state in ETCHES.items():
            for tag in ETCH_SLOW_TAGS:
                await self.vars[eq_id][tag].write_value(float(state[tag]))


# ############################################################
#  PART 2 — MQTT 시뮬레이터 (TRACK / SPTT / PROBE)
# ############################################################

MQTT_SPECS = {
    "TRACK": {
        "SPIN_RPM":  {"normal": (1500, 4000), "alarm": (1000, 4500), "type": "int"},
        "PR_THICK":  {"normal": (0.8, 2.0),   "alarm": (0.5, 2.5),  "type": "float"},
        "BAKE_TEMP": {"normal": (90, 120),    "alarm": (80, 130),   "type": "float"},
        "DEV_TIME":  {"normal": (30, 90),     "alarm": (20, 100),   "type": "int"},
        "N2_PURGE":  {"normal": (50, 200),    "alarm": (30, 250),   "type": "float"},
        "DEFECT":    {"normal": (0, 5),       "alarm": (0, 10),     "type": "int"},
    },
    "SPTT": {
        "PRESS":      {"normal": (1, 10),     "alarm": (0.5, 15),   "type": "float"},
        "DC_PWR":     {"normal": (500, 3000), "alarm": (300, 3500), "type": "float"},
        "AR_FLOW":    {"normal": (20, 100),   "alarm": (10, 150),   "type": "float"},
        "TEMP":       {"normal": (150, 350),  "alarm": (100, 400),  "type": "float"},
        "FILM_THICK": {"normal": (500, 5000), "alarm": (300, 6000), "type": "float"},
        "DEP_RATE":   {"normal": (5, 50),     "alarm": (3, 70),     "type": "float"},
    },
    "PROBE": {
        "VOLT":    {"normal": (0, 5),       "alarm": (0, 6),      "type": "float"},
        "CURR":    {"normal": (0.1, 1000),  "alarm": (0.05, 1200),"type": "float"},
        "RESIST":  {"normal": (10, 10000),  "alarm": (5, 15000),  "type": "float"},
        "BV":      {"normal": (3, 20),      "alarm": (2, 25),     "type": "float"},
        "YIELD":   {"normal": (90, 100),    "alarm": (85, 100),   "type": "float"},
        "CONTACT": {"normal": (1, 50),      "alarm": (1, 80),     "type": "float"},
    },
}

class MQTTEquipment:
    def __init__(self, code, num):
        self.code = code
        self.num = num
        self.equipment_id = f"{code}_0{num}"
        self.spec = MQTT_SPECS[code]
        self.status = 1
        self.alarm = 0
        self.prod_count = random.randint(100, 5000)
        self.ng_count = random.randint(0, 50)

    def _gen_value(self, tag, severity):
        s = self.spec[tag]
        if severity == "ERR":
            if random.random() < 0.5:
                lo = s["alarm"][0]
                val = lo - random.uniform(0.05, max(abs(lo), 1) * 0.2 + 0.5)
            else:
                hi = s["alarm"][1]
                val = hi * (1 + random.uniform(0.05, 0.2))
        elif severity == "WARN":
            if random.random() < 0.5:
                val = random.uniform(s["alarm"][0], s["normal"][0])
            else:
                val = random.uniform(s["normal"][1], s["alarm"][1])
        else:
            val = random.uniform(s["normal"][0], s["normal"][1])
        return int(val) if s["type"] == "int" else round(val, 3)

    def step(self):
        r = random.random()
        if r < MQTT_P_ERR:
            severity = "ERR"; self.status = 2; self.alarm = 1
        elif r < MQTT_P_ERR + MQTT_P_WARN:
            severity = "WARN"; self.status = 1; self.alarm = 0
        else:
            severity = None
            self.status = 1 if random.random() < 0.95 else random.choice([0, 1])
            self.alarm = 0

        eid = self.equipment_id
        payload = {"timestamp": datetime.now(timezone.utc).isoformat()}
        for tag in self.spec:
            payload[f"{eid}_{tag}"] = self._gen_value(tag, severity)
        payload[f"{eid}_STATUS"] = self.status
        payload[f"{eid}_ALARM"] = self.alarm

        if random.random() < 0.2:
            self.prod_count += 1
            if severity == "ERR" or random.random() < 0.02:
                self.ng_count += 1
        payload[f"{eid}_CYCLE_TIME"] = random.randint(30, 300)
        payload[f"{eid}_PROD_COUNT"] = self.prod_count
        payload[f"{eid}_NG_COUNT"] = self.ng_count
        return payload

MQTT_EQUIPMENTS = [MQTTEquipment(code, num)
                   for code in ("TRACK", "SPTT", "PROBE")
                   for num in (1, 2, 3)]

class MQTTSim:
    def __init__(self):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.connected = False

    def start(self):
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_start()
            self.connected = True
        except Exception as e:
            print(f"  ⚠️  MQTT 브로커 연결 실패 ({MQTT_BROKER}:{MQTT_PORT}): {e}")
            print(f"       Mosquitto 실행 중인지 확인하세요. MQTT 없이 계속 진행합니다.")
            self.connected = False

    def publish_all(self):
        if not self.connected:
            return
        for eq in MQTT_EQUIPMENTS:
            payload = eq.step()
            topic = f"smartfactory/{eq.code.lower()}/{eq.equipment_id}"
            self.client.publish(topic, json.dumps(payload), qos=1)

    def stop(self):
        if self.connected:
            self.client.loop_stop()
            self.client.disconnect()


# ############################################################
#  PART 3 — 환경 BMS 시뮬레이터 (Modbus :5021)
# ############################################################

SENSOR_SPECS = {
    "PART": {
        "fast_tags": ["STATUS", "ALARM"],
        "slow_tags": ["CNT_03", "CNT_05", "CNT_10"],
        "is_particle": True,
        "scale": {"CNT_03": 1, "CNT_05": 1, "CNT_10": 1, "STATUS": 1, "ALARM": 1},
        "initial": {"CNT_03": 1500, "CNT_05": 300, "CNT_10": 30},
        "bounds": {"CNT_03": (0, 3520), "CNT_05": (0, 832), "CNT_10": (0, 83)},
        "delta":  {"CNT_03": 200, "CNT_05": 50, "CNT_10": 10},
    },
    "TEMP": {
        "fast_tags": ["STATUS", "ALARM"],
        "slow_tags": ["VAL", "DELTA", "SETPOINT"],
        "scale": {"VAL": 100, "DELTA": 100, "SETPOINT": 100, "STATUS": 1, "ALARM": 1},
        "initial": {"VAL": 22.0, "DELTA": 0.0, "SETPOINT": 22.0},
        "bounds": {"VAL": (21.0, 23.0), "DELTA": (-1.0, 1.0), "SETPOINT": (22.0, 22.0)},
        "delta":  {"VAL": 0.1, "DELTA": 0.05, "SETPOINT": 0},
    },
    "HUM": {
        "fast_tags": ["STATUS", "ALARM"],
        "slow_tags": ["VAL", "DELTA", "SETPOINT"],
        "scale": {"VAL": 100, "DELTA": 100, "SETPOINT": 100, "STATUS": 1, "ALARM": 1},
        "initial": {"VAL": 45.0, "DELTA": 0.0, "SETPOINT": 45.0},
        "bounds": {"VAL": (42.0, 48.0), "DELTA": (-3.0, 3.0), "SETPOINT": (45.0, 45.0)},
        "delta":  {"VAL": 0.3, "DELTA": 0.1, "SETPOINT": 0},
    },
    "AMC": {
        "fast_tags": ["STATUS", "ALARM"],
        "slow_tags": ["ACID", "BASE", "COND"],
        "scale": {"ACID": 1000, "BASE": 1000, "COND": 1000, "STATUS": 1, "ALARM": 1},
        "initial": {"ACID": 0.3, "BASE": 0.05, "COND": 0.8},
        "bounds": {"ACID": (0, 1), "BASE": (0, 0.1), "COND": (0, 2)},
        "delta":  {"ACID": 0.05, "BASE": 0.005, "COND": 0.1},
    },
    "VIB": {
        "fast_tags": ["VEL_X", "VEL_Y", "VEL_Z", "FREQ", "STATUS", "ALARM"],
        "slow_tags": [],
        "scale": {"VEL_X": 10, "VEL_Y": 10, "VEL_Z": 10, "FREQ": 10, "STATUS": 1, "ALARM": 1},
        "initial": {"VEL_X": 15.0, "VEL_Y": 15.0, "VEL_Z": 15.0, "FREQ": 30.0},
        "bounds": {"VEL_X": (0, 50), "VEL_Y": (0, 50), "VEL_Z": (0, 50), "FREQ": (0, 50)},
        "delta":  {"VEL_X": 3, "VEL_Y": 3, "VEL_Z": 3, "FREQ": 1},
    },
    "ESD": {
        "fast_tags": ["STATUS", "ALARM"],
        "slow_tags": ["VOLT", "CURR", "RESIST"],
        "scale": {"VOLT": 10, "CURR": 100, "RESIST": 100, "STATUS": 1, "ALARM": 1},
        "initial": {"VOLT": 0.0, "CURR": 0.2, "RESIST": 5.0},
        "bounds": {"VOLT": (-100, 100), "CURR": (0, 1), "RESIST": (0.1, 10)},
        "delta":  {"VOLT": 5, "CURR": 0.05, "RESIST": 0.5},
    },
}

ZONE_INDICES = ["01", "02", "03"]
SENSOR_ORDER = ["PART", "TEMP", "HUM", "AMC", "VIB", "ESD"]
REG_PER_SENSOR = 10

def _env_initial(sensor_type):
    state = {"STATUS": 1, "ALARM": 0}
    state.update(SENSOR_SPECS[sensor_type]["initial"])
    return state

SENSORS = {}
for stype in SENSOR_ORDER:
    for idx in ZONE_INDICES:
        SENSORS[f"ENV_{stype}_{idx}"] = _env_initial(stype)

def _env_base_addr(sensor_id):
    stype = sensor_id.split("_")[1]
    idx = int(sensor_id.split("_")[2])
    return (SENSOR_ORDER.index(stype) * 3 + (idx - 1)) * REG_PER_SENSOR

def env_update_fast():
    for sid, state in SENSORS.items():
        stype = sid.split("_")[1]
        if state["STATUS"] == 1:
            if random.random() < ENV_ALARM_RATE:
                state["STATUS"] = 0; state["ALARM"] = 1
        elif state["STATUS"] == 0:
            if random.random() < ENV_RECOVERY_RATE:
                state["STATUS"] = 1; state["ALARM"] = 0
        if stype == "VIB" and state["STATUS"] == 1:
            spec = SENSOR_SPECS["VIB"]
            for tag in ("VEL_X", "VEL_Y", "VEL_Z", "FREQ"):
                state[tag] += random.uniform(-spec["delta"][tag], spec["delta"][tag])
                lo, hi = spec["bounds"][tag]
                state[tag] = max(lo, min(hi, state[tag]))

def env_update_slow():
    for sid, state in SENSORS.items():
        stype = sid.split("_")[1]
        if stype in ("PART", "VIB") or state["STATUS"] != 1:
            continue
        spec = SENSOR_SPECS[stype]
        for tag in spec["slow_tags"]:
            d = spec["delta"].get(tag, 0)
            if d == 0: continue
            state[tag] += random.uniform(-d, d)
            lo, hi = spec["bounds"][tag]
            state[tag] = max(lo, min(hi, state[tag]))

def env_update_particle():
    for sid, state in SENSORS.items():
        if sid.split("_")[1] != "PART" or state["STATUS"] != 1:
            continue
        spec = SENSOR_SPECS["PART"]
        for tag in spec["slow_tags"]:
            state[tag] += random.uniform(-spec["delta"][tag], spec["delta"][tag])
            lo, hi = spec["bounds"][tag]
            state[tag] = max(lo, min(hi, state[tag]))

class ModbusEnvSim:
    def __init__(self):
        self.slave = ModbusSlaveContext(
            hr=ModbusSequentialDataBlock(0, [0] * 200), zero_mode=True)
        self.context = ModbusServerContext(slaves=self.slave, single=True)

    def _write(self, addr, value, scale):
        v = int(value * scale)
        v = (v + 0x10000) & 0xFFFF if v < 0 else v & 0xFFFF
        self.slave.setValues(3, addr, [v])

    def _offsets(self, stype):
        spec = SENSOR_SPECS[stype]
        offsets = {}
        if stype == "VIB":
            for i, t in enumerate(("VEL_X", "VEL_Y", "VEL_Z", "FREQ")):
                offsets[t] = i
        else:
            for i, t in enumerate(spec["slow_tags"]):
                offsets[t] = i
        offsets["STATUS"] = 4
        offsets["ALARM"] = 5
        return offsets

    def sync_all(self):
        for sid, state in SENSORS.items():
            stype = sid.split("_")[1]
            spec = SENSOR_SPECS[stype]
            base = _env_base_addr(sid)
            for tag, offset in self._offsets(stype).items():
                self._write(base + offset, state[tag], spec["scale"][tag])

    async def start(self):
        await StartAsyncTcpServer(
            context=self.context, address=(MODBUS_HOST, MODBUS_ENV_PORT))


# ############################################################
#  메인 루프 — 4개 서버 통합 구동
# ############################################################

async def loop_fast(mb_eqp, opcua, mqtt_sim, mb_env):
    """1초 루프"""
    while True:
        eqp_update_all_fast()
        mb_eqp.sync_fast()
        await opcua.sync_fast()
        mqtt_sim.publish_all()
        env_update_fast()
        mb_env.sync_all()
        await asyncio.sleep(FAST_INTERVAL)

async def loop_slow(mb_eqp, opcua, mb_env):
    """5초 루프"""
    while True:
        eqp_update_all_slow()
        mb_eqp.sync_slow()
        await opcua.sync_slow()
        env_update_slow()
        mb_env.sync_all()
        await asyncio.sleep(SLOW_INTERVAL)

async def loop_particle(mb_env):
    """30초 루프 — PARTICLE"""
    while True:
        env_update_particle()
        mb_env.sync_all()
        await asyncio.sleep(PARTICLE_INTERVAL)

async def loop_print():
    """30초 콘솔 요약"""
    tick = 0
    while True:
        await asyncio.sleep(PRINT_INTERVAL)
        tick += 1
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"\n{'='*64}")
        print(f"[{ts}]  Tick {tick}  ({tick * PRINT_INTERVAL}s 경과)")
        print(f"{'='*64}")

        # 설비 — Modbus (FURN)
        print("  📡 Modbus :5020 (산화공정)")
        for eid, s in FURNS.items():
            m = "🟢" if s["STATUS"] == 1 else "🔴"
            print(f"    {m} {eid}  TEMP={s['TEMP']:7.1f}°C  PRESS={s['PRESS']:5.2f}T  "
                  f"PROD={s['PROD_COUNT']:3d}  NG={s['NG_COUNT']}")

        # 설비 — OPC UA (PECVD/ETCH)
        print("  📡 OPC UA :4840 (박막증착)")
        for eid, s in PECVDS.items():
            m = "🟢" if s["STATUS"] == 1 else "🔴"
            print(f"    {m} {eid}  TEMP={s['TEMP']:6.1f}°C  RF={s['RF_PWR']:5.1f}W  "
                  f"PROD={s['PROD_COUNT']:3d}  NG={s['NG_COUNT']}")

        print("  📡 OPC UA :4840 (식각공정)")
        for eid, s in ETCHES.items():
            m = "🟢" if s["STATUS"] == 1 else "🔴"
            print(f"    {m} {eid}  PRESS={s['PRESS']:5.1f}mT  RF={s['RF_PWR']:5.1f}W  "
                  f"PROD={s['PROD_COUNT']:3d}  NG={s['NG_COUNT']}")

        # MQTT
        print("  📡 MQTT :1883 (포토/배선/검사)")
        for eq in MQTT_EQUIPMENTS:
            m = "🟢" if eq.status == 1 else "🔴"
            print(f"    {m} {eq.equipment_id}  "
                  f"PROD={eq.prod_count:5d}  NG={eq.ng_count:3d}")

        # 환경 센서
        print("  📡 Modbus :5021 (환경 BMS)")
        for idx in ZONE_INDICES:
            t = SENSORS[f"ENV_TEMP_{idx}"]
            h = SENSORS[f"ENV_HUM_{idx}"]
            print(f"    구역{idx}  TEMP={t['VAL']:5.2f}°C  HUM={h['VAL']:5.1f}%  "
                  f"PART_03={SENSORS[f'ENV_PART_{idx}']['CNT_03']:.0f}")


async def main():
    print()
    print("=" * 64)
    print("  2조 SCADA-DAS 통합 시뮬레이터")
    print("=" * 64)
    print(f"  [1] Modbus  :{MODBUS_EQP_PORT}  산화 FURN_01~03")
    print(f"  [2] OPC UA  :{OPCUA_PORT}   박막 PECVD_01~03 + 식각 ETCH_01~03")
    print(f"  [3] MQTT    :{MQTT_PORT}   포토 TRACK + 배선 SPTT + 검사 PROBE (각 3대)")
    print(f"  [4] Modbus  :{MODBUS_ENV_PORT}  환경 BMS 18센서 (6타입 × 3구역)")
    print(f"  설비 총 18대 + 환경 18센서 = 36 데이터 소스")
    print(f"  Fast {FAST_INTERVAL}s / Slow {SLOW_INTERVAL}s / Particle {PARTICLE_INTERVAL}s")
    print("=" * 64)

    mb_eqp = ModbusEquipSim()
    opcua  = OPCUASim()
    mqtt_s = MQTTSim()
    mb_env = ModbusEnvSim()

    # 초기화
    await opcua.setup()
    mqtt_s.start()
    mb_env.sync_all()

    print("\n✅ 모든 서버 시작 완료. Ctrl+C로 종료.\n")

    async with opcua.server:
        try:
            await asyncio.gather(
                mb_eqp.start(),
                mb_env.start(),
                loop_fast(mb_eqp, opcua, mqtt_s, mb_env),
                loop_slow(mb_eqp, opcua, mb_env),
                loop_particle(mb_env),
                loop_print(),
            )
        except asyncio.CancelledError:
            pass
        finally:
            mqtt_s.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏹ 통합 시뮬레이터 종료\n")
        sys.exit(0)
