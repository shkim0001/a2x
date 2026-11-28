import { useEffect, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Loader2 } from "lucide-react";
import { get, post, type SessionOut } from "@/lib/api";
import { errText } from "@/lib/queries";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { IsoArt } from "@/components/iso-art";
import { cn } from "@/lib/utils";

type Mode = "login" | "signup";

// 개발용 시드 계정(비밀번호 공통). 운영 배포 시에는 이 안내를 빼야 한다.
const DEMO = [
  { email: "hong@example.com", label: "시스템 담당자 · 홍길동" },
  { email: "admin@example.com", label: "admin" },
  { email: "kim@example.com", label: "일반 사용자 · 김민수" },
];
const DEMO_PW = "a2x-demo-1234";

// Google 로그인 실패 코드(백엔드 콜백이 ?login_error=로 돌려줌) → 안내 문구
const LOGIN_ERRORS: Record<string, string> = {
  google_denied: "Google 로그인을 취소했습니다.",
  google_email_unverified: "Google에서 확인되지 않은 이메일이라 로그인할 수 없습니다.",
  google_domain_not_allowed: "허용되지 않은 도메인의 Google 계정입니다. 회사 계정으로 로그인하세요.",
  google_account_mismatch: "이 이메일은 다른 Google 계정에 연결되어 있습니다. 관리자에게 문의하세요.",
  user_inactive: "사용이 중지된 계정입니다. 관리자에게 문의하세요.",
  google_not_configured: "Google 로그인이 설정되지 않았습니다.",
  state_expired: "로그인 시간이 지났습니다. 다시 시도해 주세요.",
};

function GoogleMark() {
  return (
    <svg viewBox="0 0 48 48" className="size-[18px]" aria-hidden>
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2c-2 1.5-4.5 2.4-7.2 2.4-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}

export function LoginPage() {
  const qc = useQueryClient();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const providers = useQuery({ queryKey: ["auth-providers"], queryFn: () => get<{ google: boolean }>("/auth/providers") });

  // Google 콜백이 실패 코드를 붙여 돌려보낸 경우: 안내하고 주소를 정리한다
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("login_error");
    if (code) {
      setError(LOGIN_ERRORS[code] ?? `Google 로그인에 실패했습니다 (${code}).`);
      params.delete("login_error");
      window.history.replaceState(null, "", window.location.pathname + (params.toString() ? `?${params}` : ""));
    }
  }, []);

  const submit = async (e?: FormEvent, override?: { email: string; password: string }) => {
    e?.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = override ?? (mode === "login" ? { email, password } : { email, name, password });
      await post<SessionOut>(mode === "login" || override ? "/auth/login" : "/auth/signup", body);
      // 쿠키가 설정됐으니 내 정보를 다시 읽으면 포탈이 열린다
      await qc.invalidateQueries({ queryKey: ["me"] });
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative grid min-h-screen place-items-center overflow-hidden px-6 py-10">
      <div className="orb left-[-140px] top-[200px] size-[520px] bg-[#cfe0ff]" />
      <div className="orb right-[-160px] top-[-120px] size-[560px] bg-[#e6dcff] [animation-delay:-6s]" />

      <div className="page-in relative z-10 grid w-full max-w-[1040px] overflow-hidden rounded-[32px] bg-white shadow-[0_30px_80px_rgb(0_0_0/0.08),0_0_0_1px_rgb(0_0_0/0.04)] lg:grid-cols-[1fr_440px]">
        <div className="hidden flex-col justify-between bg-[radial-gradient(500px_300px_at_20%_10%,#e3edff,transparent_70%),linear-gradient(160deg,#f7faff,#f5f1ff)] p-10 lg:flex">
          <div className="flex items-center gap-2.5">
            <img src="/favicon.svg" alt="" className="size-[34px] rounded-[10px]" />
            <span>
              <span className="flex items-baseline gap-1.5 text-[20px] leading-[20px] tracking-[-0.045em]">
                <b className="font-extrabold">A2X</b>
                <span className="font-medium text-[#6e6e73]">Portal</span>
              </span>
              <small className="block text-[11.5px] leading-[13px] text-muted-foreground">AI 연계 거버넌스</small>
            </span>
          </div>
          <IsoArt className="mx-auto w-full max-w-[460px]" />
          <p className="text-[26px] leading-tight font-extrabold tracking-[-0.035em]">
            Connect every AI
            <br />
            to everything, <span className="grad-text">safely.</span>
          </p>
        </div>

        <div className="flex flex-col justify-center p-10">
          <h1 className="text-[28px] font-extrabold tracking-[-0.03em]">{mode === "login" ? "로그인" : "가입하기"}</h1>
          <p className="mt-1 text-[14px] text-muted-foreground">
            {mode === "login" ? "A2X 포탈 계정으로 로그인하세요." : "이메일로 바로 가입합니다. 시스템 담당자로 지정되면 담당자 메뉴가 열립니다."}
          </p>

          <form onSubmit={submit} className="mt-6 space-y-3">
            {mode === "signup" && (
              <label className="block space-y-1.5 text-sm">
                <span className="font-medium">이름</span>
                <Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required />
              </label>
            )}
            <label className="block space-y-1.5 text-sm">
              <span className="font-medium">이메일</span>
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
            </label>
            <label className="block space-y-1.5 text-sm">
              <span className="font-medium">비밀번호</span>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} required />
              {mode === "signup" && <span className="text-[12px] text-muted-foreground">8자 이상, 영문과 숫자를 함께</span>}
            </label>
            {error && <p className="rounded-xl bg-[#fdecee] px-3 py-2 text-[13px] text-[#d70015]">{error}</p>}
            <Button type="submit" className="h-11 w-full" disabled={busy}>
              {busy ? <Loader2 className="animate-spin" /> : null}
              {mode === "login" ? "로그인" : "가입하고 시작하기"} {!busy && <ArrowRight />}
            </Button>
          </form>

          {providers.data?.google && (
            <>
              <div className="my-4 flex items-center gap-3 text-[12px] text-muted-foreground">
                <span className="h-px flex-1 bg-black/[0.08]" />또는<span className="h-px flex-1 bg-black/[0.08]" />
              </div>
              {/* 전체 페이지 이동: 백엔드가 Google로 보내고, 돌아오면 세션 쿠키를 붙여 포탈로 보낸다 */}
              <a
                href="/api/v1/auth/google/login"
                className="flex h-11 w-full items-center justify-center gap-2.5 rounded-full bg-white text-[14.5px] font-bold ring-1 ring-black/[0.12] transition hover:bg-[#f5f6f8]"
              >
                <GoogleMark /> Google 계정으로 {mode === "login" ? "로그인" : "가입"}
              </a>
            </>
          )}

          <button type="button" onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(""); }} className="mt-4 text-[13.5px] font-bold text-primary">
            {mode === "login" ? "계정이 없나요? 가입하기" : "이미 계정이 있나요? 로그인"}
          </button>

          {mode === "login" && (
            <div className="mt-8 rounded-2xl bg-[#f5f6f8] p-4">
              <p className="text-[12px] font-bold text-muted-foreground">개발용 샘플 계정 (비밀번호 {DEMO_PW})</p>
              <div className="mt-2 flex flex-col gap-1.5">
                {DEMO.map((d) => (
                  <button
                    key={d.email}
                    type="button"
                    disabled={busy}
                    onClick={() => submit(undefined, { email: d.email, password: DEMO_PW })}
                    className={cn("flex items-center justify-between rounded-xl bg-white px-3 py-2 text-left text-[13px] ring-1 ring-black/[0.06] hover:ring-primary/40")}
                  >
                    <span className="font-medium">{d.label}</span>
                    <span className="font-mono text-[11.5px] text-muted-foreground">{d.email}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
