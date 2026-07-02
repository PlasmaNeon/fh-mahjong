import * as $protobuf from "protobufjs";
import Long = require("long");
/** Namespace game. */
export namespace game {

    /** Suit enum. */
    enum Suit {
        SUIT_UNKNOWN = 0,
        SUIT_SOU = 1,
        SUIT_PIN = 2,
        SUIT_MAN = 3,
        SUIT_JIHAI = 4,
        SUIT_FLOWER = 5
    }

    /** Properties of a Tile. */
    interface ITile {

        /** Tile id */
        id?: (number|undefined);

        /** Tile suit */
        suit?: (game.Suit|undefined);

        /** Tile value */
        value?: (number|undefined);
    }

    /** Represents a Tile. */
    class Tile implements ITile {

        /**
         * Constructs a new Tile.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.ITile);

        /** Tile id. */
        public id: number;

        /** Tile suit. */
        public suit: game.Suit;

        /** Tile value. */
        public value: number;

        /**
         * Creates a new Tile instance using the specified properties.
         * @param [properties] Properties to set
         * @returns Tile instance
         */
        public static create(properties?: game.ITile): game.Tile;

        /**
         * Encodes the specified Tile message. Does not implicitly {@link game.Tile.verify|verify} messages.
         * @param message Tile message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.ITile, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified Tile message, length delimited. Does not implicitly {@link game.Tile.verify|verify} messages.
         * @param message Tile message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.ITile, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a Tile message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns Tile
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.Tile;

        /**
         * Decodes a Tile message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns Tile
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.Tile;

        /**
         * Verifies a Tile message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a Tile message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns Tile
         */
        public static fromObject(object: { [k: string]: any }): game.Tile;

        /**
         * Creates a plain object from a Tile message. Also converts values to other types if specified.
         * @param message Tile
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.Tile, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this Tile to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for Tile
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** ActionType enum. */
    enum ActionType {
        ACTION_UNKNOWN = 0,
        ACTION_DRAW = 1,
        ACTION_DISCARD = 2,
        ACTION_CHII = 3,
        ACTION_PON = 4,
        ACTION_KAN = 5,
        ACTION_TSUMO = 6,
        ACTION_RON = 7,
        ACTION_PASS = 8,
        ACTION_FLOWER_REVEAL = 9,
        ACTION_READY = 10,
        ACTION_ACCEPT_HAITEI = 11,
        ACTION_REFUSE_HAITEI = 12
    }

    /** Properties of a PlayerAction. */
    interface IPlayerAction {

        /** PlayerAction type */
        type?: (game.ActionType|undefined);

        /** PlayerAction tile */
        tile?: (game.ITile|undefined);

        /** PlayerAction meldTiles */
        meldTiles?: (game.ITile[]|undefined);

        /** PlayerAction targetPlayer */
        targetPlayer?: (number|undefined);

        /** PlayerAction isRobbingKong */
        isRobbingKong?: (boolean|undefined);

        /** PlayerAction isBottomTile */
        isBottomTile?: (boolean|undefined);

        /** PlayerAction isBloomingKong */
        isBloomingKong?: (boolean|undefined);
    }

    /** Represents a PlayerAction. */
    class PlayerAction implements IPlayerAction {

        /**
         * Constructs a new PlayerAction.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IPlayerAction);

        /** PlayerAction type. */
        public type: game.ActionType;

        /** PlayerAction tile. */
        public tile: game.Tile;

        /** PlayerAction meldTiles. */
        public meldTiles: game.Tile[];

        /** PlayerAction targetPlayer. */
        public targetPlayer: number;

        /** PlayerAction isRobbingKong. */
        public isRobbingKong: boolean;

        /** PlayerAction isBottomTile. */
        public isBottomTile: boolean;

        /** PlayerAction isBloomingKong. */
        public isBloomingKong: boolean;

        /**
         * Creates a new PlayerAction instance using the specified properties.
         * @param [properties] Properties to set
         * @returns PlayerAction instance
         */
        public static create(properties?: game.IPlayerAction): game.PlayerAction;

        /**
         * Encodes the specified PlayerAction message. Does not implicitly {@link game.PlayerAction.verify|verify} messages.
         * @param message PlayerAction message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IPlayerAction, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified PlayerAction message, length delimited. Does not implicitly {@link game.PlayerAction.verify|verify} messages.
         * @param message PlayerAction message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IPlayerAction, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a PlayerAction message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns PlayerAction
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.PlayerAction;

        /**
         * Decodes a PlayerAction message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns PlayerAction
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.PlayerAction;

        /**
         * Verifies a PlayerAction message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a PlayerAction message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns PlayerAction
         */
        public static fromObject(object: { [k: string]: any }): game.PlayerAction;

        /**
         * Creates a plain object from a PlayerAction message. Also converts values to other types if specified.
         * @param message PlayerAction
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.PlayerAction, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this PlayerAction to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for PlayerAction
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** MeldDirection enum. */
    enum MeldDirection {
        MELD_DIRECTION_UNKNOWN = 0,
        MELD_DIRECTION_RIGHT = 1,
        MELD_DIRECTION_ACROSS = 2,
        MELD_DIRECTION_LEFT = 3
    }

    /** Properties of a Meld. */
    interface IMeld {

        /** Meld type */
        type?: (game.ActionType|undefined);

        /** Meld tiles */
        tiles?: (game.ITile[]|undefined);

        /** Meld calledDirection */
        calledDirection?: (game.MeldDirection|undefined);

        /** Meld calledTileId */
        calledTileId?: (number|null|undefined);

        /** Meld addedTileId */
        addedTileId?: (number|null|undefined);
    }

    /** Represents a Meld. */
    class Meld implements IMeld {

        /**
         * Constructs a new Meld.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IMeld);

        /** Meld type. */
        public type: game.ActionType;

        /** Meld tiles. */
        public tiles: game.Tile[];

        /** Meld calledDirection. */
        public calledDirection: game.MeldDirection;

        /** Meld calledTileId. */
        public calledTileId: (number|null);

        /** Meld addedTileId. */
        public addedTileId: (number|null);

        /**
         * Creates a new Meld instance using the specified properties.
         * @param [properties] Properties to set
         * @returns Meld instance
         */
        public static create(properties?: game.IMeld): game.Meld;

        /**
         * Encodes the specified Meld message. Does not implicitly {@link game.Meld.verify|verify} messages.
         * @param message Meld message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IMeld, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified Meld message, length delimited. Does not implicitly {@link game.Meld.verify|verify} messages.
         * @param message Meld message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IMeld, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a Meld message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns Meld
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.Meld;

        /**
         * Decodes a Meld message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns Meld
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.Meld;

        /**
         * Verifies a Meld message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a Meld message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns Meld
         */
        public static fromObject(object: { [k: string]: any }): game.Meld;

        /**
         * Creates a plain object from a Meld message. Also converts values to other types if specified.
         * @param message Meld
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.Meld, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this Meld to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for Meld
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a PlayerState. */
    interface IPlayerState {

        /** PlayerState seat */
        seat?: (number|undefined);

        /** PlayerState score */
        score?: (number|undefined);

        /** PlayerState closedHand */
        closedHand?: (game.ITile[]|undefined);

        /** PlayerState handSize */
        handSize?: (number|undefined);

        /** PlayerState openMelds */
        openMelds?: (game.IMeld[]|undefined);

        /** PlayerState discards */
        discards?: (game.ITile[]|undefined);

        /** PlayerState seatWind */
        seatWind?: (number|undefined);

        /** PlayerState flowerMelds */
        flowerMelds?: (game.ITile[]|undefined);

        /** PlayerState hasBuddingDirectKong */
        hasBuddingDirectKong?: (boolean|undefined);

        /** PlayerState hasBloomingDirectKong */
        hasBloomingDirectKong?: (boolean|undefined);

        /** PlayerState hasBuddingClosedKong */
        hasBuddingClosedKong?: (boolean|undefined);

        /** PlayerState hasBloomingClosedKong */
        hasBloomingClosedKong?: (boolean|undefined);

        /** PlayerState hasBuddingRiskyKong */
        hasBuddingRiskyKong?: (boolean|undefined);

        /** PlayerState hasBloomingRiskyKong */
        hasBloomingRiskyKong?: (boolean|undefined);

        /** PlayerState hasBloomingFlowerKong */
        hasBloomingFlowerKong?: (boolean|undefined);

        /** PlayerState validActions */
        validActions?: (game.IPlayerAction[]|undefined);

        /** PlayerState drawnTileId */
        drawnTileId?: (number|null|undefined);

        /** PlayerState shanten */
        shanten?: (number|undefined);

        /** PlayerState lastDiscardFromDrawn */
        lastDiscardFromDrawn?: (boolean|undefined);
    }

    /** Represents a PlayerState. */
    class PlayerState implements IPlayerState {

        /**
         * Constructs a new PlayerState.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IPlayerState);

        /** PlayerState seat. */
        public seat: number;

        /** PlayerState score. */
        public score: number;

        /** PlayerState closedHand. */
        public closedHand: game.Tile[];

        /** PlayerState handSize. */
        public handSize: number;

        /** PlayerState openMelds. */
        public openMelds: game.Meld[];

        /** PlayerState discards. */
        public discards: game.Tile[];

        /** PlayerState seatWind. */
        public seatWind: number;

        /** PlayerState flowerMelds. */
        public flowerMelds: game.Tile[];

        /** PlayerState hasBuddingDirectKong. */
        public hasBuddingDirectKong: boolean;

        /** PlayerState hasBloomingDirectKong. */
        public hasBloomingDirectKong: boolean;

        /** PlayerState hasBuddingClosedKong. */
        public hasBuddingClosedKong: boolean;

        /** PlayerState hasBloomingClosedKong. */
        public hasBloomingClosedKong: boolean;

        /** PlayerState hasBuddingRiskyKong. */
        public hasBuddingRiskyKong: boolean;

        /** PlayerState hasBloomingRiskyKong. */
        public hasBloomingRiskyKong: boolean;

        /** PlayerState hasBloomingFlowerKong. */
        public hasBloomingFlowerKong: boolean;

        /** PlayerState validActions. */
        public validActions: game.PlayerAction[];

        /** PlayerState drawnTileId. */
        public drawnTileId: (number|null);

        /** PlayerState shanten. */
        public shanten: number;

        /** PlayerState lastDiscardFromDrawn. */
        public lastDiscardFromDrawn: boolean;

        /**
         * Creates a new PlayerState instance using the specified properties.
         * @param [properties] Properties to set
         * @returns PlayerState instance
         */
        public static create(properties?: game.IPlayerState): game.PlayerState;

        /**
         * Encodes the specified PlayerState message. Does not implicitly {@link game.PlayerState.verify|verify} messages.
         * @param message PlayerState message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IPlayerState, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified PlayerState message, length delimited. Does not implicitly {@link game.PlayerState.verify|verify} messages.
         * @param message PlayerState message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IPlayerState, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a PlayerState message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns PlayerState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.PlayerState;

        /**
         * Decodes a PlayerState message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns PlayerState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.PlayerState;

        /**
         * Verifies a PlayerState message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a PlayerState message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns PlayerState
         */
        public static fromObject(object: { [k: string]: any }): game.PlayerState;

        /**
         * Creates a plain object from a PlayerState message. Also converts values to other types if specified.
         * @param message PlayerState
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.PlayerState, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this PlayerState to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for PlayerState
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** GamePhase enum. */
    enum GamePhase {
        PHASE_INIT = 0,
        PHASE_DEAL = 1,
        PHASE_PLAYER_TURN = 2,
        PHASE_WAIT_DISCARDS = 3,
        PHASE_ROUND_END = 4,
        PHASE_MATCH_END = 5
    }

    /** Properties of a GameState. */
    interface IGameState {

        /** GameState matchId */
        matchId?: (string|undefined);

        /** GameState phase */
        phase?: (game.GamePhase|undefined);

        /** GameState activePlayer */
        activePlayer?: (number|undefined);

        /** GameState players */
        players?: (game.IPlayerState[]|undefined);

        /** GameState wallCount */
        wallCount?: (number|undefined);

        /** GameState handNum */
        handNum?: (number|undefined);

        /** GameState activeDiscard */
        activeDiscard?: (game.ITile|undefined);

        /** GameState wildTiles */
        wildTiles?: (game.ITile[]|undefined);

        /** GameState prevailingWind */
        prevailingWind?: (number|undefined);

        /** GameState wallSeed */
        wallSeed?: (string|undefined);

        /** GameState roundResult */
        roundResult?: (game.IRoundResult|undefined);

        /** GameState playerReady */
        playerReady?: (boolean[]|undefined);

        /** GameState diceSum */
        diceSum?: (number|undefined);

        /** GameState wangpaiStacks */
        wangpaiStacks?: (number|undefined);

        /** GameState isHaitei */
        isHaitei?: (boolean|undefined);

        /** GameState dice1 */
        dice1?: (number|undefined);

        /** GameState dice2 */
        dice2?: (number|undefined);

        /** GameState wangpaiTilesLeft */
        wangpaiTilesLeft?: (number|undefined);

        /** GameState matchMode */
        matchMode?: (game.MatchMode|undefined);

        /** GameState chongciConfig */
        chongciConfig?: (game.IChongciConfig|undefined);

        /** GameState matchEndResult */
        matchEndResult?: (game.IMatchEndResult|undefined);
    }

    /** Represents a GameState. */
    class GameState implements IGameState {

        /**
         * Constructs a new GameState.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IGameState);

        /** GameState matchId. */
        public matchId: string;

        /** GameState phase. */
        public phase: game.GamePhase;

        /** GameState activePlayer. */
        public activePlayer: number;

        /** GameState players. */
        public players: game.PlayerState[];

        /** GameState wallCount. */
        public wallCount: number;

        /** GameState handNum. */
        public handNum: number;

        /** GameState activeDiscard. */
        public activeDiscard: game.Tile;

        /** GameState wildTiles. */
        public wildTiles: game.Tile[];

        /** GameState prevailingWind. */
        public prevailingWind: number;

        /** GameState wallSeed. */
        public wallSeed: string;

        /** GameState roundResult. */
        public roundResult: game.RoundResult;

        /** GameState playerReady. */
        public playerReady: boolean[];

        /** GameState diceSum. */
        public diceSum: number;

        /** GameState wangpaiStacks. */
        public wangpaiStacks: number;

        /** GameState isHaitei. */
        public isHaitei: boolean;

        /** GameState dice1. */
        public dice1: number;

        /** GameState dice2. */
        public dice2: number;

        /** GameState wangpaiTilesLeft. */
        public wangpaiTilesLeft: number;

        /** GameState matchMode. */
        public matchMode: game.MatchMode;

        /** GameState chongciConfig. */
        public chongciConfig: game.ChongciConfig;

        /** GameState matchEndResult. */
        public matchEndResult: game.MatchEndResult;

        /**
         * Creates a new GameState instance using the specified properties.
         * @param [properties] Properties to set
         * @returns GameState instance
         */
        public static create(properties?: game.IGameState): game.GameState;

        /**
         * Encodes the specified GameState message. Does not implicitly {@link game.GameState.verify|verify} messages.
         * @param message GameState message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IGameState, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified GameState message, length delimited. Does not implicitly {@link game.GameState.verify|verify} messages.
         * @param message GameState message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IGameState, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a GameState message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns GameState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.GameState;

        /**
         * Decodes a GameState message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns GameState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.GameState;

        /**
         * Verifies a GameState message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a GameState message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns GameState
         */
        public static fromObject(object: { [k: string]: any }): game.GameState;

        /**
         * Creates a plain object from a GameState message. Also converts values to other types if specified.
         * @param message GameState
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.GameState, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this GameState to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for GameState
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a ScoreEntry. */
    interface IScoreEntry {

        /** ScoreEntry patternName */
        patternName?: (string|undefined);

        /** ScoreEntry points */
        points?: (number|undefined);

        /** ScoreEntry patternId */
        patternId?: (string|undefined);
    }

    /** Represents a ScoreEntry. */
    class ScoreEntry implements IScoreEntry {

        /**
         * Constructs a new ScoreEntry.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IScoreEntry);

        /** ScoreEntry patternName. */
        public patternName: string;

        /** ScoreEntry points. */
        public points: number;

        /** ScoreEntry patternId. */
        public patternId: string;

        /**
         * Creates a new ScoreEntry instance using the specified properties.
         * @param [properties] Properties to set
         * @returns ScoreEntry instance
         */
        public static create(properties?: game.IScoreEntry): game.ScoreEntry;

        /**
         * Encodes the specified ScoreEntry message. Does not implicitly {@link game.ScoreEntry.verify|verify} messages.
         * @param message ScoreEntry message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IScoreEntry, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified ScoreEntry message, length delimited. Does not implicitly {@link game.ScoreEntry.verify|verify} messages.
         * @param message ScoreEntry message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IScoreEntry, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a ScoreEntry message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns ScoreEntry
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.ScoreEntry;

        /**
         * Decodes a ScoreEntry message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns ScoreEntry
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.ScoreEntry;

        /**
         * Verifies a ScoreEntry message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a ScoreEntry message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns ScoreEntry
         */
        public static fromObject(object: { [k: string]: any }): game.ScoreEntry;

        /**
         * Creates a plain object from a ScoreEntry message. Also converts values to other types if specified.
         * @param message ScoreEntry
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.ScoreEntry, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this ScoreEntry to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for ScoreEntry
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a PlayerPayout. */
    interface IPlayerPayout {

        /** PlayerPayout seat */
        seat?: (number|undefined);

        /** PlayerPayout amount */
        amount?: (number|undefined);
    }

    /** Represents a PlayerPayout. */
    class PlayerPayout implements IPlayerPayout {

        /**
         * Constructs a new PlayerPayout.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IPlayerPayout);

        /** PlayerPayout seat. */
        public seat: number;

        /** PlayerPayout amount. */
        public amount: number;

        /**
         * Creates a new PlayerPayout instance using the specified properties.
         * @param [properties] Properties to set
         * @returns PlayerPayout instance
         */
        public static create(properties?: game.IPlayerPayout): game.PlayerPayout;

        /**
         * Encodes the specified PlayerPayout message. Does not implicitly {@link game.PlayerPayout.verify|verify} messages.
         * @param message PlayerPayout message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IPlayerPayout, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified PlayerPayout message, length delimited. Does not implicitly {@link game.PlayerPayout.verify|verify} messages.
         * @param message PlayerPayout message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IPlayerPayout, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a PlayerPayout message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns PlayerPayout
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.PlayerPayout;

        /**
         * Decodes a PlayerPayout message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns PlayerPayout
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.PlayerPayout;

        /**
         * Verifies a PlayerPayout message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a PlayerPayout message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns PlayerPayout
         */
        public static fromObject(object: { [k: string]: any }): game.PlayerPayout;

        /**
         * Creates a plain object from a PlayerPayout message. Also converts values to other types if specified.
         * @param message PlayerPayout
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.PlayerPayout, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this PlayerPayout to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for PlayerPayout
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a RoundResult. */
    interface IRoundResult {

        /** RoundResult winnerSeat */
        winnerSeat?: (number|undefined);

        /** RoundResult winType */
        winType?: (game.ActionType|undefined);

        /** RoundResult discarderSeat */
        discarderSeat?: (number|undefined);

        /** RoundResult winningHand */
        winningHand?: (game.ITile[]|undefined);

        /** RoundResult winningMelds */
        winningMelds?: (game.IMeld[]|undefined);

        /** RoundResult winTile */
        winTile?: (game.ITile|undefined);

        /** RoundResult breakdown */
        breakdown?: (game.IScoreEntry[]|undefined);

        /** RoundResult totalScore */
        totalScore?: (number|undefined);

        /** RoundResult payouts */
        payouts?: (game.IPlayerPayout[]|undefined);

        /** RoundResult isDraw */
        isDraw?: (boolean|undefined);
    }

    /** Represents a RoundResult. */
    class RoundResult implements IRoundResult {

        /**
         * Constructs a new RoundResult.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IRoundResult);

        /** RoundResult winnerSeat. */
        public winnerSeat: number;

        /** RoundResult winType. */
        public winType: game.ActionType;

        /** RoundResult discarderSeat. */
        public discarderSeat: number;

        /** RoundResult winningHand. */
        public winningHand: game.Tile[];

        /** RoundResult winningMelds. */
        public winningMelds: game.Meld[];

        /** RoundResult winTile. */
        public winTile: game.Tile;

        /** RoundResult breakdown. */
        public breakdown: game.ScoreEntry[];

        /** RoundResult totalScore. */
        public totalScore: number;

        /** RoundResult payouts. */
        public payouts: game.PlayerPayout[];

        /** RoundResult isDraw. */
        public isDraw: boolean;

        /**
         * Creates a new RoundResult instance using the specified properties.
         * @param [properties] Properties to set
         * @returns RoundResult instance
         */
        public static create(properties?: game.IRoundResult): game.RoundResult;

        /**
         * Encodes the specified RoundResult message. Does not implicitly {@link game.RoundResult.verify|verify} messages.
         * @param message RoundResult message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IRoundResult, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified RoundResult message, length delimited. Does not implicitly {@link game.RoundResult.verify|verify} messages.
         * @param message RoundResult message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IRoundResult, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a RoundResult message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns RoundResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.RoundResult;

        /**
         * Decodes a RoundResult message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns RoundResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.RoundResult;

        /**
         * Verifies a RoundResult message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a RoundResult message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns RoundResult
         */
        public static fromObject(object: { [k: string]: any }): game.RoundResult;

        /**
         * Creates a plain object from a RoundResult message. Also converts values to other types if specified.
         * @param message RoundResult
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.RoundResult, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this RoundResult to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for RoundResult
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a RoundOutcome. */
    interface IRoundOutcome {

        /** RoundOutcome isDraw */
        isDraw?: (boolean|undefined);

        /** RoundOutcome winnerSeat */
        winnerSeat?: (number|undefined);

        /** RoundOutcome winType */
        winType?: (game.ActionType|undefined);

        /** RoundOutcome discarderSeat */
        discarderSeat?: (number|undefined);

        /** RoundOutcome totalScore */
        totalScore?: (number|undefined);

        /** RoundOutcome payouts */
        payouts?: (game.IPlayerPayout[]|undefined);
    }

    /** Represents a RoundOutcome. */
    class RoundOutcome implements IRoundOutcome {

        /**
         * Constructs a new RoundOutcome.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IRoundOutcome);

        /** RoundOutcome isDraw. */
        public isDraw: boolean;

        /** RoundOutcome winnerSeat. */
        public winnerSeat: number;

        /** RoundOutcome winType. */
        public winType: game.ActionType;

        /** RoundOutcome discarderSeat. */
        public discarderSeat: number;

        /** RoundOutcome totalScore. */
        public totalScore: number;

        /** RoundOutcome payouts. */
        public payouts: game.PlayerPayout[];

        /**
         * Creates a new RoundOutcome instance using the specified properties.
         * @param [properties] Properties to set
         * @returns RoundOutcome instance
         */
        public static create(properties?: game.IRoundOutcome): game.RoundOutcome;

        /**
         * Encodes the specified RoundOutcome message. Does not implicitly {@link game.RoundOutcome.verify|verify} messages.
         * @param message RoundOutcome message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IRoundOutcome, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified RoundOutcome message, length delimited. Does not implicitly {@link game.RoundOutcome.verify|verify} messages.
         * @param message RoundOutcome message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IRoundOutcome, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a RoundOutcome message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns RoundOutcome
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.RoundOutcome;

        /**
         * Decodes a RoundOutcome message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns RoundOutcome
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.RoundOutcome;

        /**
         * Verifies a RoundOutcome message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a RoundOutcome message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns RoundOutcome
         */
        public static fromObject(object: { [k: string]: any }): game.RoundOutcome;

        /**
         * Creates a plain object from a RoundOutcome message. Also converts values to other types if specified.
         * @param message RoundOutcome
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.RoundOutcome, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this RoundOutcome to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for RoundOutcome
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of an EnvConfig. */
    interface IEnvConfig {

        /** EnvConfig learningSeats */
        learningSeats?: (number[]|undefined);

        /** EnvConfig autoPlayHeuristics */
        autoPlayHeuristics?: (boolean|undefined);

        /** EnvConfig maxDecisions */
        maxDecisions?: (number|undefined);

        /** EnvConfig matchMode */
        matchMode?: (game.MatchMode|undefined);

        /** EnvConfig chongciConfig */
        chongciConfig?: (game.IChongciConfig|undefined);

        /** EnvConfig oracleObservation */
        oracleObservation?: (boolean|undefined);
    }

    /** Represents an EnvConfig. */
    class EnvConfig implements IEnvConfig {

        /**
         * Constructs a new EnvConfig.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IEnvConfig);

        /** EnvConfig learningSeats. */
        public learningSeats: number[];

        /** EnvConfig autoPlayHeuristics. */
        public autoPlayHeuristics: boolean;

        /** EnvConfig maxDecisions. */
        public maxDecisions: number;

        /** EnvConfig matchMode. */
        public matchMode: game.MatchMode;

        /** EnvConfig chongciConfig. */
        public chongciConfig: game.ChongciConfig;

        /** EnvConfig oracleObservation. */
        public oracleObservation: boolean;

        /**
         * Creates a new EnvConfig instance using the specified properties.
         * @param [properties] Properties to set
         * @returns EnvConfig instance
         */
        public static create(properties?: game.IEnvConfig): game.EnvConfig;

        /**
         * Encodes the specified EnvConfig message. Does not implicitly {@link game.EnvConfig.verify|verify} messages.
         * @param message EnvConfig message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IEnvConfig, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified EnvConfig message, length delimited. Does not implicitly {@link game.EnvConfig.verify|verify} messages.
         * @param message EnvConfig message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IEnvConfig, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an EnvConfig message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns EnvConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.EnvConfig;

        /**
         * Decodes an EnvConfig message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns EnvConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.EnvConfig;

        /**
         * Verifies an EnvConfig message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an EnvConfig message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns EnvConfig
         */
        public static fromObject(object: { [k: string]: any }): game.EnvConfig;

        /**
         * Creates a plain object from an EnvConfig message. Also converts values to other types if specified.
         * @param message EnvConfig
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.EnvConfig, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this EnvConfig to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for EnvConfig
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a SeatObservation. */
    interface ISeatObservation {

        /** SeatObservation seat */
        seat?: (number|undefined);

        /** SeatObservation planes */
        planes?: (number[]|undefined);

        /** SeatObservation planeChannels */
        planeChannels?: (number|undefined);

        /** SeatObservation planeHeight */
        planeHeight?: (number|undefined);

        /** SeatObservation planeWidth */
        planeWidth?: (number|undefined);

        /** SeatObservation scalars */
        scalars?: (number[]|undefined);

        /** SeatObservation actionMask */
        actionMask?: (Uint8Array|undefined);

        /** SeatObservation actionSpaceSize */
        actionSpaceSize?: (number|undefined);

        /** SeatObservation decisionIndex */
        decisionIndex?: (number|Long|undefined);

        /** SeatObservation phase */
        phase?: (game.GamePhase|undefined);

        /** SeatObservation activePlayer */
        activePlayer?: (number|undefined);
    }

    /** Represents a SeatObservation. */
    class SeatObservation implements ISeatObservation {

        /**
         * Constructs a new SeatObservation.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.ISeatObservation);

        /** SeatObservation seat. */
        public seat: number;

        /** SeatObservation planes. */
        public planes: number[];

        /** SeatObservation planeChannels. */
        public planeChannels: number;

        /** SeatObservation planeHeight. */
        public planeHeight: number;

        /** SeatObservation planeWidth. */
        public planeWidth: number;

        /** SeatObservation scalars. */
        public scalars: number[];

        /** SeatObservation actionMask. */
        public actionMask: Uint8Array;

        /** SeatObservation actionSpaceSize. */
        public actionSpaceSize: number;

        /** SeatObservation decisionIndex. */
        public decisionIndex: (number|Long);

        /** SeatObservation phase. */
        public phase: game.GamePhase;

        /** SeatObservation activePlayer. */
        public activePlayer: number;

        /**
         * Creates a new SeatObservation instance using the specified properties.
         * @param [properties] Properties to set
         * @returns SeatObservation instance
         */
        public static create(properties?: game.ISeatObservation): game.SeatObservation;

        /**
         * Encodes the specified SeatObservation message. Does not implicitly {@link game.SeatObservation.verify|verify} messages.
         * @param message SeatObservation message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.ISeatObservation, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified SeatObservation message, length delimited. Does not implicitly {@link game.SeatObservation.verify|verify} messages.
         * @param message SeatObservation message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.ISeatObservation, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a SeatObservation message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns SeatObservation
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.SeatObservation;

        /**
         * Decodes a SeatObservation message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns SeatObservation
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.SeatObservation;

        /**
         * Verifies a SeatObservation message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a SeatObservation message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns SeatObservation
         */
        public static fromObject(object: { [k: string]: any }): game.SeatObservation;

        /**
         * Creates a plain object from a SeatObservation message. Also converts values to other types if specified.
         * @param message SeatObservation
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.SeatObservation, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this SeatObservation to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for SeatObservation
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of an EnvResetRequest. */
    interface IEnvResetRequest {

        /** EnvResetRequest seed */
        seed?: (number|Long|undefined);

        /** EnvResetRequest config */
        config?: (game.IEnvConfig|undefined);
    }

    /** Represents an EnvResetRequest. */
    class EnvResetRequest implements IEnvResetRequest {

        /**
         * Constructs a new EnvResetRequest.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IEnvResetRequest);

        /** EnvResetRequest seed. */
        public seed: (number|Long);

        /** EnvResetRequest config. */
        public config: game.EnvConfig;

        /**
         * Creates a new EnvResetRequest instance using the specified properties.
         * @param [properties] Properties to set
         * @returns EnvResetRequest instance
         */
        public static create(properties?: game.IEnvResetRequest): game.EnvResetRequest;

        /**
         * Encodes the specified EnvResetRequest message. Does not implicitly {@link game.EnvResetRequest.verify|verify} messages.
         * @param message EnvResetRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IEnvResetRequest, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified EnvResetRequest message, length delimited. Does not implicitly {@link game.EnvResetRequest.verify|verify} messages.
         * @param message EnvResetRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IEnvResetRequest, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an EnvResetRequest message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns EnvResetRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.EnvResetRequest;

        /**
         * Decodes an EnvResetRequest message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns EnvResetRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.EnvResetRequest;

        /**
         * Verifies an EnvResetRequest message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an EnvResetRequest message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns EnvResetRequest
         */
        public static fromObject(object: { [k: string]: any }): game.EnvResetRequest;

        /**
         * Creates a plain object from an EnvResetRequest message. Also converts values to other types if specified.
         * @param message EnvResetRequest
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.EnvResetRequest, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this EnvResetRequest to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for EnvResetRequest
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of an EnvResetResponse. */
    interface IEnvResetResponse {

        /** EnvResetResponse observation */
        observation?: (game.ISeatObservation|undefined);

        /** EnvResetResponse rewards */
        rewards?: (number[]|undefined);

        /** EnvResetResponse terminated */
        terminated?: (boolean|undefined);

        /** EnvResetResponse truncated */
        truncated?: (boolean|undefined);

        /** EnvResetResponse roundOutcome */
        roundOutcome?: (game.IRoundOutcome|undefined);
    }

    /** Represents an EnvResetResponse. */
    class EnvResetResponse implements IEnvResetResponse {

        /**
         * Constructs a new EnvResetResponse.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IEnvResetResponse);

        /** EnvResetResponse observation. */
        public observation: game.SeatObservation;

        /** EnvResetResponse rewards. */
        public rewards: number[];

        /** EnvResetResponse terminated. */
        public terminated: boolean;

        /** EnvResetResponse truncated. */
        public truncated: boolean;

        /** EnvResetResponse roundOutcome. */
        public roundOutcome: game.RoundOutcome;

        /**
         * Creates a new EnvResetResponse instance using the specified properties.
         * @param [properties] Properties to set
         * @returns EnvResetResponse instance
         */
        public static create(properties?: game.IEnvResetResponse): game.EnvResetResponse;

        /**
         * Encodes the specified EnvResetResponse message. Does not implicitly {@link game.EnvResetResponse.verify|verify} messages.
         * @param message EnvResetResponse message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IEnvResetResponse, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified EnvResetResponse message, length delimited. Does not implicitly {@link game.EnvResetResponse.verify|verify} messages.
         * @param message EnvResetResponse message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IEnvResetResponse, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an EnvResetResponse message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns EnvResetResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.EnvResetResponse;

        /**
         * Decodes an EnvResetResponse message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns EnvResetResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.EnvResetResponse;

        /**
         * Verifies an EnvResetResponse message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an EnvResetResponse message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns EnvResetResponse
         */
        public static fromObject(object: { [k: string]: any }): game.EnvResetResponse;

        /**
         * Creates a plain object from an EnvResetResponse message. Also converts values to other types if specified.
         * @param message EnvResetResponse
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.EnvResetResponse, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this EnvResetResponse to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for EnvResetResponse
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of an EnvStepRequest. */
    interface IEnvStepRequest {

        /** EnvStepRequest actionId */
        actionId?: (number|undefined);
    }

    /** Represents an EnvStepRequest. */
    class EnvStepRequest implements IEnvStepRequest {

        /**
         * Constructs a new EnvStepRequest.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IEnvStepRequest);

        /** EnvStepRequest actionId. */
        public actionId: number;

        /**
         * Creates a new EnvStepRequest instance using the specified properties.
         * @param [properties] Properties to set
         * @returns EnvStepRequest instance
         */
        public static create(properties?: game.IEnvStepRequest): game.EnvStepRequest;

        /**
         * Encodes the specified EnvStepRequest message. Does not implicitly {@link game.EnvStepRequest.verify|verify} messages.
         * @param message EnvStepRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IEnvStepRequest, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified EnvStepRequest message, length delimited. Does not implicitly {@link game.EnvStepRequest.verify|verify} messages.
         * @param message EnvStepRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IEnvStepRequest, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an EnvStepRequest message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns EnvStepRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.EnvStepRequest;

        /**
         * Decodes an EnvStepRequest message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns EnvStepRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.EnvStepRequest;

        /**
         * Verifies an EnvStepRequest message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an EnvStepRequest message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns EnvStepRequest
         */
        public static fromObject(object: { [k: string]: any }): game.EnvStepRequest;

        /**
         * Creates a plain object from an EnvStepRequest message. Also converts values to other types if specified.
         * @param message EnvStepRequest
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.EnvStepRequest, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this EnvStepRequest to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for EnvStepRequest
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of an EnvStepResponse. */
    interface IEnvStepResponse {

        /** EnvStepResponse observation */
        observation?: (game.ISeatObservation|undefined);

        /** EnvStepResponse rewards */
        rewards?: (number[]|undefined);

        /** EnvStepResponse terminated */
        terminated?: (boolean|undefined);

        /** EnvStepResponse truncated */
        truncated?: (boolean|undefined);

        /** EnvStepResponse roundOutcome */
        roundOutcome?: (game.IRoundOutcome|undefined);
    }

    /** Represents an EnvStepResponse. */
    class EnvStepResponse implements IEnvStepResponse {

        /**
         * Constructs a new EnvStepResponse.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IEnvStepResponse);

        /** EnvStepResponse observation. */
        public observation: game.SeatObservation;

        /** EnvStepResponse rewards. */
        public rewards: number[];

        /** EnvStepResponse terminated. */
        public terminated: boolean;

        /** EnvStepResponse truncated. */
        public truncated: boolean;

        /** EnvStepResponse roundOutcome. */
        public roundOutcome: game.RoundOutcome;

        /**
         * Creates a new EnvStepResponse instance using the specified properties.
         * @param [properties] Properties to set
         * @returns EnvStepResponse instance
         */
        public static create(properties?: game.IEnvStepResponse): game.EnvStepResponse;

        /**
         * Encodes the specified EnvStepResponse message. Does not implicitly {@link game.EnvStepResponse.verify|verify} messages.
         * @param message EnvStepResponse message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IEnvStepResponse, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified EnvStepResponse message, length delimited. Does not implicitly {@link game.EnvStepResponse.verify|verify} messages.
         * @param message EnvStepResponse message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IEnvStepResponse, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an EnvStepResponse message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns EnvStepResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.EnvStepResponse;

        /**
         * Decodes an EnvStepResponse message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns EnvStepResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.EnvStepResponse;

        /**
         * Verifies an EnvStepResponse message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an EnvStepResponse message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns EnvStepResponse
         */
        public static fromObject(object: { [k: string]: any }): game.EnvStepResponse;

        /**
         * Creates a plain object from an EnvStepResponse message. Also converts values to other types if specified.
         * @param message EnvStepResponse
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.EnvStepResponse, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this EnvStepResponse to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for EnvStepResponse
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a BranchEvaluationRequest. */
    interface IBranchEvaluationRequest {

        /** BranchEvaluationRequest actionIds */
        actionIds?: (number[]|undefined);

        /** BranchEvaluationRequest stopAtRoundEnd */
        stopAtRoundEnd?: (boolean|undefined);

        /** BranchEvaluationRequest maxDecisions */
        maxDecisions?: (number|undefined);
    }

    /** Represents a BranchEvaluationRequest. */
    class BranchEvaluationRequest implements IBranchEvaluationRequest {

        /**
         * Constructs a new BranchEvaluationRequest.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IBranchEvaluationRequest);

        /** BranchEvaluationRequest actionIds. */
        public actionIds: number[];

        /** BranchEvaluationRequest stopAtRoundEnd. */
        public stopAtRoundEnd: boolean;

        /** BranchEvaluationRequest maxDecisions. */
        public maxDecisions: number;

        /**
         * Creates a new BranchEvaluationRequest instance using the specified properties.
         * @param [properties] Properties to set
         * @returns BranchEvaluationRequest instance
         */
        public static create(properties?: game.IBranchEvaluationRequest): game.BranchEvaluationRequest;

        /**
         * Encodes the specified BranchEvaluationRequest message. Does not implicitly {@link game.BranchEvaluationRequest.verify|verify} messages.
         * @param message BranchEvaluationRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IBranchEvaluationRequest, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified BranchEvaluationRequest message, length delimited. Does not implicitly {@link game.BranchEvaluationRequest.verify|verify} messages.
         * @param message BranchEvaluationRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IBranchEvaluationRequest, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a BranchEvaluationRequest message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns BranchEvaluationRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.BranchEvaluationRequest;

        /**
         * Decodes a BranchEvaluationRequest message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns BranchEvaluationRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.BranchEvaluationRequest;

        /**
         * Verifies a BranchEvaluationRequest message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a BranchEvaluationRequest message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns BranchEvaluationRequest
         */
        public static fromObject(object: { [k: string]: any }): game.BranchEvaluationRequest;

        /**
         * Creates a plain object from a BranchEvaluationRequest message. Also converts values to other types if specified.
         * @param message BranchEvaluationRequest
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.BranchEvaluationRequest, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this BranchEvaluationRequest to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for BranchEvaluationRequest
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a BranchEvaluationResult. */
    interface IBranchEvaluationResult {

        /** BranchEvaluationResult actionId */
        actionId?: (number|undefined);

        /** BranchEvaluationResult rewards */
        rewards?: (number[]|undefined);

        /** BranchEvaluationResult terminated */
        terminated?: (boolean|undefined);

        /** BranchEvaluationResult truncated */
        truncated?: (boolean|undefined);

        /** BranchEvaluationResult roundOutcome */
        roundOutcome?: (game.IRoundOutcome|undefined);

        /** BranchEvaluationResult decisions */
        decisions?: (number|Long|undefined);

        /** BranchEvaluationResult error */
        error?: (string|undefined);
    }

    /** Represents a BranchEvaluationResult. */
    class BranchEvaluationResult implements IBranchEvaluationResult {

        /**
         * Constructs a new BranchEvaluationResult.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IBranchEvaluationResult);

        /** BranchEvaluationResult actionId. */
        public actionId: number;

        /** BranchEvaluationResult rewards. */
        public rewards: number[];

        /** BranchEvaluationResult terminated. */
        public terminated: boolean;

        /** BranchEvaluationResult truncated. */
        public truncated: boolean;

        /** BranchEvaluationResult roundOutcome. */
        public roundOutcome: game.RoundOutcome;

        /** BranchEvaluationResult decisions. */
        public decisions: (number|Long);

        /** BranchEvaluationResult error. */
        public error: string;

        /**
         * Creates a new BranchEvaluationResult instance using the specified properties.
         * @param [properties] Properties to set
         * @returns BranchEvaluationResult instance
         */
        public static create(properties?: game.IBranchEvaluationResult): game.BranchEvaluationResult;

        /**
         * Encodes the specified BranchEvaluationResult message. Does not implicitly {@link game.BranchEvaluationResult.verify|verify} messages.
         * @param message BranchEvaluationResult message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IBranchEvaluationResult, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified BranchEvaluationResult message, length delimited. Does not implicitly {@link game.BranchEvaluationResult.verify|verify} messages.
         * @param message BranchEvaluationResult message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IBranchEvaluationResult, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a BranchEvaluationResult message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns BranchEvaluationResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.BranchEvaluationResult;

        /**
         * Decodes a BranchEvaluationResult message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns BranchEvaluationResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.BranchEvaluationResult;

        /**
         * Verifies a BranchEvaluationResult message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a BranchEvaluationResult message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns BranchEvaluationResult
         */
        public static fromObject(object: { [k: string]: any }): game.BranchEvaluationResult;

        /**
         * Creates a plain object from a BranchEvaluationResult message. Also converts values to other types if specified.
         * @param message BranchEvaluationResult
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.BranchEvaluationResult, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this BranchEvaluationResult to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for BranchEvaluationResult
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a BranchEvaluationResponse. */
    interface IBranchEvaluationResponse {

        /** BranchEvaluationResponse observation */
        observation?: (game.ISeatObservation|undefined);

        /** BranchEvaluationResponse results */
        results?: (game.IBranchEvaluationResult[]|undefined);
    }

    /** Represents a BranchEvaluationResponse. */
    class BranchEvaluationResponse implements IBranchEvaluationResponse {

        /**
         * Constructs a new BranchEvaluationResponse.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IBranchEvaluationResponse);

        /** BranchEvaluationResponse observation. */
        public observation: game.SeatObservation;

        /** BranchEvaluationResponse results. */
        public results: game.BranchEvaluationResult[];

        /**
         * Creates a new BranchEvaluationResponse instance using the specified properties.
         * @param [properties] Properties to set
         * @returns BranchEvaluationResponse instance
         */
        public static create(properties?: game.IBranchEvaluationResponse): game.BranchEvaluationResponse;

        /**
         * Encodes the specified BranchEvaluationResponse message. Does not implicitly {@link game.BranchEvaluationResponse.verify|verify} messages.
         * @param message BranchEvaluationResponse message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IBranchEvaluationResponse, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified BranchEvaluationResponse message, length delimited. Does not implicitly {@link game.BranchEvaluationResponse.verify|verify} messages.
         * @param message BranchEvaluationResponse message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IBranchEvaluationResponse, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a BranchEvaluationResponse message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns BranchEvaluationResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.BranchEvaluationResponse;

        /**
         * Decodes a BranchEvaluationResponse message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns BranchEvaluationResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.BranchEvaluationResponse;

        /**
         * Verifies a BranchEvaluationResponse message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a BranchEvaluationResponse message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns BranchEvaluationResponse
         */
        public static fromObject(object: { [k: string]: any }): game.BranchEvaluationResponse;

        /**
         * Creates a plain object from a BranchEvaluationResponse message. Also converts values to other types if specified.
         * @param message BranchEvaluationResponse
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.BranchEvaluationResponse, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this BranchEvaluationResponse to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for BranchEvaluationResponse
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a TrajectoryRequest. */
    interface ITrajectoryRequest {

        /** TrajectoryRequest episodes */
        episodes?: (number|undefined);

        /** TrajectoryRequest startSeed */
        startSeed?: (number|Long|undefined);

        /** TrajectoryRequest config */
        config?: (game.IEnvConfig|undefined);
    }

    /** Represents a TrajectoryRequest. */
    class TrajectoryRequest implements ITrajectoryRequest {

        /**
         * Constructs a new TrajectoryRequest.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.ITrajectoryRequest);

        /** TrajectoryRequest episodes. */
        public episodes: number;

        /** TrajectoryRequest startSeed. */
        public startSeed: (number|Long);

        /** TrajectoryRequest config. */
        public config: game.EnvConfig;

        /**
         * Creates a new TrajectoryRequest instance using the specified properties.
         * @param [properties] Properties to set
         * @returns TrajectoryRequest instance
         */
        public static create(properties?: game.ITrajectoryRequest): game.TrajectoryRequest;

        /**
         * Encodes the specified TrajectoryRequest message. Does not implicitly {@link game.TrajectoryRequest.verify|verify} messages.
         * @param message TrajectoryRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.ITrajectoryRequest, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified TrajectoryRequest message, length delimited. Does not implicitly {@link game.TrajectoryRequest.verify|verify} messages.
         * @param message TrajectoryRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.ITrajectoryRequest, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a TrajectoryRequest message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns TrajectoryRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.TrajectoryRequest;

        /**
         * Decodes a TrajectoryRequest message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns TrajectoryRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.TrajectoryRequest;

        /**
         * Verifies a TrajectoryRequest message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a TrajectoryRequest message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns TrajectoryRequest
         */
        public static fromObject(object: { [k: string]: any }): game.TrajectoryRequest;

        /**
         * Creates a plain object from a TrajectoryRequest message. Also converts values to other types if specified.
         * @param message TrajectoryRequest
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.TrajectoryRequest, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this TrajectoryRequest to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for TrajectoryRequest
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a TrajectorySample. */
    interface ITrajectorySample {

        /** TrajectorySample observation */
        observation?: (game.ISeatObservation|undefined);

        /** TrajectorySample actionId */
        actionId?: (number|undefined);

        /** TrajectorySample rewards */
        rewards?: (number[]|undefined);

        /** TrajectorySample nextObservation */
        nextObservation?: (game.ISeatObservation|undefined);

        /** TrajectorySample terminated */
        terminated?: (boolean|undefined);

        /** TrajectorySample truncated */
        truncated?: (boolean|undefined);

        /** TrajectorySample actingSeat */
        actingSeat?: (number|undefined);

        /** TrajectorySample episodeIndex */
        episodeIndex?: (number|Long|undefined);

        /** TrajectorySample terminalRewards */
        terminalRewards?: (number[]|undefined);

        /** TrajectorySample terminalOutcome */
        terminalOutcome?: (game.IRoundOutcome|undefined);
    }

    /** Represents a TrajectorySample. */
    class TrajectorySample implements ITrajectorySample {

        /**
         * Constructs a new TrajectorySample.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.ITrajectorySample);

        /** TrajectorySample observation. */
        public observation: game.SeatObservation;

        /** TrajectorySample actionId. */
        public actionId: number;

        /** TrajectorySample rewards. */
        public rewards: number[];

        /** TrajectorySample nextObservation. */
        public nextObservation: game.SeatObservation;

        /** TrajectorySample terminated. */
        public terminated: boolean;

        /** TrajectorySample truncated. */
        public truncated: boolean;

        /** TrajectorySample actingSeat. */
        public actingSeat: number;

        /** TrajectorySample episodeIndex. */
        public episodeIndex: (number|Long);

        /** TrajectorySample terminalRewards. */
        public terminalRewards: number[];

        /** TrajectorySample terminalOutcome. */
        public terminalOutcome: game.RoundOutcome;

        /**
         * Creates a new TrajectorySample instance using the specified properties.
         * @param [properties] Properties to set
         * @returns TrajectorySample instance
         */
        public static create(properties?: game.ITrajectorySample): game.TrajectorySample;

        /**
         * Encodes the specified TrajectorySample message. Does not implicitly {@link game.TrajectorySample.verify|verify} messages.
         * @param message TrajectorySample message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.ITrajectorySample, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified TrajectorySample message, length delimited. Does not implicitly {@link game.TrajectorySample.verify|verify} messages.
         * @param message TrajectorySample message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.ITrajectorySample, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a TrajectorySample message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns TrajectorySample
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.TrajectorySample;

        /**
         * Decodes a TrajectorySample message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns TrajectorySample
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.TrajectorySample;

        /**
         * Verifies a TrajectorySample message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a TrajectorySample message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns TrajectorySample
         */
        public static fromObject(object: { [k: string]: any }): game.TrajectorySample;

        /**
         * Creates a plain object from a TrajectorySample message. Also converts values to other types if specified.
         * @param message TrajectorySample
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.TrajectorySample, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this TrajectorySample to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for TrajectorySample
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a TrajectoryDataset. */
    interface ITrajectoryDataset {

        /** TrajectoryDataset samples */
        samples?: (game.ITrajectorySample[]|undefined);
    }

    /** Represents a TrajectoryDataset. */
    class TrajectoryDataset implements ITrajectoryDataset {

        /**
         * Constructs a new TrajectoryDataset.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.ITrajectoryDataset);

        /** TrajectoryDataset samples. */
        public samples: game.TrajectorySample[];

        /**
         * Creates a new TrajectoryDataset instance using the specified properties.
         * @param [properties] Properties to set
         * @returns TrajectoryDataset instance
         */
        public static create(properties?: game.ITrajectoryDataset): game.TrajectoryDataset;

        /**
         * Encodes the specified TrajectoryDataset message. Does not implicitly {@link game.TrajectoryDataset.verify|verify} messages.
         * @param message TrajectoryDataset message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.ITrajectoryDataset, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified TrajectoryDataset message, length delimited. Does not implicitly {@link game.TrajectoryDataset.verify|verify} messages.
         * @param message TrajectoryDataset message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.ITrajectoryDataset, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a TrajectoryDataset message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns TrajectoryDataset
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.TrajectoryDataset;

        /**
         * Decodes a TrajectoryDataset message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns TrajectoryDataset
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.TrajectoryDataset;

        /**
         * Verifies a TrajectoryDataset message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a TrajectoryDataset message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns TrajectoryDataset
         */
        public static fromObject(object: { [k: string]: any }): game.TrajectoryDataset;

        /**
         * Creates a plain object from a TrajectoryDataset message. Also converts values to other types if specified.
         * @param message TrajectoryDataset
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.TrajectoryDataset, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this TrajectoryDataset to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for TrajectoryDataset
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Difficulty enum. */
    enum Difficulty {
        DIFFICULTY_UNSPECIFIED = 0,
        DIFFICULTY_HEURISTIC = 1,
        DIFFICULTY_RL = 2
    }

    /** Properties of a SeatConfig. */
    interface ISeatConfig {

        /** SeatConfig kind */
        kind?: (string|undefined);

        /** SeatConfig userId */
        userId?: (number|undefined);

        /** SeatConfig username */
        username?: (string|undefined);

        /** SeatConfig difficulty */
        difficulty?: (game.Difficulty|undefined);
    }

    /** Represents a SeatConfig. */
    class SeatConfig implements ISeatConfig {

        /**
         * Constructs a new SeatConfig.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.ISeatConfig);

        /** SeatConfig kind. */
        public kind: string;

        /** SeatConfig userId. */
        public userId: number;

        /** SeatConfig username. */
        public username: string;

        /** SeatConfig difficulty. */
        public difficulty: game.Difficulty;

        /**
         * Creates a new SeatConfig instance using the specified properties.
         * @param [properties] Properties to set
         * @returns SeatConfig instance
         */
        public static create(properties?: game.ISeatConfig): game.SeatConfig;

        /**
         * Encodes the specified SeatConfig message. Does not implicitly {@link game.SeatConfig.verify|verify} messages.
         * @param message SeatConfig message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.ISeatConfig, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified SeatConfig message, length delimited. Does not implicitly {@link game.SeatConfig.verify|verify} messages.
         * @param message SeatConfig message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.ISeatConfig, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a SeatConfig message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns SeatConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.SeatConfig;

        /**
         * Decodes a SeatConfig message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns SeatConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.SeatConfig;

        /**
         * Verifies a SeatConfig message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a SeatConfig message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns SeatConfig
         */
        public static fromObject(object: { [k: string]: any }): game.SeatConfig;

        /**
         * Creates a plain object from a SeatConfig message. Also converts values to other types if specified.
         * @param message SeatConfig
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.SeatConfig, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this SeatConfig to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for SeatConfig
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a PrivateTableState. */
    interface IPrivateTableState {

        /** PrivateTableState tableId */
        tableId?: (string|undefined);

        /** PrivateTableState hostUserId */
        hostUserId?: (number|undefined);

        /** PrivateTableState seats */
        seats?: (game.ISeatConfig[]|undefined);

        /** PrivateTableState state */
        state?: (string|undefined);

        /** PrivateTableState matchId */
        matchId?: (string|undefined);

        /** PrivateTableState matchMode */
        matchMode?: (game.MatchMode|undefined);

        /** PrivateTableState chongciConfig */
        chongciConfig?: (game.IChongciConfig|undefined);
    }

    /** Represents a PrivateTableState. */
    class PrivateTableState implements IPrivateTableState {

        /**
         * Constructs a new PrivateTableState.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IPrivateTableState);

        /** PrivateTableState tableId. */
        public tableId: string;

        /** PrivateTableState hostUserId. */
        public hostUserId: number;

        /** PrivateTableState seats. */
        public seats: game.SeatConfig[];

        /** PrivateTableState state. */
        public state: string;

        /** PrivateTableState matchId. */
        public matchId: string;

        /** PrivateTableState matchMode. */
        public matchMode: game.MatchMode;

        /** PrivateTableState chongciConfig. */
        public chongciConfig: game.ChongciConfig;

        /**
         * Creates a new PrivateTableState instance using the specified properties.
         * @param [properties] Properties to set
         * @returns PrivateTableState instance
         */
        public static create(properties?: game.IPrivateTableState): game.PrivateTableState;

        /**
         * Encodes the specified PrivateTableState message. Does not implicitly {@link game.PrivateTableState.verify|verify} messages.
         * @param message PrivateTableState message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IPrivateTableState, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified PrivateTableState message, length delimited. Does not implicitly {@link game.PrivateTableState.verify|verify} messages.
         * @param message PrivateTableState message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IPrivateTableState, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a PrivateTableState message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns PrivateTableState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.PrivateTableState;

        /**
         * Decodes a PrivateTableState message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns PrivateTableState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.PrivateTableState;

        /**
         * Verifies a PrivateTableState message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a PrivateTableState message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns PrivateTableState
         */
        public static fromObject(object: { [k: string]: any }): game.PrivateTableState;

        /**
         * Creates a plain object from a PrivateTableState message. Also converts values to other types if specified.
         * @param message PrivateTableState
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.PrivateTableState, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this PrivateTableState to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for PrivateTableState
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** MatchMode enum. */
    enum MatchMode {
        MATCH_MODE_UNSPECIFIED = 0,
        MATCH_MODE_CLASSIC = 1,
        MATCH_MODE_CHONGCI = 2
    }

    /** Properties of a ChongciConfig. */
    interface IChongciConfig {

        /** ChongciConfig startingScore */
        startingScore?: (number|undefined);

        /** ChongciConfig bustThreshold */
        bustThreshold?: (number|undefined);

        /** ChongciConfig maxHands */
        maxHands?: (number|undefined);
    }

    /** Represents a ChongciConfig. */
    class ChongciConfig implements IChongciConfig {

        /**
         * Constructs a new ChongciConfig.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IChongciConfig);

        /** ChongciConfig startingScore. */
        public startingScore: number;

        /** ChongciConfig bustThreshold. */
        public bustThreshold: number;

        /** ChongciConfig maxHands. */
        public maxHands: number;

        /**
         * Creates a new ChongciConfig instance using the specified properties.
         * @param [properties] Properties to set
         * @returns ChongciConfig instance
         */
        public static create(properties?: game.IChongciConfig): game.ChongciConfig;

        /**
         * Encodes the specified ChongciConfig message. Does not implicitly {@link game.ChongciConfig.verify|verify} messages.
         * @param message ChongciConfig message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IChongciConfig, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified ChongciConfig message, length delimited. Does not implicitly {@link game.ChongciConfig.verify|verify} messages.
         * @param message ChongciConfig message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IChongciConfig, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a ChongciConfig message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns ChongciConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.ChongciConfig;

        /**
         * Decodes a ChongciConfig message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns ChongciConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.ChongciConfig;

        /**
         * Verifies a ChongciConfig message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a ChongciConfig message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns ChongciConfig
         */
        public static fromObject(object: { [k: string]: any }): game.ChongciConfig;

        /**
         * Creates a plain object from a ChongciConfig message. Also converts values to other types if specified.
         * @param message ChongciConfig
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.ChongciConfig, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this ChongciConfig to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for ChongciConfig
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a PlayerStanding. */
    interface IPlayerStanding {

        /** PlayerStanding seat */
        seat?: (number|undefined);

        /** PlayerStanding rank */
        rank?: (number|undefined);

        /** PlayerStanding finalScore */
        finalScore?: (number|undefined);

        /** PlayerStanding netChange */
        netChange?: (number|undefined);
    }

    /** Represents a PlayerStanding. */
    class PlayerStanding implements IPlayerStanding {

        /**
         * Constructs a new PlayerStanding.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IPlayerStanding);

        /** PlayerStanding seat. */
        public seat: number;

        /** PlayerStanding rank. */
        public rank: number;

        /** PlayerStanding finalScore. */
        public finalScore: number;

        /** PlayerStanding netChange. */
        public netChange: number;

        /**
         * Creates a new PlayerStanding instance using the specified properties.
         * @param [properties] Properties to set
         * @returns PlayerStanding instance
         */
        public static create(properties?: game.IPlayerStanding): game.PlayerStanding;

        /**
         * Encodes the specified PlayerStanding message. Does not implicitly {@link game.PlayerStanding.verify|verify} messages.
         * @param message PlayerStanding message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IPlayerStanding, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified PlayerStanding message, length delimited. Does not implicitly {@link game.PlayerStanding.verify|verify} messages.
         * @param message PlayerStanding message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IPlayerStanding, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a PlayerStanding message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns PlayerStanding
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.PlayerStanding;

        /**
         * Decodes a PlayerStanding message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns PlayerStanding
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.PlayerStanding;

        /**
         * Verifies a PlayerStanding message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a PlayerStanding message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns PlayerStanding
         */
        public static fromObject(object: { [k: string]: any }): game.PlayerStanding;

        /**
         * Creates a plain object from a PlayerStanding message. Also converts values to other types if specified.
         * @param message PlayerStanding
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.PlayerStanding, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this PlayerStanding to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for PlayerStanding
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a MatchEndResult. */
    interface IMatchEndResult {

        /** MatchEndResult reason */
        reason?: (string|undefined);

        /** MatchEndResult finalHandNum */
        finalHandNum?: (number|undefined);

        /** MatchEndResult standings */
        standings?: (game.IPlayerStanding[]|undefined);
    }

    /** Represents a MatchEndResult. */
    class MatchEndResult implements IMatchEndResult {

        /**
         * Constructs a new MatchEndResult.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IMatchEndResult);

        /** MatchEndResult reason. */
        public reason: string;

        /** MatchEndResult finalHandNum. */
        public finalHandNum: number;

        /** MatchEndResult standings. */
        public standings: game.PlayerStanding[];

        /**
         * Creates a new MatchEndResult instance using the specified properties.
         * @param [properties] Properties to set
         * @returns MatchEndResult instance
         */
        public static create(properties?: game.IMatchEndResult): game.MatchEndResult;

        /**
         * Encodes the specified MatchEndResult message. Does not implicitly {@link game.MatchEndResult.verify|verify} messages.
         * @param message MatchEndResult message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IMatchEndResult, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified MatchEndResult message, length delimited. Does not implicitly {@link game.MatchEndResult.verify|verify} messages.
         * @param message MatchEndResult message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IMatchEndResult, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a MatchEndResult message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns MatchEndResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.MatchEndResult;

        /**
         * Decodes a MatchEndResult message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns MatchEndResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.MatchEndResult;

        /**
         * Verifies a MatchEndResult message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a MatchEndResult message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns MatchEndResult
         */
        public static fromObject(object: { [k: string]: any }): game.MatchEndResult;

        /**
         * Creates a plain object from a MatchEndResult message. Also converts values to other types if specified.
         * @param message MatchEndResult
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.MatchEndResult, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this MatchEndResult to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for MatchEndResult
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of an EnvPoolNewRequest. */
    interface IEnvPoolNewRequest {

        /** EnvPoolNewRequest config */
        config?: (game.IEnvConfig|undefined);

        /** EnvPoolNewRequest slots */
        slots?: (number|undefined);
    }

    /** Represents an EnvPoolNewRequest. */
    class EnvPoolNewRequest implements IEnvPoolNewRequest {

        /**
         * Constructs a new EnvPoolNewRequest.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IEnvPoolNewRequest);

        /** EnvPoolNewRequest config. */
        public config: game.EnvConfig;

        /** EnvPoolNewRequest slots. */
        public slots: number;

        /**
         * Creates a new EnvPoolNewRequest instance using the specified properties.
         * @param [properties] Properties to set
         * @returns EnvPoolNewRequest instance
         */
        public static create(properties?: game.IEnvPoolNewRequest): game.EnvPoolNewRequest;

        /**
         * Encodes the specified EnvPoolNewRequest message. Does not implicitly {@link game.EnvPoolNewRequest.verify|verify} messages.
         * @param message EnvPoolNewRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IEnvPoolNewRequest, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified EnvPoolNewRequest message, length delimited. Does not implicitly {@link game.EnvPoolNewRequest.verify|verify} messages.
         * @param message EnvPoolNewRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IEnvPoolNewRequest, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an EnvPoolNewRequest message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns EnvPoolNewRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.EnvPoolNewRequest;

        /**
         * Decodes an EnvPoolNewRequest message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns EnvPoolNewRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.EnvPoolNewRequest;

        /**
         * Verifies an EnvPoolNewRequest message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an EnvPoolNewRequest message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns EnvPoolNewRequest
         */
        public static fromObject(object: { [k: string]: any }): game.EnvPoolNewRequest;

        /**
         * Creates a plain object from an EnvPoolNewRequest message. Also converts values to other types if specified.
         * @param message EnvPoolNewRequest
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.EnvPoolNewRequest, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this EnvPoolNewRequest to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for EnvPoolNewRequest
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a SlotCommand. */
    interface ISlotCommand {

        /** SlotCommand slot */
        slot?: (number|undefined);

        /** SlotCommand actionId */
        actionId?: (number|null|undefined);

        /** SlotCommand resetSeed */
        resetSeed?: (number|Long|null|undefined);

        /** SlotCommand skip */
        skip?: (boolean|null|undefined);
    }

    /** Represents a SlotCommand. */
    class SlotCommand implements ISlotCommand {

        /**
         * Constructs a new SlotCommand.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.ISlotCommand);

        /** SlotCommand slot. */
        public slot: number;

        /** SlotCommand actionId. */
        public actionId: (number|null);

        /** SlotCommand resetSeed. */
        public resetSeed: (number|Long|null);

        /** SlotCommand skip. */
        public skip: (boolean|null);

        /** SlotCommand cmd. */
        public cmd?: ("actionId"|"resetSeed"|"skip");

        /**
         * Creates a new SlotCommand instance using the specified properties.
         * @param [properties] Properties to set
         * @returns SlotCommand instance
         */
        public static create(properties?: game.ISlotCommand): game.SlotCommand;

        /**
         * Encodes the specified SlotCommand message. Does not implicitly {@link game.SlotCommand.verify|verify} messages.
         * @param message SlotCommand message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.ISlotCommand, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified SlotCommand message, length delimited. Does not implicitly {@link game.SlotCommand.verify|verify} messages.
         * @param message SlotCommand message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.ISlotCommand, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a SlotCommand message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns SlotCommand
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.SlotCommand;

        /**
         * Decodes a SlotCommand message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns SlotCommand
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.SlotCommand;

        /**
         * Verifies a SlotCommand message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a SlotCommand message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns SlotCommand
         */
        public static fromObject(object: { [k: string]: any }): game.SlotCommand;

        /**
         * Creates a plain object from a SlotCommand message. Also converts values to other types if specified.
         * @param message SlotCommand
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.SlotCommand, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this SlotCommand to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for SlotCommand
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of an EnvPoolStepRequest. */
    interface IEnvPoolStepRequest {

        /** EnvPoolStepRequest commands */
        commands?: (game.ISlotCommand[]|undefined);
    }

    /** Represents an EnvPoolStepRequest. */
    class EnvPoolStepRequest implements IEnvPoolStepRequest {

        /**
         * Constructs a new EnvPoolStepRequest.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IEnvPoolStepRequest);

        /** EnvPoolStepRequest commands. */
        public commands: game.SlotCommand[];

        /**
         * Creates a new EnvPoolStepRequest instance using the specified properties.
         * @param [properties] Properties to set
         * @returns EnvPoolStepRequest instance
         */
        public static create(properties?: game.IEnvPoolStepRequest): game.EnvPoolStepRequest;

        /**
         * Encodes the specified EnvPoolStepRequest message. Does not implicitly {@link game.EnvPoolStepRequest.verify|verify} messages.
         * @param message EnvPoolStepRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IEnvPoolStepRequest, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified EnvPoolStepRequest message, length delimited. Does not implicitly {@link game.EnvPoolStepRequest.verify|verify} messages.
         * @param message EnvPoolStepRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IEnvPoolStepRequest, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an EnvPoolStepRequest message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns EnvPoolStepRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.EnvPoolStepRequest;

        /**
         * Decodes an EnvPoolStepRequest message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns EnvPoolStepRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.EnvPoolStepRequest;

        /**
         * Verifies an EnvPoolStepRequest message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an EnvPoolStepRequest message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns EnvPoolStepRequest
         */
        public static fromObject(object: { [k: string]: any }): game.EnvPoolStepRequest;

        /**
         * Creates a plain object from an EnvPoolStepRequest message. Also converts values to other types if specified.
         * @param message EnvPoolStepRequest
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.EnvPoolStepRequest, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this EnvPoolStepRequest to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for EnvPoolStepRequest
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of a SlotState. */
    interface ISlotState {

        /** SlotState slot */
        slot?: (number|undefined);

        /** SlotState seat */
        seat?: (number|undefined);

        /** SlotState terminated */
        terminated?: (boolean|undefined);

        /** SlotState truncated */
        truncated?: (boolean|undefined);

        /** SlotState stepRewards */
        stepRewards?: (number[]|undefined);

        /** SlotState hasObservation */
        hasObservation?: (boolean|undefined);

        /** SlotState roundOutcome */
        roundOutcome?: (game.IRoundOutcome|undefined);

        /** SlotState error */
        error?: (string|undefined);
    }

    /** Represents a SlotState. */
    class SlotState implements ISlotState {

        /**
         * Constructs a new SlotState.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.ISlotState);

        /** SlotState slot. */
        public slot: number;

        /** SlotState seat. */
        public seat: number;

        /** SlotState terminated. */
        public terminated: boolean;

        /** SlotState truncated. */
        public truncated: boolean;

        /** SlotState stepRewards. */
        public stepRewards: number[];

        /** SlotState hasObservation. */
        public hasObservation: boolean;

        /** SlotState roundOutcome. */
        public roundOutcome: game.RoundOutcome;

        /** SlotState error. */
        public error: string;

        /**
         * Creates a new SlotState instance using the specified properties.
         * @param [properties] Properties to set
         * @returns SlotState instance
         */
        public static create(properties?: game.ISlotState): game.SlotState;

        /**
         * Encodes the specified SlotState message. Does not implicitly {@link game.SlotState.verify|verify} messages.
         * @param message SlotState message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.ISlotState, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified SlotState message, length delimited. Does not implicitly {@link game.SlotState.verify|verify} messages.
         * @param message SlotState message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.ISlotState, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a SlotState message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns SlotState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.SlotState;

        /**
         * Decodes a SlotState message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns SlotState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.SlotState;

        /**
         * Verifies a SlotState message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a SlotState message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns SlotState
         */
        public static fromObject(object: { [k: string]: any }): game.SlotState;

        /**
         * Creates a plain object from a SlotState message. Also converts values to other types if specified.
         * @param message SlotState
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.SlotState, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this SlotState to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for SlotState
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }

    /** Properties of an EnvPoolStepResponse. */
    interface IEnvPoolStepResponse {

        /** EnvPoolStepResponse slots */
        slots?: (game.ISlotState[]|undefined);

        /** EnvPoolStepResponse planes */
        planes?: (Uint8Array|undefined);

        /** EnvPoolStepResponse scalars */
        scalars?: (Uint8Array|undefined);

        /** EnvPoolStepResponse actionMasks */
        actionMasks?: (Uint8Array|undefined);

        /** EnvPoolStepResponse planeChannels */
        planeChannels?: (number|undefined);

        /** EnvPoolStepResponse planeHeight */
        planeHeight?: (number|undefined);

        /** EnvPoolStepResponse planeWidth */
        planeWidth?: (number|undefined);

        /** EnvPoolStepResponse scalarCount */
        scalarCount?: (number|undefined);

        /** EnvPoolStepResponse actionSpaceSize */
        actionSpaceSize?: (number|undefined);
    }

    /** Represents an EnvPoolStepResponse. */
    class EnvPoolStepResponse implements IEnvPoolStepResponse {

        /**
         * Constructs a new EnvPoolStepResponse.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.IEnvPoolStepResponse);

        /** EnvPoolStepResponse slots. */
        public slots: game.SlotState[];

        /** EnvPoolStepResponse planes. */
        public planes: Uint8Array;

        /** EnvPoolStepResponse scalars. */
        public scalars: Uint8Array;

        /** EnvPoolStepResponse actionMasks. */
        public actionMasks: Uint8Array;

        /** EnvPoolStepResponse planeChannels. */
        public planeChannels: number;

        /** EnvPoolStepResponse planeHeight. */
        public planeHeight: number;

        /** EnvPoolStepResponse planeWidth. */
        public planeWidth: number;

        /** EnvPoolStepResponse scalarCount. */
        public scalarCount: number;

        /** EnvPoolStepResponse actionSpaceSize. */
        public actionSpaceSize: number;

        /**
         * Creates a new EnvPoolStepResponse instance using the specified properties.
         * @param [properties] Properties to set
         * @returns EnvPoolStepResponse instance
         */
        public static create(properties?: game.IEnvPoolStepResponse): game.EnvPoolStepResponse;

        /**
         * Encodes the specified EnvPoolStepResponse message. Does not implicitly {@link game.EnvPoolStepResponse.verify|verify} messages.
         * @param message EnvPoolStepResponse message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encode(message: game.IEnvPoolStepResponse, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified EnvPoolStepResponse message, length delimited. Does not implicitly {@link game.EnvPoolStepResponse.verify|verify} messages.
         * @param message EnvPoolStepResponse message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        public static encodeDelimited(message: game.IEnvPoolStepResponse, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an EnvPoolStepResponse message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns EnvPoolStepResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.EnvPoolStepResponse;

        /**
         * Decodes an EnvPoolStepResponse message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns EnvPoolStepResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        public static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.EnvPoolStepResponse;

        /**
         * Verifies an EnvPoolStepResponse message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        public static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an EnvPoolStepResponse message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns EnvPoolStepResponse
         */
        public static fromObject(object: { [k: string]: any }): game.EnvPoolStepResponse;

        /**
         * Creates a plain object from an EnvPoolStepResponse message. Also converts values to other types if specified.
         * @param message EnvPoolStepResponse
         * @param [options] Conversion options
         * @returns Plain object
         */
        public static toObject(message: game.EnvPoolStepResponse, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this EnvPoolStepResponse to JSON.
         * @returns JSON object
         */
        public toJSON(): { [k: string]: any };

        /**
         * Gets the default type url for EnvPoolStepResponse
         * @param [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns The default type url
         */
        public static getTypeUrl(typeUrlPrefix?: string): string;
    }
}
