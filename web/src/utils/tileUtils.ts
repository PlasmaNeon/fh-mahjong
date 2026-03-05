// @ts-nocheck
import { game } from '../proto/game';

// Helper to get SVG filename for a tile
export const getTileSvgName = (tile: game.ITile | { suit: number, value: number }) => {
    let suitChar = '';
    switch (tile.suit) {
        case game.Suit.SUIT_MAN: suitChar = 'm'; break;
        case game.Suit.SUIT_PIN: suitChar = 'p'; break;
        case game.Suit.SUIT_SOU: suitChar = 's'; break;
        case game.Suit.SUIT_JIHAI: suitChar = 'z'; break;
        default: return 'Blank.svg';
    }
    return `${tile.value}${suitChar}.svg`;
};

// Helper for sorting tiles: Man -> Pin -> Sou -> Jihai
export const getSuitOrder = (suit: game.Suit | number) => {
    switch (suit) {
        case game.Suit.SUIT_MAN: return 1;
        case game.Suit.SUIT_PIN: return 2;
        case game.Suit.SUIT_SOU: return 3;
        case game.Suit.SUIT_JIHAI: return 4;
        default: return 5;
    }
};

export const getTileName = (tile: game.ITile | { suit: number, value: number }) => {
    const valueMap = ["", "1", "2", "3", "4", "5", "6", "7", "8", "9"];
    const jihaiMap = ["", "East", "South", "West", "North", "Haku", "Hatsu", "Chun"];

    switch (tile.suit) {
        case game.Suit.SUIT_MAN: return `${valueMap[tile.value]} Man`;
        case game.Suit.SUIT_PIN: return `${valueMap[tile.value]} Pin`;
        case game.Suit.SUIT_SOU: return `${valueMap[tile.value]} Sou`;
        case game.Suit.SUIT_JIHAI: return jihaiMap[tile.value] || "Unknown Jihai";
        default: return "Unknown Tile";
    }
};
