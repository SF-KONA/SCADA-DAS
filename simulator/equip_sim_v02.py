"""
==============================================================
설비 시뮬레이터 — Modbus + OPC UA (다중 주기 버전)
2조 SFaaS 프로젝트 / Day 6 / 김완택
==============================================================

담당 통신:
  - Modbus TCP slave   (port 5020)  : 산화공정 FURN_01·02·03
  - OPC UA server      (port 4840)  : 박막증착 PECVD_01·02·03
                                      식각공정 ETCH_01·02·03

★ 다중 주기 구조 ★
  1초 루프  : STATUS, ALARM, TIME           (즉시 반응 필요)
  5초 루프  : TEMP, PRESS, FLOW, RF_PWR…    (공정 파라미터)
  이벤트    : OX_THICK, DEP_THICK, ETCH_DEP, (사이클 완료 시)
              PROD_COUNT, NG_COUNT, CYCLE_TIME

설치:
    pip install pymodbus asyncua

실행:
    python simulator.py
==============================================================
"""

import asyncio
import random
import sys
from datetime import datetime

from asyncua import Server
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import StartAsyncTcpServer


# ============================================================
# 서버 설정
# ============================================================
MODBUS_HOST = "0.0.0.0"
MODBUS_PORT = 5020
OPCUA_HOST  = "0.0.0.0"
OPCUA_PORT  = 4840
OPCUA_NAMESPACE = "http://team2.factory"

FAST_INTERVAL = 1           # 1초 — STATUS, ALARM, TIME
SLOW_INTERVAL = 5           # 5초 — 공정 파라미터
PRINT_INTERVAL = 30         # 30초 — 콘솔 요약 출력

ALARM_RATE_PER_SEC    = 0.002    # 1초당 알람 발생 확률 (≈ 8분에 1번)
RECOVERY_RATE_PER_SEC = 0.01     # 1초당 복구 확률 (≈ 100초 평균)
NG_PROB = 0.03                   # 1 lot당 불량 확률


# ============================================================
# 설비 초기 상태
# ============================================================
def initial_furn_state():
    return {
        "TEMP": 1000.0, "PRESS": 5.0, "O2_FLOW": 1250.0, "N2_FLOW": 600.0,
        "TIME": 0, "OX_THICK": 1250.0, "STATUS": 1, "ALARM": 0,
        "CYCLE_TIME": 60, "PROD_COUNT": 0, "NG_COUNT": 0,
        "_cycle_elapsed": 0,
    }


def initial_pecvd_state():
    return {
        "TEMP": 375.0, "PRESS": 2.5, "RF_PWR": 300.0,
        "SIH4_FLOW": 300.0, "N2O_FLOW": 600.0,
        "DEP_THICK": 1750.0, "STATUS": 1, "ALARM": 0,
        "CYCLE_TIME": 90, "PROD_COUNT": 0, "NG_COUNT": 0,
        "_cycle_elapsed": 0,
    }


def initial_etch_state():
    return {
        "PRESS": 25.0, "RF_PWR": 500.0, "CF4_FLOW": 60.0,
        "O2_FLOW": 17.0, "TEMP": 50.0, "ETCH_DEP": 900.0,
        "STATUS": 1, "ALARM": 0,
        "CYCLE_TIME": 75, "PROD_COUNT": 0, "NG_COUNT": 0,
        "_cycle_elapsed": 0,
    }


FURNS   = {f"FURN_0{i}":  initial_furn_state()  for i in (1, 2, 3)}
PECVDS  = {f"PECVD_0{i}": initial_pecvd_state() for i in (1, 2, 3)}
ETCHES  = {f"ETCH_0{i}":  initial_etch_state()  for i in (1, 2, 3)}


# ============================================================
# Fast 갱신 (1초 루프) — STATUS, ALARM, TIME
# ============================================================
def update_fast_common(state, has_time=False):
    """모든 설비 공통: 알람 천이 + TIME tick"""
    if state["STATUS"] == 1:
        if random.random() < ALARM_RATE_PER_SEC:
            state["STATUS"] = 2
            state["ALARM"]  = 1
        elif has_time:
            state["TIME"] = min(state["TIME"] + 1, 120)
    elif state["STATUS"] == 2:
        if random.random() < RECOVERY_RATE_PER_SEC:
            state["STATUS"] = 1
            state["ALARM"]  = 0


def update_furns_fast():
    for state in FURNS.values():
        update_fast_common(state, has_time=True)  # FURN만 TIME 있음


def update_pecvds_fast():
    for state in PECVDS.values():
        update_fast_common(state, has_time=False)


def update_etches_fast():
    for state in ETCHES.values():
        update_fast_common(state, has_time=False)


# ============================================================
# Slow 갱신 (5초 루프) — 공정 파라미터 + 사이클 진행
# ============================================================
def random_walk(state, deltas, bounds):
    for tag, delta in deltas.items():
        state[tag] += random.uniform(-delta, delta)
        lo, hi = bounds[tag]
        state[tag] = max(lo, min(hi, state[tag]))


def advance_cycle(state, lot_targets):
    """사이클 진행 + 완료 시 lot 단위 태그 갱신"""
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


def update_furns_slow():
    for state in FURNS.values():
        if state["STATUS"] != 1:
            continue  # ALARM 중엔 공정 정지
        random_walk(
            state,
            deltas={"TEMP": 3, "PRESS": 0.1, "O2_FLOW": 20, "N2_FLOW": 10},
            bounds={
                "TEMP": (900, 1100), "PRESS": (0.1, 10),
                "O2_FLOW": (500, 2000), "N2_FLOW": (200, 1000),
            },
        )
        advance_cycle(state, lot_targets={"OX_THICK": (500, 2000)})


def update_pecvds_slow():
    for state in PECVDS.values():
        if state["STATUS"] != 1:
            continue
        random_walk(
            state,
            deltas={"TEMP": 2, "PRESS": 0.05, "RF_PWR": 5,
                    "SIH4_FLOW": 5, "N2O_FLOW": 10},
            bounds={
                "TEMP": (300, 450), "PRESS": (0.5, 5), "RF_PWR": (100, 500),
                "SIH4_FLOW": (100, 500), "N2O_FLOW": (200, 1000),
            },
        )
        advance_cycle(state, lot_targets={"DEP_THICK": (500, 3000)})


def update_etches_slow():
    for state in ETCHES.values():
        if state["STATUS"] != 1:
            continue
        random_walk(
            state,
            deltas={"PRESS": 1, "RF_PWR": 10, "CF4_FLOW": 2,
                    "O2_FLOW": 0.5, "TEMP": 1},
            bounds={
                "PRESS": (5, 50), "RF_PWR": (200, 800),
                "CF4_FLOW": (20, 100), "O2_FLOW": (5, 30), "TEMP": (20, 80),
            },
        )
        advance_cycle(state, lot_targets={"ETCH_DEP": (300, 1500)})


# ============================================================
# Modbus 슬레이브 — 산화공정
# ============================================================
#
# 레지스터 매핑 (Holding Register, 함수코드 3)
# ──────────────────────────────────────────────
#  FURN_01: HR  0~19   (11 used + 9 reserved)
#  FURN_02: HR 20~39
#  FURN_03: HR 40~59
#
#  각 설비 내부 오프셋 (★ Fast/Slow 영역 분리):
#  ┌─────── FAST 영역 (1초 갱신) ───────┐
#    +0  STATUS      × 1    1s
#    +1  ALARM       × 1    1s
#    +2  TIME        × 1    1s
#  └────────────────────────────────────┘
#  ┌─────── SLOW 영역 (5초 갱신) ───────┐
#    +3  TEMP        × 10   5s   (1000.5°C → 10005)
#    +4  PRESS       × 100  5s   (5.25 Torr → 525)
#    +5  O2_FLOW     × 1    5s
#    +6  N2_FLOW     × 1    5s
#    +7  OX_THICK    × 1    lot
#    +8  CYCLE_TIME  × 1    lot
#    +9  PROD_COUNT  × 1    1m
#    +10 NG_COUNT    × 1    1m
#  └────────────────────────────────────┘
#
# Node-RED modbus-read 노드 설정 — 두 그룹으로 분리:
#
#   [Group A — 1초 폴링: 빠른 태그]
#     FC: 3, Address: 0,  Quantity: 3,  Poll: 1000 ms   (FURN_01 fast)
#     FC: 3, Address: 20, Quantity: 3,  Poll: 1000 ms   (FURN_02 fast)
#     FC: 3, Address: 40, Quantity: 3,  Poll: 1000 ms   (FURN_03 fast)
#
#   [Group B — 5초 폴링: 공정값]
#     FC: 3, Address: 3,  Quantity: 8,  Poll: 5000 ms   (FURN_01 slow)
#     FC: 3, Address: 23, Quantity: 8,  Poll: 5000 ms   (FURN_02 slow)
#     FC: 3, Address: 43, Quantity: 8,  Poll: 5000 ms   (FURN_03 slow)
# ──────────────────────────────────────────────
FURN_FAST_LAYOUT = [
    ("STATUS", 1), ("ALARM", 1), ("TIME", 1),
]
FURN_SLOW_LAYOUT = [
    ("TEMP",       10),  ("PRESS",      100),
    ("O2_FLOW",    1),   ("N2_FLOW",    1),
    ("OX_THICK",   1),   ("CYCLE_TIME", 1),
    ("PROD_COUNT", 1),   ("NG_COUNT",   1),
]
FURN_REG_BASES = {"FURN_01": 0, "FURN_02": 20, "FURN_03": 40}
FAST_OFFSET = 0    # 0~2
SLOW_OFFSET = 3    # 3~10


class ModbusSimulator:
    def __init__(self):
        self.slave = ModbusSlaveContext(
            hr=ModbusSequentialDataBlock(0, [0] * 100),
            zero_mode=True,
        )
        self.context = ModbusServerContext(slaves=self.slave, single=True)

    def _write_register(self, addr, value, scale):
        v = int(value * scale) & 0xFFFF
        self.slave.setValues(3, addr, [v])

    def sync_fast(self):
        for eq_id, base in FURN_REG_BASES.items():
            state = FURNS[eq_id]
            for i, (tag, scale) in enumerate(FURN_FAST_LAYOUT):
                self._write_register(base + FAST_OFFSET + i, state[tag], scale)

    def sync_slow(self):
        for eq_id, base in FURN_REG_BASES.items():
            state = FURNS[eq_id]
            for i, (tag, scale) in enumerate(FURN_SLOW_LAYOUT):
                self._write_register(base + SLOW_OFFSET + i, state[tag], scale)

    async def start(self):
        await StartAsyncTcpServer(
            context=self.context,
            address=(MODBUS_HOST, MODBUS_PORT),
        )


# ============================================================
# OPC UA 서버 — 박막증착 + 식각공정
# ============================================================
#
# 노드 구조:
#   Objects/
#     ThinFilm/
#       PECVD_01/
#         (Fast: STATUS, ALARM)
#         (Slow: TEMP, PRESS, RF_PWR, SIH4_FLOW, N2O_FLOW,
#                DEP_THICK, CYCLE_TIME, PROD_COUNT, NG_COUNT)
#       PECVD_02/ ... PECVD_03/ ...
#     Etching/
#       ETCH_01/
#         (Fast: STATUS, ALARM)
#         (Slow: PRESS, RF_PWR, CF4_FLOW, O2_FLOW, TEMP,
#                ETCH_DEP, CYCLE_TIME, PROD_COUNT, NG_COUNT)
#       ETCH_02/ ... ETCH_03/ ...
#
# Node-RED OpcUa-Client 설정 — 두 Subscription:
#   [Subscription A — 1초] : 각 설비의 STATUS·ALARM Variable
#   [Subscription B — 5초] : 나머지 공정 Variable
# ──────────────────────────────────────────────
PECVD_FAST_TAGS = ("STATUS", "ALARM")
PECVD_SLOW_TAGS = ("TEMP", "PRESS", "RF_PWR", "SIH4_FLOW", "N2O_FLOW",
                   "DEP_THICK", "CYCLE_TIME", "PROD_COUNT", "NG_COUNT")

ETCH_FAST_TAGS = ("STATUS", "ALARM")
ETCH_SLOW_TAGS = ("PRESS", "RF_PWR", "CF4_FLOW", "O2_FLOW", "TEMP",
                  "ETCH_DEP", "CYCLE_TIME", "PROD_COUNT", "NG_COUNT")


class OPCUASimulator:
    def __init__(self):
        self.server = Server()
        self.vars = {}  # {eq_id: {tag: Variable}}

    async def setup(self):
        await self.server.init()
        self.server.set_endpoint(
            f"opc.tcp://{OPCUA_HOST}:{OPCUA_PORT}/team2/server/"
        )
        self.server.set_server_name("Team2 SCADA Simulator")

        idx = await self.server.register_namespace(OPCUA_NAMESPACE)
        objects = self.server.nodes.objects

        thinfilm = await objects.add_folder(idx, "ThinFilm")
        for eq_id, state in PECVDS.items():
            obj = await thinfilm.add_object(idx, eq_id)
            self.vars[eq_id] = {}
            for tag, value in state.items():
                if tag.startswith("_"):
                    continue
                var = await obj.add_variable(idx, tag, float(value))
                await var.set_writable()
                self.vars[eq_id][tag] = var

        etching = await objects.add_folder(idx, "Etching")
        for eq_id, state in ETCHES.items():
            obj = await etching.add_object(idx, eq_id)
            self.vars[eq_id] = {}
            for tag, value in state.items():
                if tag.startswith("_"):
                    continue
                var = await obj.add_variable(idx, tag, float(value))
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


# ============================================================
# 다중 주기 루프
# ============================================================
async def loop_fast(modbus_sim, opcua_sim):
    """1초 루프 — STATUS, ALARM, TIME 처리"""
    while True:
        update_furns_fast()
        update_pecvds_fast()
        update_etches_fast()
        modbus_sim.sync_fast()
        await opcua_sim.sync_fast()
        await asyncio.sleep(FAST_INTERVAL)


async def loop_slow(modbus_sim, opcua_sim):
    """5초 루프 — 공정 파라미터 + 사이클 진행"""
    while True:
        update_furns_slow()
        update_pecvds_slow()
        update_etches_slow()
        modbus_sim.sync_slow()
        await opcua_sim.sync_slow()
        await asyncio.sleep(SLOW_INTERVAL)


async def loop_print():
    """30초 루프 — 콘솔 상태 요약"""
    tick = 0
    while True:
        await asyncio.sleep(PRINT_INTERVAL)
        tick += 1
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{ts}]  Print Tick {tick}  ({tick * PRINT_INTERVAL}s 경과)")

        print("  📡 Modbus (산화공정)")
        for eq_id, state in FURNS.items():
            mark = "🟢" if state["STATUS"] == 1 else "🔴"
            print(f"    {mark} {eq_id}  "
                  f"TEMP={state['TEMP']:7.2f}°C  "
                  f"PRESS={state['PRESS']:5.2f}T  "
                  f"TIME={state['TIME']:3d}m  "
                  f"PROD={state['PROD_COUNT']:3d}  NG={state['NG_COUNT']:3d}")

        print("  📡 OPC UA (박막증착)")
        for eq_id, state in PECVDS.items():
            mark = "🟢" if state["STATUS"] == 1 else "🔴"
            print(f"    {mark} {eq_id}  "
                  f"TEMP={state['TEMP']:6.2f}°C  "
                  f"RF={state['RF_PWR']:6.1f}W  "
                  f"PROD={state['PROD_COUNT']:3d}  NG={state['NG_COUNT']:3d}")

        print("  📡 OPC UA (식각공정)")
        for eq_id, state in ETCHES.items():
            mark = "🟢" if state["STATUS"] == 1 else "🔴"
            print(f"    {mark} {eq_id}  "
                  f"PRESS={state['PRESS']:6.2f}mT  "
                  f"RF={state['RF_PWR']:6.1f}W  "
                  f"PROD={state['PROD_COUNT']:3d}  NG={state['NG_COUNT']:3d}")


async def main():
    print("=" * 64)
    print("  2조 SFaaS 시뮬레이터 — Modbus + OPC UA (다중 주기)")
    print("=" * 64)
    print(f"  Modbus slave : {MODBUS_HOST}:{MODBUS_PORT}")
    print(f"                  └ 산화공정 FURN_01·02·03")
    print(f"  OPC UA server: opc.tcp://{OPCUA_HOST}:{OPCUA_PORT}/team2/server/")
    print(f"                  ├ ThinFilm/PECVD_01·02·03")
    print(f"                  └ Etching/ETCH_01·02·03")
    print(f"  Fast 루프    : {FAST_INTERVAL}초 (STATUS, ALARM, TIME)")
    print(f"  Slow 루프    : {SLOW_INTERVAL}초 (공정 파라미터)")
    print("=" * 64)

    modbus_sim = ModbusSimulator()
    opcua_sim  = OPCUASimulator()

    await opcua_sim.setup()

    async with opcua_sim.server:
        try:
            await asyncio.gather(
                modbus_sim.start(),
                loop_fast(modbus_sim, opcua_sim),
                loop_slow(modbus_sim, opcua_sim),
                loop_print(),
            )
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n시뮬레이터 종료\n")
        sys.exit(0)
