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
-- ────────────────────────────────────────────
INSERT IGNORE INTO equipments
SELECT * FROM scada_db.equipments;

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
