-- ============================================================
-- master_seed.sql — 마스터 데이터 + 시연용 히스토리 시드
-- 2조 SFaaS / SCADA-DAS / 김완택
--
-- 멱등성 보장:
--   - 수집 데이터(measurements/alarms/oee/audit/status_log)는 DELETE 후 재생성
--   - 마스터 데이터는 INSERT IGNORE 또는 NOT EXISTS로 중복 SKIP
--   - equipment_measurements는 포함 X (시뮬레이터가 채움)
--
-- 실행: mysql -u root -p < sql/master_seed.sql
-- ============================================================

USE scada;
SET FOREIGN_KEY_CHECKS = 0;
SET @TODAY := CURDATE();

-- ============================================================
-- 1. 수집 데이터 초기화 (마스터 보존)
-- ============================================================
DELETE FROM equipment_measurements;
DELETE FROM environment_measurements;
DELETE FROM status_change_logs;
DELETE FROM alarms;
DELETE FROM ai_suggestions;
DELETE FROM audit_logs;
DELETE FROM oee_metrics;

-- ============================================================
-- 2. 마스터 데이터
-- ============================================================

-- ────────────────────────────────────────────
-- 2.1 processes (공정 8단계)
-- ────────────────────────────────────────────
INSERT IGNORE INTO processes
  (step_no, equipment_code, equipment_type,           has_equipment, process_name,  sort_order) VALUES
  ('01',   NULL,    NULL,                             0, 'Wafer 입고',  1),
  ('02',   'FURN',  'Vertical Diffusion Furnace',     1, '산화 공정',   2),
  ('03',   'TRACK', 'Track (Coater/Developer)',       1, '포토 공정',   3),
  ('04',   'ETCH',  'Dry Etcher (ICP)',               1, '식각 공정',   4),
  ('05',   'PECVD', 'PECVD (Plasma Enhanced CVD)',    1, '박막증착',    5),
  ('06',   'SPTT',  'PVD Sputter',                    1, '금속배선',    6),
  ('07',   'PROBE', 'Probe Station',                  1, '검사',        7),
  ('08',   NULL,    NULL,                             0, '출하/포장',   8);

-- ────────────────────────────────────────────
-- 2.2 equipments OEE 컬럼 보장 (멱등 ALTER)
-- ────────────────────────────────────────────
DROP PROCEDURE IF EXISTS _add_oee_cols;
DELIMITER //
CREATE PROCEDURE _add_oee_cols()
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                  WHERE TABLE_SCHEMA='scada' AND TABLE_NAME='equipments'
                    AND COLUMN_NAME='ideal_cycle_time') THEN
    ALTER TABLE equipments ADD COLUMN ideal_cycle_time FLOAT DEFAULT NULL
      COMMENT 'OEE 이상 사이클 시간 (초)';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                  WHERE TABLE_SCHEMA='scada' AND TABLE_NAME='equipments'
                    AND COLUMN_NAME='planned_daily_hours') THEN
    ALTER TABLE equipments ADD COLUMN planned_daily_hours FLOAT DEFAULT NULL
      COMMENT 'OEE 계획 가동 시간 (시간/일)';
  END IF;
END //
DELIMITER ;
CALL _add_oee_cols();
DROP PROCEDURE _add_oee_cols;

-- ────────────────────────────────────────────
-- 2.3 equipments (18대) + OEE 기준값 + total_running_hours 다양화
--   ideal_cycle_time: FURN=120 / PECVD=90 / ETCH=75 /
--                     TRACK=60 / SPTT=120 / PROBE=30
--   planned_daily_hours: 모두 8시간/일
--   total_running_hours: 200~800 분포 (분석 가능하도록 의도적 분산)
-- ────────────────────────────────────────────
INSERT IGNORE INTO equipments
  (equipment_id, equipment_name,                        step_no, total_running_hours, unit_no, ideal_cycle_time, planned_daily_hours) VALUES
  ('FURN_01',  '확산 산화로 #1',                          '02', 720, 1, 120, 8.0),
  ('FURN_02',  '확산 산화로 #2',                          '02', 680, 2, 120, 8.0),
  ('FURN_03',  '확산 산화로 #3',                          '02', 650, 3, 120, 8.0),
  ('TRACK_01', '포토 트랙 #1 (Coater/Developer)',         '03', 380, 1,  60, 8.0),
  ('TRACK_02', '포토 트랙 #2 (Coater/Developer)',         '03', 410, 2,  60, 8.0),
  ('TRACK_03', '포토 트랙 #3 (Coater/Developer)',         '03', 360, 3,  60, 8.0),
  ('ETCH_01',  '식각 장비 #1 (Dry Etcher / ICP)',         '04', 460, 1,  75, 8.0),
  ('ETCH_02',  '식각 장비 #2 (Dry Etcher / ICP)',         '04', 480, 2,  75, 8.0),
  ('ETCH_03',  '식각 장비 #3 (Dry Etcher / ICP)',         '04', 440, 3,  75, 8.0),
  ('PECVD_01', 'PECVD #1 (Plasma Enhanced CVD)',         '05', 540, 1,  90, 8.0),
  ('PECVD_02', 'PECVD #2 (Plasma Enhanced CVD)',         '05', 580, 2,  90, 8.0),
  ('PECVD_03', 'PECVD #3 (Plasma Enhanced CVD)',         '05', 520, 3,  90, 8.0),
  ('SPTT_01',  'PVD 스퍼터 #1',                           '06', 320, 1, 120, 8.0),
  ('SPTT_02',  'PVD 스퍼터 #2',                           '06', 340, 2, 120, 8.0),
  ('SPTT_03',  'PVD 스퍼터 #3',                           '06', 290, 3, 120, 8.0),
  ('PROBE_01', '프로브 스테이션 #1',                       '07', 250, 1,  30, 8.0),
  ('PROBE_02', '프로브 스테이션 #2',                       '07', 220, 2,  30, 8.0),
  ('PROBE_03', '프로브 스테이션 #3',                       '07', 280, 3,  30, 8.0);

-- 기존 row가 있어도 OEE/total_running_hours 값 보정 (멱등)
UPDATE equipments SET total_running_hours = 720, ideal_cycle_time = 120, planned_daily_hours = 8.0 WHERE equipment_id = 'FURN_01';
UPDATE equipments SET total_running_hours = 680, ideal_cycle_time = 120, planned_daily_hours = 8.0 WHERE equipment_id = 'FURN_02';
UPDATE equipments SET total_running_hours = 650, ideal_cycle_time = 120, planned_daily_hours = 8.0 WHERE equipment_id = 'FURN_03';
UPDATE equipments SET total_running_hours = 380, ideal_cycle_time =  60, planned_daily_hours = 8.0 WHERE equipment_id = 'TRACK_01';
UPDATE equipments SET total_running_hours = 410, ideal_cycle_time =  60, planned_daily_hours = 8.0 WHERE equipment_id = 'TRACK_02';
UPDATE equipments SET total_running_hours = 360, ideal_cycle_time =  60, planned_daily_hours = 8.0 WHERE equipment_id = 'TRACK_03';
UPDATE equipments SET total_running_hours = 460, ideal_cycle_time =  75, planned_daily_hours = 8.0 WHERE equipment_id = 'ETCH_01';
UPDATE equipments SET total_running_hours = 480, ideal_cycle_time =  75, planned_daily_hours = 8.0 WHERE equipment_id = 'ETCH_02';
UPDATE equipments SET total_running_hours = 440, ideal_cycle_time =  75, planned_daily_hours = 8.0 WHERE equipment_id = 'ETCH_03';
UPDATE equipments SET total_running_hours = 540, ideal_cycle_time =  90, planned_daily_hours = 8.0 WHERE equipment_id = 'PECVD_01';
UPDATE equipments SET total_running_hours = 580, ideal_cycle_time =  90, planned_daily_hours = 8.0 WHERE equipment_id = 'PECVD_02';
UPDATE equipments SET total_running_hours = 520, ideal_cycle_time =  90, planned_daily_hours = 8.0 WHERE equipment_id = 'PECVD_03';
UPDATE equipments SET total_running_hours = 320, ideal_cycle_time = 120, planned_daily_hours = 8.0 WHERE equipment_id = 'SPTT_01';
UPDATE equipments SET total_running_hours = 340, ideal_cycle_time = 120, planned_daily_hours = 8.0 WHERE equipment_id = 'SPTT_02';
UPDATE equipments SET total_running_hours = 290, ideal_cycle_time = 120, planned_daily_hours = 8.0 WHERE equipment_id = 'SPTT_03';
UPDATE equipments SET total_running_hours = 250, ideal_cycle_time =  30, planned_daily_hours = 8.0 WHERE equipment_id = 'PROBE_01';
UPDATE equipments SET total_running_hours = 220, ideal_cycle_time =  30, planned_daily_hours = 8.0 WHERE equipment_id = 'PROBE_02';
UPDATE equipments SET total_running_hours = 280, ideal_cycle_time =  30, planned_daily_hours = 8.0 WHERE equipment_id = 'PROBE_03';

-- ────────────────────────────────────────────
-- 2.4 equipment_parameters — OEE 4태그 (PROD/NG/OK/IDEAL_CYCLE_TIME)
--   ※ 기존 PROCESS/STATUS 태그는 scada_db.equipment_parameters에서 별도 마이그레이션
--   ※ tag_code UNIQUE 제약 없음 → NOT EXISTS로 중복 회피 (멱등)
--   ※ param_category enum=('OEE','PROCESS','STATUS') → OEE 카테고리 사용
-- ────────────────────────────────────────────
INSERT INTO equipment_parameters
  (equipment_id, tag_code, tag_name, unit, collection_period, data_type, param_category, is_controllable)
SELECT
  e.equipment_id,
  CONCAT(e.equipment_id, '_', t.tag_suffix),
  t.tag_name, t.unit, '5s', 'INT', 'OEE', FALSE
FROM (
  SELECT 'FURN_01'  AS equipment_id UNION ALL SELECT 'FURN_02'  UNION ALL SELECT 'FURN_03'  UNION ALL
  SELECT 'PECVD_01' UNION ALL SELECT 'PECVD_02' UNION ALL SELECT 'PECVD_03' UNION ALL
  SELECT 'ETCH_01'  UNION ALL SELECT 'ETCH_02'  UNION ALL SELECT 'ETCH_03'  UNION ALL
  SELECT 'TRACK_01' UNION ALL SELECT 'TRACK_02' UNION ALL SELECT 'TRACK_03' UNION ALL
  SELECT 'SPTT_01'  UNION ALL SELECT 'SPTT_02'  UNION ALL SELECT 'SPTT_03'  UNION ALL
  SELECT 'PROBE_01' UNION ALL SELECT 'PROBE_02' UNION ALL SELECT 'PROBE_03'
) e
CROSS JOIN (
  SELECT 'PROD_COUNT'       AS tag_suffix, '생산 누계'      AS tag_name, 'count' AS unit UNION ALL
  SELECT 'NG_COUNT',                       '불량 누계',                  'count'         UNION ALL
  SELECT 'OK_COUNT',                       '양품 누계',                  'count'         UNION ALL
  SELECT 'IDEAL_CYCLE_TIME',               '이상 사이클타임',            's'
) t
WHERE NOT EXISTS (
  SELECT 1 FROM equipment_parameters dst
   WHERE dst.equipment_id = e.equipment_id
     AND dst.tag_code     = CONCAT(e.equipment_id, '_', t.tag_suffix)
);

-- 기존 row의 param_category 보정 (NOT EXISTS로 SKIP된 기존 OEE 4태그가
--   param_category 비어있을 수 있음 → 'OEE'로 강제 설정)
UPDATE equipment_parameters
   SET param_category = 'OEE'
 WHERE tag_code REGEXP '_(PROD_COUNT|NG_COUNT|OK_COUNT|IDEAL_CYCLE_TIME)$'
   AND (param_category IS NULL OR param_category != 'OEE');

-- ============================================================
-- 3. environment_sensors (6타입 × 3구역 = 18센서)
--   sensor_id 끝 2자리: 01→FRONT, 02→BACK, 03→EQP
--   sensor_type enum: PARTICLE, TEMP, HUMIDITY, AMC, VIBRATION, ESD
-- ============================================================
INSERT IGNORE INTO environment_sensors
  (sensor_id,        sensor_name,         sensor_type,  zone_code) VALUES
  ('ENV_PART_01', '파티클 카운터 (FRONT)', 'PARTICLE',  'FRONT'),
  ('ENV_PART_02', '파티클 카운터 (BACK)',  'PARTICLE',  'BACK'),
  ('ENV_PART_03', '파티클 카운터 (EQP)',   'PARTICLE',  'EQP'),
  ('ENV_TEMP_01', '온도 센서 (FRONT)',     'TEMP',      'FRONT'),
  ('ENV_TEMP_02', '온도 센서 (BACK)',      'TEMP',      'BACK'),
  ('ENV_TEMP_03', '온도 센서 (EQP)',       'TEMP',      'EQP'),
  ('ENV_HUM_01',  '습도 센서 (FRONT)',     'HUMIDITY',  'FRONT'),
  ('ENV_HUM_02',  '습도 센서 (BACK)',      'HUMIDITY',  'BACK'),
  ('ENV_HUM_03',  '습도 센서 (EQP)',       'HUMIDITY',  'EQP'),
  ('ENV_AMC_01',  'AMC 센서 (FRONT)',      'AMC',       'FRONT'),
  ('ENV_AMC_02',  'AMC 센서 (BACK)',       'AMC',       'BACK'),
  ('ENV_AMC_03',  'AMC 센서 (EQP)',        'AMC',       'EQP'),
  ('ENV_VIB_01',  '진동 센서 (FRONT)',     'VIBRATION', 'FRONT'),
  ('ENV_VIB_02',  '진동 센서 (BACK)',      'VIBRATION', 'BACK'),
  ('ENV_VIB_03',  '진동 센서 (EQP)',       'VIBRATION', 'EQP'),
  ('ENV_ESD_01',  'ESD 센서 (FRONT)',      'ESD',       'FRONT'),
  ('ENV_ESD_02',  'ESD 센서 (BACK)',       'ESD',       'BACK'),
  ('ENV_ESD_03',  'ESD 센서 (EQP)',        'ESD',       'EQP');

-- 기존 row의 zone_code 보정 (INSERT IGNORE는 기존을 안 건드림)
UPDATE environment_sensors SET zone_code = 'FRONT' WHERE sensor_id LIKE '%\\_01' ESCAPE '\\';
UPDATE environment_sensors SET zone_code = 'BACK'  WHERE sensor_id LIKE '%\\_02' ESCAPE '\\';
UPDATE environment_sensors SET zone_code = 'EQP'   WHERE sensor_id LIKE '%\\_03' ESCAPE '\\';

-- 기존 row의 sensor_type 보정 (sensor_id prefix → enum 매핑)
--   enum: ('AMC','ESD','HUMIDITY','PARTICLE','TEMP','VIBRATION')
UPDATE environment_sensors SET sensor_type = 'AMC'       WHERE sensor_id LIKE 'ENV\\_AMC\\_%'  ESCAPE '\\';
UPDATE environment_sensors SET sensor_type = 'ESD'       WHERE sensor_id LIKE 'ENV\\_ESD\\_%'  ESCAPE '\\';
UPDATE environment_sensors SET sensor_type = 'HUMIDITY'  WHERE sensor_id LIKE 'ENV\\_HUM\\_%'  ESCAPE '\\';
UPDATE environment_sensors SET sensor_type = 'PARTICLE'  WHERE sensor_id LIKE 'ENV\\_PART\\_%' ESCAPE '\\';
UPDATE environment_sensors SET sensor_type = 'TEMP'      WHERE sensor_id LIKE 'ENV\\_TEMP\\_%' ESCAPE '\\';
UPDATE environment_sensors SET sensor_type = 'VIBRATION' WHERE sensor_id LIKE 'ENV\\_VIB\\_%'  ESCAPE '\\';

-- ============================================================
-- 4. environment_parameters (기존 형식 유지, 멱등)
--   ※ 신규 sensor에 대한 기본 태그 (STATUS, ALARM) 보장만 처리
--   ※ 측정 태그(CNT_03, VAL 등)는 기존 시드(279건) 그대로 보존
-- ============================================================
INSERT INTO environment_parameters
  (sensor_id, tag_code, tag_name, unit, collection_period, data_type, param_category, normal_min, normal_max, abnormal_condition)
SELECT
  s.sensor_id,
  CONCAT(s.sensor_id, '_STATUS'),
  '센서 상태', NULL, '1s', 'INT', 'STATUS', 1, 1, '0=오프라인/이상'
FROM environment_sensors s
WHERE NOT EXISTS (
  SELECT 1 FROM environment_parameters dst
   WHERE dst.tag_code = CONCAT(s.sensor_id, '_STATUS')
);

INSERT INTO environment_parameters
  (sensor_id, tag_code, tag_name, unit, collection_period, data_type, param_category, normal_min, normal_max, abnormal_condition)
SELECT
  s.sensor_id,
  CONCAT(s.sensor_id, '_ALARM'),
  '센서 알람 상태', NULL, '1s', 'BOOL', 'ALARM', 0, 0, '1=알람 발생'
FROM environment_sensors s
WHERE NOT EXISTS (
  SELECT 1 FROM environment_parameters dst
   WHERE dst.tag_code = CONCAT(s.sensor_id, '_ALARM')
);

-- ============================================================
-- 5. oee_metrics — 정상 17대 × 31일 히스토리
--   값 범위: availability 0.85~0.95, performance 0.83~0.92, quality 0.90~0.97
--   PROBE_02는 별도 처리(5.1) → 여기서는 제외
--   oee = availability × performance × quality (ROUND 4자리)
-- ============================================================
INSERT INTO oee_metrics
  (equipment_id, period_start, computed_at, availability, performance, quality, oee)
WITH RECURSIVE dates AS (
  SELECT DATE_SUB(@TODAY, INTERVAL 30 DAY) AS dt
  UNION ALL
  SELECT DATE_ADD(dt, INTERVAL 1 DAY) FROM dates WHERE dt < @TODAY
),
gen AS (
  SELECT
    e.equipment_id,
    d.dt,
    0.85 + RAND() * 0.10 AS a,   -- 0.85 ~ 0.95
    0.83 + RAND() * 0.09 AS p,   -- 0.83 ~ 0.92
    0.90 + RAND() * 0.07 AS q    -- 0.90 ~ 0.97
  FROM dates d
  CROSS JOIN equipments e
  WHERE e.equipment_id != 'PROBE_02'
)
SELECT
  equipment_id,
  TIMESTAMP(dt, '00:00:00')      AS period_start,
  TIMESTAMP(dt, '23:59:59')      AS computed_at,
  ROUND(a, 4)                    AS availability,
  ROUND(p, 4)                    AS performance,
  ROUND(q, 4)                    AS quality,
  ROUND(a * p * q, 4)            AS oee
FROM gen;

-- ============================================================
-- 5.1 oee_metrics — PROBE_02 (낮은 설비 시연용, self-contained)
--   값 범위: availability 0.78~0.85, performance 0.80~0.88, quality 0.92~0.96
--   기대 OEE 평균: 0.815 × 0.84 × 0.94 ≈ 0.64 (~0.65 목표)
--
--   ※ 이 블록만 잘라서 재실행해도 PROBE_02만 안전하게 갱신됨
--     (DELETE → INSERT 자체 완결, 다른 17대 데이터에 영향 없음)
-- ============================================================
DELETE FROM oee_metrics WHERE equipment_id = 'PROBE_02';

INSERT INTO oee_metrics
  (equipment_id, period_start, computed_at, availability, performance, quality, oee)
WITH RECURSIVE dates AS (
  SELECT DATE_SUB(CURDATE(), INTERVAL 30 DAY) AS dt
  UNION ALL
  SELECT DATE_ADD(dt, INTERVAL 1 DAY) FROM dates WHERE dt < CURDATE()
),
gen AS (
  SELECT
    dt,
    0.78 + RAND() * 0.07 AS a,   -- 0.78 ~ 0.85
    0.80 + RAND() * 0.08 AS p,   -- 0.80 ~ 0.88
    0.92 + RAND() * 0.04 AS q    -- 0.92 ~ 0.96
  FROM dates
)
SELECT
  'PROBE_02'                     AS equipment_id,
  TIMESTAMP(dt, '00:00:00')      AS period_start,
  TIMESTAMP(dt, '23:59:59')      AS computed_at,
  ROUND(a, 4)                    AS availability,
  ROUND(p, 4)                    AS performance,
  ROUND(q, 4)                    AS quality,
  ROUND(a * p * q, 4)            AS oee
FROM gen;

-- ============================================================
-- 6. alarms — 지난주(설비별 2~5건) + 지난달(설비별 3~8건) 히스토리
--   severity: ERR 30% / WARN 70% (FURN_01만 ERR 70% — 시연용)
--   status:   NEW 30% / ACK 20% / DONE 50%
--   ack/done 타임스탬프도 status에 맞춰 설정
-- ============================================================
INSERT INTO alarms
  (equipment_param_id, source_type, severity, status, message,
   triggered_value, occurred_at, last_occurred_at, occurrence_count,
   ack_at, ack_user_id, done_at, done_user_id, done_comment)
SELECT
  -- 해당 설비의 임의 STATUS 태그 param_id (없으면 첫 태그)
  (SELECT param_id FROM equipment_parameters p
    WHERE p.equipment_id = e.equipment_id
    ORDER BY (tag_code LIKE '%\\_STATUS' ESCAPE '\\') DESC, param_id
    LIMIT 1)                                                AS equipment_param_id,
  'EQP'                                                     AS source_type,
  CASE
    WHEN e.equipment_id = 'FURN_01' AND RAND() < 0.7 THEN 'ERR'
    WHEN RAND() < 0.3                                THEN 'ERR'
    ELSE 'WARN'
  END                                                       AS severity,
  CASE
    WHEN RAND() < 0.3 THEN 'NEW'
    WHEN RAND() < 0.5 THEN 'ACK'
    ELSE 'DONE'
  END                                                       AS status,
  CONCAT(e.equipment_id, ' 알람 발생 (시연 시드)')           AS message,
  ROUND(50 + RAND() * 50, 2)                                AS triggered_value,
  occurred                                                  AS occurred_at,
  occurred                                                  AS last_occurred_at,
  1                                                         AS occurrence_count,
  CASE WHEN RAND() < 0.7 THEN DATE_ADD(occurred, INTERVAL FLOOR(RAND()*120) MINUTE) END AS ack_at,
  CASE WHEN RAND() < 0.7 THEN 'admin' END                    AS ack_user_id,
  CASE WHEN RAND() < 0.5 THEN DATE_ADD(occurred, INTERVAL FLOOR(RAND()*240)+120 MINUTE) END AS done_at,
  CASE WHEN RAND() < 0.5 THEN 'admin' END                    AS done_user_id,
  CASE WHEN RAND() < 0.5 THEN '점검 완료' END                 AS done_comment
FROM equipments e
CROSS JOIN (
  -- 지난주 평균 3건 + 지난달 평균 5건 = 설비별 ~8건 (전체 ~144건)
  SELECT DATE_SUB(NOW(), INTERVAL FLOOR(RAND()*7)  DAY) AS occurred UNION ALL
  SELECT DATE_SUB(NOW(), INTERVAL FLOOR(RAND()*7)  DAY)             UNION ALL
  SELECT DATE_SUB(NOW(), INTERVAL FLOOR(RAND()*7)  DAY)             UNION ALL
  SELECT DATE_SUB(NOW(), INTERVAL FLOOR(RAND()*30) DAY)             UNION ALL
  SELECT DATE_SUB(NOW(), INTERVAL FLOOR(RAND()*30) DAY)             UNION ALL
  SELECT DATE_SUB(NOW(), INTERVAL FLOOR(RAND()*30) DAY)             UNION ALL
  SELECT DATE_SUB(NOW(), INTERVAL FLOOR(RAND()*30) DAY)             UNION ALL
  SELECT DATE_SUB(NOW(), INTERVAL FLOOR(RAND()*30) DAY)
) t;

-- alarms status 별 타임스탬프 일관성 보정
UPDATE alarms SET ack_at = NULL,  ack_user_id  = NULL,
                  done_at = NULL, done_user_id = NULL, done_comment = NULL
 WHERE status = 'NEW';
UPDATE alarms SET done_at = NULL, done_user_id = NULL, done_comment = NULL
 WHERE status = 'ACK';
UPDATE alarms SET ack_at = COALESCE(ack_at, DATE_ADD(occurred_at, INTERVAL 30 MINUTE)),
                  ack_user_id = COALESCE(ack_user_id, 'admin')
 WHERE status IN ('ACK','DONE');

-- ============================================================
-- 7. environment_measurements — 정상값 + 이상치 시연 데이터
--   분 단위 듬성듬성, 정상 ~50건 + 이상치 8건
-- ============================================================

-- 7.1 정상값 (TEMP/HUM 각 센서 × 10분 간격 × 5포인트 = 90건)
INSERT INTO environment_measurements (param_id, measured_value, measured_at)
SELECT
  p.param_id,
  CASE WHEN p.tag_code LIKE '%TEMP%VAL' THEN 22.0 + RAND() * 0.5  -- 정상 온도
       WHEN p.tag_code LIKE '%HUM%VAL'  THEN 45.0 + RAND() * 2.0  -- 정상 습도
       ELSE 100.0 + RAND() * 50.0
  END,
  DATE_SUB(NOW(), INTERVAL (m.offset_min) MINUTE)
FROM environment_parameters p
CROSS JOIN (
  SELECT 5 AS offset_min UNION ALL SELECT 20 UNION ALL SELECT 60 UNION ALL
  SELECT 120          UNION ALL SELECT 360
) m
WHERE p.tag_code LIKE 'ENV_TEMP%VAL' OR p.tag_code LIKE 'ENV_HUM%VAL';

-- 7.2 이상치 — 지난주 ENV_PART_01 CNT_03 > 1200 (3건)
INSERT INTO environment_measurements (param_id, measured_value, measured_at)
SELECT param_id, val, DATE_SUB(NOW(), INTERVAL d DAY)
FROM (
  SELECT (SELECT param_id FROM environment_parameters WHERE tag_code = 'ENV_PART_01_CNT_03' LIMIT 1) AS param_id,
         1450 AS val, 2 AS d UNION ALL
  SELECT (SELECT param_id FROM environment_parameters WHERE tag_code = 'ENV_PART_01_CNT_03' LIMIT 1),
         1320, 4 UNION ALL
  SELECT (SELECT param_id FROM environment_parameters WHERE tag_code = 'ENV_PART_01_CNT_03' LIMIT 1),
         1280, 6
) outliers
WHERE param_id IS NOT NULL;

-- 7.3 이상치 — 지난달 ENV_TEMP/HUM 범위 초과 (5건)
INSERT INTO environment_measurements (param_id, measured_value, measured_at)
SELECT param_id, val, DATE_SUB(NOW(), INTERVAL d DAY)
FROM (
  SELECT (SELECT param_id FROM environment_parameters WHERE tag_code = 'ENV_TEMP_01_VAL' LIMIT 1) AS param_id, 24.5 AS val, 10 AS d UNION ALL
  SELECT (SELECT param_id FROM environment_parameters WHERE tag_code = 'ENV_TEMP_02_VAL' LIMIT 1),                25.1,        15 UNION ALL
  SELECT (SELECT param_id FROM environment_parameters WHERE tag_code = 'ENV_HUM_01_VAL'  LIMIT 1),                52.3,        12 UNION ALL
  SELECT (SELECT param_id FROM environment_parameters WHERE tag_code = 'ENV_HUM_03_VAL'  LIMIT 1),                39.8,        20 UNION ALL
  SELECT (SELECT param_id FROM environment_parameters WHERE tag_code = 'ENV_HUM_02_VAL'  LIMIT 1),                53.6,        25
) outliers
WHERE param_id IS NOT NULL;

-- ============================================================
-- 8. partners (입고/출하 거래처)
--   step_no '01' (Wafer 입고) / step_no '08' (출하/포장)
-- ============================================================
INSERT IGNORE INTO partners
  (step_no, product_name,           stock_qty, stock_unit, deadline,
   company_name,        contact_tel,      contact_email,
   updated_at, manager_name, safety_stock, delay_reason) VALUES
  ('01', '실리콘 웨이퍼 8인치',  1200, '장',  '2026-05-26',
   '한국반도체소재', '02-1234-5678',   'wafer@krsemi.co.kr',
   NOW(), '김재원',        300, NULL),
  ('08', '반도체 패키지 트레이',  850, 'Box', '2026-05-26',
   '패키징코리아',   '031-9876-5432',  'pkg@pkgkorea.co.kr',
   NOW(), '이수진',        200, NULL);

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- 9. 검증
-- ============================================================
SELECT '=== 마스터 데이터 카운트 ===' AS '';
SELECT 'processes'              AS tbl, COUNT(*) AS cnt, 8        AS expected FROM processes
UNION ALL SELECT 'equipments',              COUNT(*), 18         FROM equipments
UNION ALL SELECT 'equipment_parameters',    COUNT(*), NULL       FROM equipment_parameters
UNION ALL SELECT 'environment_sensors',     COUNT(*), 18         FROM environment_sensors
UNION ALL SELECT 'environment_parameters',  COUNT(*), NULL       FROM environment_parameters
UNION ALL SELECT 'partners',                COUNT(*), 2          FROM partners;

SELECT '=== 히스토리 데이터 카운트 ===' AS '';
SELECT 'oee_metrics'              AS tbl, COUNT(*) AS cnt, 558  AS expected FROM oee_metrics       -- 18대 × 31일
UNION ALL SELECT 'alarms',                COUNT(*), 144         FROM alarms                       -- 18대 × 8건
UNION ALL SELECT 'environment_measurements', COUNT(*), NULL     FROM environment_measurements;

SELECT '=== oee_metrics 날짜 범위 ===' AS '';
SELECT MIN(period_start) AS first_day,
       MAX(period_start) AS last_day,
       COUNT(DISTINCT DATE(period_start)) AS day_count
  FROM oee_metrics;

SELECT '=== PROBE_02 OEE 평균 (지난달, 기대 ~0.65) ===' AS '';
SELECT equipment_id,
       ROUND(AVG(availability), 3) AS avg_a,
       ROUND(AVG(performance),  3) AS avg_p,
       ROUND(AVG(quality),      3) AS avg_q,
       ROUND(AVG(oee),          3) AS avg_oee
  FROM oee_metrics
 WHERE equipment_id IN ('FURN_01','PROBE_02')
 GROUP BY equipment_id;

SELECT '=== alarms 날짜 범위 및 분포 ===' AS '';
SELECT MIN(occurred_at) AS first_alarm,
       MAX(occurred_at) AS last_alarm,
       COUNT(*) AS total
  FROM alarms;
SELECT severity, status, COUNT(*) AS cnt FROM alarms GROUP BY severity, status ORDER BY severity, status;

SELECT '=== FURN_01 ERR 비율 (시연 기대 70%) ===' AS '';
SELECT severity, COUNT(*) AS cnt
  FROM alarms a
  JOIN equipment_parameters p ON p.param_id = a.equipment_param_id
 WHERE p.equipment_id = 'FURN_01'
 GROUP BY severity;

SELECT '=== environment_sensors zone_code 채워짐 확인 ===' AS '';
SELECT zone_code, COUNT(*) FROM environment_sensors GROUP BY zone_code;
