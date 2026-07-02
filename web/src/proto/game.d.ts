import * as $protobuf from "protobufjs";
import Long = require("long");

/** Namespace game. */
export namespace game {

    /** Suit enum. */
    enum Suit {

        /** SUIT_UNKNOWN value */
        SUIT_UNKNOWN = 0,

        /** SUIT_SOU value */
        SUIT_SOU = 1,

        /** SUIT_PIN value */
        SUIT_PIN = 2,

        /** SUIT_MAN value */
        SUIT_MAN = 3,

        /** SUIT_JIHAI value */
        SUIT_JIHAI = 4,

        /** SUIT_FLOWER value */
        SUIT_FLOWER = 5
    }

    /**
     * Properties of a Tile.
     * @deprecated Use game.Tile.$Properties instead.
     */
    interface ITile extends game.Tile.$Properties {
    }

    /** Represents a Tile. */
    class Tile {

        /**
         * Constructs a new Tile.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.Tile.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** Tile id. */
        id: number;

        /** Tile suit. */
        suit: game.Suit;

        /** Tile value. */
        value: number;

        /**
         * Creates a new Tile instance using the specified properties.
         * @param [properties] Properties to set
         * @returns Tile instance
         */
        static create(properties: game.Tile.$Shape): game.Tile & game.Tile.$Shape;
        static create(properties?: game.Tile.$Properties): game.Tile;

        /**
         * Encodes the specified Tile message. Does not implicitly {@link game.Tile.verify|verify} messages.
         * @param message Tile message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.Tile.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified Tile message, length delimited. Does not implicitly {@link game.Tile.verify|verify} messages.
         * @param message Tile message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.Tile.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a Tile message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.Tile & game.Tile.$Shape} Tile
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.Tile & game.Tile.$Shape;

        /**
         * Decodes a Tile message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.Tile & game.Tile.$Shape} Tile
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.Tile & game.Tile.$Shape;

        /**
         * Verifies a Tile message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a Tile message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns Tile
         */
        static fromObject(object: { [k: string]: any }): game.Tile;

        /**
         * Creates a plain object from a Tile message. Also converts values to other types if specified.
         * @param message Tile
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.Tile, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this Tile to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for Tile
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace Tile {

        /** Properties of a Tile. */
        interface $Properties {

            /** Tile id */
            id?: number;

            /** Tile suit */
            suit?: game.Suit;

            /** Tile value */
            value?: number;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a Tile. */
        type $Shape = game.Tile.$Properties;
    }

    /** ActionType enum. */
    enum ActionType {

        /** ACTION_UNKNOWN value */
        ACTION_UNKNOWN = 0,

        /** ACTION_DRAW value */
        ACTION_DRAW = 1,

        /** ACTION_DISCARD value */
        ACTION_DISCARD = 2,

        /** ACTION_CHII value */
        ACTION_CHII = 3,

        /** ACTION_PON value */
        ACTION_PON = 4,

        /** ACTION_KAN value */
        ACTION_KAN = 5,

        /** ACTION_TSUMO value */
        ACTION_TSUMO = 6,

        /** ACTION_RON value */
        ACTION_RON = 7,

        /** ACTION_PASS value */
        ACTION_PASS = 8,

        /** ACTION_FLOWER_REVEAL value */
        ACTION_FLOWER_REVEAL = 9,

        /** ACTION_READY value */
        ACTION_READY = 10,

        /** ACTION_ACCEPT_HAITEI value */
        ACTION_ACCEPT_HAITEI = 11,

        /** ACTION_REFUSE_HAITEI value */
        ACTION_REFUSE_HAITEI = 12
    }

    /**
     * Properties of a PlayerAction.
     * @deprecated Use game.PlayerAction.$Properties instead.
     */
    interface IPlayerAction extends game.PlayerAction.$Properties {
    }

    /** Represents a PlayerAction. */
    class PlayerAction {

        /**
         * Constructs a new PlayerAction.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.PlayerAction.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** PlayerAction type. */
        type: game.ActionType;

        /** PlayerAction tile. */
        tile: game.Tile;

        /** PlayerAction meldTiles. */
        meldTiles: game.Tile[];

        /** PlayerAction targetPlayer. */
        targetPlayer: number;

        /** PlayerAction isRobbingKong. */
        isRobbingKong: boolean;

        /** PlayerAction isBottomTile. */
        isBottomTile: boolean;

        /** PlayerAction isBloomingKong. */
        isBloomingKong: boolean;

        /**
         * Creates a new PlayerAction instance using the specified properties.
         * @param [properties] Properties to set
         * @returns PlayerAction instance
         */
        static create(properties: game.PlayerAction.$Shape): game.PlayerAction & game.PlayerAction.$Shape;
        static create(properties?: game.PlayerAction.$Properties): game.PlayerAction;

        /**
         * Encodes the specified PlayerAction message. Does not implicitly {@link game.PlayerAction.verify|verify} messages.
         * @param message PlayerAction message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.PlayerAction.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified PlayerAction message, length delimited. Does not implicitly {@link game.PlayerAction.verify|verify} messages.
         * @param message PlayerAction message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.PlayerAction.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a PlayerAction message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.PlayerAction & game.PlayerAction.$Shape} PlayerAction
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.PlayerAction & game.PlayerAction.$Shape;

        /**
         * Decodes a PlayerAction message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.PlayerAction & game.PlayerAction.$Shape} PlayerAction
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.PlayerAction & game.PlayerAction.$Shape;

        /**
         * Verifies a PlayerAction message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a PlayerAction message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns PlayerAction
         */
        static fromObject(object: { [k: string]: any }): game.PlayerAction;

        /**
         * Creates a plain object from a PlayerAction message. Also converts values to other types if specified.
         * @param message PlayerAction
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.PlayerAction, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this PlayerAction to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for PlayerAction
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace PlayerAction {

        /** Properties of a PlayerAction. */
        interface $Properties {

            /** PlayerAction type */
            type?: game.ActionType;

            /** PlayerAction tile */
            tile?: game.Tile.$Properties;

            /** PlayerAction meldTiles */
            meldTiles?: game.Tile.$Properties[];

            /** PlayerAction targetPlayer */
            targetPlayer?: number;

            /** PlayerAction isRobbingKong */
            isRobbingKong?: boolean;

            /** PlayerAction isBottomTile */
            isBottomTile?: boolean;

            /** PlayerAction isBloomingKong */
            isBloomingKong?: boolean;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a PlayerAction. */
        type $Shape = game.PlayerAction.$Properties;
    }

    /** MeldDirection enum. */
    enum MeldDirection {

        /** MELD_DIRECTION_UNKNOWN value */
        MELD_DIRECTION_UNKNOWN = 0,

        /** MELD_DIRECTION_RIGHT value */
        MELD_DIRECTION_RIGHT = 1,

        /** MELD_DIRECTION_ACROSS value */
        MELD_DIRECTION_ACROSS = 2,

        /** MELD_DIRECTION_LEFT value */
        MELD_DIRECTION_LEFT = 3
    }

    /**
     * Properties of a Meld.
     * @deprecated Use game.Meld.$Properties instead.
     */
    interface IMeld extends game.Meld.$Properties {
    }

    /** Represents a Meld. */
    class Meld {

        /**
         * Constructs a new Meld.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.Meld.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** Meld type. */
        type: game.ActionType;

        /** Meld tiles. */
        tiles: game.Tile[];

        /** Meld calledDirection. */
        calledDirection: game.MeldDirection;

        /** Meld calledTileId. */
        calledTileId: (number|null);

        /** Meld addedTileId. */
        addedTileId: (number|null);

        /**
         * Creates a new Meld instance using the specified properties.
         * @param [properties] Properties to set
         * @returns Meld instance
         */
        static create(properties: game.Meld.$Shape): game.Meld & game.Meld.$Shape;
        static create(properties?: game.Meld.$Properties): game.Meld;

        /**
         * Encodes the specified Meld message. Does not implicitly {@link game.Meld.verify|verify} messages.
         * @param message Meld message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.Meld.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified Meld message, length delimited. Does not implicitly {@link game.Meld.verify|verify} messages.
         * @param message Meld message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.Meld.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a Meld message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.Meld & game.Meld.$Shape} Meld
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.Meld & game.Meld.$Shape;

        /**
         * Decodes a Meld message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.Meld & game.Meld.$Shape} Meld
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.Meld & game.Meld.$Shape;

        /**
         * Verifies a Meld message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a Meld message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns Meld
         */
        static fromObject(object: { [k: string]: any }): game.Meld;

        /**
         * Creates a plain object from a Meld message. Also converts values to other types if specified.
         * @param message Meld
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.Meld, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this Meld to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for Meld
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace Meld {

        /** Properties of a Meld. */
        interface $Properties {

            /** Meld type */
            type?: game.ActionType;

            /** Meld tiles */
            tiles?: game.Tile.$Properties[];

            /** Meld calledDirection */
            calledDirection?: game.MeldDirection;

            /** Meld calledTileId */
            calledTileId?: (number|null);

            /** Meld addedTileId */
            addedTileId?: (number|null);

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a Meld. */
        type $Shape = game.Meld.$Properties;
    }

    /**
     * Properties of a PlayerState.
     * @deprecated Use game.PlayerState.$Properties instead.
     */
    interface IPlayerState extends game.PlayerState.$Properties {
    }

    /** Represents a PlayerState. */
    class PlayerState {

        /**
         * Constructs a new PlayerState.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.PlayerState.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** PlayerState seat. */
        seat: number;

        /** PlayerState score. */
        score: number;

        /** PlayerState closedHand. */
        closedHand: game.Tile[];

        /** PlayerState handSize. */
        handSize: number;

        /** PlayerState openMelds. */
        openMelds: game.Meld[];

        /** PlayerState discards. */
        discards: game.Tile[];

        /** PlayerState seatWind. */
        seatWind: number;

        /** PlayerState flowerMelds. */
        flowerMelds: game.Tile[];

        /** PlayerState hasBuddingDirectKong. */
        hasBuddingDirectKong: boolean;

        /** PlayerState hasBloomingDirectKong. */
        hasBloomingDirectKong: boolean;

        /** PlayerState hasBuddingClosedKong. */
        hasBuddingClosedKong: boolean;

        /** PlayerState hasBloomingClosedKong. */
        hasBloomingClosedKong: boolean;

        /** PlayerState hasBuddingRiskyKong. */
        hasBuddingRiskyKong: boolean;

        /** PlayerState hasBloomingRiskyKong. */
        hasBloomingRiskyKong: boolean;

        /** PlayerState hasBloomingFlowerKong. */
        hasBloomingFlowerKong: boolean;

        /** PlayerState validActions. */
        validActions: game.PlayerAction[];

        /** PlayerState drawnTileId. */
        drawnTileId: (number|null);

        /** PlayerState shanten. */
        shanten: number;

        /** PlayerState lastDiscardFromDrawn. */
        lastDiscardFromDrawn: boolean;

        /**
         * Creates a new PlayerState instance using the specified properties.
         * @param [properties] Properties to set
         * @returns PlayerState instance
         */
        static create(properties: game.PlayerState.$Shape): game.PlayerState & game.PlayerState.$Shape;
        static create(properties?: game.PlayerState.$Properties): game.PlayerState;

        /**
         * Encodes the specified PlayerState message. Does not implicitly {@link game.PlayerState.verify|verify} messages.
         * @param message PlayerState message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.PlayerState.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified PlayerState message, length delimited. Does not implicitly {@link game.PlayerState.verify|verify} messages.
         * @param message PlayerState message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.PlayerState.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a PlayerState message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.PlayerState & game.PlayerState.$Shape} PlayerState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.PlayerState & game.PlayerState.$Shape;

        /**
         * Decodes a PlayerState message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.PlayerState & game.PlayerState.$Shape} PlayerState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.PlayerState & game.PlayerState.$Shape;

        /**
         * Verifies a PlayerState message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a PlayerState message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns PlayerState
         */
        static fromObject(object: { [k: string]: any }): game.PlayerState;

        /**
         * Creates a plain object from a PlayerState message. Also converts values to other types if specified.
         * @param message PlayerState
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.PlayerState, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this PlayerState to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for PlayerState
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace PlayerState {

        /** Properties of a PlayerState. */
        interface $Properties {

            /** PlayerState seat */
            seat?: number;

            /** PlayerState score */
            score?: number;

            /** PlayerState closedHand */
            closedHand?: game.Tile.$Properties[];

            /** PlayerState handSize */
            handSize?: number;

            /** PlayerState openMelds */
            openMelds?: game.Meld.$Properties[];

            /** PlayerState discards */
            discards?: game.Tile.$Properties[];

            /** PlayerState seatWind */
            seatWind?: number;

            /** PlayerState flowerMelds */
            flowerMelds?: game.Tile.$Properties[];

            /** PlayerState hasBuddingDirectKong */
            hasBuddingDirectKong?: boolean;

            /** PlayerState hasBloomingDirectKong */
            hasBloomingDirectKong?: boolean;

            /** PlayerState hasBuddingClosedKong */
            hasBuddingClosedKong?: boolean;

            /** PlayerState hasBloomingClosedKong */
            hasBloomingClosedKong?: boolean;

            /** PlayerState hasBuddingRiskyKong */
            hasBuddingRiskyKong?: boolean;

            /** PlayerState hasBloomingRiskyKong */
            hasBloomingRiskyKong?: boolean;

            /** PlayerState hasBloomingFlowerKong */
            hasBloomingFlowerKong?: boolean;

            /** PlayerState validActions */
            validActions?: game.PlayerAction.$Properties[];

            /** PlayerState drawnTileId */
            drawnTileId?: (number|null);

            /** PlayerState shanten */
            shanten?: number;

            /** PlayerState lastDiscardFromDrawn */
            lastDiscardFromDrawn?: boolean;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a PlayerState. */
        type $Shape = game.PlayerState.$Properties;
    }

    /** GamePhase enum. */
    enum GamePhase {

        /** PHASE_INIT value */
        PHASE_INIT = 0,

        /** PHASE_DEAL value */
        PHASE_DEAL = 1,

        /** PHASE_PLAYER_TURN value */
        PHASE_PLAYER_TURN = 2,

        /** PHASE_WAIT_DISCARDS value */
        PHASE_WAIT_DISCARDS = 3,

        /** PHASE_ROUND_END value */
        PHASE_ROUND_END = 4,

        /** PHASE_MATCH_END value */
        PHASE_MATCH_END = 5
    }

    /**
     * Properties of a GameState.
     * @deprecated Use game.GameState.$Properties instead.
     */
    interface IGameState extends game.GameState.$Properties {
    }

    /** Represents a GameState. */
    class GameState {

        /**
         * Constructs a new GameState.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.GameState.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** GameState matchId. */
        matchId: string;

        /** GameState phase. */
        phase: game.GamePhase;

        /** GameState activePlayer. */
        activePlayer: number;

        /** GameState players. */
        players: game.PlayerState[];

        /** GameState wallCount. */
        wallCount: number;

        /** GameState handNum. */
        handNum: number;

        /** GameState activeDiscard. */
        activeDiscard: game.Tile;

        /** GameState wildTiles. */
        wildTiles: game.Tile[];

        /** GameState prevailingWind. */
        prevailingWind: number;

        /** GameState wallSeed. */
        wallSeed: string;

        /** GameState roundResult. */
        roundResult: game.RoundResult;

        /** GameState playerReady. */
        playerReady: boolean[];

        /** GameState diceSum. */
        diceSum: number;

        /** GameState wangpaiStacks. */
        wangpaiStacks: number;

        /** GameState isHaitei. */
        isHaitei: boolean;

        /** GameState dice1. */
        dice1: number;

        /** GameState dice2. */
        dice2: number;

        /** GameState wangpaiTilesLeft. */
        wangpaiTilesLeft: number;

        /** GameState matchMode. */
        matchMode: game.MatchMode;

        /** GameState chongciConfig. */
        chongciConfig: game.ChongciConfig;

        /** GameState matchEndResult. */
        matchEndResult: game.MatchEndResult;

        /**
         * Creates a new GameState instance using the specified properties.
         * @param [properties] Properties to set
         * @returns GameState instance
         */
        static create(properties: game.GameState.$Shape): game.GameState & game.GameState.$Shape;
        static create(properties?: game.GameState.$Properties): game.GameState;

        /**
         * Encodes the specified GameState message. Does not implicitly {@link game.GameState.verify|verify} messages.
         * @param message GameState message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.GameState.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified GameState message, length delimited. Does not implicitly {@link game.GameState.verify|verify} messages.
         * @param message GameState message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.GameState.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a GameState message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.GameState & game.GameState.$Shape} GameState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.GameState & game.GameState.$Shape;

        /**
         * Decodes a GameState message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.GameState & game.GameState.$Shape} GameState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.GameState & game.GameState.$Shape;

        /**
         * Verifies a GameState message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a GameState message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns GameState
         */
        static fromObject(object: { [k: string]: any }): game.GameState;

        /**
         * Creates a plain object from a GameState message. Also converts values to other types if specified.
         * @param message GameState
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.GameState, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this GameState to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for GameState
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace GameState {

        /** Properties of a GameState. */
        interface $Properties {

            /** GameState matchId */
            matchId?: string;

            /** GameState phase */
            phase?: game.GamePhase;

            /** GameState activePlayer */
            activePlayer?: number;

            /** GameState players */
            players?: game.PlayerState.$Properties[];

            /** GameState wallCount */
            wallCount?: number;

            /** GameState handNum */
            handNum?: number;

            /** GameState activeDiscard */
            activeDiscard?: game.Tile.$Properties;

            /** GameState wildTiles */
            wildTiles?: game.Tile.$Properties[];

            /** GameState prevailingWind */
            prevailingWind?: number;

            /** GameState wallSeed */
            wallSeed?: string;

            /** GameState roundResult */
            roundResult?: game.RoundResult.$Properties;

            /** GameState playerReady */
            playerReady?: boolean[];

            /** GameState diceSum */
            diceSum?: number;

            /** GameState wangpaiStacks */
            wangpaiStacks?: number;

            /** GameState isHaitei */
            isHaitei?: boolean;

            /** GameState dice1 */
            dice1?: number;

            /** GameState dice2 */
            dice2?: number;

            /** GameState wangpaiTilesLeft */
            wangpaiTilesLeft?: number;

            /** GameState matchMode */
            matchMode?: game.MatchMode;

            /** GameState chongciConfig */
            chongciConfig?: game.ChongciConfig.$Properties;

            /** GameState matchEndResult */
            matchEndResult?: game.MatchEndResult.$Properties;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a GameState. */
        type $Shape = game.GameState.$Properties;
    }

    /**
     * Properties of a ScoreEntry.
     * @deprecated Use game.ScoreEntry.$Properties instead.
     */
    interface IScoreEntry extends game.ScoreEntry.$Properties {
    }

    /** Represents a ScoreEntry. */
    class ScoreEntry {

        /**
         * Constructs a new ScoreEntry.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.ScoreEntry.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** ScoreEntry patternName. */
        patternName: string;

        /** ScoreEntry points. */
        points: number;

        /** ScoreEntry patternId. */
        patternId: string;

        /**
         * Creates a new ScoreEntry instance using the specified properties.
         * @param [properties] Properties to set
         * @returns ScoreEntry instance
         */
        static create(properties: game.ScoreEntry.$Shape): game.ScoreEntry & game.ScoreEntry.$Shape;
        static create(properties?: game.ScoreEntry.$Properties): game.ScoreEntry;

        /**
         * Encodes the specified ScoreEntry message. Does not implicitly {@link game.ScoreEntry.verify|verify} messages.
         * @param message ScoreEntry message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.ScoreEntry.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified ScoreEntry message, length delimited. Does not implicitly {@link game.ScoreEntry.verify|verify} messages.
         * @param message ScoreEntry message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.ScoreEntry.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a ScoreEntry message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.ScoreEntry & game.ScoreEntry.$Shape} ScoreEntry
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.ScoreEntry & game.ScoreEntry.$Shape;

        /**
         * Decodes a ScoreEntry message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.ScoreEntry & game.ScoreEntry.$Shape} ScoreEntry
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.ScoreEntry & game.ScoreEntry.$Shape;

        /**
         * Verifies a ScoreEntry message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a ScoreEntry message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns ScoreEntry
         */
        static fromObject(object: { [k: string]: any }): game.ScoreEntry;

        /**
         * Creates a plain object from a ScoreEntry message. Also converts values to other types if specified.
         * @param message ScoreEntry
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.ScoreEntry, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this ScoreEntry to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for ScoreEntry
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace ScoreEntry {

        /** Properties of a ScoreEntry. */
        interface $Properties {

            /** ScoreEntry patternName */
            patternName?: string;

            /** ScoreEntry points */
            points?: number;

            /** ScoreEntry patternId */
            patternId?: string;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a ScoreEntry. */
        type $Shape = game.ScoreEntry.$Properties;
    }

    /**
     * Properties of a PlayerPayout.
     * @deprecated Use game.PlayerPayout.$Properties instead.
     */
    interface IPlayerPayout extends game.PlayerPayout.$Properties {
    }

    /** Represents a PlayerPayout. */
    class PlayerPayout {

        /**
         * Constructs a new PlayerPayout.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.PlayerPayout.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** PlayerPayout seat. */
        seat: number;

        /** PlayerPayout amount. */
        amount: number;

        /**
         * Creates a new PlayerPayout instance using the specified properties.
         * @param [properties] Properties to set
         * @returns PlayerPayout instance
         */
        static create(properties: game.PlayerPayout.$Shape): game.PlayerPayout & game.PlayerPayout.$Shape;
        static create(properties?: game.PlayerPayout.$Properties): game.PlayerPayout;

        /**
         * Encodes the specified PlayerPayout message. Does not implicitly {@link game.PlayerPayout.verify|verify} messages.
         * @param message PlayerPayout message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.PlayerPayout.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified PlayerPayout message, length delimited. Does not implicitly {@link game.PlayerPayout.verify|verify} messages.
         * @param message PlayerPayout message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.PlayerPayout.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a PlayerPayout message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.PlayerPayout & game.PlayerPayout.$Shape} PlayerPayout
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.PlayerPayout & game.PlayerPayout.$Shape;

        /**
         * Decodes a PlayerPayout message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.PlayerPayout & game.PlayerPayout.$Shape} PlayerPayout
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.PlayerPayout & game.PlayerPayout.$Shape;

        /**
         * Verifies a PlayerPayout message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a PlayerPayout message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns PlayerPayout
         */
        static fromObject(object: { [k: string]: any }): game.PlayerPayout;

        /**
         * Creates a plain object from a PlayerPayout message. Also converts values to other types if specified.
         * @param message PlayerPayout
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.PlayerPayout, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this PlayerPayout to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for PlayerPayout
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace PlayerPayout {

        /** Properties of a PlayerPayout. */
        interface $Properties {

            /** PlayerPayout seat */
            seat?: number;

            /** PlayerPayout amount */
            amount?: number;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a PlayerPayout. */
        type $Shape = game.PlayerPayout.$Properties;
    }

    /**
     * Properties of a RoundResult.
     * @deprecated Use game.RoundResult.$Properties instead.
     */
    interface IRoundResult extends game.RoundResult.$Properties {
    }

    /** Represents a RoundResult. */
    class RoundResult {

        /**
         * Constructs a new RoundResult.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.RoundResult.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** RoundResult winnerSeat. */
        winnerSeat: number;

        /** RoundResult winType. */
        winType: game.ActionType;

        /** RoundResult discarderSeat. */
        discarderSeat: number;

        /** RoundResult winningHand. */
        winningHand: game.Tile[];

        /** RoundResult winningMelds. */
        winningMelds: game.Meld[];

        /** RoundResult winTile. */
        winTile: game.Tile;

        /** RoundResult breakdown. */
        breakdown: game.ScoreEntry[];

        /** RoundResult totalScore. */
        totalScore: number;

        /** RoundResult payouts. */
        payouts: game.PlayerPayout[];

        /** RoundResult isDraw. */
        isDraw: boolean;

        /**
         * Creates a new RoundResult instance using the specified properties.
         * @param [properties] Properties to set
         * @returns RoundResult instance
         */
        static create(properties: game.RoundResult.$Shape): game.RoundResult & game.RoundResult.$Shape;
        static create(properties?: game.RoundResult.$Properties): game.RoundResult;

        /**
         * Encodes the specified RoundResult message. Does not implicitly {@link game.RoundResult.verify|verify} messages.
         * @param message RoundResult message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.RoundResult.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified RoundResult message, length delimited. Does not implicitly {@link game.RoundResult.verify|verify} messages.
         * @param message RoundResult message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.RoundResult.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a RoundResult message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.RoundResult & game.RoundResult.$Shape} RoundResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.RoundResult & game.RoundResult.$Shape;

        /**
         * Decodes a RoundResult message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.RoundResult & game.RoundResult.$Shape} RoundResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.RoundResult & game.RoundResult.$Shape;

        /**
         * Verifies a RoundResult message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a RoundResult message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns RoundResult
         */
        static fromObject(object: { [k: string]: any }): game.RoundResult;

        /**
         * Creates a plain object from a RoundResult message. Also converts values to other types if specified.
         * @param message RoundResult
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.RoundResult, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this RoundResult to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for RoundResult
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace RoundResult {

        /** Properties of a RoundResult. */
        interface $Properties {

            /** RoundResult winnerSeat */
            winnerSeat?: number;

            /** RoundResult winType */
            winType?: game.ActionType;

            /** RoundResult discarderSeat */
            discarderSeat?: number;

            /** RoundResult winningHand */
            winningHand?: game.Tile.$Properties[];

            /** RoundResult winningMelds */
            winningMelds?: game.Meld.$Properties[];

            /** RoundResult winTile */
            winTile?: game.Tile.$Properties;

            /** RoundResult breakdown */
            breakdown?: game.ScoreEntry.$Properties[];

            /** RoundResult totalScore */
            totalScore?: number;

            /** RoundResult payouts */
            payouts?: game.PlayerPayout.$Properties[];

            /** RoundResult isDraw */
            isDraw?: boolean;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a RoundResult. */
        type $Shape = game.RoundResult.$Properties;
    }

    /**
     * Properties of a RoundOutcome.
     * @deprecated Use game.RoundOutcome.$Properties instead.
     */
    interface IRoundOutcome extends game.RoundOutcome.$Properties {
    }

    /** Represents a RoundOutcome. */
    class RoundOutcome {

        /**
         * Constructs a new RoundOutcome.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.RoundOutcome.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** RoundOutcome isDraw. */
        isDraw: boolean;

        /** RoundOutcome winnerSeat. */
        winnerSeat: number;

        /** RoundOutcome winType. */
        winType: game.ActionType;

        /** RoundOutcome discarderSeat. */
        discarderSeat: number;

        /** RoundOutcome totalScore. */
        totalScore: number;

        /** RoundOutcome payouts. */
        payouts: game.PlayerPayout[];

        /**
         * Creates a new RoundOutcome instance using the specified properties.
         * @param [properties] Properties to set
         * @returns RoundOutcome instance
         */
        static create(properties: game.RoundOutcome.$Shape): game.RoundOutcome & game.RoundOutcome.$Shape;
        static create(properties?: game.RoundOutcome.$Properties): game.RoundOutcome;

        /**
         * Encodes the specified RoundOutcome message. Does not implicitly {@link game.RoundOutcome.verify|verify} messages.
         * @param message RoundOutcome message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.RoundOutcome.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified RoundOutcome message, length delimited. Does not implicitly {@link game.RoundOutcome.verify|verify} messages.
         * @param message RoundOutcome message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.RoundOutcome.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a RoundOutcome message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.RoundOutcome & game.RoundOutcome.$Shape} RoundOutcome
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.RoundOutcome & game.RoundOutcome.$Shape;

        /**
         * Decodes a RoundOutcome message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.RoundOutcome & game.RoundOutcome.$Shape} RoundOutcome
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.RoundOutcome & game.RoundOutcome.$Shape;

        /**
         * Verifies a RoundOutcome message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a RoundOutcome message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns RoundOutcome
         */
        static fromObject(object: { [k: string]: any }): game.RoundOutcome;

        /**
         * Creates a plain object from a RoundOutcome message. Also converts values to other types if specified.
         * @param message RoundOutcome
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.RoundOutcome, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this RoundOutcome to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for RoundOutcome
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace RoundOutcome {

        /** Properties of a RoundOutcome. */
        interface $Properties {

            /** RoundOutcome isDraw */
            isDraw?: boolean;

            /** RoundOutcome winnerSeat */
            winnerSeat?: number;

            /** RoundOutcome winType */
            winType?: game.ActionType;

            /** RoundOutcome discarderSeat */
            discarderSeat?: number;

            /** RoundOutcome totalScore */
            totalScore?: number;

            /** RoundOutcome payouts */
            payouts?: game.PlayerPayout.$Properties[];

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a RoundOutcome. */
        type $Shape = game.RoundOutcome.$Properties;
    }

    /**
     * Properties of an EnvConfig.
     * @deprecated Use game.EnvConfig.$Properties instead.
     */
    interface IEnvConfig extends game.EnvConfig.$Properties {
    }

    /** Represents an EnvConfig. */
    class EnvConfig {

        /**
         * Constructs a new EnvConfig.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.EnvConfig.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** EnvConfig learningSeats. */
        learningSeats: number[];

        /** EnvConfig autoPlayHeuristics. */
        autoPlayHeuristics: boolean;

        /** EnvConfig maxDecisions. */
        maxDecisions: number;

        /** EnvConfig matchMode. */
        matchMode: game.MatchMode;

        /** EnvConfig chongciConfig. */
        chongciConfig: game.ChongciConfig;

        /** EnvConfig oracleObservation. */
        oracleObservation: boolean;

        /**
         * Creates a new EnvConfig instance using the specified properties.
         * @param [properties] Properties to set
         * @returns EnvConfig instance
         */
        static create(properties: game.EnvConfig.$Shape): game.EnvConfig & game.EnvConfig.$Shape;
        static create(properties?: game.EnvConfig.$Properties): game.EnvConfig;

        /**
         * Encodes the specified EnvConfig message. Does not implicitly {@link game.EnvConfig.verify|verify} messages.
         * @param message EnvConfig message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.EnvConfig.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified EnvConfig message, length delimited. Does not implicitly {@link game.EnvConfig.verify|verify} messages.
         * @param message EnvConfig message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.EnvConfig.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an EnvConfig message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.EnvConfig & game.EnvConfig.$Shape} EnvConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.EnvConfig & game.EnvConfig.$Shape;

        /**
         * Decodes an EnvConfig message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.EnvConfig & game.EnvConfig.$Shape} EnvConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.EnvConfig & game.EnvConfig.$Shape;

        /**
         * Verifies an EnvConfig message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an EnvConfig message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns EnvConfig
         */
        static fromObject(object: { [k: string]: any }): game.EnvConfig;

        /**
         * Creates a plain object from an EnvConfig message. Also converts values to other types if specified.
         * @param message EnvConfig
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.EnvConfig, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this EnvConfig to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for EnvConfig
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace EnvConfig {

        /** Properties of an EnvConfig. */
        interface $Properties {

            /** EnvConfig learningSeats */
            learningSeats?: number[];

            /** EnvConfig autoPlayHeuristics */
            autoPlayHeuristics?: boolean;

            /** EnvConfig maxDecisions */
            maxDecisions?: number;

            /** EnvConfig matchMode */
            matchMode?: game.MatchMode;

            /** EnvConfig chongciConfig */
            chongciConfig?: game.ChongciConfig.$Properties;

            /** EnvConfig oracleObservation */
            oracleObservation?: boolean;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of an EnvConfig. */
        type $Shape = game.EnvConfig.$Properties;
    }

    /**
     * Properties of a SeatObservation.
     * @deprecated Use game.SeatObservation.$Properties instead.
     */
    interface ISeatObservation extends game.SeatObservation.$Properties {
    }

    /** Represents a SeatObservation. */
    class SeatObservation {

        /**
         * Constructs a new SeatObservation.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.SeatObservation.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** SeatObservation seat. */
        seat: number;

        /** SeatObservation planes. */
        planes: number[];

        /** SeatObservation planeChannels. */
        planeChannels: number;

        /** SeatObservation planeHeight. */
        planeHeight: number;

        /** SeatObservation planeWidth. */
        planeWidth: number;

        /** SeatObservation scalars. */
        scalars: number[];

        /** SeatObservation actionMask. */
        actionMask: Uint8Array;

        /** SeatObservation actionSpaceSize. */
        actionSpaceSize: number;

        /** SeatObservation decisionIndex. */
        decisionIndex: (number|Long);

        /** SeatObservation phase. */
        phase: game.GamePhase;

        /** SeatObservation activePlayer. */
        activePlayer: number;

        /**
         * Creates a new SeatObservation instance using the specified properties.
         * @param [properties] Properties to set
         * @returns SeatObservation instance
         */
        static create(properties: game.SeatObservation.$Shape): game.SeatObservation & game.SeatObservation.$Shape;
        static create(properties?: game.SeatObservation.$Properties): game.SeatObservation;

        /**
         * Encodes the specified SeatObservation message. Does not implicitly {@link game.SeatObservation.verify|verify} messages.
         * @param message SeatObservation message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.SeatObservation.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified SeatObservation message, length delimited. Does not implicitly {@link game.SeatObservation.verify|verify} messages.
         * @param message SeatObservation message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.SeatObservation.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a SeatObservation message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.SeatObservation & game.SeatObservation.$Shape} SeatObservation
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.SeatObservation & game.SeatObservation.$Shape;

        /**
         * Decodes a SeatObservation message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.SeatObservation & game.SeatObservation.$Shape} SeatObservation
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.SeatObservation & game.SeatObservation.$Shape;

        /**
         * Verifies a SeatObservation message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a SeatObservation message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns SeatObservation
         */
        static fromObject(object: { [k: string]: any }): game.SeatObservation;

        /**
         * Creates a plain object from a SeatObservation message. Also converts values to other types if specified.
         * @param message SeatObservation
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.SeatObservation, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this SeatObservation to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for SeatObservation
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace SeatObservation {

        /** Properties of a SeatObservation. */
        interface $Properties {

            /** SeatObservation seat */
            seat?: number;

            /** SeatObservation planes */
            planes?: number[];

            /** SeatObservation planeChannels */
            planeChannels?: number;

            /** SeatObservation planeHeight */
            planeHeight?: number;

            /** SeatObservation planeWidth */
            planeWidth?: number;

            /** SeatObservation scalars */
            scalars?: number[];

            /** SeatObservation actionMask */
            actionMask?: Uint8Array;

            /** SeatObservation actionSpaceSize */
            actionSpaceSize?: number;

            /** SeatObservation decisionIndex */
            decisionIndex?: (number|Long);

            /** SeatObservation phase */
            phase?: game.GamePhase;

            /** SeatObservation activePlayer */
            activePlayer?: number;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a SeatObservation. */
        type $Shape = game.SeatObservation.$Properties;
    }

    /**
     * Properties of an EnvResetRequest.
     * @deprecated Use game.EnvResetRequest.$Properties instead.
     */
    interface IEnvResetRequest extends game.EnvResetRequest.$Properties {
    }

    /** Represents an EnvResetRequest. */
    class EnvResetRequest {

        /**
         * Constructs a new EnvResetRequest.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.EnvResetRequest.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** EnvResetRequest seed. */
        seed: (number|Long);

        /** EnvResetRequest config. */
        config: game.EnvConfig;

        /**
         * Creates a new EnvResetRequest instance using the specified properties.
         * @param [properties] Properties to set
         * @returns EnvResetRequest instance
         */
        static create(properties: game.EnvResetRequest.$Shape): game.EnvResetRequest & game.EnvResetRequest.$Shape;
        static create(properties?: game.EnvResetRequest.$Properties): game.EnvResetRequest;

        /**
         * Encodes the specified EnvResetRequest message. Does not implicitly {@link game.EnvResetRequest.verify|verify} messages.
         * @param message EnvResetRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.EnvResetRequest.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified EnvResetRequest message, length delimited. Does not implicitly {@link game.EnvResetRequest.verify|verify} messages.
         * @param message EnvResetRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.EnvResetRequest.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an EnvResetRequest message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.EnvResetRequest & game.EnvResetRequest.$Shape} EnvResetRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.EnvResetRequest & game.EnvResetRequest.$Shape;

        /**
         * Decodes an EnvResetRequest message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.EnvResetRequest & game.EnvResetRequest.$Shape} EnvResetRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.EnvResetRequest & game.EnvResetRequest.$Shape;

        /**
         * Verifies an EnvResetRequest message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an EnvResetRequest message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns EnvResetRequest
         */
        static fromObject(object: { [k: string]: any }): game.EnvResetRequest;

        /**
         * Creates a plain object from an EnvResetRequest message. Also converts values to other types if specified.
         * @param message EnvResetRequest
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.EnvResetRequest, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this EnvResetRequest to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for EnvResetRequest
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace EnvResetRequest {

        /** Properties of an EnvResetRequest. */
        interface $Properties {

            /** EnvResetRequest seed */
            seed?: (number|Long);

            /** EnvResetRequest config */
            config?: game.EnvConfig.$Properties;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of an EnvResetRequest. */
        type $Shape = game.EnvResetRequest.$Properties;
    }

    /**
     * Properties of an EnvResetResponse.
     * @deprecated Use game.EnvResetResponse.$Properties instead.
     */
    interface IEnvResetResponse extends game.EnvResetResponse.$Properties {
    }

    /** Represents an EnvResetResponse. */
    class EnvResetResponse {

        /**
         * Constructs a new EnvResetResponse.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.EnvResetResponse.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** EnvResetResponse observation. */
        observation: game.SeatObservation;

        /** EnvResetResponse rewards. */
        rewards: number[];

        /** EnvResetResponse terminated. */
        terminated: boolean;

        /** EnvResetResponse truncated. */
        truncated: boolean;

        /** EnvResetResponse roundOutcome. */
        roundOutcome: game.RoundOutcome;

        /**
         * Creates a new EnvResetResponse instance using the specified properties.
         * @param [properties] Properties to set
         * @returns EnvResetResponse instance
         */
        static create(properties: game.EnvResetResponse.$Shape): game.EnvResetResponse & game.EnvResetResponse.$Shape;
        static create(properties?: game.EnvResetResponse.$Properties): game.EnvResetResponse;

        /**
         * Encodes the specified EnvResetResponse message. Does not implicitly {@link game.EnvResetResponse.verify|verify} messages.
         * @param message EnvResetResponse message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.EnvResetResponse.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified EnvResetResponse message, length delimited. Does not implicitly {@link game.EnvResetResponse.verify|verify} messages.
         * @param message EnvResetResponse message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.EnvResetResponse.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an EnvResetResponse message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.EnvResetResponse & game.EnvResetResponse.$Shape} EnvResetResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.EnvResetResponse & game.EnvResetResponse.$Shape;

        /**
         * Decodes an EnvResetResponse message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.EnvResetResponse & game.EnvResetResponse.$Shape} EnvResetResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.EnvResetResponse & game.EnvResetResponse.$Shape;

        /**
         * Verifies an EnvResetResponse message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an EnvResetResponse message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns EnvResetResponse
         */
        static fromObject(object: { [k: string]: any }): game.EnvResetResponse;

        /**
         * Creates a plain object from an EnvResetResponse message. Also converts values to other types if specified.
         * @param message EnvResetResponse
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.EnvResetResponse, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this EnvResetResponse to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for EnvResetResponse
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace EnvResetResponse {

        /** Properties of an EnvResetResponse. */
        interface $Properties {

            /** EnvResetResponse observation */
            observation?: game.SeatObservation.$Properties;

            /** EnvResetResponse rewards */
            rewards?: number[];

            /** EnvResetResponse terminated */
            terminated?: boolean;

            /** EnvResetResponse truncated */
            truncated?: boolean;

            /** EnvResetResponse roundOutcome */
            roundOutcome?: game.RoundOutcome.$Properties;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of an EnvResetResponse. */
        type $Shape = game.EnvResetResponse.$Properties;
    }

    /**
     * Properties of an EnvStepRequest.
     * @deprecated Use game.EnvStepRequest.$Properties instead.
     */
    interface IEnvStepRequest extends game.EnvStepRequest.$Properties {
    }

    /** Represents an EnvStepRequest. */
    class EnvStepRequest {

        /**
         * Constructs a new EnvStepRequest.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.EnvStepRequest.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** EnvStepRequest actionId. */
        actionId: number;

        /**
         * Creates a new EnvStepRequest instance using the specified properties.
         * @param [properties] Properties to set
         * @returns EnvStepRequest instance
         */
        static create(properties: game.EnvStepRequest.$Shape): game.EnvStepRequest & game.EnvStepRequest.$Shape;
        static create(properties?: game.EnvStepRequest.$Properties): game.EnvStepRequest;

        /**
         * Encodes the specified EnvStepRequest message. Does not implicitly {@link game.EnvStepRequest.verify|verify} messages.
         * @param message EnvStepRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.EnvStepRequest.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified EnvStepRequest message, length delimited. Does not implicitly {@link game.EnvStepRequest.verify|verify} messages.
         * @param message EnvStepRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.EnvStepRequest.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an EnvStepRequest message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.EnvStepRequest & game.EnvStepRequest.$Shape} EnvStepRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.EnvStepRequest & game.EnvStepRequest.$Shape;

        /**
         * Decodes an EnvStepRequest message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.EnvStepRequest & game.EnvStepRequest.$Shape} EnvStepRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.EnvStepRequest & game.EnvStepRequest.$Shape;

        /**
         * Verifies an EnvStepRequest message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an EnvStepRequest message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns EnvStepRequest
         */
        static fromObject(object: { [k: string]: any }): game.EnvStepRequest;

        /**
         * Creates a plain object from an EnvStepRequest message. Also converts values to other types if specified.
         * @param message EnvStepRequest
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.EnvStepRequest, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this EnvStepRequest to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for EnvStepRequest
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace EnvStepRequest {

        /** Properties of an EnvStepRequest. */
        interface $Properties {

            /** EnvStepRequest actionId */
            actionId?: number;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of an EnvStepRequest. */
        type $Shape = game.EnvStepRequest.$Properties;
    }

    /**
     * Properties of an EnvStepResponse.
     * @deprecated Use game.EnvStepResponse.$Properties instead.
     */
    interface IEnvStepResponse extends game.EnvStepResponse.$Properties {
    }

    /** Represents an EnvStepResponse. */
    class EnvStepResponse {

        /**
         * Constructs a new EnvStepResponse.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.EnvStepResponse.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** EnvStepResponse observation. */
        observation: game.SeatObservation;

        /** EnvStepResponse rewards. */
        rewards: number[];

        /** EnvStepResponse terminated. */
        terminated: boolean;

        /** EnvStepResponse truncated. */
        truncated: boolean;

        /** EnvStepResponse roundOutcome. */
        roundOutcome: game.RoundOutcome;

        /**
         * Creates a new EnvStepResponse instance using the specified properties.
         * @param [properties] Properties to set
         * @returns EnvStepResponse instance
         */
        static create(properties: game.EnvStepResponse.$Shape): game.EnvStepResponse & game.EnvStepResponse.$Shape;
        static create(properties?: game.EnvStepResponse.$Properties): game.EnvStepResponse;

        /**
         * Encodes the specified EnvStepResponse message. Does not implicitly {@link game.EnvStepResponse.verify|verify} messages.
         * @param message EnvStepResponse message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.EnvStepResponse.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified EnvStepResponse message, length delimited. Does not implicitly {@link game.EnvStepResponse.verify|verify} messages.
         * @param message EnvStepResponse message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.EnvStepResponse.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes an EnvStepResponse message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.EnvStepResponse & game.EnvStepResponse.$Shape} EnvStepResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.EnvStepResponse & game.EnvStepResponse.$Shape;

        /**
         * Decodes an EnvStepResponse message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.EnvStepResponse & game.EnvStepResponse.$Shape} EnvStepResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.EnvStepResponse & game.EnvStepResponse.$Shape;

        /**
         * Verifies an EnvStepResponse message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates an EnvStepResponse message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns EnvStepResponse
         */
        static fromObject(object: { [k: string]: any }): game.EnvStepResponse;

        /**
         * Creates a plain object from an EnvStepResponse message. Also converts values to other types if specified.
         * @param message EnvStepResponse
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.EnvStepResponse, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this EnvStepResponse to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for EnvStepResponse
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace EnvStepResponse {

        /** Properties of an EnvStepResponse. */
        interface $Properties {

            /** EnvStepResponse observation */
            observation?: game.SeatObservation.$Properties;

            /** EnvStepResponse rewards */
            rewards?: number[];

            /** EnvStepResponse terminated */
            terminated?: boolean;

            /** EnvStepResponse truncated */
            truncated?: boolean;

            /** EnvStepResponse roundOutcome */
            roundOutcome?: game.RoundOutcome.$Properties;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of an EnvStepResponse. */
        type $Shape = game.EnvStepResponse.$Properties;
    }

    /**
     * Properties of a BranchEvaluationRequest.
     * @deprecated Use game.BranchEvaluationRequest.$Properties instead.
     */
    interface IBranchEvaluationRequest extends game.BranchEvaluationRequest.$Properties {
    }

    /** Represents a BranchEvaluationRequest. */
    class BranchEvaluationRequest {

        /**
         * Constructs a new BranchEvaluationRequest.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.BranchEvaluationRequest.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** BranchEvaluationRequest actionIds. */
        actionIds: number[];

        /** BranchEvaluationRequest stopAtRoundEnd. */
        stopAtRoundEnd: boolean;

        /** BranchEvaluationRequest maxDecisions. */
        maxDecisions: number;

        /**
         * Creates a new BranchEvaluationRequest instance using the specified properties.
         * @param [properties] Properties to set
         * @returns BranchEvaluationRequest instance
         */
        static create(properties: game.BranchEvaluationRequest.$Shape): game.BranchEvaluationRequest & game.BranchEvaluationRequest.$Shape;
        static create(properties?: game.BranchEvaluationRequest.$Properties): game.BranchEvaluationRequest;

        /**
         * Encodes the specified BranchEvaluationRequest message. Does not implicitly {@link game.BranchEvaluationRequest.verify|verify} messages.
         * @param message BranchEvaluationRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.BranchEvaluationRequest.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified BranchEvaluationRequest message, length delimited. Does not implicitly {@link game.BranchEvaluationRequest.verify|verify} messages.
         * @param message BranchEvaluationRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.BranchEvaluationRequest.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a BranchEvaluationRequest message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.BranchEvaluationRequest & game.BranchEvaluationRequest.$Shape} BranchEvaluationRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.BranchEvaluationRequest & game.BranchEvaluationRequest.$Shape;

        /**
         * Decodes a BranchEvaluationRequest message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.BranchEvaluationRequest & game.BranchEvaluationRequest.$Shape} BranchEvaluationRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.BranchEvaluationRequest & game.BranchEvaluationRequest.$Shape;

        /**
         * Verifies a BranchEvaluationRequest message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a BranchEvaluationRequest message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns BranchEvaluationRequest
         */
        static fromObject(object: { [k: string]: any }): game.BranchEvaluationRequest;

        /**
         * Creates a plain object from a BranchEvaluationRequest message. Also converts values to other types if specified.
         * @param message BranchEvaluationRequest
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.BranchEvaluationRequest, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this BranchEvaluationRequest to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for BranchEvaluationRequest
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace BranchEvaluationRequest {

        /** Properties of a BranchEvaluationRequest. */
        interface $Properties {

            /** BranchEvaluationRequest actionIds */
            actionIds?: number[];

            /** BranchEvaluationRequest stopAtRoundEnd */
            stopAtRoundEnd?: boolean;

            /** BranchEvaluationRequest maxDecisions */
            maxDecisions?: number;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a BranchEvaluationRequest. */
        type $Shape = game.BranchEvaluationRequest.$Properties;
    }

    /**
     * Properties of a BranchEvaluationResult.
     * @deprecated Use game.BranchEvaluationResult.$Properties instead.
     */
    interface IBranchEvaluationResult extends game.BranchEvaluationResult.$Properties {
    }

    /** Represents a BranchEvaluationResult. */
    class BranchEvaluationResult {

        /**
         * Constructs a new BranchEvaluationResult.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.BranchEvaluationResult.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** BranchEvaluationResult actionId. */
        actionId: number;

        /** BranchEvaluationResult rewards. */
        rewards: number[];

        /** BranchEvaluationResult terminated. */
        terminated: boolean;

        /** BranchEvaluationResult truncated. */
        truncated: boolean;

        /** BranchEvaluationResult roundOutcome. */
        roundOutcome: game.RoundOutcome;

        /** BranchEvaluationResult decisions. */
        decisions: (number|Long);

        /** BranchEvaluationResult error. */
        error: string;

        /**
         * Creates a new BranchEvaluationResult instance using the specified properties.
         * @param [properties] Properties to set
         * @returns BranchEvaluationResult instance
         */
        static create(properties: game.BranchEvaluationResult.$Shape): game.BranchEvaluationResult & game.BranchEvaluationResult.$Shape;
        static create(properties?: game.BranchEvaluationResult.$Properties): game.BranchEvaluationResult;

        /**
         * Encodes the specified BranchEvaluationResult message. Does not implicitly {@link game.BranchEvaluationResult.verify|verify} messages.
         * @param message BranchEvaluationResult message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.BranchEvaluationResult.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified BranchEvaluationResult message, length delimited. Does not implicitly {@link game.BranchEvaluationResult.verify|verify} messages.
         * @param message BranchEvaluationResult message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.BranchEvaluationResult.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a BranchEvaluationResult message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.BranchEvaluationResult & game.BranchEvaluationResult.$Shape} BranchEvaluationResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.BranchEvaluationResult & game.BranchEvaluationResult.$Shape;

        /**
         * Decodes a BranchEvaluationResult message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.BranchEvaluationResult & game.BranchEvaluationResult.$Shape} BranchEvaluationResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.BranchEvaluationResult & game.BranchEvaluationResult.$Shape;

        /**
         * Verifies a BranchEvaluationResult message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a BranchEvaluationResult message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns BranchEvaluationResult
         */
        static fromObject(object: { [k: string]: any }): game.BranchEvaluationResult;

        /**
         * Creates a plain object from a BranchEvaluationResult message. Also converts values to other types if specified.
         * @param message BranchEvaluationResult
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.BranchEvaluationResult, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this BranchEvaluationResult to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for BranchEvaluationResult
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace BranchEvaluationResult {

        /** Properties of a BranchEvaluationResult. */
        interface $Properties {

            /** BranchEvaluationResult actionId */
            actionId?: number;

            /** BranchEvaluationResult rewards */
            rewards?: number[];

            /** BranchEvaluationResult terminated */
            terminated?: boolean;

            /** BranchEvaluationResult truncated */
            truncated?: boolean;

            /** BranchEvaluationResult roundOutcome */
            roundOutcome?: game.RoundOutcome.$Properties;

            /** BranchEvaluationResult decisions */
            decisions?: (number|Long);

            /** BranchEvaluationResult error */
            error?: string;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a BranchEvaluationResult. */
        type $Shape = game.BranchEvaluationResult.$Properties;
    }

    /**
     * Properties of a BranchEvaluationResponse.
     * @deprecated Use game.BranchEvaluationResponse.$Properties instead.
     */
    interface IBranchEvaluationResponse extends game.BranchEvaluationResponse.$Properties {
    }

    /** Represents a BranchEvaluationResponse. */
    class BranchEvaluationResponse {

        /**
         * Constructs a new BranchEvaluationResponse.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.BranchEvaluationResponse.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** BranchEvaluationResponse observation. */
        observation: game.SeatObservation;

        /** BranchEvaluationResponse results. */
        results: game.BranchEvaluationResult[];

        /**
         * Creates a new BranchEvaluationResponse instance using the specified properties.
         * @param [properties] Properties to set
         * @returns BranchEvaluationResponse instance
         */
        static create(properties: game.BranchEvaluationResponse.$Shape): game.BranchEvaluationResponse & game.BranchEvaluationResponse.$Shape;
        static create(properties?: game.BranchEvaluationResponse.$Properties): game.BranchEvaluationResponse;

        /**
         * Encodes the specified BranchEvaluationResponse message. Does not implicitly {@link game.BranchEvaluationResponse.verify|verify} messages.
         * @param message BranchEvaluationResponse message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.BranchEvaluationResponse.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified BranchEvaluationResponse message, length delimited. Does not implicitly {@link game.BranchEvaluationResponse.verify|verify} messages.
         * @param message BranchEvaluationResponse message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.BranchEvaluationResponse.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a BranchEvaluationResponse message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.BranchEvaluationResponse & game.BranchEvaluationResponse.$Shape} BranchEvaluationResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.BranchEvaluationResponse & game.BranchEvaluationResponse.$Shape;

        /**
         * Decodes a BranchEvaluationResponse message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.BranchEvaluationResponse & game.BranchEvaluationResponse.$Shape} BranchEvaluationResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.BranchEvaluationResponse & game.BranchEvaluationResponse.$Shape;

        /**
         * Verifies a BranchEvaluationResponse message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a BranchEvaluationResponse message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns BranchEvaluationResponse
         */
        static fromObject(object: { [k: string]: any }): game.BranchEvaluationResponse;

        /**
         * Creates a plain object from a BranchEvaluationResponse message. Also converts values to other types if specified.
         * @param message BranchEvaluationResponse
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.BranchEvaluationResponse, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this BranchEvaluationResponse to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for BranchEvaluationResponse
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace BranchEvaluationResponse {

        /** Properties of a BranchEvaluationResponse. */
        interface $Properties {

            /** BranchEvaluationResponse observation */
            observation?: game.SeatObservation.$Properties;

            /** BranchEvaluationResponse results */
            results?: game.BranchEvaluationResult.$Properties[];

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a BranchEvaluationResponse. */
        type $Shape = game.BranchEvaluationResponse.$Properties;
    }

    /**
     * Properties of a TrajectoryRequest.
     * @deprecated Use game.TrajectoryRequest.$Properties instead.
     */
    interface ITrajectoryRequest extends game.TrajectoryRequest.$Properties {
    }

    /** Represents a TrajectoryRequest. */
    class TrajectoryRequest {

        /**
         * Constructs a new TrajectoryRequest.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.TrajectoryRequest.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** TrajectoryRequest episodes. */
        episodes: number;

        /** TrajectoryRequest startSeed. */
        startSeed: (number|Long);

        /** TrajectoryRequest config. */
        config: game.EnvConfig;

        /**
         * Creates a new TrajectoryRequest instance using the specified properties.
         * @param [properties] Properties to set
         * @returns TrajectoryRequest instance
         */
        static create(properties: game.TrajectoryRequest.$Shape): game.TrajectoryRequest & game.TrajectoryRequest.$Shape;
        static create(properties?: game.TrajectoryRequest.$Properties): game.TrajectoryRequest;

        /**
         * Encodes the specified TrajectoryRequest message. Does not implicitly {@link game.TrajectoryRequest.verify|verify} messages.
         * @param message TrajectoryRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.TrajectoryRequest.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified TrajectoryRequest message, length delimited. Does not implicitly {@link game.TrajectoryRequest.verify|verify} messages.
         * @param message TrajectoryRequest message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.TrajectoryRequest.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a TrajectoryRequest message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.TrajectoryRequest & game.TrajectoryRequest.$Shape} TrajectoryRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.TrajectoryRequest & game.TrajectoryRequest.$Shape;

        /**
         * Decodes a TrajectoryRequest message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.TrajectoryRequest & game.TrajectoryRequest.$Shape} TrajectoryRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.TrajectoryRequest & game.TrajectoryRequest.$Shape;

        /**
         * Verifies a TrajectoryRequest message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a TrajectoryRequest message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns TrajectoryRequest
         */
        static fromObject(object: { [k: string]: any }): game.TrajectoryRequest;

        /**
         * Creates a plain object from a TrajectoryRequest message. Also converts values to other types if specified.
         * @param message TrajectoryRequest
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.TrajectoryRequest, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this TrajectoryRequest to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for TrajectoryRequest
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace TrajectoryRequest {

        /** Properties of a TrajectoryRequest. */
        interface $Properties {

            /** TrajectoryRequest episodes */
            episodes?: number;

            /** TrajectoryRequest startSeed */
            startSeed?: (number|Long);

            /** TrajectoryRequest config */
            config?: game.EnvConfig.$Properties;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a TrajectoryRequest. */
        type $Shape = game.TrajectoryRequest.$Properties;
    }

    /**
     * Properties of a TrajectorySample.
     * @deprecated Use game.TrajectorySample.$Properties instead.
     */
    interface ITrajectorySample extends game.TrajectorySample.$Properties {
    }

    /** Represents a TrajectorySample. */
    class TrajectorySample {

        /**
         * Constructs a new TrajectorySample.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.TrajectorySample.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** TrajectorySample observation. */
        observation: game.SeatObservation;

        /** TrajectorySample actionId. */
        actionId: number;

        /** TrajectorySample rewards. */
        rewards: number[];

        /** TrajectorySample nextObservation. */
        nextObservation: game.SeatObservation;

        /** TrajectorySample terminated. */
        terminated: boolean;

        /** TrajectorySample truncated. */
        truncated: boolean;

        /** TrajectorySample actingSeat. */
        actingSeat: number;

        /** TrajectorySample episodeIndex. */
        episodeIndex: (number|Long);

        /** TrajectorySample terminalRewards. */
        terminalRewards: number[];

        /** TrajectorySample terminalOutcome. */
        terminalOutcome: game.RoundOutcome;

        /**
         * Creates a new TrajectorySample instance using the specified properties.
         * @param [properties] Properties to set
         * @returns TrajectorySample instance
         */
        static create(properties: game.TrajectorySample.$Shape): game.TrajectorySample & game.TrajectorySample.$Shape;
        static create(properties?: game.TrajectorySample.$Properties): game.TrajectorySample;

        /**
         * Encodes the specified TrajectorySample message. Does not implicitly {@link game.TrajectorySample.verify|verify} messages.
         * @param message TrajectorySample message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.TrajectorySample.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified TrajectorySample message, length delimited. Does not implicitly {@link game.TrajectorySample.verify|verify} messages.
         * @param message TrajectorySample message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.TrajectorySample.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a TrajectorySample message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.TrajectorySample & game.TrajectorySample.$Shape} TrajectorySample
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.TrajectorySample & game.TrajectorySample.$Shape;

        /**
         * Decodes a TrajectorySample message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.TrajectorySample & game.TrajectorySample.$Shape} TrajectorySample
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.TrajectorySample & game.TrajectorySample.$Shape;

        /**
         * Verifies a TrajectorySample message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a TrajectorySample message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns TrajectorySample
         */
        static fromObject(object: { [k: string]: any }): game.TrajectorySample;

        /**
         * Creates a plain object from a TrajectorySample message. Also converts values to other types if specified.
         * @param message TrajectorySample
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.TrajectorySample, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this TrajectorySample to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for TrajectorySample
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace TrajectorySample {

        /** Properties of a TrajectorySample. */
        interface $Properties {

            /** TrajectorySample observation */
            observation?: game.SeatObservation.$Properties;

            /** TrajectorySample actionId */
            actionId?: number;

            /** TrajectorySample rewards */
            rewards?: number[];

            /** TrajectorySample nextObservation */
            nextObservation?: game.SeatObservation.$Properties;

            /** TrajectorySample terminated */
            terminated?: boolean;

            /** TrajectorySample truncated */
            truncated?: boolean;

            /** TrajectorySample actingSeat */
            actingSeat?: number;

            /** TrajectorySample episodeIndex */
            episodeIndex?: (number|Long);

            /** TrajectorySample terminalRewards */
            terminalRewards?: number[];

            /** TrajectorySample terminalOutcome */
            terminalOutcome?: game.RoundOutcome.$Properties;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a TrajectorySample. */
        type $Shape = game.TrajectorySample.$Properties;
    }

    /**
     * Properties of a TrajectoryDataset.
     * @deprecated Use game.TrajectoryDataset.$Properties instead.
     */
    interface ITrajectoryDataset extends game.TrajectoryDataset.$Properties {
    }

    /** Represents a TrajectoryDataset. */
    class TrajectoryDataset {

        /**
         * Constructs a new TrajectoryDataset.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.TrajectoryDataset.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** TrajectoryDataset samples. */
        samples: game.TrajectorySample[];

        /**
         * Creates a new TrajectoryDataset instance using the specified properties.
         * @param [properties] Properties to set
         * @returns TrajectoryDataset instance
         */
        static create(properties: game.TrajectoryDataset.$Shape): game.TrajectoryDataset & game.TrajectoryDataset.$Shape;
        static create(properties?: game.TrajectoryDataset.$Properties): game.TrajectoryDataset;

        /**
         * Encodes the specified TrajectoryDataset message. Does not implicitly {@link game.TrajectoryDataset.verify|verify} messages.
         * @param message TrajectoryDataset message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.TrajectoryDataset.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified TrajectoryDataset message, length delimited. Does not implicitly {@link game.TrajectoryDataset.verify|verify} messages.
         * @param message TrajectoryDataset message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.TrajectoryDataset.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a TrajectoryDataset message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.TrajectoryDataset & game.TrajectoryDataset.$Shape} TrajectoryDataset
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.TrajectoryDataset & game.TrajectoryDataset.$Shape;

        /**
         * Decodes a TrajectoryDataset message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.TrajectoryDataset & game.TrajectoryDataset.$Shape} TrajectoryDataset
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.TrajectoryDataset & game.TrajectoryDataset.$Shape;

        /**
         * Verifies a TrajectoryDataset message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a TrajectoryDataset message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns TrajectoryDataset
         */
        static fromObject(object: { [k: string]: any }): game.TrajectoryDataset;

        /**
         * Creates a plain object from a TrajectoryDataset message. Also converts values to other types if specified.
         * @param message TrajectoryDataset
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.TrajectoryDataset, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this TrajectoryDataset to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for TrajectoryDataset
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace TrajectoryDataset {

        /** Properties of a TrajectoryDataset. */
        interface $Properties {

            /** TrajectoryDataset samples */
            samples?: game.TrajectorySample.$Properties[];

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a TrajectoryDataset. */
        type $Shape = game.TrajectoryDataset.$Properties;
    }

    /** Difficulty enum. */
    enum Difficulty {

        /** DIFFICULTY_UNSPECIFIED value */
        DIFFICULTY_UNSPECIFIED = 0,

        /** DIFFICULTY_HEURISTIC value */
        DIFFICULTY_HEURISTIC = 1,

        /** DIFFICULTY_RL value */
        DIFFICULTY_RL = 2
    }

    /**
     * Properties of a SeatConfig.
     * @deprecated Use game.SeatConfig.$Properties instead.
     */
    interface ISeatConfig extends game.SeatConfig.$Properties {
    }

    /** Represents a SeatConfig. */
    class SeatConfig {

        /**
         * Constructs a new SeatConfig.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.SeatConfig.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** SeatConfig kind. */
        kind: string;

        /** SeatConfig userId. */
        userId: number;

        /** SeatConfig username. */
        username: string;

        /** SeatConfig difficulty. */
        difficulty: game.Difficulty;

        /**
         * Creates a new SeatConfig instance using the specified properties.
         * @param [properties] Properties to set
         * @returns SeatConfig instance
         */
        static create(properties: game.SeatConfig.$Shape): game.SeatConfig & game.SeatConfig.$Shape;
        static create(properties?: game.SeatConfig.$Properties): game.SeatConfig;

        /**
         * Encodes the specified SeatConfig message. Does not implicitly {@link game.SeatConfig.verify|verify} messages.
         * @param message SeatConfig message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.SeatConfig.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified SeatConfig message, length delimited. Does not implicitly {@link game.SeatConfig.verify|verify} messages.
         * @param message SeatConfig message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.SeatConfig.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a SeatConfig message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.SeatConfig & game.SeatConfig.$Shape} SeatConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.SeatConfig & game.SeatConfig.$Shape;

        /**
         * Decodes a SeatConfig message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.SeatConfig & game.SeatConfig.$Shape} SeatConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.SeatConfig & game.SeatConfig.$Shape;

        /**
         * Verifies a SeatConfig message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a SeatConfig message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns SeatConfig
         */
        static fromObject(object: { [k: string]: any }): game.SeatConfig;

        /**
         * Creates a plain object from a SeatConfig message. Also converts values to other types if specified.
         * @param message SeatConfig
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.SeatConfig, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this SeatConfig to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for SeatConfig
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace SeatConfig {

        /** Properties of a SeatConfig. */
        interface $Properties {

            /** SeatConfig kind */
            kind?: string;

            /** SeatConfig userId */
            userId?: number;

            /** SeatConfig username */
            username?: string;

            /** SeatConfig difficulty */
            difficulty?: game.Difficulty;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a SeatConfig. */
        type $Shape = game.SeatConfig.$Properties;
    }

    /**
     * Properties of a PrivateTableState.
     * @deprecated Use game.PrivateTableState.$Properties instead.
     */
    interface IPrivateTableState extends game.PrivateTableState.$Properties {
    }

    /** Represents a PrivateTableState. */
    class PrivateTableState {

        /**
         * Constructs a new PrivateTableState.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.PrivateTableState.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** PrivateTableState tableId. */
        tableId: string;

        /** PrivateTableState hostUserId. */
        hostUserId: number;

        /** PrivateTableState seats. */
        seats: game.SeatConfig[];

        /** PrivateTableState state. */
        state: string;

        /** PrivateTableState matchId. */
        matchId: string;

        /** PrivateTableState matchMode. */
        matchMode: game.MatchMode;

        /** PrivateTableState chongciConfig. */
        chongciConfig: game.ChongciConfig;

        /**
         * Creates a new PrivateTableState instance using the specified properties.
         * @param [properties] Properties to set
         * @returns PrivateTableState instance
         */
        static create(properties: game.PrivateTableState.$Shape): game.PrivateTableState & game.PrivateTableState.$Shape;
        static create(properties?: game.PrivateTableState.$Properties): game.PrivateTableState;

        /**
         * Encodes the specified PrivateTableState message. Does not implicitly {@link game.PrivateTableState.verify|verify} messages.
         * @param message PrivateTableState message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.PrivateTableState.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified PrivateTableState message, length delimited. Does not implicitly {@link game.PrivateTableState.verify|verify} messages.
         * @param message PrivateTableState message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.PrivateTableState.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a PrivateTableState message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.PrivateTableState & game.PrivateTableState.$Shape} PrivateTableState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.PrivateTableState & game.PrivateTableState.$Shape;

        /**
         * Decodes a PrivateTableState message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.PrivateTableState & game.PrivateTableState.$Shape} PrivateTableState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.PrivateTableState & game.PrivateTableState.$Shape;

        /**
         * Verifies a PrivateTableState message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a PrivateTableState message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns PrivateTableState
         */
        static fromObject(object: { [k: string]: any }): game.PrivateTableState;

        /**
         * Creates a plain object from a PrivateTableState message. Also converts values to other types if specified.
         * @param message PrivateTableState
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.PrivateTableState, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this PrivateTableState to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for PrivateTableState
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace PrivateTableState {

        /** Properties of a PrivateTableState. */
        interface $Properties {

            /** PrivateTableState tableId */
            tableId?: string;

            /** PrivateTableState hostUserId */
            hostUserId?: number;

            /** PrivateTableState seats */
            seats?: game.SeatConfig.$Properties[];

            /** PrivateTableState state */
            state?: string;

            /** PrivateTableState matchId */
            matchId?: string;

            /** PrivateTableState matchMode */
            matchMode?: game.MatchMode;

            /** PrivateTableState chongciConfig */
            chongciConfig?: game.ChongciConfig.$Properties;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a PrivateTableState. */
        type $Shape = game.PrivateTableState.$Properties;
    }

    /** MatchMode enum. */
    enum MatchMode {

        /** MATCH_MODE_UNSPECIFIED value */
        MATCH_MODE_UNSPECIFIED = 0,

        /** MATCH_MODE_CLASSIC value */
        MATCH_MODE_CLASSIC = 1,

        /** MATCH_MODE_CHONGCI value */
        MATCH_MODE_CHONGCI = 2
    }

    /**
     * Properties of a ChongciConfig.
     * @deprecated Use game.ChongciConfig.$Properties instead.
     */
    interface IChongciConfig extends game.ChongciConfig.$Properties {
    }

    /** Represents a ChongciConfig. */
    class ChongciConfig {

        /**
         * Constructs a new ChongciConfig.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.ChongciConfig.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** ChongciConfig startingScore. */
        startingScore: number;

        /** ChongciConfig bustThreshold. */
        bustThreshold: number;

        /** ChongciConfig maxHands. */
        maxHands: number;

        /**
         * Creates a new ChongciConfig instance using the specified properties.
         * @param [properties] Properties to set
         * @returns ChongciConfig instance
         */
        static create(properties: game.ChongciConfig.$Shape): game.ChongciConfig & game.ChongciConfig.$Shape;
        static create(properties?: game.ChongciConfig.$Properties): game.ChongciConfig;

        /**
         * Encodes the specified ChongciConfig message. Does not implicitly {@link game.ChongciConfig.verify|verify} messages.
         * @param message ChongciConfig message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.ChongciConfig.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified ChongciConfig message, length delimited. Does not implicitly {@link game.ChongciConfig.verify|verify} messages.
         * @param message ChongciConfig message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.ChongciConfig.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a ChongciConfig message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.ChongciConfig & game.ChongciConfig.$Shape} ChongciConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.ChongciConfig & game.ChongciConfig.$Shape;

        /**
         * Decodes a ChongciConfig message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.ChongciConfig & game.ChongciConfig.$Shape} ChongciConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.ChongciConfig & game.ChongciConfig.$Shape;

        /**
         * Verifies a ChongciConfig message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a ChongciConfig message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns ChongciConfig
         */
        static fromObject(object: { [k: string]: any }): game.ChongciConfig;

        /**
         * Creates a plain object from a ChongciConfig message. Also converts values to other types if specified.
         * @param message ChongciConfig
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.ChongciConfig, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this ChongciConfig to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for ChongciConfig
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace ChongciConfig {

        /** Properties of a ChongciConfig. */
        interface $Properties {

            /** ChongciConfig startingScore */
            startingScore?: number;

            /** ChongciConfig bustThreshold */
            bustThreshold?: number;

            /** ChongciConfig maxHands */
            maxHands?: number;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a ChongciConfig. */
        type $Shape = game.ChongciConfig.$Properties;
    }

    /**
     * Properties of a PlayerStanding.
     * @deprecated Use game.PlayerStanding.$Properties instead.
     */
    interface IPlayerStanding extends game.PlayerStanding.$Properties {
    }

    /** Represents a PlayerStanding. */
    class PlayerStanding {

        /**
         * Constructs a new PlayerStanding.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.PlayerStanding.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** PlayerStanding seat. */
        seat: number;

        /** PlayerStanding rank. */
        rank: number;

        /** PlayerStanding finalScore. */
        finalScore: number;

        /** PlayerStanding netChange. */
        netChange: number;

        /**
         * Creates a new PlayerStanding instance using the specified properties.
         * @param [properties] Properties to set
         * @returns PlayerStanding instance
         */
        static create(properties: game.PlayerStanding.$Shape): game.PlayerStanding & game.PlayerStanding.$Shape;
        static create(properties?: game.PlayerStanding.$Properties): game.PlayerStanding;

        /**
         * Encodes the specified PlayerStanding message. Does not implicitly {@link game.PlayerStanding.verify|verify} messages.
         * @param message PlayerStanding message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.PlayerStanding.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified PlayerStanding message, length delimited. Does not implicitly {@link game.PlayerStanding.verify|verify} messages.
         * @param message PlayerStanding message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.PlayerStanding.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a PlayerStanding message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.PlayerStanding & game.PlayerStanding.$Shape} PlayerStanding
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.PlayerStanding & game.PlayerStanding.$Shape;

        /**
         * Decodes a PlayerStanding message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.PlayerStanding & game.PlayerStanding.$Shape} PlayerStanding
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.PlayerStanding & game.PlayerStanding.$Shape;

        /**
         * Verifies a PlayerStanding message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a PlayerStanding message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns PlayerStanding
         */
        static fromObject(object: { [k: string]: any }): game.PlayerStanding;

        /**
         * Creates a plain object from a PlayerStanding message. Also converts values to other types if specified.
         * @param message PlayerStanding
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.PlayerStanding, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this PlayerStanding to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for PlayerStanding
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace PlayerStanding {

        /** Properties of a PlayerStanding. */
        interface $Properties {

            /** PlayerStanding seat */
            seat?: number;

            /** PlayerStanding rank */
            rank?: number;

            /** PlayerStanding finalScore */
            finalScore?: number;

            /** PlayerStanding netChange */
            netChange?: number;

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a PlayerStanding. */
        type $Shape = game.PlayerStanding.$Properties;
    }

    /**
     * Properties of a MatchEndResult.
     * @deprecated Use game.MatchEndResult.$Properties instead.
     */
    interface IMatchEndResult extends game.MatchEndResult.$Properties {
    }

    /** Represents a MatchEndResult. */
    class MatchEndResult {

        /**
         * Constructs a new MatchEndResult.
         * @param [properties] Properties to set
         */
        constructor(properties?: game.MatchEndResult.$Properties);

        /** Unknown fields preserved while decoding when enabled */
        $unknowns?: Uint8Array[];

        /** MatchEndResult reason. */
        reason: string;

        /** MatchEndResult finalHandNum. */
        finalHandNum: number;

        /** MatchEndResult standings. */
        standings: game.PlayerStanding[];

        /**
         * Creates a new MatchEndResult instance using the specified properties.
         * @param [properties] Properties to set
         * @returns MatchEndResult instance
         */
        static create(properties: game.MatchEndResult.$Shape): game.MatchEndResult & game.MatchEndResult.$Shape;
        static create(properties?: game.MatchEndResult.$Properties): game.MatchEndResult;

        /**
         * Encodes the specified MatchEndResult message. Does not implicitly {@link game.MatchEndResult.verify|verify} messages.
         * @param message MatchEndResult message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encode(message: game.MatchEndResult.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Encodes the specified MatchEndResult message, length delimited. Does not implicitly {@link game.MatchEndResult.verify|verify} messages.
         * @param message MatchEndResult message or plain object to encode
         * @param [writer] Writer to encode to
         * @returns Writer
         */
        static encodeDelimited(message: game.MatchEndResult.$Properties, writer?: $protobuf.Writer): $protobuf.Writer;

        /**
         * Decodes a MatchEndResult message from the specified reader or buffer.
         * @param reader Reader or buffer to decode from
         * @param [length] Message length if known beforehand
         * @returns {game.MatchEndResult & game.MatchEndResult.$Shape} MatchEndResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decode(reader: ($protobuf.Reader|Uint8Array), length?: number): game.MatchEndResult & game.MatchEndResult.$Shape;

        /**
         * Decodes a MatchEndResult message from the specified reader or buffer, length delimited.
         * @param reader Reader or buffer to decode from
         * @returns {game.MatchEndResult & game.MatchEndResult.$Shape} MatchEndResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        static decodeDelimited(reader: ($protobuf.Reader|Uint8Array)): game.MatchEndResult & game.MatchEndResult.$Shape;

        /**
         * Verifies a MatchEndResult message.
         * @param message Plain object to verify
         * @returns `null` if valid, otherwise the reason why it is not
         */
        static verify(message: { [k: string]: any }): (string|null);

        /**
         * Creates a MatchEndResult message from a plain object. Also converts values to their respective internal types.
         * @param object Plain object
         * @returns MatchEndResult
         */
        static fromObject(object: { [k: string]: any }): game.MatchEndResult;

        /**
         * Creates a plain object from a MatchEndResult message. Also converts values to other types if specified.
         * @param message MatchEndResult
         * @param [options] Conversion options
         * @returns Plain object
         */
        static toObject(message: game.MatchEndResult, options?: $protobuf.IConversionOptions): { [k: string]: any };

        /**
         * Converts this MatchEndResult to JSON.
         * @returns JSON object
         */
        toJSON(): { [k: string]: any };

        /**
         * Gets the type url for MatchEndResult
         * @param [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns The type url
         */
        static getTypeUrl(prefix?: string): string;
    }

    namespace MatchEndResult {

        /** Properties of a MatchEndResult. */
        interface $Properties {

            /** MatchEndResult reason */
            reason?: string;

            /** MatchEndResult finalHandNum */
            finalHandNum?: number;

            /** MatchEndResult standings */
            standings?: game.PlayerStanding.$Properties[];

            /** Unknown fields preserved while decoding when enabled */
            $unknowns?: Uint8Array[];
        }

        /** Shape of a MatchEndResult. */
        type $Shape = game.MatchEndResult.$Properties;
    }
}
