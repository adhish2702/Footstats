// Small inline icons. Decorative by default (aria-hidden); meaning is always
// also given in text next to them.
import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Icon({ size = 16, children, ...rest }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" {...rest}>
      {children}
    </svg>
  );
}

export const UpIcon = (p: IconProps) => <Icon {...p}><path d="M12 5 4 17h16z" fill="currentColor" stroke="none" /></Icon>;
export const DownIcon = (p: IconProps) => <Icon {...p}><path d="m12 19 8-12H4z" fill="currentColor" stroke="none" /></Icon>;
export const LevelIcon = (p: IconProps) => <Icon {...p}><path d="M5 12h14" /></Icon>;
export const AlertIcon = (p: IconProps) => <Icon {...p}><path d="M12 3 2 21h20z" /><path d="M12 10v5M12 18h.01" /></Icon>;
export const SearchIcon = (p: IconProps) => <Icon {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></Icon>;
export const SunIcon = (p: IconProps) => <Icon {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></Icon>;
export const MoonIcon = (p: IconProps) => <Icon {...p}><path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" /></Icon>;
export const PlusIcon = (p: IconProps) => <Icon {...p}><path d="M12 5v14M5 12h14" /></Icon>;
export const CloseIcon = (p: IconProps) => <Icon {...p}><path d="M6 6l12 12M18 6 6 18" /></Icon>;
export const EmptyIcon = (p: IconProps) => <Icon {...p}><rect x="3" y="5" width="18" height="14" rx="1" /><path d="M3 12h18M12 5v14" /><circle cx="12" cy="12" r="2.5" /></Icon>;
export const OfflineIcon = (p: IconProps) => <Icon {...p}><path d="M2 2l20 20M8.5 16.5a5 5 0 0 1 7 0M5 13a10 10 0 0 1 5.2-2.8M19 13a10 10 0 0 0-2.2-1.6M12 20h.01" /></Icon>;
