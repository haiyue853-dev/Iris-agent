// 集中导出侧边栏用到的所有内联 SVG 图标 (保持原有 path 数据, 只换容器)
// 所有图标接受与 lucide-react 一致的 props: size / strokeWidth / className / ...

import type { SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

const baseProps = (size = 16) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.5,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
});

export const PlusIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}><path d="M12 5v14M5 12h14" /></svg>
);

export const ChatIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
  </svg>
);

export const DocumentIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <path d="M6 3h9l3 3v15H6z" />
    <path d="M15 3v4h4M9 12h6M9 16h4" />
  </svg>
);

export const NewspaperIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-4 0V9" />
    <path d="M18 14h-8" />
    <path d="M15 18h-5" />
    <path d="M10 6h8v4h-8V6z" />
  </svg>
);

export const GridIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <rect x="3" y="3" width="7" height="7" rx="1.5" />
    <rect x="14" y="3" width="7" height="7" rx="1.5" />
    <rect x="3" y="14" width="7" height="7" rx="1.5" />
    <rect x="14" y="14" width="7" height="7" rx="1.5" />
    <path d="M10 6.5h4M6.5 10v4M17.5 10v4M10 17.5h4" />
  </svg>
);

export const HomeIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <path d="M4 20h16" />
    <path d="M6 20V9l6-5 6 5v11" />
    <path d="M9 20v-6h6v6" />
  </svg>
);

export const SkillIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <path d="m12 3 1.4 4.1 4.1 1.4-4.1 1.4L12 14l-1.4-4.1-4.1-1.4 4.1-1.4L12 3z" />
    <path d="m18.5 14 .7 2.3 2.3.7-2.3.7-.7 2.3-.7-2.3-2.3-.7 2.3-.7.7-2.3z" />
    <path d="m5 14 .5 1.5L7 16l-1.5.5L5 18l-.5-1.5L3 16l1.5-.5L5 14z" />
  </svg>
);

export const ClockIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <circle cx="12" cy="12" r="8" />
    <path d="M12 7v5l3 2" />
  </svg>
);

export const DotsIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <circle cx="5" cy="12" r="1" />
    <circle cx="12" cy="12" r="1" />
    <circle cx="19" cy="12" r="1" />
  </svg>
);

export const ChevronRightIcon = ({ size = 14, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest} strokeWidth={1.8}>
    <path d="m9 18 6-6-6-6" />
  </svg>
);

export const ChevronLeftIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest} strokeWidth={1.8}>
    <path d="m15 18-6-6 6-6" />
  </svg>
);

export const ChevronRightSquareIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <rect x="3" y="3" width="18" height="18" rx="3" />
    <path d="M9 3v18" />
    <path d="m13 9 3 3-3 3" />
  </svg>
);

export const PanelLeftIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <rect x="3" y="3" width="18" height="18" rx="3" />
    <path d="M9 3v18" />
  </svg>
);

export const TrashIcon = ({ size = 14, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
  </svg>
);

export const SettingsIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);

export const ListIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5" />
  </svg>
);

export const BrainIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <path d="M12 3a3 3 0 0 0-3 3 3 3 0 0 0-2.4 5A3 3 0 0 0 9 16a3 3 0 0 0 6 0 3 3 0 0 0 2.4-5A3 3 0 0 0 15 6a3 3 0 0 0-3-3z" />
    <path d="M12 8v4l2.5 1.5" />
  </svg>
);

export const BookIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
  </svg>
);

export const ShieldCheckIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <path d="M12 3l7 4v5c0 4.4-3 7.6-7 9-4-1.4-7-4.6-7-9V7z" />
    <path d="M9 12l2 2 4-4" />
  </svg>
);

export const ServerIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <path d="M8 3v4m8-4v4M6 7h12v14H6zM9 11h6m-6 4h6" />
  </svg>
);

export const ToolIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <path d="m14.7 6.3 3-3a4 4 0 0 0-5 5l-8.4 8.4a2 2 0 1 0 2.8 2.8l8.4-8.4a4 4 0 0 0 5-5l-3 3z" />
  </svg>
);
export const ChannelsIcon = ({ size = 16, ...rest }: IconProps) => (
  <svg {...baseProps(size)} {...rest}>
    <circle cx="6" cy="12" r="2.5" />
    <circle cx="18" cy="6" r="2.5" />
    <circle cx="18" cy="18" r="2.5" />
    <path d="m8.2 10.8 7.5-3.6M8.2 13.2l7.5 3.6" />
  </svg>
);
