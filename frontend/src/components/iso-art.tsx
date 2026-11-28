// 메인 히어로 그림: 밝은 아이소메트릭 일러스트.
// AI Agent 블록 → A2X Gateway(방패) → 사내 시스템 서버 블록. 길을 따라 점이 흐른다.
// 등각 투영을 직접 계산해 SVG로 그린다(외부 이미지 · 라이브러리 없음).

const U = 26; // 격자 한 칸 크기(px)
const C = Math.cos(Math.PI / 6);
const S = 0.5;
const OX = 202;
const OY = 84;

type P = [number, number];
const p = (x: number, y: number, z = 0): P => [OX + (x - y) * C * U, OY + (x + y) * S * U - z * U];
const pts = (a: P[]) => a.map((q) => q.map((v) => v.toFixed(1)).join(",")).join(" ");
const path = (a: P[]) => "M" + a.map((q) => q.map((v) => v.toFixed(1)).join(",")).join(" L");

type Tone = { top: string; left: string; right: string };

const TONES: Record<string, Tone> = {
  base: { top: "#ffffff", left: "#e8edf6", right: "#dae1ee" },
  violet: { top: "#ddd2ff", left: "#b9a4fb", right: "#9c84f0" },
  blue: { top: "#cfe2ff", left: "#9cc3ff", right: "#7aa7f5" },
  mint: { top: "#cdf3dc", left: "#97e0b4", right: "#74cc98" },
  gate: { top: "#b9ccff", left: "#5f7dfb", right: "#4a5fe0" },
  orange: { top: "#ffe2bf", left: "#ffc07a", right: "#f5a656" },
  green: { top: "#d2f1d9", left: "#9ddcac", right: "#7dc78f" },
  teal: { top: "#cdeff5", left: "#8fd6e4", right: "#6cc0d2" },
  pink: { top: "#ffd9e4", left: "#ffa9c2", right: "#f28aa8" },
};

function Box({ x, y, z = 0, w, d, h, tone, stroke = "rgb(0 0 0 / .05)" }: { x: number; y: number; z?: number; w: number; d: number; h: number; tone: Tone; stroke?: string }) {
  const top = [p(x, y, z + h), p(x + w, y, z + h), p(x + w, y + d, z + h), p(x, y + d, z + h)];
  const left = [p(x, y + d, z), p(x + w, y + d, z), p(x + w, y + d, z + h), p(x, y + d, z + h)];
  const right = [p(x + w, y, z), p(x + w, y + d, z), p(x + w, y + d, z + h), p(x + w, y, z + h)];
  return (
    <g strokeLinejoin="round">
      <polygon points={pts(left)} fill={tone.left} stroke={stroke} />
      <polygon points={pts(right)} fill={tone.right} stroke={stroke} />
      <polygon points={pts(top)} fill={tone.top} stroke={stroke} />
    </g>
  );
}

// 떠 있는 이름표
function Tag({ at, text, color, delay = 0 }: { at: P; text: string; color: string; delay?: number }) {
  const w = text.length * 7.4 + 22;
  return (
    <g>
      <animateTransform attributeName="transform" type="translate" values="0 0; 0 -4; 0 0" dur="3.2s" begin={`${delay}s`} repeatCount="indefinite" />
      <line x1={at[0]} y1={at[1]} x2={at[0]} y2={at[1] - 16} stroke={color} strokeWidth={1.4} strokeDasharray="2 3" opacity={0.7} />
      <rect x={at[0] - w / 2} y={at[1] - 38} width={w} height={22} rx={11} fill="#fff" stroke="rgb(0 0 0 / .06)" filter="url(#iso-soft)" />
      <circle cx={at[0] - w / 2 + 11} cy={at[1] - 27} r={3.5} fill={color} />
      <text x={at[0] - w / 2 + 19} y={at[1] - 23} fontSize={11} fontWeight={700} fill="#3a3a3c" style={{ fontFamily: "inherit" }}>
        {text}
      </text>
    </g>
  );
}

const AGENTS = [
  { y: 0.2, tone: TONES.violet, name: "CS 챗봇", color: "#8b6cf0" },
  { y: 2.6, tone: TONES.blue, name: "구매 Agent", color: "#4f8ef7" },
  { y: 5.0, tone: TONES.mint, name: "분석 Agent", color: "#34c759" },
];
const SYSTEMS = [
  { y: -0.4, h: 2.2, tone: TONES.orange, name: "ERP", color: "#ff9500" },
  { y: 1.5, h: 1.6, tone: TONES.green, name: "WMS", color: "#30b955" },
  { y: 3.4, h: 2.6, tone: TONES.teal, name: "CRM", color: "#1fa7c2" },
  { y: 5.3, h: 1.9, tone: TONES.pink, name: "HR", color: "#f0587f" },
];
const GATE = { x: 4.6, y: 2.2, w: 2.6, d: 2.6, h: 2.3 };
const GC: [number, number] = [GATE.x + GATE.w / 2, GATE.y + GATE.d / 2];

// 길: Agent 앞 → 게이트 / 게이트 → 시스템 (바닥 위 꺾인 선)
const inLanes = AGENTS.map((a) => [p(1.5, a.y + 0.7), p(3.2, a.y + 0.7), p(3.2, GC[1]), p(GATE.x, GC[1])]);
const outLanes = SYSTEMS.map((s) => [p(GATE.x + GATE.w, GC[1]), p(8.6, GC[1]), p(8.6, s.y + 0.7), p(9.8, s.y + 0.7)]);

export function IsoArt({ className }: { className?: string }) {
  // 게이트 앞면(왼쪽 면) 가운데: 방패 위치
  const fc = p(GATE.x + GATE.w / 2, GATE.y + GATE.d, GATE.h / 2);
  const topC = p(GC[0], GC[1], GATE.h);

  return (
    // 상자 없이 장면만: 히어로 배경에 녹아들도록 하고, 장면 둘레 여백은 viewBox로 잘라 크게 보이게 한다
    <div className={className} style={{ position: "relative", aspectRatio: "496 / 360" }}>
      <svg viewBox="12 28 496 360" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", overflow: "visible" }} role="img" aria-label="AI Agent가 A2X Gateway를 거쳐 사내 시스템에 연결되는 그림">
        <defs>
          <filter id="iso-shadow" x="-20%" y="-20%" width="140%" height="160%">
            <feDropShadow dx="0" dy="18" stdDeviation="16" floodColor="#5e5ce6" floodOpacity=".16" />
          </filter>
          <filter id="iso-soft" x="-30%" y="-50%" width="160%" height="220%">
            <feDropShadow dx="0" dy="3" stdDeviation="3" floodColor="#000" floodOpacity=".08" />
          </filter>
          <filter id="iso-glow" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="2.2" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <radialGradient id="iso-ring">
            <stop offset=".55" stopColor="#7d5cf5" stopOpacity="0" />
            <stop offset=".8" stopColor="#7d5cf5" stopOpacity=".35" />
            <stop offset="1" stopColor="#7d5cf5" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* 받침판 */}
        <g filter="url(#iso-shadow)">
          <Box x={-0.8} y={-1.2} w={12.4} d={8.2} h={0.45} z={-0.45} tone={TONES.base} />
        </g>
        {/* 바닥 격자 */}
        <g stroke="#eef1f7" strokeWidth={1}>
          {Array.from({ length: 12 }, (_, i) => (
            <line key={"gx" + i} x1={p(-0.8 + i + 0.4, -1.2)[0]} y1={p(-0.8 + i + 0.4, -1.2)[1]} x2={p(-0.8 + i + 0.4, 7)[0]} y2={p(-0.8 + i + 0.4, 7)[1]} />
          ))}
          {Array.from({ length: 8 }, (_, i) => (
            <line key={"gy" + i} x1={p(-0.8, -1.2 + i + 0.6)[0]} y1={p(-0.8, -1.2 + i + 0.6)[1]} x2={p(11.6, -1.2 + i + 0.6)[0]} y2={p(11.6, -1.2 + i + 0.6)[1]} />
          ))}
        </g>

        {/* 길 */}
        {[...inLanes, ...outLanes].map((l, i) => (
          <g key={"lane" + i}>
            <polyline points={pts(l)} fill="none" stroke="#dfe6f3" strokeWidth={7} strokeLinecap="round" strokeLinejoin="round" />
            <polyline points={pts(l)} fill="none" stroke="#fff" strokeWidth={1.6} strokeDasharray="3 5" strokeLinecap="round" />
          </g>
        ))}

        {/* 흐르는 점 */}
        <g filter="url(#iso-glow)">
          {inLanes.map((l, i) => (
            <circle key={"di" + i} r={3.6} fill={AGENTS[i].color}>
              <animateMotion dur="2.4s" begin={`${i * 0.7}s`} repeatCount="indefinite" path={path(l)} />
              <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;.12;.88;1" dur="2.4s" begin={`${i * 0.7}s`} repeatCount="indefinite" />
            </circle>
          ))}
          {outLanes.map((l, i) => (
            <circle key={"do" + i} r={3.6} fill={SYSTEMS[i].color}>
              <animateMotion dur="2.2s" begin={`${1.2 + i * 0.55}s`} repeatCount="indefinite" path={path(l)} />
              <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;.12;.88;1" dur="2.2s" begin={`${1.2 + i * 0.55}s`} repeatCount="indefinite" />
            </circle>
          ))}
        </g>

        {/* Agent 블록 (뒤쪽부터) */}
        {AGENTS.map((a) => (
          <g key={a.name}>
            <Box x={0} y={a.y} w={1.4} d={1.4} h={1.1} tone={a.tone} />
            {/* 윗면의 로봇 얼굴 */}
            {(() => {
              const c = p(0.7, a.y + 0.7, 1.1);
              return (
                <g>
                  <ellipse cx={c[0]} cy={c[1]} rx={13} ry={7.5} fill="#fff" opacity={0.85} />
                  <circle cx={c[0] - 4.5} cy={c[1]} r={1.8} fill={a.color} />
                  <circle cx={c[0] + 4.5} cy={c[1]} r={1.8} fill={a.color} />
                </g>
              );
            })()}
          </g>
        ))}

        {/* A2X Gateway */}
        <Box x={GATE.x} y={GATE.y} w={GATE.w} d={GATE.d} h={GATE.h} tone={TONES.gate} stroke="rgb(255 255 255 / .35)" />
        {/* 앞면 방패 */}
        <g transform={`translate(${fc[0]} ${fc[1]}) skewY(30) scale(.95)`}>
          <path d="M0,-17 L13,-11.5 V-1 C13,8 7,14 0,17 C-7,14 -13,8 -13,-1 V-11.5 Z" fill="#fff" opacity={0.95} />
          <path d="M-5.5,0 L-1.5,4 L6,-4" fill="none" stroke="#5f7dfb" strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round" />
        </g>
        {/* 오른쪽 면 슬롯 */}
        {[0.6, 1.1, 1.6].map((z) => (
          <polyline key={z} points={pts([p(GATE.x + GATE.w, GATE.y + 0.5, z), p(GATE.x + GATE.w, GATE.y + GATE.d - 0.5, z)])} stroke="rgb(255 255 255 / .45)" strokeWidth={2} strokeLinecap="round" />
        ))}
        {/* 윗면 빛 링 */}
        <ellipse cx={topC[0]} cy={topC[1]} rx={30} ry={17} fill="none" stroke="#fff" strokeWidth={2.2} opacity={0.9} />
        <ellipse cx={topC[0]} cy={topC[1]} rx={30} ry={17} fill="url(#iso-ring)">
          <animate attributeName="rx" values="30;46;30" dur="2.6s" repeatCount="indefinite" />
          <animate attributeName="ry" values="17;26;17" dur="2.6s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="1;0;1" dur="2.6s" repeatCount="indefinite" />
        </ellipse>
        <text x={topC[0]} y={topC[1] + 4} textAnchor="middle" fontSize={12} fontWeight={800} fill="#3b4fd6" letterSpacing="-.3" style={{ fontFamily: "inherit" }}>
          A2X
        </text>

        {/* 시스템 서버 블록 */}
        {SYSTEMS.map((s) => (
          <g key={s.name}>
            <Box x={9.8} y={s.y} w={1.4} d={1.4} h={s.h} tone={s.tone} />
            {Array.from({ length: Math.floor(s.h / 0.5) }, (_, k) => {
              const z = 0.35 + k * 0.5;
              return (
                <g key={k}>
                  <polyline points={pts([p(11.2, s.y + 0.25, z), p(11.2, s.y + 1.0, z)])} stroke="rgb(255 255 255 / .55)" strokeWidth={2.2} strokeLinecap="round" />
                  <circle cx={p(11.2, s.y + 1.18, z)[0]} cy={p(11.2, s.y + 1.18, z)[1]} r={1.6} fill="#fff">
                    <animate attributeName="opacity" values="1;.3;1" dur={`${1.2 + k * 0.3}s`} repeatCount="indefinite" />
                  </circle>
                </g>
              );
            })}
          </g>
        ))}

        {/* 떠다니는 장식 블록 */}
        <g>
          <animateTransform attributeName="transform" type="translate" values="0 0; 0 -7; 0 0" dur="4s" repeatCount="indefinite" />
          <Box x={6.6} y={-1.0} z={2.4} w={0.6} d={0.6} h={0.6} tone={TONES.violet} />
        </g>
        <g>
          <animateTransform attributeName="transform" type="translate" values="0 0; 0 -5; 0 0" dur="3.4s" begin="1s" repeatCount="indefinite" />
          <Box x={2.2} y={6.0} z={1.6} w={0.5} d={0.5} h={0.5} tone={TONES.orange} />
        </g>

        {/* 이름표 */}
        {AGENTS.map((a, i) => (
          <Tag key={a.name} at={p(0.7, a.y + 0.7, 1.1)} text={a.name} color={a.color} delay={i * 0.5} />
        ))}
        <Tag at={[topC[0], topC[1] - 16]} text="A2X Gateway" color="#5f7dfb" delay={0.3} />
        {SYSTEMS.map((s, i) => (
          <Tag key={s.name} at={p(10.5, s.y + 0.7, s.h)} text={s.name} color={s.color} delay={0.8 + i * 0.4} />
        ))}

        {/* 검사 칩 */}
        <g filter="url(#iso-soft)">
          <animateTransform attributeName="transform" type="translate" values="0 0; 0 -3; 0 0" dur="3.6s" begin=".6s" repeatCount="indefinite" />
          {["인증", "Tool 권한", "가드레일"].map((t, i) => {
            const x = 149 + i * 74;
            const y = 362;
            return (
              <g key={t}>
                <rect x={x} y={y} width={68} height={22} rx={11} fill="#fff" />
                <circle cx={x + 12} cy={y + 11} r={6} fill="#34c759" />
                <path d={`M${x + 9},${y + 11} l2,2 l4,-4`} fill="none" stroke="#fff" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" />
                <text x={x + 22} y={y + 15} fontSize={10.5} fontWeight={700} fill="#3a3a3c" style={{ fontFamily: "inherit" }}>{t}</text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
