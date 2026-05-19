/* eslint-disable */
// =====================================================================
//  SCADA-DAS · 2-Slide Deck Generator
//  Output: SCADA-DAS_2slides.pptx
// =====================================================================
const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout  = "LAYOUT_WIDE";   // 13.333" x 7.5"
pres.author  = "w-taek";
pres.title   = "SCADA-DAS — Data Acquisition System";
pres.subject = "2-slide briefing";

// === Industrial SCADA-HMI palette =====================================
const C = {
  bg:        "0D1B2A",
  card:      "1B263B",
  cardHi:    "2A3A55",
  cardLine:  "3A4A65",
  muted:     "8DA0BD",
  dim:       "5C6F84",
  warmWhite: "E8ECF1",
  white:     "FFFFFF",
  accent:    "F77F00",   // amber — alarm / critical
  amber2:    "FCBF49",   // light amber
  cyan:      "06D6A0",   // mint — data / success
  blue:      "4ECDC4",   // teal — info
  red:       "EF476F",   // red — error
};

const F = { kr: "Apple SD Gothic Neo" };  // safe on macOS + falls back to 맑은 고딕 on Windows PowerPoint

// helper: footer accent strip + page number on every slide
function chrome(s, pageLabel) {
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.12, h: 7.5,
    fill: { color: C.accent }, line: { color: C.accent, width: 0 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 7.30, w: 13.333, h: 0.005,
    fill: { color: C.cardLine }, line: { color: C.cardLine, width: 0 },
  });
  s.addText(pageLabel, {
    x: 12.0, y: 7.20, w: 1.0, h: 0.22,
    fontSize: 9, fontFace: F.kr, color: C.dim,
    align: "right", charSpacing: 4, margin: 0,
  });
  s.addText("SCADA-DAS · 김완택", {
    x: 0.4, y: 7.20, w: 6, h: 0.22,
    fontSize: 9, fontFace: F.kr, color: C.dim,
    charSpacing: 4, margin: 0,
  });
}

// =====================================================================
//  SLIDE 1 — 문제 정의 & 시스템 전경
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: C.bg };
  chrome(s, "01 / 02");

  // ── Header ──────────────────────────────────────────────────────────
  s.addText("◆  DAS · DATA ACQUISITION SYSTEM", {
    x: 0.6, y: 0.35, w: 12, h: 0.3,
    fontSize: 11, fontFace: F.kr, bold: true,
    color: C.accent, charSpacing: 6, margin: 0,
  });

  s.addText("이질적인 6공정 라인을 단일 SCADA로", {
    x: 0.6, y: 0.65, w: 12, h: 0.85,
    fontSize: 36, fontFace: F.kr, bold: true,
    color: C.white, margin: 0,
  });

  s.addText([
    { text: "FIELD", options: { color: C.muted, bold: true } },
    { text: "    ▸    ", options: { color: C.accent, bold: true } },
    { text: "GATEWAY", options: { color: C.muted, bold: true } },
    { text: "    ▸    ", options: { color: C.accent, bold: true } },
    { text: "STORE", options: { color: C.muted, bold: true } },
  ], {
    x: 0.6, y: 1.55, w: 12, h: 0.3,
    fontSize: 12, fontFace: F.kr, charSpacing: 8, margin: 0,
  });

  // ── Diagram (3 cards horizontally) ──────────────────────────────────
  const dY = 2.05;
  const dH = 3.2;

  const cardW = 3.7;
  const gap   = 0.55;
  const card1X = 0.6;
  const card2X = card1X + cardW + gap;          // 4.85
  const card3X = card2X + cardW + gap;          // 9.10

  // ── FIELD card ──────────────────────────────────────────────────────
  s.addShape(pres.shapes.RECTANGLE, {
    x: card1X, y: dY, w: cardW, h: dH,
    fill: { color: C.card }, line: { color: C.cardLine, width: 0.75 },
  });
  // top label strip
  s.addShape(pres.shapes.RECTANGLE, {
    x: card1X, y: dY, w: cardW, h: 0.32,
    fill: { color: C.cardHi }, line: { color: C.cardHi, width: 0 },
  });
  s.addText("FIELD", {
    x: card1X, y: dY, w: cardW, h: 0.32,
    fontSize: 11, fontFace: F.kr, bold: true,
    color: C.muted, charSpacing: 6, align: "center", valign: "middle", margin: 0,
  });

  const procs = [
    ["①", "포토",   "TRACK",  "MQTT",   C.blue],
    ["②", "산화",   "FURN",   "Modbus", C.accent],
    ["③", "박막",   "PECVD",  "OPC UA", C.cyan],
    ["④", "식각",   "ETCH",   "OPC UA", C.cyan],
    ["⑤", "배선",   "SPTT",   "MQTT",   C.blue],
    ["⑥", "검사",   "PROBE",  "MQTT",   C.blue],
  ];

  const pStartY = dY + 0.45;
  const pRowH   = 0.30;
  procs.forEach(([num, kor, eng, proto, col], i) => {
    const y = pStartY + i * pRowH;
    // num + kor + eng
    s.addText([
      { text: num + " ", options: { color: C.dim, bold: true, fontSize: 12 } },
      { text: kor + " ",  options: { color: C.warmWhite, bold: true, fontSize: 12 } },
      { text: eng,        options: { color: C.muted, fontSize: 11 } },
    ], {
      x: card1X + 0.2, y: y, w: 2.2, h: 0.26,
      fontFace: F.kr, margin: 0, valign: "middle",
    });
    // proto badge
    const bx = card1X + cardW - 1.1;
    s.addShape(pres.shapes.RECTANGLE, {
      x: bx, y: y + 0.03, w: 0.9, h: 0.20,
      fill: { color: col, transparency: 75 },
      line: { color: col, width: 0.75 },
    });
    s.addText(proto, {
      x: bx, y: y + 0.03, w: 0.9, h: 0.20,
      fontSize: 9, fontFace: F.kr, bold: true,
      color: col, align: "center", valign: "middle", margin: 0,
    });
  });

  // BMS divider + row
  const bmsY = pStartY + 6 * pRowH + 0.13;
  s.addShape(pres.shapes.LINE, {
    x: card1X + 0.2, y: bmsY - 0.04, w: cardW - 0.4, h: 0,
    line: { color: C.cardLine, width: 0.75, dashType: "dash" },
  });
  s.addText([
    { text: "◇ ",         options: { color: C.amber2, fontSize: 11 } },
    { text: "환경 BMS  ",  options: { color: C.warmWhite, bold: true, fontSize: 12 } },
    { text: "18 센서",     options: { color: C.muted, fontSize: 11 } },
  ], {
    x: card1X + 0.2, y: bmsY + 0.02, w: 2.2, h: 0.26,
    fontFace: F.kr, margin: 0, valign: "middle",
  });
  const bbx = card1X + cardW - 1.1;
  s.addShape(pres.shapes.RECTANGLE, {
    x: bbx, y: bmsY + 0.05, w: 0.9, h: 0.20,
    fill: { color: C.accent, transparency: 75 },
    line: { color: C.accent, width: 0.75 },
  });
  s.addText("Modbus", {
    x: bbx, y: bmsY + 0.05, w: 0.9, h: 0.20,
    fontSize: 9, fontFace: F.kr, bold: true,
    color: C.accent, align: "center", valign: "middle", margin: 0,
  });

  // ── GATEWAY card ────────────────────────────────────────────────────
  s.addShape(pres.shapes.RECTANGLE, {
    x: card2X, y: dY, w: cardW, h: dH,
    fill: { color: C.cardHi }, line: { color: C.accent, width: 1.25 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: card2X, y: dY, w: cardW, h: 0.32,
    fill: { color: C.accent, transparency: 0 }, line: { color: C.accent, width: 0 },
  });
  s.addText("GATEWAY", {
    x: card2X, y: dY, w: cardW, h: 0.32,
    fontSize: 11, fontFace: F.kr, bold: true,
    color: C.bg, charSpacing: 6, align: "center", valign: "middle", margin: 0,
  });

  // Big "Node-RED" label
  s.addText("Node-RED", {
    x: card2X, y: dY + 0.55, w: cardW, h: 0.55,
    fontSize: 28, fontFace: F.kr, bold: true,
    color: C.white, align: "center", margin: 0,
  });
  s.addText("315 nodes  ·  9 sections", {
    x: card2X, y: dY + 1.10, w: cardW, h: 0.3,
    fontSize: 11, fontFace: F.kr,
    color: C.muted, align: "center", italic: true, margin: 0,
  });

  // 4-stage pipeline pills
  const stages = [
    { n: "1", label: "수집", desc: "Acquire" },
    { n: "2", label: "가공", desc: "Transform" },
    { n: "3", label: "저장", desc: "Persist" },
    { n: "4", label: "알람", desc: "Notify" },
  ];
  stages.forEach((st, i) => {
    const sy = dY + 1.65 + i * 0.36;
    const highlight = (i === 3);
    s.addShape(pres.shapes.RECTANGLE, {
      x: card2X + 0.25, y: sy, w: cardW - 0.5, h: 0.30,
      fill: { color: highlight ? C.accent : C.bg, transparency: highlight ? 0 : 0 },
      line: { color: highlight ? C.accent : C.cardLine, width: 0.75 },
    });
    s.addText([
      { text: st.n + ".  ", options: { color: highlight ? C.bg : C.muted, bold: true } },
      { text: st.label,     options: { color: highlight ? C.bg : C.white, bold: true } },
      { text: "   " + st.desc, options: { color: highlight ? C.bg : C.dim, fontSize: 9, italic: true } },
    ], {
      x: card2X + 0.25, y: sy, w: cardW - 0.5, h: 0.30,
      fontSize: 11, fontFace: F.kr, align: "center", valign: "middle", margin: 0,
    });
  });

  // ── STORE card ──────────────────────────────────────────────────────
  s.addShape(pres.shapes.RECTANGLE, {
    x: card3X, y: dY, w: cardW, h: dH,
    fill: { color: C.card }, line: { color: C.cardLine, width: 0.75 },
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: card3X, y: dY, w: cardW, h: 0.32,
    fill: { color: C.cardHi }, line: { color: C.cardHi, width: 0 },
  });
  s.addText("STORE", {
    x: card3X, y: dY, w: cardW, h: 0.32,
    fontSize: 11, fontFace: F.kr, bold: true,
    color: C.muted, charSpacing: 6, align: "center", valign: "middle", margin: 0,
  });

  // MySQL block
  s.addShape(pres.shapes.RECTANGLE, {
    x: card3X + 0.3, y: dY + 0.55, w: cardW - 0.6, h: 1.18,
    fill: { color: C.bg }, line: { color: C.cyan, width: 1.25 },
  });
  s.addText([
    { text: "MySQL",                 options: { color: C.cyan, bold: true, fontSize: 20 } },
    { text: "\n시계열 + 마스터 + 이벤트",  options: { color: C.warmWhite, fontSize: 11 } },
    { text: "\n8 tables",            options: { color: C.muted, fontSize: 10, italic: true } },
  ], {
    x: card3X + 0.3, y: dY + 0.6, w: cardW - 0.6, h: 1.1,
    fontFace: F.kr, align: "center", valign: "middle", margin: 0, paraSpaceAfter: 2,
  });

  // MQTT block
  s.addShape(pres.shapes.RECTANGLE, {
    x: card3X + 0.3, y: dY + 1.88, w: cardW - 0.6, h: 1.18,
    fill: { color: C.bg }, line: { color: C.accent, width: 1.25 },
  });
  s.addText([
    { text: "MQTT",                          options: { color: C.accent, bold: true, fontSize: 20 } },
    { text: "\n실시간 알람 버스",                 options: { color: C.warmWhite, fontSize: 11 } },
    { text: "\nsmartfactory/alarms",         options: { color: C.muted, fontSize: 10, italic: true } },
  ], {
    x: card3X + 0.3, y: dY + 1.93, w: cardW - 0.6, h: 1.1,
    fontFace: F.kr, align: "center", valign: "middle", margin: 0, paraSpaceAfter: 2,
  });

  // Arrows between cards
  const arrowY = dY + dH / 2;
  // FIELD -> GATEWAY
  s.addShape(pres.shapes.LINE, {
    x: card1X + cardW + 0.05, y: arrowY, w: gap - 0.10, h: 0,
    line: { color: C.muted, width: 2.5, endArrowType: "triangle" },
  });
  // GATEWAY -> STORE
  s.addShape(pres.shapes.LINE, {
    x: card2X + cardW + 0.05, y: arrowY, w: gap - 0.10, h: 0,
    line: { color: C.muted, width: 2.5, endArrowType: "triangle" },
  });

  // ── Big stat callouts row ────────────────────────────────────────────
  const sY = dY + dH + 0.4;
  const sH = 1.05;
  const stats = [
    { n: "4",   u: "",  label: "프로토콜",    sub: "Modbus · OPC UA · MQTT" },
    { n: "36",  u: "",  label: "데이터 소스",  sub: "설비 18 + 센서 18" },
    { n: "270", u: "+", label: "시계열 태그",  sub: "180 EQP + 93 ENV" },
    { n: "3",   u: "",  label: "다중 주기",    sub: "1s · 5s · 30s + event" },
  ];
  const statW = (13.333 - 0.6 * 2 - 0.5 * 3) / 4;   // ~2.78
  stats.forEach((st, i) => {
    const sx = 0.6 + i * (statW + 0.5);
    // bottom accent line
    s.addShape(pres.shapes.RECTANGLE, {
      x: sx, y: sY + sH - 0.05, w: statW, h: 0.04,
      fill: { color: C.accent }, line: { color: C.accent, width: 0 },
    });
    // big number
    s.addText([
      { text: st.n, options: { color: C.white, bold: true, fontSize: 54 } },
      { text: st.u, options: { color: C.accent, bold: true, fontSize: 30 } },
    ], {
      x: sx, y: sY, w: statW, h: 0.7, fontFace: F.kr, margin: 0, valign: "bottom",
    });
    s.addText(st.label, {
      x: sx, y: sY + 0.65, w: statW, h: 0.22,
      fontSize: 11, fontFace: F.kr, bold: true,
      color: C.amber2, charSpacing: 4, margin: 0,
    });
    s.addText(st.sub, {
      x: sx, y: sY + 0.85, w: statW, h: 0.2,
      fontSize: 9, fontFace: F.kr, color: C.muted, margin: 0, italic: true,
    });
  });

  // ── Footer quote ────────────────────────────────────────────────────
  s.addText([
    { text: "“  ", options: { color: C.accent, fontSize: 16, bold: true } },
    { text: "프로토콜 4개를 다룬 건 자랑이 아니라 ",
      options: { color: C.warmWhite, fontSize: 13, italic: true } },
    { text: "공장 현실",
      options: { color: C.accent, fontSize: 13, bold: true, italic: true } },
    { text: "이다  ”", options: { color: C.warmWhite, fontSize: 13, italic: true } },
  ], {
    x: 0.6, y: 6.85, w: 12, h: 0.3,
    fontFace: F.kr, margin: 0,
  });
}

// =====================================================================
//  SLIDE 2 — 파이프라인 4단계 & 이중 경로 알람 (with EVENT 캡처)
// =====================================================================
{
  const s = pres.addSlide();
  s.background = { color: C.bg };
  chrome(s, "02 / 02");

  // ── Header ──────────────────────────────────────────────────────────
  s.addText("◆  NODE-RED PIPELINE  ·  4 STAGES", {
    x: 0.6, y: 0.35, w: 12, h: 0.3,
    fontSize: 11, fontFace: F.kr, bold: true,
    color: C.accent, charSpacing: 6, margin: 0,
  });

  s.addText([
    { text: "수집 ", options: { color: C.white } },
    { text: "→ ",    options: { color: C.muted } },
    { text: "가공 ", options: { color: C.white } },
    { text: "→ ",    options: { color: C.muted } },
    { text: "저장 ", options: { color: C.white } },
    { text: "→ ",    options: { color: C.muted } },
    { text: "알람",   options: { color: C.accent } },
  ], {
    x: 0.6, y: 0.65, w: 12, h: 0.85,
    fontSize: 36, fontFace: F.kr, bold: true, margin: 0,
  });

  s.addText("4 protocols  →  single schema  →  dual-path alarm", {
    x: 0.6, y: 1.55, w: 12, h: 0.3,
    fontSize: 12, fontFace: F.kr,
    color: C.muted, charSpacing: 8, italic: true, margin: 0,
  });

  // ── 4-Stage horizontal flow row (slim) ──────────────────────────────
  const fY = 2.00;
  const fH = 0.85;
  const fMargin = 0.6;
  const fGap = 0.20;
  const flowItemW = (13.333 - fMargin * 2 - fGap * 3) / 4;

  const stageFlow = [
    { n: "01", title: "수집", desc: "Modbus × 36 · OPC UA Fan-out 66 · MQTT 구독" },
    { n: "02", title: "가공", desc: "Function 88개 · 스케일·tag 매핑·임계치" },
    { n: "03", title: "저장", desc: "마스터 ↔ 시계열 분리 · 멀티 row INSERT" },
    { n: "04", title: "알람", desc: "Edge-trigger 디듀플 · ★ DB + MQTT 이중경로", hot: true },
  ];

  stageFlow.forEach((st, i) => {
    const x = fMargin + i * (flowItemW + fGap);
    const hot = !!st.hot;

    s.addShape(pres.shapes.RECTANGLE, {
      x: x, y: fY, w: flowItemW, h: fH,
      fill: { color: hot ? C.cardHi : C.card },
      line: { color: hot ? C.accent : C.cardLine, width: hot ? 1.5 : 0.75 },
    });
    // Number (left)
    s.addText(st.n, {
      x: x + 0.18, y: fY + 0.05, w: 0.55, h: 0.32,
      fontSize: 16, fontFace: F.kr, bold: true,
      color: hot ? C.accent : C.muted, margin: 0, valign: "middle",
    });
    // Title (next to number)
    s.addText(st.title, {
      x: x + 0.75, y: fY + 0.05, w: flowItemW - 0.9, h: 0.36,
      fontSize: 18, fontFace: F.kr, bold: true,
      color: hot ? C.accent : C.white, margin: 0, valign: "middle",
    });
    // Description (below)
    s.addText(st.desc, {
      x: x + 0.18, y: fY + 0.43, w: flowItemW - 0.3, h: 0.38,
      fontSize: 9, fontFace: F.kr,
      color: hot ? C.amber2 : C.muted, margin: 0, valign: "middle",
    });

    // Arrow between items (not after the last)
    if (i < 3) {
      s.addShape(pres.shapes.LINE, {
        x: x + flowItemW + 0.02, y: fY + fH / 2,
        w: fGap - 0.04, h: 0,
        line: { color: C.accent, width: 1.5, endArrowType: "triangle" },
      });
    }
  });

  // ── Spotlight label for the capture ─────────────────────────────────
  const capY = 3.20;

  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: capY, w: 0.05, h: 0.32,
    fill: { color: C.accent }, line: { color: C.accent, width: 0 },
  });
  s.addText([
    { text: "★  ", options: { color: C.accent, bold: true } },
    { text: "EVENT  ·  알람 이중 경로 (Dual-Path Alarm)",
      options: { color: C.white, bold: true } },
  ], {
    x: 0.75, y: capY, w: 8.0, h: 0.32,
    fontSize: 13, fontFace: F.kr, charSpacing: 2, margin: 0, valign: "middle",
  });
  s.addText("Build Alarm INSERT → MySQL (이력)   +   Format MQTT Payload → MQTT Out (실시간)", {
    x: 0.75, y: capY + 0.32, w: 12, h: 0.25,
    fontSize: 10, fontFace: F.kr, italic: true,
    color: C.muted, margin: 0,
  });

  // ── EVENT capture image (main visual, centered) ─────────────────────
  // Original: 1834 x 730 (ratio 2.512:1)
  const imgPath = "/Users/w-taek/Desktop/node-red_04_Event_통합처리.png";
  const imgRatio = 1834 / 730;
  const targetH = 2.05;
  const calcW = targetH * imgRatio; // ≈ 5.15
  const imgX = (13.333 - calcW) / 2;
  const imgY = capY + 0.62;

  // White-ish frame around image to make it pop against dark bg
  s.addShape(pres.shapes.RECTANGLE, {
    x: imgX - 0.06, y: imgY - 0.06, w: calcW + 0.12, h: targetH + 0.12,
    fill: { color: C.warmWhite }, line: { color: C.accent, width: 0 },
  });

  s.addImage({
    path: imgPath,
    x: imgX, y: imgY, w: calcW, h: targetH,
  });

  // Side annotations: left "이력" / right "실시간"
  s.addText([
    { text: "이력\n",      options: { color: C.cyan, bold: true, fontSize: 20, breakLine: true } },
    { text: "DB",          options: { color: C.cyan, bold: true, fontSize: 14, breakLine: true } },
    { text: "(MySQL)",     options: { color: C.muted, fontSize: 10 } },
  ], {
    x: 0.6, y: imgY, w: imgX - 0.8, h: targetH,
    fontFace: F.kr, align: "center", valign: "middle", margin: 0,
  });
  s.addText([
    { text: "실시간\n",    options: { color: C.accent, bold: true, fontSize: 20, breakLine: true } },
    { text: "MQTT",        options: { color: C.accent, bold: true, fontSize: 14, breakLine: true } },
    { text: "(즉시 전파)", options: { color: C.muted, fontSize: 10 } },
  ], {
    x: imgX + calcW + 0.2, y: imgY, w: 13.333 - imgX - calcW - 0.8, h: targetH,
    fontFace: F.kr, align: "center", valign: "middle", margin: 0,
  });

  // ── Footer quote (table removed — content moved to verbal narration) ─
  s.addText([
    { text: "“  ", options: { color: C.accent, fontSize: 16, bold: true } },
    { text: "DAS의 가치는 ", options: { color: C.warmWhite, fontSize: 13, italic: true } },
    { text: "4개를 다룬 것",   options: { color: C.dim, fontSize: 13, italic: true } },
    { text: "이 아니라, ",     options: { color: C.warmWhite, fontSize: 13, italic: true } },
    { text: "위에서 잊을 수 있게 한 것", options: { color: C.accent, fontSize: 13, bold: true, italic: true } },
    { text: "이다  ”",         options: { color: C.warmWhite, fontSize: 13, italic: true } },
  ], {
    x: 0.6, y: 6.85, w: 12, h: 0.3,
    fontFace: F.kr, margin: 0,
  });
}

// =====================================================================
pres.writeFile({ fileName: "/Users/w-taek/work/25_26-AutoEver3/16_SCADA/SCADA-DAS/docs/slides/SCADA-DAS_2slides.pptx" })
  .then(fn => console.log("✅ Created:", fn))
  .catch(err => { console.error("❌", err); process.exit(1); });
