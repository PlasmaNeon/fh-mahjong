import { describe, expect, it } from 'vitest';
import { parseRLAgents, rlSeatLabel } from './rlAgents';

describe('parseRLAgents', () => {
    it('keeps well-formed agents in server order', () => {
        const agents = parseRLAgents({ rlAgents: [
            { id: 'v4', label: 'AI v4', available: true },
            { id: 'v3', label: 'AI v3', available: false },
        ] });
        expect(agents).toEqual([
            { id: 'v4', label: 'AI v4', available: true },
            { id: 'v3', label: 'AI v3', available: false },
        ]);
    });
    it('drops malformed entries and tolerates a missing list', () => {
        expect(parseRLAgents({ rlAgents: [{ id: 'v4' }, null, { id: 'v2', label: 'AI v2', available: 'yes' }] }))
            .toEqual([{ id: 'v2', label: 'AI v2', available: false }]);
        expect(parseRLAgents({ rlAgentAvailable: true })).toEqual([]);
        expect(parseRLAgents(null)).toEqual([]);
    });
});

describe('rlSeatLabel', () => {
    const agents = [
        { id: 'v4', label: 'AI v4', available: false },
        { id: 'v3', label: 'AI v3', available: false },
    ];
    it('labels a seat by its agent, an empty agent by the default', () => {
        expect(rlSeatLabel('v3', agents)).toBe('AI v3');
        expect(rlSeatLabel('', agents)).toBe('AI v4');
        expect(rlSeatLabel(null, agents)).toBe('AI v4');
    });
    it('returns null when the agent is unknown or no list is loaded yet', () => {
        expect(rlSeatLabel('v9', agents)).toBeNull();
        expect(rlSeatLabel('v3', [])).toBeNull();
    });
});
