-- ============================================================
-- scada_db → scada 마이그레이션 (안전 버전)
-- 
-- 원칙: BE 데이터(ai_suggestions, optimization_actions, oee_metrics) 보존
--       DAS 마스터(equipments, parameters, sensors)만 scada_db 기준으로 동기화
--
-- 실행 전 확인:
--   백엔드 담당자에게 "DAS 마스터 데이터 넣는다" 공유
--
-- 실행: mysql -u root -p < migrate_seed_to_scada_v2.sql
-- ============================================================

USE scada;
SET FOREIGN_KEY_CHECKS = 0;

-- ────────────────────────────────────────────
-- 1. processes — 기존 유지 + 누락분 추가
-- ────────────────────────────────────────────
INSERT IGNORE INTO processes
SELECT * FROM scada_db.processes;

-- ────────────────────────────────────────────
-- 2. equipments — FURN 3대 유지, 나머지 15대 추가
--
--    ※ SELECT * 미사용: 아래 2-1에서 OEE 컬럼(ideal_cycle_time,
--      planned_daily_hours) 추가 후 재실행 시 컬럼 수 불일치 회피
--    ※ INSERT IGNORE + PK(equipment_id) 조합으로 멱등성 보장
-- ────────────────────────────────────────────
INSERT IGNORE INTO equipments
  (equipment_id, equipment_name, step_no, total_running_hours, unit_no)
SELECT
  equipment_id, equipment_name, step_no, total_running_hours, unit_no
FROM scada_db.equipments;

-- ────────────────────────────────────────────
-- 2-1. equipments — OEE 계산용 컬럼 추가
--     ideal_cycle_time   : 이상 사이클 시간 (초) — 성능률 계산
--     planned_daily_hours: 계획 가동 시간 (시간/일) — 가용률 계산
--
--     ※ 위 INSERT는 컬럼명을 명시하므로 컬럼 수 불일치 없음
--     ※ 멱등 실행을 위해 information_schema로 존재 여부 확인
-- ────────────────────────────────────────────
DROP PROCEDURE IF EXISTS _add_oee_cols;
DELIMITER //
CREATE PROCEDURE _add_oee_cols()
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'scada' AND TABLE_NAME = 'equipments'
      AND COLUMN_NAME = 'ideal_cycle_time'
  ) THEN
    ALTER TABLE equipments
      ADD COLUMN ideal_cycle_time FLOAT DEFAULT NULL
      COMMENT 'OEE 이상 사이클 시간 (초)';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'scada' AND TABLE_NAME = 'equipments'
      AND COLUMN_NAME = 'planned_daily_hours'
  ) THEN
    ALTER TABLE equipments
      ADD COLUMN planned_daily_hours FLOAT DEFAULT NULL
      COMMENT 'OEE 계획 가동 시간 (시간/일)';
  END IF;
END //
DELIMITER ;

CALL _add_oee_cols();
DROP PROCEDURE _add_oee_cols;

-- 설비 그룹별 OEE 기준값 설정 (이상 사이클 / 계획 가동 8시간/일)
--   FURN(산화) 120s, PECVD(박막증착) 90s, ETCH(식각) 75s,
--   TRACK(포토) 60s, SPTT(배선) 120s, PROBE(검사) 30s
UPDATE equipments SET ideal_cycle_time = 120, planned_daily_hours = 8.0
 WHERE equipment_id IN ('FURN_01',  'FURN_02',  'FURN_03');

UPDATE equipments SET ideal_cycle_time =  90, planned_daily_hours = 8.0
 WHERE equipment_id IN ('PECVD_01', 'PECVD_02', 'PECVD_03');

UPDATE equipments SET ideal_cycle_time =  75, planned_daily_hours = 8.0
 WHERE equipment_id IN ('ETCH_01',  'ETCH_02',  'ETCH_03');

UPDATE equipments SET ideal_cycle_time =  60, planned_daily_hours = 8.0
 WHERE equipment_id IN ('TRACK_01', 'TRACK_02', 'TRACK_03');

UPDATE equipments SET ideal_cycle_time = 120, planned_daily_hours = 8.0
 WHERE equipment_id IN ('SPTT_01',  'SPTT_02',  'SPTT_03');

UPDATE equipments SET ideal_cycle_time =  30, planned_daily_hours = 8.0
 WHERE equipment_id IN ('PROBE_01', 'PROBE_02', 'PROBE_03');

-- ────────────────────────────────────────────
-- 3. equipment_parameters — 핵심 교체
--    기존 9개 (PRESSURE 등 불일치) 삭제 → scada_db 198개로 교체
--    ⚠️ 기존 equipment_measurements 9개도 삭제 (param_id 꼬임 방지)
-- ────────────────────────────────────────────
DELETE FROM equipment_measurements;  -- 테스트 데이터 9건
DELETE FROM equipment_parameters;    -- 불일치 tag_code 9건

ALTER TABLE equipment_parameters AUTO_INCREMENT = 1;

INSERT INTO equipment_parameters
  (equipment_id, tag_code, tag_name, unit,
   normal_min, normal_max, abnormal_condition,
   collection_period, data_type, param_category, is_controllable)
SELECT
  equipment_id, tag_code, tag_name, unit,
  normal_min, normal_max, abnormal_condition,
  collection_period, data_type, param_category, is_controllable
FROM scada_db.equipment_parameters
ORDER BY param_id;

-- ────────────────────────────────────────────
-- 3-1. OEE 계산용 태그 일괄 등록 (18대 × 4태그 = 72 row)
--     PROD_COUNT, NG_COUNT, OK_COUNT, IDEAL_CYCLE_TIME
--
--     ※ 기존 scada_db.equipment_parameters에 일부 등록되어 있을 수 있으나
--       INSERT IGNORE + UNIQUE(tag_code) 조합으로 중복 등록 회피
--     ※ FURN(3) + PECVD(3) + ETCH(3) + TRACK(3) + SPTT(3) + PROBE(3) = 18대
-- ────────────────────────────────────────────
INSERT IGNORE INTO equipment_parameters
  (equipment_id, tag_code, tag_name, unit,
   collection_period, data_type, param_category, is_controllable)
SELECT
  e.equipment_id,
  CONCAT(e.equipment_id, '_', t.tag_suffix) AS tag_code,
  t.tag_name,
  t.unit,
  '5s', 'INT', t.category, FALSE
FROM (
  SELECT 'FURN_01' AS equipment_id UNION ALL
  SELECT 'FURN_02'  UNION ALL SELECT 'FURN_03'  UNION ALL
  SELECT 'PECVD_01' UNION ALL SELECT 'PECVD_02' UNION ALL SELECT 'PECVD_03' UNION ALL
  SELECT 'ETCH_01'  UNION ALL SELECT 'ETCH_02'  UNION ALL SELECT 'ETCH_03'  UNION ALL
  SELECT 'TRACK_01' UNION ALL SELECT 'TRACK_02' UNION ALL SELECT 'TRACK_03' UNION ALL
  SELECT 'SPTT_01'  UNION ALL SELECT 'SPTT_02'  UNION ALL SELECT 'SPTT_03'  UNION ALL
  SELECT 'PROBE_01' UNION ALL SELECT 'PROBE_02' UNION ALL SELECT 'PROBE_03'
) e
CROSS JOIN (
  SELECT 'PROD_COUNT'       AS tag_suffix, '생산 누계'      AS tag_name, 'count' AS unit, 'PROD'     AS category UNION ALL
  SELECT 'NG_COUNT',                       '불량 누계',                  'count',         'PROD'              UNION ALL
  SELECT 'OK_COUNT',                       '양품 누계',                  'count',         'PROD'              UNION ALL
  SELECT 'IDEAL_CYCLE_TIME',               '이상 사이클타임',            's',             'SETPOINT'
) t;

-- ────────────────────────────────────────────
-- 4. environment_sensors — 신규 삽입 (기존 0건)
-- ────────────────────────────────────────────
INSERT IGNORE INTO environment_sensors
SELECT * FROM scada_db.environment_sensors;

-- ────────────────────────────────────────────
-- 5. environment_parameters — 신규 삽입 (기존 0건)
-- ────────────────────────────────────────────
ALTER TABLE environment_parameters AUTO_INCREMENT = 1;

INSERT INTO environment_parameters
  (sensor_id, tag_code, tag_name, unit,
   normal_min, normal_max, abnormal_condition,
   collection_period, data_type, param_category)
SELECT
  sensor_id, tag_code, tag_name, unit,
  normal_min, normal_max, abnormal_condition,
  collection_period, data_type, param_category
FROM scada_db.environment_parameters
ORDER BY param_id;

SET FOREIGN_KEY_CHECKS = 1;

-- ────────────────────────────────────────────
-- 6. 검증
-- ────────────────────────────────────────────
SELECT '=== 마이그레이션 결과 ===' AS '';

SELECT 'equipments' AS tbl, COUNT(*) AS cnt FROM equipments
UNION ALL SELECT 'equip_params', COUNT(*) FROM equipment_parameters
UNION ALL SELECT 'env_sensors', COUNT(*) FROM environment_sensors
UNION ALL SELECT 'env_params', COUNT(*) FROM environment_parameters;

-- BE 데이터 보존 확인
SELECT '=== BE 데이터 보존 확인 ===' AS '';

SELECT 'ai_suggestions' AS tbl, COUNT(*) AS cnt FROM ai_suggestions
UNION ALL SELECT 'optimization_actions', COUNT(*) FROM optimization_actions
UNION ALL SELECT 'oee_metrics', COUNT(*) FROM oee_metrics;

-- tag_code 샘플 (PRESSURE → PRESS 교체 확인)
SELECT '=== FURN_01 tag_code 확인 ===' AS '';
SELECT tag_code FROM equipment_parameters WHERE tag_code LIKE 'FURN_01%';

-- OEE 컬럼 확인 (18대 전체 ideal_cycle_time, planned_daily_hours)
SELECT '=== 설비 OEE 기준값 확인 (18대) ===' AS '';
SELECT equipment_id, ideal_cycle_time, planned_daily_hours
  FROM equipments
 WHERE equipment_id REGEXP '^(FURN|PECVD|ETCH|TRACK|SPTT|PROBE)_0[123]$'
 ORDER BY equipment_id;

-- OEE 태그 등록 확인 (18대 × 4태그 = 72건 목표)
SELECT '=== OEE 태그 등록 수 확인 (설비별) ===' AS '';
SELECT equipment_id, COUNT(*) AS oee_tag_cnt
  FROM equipment_parameters
 WHERE tag_code REGEXP '_(PROD_COUNT|NG_COUNT|OK_COUNT|IDEAL_CYCLE_TIME)$'
 GROUP BY equipment_id
 ORDER BY equipment_id;
