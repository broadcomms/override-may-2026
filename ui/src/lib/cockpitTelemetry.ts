import type { LiveLapStats } from "@/api/types";

export interface DerivedLiveSignal {
  energySpendMj: number;
  socPercent: number;
  netEnergyMj: number;
  balanceLabel: "spending" | "recovering" | "balanced";
  pressureLabel:
    | "Candidate inefficient deploy"
    | "Deployment pressure"
    | "Conserve signal"
    | "Over-harvest watch"
    | "Review pending";
  pressureTone: "accent" | "warning" | "success" | "neutral";
  pressureDetail: string;
  suggestedAction: string;
  fanSummary: string;
  warning: boolean;
}

const BALANCE_MARGIN_MJ = 0.2;

export function truncateSessionId(sessionId: string, max = 18): string {
  return sessionId.length <= max ? sessionId : `${sessionId.slice(0, max - 1)}…`;
}

export function formatTorcsStateShort(state: string | null | undefined): string {
  if (!state) return "idle";
  return state.replace("_", " ");
}

export function describeLapBalance(
  lap: LiveLapStats,
): "energy-positive" | "energy-negative" | "balanced" {
  const net = lap.harvest_mj - lap.deploy_mj;
  if (net > BALANCE_MARGIN_MJ) return "energy-positive";
  if (net < -BALANCE_MARGIN_MJ) return "energy-negative";
  return "balanced";
}

export function deriveLiveSignal(
  latestLap: LiveLapStats | null,
  previousLap: LiveLapStats | null,
): DerivedLiveSignal | null {
  if (!latestLap) return null;

  const socPercent = latestLap.soc_end * 100;
  const energySpendMj = latestLap.deploy_mj - latestLap.harvest_mj;
  const netEnergyMj = latestLap.harvest_mj - latestLap.deploy_mj;
  const previousSocPercent = previousLap ? previousLap.soc_end * 100 : null;
  const socDrop = previousSocPercent == null ? 0 : previousSocPercent - socPercent;

  const balanceLabel =
    energySpendMj > BALANCE_MARGIN_MJ
      ? "spending"
      : energySpendMj < -BALANCE_MARGIN_MJ
      ? "recovering"
      : "balanced";

  if (socPercent <= 35) {
    return {
      energySpendMj,
      socPercent,
      netEnergyMj,
      balanceLabel,
      pressureLabel: "Conserve signal",
      pressureTone: "warning",
      pressureDetail: `SoC closed at ${socPercent.toFixed(0)}% on lap ${latestLap.lap}. Energy reserve is narrowing.`,
      suggestedAction:
        "Suggested action: support a lighter deploy lap next time through and prioritize recovery where traction is stable.",
      fanSummary:
        "The battery reserve is running low. Saving boost for higher-value sections can preserve options later in the stint.",
      warning: true,
    };
  }

  if (
    energySpendMj >= 0.5 &&
    (socPercent <= 72 || socDrop >= 3)
  ) {
    return {
      energySpendMj,
      socPercent,
      netEnergyMj,
      balanceLabel,
      pressureLabel: "Deployment pressure",
      pressureTone: "warning",
      pressureDetail: `Deploy exceeded harvest by ${energySpendMj.toFixed(2)} MJ while SoC closed at ${socPercent.toFixed(0)}%.`,
      suggestedAction:
        "Suggested action: support a conserve-and-recover lap on the next low-ROI section before the battery window tightens further.",
      fanSummary:
        "The car spent more battery than it recovered this lap. That can help now, but it may reduce options later in the run.",
      warning: true,
    };
  }

  if (
    socPercent >= 85 &&
    latestLap.harvest_mj >= 0.7 &&
    latestLap.harvest_mj - latestLap.deploy_mj >= 0.35
  ) {
    return {
      energySpendMj,
      socPercent,
      netEnergyMj,
      balanceLabel,
      pressureLabel: "Over-harvest watch",
      pressureTone: "success",
      pressureDetail: `Harvest stayed high at ${latestLap.harvest_mj.toFixed(2)} MJ with SoC already at ${socPercent.toFixed(0)}%.`,
      suggestedAction:
        "Suggested action: support a slightly more assertive deploy window if pace gain is available; the battery finished the lap well covered.",
      fanSummary:
        "The car recovered plenty of battery this lap and finished with strong charge. That supports a bigger push when the track rewards it.",
      warning: false,
    };
  }

  if (energySpendMj >= 0.3) {
    return {
      energySpendMj,
      socPercent,
      netEnergyMj,
      balanceLabel,
      pressureLabel: "Candidate inefficient deploy",
      pressureTone: "accent",
      pressureDetail: `Deploy led harvest by ${energySpendMj.toFixed(2)} MJ, but the battery still looks stable enough for review rather than escalation.`,
      suggestedAction:
        "Suggested action: support a quick post-lap review of where deploy was spent before repeating the same release pattern.",
      fanSummary:
        "The car used a noticeable chunk of battery here. It may have helped, but the team should check whether that spend paid off.",
      warning: true,
    };
  }

  return {
    energySpendMj,
    socPercent,
    netEnergyMj,
    balanceLabel,
    pressureLabel: "Review pending",
    pressureTone: "neutral",
    pressureDetail: `Harvest and deploy stayed close on lap ${latestLap.lap}; no strong live energy pressure signal is active yet.`,
    suggestedAction:
      "Suggested action: support the current deployment pattern and wait for the next completed lap before escalating strategy changes.",
    fanSummary:
      "Battery use looked balanced this lap, so the team can wait for more evidence before changing strategy.",
    warning: false,
  };
}
