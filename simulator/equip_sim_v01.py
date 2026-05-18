"""
==============================================================
설비 시뮬레이터 — Modbus + OPC UA
2조 SFaaS 프로젝트 / Day 6 / 김완택
==============================================================

담당 통신:
  - Modbus TCP slave   (port 5020)  : 산화공정 FURN_01·02·03
  - OPC UA server      (port 4840)  : 박막증착 PECVD_01·02·03
                                      식각공정 ETCH_01·02·03

데이터 명세: 첨부 정의서 그대로 (단, 5초 주기로 단순화)

설치:
    pip install pymodbus asyncua

실행:
    python simulator.py

종료: Ctrl+C
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
MODBUS_PORT = 5020          # 502는 관리자 권한 필요 → 5020 사용
OPCUA_HOST  = "0.0.0.0"
OPCUA_PORT  = 4840
OPCUA_NAMESPACE = "http://team2.factory"

UPDATE_INTERVAL = 5         # 데이터 갱신 주기 (초) — 5초 버킷
ALARM_PROB      = 0.01      # 매 갱신당 알람 발생 확률
RECOVERY_PROB   = 0.05      # 알람 상태에서 복구 확률
NG_PROB         = 0.03      # 1 lot당 불량 발생 확률


# ============================================================
# 설비 초기 상태 — 정의서 정상 범위 중앙값
# ============================================================
def initial_furn_state():
    """산화공정 — 수직형 확산로 (Vertical Diffusion Furnace)"""
    return {
        # 공정 데이터 (5초 주기)
        "TEMP":       1000.0,   # 900~1100 °C
        "PRESS":      5.0,      # 0.1~10 Torr
        "O2_FLOW":    1250.0,   # 500~2000 sccm
        "N2_FLOW":    600.0,    # 200~1000 sccm
        "TIME":       0,        # 0~120 min
        # lot 단위 측정값
        "OX_THICK":   1250.0,   # 500~2000 Å
        # 상태·알람
        "STATUS":     1,        # 0=idle 1=run 2=alarm
        "ALARM":      0,
        # OEE
        "CYCLE_TIME": 60,       # 30~300 sec
        "PROD_COUNT": 0,
        "NG_COUNT":   0,
        # internal
        "_cycle_elapsed": 0,
    }


def initial_pecvd_state():
    """박막증착 — PECVD (Plasma Enhanced CVD)"""
    return {
        "TEMP":       375.0,    # 300~450 °C
        "PRESS":      2.5,      # 0.5~5 Torr
        "RF_PWR":     300.0,    # 100~500 W
        "SIH4_FLOW":  300.0,    # 100~500 sccm
        "N2O_FLOW":   600.0,    # 200~1000 sccm
        "DEP_THICK":  1750.0,   # 500~3000 Å (lot)
        "STATUS":     1,
        "ALARM":      0,
        "CYCLE_TIME": 90,
        "PROD_COUNT": 0,
        "NG_COUNT":   0,
        "_cycle_elapsed": 0,
    }


def initial_etch_state():
    """식각공정 — 건식 식각기 (Dry Etcher / ICP)"""
    return {
        "PRESS":      25.0,     # 5~50 mTorr
        "RF_PWR":     500.0,    # 200~800 W
        "CF4_FLOW":   60.0,     # 20~100 sccm
        "O2_FLOW":    17.0,     # 5~30 sccm
        "TEMP":       50.0,     # 20~80 °C
        "ETCH_DEP":   900.0,    # 300~1500 Å (lot)
        "STATUS":     1,
        "ALARM":      0,
        "CYCLE_TIME": 75,
        "PROD_COUNT": 0,
        "NG_COUNT":   0,
        "_cycle_elapsed": 0,
    }


FURNS   = {f"FURN_0{i}":  initial_furn_state()  for i in (1, 2, 3)}
PECVDS  = {f"PECVD_0{i}": initial_pecvd_state() for i in (1, 2, 3)}
ETCHES  = {f"ETCH_0{i}":  initial_etch_state()  for i in (1, 2, 3)}


# ============================================================
# 데이터 변동 로직 — RUN 상태 공통 패턴
# ============================================================
def update_running(state, deltas, bounds, lot_targets):
    """RUN 상태에서 랜덤워크 + lot 완료 처리"""
    # 랜덤워크
    for tag, delta in deltas.items():
        state[tag] += random.uniform(-delta, delta)
        lo, hi = bounds[tag]
        state[tag] = max(lo, min(hi, state[tag]))

    # 사이클 진행
    state["_cycle_elapsed"] += UPDATE_INTERVAL
    if state["_cycle_elapsed"] >= state["CYCLE_TIME"]:
        # 1 lot 완료
        state["PROD_COUNT"] += 1
        if random.random() < NG_PROB:
            state["NG_COUNT"] += 1
        # lot 단위 측정값 갱신
        for tag, (lo, hi) in lot_targets.items():
            state[tag] = random.uniform(lo, hi)
        state["_cycle_elapsed"] = 0


def update_furnace(state):
    if state["STATUS"] == 1:  # RUN
        update_running(
            state,
            deltas={"TEMP": 3, "PRESS": 0.1, "O2_FLOW": 20, "N2_FLOW": 10},
            bounds={
                "TEMP":    (900, 1100),
                "PRESS":   (0.1, 10),
                "O2_FLOW": (500, 2000),
                "N2_FLOW": (200, 1000),
            },
            lot_targets={"OX_THICK": (500, 2000)},
        )
        state["TIME"] = min(state["TIME"] + 1, 120)

        if random.random() < ALARM_PROB:
            state["TEMP"]   = random.uniform(1170, 1200)  # 과열
            state["STATUS"] = 2
            state["ALARM"]  = 1

    elif state["STATUS"] == 2:  # ALARM
        if random.random() < RECOVERY_PROB:
            state["TEMP"]   = 1000.0
            state["STATUS"] = 1
            state["ALARM"]  = 0


def update_pecvd(state):
    if state["STATUS"] == 1:
        update_running(
            state,
            deltas={
                "TEMP": 2, "PRESS": 0.05, "RF_PWR": 5,
                "SIH4_FLOW": 5, "N2O_FLOW": 10,
            },
            bounds={
                "TEMP":      (300, 450),
                "PRESS":     (0.5, 5),
                "RF_PWR":    (100, 500),
                "SIH4_FLOW": (100, 500),
                "N2O_FLOW":  (200, 1000),
            },
            lot_targets={"DEP_THICK": (500, 3000)},
        )

        if random.random() < ALARM_PROB:
            state["TEMP"]   = random.uniform(480, 500)
            state["STATUS"] = 2
            state["ALARM"]  = 1

    elif state["STATUS"] == 2:
        if random.random() < RECOVERY_PROB:
            state["TEMP"]   = 375.0
            state["STATUS"] = 1
            state["ALARM"]  = 0


def update_etcher(state):
    if state["STATUS"] == 1:
        update_running(
            state,
            deltas={
                "PRESS": 1, "RF_PWR": 10, "CF4_FLOW": 2,
                "O2_FLOW": 0.5, "TEMP": 1,
            },
            bounds={
                "PRESS":    (5, 50),
                "RF_PWR":   (200, 800),
                "CF4_FLOW": (20, 100),
                "O2_FLOW":  (5, 30),
                "TEMP":     (20, 80),
            },
            lot_targets={"ETCH_DEP": (300, 1500)},
        )

        if random.random() < ALARM_PROB:
            state["TEMP"]   = random.uniform(95, 100)
            state["STATUS"] = 2
            state["ALARM"]  = 1

    elif state["STATUS"] == 2:
        if random.random() < RECOVERY_PROB:
            state["TEMP"]   = 50.0
            state["STATUS"] = 1
            state["ALARM"]  = 0


# ============================================================
# Modbus 슬레이브 — 산화공정 (FURN_01·02·03)
# ============================================================
#
# 레지스터 매핑 (Holding Register, 함수코드 3)
# ──────────────────────────────────────────────
#  FURN_01: HR  0~19  (11 used + 9 reserved)
#  FURN_02: HR 20~39
#  FURN_03: HR 40~59
#
#  각 설비 내부 오프셋:
#    +0  TEMP        × 10   (예: 1000.5°C → 10005)
#    +1  PRESS       × 100  (예: 5.25 Torr → 525)
#    +2  O2_FLOW     × 1
#    +3  N2_FLOW     × 1
#    +4  TIME        × 1
#    +5  OX_THICK    × 1
#    +6  STATUS      × 1    (0/1/2)
#    +7  ALARM       × 1    (0/1)
#    +8  CYCLE_TIME  × 1
#    +9  PROD_COUNT  × 1
#    +10 NG_COUNT    × 1
#
# Node-RED modbus-read 노드 설정 예시:
#   Unit-Id : 1
#   FC      : FC 3 - Read Holding Registers
#   Address : 0
#   Quantity: 60   (3대 × 20 reg)
#   Poll    : 5000 ms
# ──────────────────────────────────────────────
FURN_REG_LAYOUT = [
    ("TEMP",       10),
    ("PRESS",      100),
    ("O2_FLOW",    1),
    ("N2_FLOW",    1),
    ("TIME",       1),
    ("OX_THICK",   1),
    ("STATUS",     1),
    ("ALARM",      1),
    ("CYCLE_TIME", 1),
    ("PROD_COUNT", 1),
    ("NG_COUNT",   1),
]
FURN_REG_BASES = {"FURN_01": 0, "FURN_02": 20, "FURN_03": 40}


class ModbusSimulator:
    def __init__(self):
        # Holding Register 100개 (FURN 3대 × 20 + 여유)
        self.slave = ModbusSlaveContext(
            hr=ModbusSequentialDataBlock(0, [0] * 100),
            zero_mode=True,  # 주소를 0부터 시작
        )
        self.context = ModbusServerContext(slaves=self.slave, single=True)

    def sync_state(self):
        """FURNS 상태 → Modbus 레지스터"""
        for eq_id, base in FURN_REG_BASES.items():
            state = FURNS[eq_id]
            for offset, (tag, scale) in enumerate(FURN_REG_LAYOUT):
                value = int(state[tag] * scale)
                # int16 안전 처리 (음수는 two's complement)
                value = value & 0xFFFF
                # Holding Register = 함수코드 3
                self.slave.setValues(3, base + offset, [value])

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
#     ThinFilm/          ← 박막증착 폴더
#       PECVD_01/
#         TEMP, PRESS, RF_PWR, SIH4_FLOW, N2O_FLOW,
#         DEP_THICK, STATUS, ALARM,
#         CYCLE_TIME, PROD_COUNT, NG_COUNT
#       PECVD_02/ ...
#       PECVD_03/ ...
#     Etching/           ← 식각공정 폴더
#       ETCH_01/
#         PRESS, RF_PWR, CF4_FLOW, O2_FLOW, TEMP,
#         ETCH_DEP, STATUS, ALARM,
#         CYCLE_TIME, PROD_COUNT, NG_COUNT
#       ETCH_02/ ...
#       ETCH_03/ ...
#
# Node-RED OpcUa-Client 설정 예시:
#   Endpoint: opc.tcp://<서버IP>:4840/team2/server/
#   Security: None
#   NodeId  : ns=2;s=ThinFilm/PECVD_01/TEMP
#   (또는 OPC UA Browse로 직접 탐색)
# ──────────────────────────────────────────────
class OPCUASimulator:
    def __init__(self):
        self.server = Server()
        self.variables = {}  # {eq_id: {tag: Variable}}

    async def setup(self):
        await self.server.init()
        self.server.set_endpoint(
            f"opc.tcp://{OPCUA_HOST}:{OPCUA_PORT}/team2/server/"
        )
        self.server.set_server_name("Team2 SCADA Simulator")

        idx = await self.server.register_namespace(OPCUA_NAMESPACE)
        objects = self.server.nodes.objects

        # 박막증착
        thinfilm = await objects.add_folder(idx, "ThinFilm")
        for eq_id, state in PECVDS.items():
            obj = await thinfilm.add_object(idx, eq_id)
            self.variables[eq_id] = {}
            for tag, value in state.items():
                if tag.startswith("_"):
                    continue
                var = await obj.add_variable(idx, tag, float(value))
                await var.set_writable()
                self.variables[eq_id][tag] = var

        # 식각공정
        etching = await objects.add_folder(idx, "Etching")
        for eq_id, state in ETCHES.items():
            obj = await etching.add_object(idx, eq_id)
            self.variables[eq_id] = {}
            for tag, value in state.items():
                if tag.startswith("_"):
                    continue
                var = await obj.add_variable(idx, tag, float(value))
                await var.set_writable()
                self.variables[eq_id][tag] = var

    async def sync_state(self):
        """PECVDS, ETCHES 상태 → OPC UA Variable"""
        combined = {**PECVDS, **ETCHES}
        for eq_id, state in combined.items():
            for tag, var in self.variables[eq_id].items():
                await var.write_value(float(state[tag]))


# ============================================================
# 메인 루프
# ============================================================
def print_console(cycle):
    """30초마다 콘솔에 현재 상태 요약 출력"""
    if cycle % 6 != 0:
        return

    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}]  Cycle {cycle:4d}  ({cycle * UPDATE_INTERVAL}s 경과)")

    print("  📡 Modbus  (산화공정)")
    for eq_id, state in FURNS.items():
        mark = "🟢" if state["STATUS"] == 1 else "🔴"
        print(f"    {mark} {eq_id}  "
              f"TEMP={state['TEMP']:7.2f}°C  "
              f"PRESS={state['PRESS']:6.2f}T  "
              f"PROD={state['PROD_COUNT']:3d}  NG={state['NG_COUNT']:3d}")

    print("  📡 OPC UA  (박막증착)")
    for eq_id, state in PECVDS.items():
        mark = "🟢" if state["STATUS"] == 1 else "🔴"
        print(f"    {mark} {eq_id}  "
              f"TEMP={state['TEMP']:6.2f}°C  "
              f"RF={state['RF_PWR']:6.1f}W  "
              f"PROD={state['PROD_COUNT']:3d}  NG={state['NG_COUNT']:3d}")

    print("  📡 OPC UA  (식각공정)")
    for eq_id, state in ETCHES.items():
        mark = "🟢" if state["STATUS"] == 1 else "🔴"
        print(f"    {mark} {eq_id}  "
              f"PRESS={state['PRESS']:6.2f}mT  "
              f"RF={state['RF_PWR']:6.1f}W  "
              f"PROD={state['PROD_COUNT']:3d}  NG={state['NG_COUNT']:3d}")


async def data_generation_loop(modbus_sim, opcua_sim):
    """메인 데이터 생성 + 양 서버 동기화 루프"""
    cycle = 0
    while True:
        # 1) 데이터 변동
        for state in FURNS.values():
            update_furnace(state)
        for state in PECVDS.values():
            update_pecvd(state)
        for state in ETCHES.values():
            update_etcher(state)

        # 2) 양 서버에 동일 상태 반영
        modbus_sim.sync_state()
        await opcua_sim.sync_state()

        # 3) 콘솔 출력
        print_console(cycle)

        cycle += 1
        await asyncio.sleep(UPDATE_INTERVAL)


async def main():
    print("=" * 64)
    print("  2조 SFaaS 시뮬레이터 — Modbus + OPC UA")
    print("=" * 64)
    print(f"  Modbus slave : {MODBUS_HOST}:{MODBUS_PORT}")
    print(f"                  └ 산화공정 FURN_01·02·03")
    print(f"  OPC UA server: opc.tcp://{OPCUA_HOST}:{OPCUA_PORT}/team2/server/")
    print(f"                  ├ ThinFilm/PECVD_01·02·03")
    print(f"                  └ Etching/ETCH_01·02·03")
    print(f"  갱신 주기    : {UPDATE_INTERVAL}초")
    print("=" * 64)

    modbus_sim = ModbusSimulator()
    opcua_sim  = OPCUASimulator()

    await opcua_sim.setup()

    async with opcua_sim.server:
        try:
            await asyncio.gather(
                modbus_sim.start(),
                data_generation_loop(modbus_sim, opcua_sim),
            )
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n시뮬레이터 종료\n")
        sys.exit(0)
