"""
==============================================================
환경 센서 시뮬레이터 — Modbus TCP (다중 주기 버전)
DB하이텍 음성공장 Web SCADA / 환경 18센서
==============================================================

담당 통신:
  - Modbus TCP slave (port 5021): 환경 18센서
    ├ 파티클  (PART) × 3구역  (FRONT / BACK / EQP)
    ├ 온도    (TEMP) × 3구역
    ├ 습도    (HUM)  × 3구역
    ├ AMC          × 3구역  (Airborne Molecular Contamination)
    ├ 진동    (VIB) × 3구역
    └ ESD          × 3구역

  ※ 강사님 시뮬레이터(설비, port 5020)와 별도 포트로 분리
     실제 공장에서도 환경 BMS는 별도 네트워크 세그먼트로 운영

★ 다중 주기 구조 ★
  1초 루프  : STATUS, ALARM          (즉시 반응 필요)
  5초 루프  : 측정값 random walk      (TEMP, HUM, AMC, VIB, ESD)
  30초 루프 : PARTICLE 카운트         (느린 측정 주기)

설치:
    pip install pymodbus

실행:
    python env_simulator.py

검증 (Node-RED Modbus-Read):
    FC: 3, Address: 0, Quantity: 180  → 18센서 전체 일괄 폴링
==============================================================
"""

import asyncio
import random
import sys
from datetime import datetime

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
MODBUS_PORT = 5021                # 설비 시뮬레이터(5020)와 분리

FAST_INTERVAL     = 1             # 1초  — STATUS, ALARM, VIB (진동은 빠른 감지)
SLOW_INTERVAL     = 5             # 5초  — TEMP, HUM, AMC, ESD
PARTICLE_INTERVAL = 30            # 30초 — PARTICLE (느린 측정)
PRINT_INTERVAL    = 30            # 30초 — 콘솔 출력

ALARM_RATE_PER_SEC    = 0.001     # 1초당 알람 발생 확률 (≈ 16분에 1번)
RECOVERY_RATE_PER_SEC = 0.02      # 1초당 복구 확률 (≈ 50초 평균)


# ============================================================
# 센서 스펙 정의 — 데이터 정의서 기반
# ============================================================
#
# 각 센서 타입의 레지스터 배치 (모든 센서 10 레지스터 할당, 예비 포함):
#
#   +0~+3  측정값 (각 1 레지스터, 스케일 적용)
#   +4     STATUS  (1=정상, 0=이상)
#   +5     ALARM   (0=정상, 1=발생)
#   +6~+9  예비 (확장용)
#
# 스케일 (Float → Int16 변환):
#   ×100  : 소수 둘째 자리까지 (예 22.35°C → 2235)
#   ×10   : 소수 첫째 자리까지 (예 75.2 → 752)
#   ×1    : 정수 그대로
#   ×1000 : ppb 단위 (예 0.123 ppb → 123)
# ============================================================

SENSOR_SPECS = {
    "PART": {
        # 파티클: ISO 14644-1 Class 5 기준
        # CNT_03 ≤ 3,520 / CNT_05 ≤ 832 / CNT_10 ≤ 83 (개/m³)
        "fast_tags": ["STATUS", "ALARM"],
        "slow_tags": ["CNT_03", "CNT_05", "CNT_10"],
        "is_particle": True,   # 30초 주기로 처리
        "scale": {"CNT_03": 1, "CNT_05": 1, "CNT_10": 1, "STATUS": 1, "ALARM": 1},
        "initial": {"CNT_03": 1500, "CNT_05": 300, "CNT_10": 30},
        "bounds": {"CNT_03": (0, 3520), "CNT_05": (0, 832), "CNT_10": (0, 83)},
        "delta":  {"CNT_03": 200, "CNT_05": 50, "CNT_10": 10},
    },
    "TEMP": {
        # 클린룸 온도: 22 ± 1°C (반도체 기준)
        "fast_tags": ["STATUS", "ALARM"],
        "slow_tags": ["VAL", "DELTA", "SETPOINT"],
        "scale": {"VAL": 100, "DELTA": 100, "SETPOINT": 100, "STATUS": 1, "ALARM": 1},
        "initial": {"VAL": 22.0, "DELTA": 0.0, "SETPOINT": 22.0},
        "bounds": {"VAL": (21.0, 23.0), "DELTA": (-1.0, 1.0), "SETPOINT": (22.0, 22.0)},
        "delta":  {"VAL": 0.1, "DELTA": 0.05, "SETPOINT": 0},  # SETPOINT 거의 안 변함
    },
    "HUM": {
        # 클린룸 습도: 45 ± 5 %RH
        "fast_tags": ["STATUS", "ALARM"],
        "slow_tags": ["VAL", "DELTA", "SETPOINT"],
        "scale": {"VAL": 100, "DELTA": 100, "SETPOINT": 100, "STATUS": 1, "ALARM": 1},
        "initial": {"VAL": 45.0, "DELTA": 0.0, "SETPOINT": 45.0},
        "bounds": {"VAL": (42.0, 48.0), "DELTA": (-3.0, 3.0), "SETPOINT": (45.0, 45.0)},
        "delta":  {"VAL": 0.3, "DELTA": 0.1, "SETPOINT": 0},
    },
    "AMC": {
        # AMC (분자 오염): ppb 단위, 매우 작은 값
        "fast_tags": ["STATUS", "ALARM"],
        "slow_tags": ["ACID", "BASE", "COND"],
        "scale": {"ACID": 1000, "BASE": 1000, "COND": 1000, "STATUS": 1, "ALARM": 1},
        "initial": {"ACID": 0.3, "BASE": 0.05, "COND": 0.8},
        "bounds": {"ACID": (0, 1), "BASE": (0, 0.1), "COND": (0, 2)},
        "delta":  {"ACID": 0.05, "BASE": 0.005, "COND": 0.1},
    },
    "VIB": {
        # 진동: μm/s, Hz — 4태그 (X·Y·Z·주파수)
        # ★ 빠른 변화가 필요하므로 fast_tags에 진동 측정값 포함
        "fast_tags": ["VEL_X", "VEL_Y", "VEL_Z", "FREQ", "STATUS", "ALARM"],
        "slow_tags": [],
        "scale": {"VEL_X": 10, "VEL_Y": 10, "VEL_Z": 10, "FREQ": 10, "STATUS": 1, "ALARM": 1},
        "initial": {"VEL_X": 15.0, "VEL_Y": 15.0, "VEL_Z": 15.0, "FREQ": 30.0},
        "bounds": {"VEL_X": (0, 50), "VEL_Y": (0, 50), "VEL_Z": (0, 50), "FREQ": (0, 50)},
        "delta":  {"VEL_X": 3, "VEL_Y": 3, "VEL_Z": 3, "FREQ": 1},
    },
    "ESD": {
        # ESD: 정전기 전압·전류·접지저항
        "fast_tags": ["STATUS", "ALARM"],
        "slow_tags": ["VOLT", "CURR", "RESIST"],
        "scale": {"VOLT": 10, "CURR": 100, "RESIST": 100, "STATUS": 1, "ALARM": 1},
        "initial": {"VOLT": 0.0, "CURR": 0.2, "RESIST": 5.0},
        "bounds": {"VOLT": (-100, 100), "CURR": (0, 1), "RESIST": (0.1, 10)},
        "delta":  {"VOLT": 5, "CURR": 0.05, "RESIST": 0.5},
    },
}

# 구역 코드 (3개소)
ZONE_INDICES = ["01", "02", "03"]   # FRONT / BACK / EQP

# 센서 ID 순서 (레지스터 배치 결정) — PART → TEMP → HUM → AMC → VIB → ESD
SENSOR_ORDER = ["PART", "TEMP", "HUM", "AMC", "VIB", "ESD"]
REG_PER_SENSOR = 10                  # 각 센서 10 레지스터 (예비 포함)


# ============================================================
# 센서 상태 초기화
# ============================================================
def initial_state(sensor_type):
    """센서 타입에 따른 초기 상태 dict 생성"""
    spec = SENSOR_SPECS[sensor_type]
    state = {"STATUS": 1, "ALARM": 0}
    state.update(spec["initial"])
    return state


# 18센서 × 5~6태그 = 93태그 전체 상태
# 구조: SENSORS[sensor_id] = {태그: 값}
SENSORS = {}
for stype in SENSOR_ORDER:
    for idx in ZONE_INDICES:
        sensor_id = f"ENV_{stype}_{idx}"
        SENSORS[sensor_id] = initial_state(stype)


# ============================================================
# 레지스터 베이스 주소 계산
# ============================================================
def base_address(sensor_id):
    """sensor_id → 레지스터 시작 주소 매핑"""
    stype = sensor_id.split("_")[1]
    idx = int(sensor_id.split("_")[2])
    type_idx = SENSOR_ORDER.index(stype)
    return (type_idx * 3 + (idx - 1)) * REG_PER_SENSOR


# ============================================================
# 갱신 함수 — 공통 (알람 천이 + 측정값 random walk)
# ============================================================
def update_alarm_state(state):
    """모든 센서 공통: 정상 ↔ 알람 천이"""
    if state["STATUS"] == 1:
        if random.random() < ALARM_RATE_PER_SEC:
            state["STATUS"] = 0
            state["ALARM"]  = 1
    elif state["STATUS"] == 0:
        if random.random() < RECOVERY_RATE_PER_SEC:
            state["STATUS"] = 1
            state["ALARM"]  = 0


def random_walk(state, spec, tags):
    """주어진 태그들에 대해 random walk 수행"""
    bounds = spec["bounds"]
    deltas = spec["delta"]
    for tag in tags:
        if tag not in deltas or deltas[tag] == 0:
            continue
        state[tag] += random.uniform(-deltas[tag], deltas[tag])
        lo, hi = bounds[tag]
        state[tag] = max(lo, min(hi, state[tag]))


def update_fast():
    """1초 루프 — 알람 천이 + VIB 측정값"""
    for sensor_id, state in SENSORS.items():
        stype = sensor_id.split("_")[1]
        spec = SENSOR_SPECS[stype]
        update_alarm_state(state)
        # VIB만 fast 측정값 갱신
        if stype == "VIB" and state["STATUS"] == 1:
            random_walk(state, spec, ["VEL_X", "VEL_Y", "VEL_Z", "FREQ"])


def update_slow():
    """5초 루프 — TEMP, HUM, AMC, ESD 측정값"""
    for sensor_id, state in SENSORS.items():
        stype = sensor_id.split("_")[1]
        if stype in ("PART", "VIB"):
            continue  # PARTICLE은 30초, VIB는 fast에서 처리
        if state["STATUS"] != 1:
            continue  # 알람 중엔 측정값 정지
        spec = SENSOR_SPECS[stype]
        random_walk(state, spec, spec["slow_tags"])


def update_particle():
    """30초 루프 — PARTICLE 카운트만"""
    for sensor_id, state in SENSORS.items():
        stype = sensor_id.split("_")[1]
        if stype != "PART":
            continue
        if state["STATUS"] != 1:
            continue
        spec = SENSOR_SPECS["PART"]
        random_walk(state, spec, spec["slow_tags"])


# ============================================================
# Modbus 슬레이브 — 환경 18센서
# ============================================================
#
# 레지스터 매핑 (Holding Register, 함수코드 3)
# ──────────────────────────────────────────────
# 타입별 베이스:
#   PART_01: HR   0~9     PART_02: HR  10~19   PART_03: HR  20~29
#   TEMP_01: HR  30~39    TEMP_02: HR  40~49   TEMP_03: HR  50~59
#   HUM_01:  HR  60~69    HUM_02:  HR  70~79   HUM_03:  HR  80~89
#   AMC_01:  HR  90~99    AMC_02:  HR 100~109  AMC_03:  HR 110~119
#   VIB_01:  HR 120~129   VIB_02:  HR 130~139  VIB_03:  HR 140~149
#   ESD_01:  HR 150~159   ESD_02:  HR 160~169  ESD_03:  HR 170~179
#
# 각 센서 내부 오프셋 (PART 예시):
#   +0  CNT_03  × 1     30s
#   +1  CNT_05  × 1     30s
#   +2  CNT_10  × 1     30s
#   +3  (예비 — 측정값 4번째)
#   +4  STATUS  × 1     1s
#   +5  ALARM   × 1     1s
#   +6~+9  예비
#
# Node-RED modbus-read 노드 설정:
#   [Group A — 1초]:  FC=3, Address=0,   Quantity=180,  Poll=1000ms
#                     ★ 단순화: 한번에 전체 폴링 후 Function 노드로 분배
#   또는 그룹별로:
#   [Group B — 5초]:  TEMP/HUM/AMC/ESD 영역만 분리 폴링
#   [Group C — 30초]: PART 영역만 분리 폴링
#
# ──────────────────────────────────────────────


class ModbusSimulator:
    def __init__(self):
        # 200 레지스터 할당 (18센서 × 10 = 180 + 여유 20)
        self.slave = ModbusSlaveContext(
            hr=ModbusSequentialDataBlock(0, [0] * 200),
            zero_mode=True,
        )
        self.context = ModbusServerContext(slaves=self.slave, single=True)

    def _write_register(self, addr, value, scale):
        """Float 값을 Int16으로 변환하여 레지스터에 기록"""
        v = int(value * scale)
        # 음수 처리: signed Int16 → 2's complement
        if v < 0:
            v = (v + 0x10000) & 0xFFFF
        else:
            v = v & 0xFFFF
        self.slave.setValues(3, addr, [v])

    def _layout_offsets(self, stype):
        """센서 타입의 태그 → 레지스터 오프셋 매핑"""
        spec = SENSOR_SPECS[stype]
        offsets = {}

        if stype == "VIB":
            # VIB는 측정값 4개 + STATUS/ALARM (모두 fast)
            for i, tag in enumerate(["VEL_X", "VEL_Y", "VEL_Z", "FREQ"]):
                offsets[tag] = i
            offsets["STATUS"] = 4
            offsets["ALARM"] = 5
        else:
            # 나머지: 측정값 3개 + 예비1 + STATUS + ALARM
            for i, tag in enumerate(spec["slow_tags"]):
                offsets[tag] = i
            offsets["STATUS"] = 4
            offsets["ALARM"] = 5

        return offsets

    def sync_all(self):
        """전체 18센서의 모든 태그를 레지스터에 동기화"""
        for sensor_id, state in SENSORS.items():
            stype = sensor_id.split("_")[1]
            spec = SENSOR_SPECS[stype]
            base = base_address(sensor_id)
            offsets = self._layout_offsets(stype)

            for tag, offset in offsets.items():
                scale = spec["scale"][tag]
                self._write_register(base + offset, state[tag], scale)

    async def start(self):
        await StartAsyncTcpServer(
            context=self.context,
            address=(MODBUS_HOST, MODBUS_PORT),
        )


# ============================================================
# 다중 주기 루프
# ============================================================
async def loop_fast(modbus_sim):
    """1초 루프 — STATUS, ALARM, VIB 처리 + 레지스터 동기화"""
    while True:
        update_fast()
        modbus_sim.sync_all()
        await asyncio.sleep(FAST_INTERVAL)


async def loop_slow(modbus_sim):
    """5초 루프 — TEMP, HUM, AMC, ESD"""
    while True:
        update_slow()
        modbus_sim.sync_all()
        await asyncio.sleep(SLOW_INTERVAL)


async def loop_particle(modbus_sim):
    """30초 루프 — PARTICLE"""
    while True:
        update_particle()
        modbus_sim.sync_all()
        await asyncio.sleep(PARTICLE_INTERVAL)


async def loop_print():
    """30초 루프 — 콘솔 상태 요약"""
    tick = 0
    while True:
        await asyncio.sleep(PRINT_INTERVAL)
        tick += 1
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{ts}]  Print Tick {tick}  ({tick * PRINT_INTERVAL}s 경과)")

        # 파티클
        print("  📡 PARTICLE (ISO 14644-1 Class 5 기준)")
        for idx in ZONE_INDICES:
            s = SENSORS[f"ENV_PART_{idx}"]
            mark = "🟢" if s["STATUS"] == 1 else "🔴"
            print(f"    {mark} ENV_PART_{idx}  "
                  f"0.3μm={s['CNT_03']:5.0f}  "
                  f"0.5μm={s['CNT_05']:4.0f}  "
                  f"1.0μm={s['CNT_10']:3.0f} 개/m³")

        # 온습도
        print("  📡 TEMP / HUM (클린룸 22±1°C / 45±5%RH)")
        for idx in ZONE_INDICES:
            t = SENSORS[f"ENV_TEMP_{idx}"]
            h = SENSORS[f"ENV_HUM_{idx}"]
            tm = "🟢" if t["STATUS"] == 1 else "🔴"
            hm = "🟢" if h["STATUS"] == 1 else "🔴"
            print(f"    {tm} TEMP_{idx} {t['VAL']:5.2f}°C  "
                  f"Δ={t['DELTA']:+5.2f}     "
                  f"{hm} HUM_{idx} {h['VAL']:5.2f}%RH  Δ={h['DELTA']:+5.2f}")

        # AMC + VIB + ESD
        print("  📡 AMC (ppb) / VIB (μm/s) / ESD (V·μA·MΩ)")
        for idx in ZONE_INDICES:
            a = SENSORS[f"ENV_AMC_{idx}"]
            v = SENSORS[f"ENV_VIB_{idx}"]
            e = SENSORS[f"ENV_ESD_{idx}"]
            am = "🟢" if a["STATUS"] == 1 else "🔴"
            vm = "🟢" if v["STATUS"] == 1 else "🔴"
            em = "🟢" if e["STATUS"] == 1 else "🔴"
            print(f"    {am} AMC_{idx} ACID={a['ACID']:4.2f} BASE={a['BASE']:5.3f} COND={a['COND']:4.2f}  "
                  f"{vm} VIB_{idx} X={v['VEL_X']:4.1f} Y={v['VEL_Y']:4.1f} Z={v['VEL_Z']:4.1f}  "
                  f"{em} ESD_{idx} V={e['VOLT']:+5.1f}")


async def main():
    print("=" * 72)
    print("  환경 센서 시뮬레이터 — Modbus TCP (다중 주기)")
    print("  DB하이텍 음성공장 Web SCADA / 18 환경센서")
    print("=" * 72)
    print(f"  Modbus slave : {MODBUS_HOST}:{MODBUS_PORT}")
    print(f"                  ├ PARTICLE (HR  0~29)   × 3구역")
    print(f"                  ├ TEMP     (HR 30~59)   × 3구역")
    print(f"                  ├ HUM      (HR 60~89)   × 3구역")
    print(f"                  ├ AMC      (HR 90~119)  × 3구역")
    print(f"                  ├ VIB      (HR 120~149) × 3구역")
    print(f"                  └ ESD      (HR 150~179) × 3구역")
    print(f"  Fast 루프      : {FAST_INTERVAL}초  (STATUS, ALARM, VIB)")
    print(f"  Slow 루프      : {SLOW_INTERVAL}초  (TEMP, HUM, AMC, ESD)")
    print(f"  Particle 루프  : {PARTICLE_INTERVAL}초 (PART CNT_03/05/10)")
    print(f"  알람 발생률    : {ALARM_RATE_PER_SEC*60*60:.1f}회/시간")
    print("=" * 72)

    modbus_sim = ModbusSimulator()
    modbus_sim.sync_all()   # 초기 동기화

    try:
        await asyncio.gather(
            modbus_sim.start(),
            loop_fast(modbus_sim),
            loop_slow(modbus_sim),
            loop_particle(modbus_sim),
            loop_print(),
        )
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n환경 시뮬레이터 종료\n")
        sys.exit(0)
