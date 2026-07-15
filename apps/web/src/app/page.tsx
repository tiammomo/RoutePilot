import Link from "next/link";

import { AuthControls } from "@/features/auth/AuthControls";
import { HomeQuickStart } from "@/features/trip-create/HomeQuickStart";
import { Icons } from "@/shared/ui/Icons";

const inspiration = [
  { city: "京都", kind: "住宿选择", note: "第一次去，住哪里最方便？", mark: "京", variant: "amber" },
  { city: "北京", kind: "轻松出行", note: "带父母如何安排得轻松？", mark: "北", variant: "blue" },
  { city: "大理", kind: "预算判断", note: "两个人玩五天预算多少？", mark: "理", variant: "green" },
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
        <div className="hero-visual" aria-label="RoutePilot 旅行问答预览">
          <div className="hero-map-lines" aria-hidden="true"><span /><span /><span /></div>
          <div className="answer-preview">
            <div className="preview-question">
              <span>你的问题</span>
              <p>第一次去京都，住哪里出行最方便？</p>
            </div>
            <div className="preview-answer">
              <div className="preview-answer-heading"><span><Icons.Spark /> 直接建议</span><small>示例回答</small></div>
              <strong>先按交通便利度筛选住宿区域，再结合预算与每天动线做取舍。</strong>
              <p>RoutePilot 会把结论、理由和仍需核验的信息分开呈现，不用先读完一整篇攻略。</p>
              <div className="preview-facts">
                <span data-tone="lake"><Icons.Map /> 交通便利</span>
                <span data-tone="sun"><Icons.Wallet /> 预算可控</span>
                <span data-tone="green"><Icons.Evidence /> 来源可查</span>
              </div>
            </div>
            <div className="preview-footer">
              <span><i /> 6 条来源 · 刚刚核验</span>
              <strong>可继续追问 <Icons.Arrow /></strong>
            </div>
          </div>
          <div className="floating-card card-evidence"><Icons.Evidence /><span><small>证据状态</small><strong>事实已核验</strong></span><i /></div>
          <div className="floating-card card-budget"><small>下一步</small><strong>一键转成完整行程</strong><span>日期、预算与同行人按需补充</span></div>
        </div>
      </section>

      <section className="inspiration constrained" aria-labelledby="inspiration-title">
        <div className="section-heading"><div><span className="eyebrow">常见问题，一句话开始</span><h2 id="inspiration-title">你现在想解决哪类旅行问题？</h2></div><Link href="/trips">查看我的旅行 <Icons.Arrow /></Link></div>
        <div className="inspiration-grid">
          {inspiration.map((item) => (
            <Link href={`/trips?prompt=${encodeURIComponent(`${item.city}：${item.note}`)}`} className="destination-card" data-variant={item.variant} key={item.city}>
              <div className="destination-art"><span>{item.mark}</span><i /><i /><b /><b /></div>
              <div><small>{item.kind}</small><h3>{item.city}</h3><p>{item.note}</p></div><Icons.Arrow />
            </Link>
          ))}
        </div>
      </section>

    </main>
  );
}
