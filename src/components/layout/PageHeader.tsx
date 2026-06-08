import type { ReactNode } from "react"
import Link from "next/link"
import { ArrowLeft } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface PageHeaderProps {
  title: string
  badge?: ReactNode
  subtitle?: string
  /** Right-side toolbar content: view switchers, refresh, actions */
  children?: ReactNode
  /** Replace default back-to-home link. Set to false to hide. */
  backHref?: string | false
  className?: string
}

function PageHeader({
  title,
  badge,
  subtitle,
  children,
  backHref = "/",
  className,
}: PageHeaderProps) {
  return (
    <header className={cn("border-b border-slate-200 bg-white", className)}>
      <div className="flex min-h-14 flex-col items-stretch justify-between gap-3 px-4 py-3 lg:flex-row lg:items-center lg:px-6">
        <div className="flex min-w-0 items-center gap-3">
          {backHref !== false && (
            <Button variant="ghost" size="icon" asChild className="shrink-0">
              <Link href={backHref} aria-label="返回首页">
                <ArrowLeft className="h-5 w-5" />
              </Link>
            </Button>
          )}
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="truncate text-lg font-semibold tracking-normal text-slate-950">
                {title}
              </h1>
              {badge}
            </div>
            {subtitle && (
              <p className="mt-0.5 truncate text-xs text-slate-500">{subtitle}</p>
            )}
          </div>
        </div>
        {children && (
          <div className="flex flex-wrap items-center gap-2">{children}</div>
        )}
      </div>
    </header>
  )
}

export { PageHeader }
export type { PageHeaderProps }
