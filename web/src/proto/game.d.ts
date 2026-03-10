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
        ACTION_READY = 10
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
        calledTileId?: (number|undefined);
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
        public calledTileId: number;

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
        PHASE_ROUND_END = 4
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
}
