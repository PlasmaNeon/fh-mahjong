// RL agents a private-room host can seat, as listed by GET /api/v1/config
// (server order: the first is the default agent).
export interface RLAgentInfo {
    id: string;
    label: string;
    available: boolean;
}

export function parseRLAgents(config: unknown): RLAgentInfo[] {
    const list = (config as { rlAgents?: unknown } | null)?.rlAgents;
    if (!Array.isArray(list)) return [];
    return list.flatMap((entry): RLAgentInfo[] => {
        if (!entry || typeof entry !== 'object') return [];
        const { id, label, available } = entry as Record<string, unknown>;
        if (typeof id !== 'string' || !id || typeof label !== 'string' || !label) return [];
        return [{ id, label, available: available === true }];
    });
}

// The label for an RL seat: its agent's, the default agent's for a seat with
// no agent id, or null when the agent list does not (yet) name it.
export function rlSeatLabel(rlAgent: string | null | undefined, agents: RLAgentInfo[]): string | null {
    if (agents.length === 0) return null;
    if (!rlAgent) return agents[0].label;
    return agents.find(a => a.id === rlAgent)?.label ?? null;
}
