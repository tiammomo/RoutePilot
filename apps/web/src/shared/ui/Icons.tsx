import type { SVGProps } from "react";

function IconBase({ children, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      {children}
    </svg>
  );
}

export const Icons = {
  Arrow: (props: SVGProps<SVGSVGElement>) => <IconBase {...props}><path d="m5 12 14 0m-5-5 5 5-5 5" /></IconBase>,
  Calendar: (props: SVGProps<SVGSVGElement>) => <IconBase {...props}><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M8 3v4m8-4v4M3 10h18" /></IconBase>,
  Check: (props: SVGProps<SVGSVGElement>) => <IconBase {...props}><path d="m5 12 4 4L19 6" /></IconBase>,
  Compass: (props: SVGProps<SVGSVGElement>) => <IconBase {...props}><circle cx="12" cy="12" r="9" /><path d="m15.5 8.5-2 5-5 2 2-5 5-2Z" /></IconBase>,
  Evidence: (props: SVGProps<SVGSVGElement>) => <IconBase {...props}><path d="M6 3h9l4 4v14H6z" /><path d="M14 3v5h5M9 12h6m-6 4h5" /></IconBase>,
  Map: (props: SVGProps<SVGSVGElement>) => <IconBase {...props}><path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3zM9 3v15m6-12v15" /></IconBase>,
  Plus: (props: SVGProps<SVGSVGElement>) => <IconBase {...props}><path d="M12 5v14M5 12h14" /></IconBase>,
  Route: (props: SVGProps<SVGSVGElement>) => <IconBase {...props}><circle cx="6" cy="18" r="2" /><circle cx="18" cy="6" r="2" /><path d="M8 18h3a3 3 0 0 0 3-3V9a3 3 0 0 1 3-3" /></IconBase>,
  Search: (props: SVGProps<SVGSVGElement>) => <IconBase {...props}><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></IconBase>,
  Spark: (props: SVGProps<SVGSVGElement>) => <IconBase {...props}><path d="m12 3 1.3 4.2L17 9l-3.7 1.8L12 15l-1.3-4.2L7 9l3.7-1.8L12 3ZM5 14l.8 2.2L8 17l-2.2.8L5 20l-.8-2.2L2 17l2.2-.8L5 14Zm14-2 .7 2.3L22 15l-2.3.7L19 18l-.7-2.3L16 15l2.3-.7L19 12Z" /></IconBase>,
  Wallet: (props: SVGProps<SVGSVGElement>) => <IconBase {...props}><path d="M4 6h14a2 2 0 0 1 2 2v11H4a2 2 0 0 1-2-2V6a3 3 0 0 1 3-3h12" /><path d="M16 11h5v4h-5a2 2 0 0 1 0-4Z" /></IconBase>,
  Warning: (props: SVGProps<SVGSVGElement>) => <IconBase {...props}><path d="M12 3 2.5 20h19L12 3Z" /><path d="M12 9v5m0 3h.01" /></IconBase>,
};
