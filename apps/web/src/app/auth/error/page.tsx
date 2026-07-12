import Link from "next/link";

import { Icons } from "@/shared/ui/Icons";

export default function AuthenticationErrorPage() {
  return (
    <main className="workspace-gate">
      <Link href="/" className="brand">
        <span className="brand-mark"><Icons.Route /></span><span>RoutePilot</span>
      </Link>
      <span className="empty-icon">!</span>
      <h1>登录没有完成</h1>
      <p>身份服务暂时无法确认本次登录。请重新开始；我们不会保留失败响应中的凭据或错误详情。</p>
      <a className="primary-button" href="/api/auth/login">重新登录</a>
      <Link href="/">返回首页</Link>
    </main>
  );
}
