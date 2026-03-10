/*eslint-disable block-scoped-var, id-length, no-control-regex, no-magic-numbers, no-prototype-builtins, no-redeclare, no-shadow, no-var, sort-vars*/
import * as $protobuf from "protobufjs/minimal";

// Common aliases
const $Reader = $protobuf.Reader, $Writer = $protobuf.Writer, $util = $protobuf.util;

// Exported root namespace
const $root = $protobuf.roots["default"] || ($protobuf.roots["default"] = {});

export const game = $root.game = (() => {

    /**
     * Namespace game.
     * @exports game
     * @namespace
     */
    const game = {};

    /**
     * Suit enum.
     * @name game.Suit
     * @enum {number}
     * @property {number} SUIT_UNKNOWN=0 SUIT_UNKNOWN value
     * @property {number} SUIT_SOU=1 SUIT_SOU value
     * @property {number} SUIT_PIN=2 SUIT_PIN value
     * @property {number} SUIT_MAN=3 SUIT_MAN value
     * @property {number} SUIT_JIHAI=4 SUIT_JIHAI value
     * @property {number} SUIT_FLOWER=5 SUIT_FLOWER value
     */
    game.Suit = (function() {
        const valuesById = {}, values = Object.create(valuesById);
        values[valuesById[0] = "SUIT_UNKNOWN"] = 0;
        values[valuesById[1] = "SUIT_SOU"] = 1;
        values[valuesById[2] = "SUIT_PIN"] = 2;
        values[valuesById[3] = "SUIT_MAN"] = 3;
        values[valuesById[4] = "SUIT_JIHAI"] = 4;
        values[valuesById[5] = "SUIT_FLOWER"] = 5;
        return values;
    })();

    game.Tile = (function() {

        /**
         * Properties of a Tile.
         * @memberof game
         * @interface ITile
         * @property {number|undefined} [id] Tile id
         * @property {game.Suit|undefined} [suit] Tile suit
         * @property {number|undefined} [value] Tile value
         */

        /**
         * Constructs a new Tile.
         * @memberof game
         * @classdesc Represents a Tile.
         * @implements ITile
         * @constructor
         * @param {game.ITile=} [properties] Properties to set
         */
        function Tile(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * Tile id.
         * @member {number} id
         * @memberof game.Tile
         * @instance
         */
        Tile.prototype.id = 0;

        /**
         * Tile suit.
         * @member {game.Suit} suit
         * @memberof game.Tile
         * @instance
         */
        Tile.prototype.suit = 0;

        /**
         * Tile value.
         * @member {number} value
         * @memberof game.Tile
         * @instance
         */
        Tile.prototype.value = 0;

        /**
         * Creates a new Tile instance using the specified properties.
         * @function create
         * @memberof game.Tile
         * @static
         * @param {game.ITile=} [properties] Properties to set
         * @returns {game.Tile} Tile instance
         */
        Tile.create = function create(properties) {
            return new Tile(properties);
        };

        /**
         * Encodes the specified Tile message. Does not implicitly {@link game.Tile.verify|verify} messages.
         * @function encode
         * @memberof game.Tile
         * @static
         * @param {game.ITile} message Tile message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Tile.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.id != null && Object.hasOwnProperty.call(message, "id"))
                writer.uint32(/* id 1, wireType 0 =*/8).uint32(message.id);
            if (message.suit != null && Object.hasOwnProperty.call(message, "suit"))
                writer.uint32(/* id 2, wireType 0 =*/16).int32(message.suit);
            if (message.value != null && Object.hasOwnProperty.call(message, "value"))
                writer.uint32(/* id 3, wireType 0 =*/24).uint32(message.value);
            return writer;
        };

        /**
         * Encodes the specified Tile message, length delimited. Does not implicitly {@link game.Tile.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.Tile
         * @static
         * @param {game.ITile} message Tile message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Tile.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a Tile message from the specified reader or buffer.
         * @function decode
         * @memberof game.Tile
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.Tile} Tile
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Tile.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.Tile();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.id = reader.uint32();
                        break;
                    }
                case 2: {
                        message.suit = reader.int32();
                        break;
                    }
                case 3: {
                        message.value = reader.uint32();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a Tile message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.Tile
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.Tile} Tile
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Tile.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a Tile message.
         * @function verify
         * @memberof game.Tile
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        Tile.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.id != null && message.hasOwnProperty("id"))
                if (!$util.isInteger(message.id))
                    return "id: integer expected";
            if (message.suit != null && message.hasOwnProperty("suit"))
                switch (message.suit) {
                default:
                    return "suit: enum value expected";
                case 0:
                case 1:
                case 2:
                case 3:
                case 4:
                case 5:
                    break;
                }
            if (message.value != null && message.hasOwnProperty("value"))
                if (!$util.isInteger(message.value))
                    return "value: integer expected";
            return null;
        };

        /**
         * Creates a Tile message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.Tile
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.Tile} Tile
         */
        Tile.fromObject = function fromObject(object) {
            if (object instanceof $root.game.Tile)
                return object;
            let message = new $root.game.Tile();
            if (object.id != null)
                message.id = object.id >>> 0;
            switch (object.suit) {
            default:
                if (typeof object.suit === "number") {
                    message.suit = object.suit;
                    break;
                }
                break;
            case "SUIT_UNKNOWN":
            case 0:
                message.suit = 0;
                break;
            case "SUIT_SOU":
            case 1:
                message.suit = 1;
                break;
            case "SUIT_PIN":
            case 2:
                message.suit = 2;
                break;
            case "SUIT_MAN":
            case 3:
                message.suit = 3;
                break;
            case "SUIT_JIHAI":
            case 4:
                message.suit = 4;
                break;
            case "SUIT_FLOWER":
            case 5:
                message.suit = 5;
                break;
            }
            if (object.value != null)
                message.value = object.value >>> 0;
            return message;
        };

        /**
         * Creates a plain object from a Tile message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.Tile
         * @static
         * @param {game.Tile} message Tile
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        Tile.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults) {
                object.id = 0;
                object.suit = options.enums === String ? "SUIT_UNKNOWN" : 0;
                object.value = 0;
            }
            if (message.id != null && message.hasOwnProperty("id"))
                object.id = message.id;
            if (message.suit != null && message.hasOwnProperty("suit"))
                object.suit = options.enums === String ? $root.game.Suit[message.suit] === undefined ? message.suit : $root.game.Suit[message.suit] : message.suit;
            if (message.value != null && message.hasOwnProperty("value"))
                object.value = message.value;
            return object;
        };

        /**
         * Converts this Tile to JSON.
         * @function toJSON
         * @memberof game.Tile
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        Tile.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for Tile
         * @function getTypeUrl
         * @memberof game.Tile
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        Tile.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.Tile";
        };

        return Tile;
    })();

    /**
     * ActionType enum.
     * @name game.ActionType
     * @enum {number}
     * @property {number} ACTION_UNKNOWN=0 ACTION_UNKNOWN value
     * @property {number} ACTION_DRAW=1 ACTION_DRAW value
     * @property {number} ACTION_DISCARD=2 ACTION_DISCARD value
     * @property {number} ACTION_CHII=3 ACTION_CHII value
     * @property {number} ACTION_PON=4 ACTION_PON value
     * @property {number} ACTION_KAN=5 ACTION_KAN value
     * @property {number} ACTION_TSUMO=6 ACTION_TSUMO value
     * @property {number} ACTION_RON=7 ACTION_RON value
     * @property {number} ACTION_PASS=8 ACTION_PASS value
     * @property {number} ACTION_FLOWER_REVEAL=9 ACTION_FLOWER_REVEAL value
     * @property {number} ACTION_READY=10 ACTION_READY value
     * @property {number} ACTION_ACCEPT_HAITEI=11 ACTION_ACCEPT_HAITEI value
     * @property {number} ACTION_REFUSE_HAITEI=12 ACTION_REFUSE_HAITEI value
     */
    game.ActionType = (function() {
        const valuesById = {}, values = Object.create(valuesById);
        values[valuesById[0] = "ACTION_UNKNOWN"] = 0;
        values[valuesById[1] = "ACTION_DRAW"] = 1;
        values[valuesById[2] = "ACTION_DISCARD"] = 2;
        values[valuesById[3] = "ACTION_CHII"] = 3;
        values[valuesById[4] = "ACTION_PON"] = 4;
        values[valuesById[5] = "ACTION_KAN"] = 5;
        values[valuesById[6] = "ACTION_TSUMO"] = 6;
        values[valuesById[7] = "ACTION_RON"] = 7;
        values[valuesById[8] = "ACTION_PASS"] = 8;
        values[valuesById[9] = "ACTION_FLOWER_REVEAL"] = 9;
        values[valuesById[10] = "ACTION_READY"] = 10;
        values[valuesById[11] = "ACTION_ACCEPT_HAITEI"] = 11;
        values[valuesById[12] = "ACTION_REFUSE_HAITEI"] = 12;
        return values;
    })();

    game.PlayerAction = (function() {

        /**
         * Properties of a PlayerAction.
         * @memberof game
         * @interface IPlayerAction
         * @property {game.ActionType|undefined} [type] PlayerAction type
         * @property {game.ITile|undefined} [tile] PlayerAction tile
         * @property {Array.<game.ITile>|undefined} [meldTiles] PlayerAction meldTiles
         * @property {number|undefined} [targetPlayer] PlayerAction targetPlayer
         * @property {boolean|undefined} [isRobbingKong] PlayerAction isRobbingKong
         * @property {boolean|undefined} [isBottomTile] PlayerAction isBottomTile
         * @property {boolean|undefined} [isBloomingKong] PlayerAction isBloomingKong
         */

        /**
         * Constructs a new PlayerAction.
         * @memberof game
         * @classdesc Represents a PlayerAction.
         * @implements IPlayerAction
         * @constructor
         * @param {game.IPlayerAction=} [properties] Properties to set
         */
        function PlayerAction(properties) {
            this.meldTiles = [];
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * PlayerAction type.
         * @member {game.ActionType} type
         * @memberof game.PlayerAction
         * @instance
         */
        PlayerAction.prototype.type = 0;

        /**
         * PlayerAction tile.
         * @member {game.Tile} tile
         * @memberof game.PlayerAction
         * @instance
         */
        PlayerAction.prototype.tile = null;

        /**
         * PlayerAction meldTiles.
         * @member {Array.<game.Tile>} meldTiles
         * @memberof game.PlayerAction
         * @instance
         */
        PlayerAction.prototype.meldTiles = $util.emptyArray;

        /**
         * PlayerAction targetPlayer.
         * @member {number} targetPlayer
         * @memberof game.PlayerAction
         * @instance
         */
        PlayerAction.prototype.targetPlayer = 0;

        /**
         * PlayerAction isRobbingKong.
         * @member {boolean} isRobbingKong
         * @memberof game.PlayerAction
         * @instance
         */
        PlayerAction.prototype.isRobbingKong = false;

        /**
         * PlayerAction isBottomTile.
         * @member {boolean} isBottomTile
         * @memberof game.PlayerAction
         * @instance
         */
        PlayerAction.prototype.isBottomTile = false;

        /**
         * PlayerAction isBloomingKong.
         * @member {boolean} isBloomingKong
         * @memberof game.PlayerAction
         * @instance
         */
        PlayerAction.prototype.isBloomingKong = false;

        /**
         * Creates a new PlayerAction instance using the specified properties.
         * @function create
         * @memberof game.PlayerAction
         * @static
         * @param {game.IPlayerAction=} [properties] Properties to set
         * @returns {game.PlayerAction} PlayerAction instance
         */
        PlayerAction.create = function create(properties) {
            return new PlayerAction(properties);
        };

        /**
         * Encodes the specified PlayerAction message. Does not implicitly {@link game.PlayerAction.verify|verify} messages.
         * @function encode
         * @memberof game.PlayerAction
         * @static
         * @param {game.IPlayerAction} message PlayerAction message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PlayerAction.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.type != null && Object.hasOwnProperty.call(message, "type"))
                writer.uint32(/* id 1, wireType 0 =*/8).int32(message.type);
            if (message.tile != null && Object.hasOwnProperty.call(message, "tile"))
                $root.game.Tile.encode(message.tile, writer.uint32(/* id 2, wireType 2 =*/18).fork()).ldelim();
            if (message.meldTiles != null && message.meldTiles.length)
                for (let i = 0; i < message.meldTiles.length; ++i)
                    $root.game.Tile.encode(message.meldTiles[i], writer.uint32(/* id 3, wireType 2 =*/26).fork()).ldelim();
            if (message.targetPlayer != null && Object.hasOwnProperty.call(message, "targetPlayer"))
                writer.uint32(/* id 4, wireType 0 =*/32).uint32(message.targetPlayer);
            if (message.isRobbingKong != null && Object.hasOwnProperty.call(message, "isRobbingKong"))
                writer.uint32(/* id 5, wireType 0 =*/40).bool(message.isRobbingKong);
            if (message.isBottomTile != null && Object.hasOwnProperty.call(message, "isBottomTile"))
                writer.uint32(/* id 6, wireType 0 =*/48).bool(message.isBottomTile);
            if (message.isBloomingKong != null && Object.hasOwnProperty.call(message, "isBloomingKong"))
                writer.uint32(/* id 7, wireType 0 =*/56).bool(message.isBloomingKong);
            return writer;
        };

        /**
         * Encodes the specified PlayerAction message, length delimited. Does not implicitly {@link game.PlayerAction.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.PlayerAction
         * @static
         * @param {game.IPlayerAction} message PlayerAction message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PlayerAction.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a PlayerAction message from the specified reader or buffer.
         * @function decode
         * @memberof game.PlayerAction
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.PlayerAction} PlayerAction
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PlayerAction.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.PlayerAction();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.type = reader.int32();
                        break;
                    }
                case 2: {
                        message.tile = $root.game.Tile.decode(reader, reader.uint32());
                        break;
                    }
                case 3: {
                        if (!(message.meldTiles && message.meldTiles.length))
                            message.meldTiles = [];
                        message.meldTiles.push($root.game.Tile.decode(reader, reader.uint32()));
                        break;
                    }
                case 4: {
                        message.targetPlayer = reader.uint32();
                        break;
                    }
                case 5: {
                        message.isRobbingKong = reader.bool();
                        break;
                    }
                case 6: {
                        message.isBottomTile = reader.bool();
                        break;
                    }
                case 7: {
                        message.isBloomingKong = reader.bool();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a PlayerAction message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.PlayerAction
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.PlayerAction} PlayerAction
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PlayerAction.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a PlayerAction message.
         * @function verify
         * @memberof game.PlayerAction
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        PlayerAction.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.type != null && message.hasOwnProperty("type"))
                switch (message.type) {
                default:
                    return "type: enum value expected";
                case 0:
                case 1:
                case 2:
                case 3:
                case 4:
                case 5:
                case 6:
                case 7:
                case 8:
                case 9:
                case 10:
                case 11:
                case 12:
                    break;
                }
            if (message.tile != null && message.hasOwnProperty("tile")) {
                let error = $root.game.Tile.verify(message.tile);
                if (error)
                    return "tile." + error;
            }
            if (message.meldTiles != null && message.hasOwnProperty("meldTiles")) {
                if (!Array.isArray(message.meldTiles))
                    return "meldTiles: array expected";
                for (let i = 0; i < message.meldTiles.length; ++i) {
                    let error = $root.game.Tile.verify(message.meldTiles[i]);
                    if (error)
                        return "meldTiles." + error;
                }
            }
            if (message.targetPlayer != null && message.hasOwnProperty("targetPlayer"))
                if (!$util.isInteger(message.targetPlayer))
                    return "targetPlayer: integer expected";
            if (message.isRobbingKong != null && message.hasOwnProperty("isRobbingKong"))
                if (typeof message.isRobbingKong !== "boolean")
                    return "isRobbingKong: boolean expected";
            if (message.isBottomTile != null && message.hasOwnProperty("isBottomTile"))
                if (typeof message.isBottomTile !== "boolean")
                    return "isBottomTile: boolean expected";
            if (message.isBloomingKong != null && message.hasOwnProperty("isBloomingKong"))
                if (typeof message.isBloomingKong !== "boolean")
                    return "isBloomingKong: boolean expected";
            return null;
        };

        /**
         * Creates a PlayerAction message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.PlayerAction
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.PlayerAction} PlayerAction
         */
        PlayerAction.fromObject = function fromObject(object) {
            if (object instanceof $root.game.PlayerAction)
                return object;
            let message = new $root.game.PlayerAction();
            switch (object.type) {
            default:
                if (typeof object.type === "number") {
                    message.type = object.type;
                    break;
                }
                break;
            case "ACTION_UNKNOWN":
            case 0:
                message.type = 0;
                break;
            case "ACTION_DRAW":
            case 1:
                message.type = 1;
                break;
            case "ACTION_DISCARD":
            case 2:
                message.type = 2;
                break;
            case "ACTION_CHII":
            case 3:
                message.type = 3;
                break;
            case "ACTION_PON":
            case 4:
                message.type = 4;
                break;
            case "ACTION_KAN":
            case 5:
                message.type = 5;
                break;
            case "ACTION_TSUMO":
            case 6:
                message.type = 6;
                break;
            case "ACTION_RON":
            case 7:
                message.type = 7;
                break;
            case "ACTION_PASS":
            case 8:
                message.type = 8;
                break;
            case "ACTION_FLOWER_REVEAL":
            case 9:
                message.type = 9;
                break;
            case "ACTION_READY":
            case 10:
                message.type = 10;
                break;
            case "ACTION_ACCEPT_HAITEI":
            case 11:
                message.type = 11;
                break;
            case "ACTION_REFUSE_HAITEI":
            case 12:
                message.type = 12;
                break;
            }
            if (object.tile != null) {
                if (typeof object.tile !== "object")
                    throw TypeError(".game.PlayerAction.tile: object expected");
                message.tile = $root.game.Tile.fromObject(object.tile);
            }
            if (object.meldTiles) {
                if (!Array.isArray(object.meldTiles))
                    throw TypeError(".game.PlayerAction.meldTiles: array expected");
                message.meldTiles = [];
                for (let i = 0; i < object.meldTiles.length; ++i) {
                    if (typeof object.meldTiles[i] !== "object")
                        throw TypeError(".game.PlayerAction.meldTiles: object expected");
                    message.meldTiles[i] = $root.game.Tile.fromObject(object.meldTiles[i]);
                }
            }
            if (object.targetPlayer != null)
                message.targetPlayer = object.targetPlayer >>> 0;
            if (object.isRobbingKong != null)
                message.isRobbingKong = Boolean(object.isRobbingKong);
            if (object.isBottomTile != null)
                message.isBottomTile = Boolean(object.isBottomTile);
            if (object.isBloomingKong != null)
                message.isBloomingKong = Boolean(object.isBloomingKong);
            return message;
        };

        /**
         * Creates a plain object from a PlayerAction message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.PlayerAction
         * @static
         * @param {game.PlayerAction} message PlayerAction
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        PlayerAction.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.arrays || options.defaults)
                object.meldTiles = [];
            if (options.defaults) {
                object.type = options.enums === String ? "ACTION_UNKNOWN" : 0;
                object.tile = null;
                object.targetPlayer = 0;
                object.isRobbingKong = false;
                object.isBottomTile = false;
                object.isBloomingKong = false;
            }
            if (message.type != null && message.hasOwnProperty("type"))
                object.type = options.enums === String ? $root.game.ActionType[message.type] === undefined ? message.type : $root.game.ActionType[message.type] : message.type;
            if (message.tile != null && message.hasOwnProperty("tile"))
                object.tile = $root.game.Tile.toObject(message.tile, options);
            if (message.meldTiles && message.meldTiles.length) {
                object.meldTiles = [];
                for (let j = 0; j < message.meldTiles.length; ++j)
                    object.meldTiles[j] = $root.game.Tile.toObject(message.meldTiles[j], options);
            }
            if (message.targetPlayer != null && message.hasOwnProperty("targetPlayer"))
                object.targetPlayer = message.targetPlayer;
            if (message.isRobbingKong != null && message.hasOwnProperty("isRobbingKong"))
                object.isRobbingKong = message.isRobbingKong;
            if (message.isBottomTile != null && message.hasOwnProperty("isBottomTile"))
                object.isBottomTile = message.isBottomTile;
            if (message.isBloomingKong != null && message.hasOwnProperty("isBloomingKong"))
                object.isBloomingKong = message.isBloomingKong;
            return object;
        };

        /**
         * Converts this PlayerAction to JSON.
         * @function toJSON
         * @memberof game.PlayerAction
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        PlayerAction.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for PlayerAction
         * @function getTypeUrl
         * @memberof game.PlayerAction
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        PlayerAction.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.PlayerAction";
        };

        return PlayerAction;
    })();

    /**
     * MeldDirection enum.
     * @name game.MeldDirection
     * @enum {number}
     * @property {number} MELD_DIRECTION_UNKNOWN=0 MELD_DIRECTION_UNKNOWN value
     * @property {number} MELD_DIRECTION_RIGHT=1 MELD_DIRECTION_RIGHT value
     * @property {number} MELD_DIRECTION_ACROSS=2 MELD_DIRECTION_ACROSS value
     * @property {number} MELD_DIRECTION_LEFT=3 MELD_DIRECTION_LEFT value
     */
    game.MeldDirection = (function() {
        const valuesById = {}, values = Object.create(valuesById);
        values[valuesById[0] = "MELD_DIRECTION_UNKNOWN"] = 0;
        values[valuesById[1] = "MELD_DIRECTION_RIGHT"] = 1;
        values[valuesById[2] = "MELD_DIRECTION_ACROSS"] = 2;
        values[valuesById[3] = "MELD_DIRECTION_LEFT"] = 3;
        return values;
    })();

    game.Meld = (function() {

        /**
         * Properties of a Meld.
         * @memberof game
         * @interface IMeld
         * @property {game.ActionType|undefined} [type] Meld type
         * @property {Array.<game.ITile>|undefined} [tiles] Meld tiles
         * @property {game.MeldDirection|undefined} [calledDirection] Meld calledDirection
         * @property {number|undefined} [calledTileId] Meld calledTileId
         */

        /**
         * Constructs a new Meld.
         * @memberof game
         * @classdesc Represents a Meld.
         * @implements IMeld
         * @constructor
         * @param {game.IMeld=} [properties] Properties to set
         */
        function Meld(properties) {
            this.tiles = [];
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * Meld type.
         * @member {game.ActionType} type
         * @memberof game.Meld
         * @instance
         */
        Meld.prototype.type = 0;

        /**
         * Meld tiles.
         * @member {Array.<game.Tile>} tiles
         * @memberof game.Meld
         * @instance
         */
        Meld.prototype.tiles = $util.emptyArray;

        /**
         * Meld calledDirection.
         * @member {game.MeldDirection} calledDirection
         * @memberof game.Meld
         * @instance
         */
        Meld.prototype.calledDirection = 0;

        /**
         * Meld calledTileId.
         * @member {number} calledTileId
         * @memberof game.Meld
         * @instance
         */
        Meld.prototype.calledTileId = 0;

        /**
         * Creates a new Meld instance using the specified properties.
         * @function create
         * @memberof game.Meld
         * @static
         * @param {game.IMeld=} [properties] Properties to set
         * @returns {game.Meld} Meld instance
         */
        Meld.create = function create(properties) {
            return new Meld(properties);
        };

        /**
         * Encodes the specified Meld message. Does not implicitly {@link game.Meld.verify|verify} messages.
         * @function encode
         * @memberof game.Meld
         * @static
         * @param {game.IMeld} message Meld message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Meld.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.type != null && Object.hasOwnProperty.call(message, "type"))
                writer.uint32(/* id 1, wireType 0 =*/8).int32(message.type);
            if (message.tiles != null && message.tiles.length)
                for (let i = 0; i < message.tiles.length; ++i)
                    $root.game.Tile.encode(message.tiles[i], writer.uint32(/* id 2, wireType 2 =*/18).fork()).ldelim();
            if (message.calledDirection != null && Object.hasOwnProperty.call(message, "calledDirection"))
                writer.uint32(/* id 3, wireType 0 =*/24).int32(message.calledDirection);
            if (message.calledTileId != null && Object.hasOwnProperty.call(message, "calledTileId"))
                writer.uint32(/* id 4, wireType 0 =*/32).uint32(message.calledTileId);
            return writer;
        };

        /**
         * Encodes the specified Meld message, length delimited. Does not implicitly {@link game.Meld.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.Meld
         * @static
         * @param {game.IMeld} message Meld message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Meld.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a Meld message from the specified reader or buffer.
         * @function decode
         * @memberof game.Meld
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.Meld} Meld
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Meld.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.Meld();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.type = reader.int32();
                        break;
                    }
                case 2: {
                        if (!(message.tiles && message.tiles.length))
                            message.tiles = [];
                        message.tiles.push($root.game.Tile.decode(reader, reader.uint32()));
                        break;
                    }
                case 3: {
                        message.calledDirection = reader.int32();
                        break;
                    }
                case 4: {
                        message.calledTileId = reader.uint32();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a Meld message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.Meld
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.Meld} Meld
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Meld.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a Meld message.
         * @function verify
         * @memberof game.Meld
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        Meld.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.type != null && message.hasOwnProperty("type"))
                switch (message.type) {
                default:
                    return "type: enum value expected";
                case 0:
                case 1:
                case 2:
                case 3:
                case 4:
                case 5:
                case 6:
                case 7:
                case 8:
                case 9:
                case 10:
                case 11:
                case 12:
                    break;
                }
            if (message.tiles != null && message.hasOwnProperty("tiles")) {
                if (!Array.isArray(message.tiles))
                    return "tiles: array expected";
                for (let i = 0; i < message.tiles.length; ++i) {
                    let error = $root.game.Tile.verify(message.tiles[i]);
                    if (error)
                        return "tiles." + error;
                }
            }
            if (message.calledDirection != null && message.hasOwnProperty("calledDirection"))
                switch (message.calledDirection) {
                default:
                    return "calledDirection: enum value expected";
                case 0:
                case 1:
                case 2:
                case 3:
                    break;
                }
            if (message.calledTileId != null && message.hasOwnProperty("calledTileId"))
                if (!$util.isInteger(message.calledTileId))
                    return "calledTileId: integer expected";
            return null;
        };

        /**
         * Creates a Meld message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.Meld
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.Meld} Meld
         */
        Meld.fromObject = function fromObject(object) {
            if (object instanceof $root.game.Meld)
                return object;
            let message = new $root.game.Meld();
            switch (object.type) {
            default:
                if (typeof object.type === "number") {
                    message.type = object.type;
                    break;
                }
                break;
            case "ACTION_UNKNOWN":
            case 0:
                message.type = 0;
                break;
            case "ACTION_DRAW":
            case 1:
                message.type = 1;
                break;
            case "ACTION_DISCARD":
            case 2:
                message.type = 2;
                break;
            case "ACTION_CHII":
            case 3:
                message.type = 3;
                break;
            case "ACTION_PON":
            case 4:
                message.type = 4;
                break;
            case "ACTION_KAN":
            case 5:
                message.type = 5;
                break;
            case "ACTION_TSUMO":
            case 6:
                message.type = 6;
                break;
            case "ACTION_RON":
            case 7:
                message.type = 7;
                break;
            case "ACTION_PASS":
            case 8:
                message.type = 8;
                break;
            case "ACTION_FLOWER_REVEAL":
            case 9:
                message.type = 9;
                break;
            case "ACTION_READY":
            case 10:
                message.type = 10;
                break;
            case "ACTION_ACCEPT_HAITEI":
            case 11:
                message.type = 11;
                break;
            case "ACTION_REFUSE_HAITEI":
            case 12:
                message.type = 12;
                break;
            }
            if (object.tiles) {
                if (!Array.isArray(object.tiles))
                    throw TypeError(".game.Meld.tiles: array expected");
                message.tiles = [];
                for (let i = 0; i < object.tiles.length; ++i) {
                    if (typeof object.tiles[i] !== "object")
                        throw TypeError(".game.Meld.tiles: object expected");
                    message.tiles[i] = $root.game.Tile.fromObject(object.tiles[i]);
                }
            }
            switch (object.calledDirection) {
            default:
                if (typeof object.calledDirection === "number") {
                    message.calledDirection = object.calledDirection;
                    break;
                }
                break;
            case "MELD_DIRECTION_UNKNOWN":
            case 0:
                message.calledDirection = 0;
                break;
            case "MELD_DIRECTION_RIGHT":
            case 1:
                message.calledDirection = 1;
                break;
            case "MELD_DIRECTION_ACROSS":
            case 2:
                message.calledDirection = 2;
                break;
            case "MELD_DIRECTION_LEFT":
            case 3:
                message.calledDirection = 3;
                break;
            }
            if (object.calledTileId != null)
                message.calledTileId = object.calledTileId >>> 0;
            return message;
        };

        /**
         * Creates a plain object from a Meld message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.Meld
         * @static
         * @param {game.Meld} message Meld
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        Meld.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.arrays || options.defaults)
                object.tiles = [];
            if (options.defaults) {
                object.type = options.enums === String ? "ACTION_UNKNOWN" : 0;
                object.calledDirection = options.enums === String ? "MELD_DIRECTION_UNKNOWN" : 0;
                object.calledTileId = 0;
            }
            if (message.type != null && message.hasOwnProperty("type"))
                object.type = options.enums === String ? $root.game.ActionType[message.type] === undefined ? message.type : $root.game.ActionType[message.type] : message.type;
            if (message.tiles && message.tiles.length) {
                object.tiles = [];
                for (let j = 0; j < message.tiles.length; ++j)
                    object.tiles[j] = $root.game.Tile.toObject(message.tiles[j], options);
            }
            if (message.calledDirection != null && message.hasOwnProperty("calledDirection"))
                object.calledDirection = options.enums === String ? $root.game.MeldDirection[message.calledDirection] === undefined ? message.calledDirection : $root.game.MeldDirection[message.calledDirection] : message.calledDirection;
            if (message.calledTileId != null && message.hasOwnProperty("calledTileId"))
                object.calledTileId = message.calledTileId;
            return object;
        };

        /**
         * Converts this Meld to JSON.
         * @function toJSON
         * @memberof game.Meld
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        Meld.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for Meld
         * @function getTypeUrl
         * @memberof game.Meld
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        Meld.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.Meld";
        };

        return Meld;
    })();

    game.PlayerState = (function() {

        /**
         * Properties of a PlayerState.
         * @memberof game
         * @interface IPlayerState
         * @property {number|undefined} [seat] PlayerState seat
         * @property {number|undefined} [score] PlayerState score
         * @property {Array.<game.ITile>|undefined} [closedHand] PlayerState closedHand
         * @property {number|undefined} [handSize] PlayerState handSize
         * @property {Array.<game.IMeld>|undefined} [openMelds] PlayerState openMelds
         * @property {Array.<game.ITile>|undefined} [discards] PlayerState discards
         * @property {number|undefined} [seatWind] PlayerState seatWind
         * @property {Array.<game.ITile>|undefined} [flowerMelds] PlayerState flowerMelds
         * @property {boolean|undefined} [hasBuddingDirectKong] PlayerState hasBuddingDirectKong
         * @property {boolean|undefined} [hasBloomingDirectKong] PlayerState hasBloomingDirectKong
         * @property {boolean|undefined} [hasBuddingClosedKong] PlayerState hasBuddingClosedKong
         * @property {boolean|undefined} [hasBloomingClosedKong] PlayerState hasBloomingClosedKong
         * @property {boolean|undefined} [hasBuddingRiskyKong] PlayerState hasBuddingRiskyKong
         * @property {boolean|undefined} [hasBloomingRiskyKong] PlayerState hasBloomingRiskyKong
         * @property {boolean|undefined} [hasBloomingFlowerKong] PlayerState hasBloomingFlowerKong
         * @property {Array.<game.IPlayerAction>|undefined} [validActions] PlayerState validActions
         * @property {number|null|undefined} [drawnTileId] PlayerState drawnTileId
         */

        /**
         * Constructs a new PlayerState.
         * @memberof game
         * @classdesc Represents a PlayerState.
         * @implements IPlayerState
         * @constructor
         * @param {game.IPlayerState=} [properties] Properties to set
         */
        function PlayerState(properties) {
            this.closedHand = [];
            this.openMelds = [];
            this.discards = [];
            this.flowerMelds = [];
            this.validActions = [];
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * PlayerState seat.
         * @member {number} seat
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.seat = 0;

        /**
         * PlayerState score.
         * @member {number} score
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.score = 0;

        /**
         * PlayerState closedHand.
         * @member {Array.<game.Tile>} closedHand
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.closedHand = $util.emptyArray;

        /**
         * PlayerState handSize.
         * @member {number} handSize
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.handSize = 0;

        /**
         * PlayerState openMelds.
         * @member {Array.<game.Meld>} openMelds
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.openMelds = $util.emptyArray;

        /**
         * PlayerState discards.
         * @member {Array.<game.Tile>} discards
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.discards = $util.emptyArray;

        /**
         * PlayerState seatWind.
         * @member {number} seatWind
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.seatWind = 0;

        /**
         * PlayerState flowerMelds.
         * @member {Array.<game.Tile>} flowerMelds
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.flowerMelds = $util.emptyArray;

        /**
         * PlayerState hasBuddingDirectKong.
         * @member {boolean} hasBuddingDirectKong
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.hasBuddingDirectKong = false;

        /**
         * PlayerState hasBloomingDirectKong.
         * @member {boolean} hasBloomingDirectKong
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.hasBloomingDirectKong = false;

        /**
         * PlayerState hasBuddingClosedKong.
         * @member {boolean} hasBuddingClosedKong
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.hasBuddingClosedKong = false;

        /**
         * PlayerState hasBloomingClosedKong.
         * @member {boolean} hasBloomingClosedKong
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.hasBloomingClosedKong = false;

        /**
         * PlayerState hasBuddingRiskyKong.
         * @member {boolean} hasBuddingRiskyKong
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.hasBuddingRiskyKong = false;

        /**
         * PlayerState hasBloomingRiskyKong.
         * @member {boolean} hasBloomingRiskyKong
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.hasBloomingRiskyKong = false;

        /**
         * PlayerState hasBloomingFlowerKong.
         * @member {boolean} hasBloomingFlowerKong
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.hasBloomingFlowerKong = false;

        /**
         * PlayerState validActions.
         * @member {Array.<game.PlayerAction>} validActions
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.validActions = $util.emptyArray;

        /**
         * PlayerState drawnTileId.
         * @member {number|null} drawnTileId
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.drawnTileId = null;

        // OneOf field names bound to virtual getters and setters
        let $oneOfFields;

        // Virtual OneOf for proto3 optional field
        Object.defineProperty(PlayerState.prototype, "_drawnTileId", {
            get: $util.oneOfGetter($oneOfFields = ["drawnTileId"]),
            set: $util.oneOfSetter($oneOfFields)
        });

        /**
         * Creates a new PlayerState instance using the specified properties.
         * @function create
         * @memberof game.PlayerState
         * @static
         * @param {game.IPlayerState=} [properties] Properties to set
         * @returns {game.PlayerState} PlayerState instance
         */
        PlayerState.create = function create(properties) {
            return new PlayerState(properties);
        };

        /**
         * Encodes the specified PlayerState message. Does not implicitly {@link game.PlayerState.verify|verify} messages.
         * @function encode
         * @memberof game.PlayerState
         * @static
         * @param {game.IPlayerState} message PlayerState message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PlayerState.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.seat != null && Object.hasOwnProperty.call(message, "seat"))
                writer.uint32(/* id 1, wireType 0 =*/8).uint32(message.seat);
            if (message.score != null && Object.hasOwnProperty.call(message, "score"))
                writer.uint32(/* id 2, wireType 0 =*/16).int32(message.score);
            if (message.closedHand != null && message.closedHand.length)
                for (let i = 0; i < message.closedHand.length; ++i)
                    $root.game.Tile.encode(message.closedHand[i], writer.uint32(/* id 3, wireType 2 =*/26).fork()).ldelim();
            if (message.handSize != null && Object.hasOwnProperty.call(message, "handSize"))
                writer.uint32(/* id 4, wireType 0 =*/32).uint32(message.handSize);
            if (message.openMelds != null && message.openMelds.length)
                for (let i = 0; i < message.openMelds.length; ++i)
                    $root.game.Meld.encode(message.openMelds[i], writer.uint32(/* id 5, wireType 2 =*/42).fork()).ldelim();
            if (message.discards != null && message.discards.length)
                for (let i = 0; i < message.discards.length; ++i)
                    $root.game.Tile.encode(message.discards[i], writer.uint32(/* id 6, wireType 2 =*/50).fork()).ldelim();
            if (message.seatWind != null && Object.hasOwnProperty.call(message, "seatWind"))
                writer.uint32(/* id 7, wireType 0 =*/56).uint32(message.seatWind);
            if (message.flowerMelds != null && message.flowerMelds.length)
                for (let i = 0; i < message.flowerMelds.length; ++i)
                    $root.game.Tile.encode(message.flowerMelds[i], writer.uint32(/* id 8, wireType 2 =*/66).fork()).ldelim();
            if (message.hasBuddingDirectKong != null && Object.hasOwnProperty.call(message, "hasBuddingDirectKong"))
                writer.uint32(/* id 9, wireType 0 =*/72).bool(message.hasBuddingDirectKong);
            if (message.hasBloomingDirectKong != null && Object.hasOwnProperty.call(message, "hasBloomingDirectKong"))
                writer.uint32(/* id 10, wireType 0 =*/80).bool(message.hasBloomingDirectKong);
            if (message.hasBuddingClosedKong != null && Object.hasOwnProperty.call(message, "hasBuddingClosedKong"))
                writer.uint32(/* id 11, wireType 0 =*/88).bool(message.hasBuddingClosedKong);
            if (message.hasBloomingClosedKong != null && Object.hasOwnProperty.call(message, "hasBloomingClosedKong"))
                writer.uint32(/* id 12, wireType 0 =*/96).bool(message.hasBloomingClosedKong);
            if (message.hasBuddingRiskyKong != null && Object.hasOwnProperty.call(message, "hasBuddingRiskyKong"))
                writer.uint32(/* id 13, wireType 0 =*/104).bool(message.hasBuddingRiskyKong);
            if (message.hasBloomingRiskyKong != null && Object.hasOwnProperty.call(message, "hasBloomingRiskyKong"))
                writer.uint32(/* id 14, wireType 0 =*/112).bool(message.hasBloomingRiskyKong);
            if (message.hasBloomingFlowerKong != null && Object.hasOwnProperty.call(message, "hasBloomingFlowerKong"))
                writer.uint32(/* id 15, wireType 0 =*/120).bool(message.hasBloomingFlowerKong);
            if (message.validActions != null && message.validActions.length)
                for (let i = 0; i < message.validActions.length; ++i)
                    $root.game.PlayerAction.encode(message.validActions[i], writer.uint32(/* id 16, wireType 2 =*/130).fork()).ldelim();
            if (message.drawnTileId != null && Object.hasOwnProperty.call(message, "drawnTileId"))
                writer.uint32(/* id 17, wireType 0 =*/136).int32(message.drawnTileId);
            return writer;
        };

        /**
         * Encodes the specified PlayerState message, length delimited. Does not implicitly {@link game.PlayerState.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.PlayerState
         * @static
         * @param {game.IPlayerState} message PlayerState message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PlayerState.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a PlayerState message from the specified reader or buffer.
         * @function decode
         * @memberof game.PlayerState
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.PlayerState} PlayerState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PlayerState.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.PlayerState();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.seat = reader.uint32();
                        break;
                    }
                case 2: {
                        message.score = reader.int32();
                        break;
                    }
                case 3: {
                        if (!(message.closedHand && message.closedHand.length))
                            message.closedHand = [];
                        message.closedHand.push($root.game.Tile.decode(reader, reader.uint32()));
                        break;
                    }
                case 4: {
                        message.handSize = reader.uint32();
                        break;
                    }
                case 5: {
                        if (!(message.openMelds && message.openMelds.length))
                            message.openMelds = [];
                        message.openMelds.push($root.game.Meld.decode(reader, reader.uint32()));
                        break;
                    }
                case 6: {
                        if (!(message.discards && message.discards.length))
                            message.discards = [];
                        message.discards.push($root.game.Tile.decode(reader, reader.uint32()));
                        break;
                    }
                case 7: {
                        message.seatWind = reader.uint32();
                        break;
                    }
                case 8: {
                        if (!(message.flowerMelds && message.flowerMelds.length))
                            message.flowerMelds = [];
                        message.flowerMelds.push($root.game.Tile.decode(reader, reader.uint32()));
                        break;
                    }
                case 9: {
                        message.hasBuddingDirectKong = reader.bool();
                        break;
                    }
                case 10: {
                        message.hasBloomingDirectKong = reader.bool();
                        break;
                    }
                case 11: {
                        message.hasBuddingClosedKong = reader.bool();
                        break;
                    }
                case 12: {
                        message.hasBloomingClosedKong = reader.bool();
                        break;
                    }
                case 13: {
                        message.hasBuddingRiskyKong = reader.bool();
                        break;
                    }
                case 14: {
                        message.hasBloomingRiskyKong = reader.bool();
                        break;
                    }
                case 15: {
                        message.hasBloomingFlowerKong = reader.bool();
                        break;
                    }
                case 16: {
                        if (!(message.validActions && message.validActions.length))
                            message.validActions = [];
                        message.validActions.push($root.game.PlayerAction.decode(reader, reader.uint32()));
                        break;
                    }
                case 17: {
                        message.drawnTileId = reader.int32();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a PlayerState message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.PlayerState
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.PlayerState} PlayerState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PlayerState.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a PlayerState message.
         * @function verify
         * @memberof game.PlayerState
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        PlayerState.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            let properties = {};
            if (message.seat != null && message.hasOwnProperty("seat"))
                if (!$util.isInteger(message.seat))
                    return "seat: integer expected";
            if (message.score != null && message.hasOwnProperty("score"))
                if (!$util.isInteger(message.score))
                    return "score: integer expected";
            if (message.closedHand != null && message.hasOwnProperty("closedHand")) {
                if (!Array.isArray(message.closedHand))
                    return "closedHand: array expected";
                for (let i = 0; i < message.closedHand.length; ++i) {
                    let error = $root.game.Tile.verify(message.closedHand[i]);
                    if (error)
                        return "closedHand." + error;
                }
            }
            if (message.handSize != null && message.hasOwnProperty("handSize"))
                if (!$util.isInteger(message.handSize))
                    return "handSize: integer expected";
            if (message.openMelds != null && message.hasOwnProperty("openMelds")) {
                if (!Array.isArray(message.openMelds))
                    return "openMelds: array expected";
                for (let i = 0; i < message.openMelds.length; ++i) {
                    let error = $root.game.Meld.verify(message.openMelds[i]);
                    if (error)
                        return "openMelds." + error;
                }
            }
            if (message.discards != null && message.hasOwnProperty("discards")) {
                if (!Array.isArray(message.discards))
                    return "discards: array expected";
                for (let i = 0; i < message.discards.length; ++i) {
                    let error = $root.game.Tile.verify(message.discards[i]);
                    if (error)
                        return "discards." + error;
                }
            }
            if (message.seatWind != null && message.hasOwnProperty("seatWind"))
                if (!$util.isInteger(message.seatWind))
                    return "seatWind: integer expected";
            if (message.flowerMelds != null && message.hasOwnProperty("flowerMelds")) {
                if (!Array.isArray(message.flowerMelds))
                    return "flowerMelds: array expected";
                for (let i = 0; i < message.flowerMelds.length; ++i) {
                    let error = $root.game.Tile.verify(message.flowerMelds[i]);
                    if (error)
                        return "flowerMelds." + error;
                }
            }
            if (message.hasBuddingDirectKong != null && message.hasOwnProperty("hasBuddingDirectKong"))
                if (typeof message.hasBuddingDirectKong !== "boolean")
                    return "hasBuddingDirectKong: boolean expected";
            if (message.hasBloomingDirectKong != null && message.hasOwnProperty("hasBloomingDirectKong"))
                if (typeof message.hasBloomingDirectKong !== "boolean")
                    return "hasBloomingDirectKong: boolean expected";
            if (message.hasBuddingClosedKong != null && message.hasOwnProperty("hasBuddingClosedKong"))
                if (typeof message.hasBuddingClosedKong !== "boolean")
                    return "hasBuddingClosedKong: boolean expected";
            if (message.hasBloomingClosedKong != null && message.hasOwnProperty("hasBloomingClosedKong"))
                if (typeof message.hasBloomingClosedKong !== "boolean")
                    return "hasBloomingClosedKong: boolean expected";
            if (message.hasBuddingRiskyKong != null && message.hasOwnProperty("hasBuddingRiskyKong"))
                if (typeof message.hasBuddingRiskyKong !== "boolean")
                    return "hasBuddingRiskyKong: boolean expected";
            if (message.hasBloomingRiskyKong != null && message.hasOwnProperty("hasBloomingRiskyKong"))
                if (typeof message.hasBloomingRiskyKong !== "boolean")
                    return "hasBloomingRiskyKong: boolean expected";
            if (message.hasBloomingFlowerKong != null && message.hasOwnProperty("hasBloomingFlowerKong"))
                if (typeof message.hasBloomingFlowerKong !== "boolean")
                    return "hasBloomingFlowerKong: boolean expected";
            if (message.validActions != null && message.hasOwnProperty("validActions")) {
                if (!Array.isArray(message.validActions))
                    return "validActions: array expected";
                for (let i = 0; i < message.validActions.length; ++i) {
                    let error = $root.game.PlayerAction.verify(message.validActions[i]);
                    if (error)
                        return "validActions." + error;
                }
            }
            if (message.drawnTileId != null && message.hasOwnProperty("drawnTileId")) {
                properties._drawnTileId = 1;
                if (!$util.isInteger(message.drawnTileId))
                    return "drawnTileId: integer expected";
            }
            return null;
        };

        /**
         * Creates a PlayerState message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.PlayerState
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.PlayerState} PlayerState
         */
        PlayerState.fromObject = function fromObject(object) {
            if (object instanceof $root.game.PlayerState)
                return object;
            let message = new $root.game.PlayerState();
            if (object.seat != null)
                message.seat = object.seat >>> 0;
            if (object.score != null)
                message.score = object.score | 0;
            if (object.closedHand) {
                if (!Array.isArray(object.closedHand))
                    throw TypeError(".game.PlayerState.closedHand: array expected");
                message.closedHand = [];
                for (let i = 0; i < object.closedHand.length; ++i) {
                    if (typeof object.closedHand[i] !== "object")
                        throw TypeError(".game.PlayerState.closedHand: object expected");
                    message.closedHand[i] = $root.game.Tile.fromObject(object.closedHand[i]);
                }
            }
            if (object.handSize != null)
                message.handSize = object.handSize >>> 0;
            if (object.openMelds) {
                if (!Array.isArray(object.openMelds))
                    throw TypeError(".game.PlayerState.openMelds: array expected");
                message.openMelds = [];
                for (let i = 0; i < object.openMelds.length; ++i) {
                    if (typeof object.openMelds[i] !== "object")
                        throw TypeError(".game.PlayerState.openMelds: object expected");
                    message.openMelds[i] = $root.game.Meld.fromObject(object.openMelds[i]);
                }
            }
            if (object.discards) {
                if (!Array.isArray(object.discards))
                    throw TypeError(".game.PlayerState.discards: array expected");
                message.discards = [];
                for (let i = 0; i < object.discards.length; ++i) {
                    if (typeof object.discards[i] !== "object")
                        throw TypeError(".game.PlayerState.discards: object expected");
                    message.discards[i] = $root.game.Tile.fromObject(object.discards[i]);
                }
            }
            if (object.seatWind != null)
                message.seatWind = object.seatWind >>> 0;
            if (object.flowerMelds) {
                if (!Array.isArray(object.flowerMelds))
                    throw TypeError(".game.PlayerState.flowerMelds: array expected");
                message.flowerMelds = [];
                for (let i = 0; i < object.flowerMelds.length; ++i) {
                    if (typeof object.flowerMelds[i] !== "object")
                        throw TypeError(".game.PlayerState.flowerMelds: object expected");
                    message.flowerMelds[i] = $root.game.Tile.fromObject(object.flowerMelds[i]);
                }
            }
            if (object.hasBuddingDirectKong != null)
                message.hasBuddingDirectKong = Boolean(object.hasBuddingDirectKong);
            if (object.hasBloomingDirectKong != null)
                message.hasBloomingDirectKong = Boolean(object.hasBloomingDirectKong);
            if (object.hasBuddingClosedKong != null)
                message.hasBuddingClosedKong = Boolean(object.hasBuddingClosedKong);
            if (object.hasBloomingClosedKong != null)
                message.hasBloomingClosedKong = Boolean(object.hasBloomingClosedKong);
            if (object.hasBuddingRiskyKong != null)
                message.hasBuddingRiskyKong = Boolean(object.hasBuddingRiskyKong);
            if (object.hasBloomingRiskyKong != null)
                message.hasBloomingRiskyKong = Boolean(object.hasBloomingRiskyKong);
            if (object.hasBloomingFlowerKong != null)
                message.hasBloomingFlowerKong = Boolean(object.hasBloomingFlowerKong);
            if (object.validActions) {
                if (!Array.isArray(object.validActions))
                    throw TypeError(".game.PlayerState.validActions: array expected");
                message.validActions = [];
                for (let i = 0; i < object.validActions.length; ++i) {
                    if (typeof object.validActions[i] !== "object")
                        throw TypeError(".game.PlayerState.validActions: object expected");
                    message.validActions[i] = $root.game.PlayerAction.fromObject(object.validActions[i]);
                }
            }
            if (object.drawnTileId != null)
                message.drawnTileId = object.drawnTileId | 0;
            return message;
        };

        /**
         * Creates a plain object from a PlayerState message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.PlayerState
         * @static
         * @param {game.PlayerState} message PlayerState
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        PlayerState.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.arrays || options.defaults) {
                object.closedHand = [];
                object.openMelds = [];
                object.discards = [];
                object.flowerMelds = [];
                object.validActions = [];
            }
            if (options.defaults) {
                object.seat = 0;
                object.score = 0;
                object.handSize = 0;
                object.seatWind = 0;
                object.hasBuddingDirectKong = false;
                object.hasBloomingDirectKong = false;
                object.hasBuddingClosedKong = false;
                object.hasBloomingClosedKong = false;
                object.hasBuddingRiskyKong = false;
                object.hasBloomingRiskyKong = false;
                object.hasBloomingFlowerKong = false;
            }
            if (message.seat != null && message.hasOwnProperty("seat"))
                object.seat = message.seat;
            if (message.score != null && message.hasOwnProperty("score"))
                object.score = message.score;
            if (message.closedHand && message.closedHand.length) {
                object.closedHand = [];
                for (let j = 0; j < message.closedHand.length; ++j)
                    object.closedHand[j] = $root.game.Tile.toObject(message.closedHand[j], options);
            }
            if (message.handSize != null && message.hasOwnProperty("handSize"))
                object.handSize = message.handSize;
            if (message.openMelds && message.openMelds.length) {
                object.openMelds = [];
                for (let j = 0; j < message.openMelds.length; ++j)
                    object.openMelds[j] = $root.game.Meld.toObject(message.openMelds[j], options);
            }
            if (message.discards && message.discards.length) {
                object.discards = [];
                for (let j = 0; j < message.discards.length; ++j)
                    object.discards[j] = $root.game.Tile.toObject(message.discards[j], options);
            }
            if (message.seatWind != null && message.hasOwnProperty("seatWind"))
                object.seatWind = message.seatWind;
            if (message.flowerMelds && message.flowerMelds.length) {
                object.flowerMelds = [];
                for (let j = 0; j < message.flowerMelds.length; ++j)
                    object.flowerMelds[j] = $root.game.Tile.toObject(message.flowerMelds[j], options);
            }
            if (message.hasBuddingDirectKong != null && message.hasOwnProperty("hasBuddingDirectKong"))
                object.hasBuddingDirectKong = message.hasBuddingDirectKong;
            if (message.hasBloomingDirectKong != null && message.hasOwnProperty("hasBloomingDirectKong"))
                object.hasBloomingDirectKong = message.hasBloomingDirectKong;
            if (message.hasBuddingClosedKong != null && message.hasOwnProperty("hasBuddingClosedKong"))
                object.hasBuddingClosedKong = message.hasBuddingClosedKong;
            if (message.hasBloomingClosedKong != null && message.hasOwnProperty("hasBloomingClosedKong"))
                object.hasBloomingClosedKong = message.hasBloomingClosedKong;
            if (message.hasBuddingRiskyKong != null && message.hasOwnProperty("hasBuddingRiskyKong"))
                object.hasBuddingRiskyKong = message.hasBuddingRiskyKong;
            if (message.hasBloomingRiskyKong != null && message.hasOwnProperty("hasBloomingRiskyKong"))
                object.hasBloomingRiskyKong = message.hasBloomingRiskyKong;
            if (message.hasBloomingFlowerKong != null && message.hasOwnProperty("hasBloomingFlowerKong"))
                object.hasBloomingFlowerKong = message.hasBloomingFlowerKong;
            if (message.validActions && message.validActions.length) {
                object.validActions = [];
                for (let j = 0; j < message.validActions.length; ++j)
                    object.validActions[j] = $root.game.PlayerAction.toObject(message.validActions[j], options);
            }
            if (message.drawnTileId != null && message.hasOwnProperty("drawnTileId")) {
                object.drawnTileId = message.drawnTileId;
                if (options.oneofs)
                    object._drawnTileId = "drawnTileId";
            }
            return object;
        };

        /**
         * Converts this PlayerState to JSON.
         * @function toJSON
         * @memberof game.PlayerState
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        PlayerState.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for PlayerState
         * @function getTypeUrl
         * @memberof game.PlayerState
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        PlayerState.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.PlayerState";
        };

        return PlayerState;
    })();

    /**
     * GamePhase enum.
     * @name game.GamePhase
     * @enum {number}
     * @property {number} PHASE_INIT=0 PHASE_INIT value
     * @property {number} PHASE_DEAL=1 PHASE_DEAL value
     * @property {number} PHASE_PLAYER_TURN=2 PHASE_PLAYER_TURN value
     * @property {number} PHASE_WAIT_DISCARDS=3 PHASE_WAIT_DISCARDS value
     * @property {number} PHASE_ROUND_END=4 PHASE_ROUND_END value
     */
    game.GamePhase = (function() {
        const valuesById = {}, values = Object.create(valuesById);
        values[valuesById[0] = "PHASE_INIT"] = 0;
        values[valuesById[1] = "PHASE_DEAL"] = 1;
        values[valuesById[2] = "PHASE_PLAYER_TURN"] = 2;
        values[valuesById[3] = "PHASE_WAIT_DISCARDS"] = 3;
        values[valuesById[4] = "PHASE_ROUND_END"] = 4;
        return values;
    })();

    game.GameState = (function() {

        /**
         * Properties of a GameState.
         * @memberof game
         * @interface IGameState
         * @property {string|undefined} [matchId] GameState matchId
         * @property {game.GamePhase|undefined} [phase] GameState phase
         * @property {number|undefined} [activePlayer] GameState activePlayer
         * @property {Array.<game.IPlayerState>|undefined} [players] GameState players
         * @property {number|undefined} [wallCount] GameState wallCount
         * @property {number|undefined} [handNum] GameState handNum
         * @property {game.ITile|undefined} [activeDiscard] GameState activeDiscard
         * @property {Array.<game.ITile>|undefined} [wildTiles] GameState wildTiles
         * @property {number|undefined} [prevailingWind] GameState prevailingWind
         * @property {string|undefined} [wallSeed] GameState wallSeed
         * @property {game.IRoundResult|undefined} [roundResult] GameState roundResult
         * @property {Array.<boolean>|undefined} [playerReady] GameState playerReady
         * @property {number|undefined} [diceSum] GameState diceSum
         * @property {number|undefined} [wangpaiStacks] GameState wangpaiStacks
         * @property {boolean|undefined} [isHaitei] GameState isHaitei
         * @property {number|undefined} [dice1] GameState dice1
         * @property {number|undefined} [dice2] GameState dice2
         * @property {number|undefined} [wangpaiTilesLeft] GameState wangpaiTilesLeft
         */

        /**
         * Constructs a new GameState.
         * @memberof game
         * @classdesc Represents a GameState.
         * @implements IGameState
         * @constructor
         * @param {game.IGameState=} [properties] Properties to set
         */
        function GameState(properties) {
            this.players = [];
            this.wildTiles = [];
            this.playerReady = [];
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * GameState matchId.
         * @member {string} matchId
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.matchId = "";

        /**
         * GameState phase.
         * @member {game.GamePhase} phase
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.phase = 0;

        /**
         * GameState activePlayer.
         * @member {number} activePlayer
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.activePlayer = 0;

        /**
         * GameState players.
         * @member {Array.<game.PlayerState>} players
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.players = $util.emptyArray;

        /**
         * GameState wallCount.
         * @member {number} wallCount
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.wallCount = 0;

        /**
         * GameState handNum.
         * @member {number} handNum
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.handNum = 0;

        /**
         * GameState activeDiscard.
         * @member {game.Tile} activeDiscard
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.activeDiscard = null;

        /**
         * GameState wildTiles.
         * @member {Array.<game.Tile>} wildTiles
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.wildTiles = $util.emptyArray;

        /**
         * GameState prevailingWind.
         * @member {number} prevailingWind
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.prevailingWind = 0;

        /**
         * GameState wallSeed.
         * @member {string} wallSeed
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.wallSeed = "";

        /**
         * GameState roundResult.
         * @member {game.RoundResult} roundResult
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.roundResult = null;

        /**
         * GameState playerReady.
         * @member {Array.<boolean>} playerReady
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.playerReady = $util.emptyArray;

        /**
         * GameState diceSum.
         * @member {number} diceSum
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.diceSum = 0;

        /**
         * GameState wangpaiStacks.
         * @member {number} wangpaiStacks
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.wangpaiStacks = 0;

        /**
         * GameState isHaitei.
         * @member {boolean} isHaitei
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.isHaitei = false;

        /**
         * GameState dice1.
         * @member {number} dice1
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.dice1 = 0;

        /**
         * GameState dice2.
         * @member {number} dice2
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.dice2 = 0;

        /**
         * GameState wangpaiTilesLeft.
         * @member {number} wangpaiTilesLeft
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.wangpaiTilesLeft = 0;

        /**
         * Creates a new GameState instance using the specified properties.
         * @function create
         * @memberof game.GameState
         * @static
         * @param {game.IGameState=} [properties] Properties to set
         * @returns {game.GameState} GameState instance
         */
        GameState.create = function create(properties) {
            return new GameState(properties);
        };

        /**
         * Encodes the specified GameState message. Does not implicitly {@link game.GameState.verify|verify} messages.
         * @function encode
         * @memberof game.GameState
         * @static
         * @param {game.IGameState} message GameState message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        GameState.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.matchId != null && Object.hasOwnProperty.call(message, "matchId"))
                writer.uint32(/* id 1, wireType 2 =*/10).string(message.matchId);
            if (message.phase != null && Object.hasOwnProperty.call(message, "phase"))
                writer.uint32(/* id 2, wireType 0 =*/16).int32(message.phase);
            if (message.activePlayer != null && Object.hasOwnProperty.call(message, "activePlayer"))
                writer.uint32(/* id 3, wireType 0 =*/24).uint32(message.activePlayer);
            if (message.players != null && message.players.length)
                for (let i = 0; i < message.players.length; ++i)
                    $root.game.PlayerState.encode(message.players[i], writer.uint32(/* id 4, wireType 2 =*/34).fork()).ldelim();
            if (message.wallCount != null && Object.hasOwnProperty.call(message, "wallCount"))
                writer.uint32(/* id 5, wireType 0 =*/40).uint32(message.wallCount);
            if (message.handNum != null && Object.hasOwnProperty.call(message, "handNum"))
                writer.uint32(/* id 6, wireType 0 =*/48).uint32(message.handNum);
            if (message.activeDiscard != null && Object.hasOwnProperty.call(message, "activeDiscard"))
                $root.game.Tile.encode(message.activeDiscard, writer.uint32(/* id 7, wireType 2 =*/58).fork()).ldelim();
            if (message.wildTiles != null && message.wildTiles.length)
                for (let i = 0; i < message.wildTiles.length; ++i)
                    $root.game.Tile.encode(message.wildTiles[i], writer.uint32(/* id 8, wireType 2 =*/66).fork()).ldelim();
            if (message.prevailingWind != null && Object.hasOwnProperty.call(message, "prevailingWind"))
                writer.uint32(/* id 11, wireType 0 =*/88).uint32(message.prevailingWind);
            if (message.wallSeed != null && Object.hasOwnProperty.call(message, "wallSeed"))
                writer.uint32(/* id 12, wireType 2 =*/98).string(message.wallSeed);
            if (message.roundResult != null && Object.hasOwnProperty.call(message, "roundResult"))
                $root.game.RoundResult.encode(message.roundResult, writer.uint32(/* id 13, wireType 2 =*/106).fork()).ldelim();
            if (message.playerReady != null && message.playerReady.length) {
                writer.uint32(/* id 14, wireType 2 =*/114).fork();
                for (let i = 0; i < message.playerReady.length; ++i)
                    writer.bool(message.playerReady[i]);
                writer.ldelim();
            }
            if (message.diceSum != null && Object.hasOwnProperty.call(message, "diceSum"))
                writer.uint32(/* id 15, wireType 0 =*/120).uint32(message.diceSum);
            if (message.wangpaiStacks != null && Object.hasOwnProperty.call(message, "wangpaiStacks"))
                writer.uint32(/* id 16, wireType 0 =*/128).uint32(message.wangpaiStacks);
            if (message.isHaitei != null && Object.hasOwnProperty.call(message, "isHaitei"))
                writer.uint32(/* id 17, wireType 0 =*/136).bool(message.isHaitei);
            if (message.dice1 != null && Object.hasOwnProperty.call(message, "dice1"))
                writer.uint32(/* id 18, wireType 0 =*/144).uint32(message.dice1);
            if (message.dice2 != null && Object.hasOwnProperty.call(message, "dice2"))
                writer.uint32(/* id 19, wireType 0 =*/152).uint32(message.dice2);
            if (message.wangpaiTilesLeft != null && Object.hasOwnProperty.call(message, "wangpaiTilesLeft"))
                writer.uint32(/* id 20, wireType 0 =*/160).uint32(message.wangpaiTilesLeft);
            return writer;
        };

        /**
         * Encodes the specified GameState message, length delimited. Does not implicitly {@link game.GameState.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.GameState
         * @static
         * @param {game.IGameState} message GameState message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        GameState.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a GameState message from the specified reader or buffer.
         * @function decode
         * @memberof game.GameState
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.GameState} GameState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        GameState.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.GameState();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.matchId = reader.string();
                        break;
                    }
                case 2: {
                        message.phase = reader.int32();
                        break;
                    }
                case 3: {
                        message.activePlayer = reader.uint32();
                        break;
                    }
                case 4: {
                        if (!(message.players && message.players.length))
                            message.players = [];
                        message.players.push($root.game.PlayerState.decode(reader, reader.uint32()));
                        break;
                    }
                case 5: {
                        message.wallCount = reader.uint32();
                        break;
                    }
                case 6: {
                        message.handNum = reader.uint32();
                        break;
                    }
                case 7: {
                        message.activeDiscard = $root.game.Tile.decode(reader, reader.uint32());
                        break;
                    }
                case 8: {
                        if (!(message.wildTiles && message.wildTiles.length))
                            message.wildTiles = [];
                        message.wildTiles.push($root.game.Tile.decode(reader, reader.uint32()));
                        break;
                    }
                case 11: {
                        message.prevailingWind = reader.uint32();
                        break;
                    }
                case 12: {
                        message.wallSeed = reader.string();
                        break;
                    }
                case 13: {
                        message.roundResult = $root.game.RoundResult.decode(reader, reader.uint32());
                        break;
                    }
                case 14: {
                        if (!(message.playerReady && message.playerReady.length))
                            message.playerReady = [];
                        if ((tag & 7) === 2) {
                            let end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.playerReady.push(reader.bool());
                        } else
                            message.playerReady.push(reader.bool());
                        break;
                    }
                case 15: {
                        message.diceSum = reader.uint32();
                        break;
                    }
                case 16: {
                        message.wangpaiStacks = reader.uint32();
                        break;
                    }
                case 17: {
                        message.isHaitei = reader.bool();
                        break;
                    }
                case 18: {
                        message.dice1 = reader.uint32();
                        break;
                    }
                case 19: {
                        message.dice2 = reader.uint32();
                        break;
                    }
                case 20: {
                        message.wangpaiTilesLeft = reader.uint32();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a GameState message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.GameState
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.GameState} GameState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        GameState.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a GameState message.
         * @function verify
         * @memberof game.GameState
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        GameState.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.matchId != null && message.hasOwnProperty("matchId"))
                if (!$util.isString(message.matchId))
                    return "matchId: string expected";
            if (message.phase != null && message.hasOwnProperty("phase"))
                switch (message.phase) {
                default:
                    return "phase: enum value expected";
                case 0:
                case 1:
                case 2:
                case 3:
                case 4:
                    break;
                }
            if (message.activePlayer != null && message.hasOwnProperty("activePlayer"))
                if (!$util.isInteger(message.activePlayer))
                    return "activePlayer: integer expected";
            if (message.players != null && message.hasOwnProperty("players")) {
                if (!Array.isArray(message.players))
                    return "players: array expected";
                for (let i = 0; i < message.players.length; ++i) {
                    let error = $root.game.PlayerState.verify(message.players[i]);
                    if (error)
                        return "players." + error;
                }
            }
            if (message.wallCount != null && message.hasOwnProperty("wallCount"))
                if (!$util.isInteger(message.wallCount))
                    return "wallCount: integer expected";
            if (message.handNum != null && message.hasOwnProperty("handNum"))
                if (!$util.isInteger(message.handNum))
                    return "handNum: integer expected";
            if (message.activeDiscard != null && message.hasOwnProperty("activeDiscard")) {
                let error = $root.game.Tile.verify(message.activeDiscard);
                if (error)
                    return "activeDiscard." + error;
            }
            if (message.wildTiles != null && message.hasOwnProperty("wildTiles")) {
                if (!Array.isArray(message.wildTiles))
                    return "wildTiles: array expected";
                for (let i = 0; i < message.wildTiles.length; ++i) {
                    let error = $root.game.Tile.verify(message.wildTiles[i]);
                    if (error)
                        return "wildTiles." + error;
                }
            }
            if (message.prevailingWind != null && message.hasOwnProperty("prevailingWind"))
                if (!$util.isInteger(message.prevailingWind))
                    return "prevailingWind: integer expected";
            if (message.wallSeed != null && message.hasOwnProperty("wallSeed"))
                if (!$util.isString(message.wallSeed))
                    return "wallSeed: string expected";
            if (message.roundResult != null && message.hasOwnProperty("roundResult")) {
                let error = $root.game.RoundResult.verify(message.roundResult);
                if (error)
                    return "roundResult." + error;
            }
            if (message.playerReady != null && message.hasOwnProperty("playerReady")) {
                if (!Array.isArray(message.playerReady))
                    return "playerReady: array expected";
                for (let i = 0; i < message.playerReady.length; ++i)
                    if (typeof message.playerReady[i] !== "boolean")
                        return "playerReady: boolean[] expected";
            }
            if (message.diceSum != null && message.hasOwnProperty("diceSum"))
                if (!$util.isInteger(message.diceSum))
                    return "diceSum: integer expected";
            if (message.wangpaiStacks != null && message.hasOwnProperty("wangpaiStacks"))
                if (!$util.isInteger(message.wangpaiStacks))
                    return "wangpaiStacks: integer expected";
            if (message.isHaitei != null && message.hasOwnProperty("isHaitei"))
                if (typeof message.isHaitei !== "boolean")
                    return "isHaitei: boolean expected";
            if (message.dice1 != null && message.hasOwnProperty("dice1"))
                if (!$util.isInteger(message.dice1))
                    return "dice1: integer expected";
            if (message.dice2 != null && message.hasOwnProperty("dice2"))
                if (!$util.isInteger(message.dice2))
                    return "dice2: integer expected";
            if (message.wangpaiTilesLeft != null && message.hasOwnProperty("wangpaiTilesLeft"))
                if (!$util.isInteger(message.wangpaiTilesLeft))
                    return "wangpaiTilesLeft: integer expected";
            return null;
        };

        /**
         * Creates a GameState message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.GameState
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.GameState} GameState
         */
        GameState.fromObject = function fromObject(object) {
            if (object instanceof $root.game.GameState)
                return object;
            let message = new $root.game.GameState();
            if (object.matchId != null)
                message.matchId = String(object.matchId);
            switch (object.phase) {
            default:
                if (typeof object.phase === "number") {
                    message.phase = object.phase;
                    break;
                }
                break;
            case "PHASE_INIT":
            case 0:
                message.phase = 0;
                break;
            case "PHASE_DEAL":
            case 1:
                message.phase = 1;
                break;
            case "PHASE_PLAYER_TURN":
            case 2:
                message.phase = 2;
                break;
            case "PHASE_WAIT_DISCARDS":
            case 3:
                message.phase = 3;
                break;
            case "PHASE_ROUND_END":
            case 4:
                message.phase = 4;
                break;
            }
            if (object.activePlayer != null)
                message.activePlayer = object.activePlayer >>> 0;
            if (object.players) {
                if (!Array.isArray(object.players))
                    throw TypeError(".game.GameState.players: array expected");
                message.players = [];
                for (let i = 0; i < object.players.length; ++i) {
                    if (typeof object.players[i] !== "object")
                        throw TypeError(".game.GameState.players: object expected");
                    message.players[i] = $root.game.PlayerState.fromObject(object.players[i]);
                }
            }
            if (object.wallCount != null)
                message.wallCount = object.wallCount >>> 0;
            if (object.handNum != null)
                message.handNum = object.handNum >>> 0;
            if (object.activeDiscard != null) {
                if (typeof object.activeDiscard !== "object")
                    throw TypeError(".game.GameState.activeDiscard: object expected");
                message.activeDiscard = $root.game.Tile.fromObject(object.activeDiscard);
            }
            if (object.wildTiles) {
                if (!Array.isArray(object.wildTiles))
                    throw TypeError(".game.GameState.wildTiles: array expected");
                message.wildTiles = [];
                for (let i = 0; i < object.wildTiles.length; ++i) {
                    if (typeof object.wildTiles[i] !== "object")
                        throw TypeError(".game.GameState.wildTiles: object expected");
                    message.wildTiles[i] = $root.game.Tile.fromObject(object.wildTiles[i]);
                }
            }
            if (object.prevailingWind != null)
                message.prevailingWind = object.prevailingWind >>> 0;
            if (object.wallSeed != null)
                message.wallSeed = String(object.wallSeed);
            if (object.roundResult != null) {
                if (typeof object.roundResult !== "object")
                    throw TypeError(".game.GameState.roundResult: object expected");
                message.roundResult = $root.game.RoundResult.fromObject(object.roundResult);
            }
            if (object.playerReady) {
                if (!Array.isArray(object.playerReady))
                    throw TypeError(".game.GameState.playerReady: array expected");
                message.playerReady = [];
                for (let i = 0; i < object.playerReady.length; ++i)
                    message.playerReady[i] = Boolean(object.playerReady[i]);
            }
            if (object.diceSum != null)
                message.diceSum = object.diceSum >>> 0;
            if (object.wangpaiStacks != null)
                message.wangpaiStacks = object.wangpaiStacks >>> 0;
            if (object.isHaitei != null)
                message.isHaitei = Boolean(object.isHaitei);
            if (object.dice1 != null)
                message.dice1 = object.dice1 >>> 0;
            if (object.dice2 != null)
                message.dice2 = object.dice2 >>> 0;
            if (object.wangpaiTilesLeft != null)
                message.wangpaiTilesLeft = object.wangpaiTilesLeft >>> 0;
            return message;
        };

        /**
         * Creates a plain object from a GameState message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.GameState
         * @static
         * @param {game.GameState} message GameState
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        GameState.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.arrays || options.defaults) {
                object.players = [];
                object.wildTiles = [];
                object.playerReady = [];
            }
            if (options.defaults) {
                object.matchId = "";
                object.phase = options.enums === String ? "PHASE_INIT" : 0;
                object.activePlayer = 0;
                object.wallCount = 0;
                object.handNum = 0;
                object.activeDiscard = null;
                object.prevailingWind = 0;
                object.wallSeed = "";
                object.roundResult = null;
                object.diceSum = 0;
                object.wangpaiStacks = 0;
                object.isHaitei = false;
                object.dice1 = 0;
                object.dice2 = 0;
                object.wangpaiTilesLeft = 0;
            }
            if (message.matchId != null && message.hasOwnProperty("matchId"))
                object.matchId = message.matchId;
            if (message.phase != null && message.hasOwnProperty("phase"))
                object.phase = options.enums === String ? $root.game.GamePhase[message.phase] === undefined ? message.phase : $root.game.GamePhase[message.phase] : message.phase;
            if (message.activePlayer != null && message.hasOwnProperty("activePlayer"))
                object.activePlayer = message.activePlayer;
            if (message.players && message.players.length) {
                object.players = [];
                for (let j = 0; j < message.players.length; ++j)
                    object.players[j] = $root.game.PlayerState.toObject(message.players[j], options);
            }
            if (message.wallCount != null && message.hasOwnProperty("wallCount"))
                object.wallCount = message.wallCount;
            if (message.handNum != null && message.hasOwnProperty("handNum"))
                object.handNum = message.handNum;
            if (message.activeDiscard != null && message.hasOwnProperty("activeDiscard"))
                object.activeDiscard = $root.game.Tile.toObject(message.activeDiscard, options);
            if (message.wildTiles && message.wildTiles.length) {
                object.wildTiles = [];
                for (let j = 0; j < message.wildTiles.length; ++j)
                    object.wildTiles[j] = $root.game.Tile.toObject(message.wildTiles[j], options);
            }
            if (message.prevailingWind != null && message.hasOwnProperty("prevailingWind"))
                object.prevailingWind = message.prevailingWind;
            if (message.wallSeed != null && message.hasOwnProperty("wallSeed"))
                object.wallSeed = message.wallSeed;
            if (message.roundResult != null && message.hasOwnProperty("roundResult"))
                object.roundResult = $root.game.RoundResult.toObject(message.roundResult, options);
            if (message.playerReady && message.playerReady.length) {
                object.playerReady = [];
                for (let j = 0; j < message.playerReady.length; ++j)
                    object.playerReady[j] = message.playerReady[j];
            }
            if (message.diceSum != null && message.hasOwnProperty("diceSum"))
                object.diceSum = message.diceSum;
            if (message.wangpaiStacks != null && message.hasOwnProperty("wangpaiStacks"))
                object.wangpaiStacks = message.wangpaiStacks;
            if (message.isHaitei != null && message.hasOwnProperty("isHaitei"))
                object.isHaitei = message.isHaitei;
            if (message.dice1 != null && message.hasOwnProperty("dice1"))
                object.dice1 = message.dice1;
            if (message.dice2 != null && message.hasOwnProperty("dice2"))
                object.dice2 = message.dice2;
            if (message.wangpaiTilesLeft != null && message.hasOwnProperty("wangpaiTilesLeft"))
                object.wangpaiTilesLeft = message.wangpaiTilesLeft;
            return object;
        };

        /**
         * Converts this GameState to JSON.
         * @function toJSON
         * @memberof game.GameState
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        GameState.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for GameState
         * @function getTypeUrl
         * @memberof game.GameState
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        GameState.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.GameState";
        };

        return GameState;
    })();

    game.ScoreEntry = (function() {

        /**
         * Properties of a ScoreEntry.
         * @memberof game
         * @interface IScoreEntry
         * @property {string|undefined} [patternName] ScoreEntry patternName
         * @property {number|undefined} [points] ScoreEntry points
         */

        /**
         * Constructs a new ScoreEntry.
         * @memberof game
         * @classdesc Represents a ScoreEntry.
         * @implements IScoreEntry
         * @constructor
         * @param {game.IScoreEntry=} [properties] Properties to set
         */
        function ScoreEntry(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * ScoreEntry patternName.
         * @member {string} patternName
         * @memberof game.ScoreEntry
         * @instance
         */
        ScoreEntry.prototype.patternName = "";

        /**
         * ScoreEntry points.
         * @member {number} points
         * @memberof game.ScoreEntry
         * @instance
         */
        ScoreEntry.prototype.points = 0;

        /**
         * Creates a new ScoreEntry instance using the specified properties.
         * @function create
         * @memberof game.ScoreEntry
         * @static
         * @param {game.IScoreEntry=} [properties] Properties to set
         * @returns {game.ScoreEntry} ScoreEntry instance
         */
        ScoreEntry.create = function create(properties) {
            return new ScoreEntry(properties);
        };

        /**
         * Encodes the specified ScoreEntry message. Does not implicitly {@link game.ScoreEntry.verify|verify} messages.
         * @function encode
         * @memberof game.ScoreEntry
         * @static
         * @param {game.IScoreEntry} message ScoreEntry message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        ScoreEntry.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.patternName != null && Object.hasOwnProperty.call(message, "patternName"))
                writer.uint32(/* id 1, wireType 2 =*/10).string(message.patternName);
            if (message.points != null && Object.hasOwnProperty.call(message, "points"))
                writer.uint32(/* id 2, wireType 0 =*/16).int32(message.points);
            return writer;
        };

        /**
         * Encodes the specified ScoreEntry message, length delimited. Does not implicitly {@link game.ScoreEntry.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.ScoreEntry
         * @static
         * @param {game.IScoreEntry} message ScoreEntry message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        ScoreEntry.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a ScoreEntry message from the specified reader or buffer.
         * @function decode
         * @memberof game.ScoreEntry
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.ScoreEntry} ScoreEntry
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        ScoreEntry.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.ScoreEntry();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.patternName = reader.string();
                        break;
                    }
                case 2: {
                        message.points = reader.int32();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a ScoreEntry message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.ScoreEntry
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.ScoreEntry} ScoreEntry
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        ScoreEntry.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a ScoreEntry message.
         * @function verify
         * @memberof game.ScoreEntry
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        ScoreEntry.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.patternName != null && message.hasOwnProperty("patternName"))
                if (!$util.isString(message.patternName))
                    return "patternName: string expected";
            if (message.points != null && message.hasOwnProperty("points"))
                if (!$util.isInteger(message.points))
                    return "points: integer expected";
            return null;
        };

        /**
         * Creates a ScoreEntry message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.ScoreEntry
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.ScoreEntry} ScoreEntry
         */
        ScoreEntry.fromObject = function fromObject(object) {
            if (object instanceof $root.game.ScoreEntry)
                return object;
            let message = new $root.game.ScoreEntry();
            if (object.patternName != null)
                message.patternName = String(object.patternName);
            if (object.points != null)
                message.points = object.points | 0;
            return message;
        };

        /**
         * Creates a plain object from a ScoreEntry message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.ScoreEntry
         * @static
         * @param {game.ScoreEntry} message ScoreEntry
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        ScoreEntry.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults) {
                object.patternName = "";
                object.points = 0;
            }
            if (message.patternName != null && message.hasOwnProperty("patternName"))
                object.patternName = message.patternName;
            if (message.points != null && message.hasOwnProperty("points"))
                object.points = message.points;
            return object;
        };

        /**
         * Converts this ScoreEntry to JSON.
         * @function toJSON
         * @memberof game.ScoreEntry
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        ScoreEntry.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for ScoreEntry
         * @function getTypeUrl
         * @memberof game.ScoreEntry
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        ScoreEntry.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.ScoreEntry";
        };

        return ScoreEntry;
    })();

    game.PlayerPayout = (function() {

        /**
         * Properties of a PlayerPayout.
         * @memberof game
         * @interface IPlayerPayout
         * @property {number|undefined} [seat] PlayerPayout seat
         * @property {number|undefined} [amount] PlayerPayout amount
         */

        /**
         * Constructs a new PlayerPayout.
         * @memberof game
         * @classdesc Represents a PlayerPayout.
         * @implements IPlayerPayout
         * @constructor
         * @param {game.IPlayerPayout=} [properties] Properties to set
         */
        function PlayerPayout(properties) {
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * PlayerPayout seat.
         * @member {number} seat
         * @memberof game.PlayerPayout
         * @instance
         */
        PlayerPayout.prototype.seat = 0;

        /**
         * PlayerPayout amount.
         * @member {number} amount
         * @memberof game.PlayerPayout
         * @instance
         */
        PlayerPayout.prototype.amount = 0;

        /**
         * Creates a new PlayerPayout instance using the specified properties.
         * @function create
         * @memberof game.PlayerPayout
         * @static
         * @param {game.IPlayerPayout=} [properties] Properties to set
         * @returns {game.PlayerPayout} PlayerPayout instance
         */
        PlayerPayout.create = function create(properties) {
            return new PlayerPayout(properties);
        };

        /**
         * Encodes the specified PlayerPayout message. Does not implicitly {@link game.PlayerPayout.verify|verify} messages.
         * @function encode
         * @memberof game.PlayerPayout
         * @static
         * @param {game.IPlayerPayout} message PlayerPayout message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PlayerPayout.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.seat != null && Object.hasOwnProperty.call(message, "seat"))
                writer.uint32(/* id 1, wireType 0 =*/8).uint32(message.seat);
            if (message.amount != null && Object.hasOwnProperty.call(message, "amount"))
                writer.uint32(/* id 2, wireType 0 =*/16).int32(message.amount);
            return writer;
        };

        /**
         * Encodes the specified PlayerPayout message, length delimited. Does not implicitly {@link game.PlayerPayout.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.PlayerPayout
         * @static
         * @param {game.IPlayerPayout} message PlayerPayout message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PlayerPayout.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a PlayerPayout message from the specified reader or buffer.
         * @function decode
         * @memberof game.PlayerPayout
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.PlayerPayout} PlayerPayout
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PlayerPayout.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.PlayerPayout();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.seat = reader.uint32();
                        break;
                    }
                case 2: {
                        message.amount = reader.int32();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a PlayerPayout message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.PlayerPayout
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.PlayerPayout} PlayerPayout
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PlayerPayout.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a PlayerPayout message.
         * @function verify
         * @memberof game.PlayerPayout
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        PlayerPayout.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.seat != null && message.hasOwnProperty("seat"))
                if (!$util.isInteger(message.seat))
                    return "seat: integer expected";
            if (message.amount != null && message.hasOwnProperty("amount"))
                if (!$util.isInteger(message.amount))
                    return "amount: integer expected";
            return null;
        };

        /**
         * Creates a PlayerPayout message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.PlayerPayout
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.PlayerPayout} PlayerPayout
         */
        PlayerPayout.fromObject = function fromObject(object) {
            if (object instanceof $root.game.PlayerPayout)
                return object;
            let message = new $root.game.PlayerPayout();
            if (object.seat != null)
                message.seat = object.seat >>> 0;
            if (object.amount != null)
                message.amount = object.amount | 0;
            return message;
        };

        /**
         * Creates a plain object from a PlayerPayout message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.PlayerPayout
         * @static
         * @param {game.PlayerPayout} message PlayerPayout
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        PlayerPayout.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.defaults) {
                object.seat = 0;
                object.amount = 0;
            }
            if (message.seat != null && message.hasOwnProperty("seat"))
                object.seat = message.seat;
            if (message.amount != null && message.hasOwnProperty("amount"))
                object.amount = message.amount;
            return object;
        };

        /**
         * Converts this PlayerPayout to JSON.
         * @function toJSON
         * @memberof game.PlayerPayout
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        PlayerPayout.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for PlayerPayout
         * @function getTypeUrl
         * @memberof game.PlayerPayout
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        PlayerPayout.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.PlayerPayout";
        };

        return PlayerPayout;
    })();

    game.RoundResult = (function() {

        /**
         * Properties of a RoundResult.
         * @memberof game
         * @interface IRoundResult
         * @property {number|undefined} [winnerSeat] RoundResult winnerSeat
         * @property {game.ActionType|undefined} [winType] RoundResult winType
         * @property {number|undefined} [discarderSeat] RoundResult discarderSeat
         * @property {Array.<game.ITile>|undefined} [winningHand] RoundResult winningHand
         * @property {Array.<game.IMeld>|undefined} [winningMelds] RoundResult winningMelds
         * @property {game.ITile|undefined} [winTile] RoundResult winTile
         * @property {Array.<game.IScoreEntry>|undefined} [breakdown] RoundResult breakdown
         * @property {number|undefined} [totalScore] RoundResult totalScore
         * @property {Array.<game.IPlayerPayout>|undefined} [payouts] RoundResult payouts
         * @property {boolean|undefined} [isDraw] RoundResult isDraw
         */

        /**
         * Constructs a new RoundResult.
         * @memberof game
         * @classdesc Represents a RoundResult.
         * @implements IRoundResult
         * @constructor
         * @param {game.IRoundResult=} [properties] Properties to set
         */
        function RoundResult(properties) {
            this.winningHand = [];
            this.winningMelds = [];
            this.breakdown = [];
            this.payouts = [];
            if (properties)
                for (let keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * RoundResult winnerSeat.
         * @member {number} winnerSeat
         * @memberof game.RoundResult
         * @instance
         */
        RoundResult.prototype.winnerSeat = 0;

        /**
         * RoundResult winType.
         * @member {game.ActionType} winType
         * @memberof game.RoundResult
         * @instance
         */
        RoundResult.prototype.winType = 0;

        /**
         * RoundResult discarderSeat.
         * @member {number} discarderSeat
         * @memberof game.RoundResult
         * @instance
         */
        RoundResult.prototype.discarderSeat = 0;

        /**
         * RoundResult winningHand.
         * @member {Array.<game.Tile>} winningHand
         * @memberof game.RoundResult
         * @instance
         */
        RoundResult.prototype.winningHand = $util.emptyArray;

        /**
         * RoundResult winningMelds.
         * @member {Array.<game.Meld>} winningMelds
         * @memberof game.RoundResult
         * @instance
         */
        RoundResult.prototype.winningMelds = $util.emptyArray;

        /**
         * RoundResult winTile.
         * @member {game.Tile} winTile
         * @memberof game.RoundResult
         * @instance
         */
        RoundResult.prototype.winTile = null;

        /**
         * RoundResult breakdown.
         * @member {Array.<game.ScoreEntry>} breakdown
         * @memberof game.RoundResult
         * @instance
         */
        RoundResult.prototype.breakdown = $util.emptyArray;

        /**
         * RoundResult totalScore.
         * @member {number} totalScore
         * @memberof game.RoundResult
         * @instance
         */
        RoundResult.prototype.totalScore = 0;

        /**
         * RoundResult payouts.
         * @member {Array.<game.PlayerPayout>} payouts
         * @memberof game.RoundResult
         * @instance
         */
        RoundResult.prototype.payouts = $util.emptyArray;

        /**
         * RoundResult isDraw.
         * @member {boolean} isDraw
         * @memberof game.RoundResult
         * @instance
         */
        RoundResult.prototype.isDraw = false;

        /**
         * Creates a new RoundResult instance using the specified properties.
         * @function create
         * @memberof game.RoundResult
         * @static
         * @param {game.IRoundResult=} [properties] Properties to set
         * @returns {game.RoundResult} RoundResult instance
         */
        RoundResult.create = function create(properties) {
            return new RoundResult(properties);
        };

        /**
         * Encodes the specified RoundResult message. Does not implicitly {@link game.RoundResult.verify|verify} messages.
         * @function encode
         * @memberof game.RoundResult
         * @static
         * @param {game.IRoundResult} message RoundResult message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        RoundResult.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.winnerSeat != null && Object.hasOwnProperty.call(message, "winnerSeat"))
                writer.uint32(/* id 1, wireType 0 =*/8).uint32(message.winnerSeat);
            if (message.winType != null && Object.hasOwnProperty.call(message, "winType"))
                writer.uint32(/* id 2, wireType 0 =*/16).int32(message.winType);
            if (message.discarderSeat != null && Object.hasOwnProperty.call(message, "discarderSeat"))
                writer.uint32(/* id 3, wireType 0 =*/24).uint32(message.discarderSeat);
            if (message.winningHand != null && message.winningHand.length)
                for (let i = 0; i < message.winningHand.length; ++i)
                    $root.game.Tile.encode(message.winningHand[i], writer.uint32(/* id 4, wireType 2 =*/34).fork()).ldelim();
            if (message.winningMelds != null && message.winningMelds.length)
                for (let i = 0; i < message.winningMelds.length; ++i)
                    $root.game.Meld.encode(message.winningMelds[i], writer.uint32(/* id 5, wireType 2 =*/42).fork()).ldelim();
            if (message.winTile != null && Object.hasOwnProperty.call(message, "winTile"))
                $root.game.Tile.encode(message.winTile, writer.uint32(/* id 6, wireType 2 =*/50).fork()).ldelim();
            if (message.breakdown != null && message.breakdown.length)
                for (let i = 0; i < message.breakdown.length; ++i)
                    $root.game.ScoreEntry.encode(message.breakdown[i], writer.uint32(/* id 7, wireType 2 =*/58).fork()).ldelim();
            if (message.totalScore != null && Object.hasOwnProperty.call(message, "totalScore"))
                writer.uint32(/* id 8, wireType 0 =*/64).int32(message.totalScore);
            if (message.payouts != null && message.payouts.length)
                for (let i = 0; i < message.payouts.length; ++i)
                    $root.game.PlayerPayout.encode(message.payouts[i], writer.uint32(/* id 9, wireType 2 =*/74).fork()).ldelim();
            if (message.isDraw != null && Object.hasOwnProperty.call(message, "isDraw"))
                writer.uint32(/* id 10, wireType 0 =*/80).bool(message.isDraw);
            return writer;
        };

        /**
         * Encodes the specified RoundResult message, length delimited. Does not implicitly {@link game.RoundResult.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.RoundResult
         * @static
         * @param {game.IRoundResult} message RoundResult message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        RoundResult.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a RoundResult message from the specified reader or buffer.
         * @function decode
         * @memberof game.RoundResult
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.RoundResult} RoundResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        RoundResult.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            let end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.RoundResult();
            while (reader.pos < end) {
                let tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.winnerSeat = reader.uint32();
                        break;
                    }
                case 2: {
                        message.winType = reader.int32();
                        break;
                    }
                case 3: {
                        message.discarderSeat = reader.uint32();
                        break;
                    }
                case 4: {
                        if (!(message.winningHand && message.winningHand.length))
                            message.winningHand = [];
                        message.winningHand.push($root.game.Tile.decode(reader, reader.uint32()));
                        break;
                    }
                case 5: {
                        if (!(message.winningMelds && message.winningMelds.length))
                            message.winningMelds = [];
                        message.winningMelds.push($root.game.Meld.decode(reader, reader.uint32()));
                        break;
                    }
                case 6: {
                        message.winTile = $root.game.Tile.decode(reader, reader.uint32());
                        break;
                    }
                case 7: {
                        if (!(message.breakdown && message.breakdown.length))
                            message.breakdown = [];
                        message.breakdown.push($root.game.ScoreEntry.decode(reader, reader.uint32()));
                        break;
                    }
                case 8: {
                        message.totalScore = reader.int32();
                        break;
                    }
                case 9: {
                        if (!(message.payouts && message.payouts.length))
                            message.payouts = [];
                        message.payouts.push($root.game.PlayerPayout.decode(reader, reader.uint32()));
                        break;
                    }
                case 10: {
                        message.isDraw = reader.bool();
                        break;
                    }
                default:
                    reader.skipType(tag & 7);
                    break;
                }
            }
            return message;
        };

        /**
         * Decodes a RoundResult message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.RoundResult
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.RoundResult} RoundResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        RoundResult.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a RoundResult message.
         * @function verify
         * @memberof game.RoundResult
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        RoundResult.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.winnerSeat != null && message.hasOwnProperty("winnerSeat"))
                if (!$util.isInteger(message.winnerSeat))
                    return "winnerSeat: integer expected";
            if (message.winType != null && message.hasOwnProperty("winType"))
                switch (message.winType) {
                default:
                    return "winType: enum value expected";
                case 0:
                case 1:
                case 2:
                case 3:
                case 4:
                case 5:
                case 6:
                case 7:
                case 8:
                case 9:
                case 10:
                case 11:
                case 12:
                    break;
                }
            if (message.discarderSeat != null && message.hasOwnProperty("discarderSeat"))
                if (!$util.isInteger(message.discarderSeat))
                    return "discarderSeat: integer expected";
            if (message.winningHand != null && message.hasOwnProperty("winningHand")) {
                if (!Array.isArray(message.winningHand))
                    return "winningHand: array expected";
                for (let i = 0; i < message.winningHand.length; ++i) {
                    let error = $root.game.Tile.verify(message.winningHand[i]);
                    if (error)
                        return "winningHand." + error;
                }
            }
            if (message.winningMelds != null && message.hasOwnProperty("winningMelds")) {
                if (!Array.isArray(message.winningMelds))
                    return "winningMelds: array expected";
                for (let i = 0; i < message.winningMelds.length; ++i) {
                    let error = $root.game.Meld.verify(message.winningMelds[i]);
                    if (error)
                        return "winningMelds." + error;
                }
            }
            if (message.winTile != null && message.hasOwnProperty("winTile")) {
                let error = $root.game.Tile.verify(message.winTile);
                if (error)
                    return "winTile." + error;
            }
            if (message.breakdown != null && message.hasOwnProperty("breakdown")) {
                if (!Array.isArray(message.breakdown))
                    return "breakdown: array expected";
                for (let i = 0; i < message.breakdown.length; ++i) {
                    let error = $root.game.ScoreEntry.verify(message.breakdown[i]);
                    if (error)
                        return "breakdown." + error;
                }
            }
            if (message.totalScore != null && message.hasOwnProperty("totalScore"))
                if (!$util.isInteger(message.totalScore))
                    return "totalScore: integer expected";
            if (message.payouts != null && message.hasOwnProperty("payouts")) {
                if (!Array.isArray(message.payouts))
                    return "payouts: array expected";
                for (let i = 0; i < message.payouts.length; ++i) {
                    let error = $root.game.PlayerPayout.verify(message.payouts[i]);
                    if (error)
                        return "payouts." + error;
                }
            }
            if (message.isDraw != null && message.hasOwnProperty("isDraw"))
                if (typeof message.isDraw !== "boolean")
                    return "isDraw: boolean expected";
            return null;
        };

        /**
         * Creates a RoundResult message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.RoundResult
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.RoundResult} RoundResult
         */
        RoundResult.fromObject = function fromObject(object) {
            if (object instanceof $root.game.RoundResult)
                return object;
            let message = new $root.game.RoundResult();
            if (object.winnerSeat != null)
                message.winnerSeat = object.winnerSeat >>> 0;
            switch (object.winType) {
            default:
                if (typeof object.winType === "number") {
                    message.winType = object.winType;
                    break;
                }
                break;
            case "ACTION_UNKNOWN":
            case 0:
                message.winType = 0;
                break;
            case "ACTION_DRAW":
            case 1:
                message.winType = 1;
                break;
            case "ACTION_DISCARD":
            case 2:
                message.winType = 2;
                break;
            case "ACTION_CHII":
            case 3:
                message.winType = 3;
                break;
            case "ACTION_PON":
            case 4:
                message.winType = 4;
                break;
            case "ACTION_KAN":
            case 5:
                message.winType = 5;
                break;
            case "ACTION_TSUMO":
            case 6:
                message.winType = 6;
                break;
            case "ACTION_RON":
            case 7:
                message.winType = 7;
                break;
            case "ACTION_PASS":
            case 8:
                message.winType = 8;
                break;
            case "ACTION_FLOWER_REVEAL":
            case 9:
                message.winType = 9;
                break;
            case "ACTION_READY":
            case 10:
                message.winType = 10;
                break;
            case "ACTION_ACCEPT_HAITEI":
            case 11:
                message.winType = 11;
                break;
            case "ACTION_REFUSE_HAITEI":
            case 12:
                message.winType = 12;
                break;
            }
            if (object.discarderSeat != null)
                message.discarderSeat = object.discarderSeat >>> 0;
            if (object.winningHand) {
                if (!Array.isArray(object.winningHand))
                    throw TypeError(".game.RoundResult.winningHand: array expected");
                message.winningHand = [];
                for (let i = 0; i < object.winningHand.length; ++i) {
                    if (typeof object.winningHand[i] !== "object")
                        throw TypeError(".game.RoundResult.winningHand: object expected");
                    message.winningHand[i] = $root.game.Tile.fromObject(object.winningHand[i]);
                }
            }
            if (object.winningMelds) {
                if (!Array.isArray(object.winningMelds))
                    throw TypeError(".game.RoundResult.winningMelds: array expected");
                message.winningMelds = [];
                for (let i = 0; i < object.winningMelds.length; ++i) {
                    if (typeof object.winningMelds[i] !== "object")
                        throw TypeError(".game.RoundResult.winningMelds: object expected");
                    message.winningMelds[i] = $root.game.Meld.fromObject(object.winningMelds[i]);
                }
            }
            if (object.winTile != null) {
                if (typeof object.winTile !== "object")
                    throw TypeError(".game.RoundResult.winTile: object expected");
                message.winTile = $root.game.Tile.fromObject(object.winTile);
            }
            if (object.breakdown) {
                if (!Array.isArray(object.breakdown))
                    throw TypeError(".game.RoundResult.breakdown: array expected");
                message.breakdown = [];
                for (let i = 0; i < object.breakdown.length; ++i) {
                    if (typeof object.breakdown[i] !== "object")
                        throw TypeError(".game.RoundResult.breakdown: object expected");
                    message.breakdown[i] = $root.game.ScoreEntry.fromObject(object.breakdown[i]);
                }
            }
            if (object.totalScore != null)
                message.totalScore = object.totalScore | 0;
            if (object.payouts) {
                if (!Array.isArray(object.payouts))
                    throw TypeError(".game.RoundResult.payouts: array expected");
                message.payouts = [];
                for (let i = 0; i < object.payouts.length; ++i) {
                    if (typeof object.payouts[i] !== "object")
                        throw TypeError(".game.RoundResult.payouts: object expected");
                    message.payouts[i] = $root.game.PlayerPayout.fromObject(object.payouts[i]);
                }
            }
            if (object.isDraw != null)
                message.isDraw = Boolean(object.isDraw);
            return message;
        };

        /**
         * Creates a plain object from a RoundResult message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.RoundResult
         * @static
         * @param {game.RoundResult} message RoundResult
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        RoundResult.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            let object = {};
            if (options.arrays || options.defaults) {
                object.winningHand = [];
                object.winningMelds = [];
                object.breakdown = [];
                object.payouts = [];
            }
            if (options.defaults) {
                object.winnerSeat = 0;
                object.winType = options.enums === String ? "ACTION_UNKNOWN" : 0;
                object.discarderSeat = 0;
                object.winTile = null;
                object.totalScore = 0;
                object.isDraw = false;
            }
            if (message.winnerSeat != null && message.hasOwnProperty("winnerSeat"))
                object.winnerSeat = message.winnerSeat;
            if (message.winType != null && message.hasOwnProperty("winType"))
                object.winType = options.enums === String ? $root.game.ActionType[message.winType] === undefined ? message.winType : $root.game.ActionType[message.winType] : message.winType;
            if (message.discarderSeat != null && message.hasOwnProperty("discarderSeat"))
                object.discarderSeat = message.discarderSeat;
            if (message.winningHand && message.winningHand.length) {
                object.winningHand = [];
                for (let j = 0; j < message.winningHand.length; ++j)
                    object.winningHand[j] = $root.game.Tile.toObject(message.winningHand[j], options);
            }
            if (message.winningMelds && message.winningMelds.length) {
                object.winningMelds = [];
                for (let j = 0; j < message.winningMelds.length; ++j)
                    object.winningMelds[j] = $root.game.Meld.toObject(message.winningMelds[j], options);
            }
            if (message.winTile != null && message.hasOwnProperty("winTile"))
                object.winTile = $root.game.Tile.toObject(message.winTile, options);
            if (message.breakdown && message.breakdown.length) {
                object.breakdown = [];
                for (let j = 0; j < message.breakdown.length; ++j)
                    object.breakdown[j] = $root.game.ScoreEntry.toObject(message.breakdown[j], options);
            }
            if (message.totalScore != null && message.hasOwnProperty("totalScore"))
                object.totalScore = message.totalScore;
            if (message.payouts && message.payouts.length) {
                object.payouts = [];
                for (let j = 0; j < message.payouts.length; ++j)
                    object.payouts[j] = $root.game.PlayerPayout.toObject(message.payouts[j], options);
            }
            if (message.isDraw != null && message.hasOwnProperty("isDraw"))
                object.isDraw = message.isDraw;
            return object;
        };

        /**
         * Converts this RoundResult to JSON.
         * @function toJSON
         * @memberof game.RoundResult
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        RoundResult.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for RoundResult
         * @function getTypeUrl
         * @memberof game.RoundResult
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        RoundResult.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.RoundResult";
        };

        return RoundResult;
    })();

    return game;
})();

export { $root as default };
