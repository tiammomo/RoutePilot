import Link from "next/link";

import { AuthControls } from "@/features/auth/AuthControls";
import { Icons } from "@/shared/ui/Icons";

const inspiration = [
  { city: "京都", note: "红叶季 · 慢节奏", mark: "京", variant: "amber" },
  { city: "北京", note: "古建与胡同 · 2–4 天", mark: "北", variant: "blue" },
  { city: "大理", note: "山海与村落 · 松弛", mark: "理", variant: "green" },
];

export default function HomePage() {
  return (
    <main className="landing-page">
      <header className="site-header constrained">
        <Link href="/" className="brand" aria-label="RoutePilot 首页">
          <span className="brand-mark"><Icons.Route /></span>
          <span>RoutePilot</span>
        </Link>
        <nav aria-label="主导航">
          <Link href="/" aria-current="page">发现</Link>
          <Link href="/trips">我的旅行</Link>
        </nav>
        <div className="header-account"><AuthControls compact /><Link className="header-cta" href="/trips">开始规划 <Icons.Arrow /></Link></div>
      </header>

      <section className="landing-hero constrained">
        <div className="hero-copy">
          <span className="eyebrow"><span /> ARTIFACT-FIRST TRAVEL</span>
          <h1>少一点攻略焦虑，<br /><em>多一点确定的出发。</em></h1>
          <p>RoutePilot 让专业 Agent 协作研究、规划与验证；你看到的是一份可编辑、可追溯、可恢复的旅行方案。</p>
          <div className="hero-actions">
            <Link className="primary-button large" href="/trips">创建一段旅行 <Icons.Arrow /></Link>
            <a className="secondary-button large" href="#how-it-works">看看如何工作</a>
          </div>
          <div className="hero-trust"><span><Icons.Check /> 关键事实有来源</span><span><Icons.Check /> 硬约束确定性校验</span><span><Icons.Check /> 断线可恢复</span></div>
        </div>
        <div className="hero-visual" aria-label="RoutePilot 行程工作台预览">
          <div className="hero-map-lines" aria-hidden="true"><span /><span /><span /></div>
          <div className="floating-card card-day">
            <span className="mini-label">DAY 01 · KYOTO</span>
            <strong>清晨的东山与寺院</strong>
            <div className="mini-stop"><i>09:00</i><span /><b>清水寺</b></div>
            <div className="mini-stop"><i>11:30</i><span /><b>祇园小巷</b></div>
            <div className="mini-stop"><i>14:00</i><span /><b>哲学之道</b></div>
          </div>
          <div className="floating-card card-evidence"><Icons.Evidence /><span><small>证据新鲜度</small><strong>刚刚验证</strong></span><i /></div>
          <div className="floating-card card-budget"><small>预计预算</small><strong>¥ 8,600 – 9,900</strong><span>含 12% 机动空间</span></div>
          <div className="hero-stamp"><Icons.Compass /><span>计划不是答案文本<br /><strong>是可编辑的旅行资产</strong></span></div>
        </div>
      </section>

      <section className="inspiration constrained" aria-labelledby="inspiration-title">
        <div className="section-heading"><div><span className="eyebrow">START WITH A FEELING</span><h2 id="inspiration-title">你想去哪里？</h2></div><Link href="/trips">查看我的旅行 <Icons.Arrow /></Link></div>
        <div className="inspiration-grid">
          {inspiration.map((item) => (
            <Link href="/trips" className="destination-card" data-variant={item.variant} key={item.city}>
              <div className="destination-art"><span>{item.mark}</span><i /><i /></div>
              <div><h3>{item.city}</h3><p>{item.note}</p></div><Icons.Arrow />
            </Link>
          ))}
        </div>
      </section>

      <section className="how-it-works" id="how-it-works">
        <div className="constrained">
          <span className="eyebrow">ONE WORKSPACE, CLEAR DECISIONS</span>
          <h2>从一句想法，到一份能出发的计划。</h2>
          <div className="principle-grid">
            <article><span>01</span><Icons.Spark /><h3>说出你的真实偏好</h3><p>日期、预算、同行人和必须保留的地点会成为可见约束。</p></article>
            <article><span>02</span><Icons.Evidence /><h3>Agent 带着证据协作</h3><p>Research、Planner 与 Verifier 分工，实时事实不由模型猜测。</p></article>
            <article><span>03</span><Icons.Route /><h3>直接编辑正式方案</h3><p>候选与正式状态清晰分开，局部修改不必重写整篇攻略。</p></article>
          </div>
        </div>
      </section>
    </main>
  );
}
