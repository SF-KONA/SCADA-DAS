# SCADA-DAS

> 2조 SFaaS 심화 프로젝트 — 데이터 수집 서버 (Data Acquisition System)

설비 시뮬레이터(Python)로 반도체 공정 데이터를 생성하고, Node-RED DAS가 4종 산업용 프로토콜로 수집하여 MySQL에 저장합니다.

---

## 시스템 구성

```
┌──────────────────────────────────────────────────────────────┐
│  Python 시뮬레이터 (integrated_sim.py)                        │
│                                                              │
│  Modbus :5020  ─── FURN_01~03 (산화공정)                      │
│  OPC UA :4840  ─── PECVD_01~03 (박막증착) + ETCH_01~03 (식각)  │
│  MQTT   :1883  ─── TRACK_01~03 / SPTT_01~03 / PROBE_01~03   │
│  Modbus :5021  ─── 환경 BMS 18센서 (6타입 × 3구역)             │
└──────────────────────┬───────────────────────────────────────┘
                       │ 4종 프로토콜
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  Node-RED DAS (:1880)                                        │
│                                                              │
│  ├ tag_code → param_id 캐시 (INIT 시 DB 조회)                 │
│  ├ equipment_measurements INSERT (설비 측정값)                 │
│  ├ environment_measurements INSERT (환경 측정값)               │
│  ├ 임계값 비교 → alarms INSERT (엣지 트리거)                    │
│  └ 상태 변경 감지 → status_change_logs INSERT                  │
└──────────────────────┬───────────────────────────────────────┘
                       │ MySQL
                       ▼
┌──────────────────────────────────────────────────────────────┐
│  scada DB (:3306)                                            │
│                                                              │
│  ├ equipments (18대)          ├ environment_sensors (18개)    │
│  ├ equipment_parameters (198) ├ environment_parameters (93)  │
│  ├ equipment_measurements     ├ environment_measurements     │
│  ├ alarms                     └ status_change_logs           │
│  └ oee_metrics                                               │
└──────────────────────┬───────────────────────────────────────┘
                       │ REST API
                       ▼
              Spring Boot → Vue.js (별도 repo)
```

## 설비 18대 + 환경 18센서

| 프로토콜 | 설비 | 공정 | 수집 주기 |
|---|---|---|---|
| Modbus TCP :5020 | FURN_01~03 | 산화 | 1s (상태) / 5s (공정) |
| OPC UA :4840 | PECVD_01~03 | 박막증착 (CVD) | 1s / 5s |
| OPC UA :4840 | ETCH_01~03 | 식각 | 1s / 5s |
| MQTT :1883 | TRACK_01~03 | 포토 | 1s |
| MQTT :1883 | SPTT_01~03 | 금속배선 | 1s |
| MQTT :1883 | PROBE_01~03 | EDS 검사 | 1s |
| Modbus TCP :5021 | ENV 18센서 | 환경 BMS | 1s / 5s / 30s |

---

## 실행 방법

### 사전 요구

```bash
pip install pymodbus asyncua paho-mqtt
brew install mosquitto    # Mac
```

Node-RED 팔레트:
```bash
cd ~/.node-red
npm install node-red-node-mysql node-red-contrib-modbus node-red-contrib-opcua
```

### DB 초기 데이터

최초 1회, 마스터 데이터(설비 정의, 태그 정의, 환경 센서 정의)를 삽입해야 합니다:

```bash
mysql -u root -p < sql/migrate_seed_to_scada_v2.sql
```

### 실행 순서

```bash
# 1. Mosquitto (MQTT 브로커)
mosquitto

# 2. 시뮬레이터 (터미널 새로 열고)
cd simulator
python integrated_sim.py

# 3. Node-RED (터미널 새로 열고)
node-red

# 4. 브라우저에서 확인
open http://127.0.0.1:1880
```

### 데이터 확인

```sql
SELECT 'equip' AS src, COUNT(*) AS cnt FROM scada.equipment_measurements
UNION ALL SELECT 'env', COUNT(*) FROM scada.environment_measurements
UNION ALL SELECT 'alarm', COUNT(*) FROM scada.alarms
UNION ALL SELECT 'status', COUNT(*) FROM scada.status_change_logs;
```

---

## 폴더 구조

```
SCADA-DAS/
├── simulator/
│   ├── integrated_sim.py      ← 통합 시뮬레이터 (시연용)
│   ├── equip_sim_v01.py       ← Modbus+OPC UA 초기 버전
│   ├── equip_sim_v02.py       ← Modbus+OPC UA 다중주기 버전
│   ├── mqtt_sim_v01.py        ← MQTT (TRACK/SPTT/PROBE)
│   ├── env_sim_v01.py         ← 환경 BMS Modbus
│   └── opcua_dump.py          ← OPC UA NodeID 확인 유틸
├── nodered/
│   ├── flows.json             ← Node-RED 플로우
│   └── package.json           ← 팔레트 의존성
├── sql/
│   └── migrate_seed_to_scada_v2.sql  ← DB 마스터 데이터
└── docs/
```

---

## 관련 저장소

| 저장소 | 설명 |
|---|---|
| [SCADA-DAS](https://github.com/SF-KONA/SCADA-DAS) | 데이터 수집 (이 저장소) |
| [SCADA-backend](https://github.com/SF-KONA/SCADA-backend) | Spring Boot API 서버 |
| [SCADA-frontend](https://github.com/SF-KONA/SCADA-frontend) | Vue.js 모니터링 UI |
