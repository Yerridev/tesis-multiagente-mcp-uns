import type { SVGProps } from 'react';

export type IconProps = SVGProps<SVGSVGElement>;

function Icon({ children, ...rest }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={20}
      height={20}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const IconMenu = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </Icon>
);

export const IconClose = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Icon>
);

export const IconGrid = (p: IconProps) => (
  <Icon {...p}>
    <rect x="4" y="4" width="7" height="7" rx="1.5" />
    <rect x="13" y="4" width="7" height="7" rx="1.5" />
    <rect x="4" y="13" width="7" height="7" rx="1.5" />
    <rect x="13" y="13" width="7" height="7" rx="1.5" />
  </Icon>
);

export const IconTank = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 4h14v13a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3z" />
    <path d="M5 12h14" />
    <path d="M9 4v3M15 4v3" />
  </Icon>
);

export const IconHistory = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="8" />
    <path d="M12 7.5V12l3 2" />
  </Icon>
);

export const IconAgent = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3.5l1.7 4.3 4.3 1.7-4.3 1.7L12 15.5l-1.7-4.3L6 9.5l4.3-1.7z" />
    <path d="M18 15.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" />
  </Icon>
);

export const IconFlow = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 8.5c2-2 4-2 6 0s4 2 6 0 4-2 6 0" />
    <path d="M3 14.5c2-2 4-2 6 0s4 2 6 0 4-2 6 0" />
  </Icon>
);

export const IconGauge = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 17a8.5 8.5 0 1 1 16 0" />
    <path d="M12 17l4.5-5" />
    <circle cx="12" cy="17" r="1.4" />
  </Icon>
);

export const IconPump = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="11" cy="12" r="6" />
    <path d="M11 6V3.5M17 12h3.5M11 18v2.5M5 12H2.5" />
    <path d="M11 9.5v5l3.5-2.5z" />
  </Icon>
);

export const IconValve = (p: IconProps) => (
  <Icon {...p}>
    <path d="M7 8l5 4-5 4z" />
    <path d="M17 8l-5 4 5 4z" />
    <path d="M4 12h3M17 12h3M12 6v4" />
  </Icon>
);

export const IconPlc = (p: IconProps) => (
  <Icon {...p}>
    <rect x="6" y="6" width="12" height="12" rx="2" />
    <path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3" />
  </Icon>
);

export const IconSignal = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4.5 11.5a10.5 10.5 0 0 1 15 0" />
    <path d="M8 15a6 6 0 0 1 8 0" />
    <circle cx="12" cy="18.5" r="1.3" />
  </Icon>
);

export const IconDatabase = (p: IconProps) => (
  <Icon {...p}>
    <ellipse cx="12" cy="6.5" rx="7" ry="3" />
    <path d="M5 6.5v11c0 1.7 3.1 3 7 3s7-1.3 7-3v-11" />
    <path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3" />
  </Icon>
);

export const IconAlert = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 4.5l8.5 15H3.5z" />
    <path d="M12 10v4M12 17h.01" />
  </Icon>
);

export const IconArrow = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 12h13M13 6.5l5.5 5.5L13 17.5" />
  </Icon>
);

export const IconRefresh = (p: IconProps) => (
  <Icon {...p}>
    <path d="M20 12a8 8 0 1 1-2.4-5.7" />
    <path d="M20 4v4.5h-4.5" />
  </Icon>
);

export const IconLock = (p: IconProps) => (
  <Icon {...p}>
    <rect x="5" y="10.5" width="14" height="9.5" rx="2" />
    <path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" />
  </Icon>
);

export const IconUser = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="8.5" r="3.5" />
    <path d="M5 20c1.2-3.4 3.8-5 7-5s5.8 1.6 7 5" />
  </Icon>
);

export const IconClock = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="8" />
    <path d="M12 7.5V12l3 2" />
  </Icon>
);

export const IconMonitor = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 13h4l3 6 4-14 3 8h4" />
  </Icon>
);

export const IconServer = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3.5" y="4" width="17" height="6" rx="2" />
    <rect x="3.5" y="14" width="17" height="6" rx="2" />
    <path d="M7 7h.01M7 17h.01" />
  </Icon>
);

export const IconTopology = (p: IconProps) => (
  <Icon {...p}>
    <rect x="9" y="3" width="6" height="5" rx="1.5" />
    <rect x="3" y="16" width="6" height="5" rx="1.5" />
    <rect x="15" y="16" width="6" height="5" rx="1.5" />
    <path d="M12 8v4M6 16v-4h12v4" />
  </Icon>
);

export const IconBranch = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="6" cy="5.5" r="2.5" />
    <circle cx="6" cy="18.5" r="2.5" />
    <circle cx="18" cy="10.5" r="2.5" />
    <path d="M6 8v8M8.5 5.5H13a2.5 2.5 0 0 1 2.5 2.5v.5M8.5 18.5H13" />
  </Icon>
);

export const IconLayers = (p: IconProps) => (
  <Icon {...p}>
    <rect x="4" y="4" width="7" height="7" rx="1.5" />
    <rect x="13" y="4" width="7" height="7" rx="1.5" />
    <rect x="4" y="13" width="7" height="7" rx="1.5" />
    <path d="M14 16.5h5M16.5 14v5" />
  </Icon>
);

export const IconThermometer = (p: IconProps) => (
  <Icon {...p}>
    <path d="M14 14.8V5.5a2 2 0 1 0-4 0v9.3a4 4 0 1 0 4 0z" />
    <path d="M12 9.5v6" />
  </Icon>
);

export const IconChart = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 4v16h16" />
    <path d="M8 16v-4M12 16V8M16 16v-6" />
  </Icon>
);

export const IconSettings = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 7h9M17 7h3M4 17h3M11 17h9" />
    <circle cx="15" cy="7" r="2.2" />
    <circle cx="9" cy="17" r="2.2" />
  </Icon>
);

export const IconPanel = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
    <path d="M7.5 9v6M12 9v3M16.5 9v6" />
  </Icon>
);

export const IconBarChart = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 20h16" />
    <rect x="5.5" y="11" width="3.5" height="6" rx="1" />
    <rect x="10.5" y="6.5" width="3.5" height="10.5" rx="1" />
    <rect x="15.5" y="9" width="3.5" height="8" rx="1" />
  </Icon>
);

export const IconInbox = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 13.5V6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7" />
    <path d="M4 13.5h4l1.5 2.5h5L16 13.5h4v4A2.5 2.5 0 0 1 17.5 20h-11A2.5 2.5 0 0 1 4 17.5z" />
  </Icon>
);

export const IconPlay = (p: IconProps) => (
  <Icon {...p}>
    <path d="M8 5.5l10 6.5-10 6.5z" />
  </Icon>
);

export const IconPause = (p: IconProps) => (
  <Icon {...p}>
    <path d="M9 5.5v13M15 5.5v13" />
  </Icon>
);
