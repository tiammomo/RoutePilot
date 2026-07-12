import Link from "next/link";

import { AuthControls } from "@/features/auth/AuthControls";
import { HomeQuickStart } from "@/features/trip-create/HomeQuickStart";
import { Icons } from "@/shared/ui/Icons";

const inspiration = [
  { city: "京都", note: "第一次去，住哪里最方便？", mark: "京", variant: "amber" },
  { city: "北京", note: "带父母如何安排得轻松？", mark: "北", variant: "blue" },
  { city: "大理", note: "两个人玩五天预算多少？", mark: "理", variant: "green" },
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
          <Link href="/" aria-current="page">问助手</Link>
          <Link href="/trips">我的旅行</Link>
        </nav>
        <div className="header-account"><AuthControls compact /><Link className="header-cta" href="/trips">问旅行助手 <Icons.Arrow /></Link></div>
      </header>

      <section className="landing-hero constrained">
        <div className="hero-copy">
          <span className="eyebrow"><span /> 你的旅行问答助手</span>
          <h1>说出旅行难题，<br /><em>马上得到可执行的答案。</em></h1>
          <p>不用先整理攻略，也不用先创建复杂项目。告诉 RoutePilot 你想去哪里、和谁去或正在纠结什么，多个专业 Agent 会协作研究、规划与核验。</p>
          <HomeQuickStart />
          <div className="hero-trust"><span><Icons.Check /> 关键事实有来源</span><span><Icons.Check /> 只追问必要信息</span><span><Icons.Check /> 方案可继续修改</span></div>
        </div>
        <div className="hero-visual" aria-label="RoutePilot 行程工作台预览">
          <div className="hero-map-lines" aria-hidden="true"><span /><span /><span /></div>
          <div className="floating-card card-day">
            <span className="mini-label">DAY 01 · KYOTO</span>
            <strong>第一次去京都，怎么排？</strong>
            <div className="mini-stop"><i>09:00</i><span /><b>清水寺</b></div>
            <div className="mini-stop"><i>11:30</i><span /><b>祇园小巷</b></div>
            <div className="mini-stop"><i>14:00</i><span /><b>哲学之道</b></div>
          </div>
          <div className="floating-card card-evidence"><Icons.Evidence /><span><small>开放与营业信息</small><strong>刚刚核验</strong></span><i /></div>
          <div className="floating-card card-budget"><small>两人预算是否够用？</small><strong>¥ 8,600 – 9,900</strong><span>已预留 12% 机动空间</span></div>
          <div className="hero-stamp"><Icons.Compass /><span>答案不止能看<br /><strong>还能继续追问和调整</strong></span></div>
        </div>
      </section>

      <section className="inspiration constrained" aria-labelledby="inspiration-title">
        <div className="section-heading"><div><span className="eyebrow">常见问题，一句话开始</span><h2 id="inspiration-title">你现在想解决哪类旅行问题？</h2></div><Link href="/trips">查看我的旅行 <Icons.Arrow /></Link></div>
        <div className="inspiration-grid">
          {inspiration.map((item) => (
            <Link href={`/trips?prompt=${encodeURIComponent(`${item.city}：${item.note}`)}`} className="destination-card" data-variant={item.variant} key={item.city}>
              <div className="destination-art"><span>{item.mark}</span><i /><i /></div>
              <div><h3>{item.city}</h3><p>{item.note}</p></div><Icons.Arrow />
            </Link>
          ))}
        </div>
      </section>

    </main>
  );
}
