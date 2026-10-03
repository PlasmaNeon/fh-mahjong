# Fenghua Mahjong Rules & Technical Implementation

## 0. Tile Notation & Terminology

### Suit Names
| Suit | Chinese | Short | Tiles |
|------|---------|-------|-------|
| man (Characters) | 万子 | `m` | 1m–9m |
| pin (Dots) | 筒子 | `p` | 1p–9p |
| sou (Bamboo) | 索子 | `s` | 1s–9s |
| jihai (Honors) | 字牌 | `z` | 1z–7z |

### Jihai Values
| Value | Wind/Dragon | Chinese |
|-------|-------------|---------|
| 1z | East | 東 |
| 2z | South | 南 |
| 3z | West | 西 |
| 4z | North | 北 |
| 5z | Haku (White) | 白 |
| 6z | Hatsu (Green) | 発 |
| 7z | Chun (Red) | 中 |

### Meld Terms
| Term | Chinese | Meaning |
|------|---------|---------|
| chii | 吃 | Sequence of 3 consecutive tiles of the same suit |
| pon | 碰 | Triplet of 3 identical tiles |
| kan | 杠 | Quad of 4 identical tiles |

### Tile Notation Examples
- Hand: `1m2m3m 4p5p6p 7s8s9s 1z1z1z 2z` (waiting on 2z)
- Meld: `chii(2s3s4s)`, `pon(1z)`, `kan(5z)`
- Wild tile: `9s` means all copies of 9-sou are wild this round

### Proto Enum Mapping
| Proto Constant | Terminology |
|----------------|-------------|
| `SUIT_SOU` = 1 | sou |
| `SUIT_PIN` = 2 | pin |
| `SUIT_MAN` = 3 | man |
| `SUIT_JIHAI` = 4 | jihai |
| `SUIT_FLOWER` = 5 | flower |

---

## 1. Overview
The Fenghua (Zhejiang) Mahjong rules feature a rich and complex point (S) scoring system primarily centered around **Wild Tiles**, specific **Bonus/Penalty liabilities**, and a massive list of **Special Patterns** (Independence, Loner, Seven Pairs).

## 2. Core Differences from Standard Rules
1. **Tiles**: Uses the full 136 standard tiles, plus 8 Flower tiles (Seasons/Flowers). Total 144.
2. **Wild Tiles (搭)**: The game features "Wild Tiles" (often rolled via a dice or flipped tile at the start of the round). **Wild tiles are selected in each game randomly.** 
   - If the indicator is a standard tile, the other **3 copies** of that exact tile type circulating in play act as wilds.
   - If the indicator is a Flower tile, the other **3 flowers in its category** (Seasons 1-4 or Plants 5-8) act as wilds. These matching wild flowers bypass auto-reveal rules and are kept in the player's closed hand.
   The rules differentiate heavily based on whether a hand has 0, 1, 2, or 3 wild tiles, or if the wild tiles are "tamed" (used for their natural face value).
3. **Winning Minimum**: A win by claiming a discard (Ron) requires a minimum of **4 points**. Winning by drawing (Tsumo) has no strict minimum, but awards 1 base point.
4. **Highest-Scoring Pattern**: When a hand qualifies for multiple winning patterns simultaneously (e.g., a hand that is both a valid Seven Pairs and a valid Standard hand), the engine always scores it by the pattern that yields the **highest total points**. No points are lost by fitting more than one pattern.
5. **Multiplier Payout**:
   - Draw (Tsumo): All 3 losers pay (Score x 2).
   - Steal (Ron): The discarder pays (Score x 2). The other two losers pay (Score x 1).

## 3. Tile Array Structure and Drawing Mechanics
Fenghua Mahjong perfectly simulates a physical, two-tiered Mahjong wall. The starting 144 tiles are arranged mathematically such that adjacent array indices form vertical 2-tile stacks:
1. **Front Wall Draws:** Standard draws start from the front (index 0). Index 0 represents the top tile of the 1st stack, and Index 1 represents the bottom tile of the 1st stack.
2. **Dice Roll & Wangpai (Dead Wall):** At the start of each round, two dice are rolled. The sum (2-12) determines how many stacks from the end of the wall form the **wangpai** (dead wall). Normal draws cannot enter this zone.
3. **Wild Indicator:** The top tile of the **innermost wangpai stack** (closest to the live wall) is revealed face-up as the wild indicator. It is never drawn by anyone.
4. **Dead Wall (Back) Draws:** For a Kong or Flower replacement, players draw from the tail of the wall going backward. Back-draws always take the **top tile** of the last available stack first, then the **bottom tile**, skipping the wild indicator. If many Kongs occur and all wangpai tiles are consumed, Kong draws can continue — all tiles in the wall may be used.
5. **Haitei (Last Tile):** The tile physically under the wild indicator is the haitei tile. When normal draws are exhausted, the active player may choose to **accept or refuse** the haitei tile (before seeing it). If accepted: can only Tsumo or Discard; other players can only Ron (no Chii/Pon/Kan). If refused: ryuukyoku. If the haitei tile was already consumed by a Kong draw, the game is ryuukyoku when normal draws exhaust.

## 4. Complete Scoring Reference (from official-rules.md)

### Base & Universal Bonuses
- **Base Point (坐台)**: +1 (Always awarded on all wins).
- **Win by Own Tile (自摸)**: +1.
- **Common Win (朋胡)**: +1 (Four runs and a pair of eyes — only if no higher pattern applies).

### Wild Tile Bonuses
- **No Wild Tiles (无搭)**: +1.
- **One Wild Tile (一搭)**: +1.
- **Two Wild Tiles (二搭)**: +2.
- **Three Normal Wild Tiles (普通三百搭)**: +150.
- **Three Flower Wild Tiles (三花三百搭)**: +300 (When the wild tile type is a flower tile).
- **Tame Wild Tiles (还搭)**: +1 (All wild tiles used at face value).

### Wind & Dragon Pung Bonuses
- **Dragon Pung (中发白碰出)**: +1 each (Pung of Haku 5z, Hatsu 6z, or Chun 7z).
- **Pung of Seat Wind (位风)**: +1.
- **Pung of Prevailing Wind (圈风)**: +1.
- **Pung of Right Wind (正风)**: +2 (When seat wind and prevailing wind coincide).
- Seat winds follow turn order from the dealer: dealer East, next South, then West, then North. The prevailing wind is East for every hand (a chongci match is played entirely in the East round), so an East pung scores Right Wind (+2) for the dealer and Prevailing Wind (+1) for anyone else.

### Wait Pattern Bonuses
- **Single Call (边，嵌，单吊)**: +1 (Gap, edge, or single eye wait).
- **Pair Call (对倒)**: +1 (Two pairs calling for one to become a pung).

### Independence Variants (14 unique disconnected tiles, no melds)
All bonuses are additive on top of the base. Multiple bonuses can combine.
- **Independence (大大胡)**: +50 (base — always awarded for any independence hand).
- **Closed Seven Stars (暗七星)**: +100 (all 7 honors already in hand; the winning tile, self-drawn or claimed, is not an honor). Stacks: 50+100=150.
- **Open Seven Stars (明七星)**: +50 (the winning tile, self-drawn or claimed, is the 7th honor; an unknown winning tile scores open). Stacks: 50+50=100.
  - Seven Stars is pure: a wild counts only as its own face, so an honor-faced wild is that honor and a suit-faced wild never stands in for one.
- **Independence Without a Suit (缺色)**: +100 (the winning hand's natural tiles lack one of man/pin/sou; wilds never count toward a suit, whatever their face). It needs at least one wild: two suits hold at most 3+3 Independence tiles, plus 7 honors, which is 13. Stacks with Seven Stars: e.g. 50+100(closed)+100=250.

### Seven Pairs Variants
- **Straight Seven Pairs (无搭)**: 150 (No wild tiles).
- **Wild Seven Pairs (有搭)**: 50 (With wild tiles).
- **Closed Bomb in Seven Pairs (暗炸)**: +100 (4 identical tiles, none claimed, not wild).
- **Open Bomb in Seven Pairs (明炸)**: +50 (4 identical tiles, one claimed for win, not wild).

### All Pung Variants (4 pungs/kongs + 1 pair)
- **Straight All Pung (无搭)**: 100.
- **Wild All Pung (有搭)**: 50.

### Loner Variants (4 open melds + 1 tile in hand)
- **Straight Loner (大吊车无搭)**: 100.
- **Wild Loner (大吊车有搭)**: 50.

### Suit Patterns
- **Mixed One Suit (混一色)**: 70 (One suit + honors).
- **Pure One Suit (清一色)**: 150 (One suit only).

### Honor Patterns
- **Uncompleted All Honors (乱老头)**: 400 (All tiles are honors, no standard structure required).
- **Completed All Honors (清老头)**: 800 (All honors forming a valid standard hand).

### Flower Patterns
- **Own Flower (花)**: +2 (Melded flower matching player's seat wind position). Both groups map onto the seats: 春/梅 East, 夏/兰 South, 秋/菊 West, 冬/竹 North — so a plant flower scores exactly like the matching season.
- **Four Flowers (四花)**: 150 (A COMPLETE group of one kind — 春夏秋冬 or 梅兰菊竹). Any four flowers spanning both groups do not qualify.
- **Uncompleted Eight Flowers (八花直胡)**: 400 (Win by 8 melded flowers alone).
- **Completed Eight Flowers (八花搓胡)**: 800 (8 melded flowers + completing a normal winning hand).

### Kong Bonuses
- **Budding Direct Kong (直杠不开花)**: 50 (Open kong, not winning by supplement tile).
- **Blooming Direct Kong (直杠开花)**: 100 (Open kong, winning by supplement tile).
- **Budding Closed Kong (暗杠不开花)**: 100 (Closed kong, not winning by supplement tile).
- **Blooming Closed Kong (暗杠开花)**: 150 (Closed kong, winning by supplement tile).
- **Budding Risky Kong (风险杠不开花)**: 100 (Filling open kong, not winning by supplement).
- **Blooming Risky Kong (风险杠开花)**: 200 (Filling open kong, winning by supplement).
- **Blooming Flower Kong (花杠杠开)**: 50 (Reveal a flower tile, draw a replacement from the dead wall, and win (tsumo) on that replacement tile. Only applies to tsumo — cleared if the player discards instead).

### Special (No Extra Points)
- **Heavenly Win (天胡)**: Banker wins on initial draw. Celebration only.
- **Earthly Win (地胡)**: Non-banker wins on first discard. Celebration only.
- **Robbing a Kong (拉杠)**: No extra points; scored as own-tile win, robbed player is liable.
- **Win by Bottom Tile (海底捞月)**: No extra points; discarder is liable.

## 5. Liabilities (Exceptions)
- If Player A discards 4 tiles that are all claimed (open run/pung/kong) by Player B, and B wins, A pays for the *entire* table.
- If Player A discards 3 tiles claimed by B, and B wins with Pure One Suit, Mixed One Suit, or All Pung, A is liable.
- **Robbing a Kong**: scored as an own-tile (Tsumo) win; the player whose kong was robbed pays everything.
- **Claimed Bottom Tile**: the player whose bottom tile was claimed for a win is liable.

---

## 6. Go Implementation (`internal/rules/fh.go`)

- `EvaluateHand` scores every pattern above through a staged pipeline over three exclusive routes (Independence, Seven Pairs, Standard); the highest-scoring route wins. Stage order and helpers are in `internal/rules/CLAUDE.md`.
- Wild counting, tame-wild detection, wait-pattern bonuses, flower and kong bonuses, and the 4-point Ron minimum are enforced there. Kong bonus context comes from `PlayerState.has_*_kong` flags set by the game loop.
- `CalculatePayouts` implements the base multipliers only: Tsumo → each loser pays S×2; Ron → discarder S×2, the other two S×1.
- **Not implemented:** the liabilities in §5 and robbing a kong. `PlayerAction.is_robbing_kong` / `is_bottom_tile` exist in the proto but nothing reads them.

## 7. Key Differences from Riichi (Japanese / Tenhou) Mahjong

The engine reproduces the Tenhou wall shuffle (MT19937), but Fenghua has none of these Riichi concepts:

1. **No Riichi declarations.**
2. **No red fives (aka dora).** `Tile.is_red` exists in the proto and is unused.
3. **No honba** (repeat-hand bonus sticks).
4. **No kita** (3-player north peeking).
5. **No furiten.** A player may win on any discard that meets the 4-point Ron minimum, even one they discarded earlier.
6. **No dora indicators.** The flipped indicator makes the other 3 copies of *that exact tile* wild.
7. **Prevailing wind, not round wind.** The proto field is `prevailing_wind` (圈风).
