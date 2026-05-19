/*eslint-disable block-scoped-var, id-length, no-control-regex, no-magic-numbers, no-prototype-builtins, no-redeclare, no-shadow, no-var, sort-vars*/
"use strict";

var $protobuf = require("protobufjs/minimal");

// Common aliases
var $Reader = $protobuf.Reader, $Writer = $protobuf.Writer, $util = $protobuf.util;

// Exported root namespace
var $root = $protobuf.roots["default"] || ($protobuf.roots["default"] = {});

$root.game = (function() {

    /**
     * Namespace game.
     * @exports game
     * @namespace
     */
    var game = {};

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
        var valuesById = {}, values = Object.create(valuesById);
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
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
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
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.Tile();
            while (reader.pos < end) {
                var tag = reader.uint32();
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
            var message = new $root.game.Tile();
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
            var object = {};
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
        var valuesById = {}, values = Object.create(valuesById);
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
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
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
                for (var i = 0; i < message.meldTiles.length; ++i)
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
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.PlayerAction();
            while (reader.pos < end) {
                var tag = reader.uint32();
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
                var error = $root.game.Tile.verify(message.tile);
                if (error)
                    return "tile." + error;
            }
            if (message.meldTiles != null && message.hasOwnProperty("meldTiles")) {
                if (!Array.isArray(message.meldTiles))
                    return "meldTiles: array expected";
                for (var i = 0; i < message.meldTiles.length; ++i) {
                    var error = $root.game.Tile.verify(message.meldTiles[i]);
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
            var message = new $root.game.PlayerAction();
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
                for (var i = 0; i < object.meldTiles.length; ++i) {
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
            var object = {};
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
                for (var j = 0; j < message.meldTiles.length; ++j)
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
        var valuesById = {}, values = Object.create(valuesById);
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
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
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
                for (var i = 0; i < message.tiles.length; ++i)
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
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.Meld();
            while (reader.pos < end) {
                var tag = reader.uint32();
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
                for (var i = 0; i < message.tiles.length; ++i) {
                    var error = $root.game.Tile.verify(message.tiles[i]);
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
            var message = new $root.game.Meld();
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
                for (var i = 0; i < object.tiles.length; ++i) {
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
            var object = {};
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
                for (var j = 0; j < message.tiles.length; ++j)
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
         * @property {number|undefined} [shanten] PlayerState shanten
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
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
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

        /**
         * PlayerState shanten.
         * @member {number} shanten
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.shanten = 0;

        // OneOf field names bound to virtual getters and setters
        var $oneOfFields;

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
                for (var i = 0; i < message.closedHand.length; ++i)
                    $root.game.Tile.encode(message.closedHand[i], writer.uint32(/* id 3, wireType 2 =*/26).fork()).ldelim();
            if (message.handSize != null && Object.hasOwnProperty.call(message, "handSize"))
                writer.uint32(/* id 4, wireType 0 =*/32).uint32(message.handSize);
            if (message.openMelds != null && message.openMelds.length)
                for (var i = 0; i < message.openMelds.length; ++i)
                    $root.game.Meld.encode(message.openMelds[i], writer.uint32(/* id 5, wireType 2 =*/42).fork()).ldelim();
            if (message.discards != null && message.discards.length)
                for (var i = 0; i < message.discards.length; ++i)
                    $root.game.Tile.encode(message.discards[i], writer.uint32(/* id 6, wireType 2 =*/50).fork()).ldelim();
            if (message.seatWind != null && Object.hasOwnProperty.call(message, "seatWind"))
                writer.uint32(/* id 7, wireType 0 =*/56).uint32(message.seatWind);
            if (message.flowerMelds != null && message.flowerMelds.length)
                for (var i = 0; i < message.flowerMelds.length; ++i)
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
                for (var i = 0; i < message.validActions.length; ++i)
                    $root.game.PlayerAction.encode(message.validActions[i], writer.uint32(/* id 16, wireType 2 =*/130).fork()).ldelim();
            if (message.drawnTileId != null && Object.hasOwnProperty.call(message, "drawnTileId"))
                writer.uint32(/* id 17, wireType 0 =*/136).int32(message.drawnTileId);
            if (message.shanten != null && Object.hasOwnProperty.call(message, "shanten"))
                writer.uint32(/* id 18, wireType 0 =*/144).int32(message.shanten);
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
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.PlayerState();
            while (reader.pos < end) {
                var tag = reader.uint32();
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
                case 18: {
                        message.shanten = reader.int32();
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
            var properties = {};
            if (message.seat != null && message.hasOwnProperty("seat"))
                if (!$util.isInteger(message.seat))
                    return "seat: integer expected";
            if (message.score != null && message.hasOwnProperty("score"))
                if (!$util.isInteger(message.score))
                    return "score: integer expected";
            if (message.closedHand != null && message.hasOwnProperty("closedHand")) {
                if (!Array.isArray(message.closedHand))
                    return "closedHand: array expected";
                for (var i = 0; i < message.closedHand.length; ++i) {
                    var error = $root.game.Tile.verify(message.closedHand[i]);
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
                for (var i = 0; i < message.openMelds.length; ++i) {
                    var error = $root.game.Meld.verify(message.openMelds[i]);
                    if (error)
                        return "openMelds." + error;
                }
            }
            if (message.discards != null && message.hasOwnProperty("discards")) {
                if (!Array.isArray(message.discards))
                    return "discards: array expected";
                for (var i = 0; i < message.discards.length; ++i) {
                    var error = $root.game.Tile.verify(message.discards[i]);
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
                for (var i = 0; i < message.flowerMelds.length; ++i) {
                    var error = $root.game.Tile.verify(message.flowerMelds[i]);
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
                for (var i = 0; i < message.validActions.length; ++i) {
                    var error = $root.game.PlayerAction.verify(message.validActions[i]);
                    if (error)
                        return "validActions." + error;
                }
            }
            if (message.drawnTileId != null && message.hasOwnProperty("drawnTileId")) {
                properties._drawnTileId = 1;
                if (!$util.isInteger(message.drawnTileId))
                    return "drawnTileId: integer expected";
            }
            if (message.shanten != null && message.hasOwnProperty("shanten"))
                if (!$util.isInteger(message.shanten))
                    return "shanten: integer expected";
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
            var message = new $root.game.PlayerState();
            if (object.seat != null)
                message.seat = object.seat >>> 0;
            if (object.score != null)
                message.score = object.score | 0;
            if (object.closedHand) {
                if (!Array.isArray(object.closedHand))
                    throw TypeError(".game.PlayerState.closedHand: array expected");
                message.closedHand = [];
                for (var i = 0; i < object.closedHand.length; ++i) {
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
                for (var i = 0; i < object.openMelds.length; ++i) {
                    if (typeof object.openMelds[i] !== "object")
                        throw TypeError(".game.PlayerState.openMelds: object expected");
                    message.openMelds[i] = $root.game.Meld.fromObject(object.openMelds[i]);
                }
            }
            if (object.discards) {
                if (!Array.isArray(object.discards))
                    throw TypeError(".game.PlayerState.discards: array expected");
                message.discards = [];
                for (var i = 0; i < object.discards.length; ++i) {
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
                for (var i = 0; i < object.flowerMelds.length; ++i) {
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
                for (var i = 0; i < object.validActions.length; ++i) {
                    if (typeof object.validActions[i] !== "object")
                        throw TypeError(".game.PlayerState.validActions: object expected");
                    message.validActions[i] = $root.game.PlayerAction.fromObject(object.validActions[i]);
                }
            }
            if (object.drawnTileId != null)
                message.drawnTileId = object.drawnTileId | 0;
            if (object.shanten != null)
                message.shanten = object.shanten | 0;
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
            var object = {};
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
                object.shanten = 0;
            }
            if (message.seat != null && message.hasOwnProperty("seat"))
                object.seat = message.seat;
            if (message.score != null && message.hasOwnProperty("score"))
                object.score = message.score;
            if (message.closedHand && message.closedHand.length) {
                object.closedHand = [];
                for (var j = 0; j < message.closedHand.length; ++j)
                    object.closedHand[j] = $root.game.Tile.toObject(message.closedHand[j], options);
            }
            if (message.handSize != null && message.hasOwnProperty("handSize"))
                object.handSize = message.handSize;
            if (message.openMelds && message.openMelds.length) {
                object.openMelds = [];
                for (var j = 0; j < message.openMelds.length; ++j)
                    object.openMelds[j] = $root.game.Meld.toObject(message.openMelds[j], options);
            }
            if (message.discards && message.discards.length) {
                object.discards = [];
                for (var j = 0; j < message.discards.length; ++j)
                    object.discards[j] = $root.game.Tile.toObject(message.discards[j], options);
            }
            if (message.seatWind != null && message.hasOwnProperty("seatWind"))
                object.seatWind = message.seatWind;
            if (message.flowerMelds && message.flowerMelds.length) {
                object.flowerMelds = [];
                for (var j = 0; j < message.flowerMelds.length; ++j)
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
                for (var j = 0; j < message.validActions.length; ++j)
                    object.validActions[j] = $root.game.PlayerAction.toObject(message.validActions[j], options);
            }
            if (message.drawnTileId != null && message.hasOwnProperty("drawnTileId")) {
                object.drawnTileId = message.drawnTileId;
                if (options.oneofs)
                    object._drawnTileId = "drawnTileId";
            }
            if (message.shanten != null && message.hasOwnProperty("shanten"))
                object.shanten = message.shanten;
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
     * @property {number} PHASE_MATCH_END=5 PHASE_MATCH_END value
     */
    game.GamePhase = (function() {
        var valuesById = {}, values = Object.create(valuesById);
        values[valuesById[0] = "PHASE_INIT"] = 0;
        values[valuesById[1] = "PHASE_DEAL"] = 1;
        values[valuesById[2] = "PHASE_PLAYER_TURN"] = 2;
        values[valuesById[3] = "PHASE_WAIT_DISCARDS"] = 3;
        values[valuesById[4] = "PHASE_ROUND_END"] = 4;
        values[valuesById[5] = "PHASE_MATCH_END"] = 5;
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
         * @property {game.MatchMode|undefined} [matchMode] GameState matchMode
         * @property {game.IChongciConfig|undefined} [chongciConfig] GameState chongciConfig
         * @property {game.IMatchEndResult|undefined} [matchEndResult] GameState matchEndResult
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
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
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
         * GameState matchMode.
         * @member {game.MatchMode} matchMode
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.matchMode = 0;

        /**
         * GameState chongciConfig.
         * @member {game.ChongciConfig} chongciConfig
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.chongciConfig = null;

        /**
         * GameState matchEndResult.
         * @member {game.MatchEndResult} matchEndResult
         * @memberof game.GameState
         * @instance
         */
        GameState.prototype.matchEndResult = null;

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
                for (var i = 0; i < message.players.length; ++i)
                    $root.game.PlayerState.encode(message.players[i], writer.uint32(/* id 4, wireType 2 =*/34).fork()).ldelim();
            if (message.wallCount != null && Object.hasOwnProperty.call(message, "wallCount"))
                writer.uint32(/* id 5, wireType 0 =*/40).uint32(message.wallCount);
            if (message.handNum != null && Object.hasOwnProperty.call(message, "handNum"))
                writer.uint32(/* id 6, wireType 0 =*/48).uint32(message.handNum);
            if (message.activeDiscard != null && Object.hasOwnProperty.call(message, "activeDiscard"))
                $root.game.Tile.encode(message.activeDiscard, writer.uint32(/* id 7, wireType 2 =*/58).fork()).ldelim();
            if (message.wildTiles != null && message.wildTiles.length)
                for (var i = 0; i < message.wildTiles.length; ++i)
                    $root.game.Tile.encode(message.wildTiles[i], writer.uint32(/* id 8, wireType 2 =*/66).fork()).ldelim();
            if (message.prevailingWind != null && Object.hasOwnProperty.call(message, "prevailingWind"))
                writer.uint32(/* id 11, wireType 0 =*/88).uint32(message.prevailingWind);
            if (message.wallSeed != null && Object.hasOwnProperty.call(message, "wallSeed"))
                writer.uint32(/* id 12, wireType 2 =*/98).string(message.wallSeed);
            if (message.roundResult != null && Object.hasOwnProperty.call(message, "roundResult"))
                $root.game.RoundResult.encode(message.roundResult, writer.uint32(/* id 13, wireType 2 =*/106).fork()).ldelim();
            if (message.playerReady != null && message.playerReady.length) {
                writer.uint32(/* id 14, wireType 2 =*/114).fork();
                for (var i = 0; i < message.playerReady.length; ++i)
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
            if (message.matchMode != null && Object.hasOwnProperty.call(message, "matchMode"))
                writer.uint32(/* id 21, wireType 0 =*/168).int32(message.matchMode);
            if (message.chongciConfig != null && Object.hasOwnProperty.call(message, "chongciConfig"))
                $root.game.ChongciConfig.encode(message.chongciConfig, writer.uint32(/* id 22, wireType 2 =*/178).fork()).ldelim();
            if (message.matchEndResult != null && Object.hasOwnProperty.call(message, "matchEndResult"))
                $root.game.MatchEndResult.encode(message.matchEndResult, writer.uint32(/* id 23, wireType 2 =*/186).fork()).ldelim();
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
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.GameState();
            while (reader.pos < end) {
                var tag = reader.uint32();
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
                            var end2 = reader.uint32() + reader.pos;
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
                case 21: {
                        message.matchMode = reader.int32();
                        break;
                    }
                case 22: {
                        message.chongciConfig = $root.game.ChongciConfig.decode(reader, reader.uint32());
                        break;
                    }
                case 23: {
                        message.matchEndResult = $root.game.MatchEndResult.decode(reader, reader.uint32());
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
                case 5:
                    break;
                }
            if (message.activePlayer != null && message.hasOwnProperty("activePlayer"))
                if (!$util.isInteger(message.activePlayer))
                    return "activePlayer: integer expected";
            if (message.players != null && message.hasOwnProperty("players")) {
                if (!Array.isArray(message.players))
                    return "players: array expected";
                for (var i = 0; i < message.players.length; ++i) {
                    var error = $root.game.PlayerState.verify(message.players[i]);
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
                var error = $root.game.Tile.verify(message.activeDiscard);
                if (error)
                    return "activeDiscard." + error;
            }
            if (message.wildTiles != null && message.hasOwnProperty("wildTiles")) {
                if (!Array.isArray(message.wildTiles))
                    return "wildTiles: array expected";
                for (var i = 0; i < message.wildTiles.length; ++i) {
                    var error = $root.game.Tile.verify(message.wildTiles[i]);
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
                var error = $root.game.RoundResult.verify(message.roundResult);
                if (error)
                    return "roundResult." + error;
            }
            if (message.playerReady != null && message.hasOwnProperty("playerReady")) {
                if (!Array.isArray(message.playerReady))
                    return "playerReady: array expected";
                for (var i = 0; i < message.playerReady.length; ++i)
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
            if (message.matchMode != null && message.hasOwnProperty("matchMode"))
                switch (message.matchMode) {
                default:
                    return "matchMode: enum value expected";
                case 0:
                case 1:
                case 2:
                    break;
                }
            if (message.chongciConfig != null && message.hasOwnProperty("chongciConfig")) {
                var error = $root.game.ChongciConfig.verify(message.chongciConfig);
                if (error)
                    return "chongciConfig." + error;
            }
            if (message.matchEndResult != null && message.hasOwnProperty("matchEndResult")) {
                var error = $root.game.MatchEndResult.verify(message.matchEndResult);
                if (error)
                    return "matchEndResult." + error;
            }
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
            var message = new $root.game.GameState();
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
            case "PHASE_MATCH_END":
            case 5:
                message.phase = 5;
                break;
            }
            if (object.activePlayer != null)
                message.activePlayer = object.activePlayer >>> 0;
            if (object.players) {
                if (!Array.isArray(object.players))
                    throw TypeError(".game.GameState.players: array expected");
                message.players = [];
                for (var i = 0; i < object.players.length; ++i) {
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
                for (var i = 0; i < object.wildTiles.length; ++i) {
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
                for (var i = 0; i < object.playerReady.length; ++i)
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
            switch (object.matchMode) {
            default:
                if (typeof object.matchMode === "number") {
                    message.matchMode = object.matchMode;
                    break;
                }
                break;
            case "MATCH_MODE_UNSPECIFIED":
            case 0:
                message.matchMode = 0;
                break;
            case "MATCH_MODE_CLASSIC":
            case 1:
                message.matchMode = 1;
                break;
            case "MATCH_MODE_CHONGCI":
            case 2:
                message.matchMode = 2;
                break;
            }
            if (object.chongciConfig != null) {
                if (typeof object.chongciConfig !== "object")
                    throw TypeError(".game.GameState.chongciConfig: object expected");
                message.chongciConfig = $root.game.ChongciConfig.fromObject(object.chongciConfig);
            }
            if (object.matchEndResult != null) {
                if (typeof object.matchEndResult !== "object")
                    throw TypeError(".game.GameState.matchEndResult: object expected");
                message.matchEndResult = $root.game.MatchEndResult.fromObject(object.matchEndResult);
            }
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
            var object = {};
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
                object.matchMode = options.enums === String ? "MATCH_MODE_UNSPECIFIED" : 0;
                object.chongciConfig = null;
                object.matchEndResult = null;
            }
            if (message.matchId != null && message.hasOwnProperty("matchId"))
                object.matchId = message.matchId;
            if (message.phase != null && message.hasOwnProperty("phase"))
                object.phase = options.enums === String ? $root.game.GamePhase[message.phase] === undefined ? message.phase : $root.game.GamePhase[message.phase] : message.phase;
            if (message.activePlayer != null && message.hasOwnProperty("activePlayer"))
                object.activePlayer = message.activePlayer;
            if (message.players && message.players.length) {
                object.players = [];
                for (var j = 0; j < message.players.length; ++j)
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
                for (var j = 0; j < message.wildTiles.length; ++j)
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
                for (var j = 0; j < message.playerReady.length; ++j)
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
            if (message.matchMode != null && message.hasOwnProperty("matchMode"))
                object.matchMode = options.enums === String ? $root.game.MatchMode[message.matchMode] === undefined ? message.matchMode : $root.game.MatchMode[message.matchMode] : message.matchMode;
            if (message.chongciConfig != null && message.hasOwnProperty("chongciConfig"))
                object.chongciConfig = $root.game.ChongciConfig.toObject(message.chongciConfig, options);
            if (message.matchEndResult != null && message.hasOwnProperty("matchEndResult"))
                object.matchEndResult = $root.game.MatchEndResult.toObject(message.matchEndResult, options);
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
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
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
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.ScoreEntry();
            while (reader.pos < end) {
                var tag = reader.uint32();
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
            var message = new $root.game.ScoreEntry();
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
            var object = {};
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
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
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
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.PlayerPayout();
            while (reader.pos < end) {
                var tag = reader.uint32();
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
            var message = new $root.game.PlayerPayout();
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
            var object = {};
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
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
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
                for (var i = 0; i < message.winningHand.length; ++i)
                    $root.game.Tile.encode(message.winningHand[i], writer.uint32(/* id 4, wireType 2 =*/34).fork()).ldelim();
            if (message.winningMelds != null && message.winningMelds.length)
                for (var i = 0; i < message.winningMelds.length; ++i)
                    $root.game.Meld.encode(message.winningMelds[i], writer.uint32(/* id 5, wireType 2 =*/42).fork()).ldelim();
            if (message.winTile != null && Object.hasOwnProperty.call(message, "winTile"))
                $root.game.Tile.encode(message.winTile, writer.uint32(/* id 6, wireType 2 =*/50).fork()).ldelim();
            if (message.breakdown != null && message.breakdown.length)
                for (var i = 0; i < message.breakdown.length; ++i)
                    $root.game.ScoreEntry.encode(message.breakdown[i], writer.uint32(/* id 7, wireType 2 =*/58).fork()).ldelim();
            if (message.totalScore != null && Object.hasOwnProperty.call(message, "totalScore"))
                writer.uint32(/* id 8, wireType 0 =*/64).int32(message.totalScore);
            if (message.payouts != null && message.payouts.length)
                for (var i = 0; i < message.payouts.length; ++i)
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
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.RoundResult();
            while (reader.pos < end) {
                var tag = reader.uint32();
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
                for (var i = 0; i < message.winningHand.length; ++i) {
                    var error = $root.game.Tile.verify(message.winningHand[i]);
                    if (error)
                        return "winningHand." + error;
                }
            }
            if (message.winningMelds != null && message.hasOwnProperty("winningMelds")) {
                if (!Array.isArray(message.winningMelds))
                    return "winningMelds: array expected";
                for (var i = 0; i < message.winningMelds.length; ++i) {
                    var error = $root.game.Meld.verify(message.winningMelds[i]);
                    if (error)
                        return "winningMelds." + error;
                }
            }
            if (message.winTile != null && message.hasOwnProperty("winTile")) {
                var error = $root.game.Tile.verify(message.winTile);
                if (error)
                    return "winTile." + error;
            }
            if (message.breakdown != null && message.hasOwnProperty("breakdown")) {
                if (!Array.isArray(message.breakdown))
                    return "breakdown: array expected";
                for (var i = 0; i < message.breakdown.length; ++i) {
                    var error = $root.game.ScoreEntry.verify(message.breakdown[i]);
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
                for (var i = 0; i < message.payouts.length; ++i) {
                    var error = $root.game.PlayerPayout.verify(message.payouts[i]);
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
            var message = new $root.game.RoundResult();
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
                for (var i = 0; i < object.winningHand.length; ++i) {
                    if (typeof object.winningHand[i] !== "object")
                        throw TypeError(".game.RoundResult.winningHand: object expected");
                    message.winningHand[i] = $root.game.Tile.fromObject(object.winningHand[i]);
                }
            }
            if (object.winningMelds) {
                if (!Array.isArray(object.winningMelds))
                    throw TypeError(".game.RoundResult.winningMelds: array expected");
                message.winningMelds = [];
                for (var i = 0; i < object.winningMelds.length; ++i) {
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
                for (var i = 0; i < object.breakdown.length; ++i) {
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
                for (var i = 0; i < object.payouts.length; ++i) {
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
            var object = {};
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
                for (var j = 0; j < message.winningHand.length; ++j)
                    object.winningHand[j] = $root.game.Tile.toObject(message.winningHand[j], options);
            }
            if (message.winningMelds && message.winningMelds.length) {
                object.winningMelds = [];
                for (var j = 0; j < message.winningMelds.length; ++j)
                    object.winningMelds[j] = $root.game.Meld.toObject(message.winningMelds[j], options);
            }
            if (message.winTile != null && message.hasOwnProperty("winTile"))
                object.winTile = $root.game.Tile.toObject(message.winTile, options);
            if (message.breakdown && message.breakdown.length) {
                object.breakdown = [];
                for (var j = 0; j < message.breakdown.length; ++j)
                    object.breakdown[j] = $root.game.ScoreEntry.toObject(message.breakdown[j], options);
            }
            if (message.totalScore != null && message.hasOwnProperty("totalScore"))
                object.totalScore = message.totalScore;
            if (message.payouts && message.payouts.length) {
                object.payouts = [];
                for (var j = 0; j < message.payouts.length; ++j)
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

    game.RoundOutcome = (function() {

        /**
         * Properties of a RoundOutcome.
         * @memberof game
         * @interface IRoundOutcome
         * @property {boolean|undefined} [isDraw] RoundOutcome isDraw
         * @property {number|undefined} [winnerSeat] RoundOutcome winnerSeat
         * @property {game.ActionType|undefined} [winType] RoundOutcome winType
         * @property {number|undefined} [discarderSeat] RoundOutcome discarderSeat
         * @property {number|undefined} [totalScore] RoundOutcome totalScore
         * @property {Array.<game.IPlayerPayout>|undefined} [payouts] RoundOutcome payouts
         */

        /**
         * Constructs a new RoundOutcome.
         * @memberof game
         * @classdesc Represents a RoundOutcome.
         * @implements IRoundOutcome
         * @constructor
         * @param {game.IRoundOutcome=} [properties] Properties to set
         */
        function RoundOutcome(properties) {
            this.payouts = [];
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * RoundOutcome isDraw.
         * @member {boolean} isDraw
         * @memberof game.RoundOutcome
         * @instance
         */
        RoundOutcome.prototype.isDraw = false;

        /**
         * RoundOutcome winnerSeat.
         * @member {number} winnerSeat
         * @memberof game.RoundOutcome
         * @instance
         */
        RoundOutcome.prototype.winnerSeat = 0;

        /**
         * RoundOutcome winType.
         * @member {game.ActionType} winType
         * @memberof game.RoundOutcome
         * @instance
         */
        RoundOutcome.prototype.winType = 0;

        /**
         * RoundOutcome discarderSeat.
         * @member {number} discarderSeat
         * @memberof game.RoundOutcome
         * @instance
         */
        RoundOutcome.prototype.discarderSeat = 0;

        /**
         * RoundOutcome totalScore.
         * @member {number} totalScore
         * @memberof game.RoundOutcome
         * @instance
         */
        RoundOutcome.prototype.totalScore = 0;

        /**
         * RoundOutcome payouts.
         * @member {Array.<game.PlayerPayout>} payouts
         * @memberof game.RoundOutcome
         * @instance
         */
        RoundOutcome.prototype.payouts = $util.emptyArray;

        /**
         * Creates a new RoundOutcome instance using the specified properties.
         * @function create
         * @memberof game.RoundOutcome
         * @static
         * @param {game.IRoundOutcome=} [properties] Properties to set
         * @returns {game.RoundOutcome} RoundOutcome instance
         */
        RoundOutcome.create = function create(properties) {
            return new RoundOutcome(properties);
        };

        /**
         * Encodes the specified RoundOutcome message. Does not implicitly {@link game.RoundOutcome.verify|verify} messages.
         * @function encode
         * @memberof game.RoundOutcome
         * @static
         * @param {game.IRoundOutcome} message RoundOutcome message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        RoundOutcome.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.isDraw != null && Object.hasOwnProperty.call(message, "isDraw"))
                writer.uint32(/* id 1, wireType 0 =*/8).bool(message.isDraw);
            if (message.winnerSeat != null && Object.hasOwnProperty.call(message, "winnerSeat"))
                writer.uint32(/* id 2, wireType 0 =*/16).uint32(message.winnerSeat);
            if (message.winType != null && Object.hasOwnProperty.call(message, "winType"))
                writer.uint32(/* id 3, wireType 0 =*/24).int32(message.winType);
            if (message.discarderSeat != null && Object.hasOwnProperty.call(message, "discarderSeat"))
                writer.uint32(/* id 4, wireType 0 =*/32).uint32(message.discarderSeat);
            if (message.totalScore != null && Object.hasOwnProperty.call(message, "totalScore"))
                writer.uint32(/* id 5, wireType 0 =*/40).int32(message.totalScore);
            if (message.payouts != null && message.payouts.length)
                for (var i = 0; i < message.payouts.length; ++i)
                    $root.game.PlayerPayout.encode(message.payouts[i], writer.uint32(/* id 6, wireType 2 =*/50).fork()).ldelim();
            return writer;
        };

        /**
         * Encodes the specified RoundOutcome message, length delimited. Does not implicitly {@link game.RoundOutcome.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.RoundOutcome
         * @static
         * @param {game.IRoundOutcome} message RoundOutcome message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        RoundOutcome.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a RoundOutcome message from the specified reader or buffer.
         * @function decode
         * @memberof game.RoundOutcome
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.RoundOutcome} RoundOutcome
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        RoundOutcome.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.RoundOutcome();
            while (reader.pos < end) {
                var tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.isDraw = reader.bool();
                        break;
                    }
                case 2: {
                        message.winnerSeat = reader.uint32();
                        break;
                    }
                case 3: {
                        message.winType = reader.int32();
                        break;
                    }
                case 4: {
                        message.discarderSeat = reader.uint32();
                        break;
                    }
                case 5: {
                        message.totalScore = reader.int32();
                        break;
                    }
                case 6: {
                        if (!(message.payouts && message.payouts.length))
                            message.payouts = [];
                        message.payouts.push($root.game.PlayerPayout.decode(reader, reader.uint32()));
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
         * Decodes a RoundOutcome message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.RoundOutcome
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.RoundOutcome} RoundOutcome
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        RoundOutcome.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a RoundOutcome message.
         * @function verify
         * @memberof game.RoundOutcome
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        RoundOutcome.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.isDraw != null && message.hasOwnProperty("isDraw"))
                if (typeof message.isDraw !== "boolean")
                    return "isDraw: boolean expected";
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
            if (message.totalScore != null && message.hasOwnProperty("totalScore"))
                if (!$util.isInteger(message.totalScore))
                    return "totalScore: integer expected";
            if (message.payouts != null && message.hasOwnProperty("payouts")) {
                if (!Array.isArray(message.payouts))
                    return "payouts: array expected";
                for (var i = 0; i < message.payouts.length; ++i) {
                    var error = $root.game.PlayerPayout.verify(message.payouts[i]);
                    if (error)
                        return "payouts." + error;
                }
            }
            return null;
        };

        /**
         * Creates a RoundOutcome message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.RoundOutcome
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.RoundOutcome} RoundOutcome
         */
        RoundOutcome.fromObject = function fromObject(object) {
            if (object instanceof $root.game.RoundOutcome)
                return object;
            var message = new $root.game.RoundOutcome();
            if (object.isDraw != null)
                message.isDraw = Boolean(object.isDraw);
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
            if (object.totalScore != null)
                message.totalScore = object.totalScore | 0;
            if (object.payouts) {
                if (!Array.isArray(object.payouts))
                    throw TypeError(".game.RoundOutcome.payouts: array expected");
                message.payouts = [];
                for (var i = 0; i < object.payouts.length; ++i) {
                    if (typeof object.payouts[i] !== "object")
                        throw TypeError(".game.RoundOutcome.payouts: object expected");
                    message.payouts[i] = $root.game.PlayerPayout.fromObject(object.payouts[i]);
                }
            }
            return message;
        };

        /**
         * Creates a plain object from a RoundOutcome message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.RoundOutcome
         * @static
         * @param {game.RoundOutcome} message RoundOutcome
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        RoundOutcome.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.arrays || options.defaults)
                object.payouts = [];
            if (options.defaults) {
                object.isDraw = false;
                object.winnerSeat = 0;
                object.winType = options.enums === String ? "ACTION_UNKNOWN" : 0;
                object.discarderSeat = 0;
                object.totalScore = 0;
            }
            if (message.isDraw != null && message.hasOwnProperty("isDraw"))
                object.isDraw = message.isDraw;
            if (message.winnerSeat != null && message.hasOwnProperty("winnerSeat"))
                object.winnerSeat = message.winnerSeat;
            if (message.winType != null && message.hasOwnProperty("winType"))
                object.winType = options.enums === String ? $root.game.ActionType[message.winType] === undefined ? message.winType : $root.game.ActionType[message.winType] : message.winType;
            if (message.discarderSeat != null && message.hasOwnProperty("discarderSeat"))
                object.discarderSeat = message.discarderSeat;
            if (message.totalScore != null && message.hasOwnProperty("totalScore"))
                object.totalScore = message.totalScore;
            if (message.payouts && message.payouts.length) {
                object.payouts = [];
                for (var j = 0; j < message.payouts.length; ++j)
                    object.payouts[j] = $root.game.PlayerPayout.toObject(message.payouts[j], options);
            }
            return object;
        };

        /**
         * Converts this RoundOutcome to JSON.
         * @function toJSON
         * @memberof game.RoundOutcome
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        RoundOutcome.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for RoundOutcome
         * @function getTypeUrl
         * @memberof game.RoundOutcome
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        RoundOutcome.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.RoundOutcome";
        };

        return RoundOutcome;
    })();

    game.EnvConfig = (function() {

        /**
         * Properties of an EnvConfig.
         * @memberof game
         * @interface IEnvConfig
         * @property {Array.<number>|undefined} [learningSeats] EnvConfig learningSeats
         * @property {boolean|undefined} [autoPlayHeuristics] EnvConfig autoPlayHeuristics
         * @property {number|undefined} [maxDecisions] EnvConfig maxDecisions
         */

        /**
         * Constructs a new EnvConfig.
         * @memberof game
         * @classdesc Represents an EnvConfig.
         * @implements IEnvConfig
         * @constructor
         * @param {game.IEnvConfig=} [properties] Properties to set
         */
        function EnvConfig(properties) {
            this.learningSeats = [];
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * EnvConfig learningSeats.
         * @member {Array.<number>} learningSeats
         * @memberof game.EnvConfig
         * @instance
         */
        EnvConfig.prototype.learningSeats = $util.emptyArray;

        /**
         * EnvConfig autoPlayHeuristics.
         * @member {boolean} autoPlayHeuristics
         * @memberof game.EnvConfig
         * @instance
         */
        EnvConfig.prototype.autoPlayHeuristics = false;

        /**
         * EnvConfig maxDecisions.
         * @member {number} maxDecisions
         * @memberof game.EnvConfig
         * @instance
         */
        EnvConfig.prototype.maxDecisions = 0;

        /**
         * Creates a new EnvConfig instance using the specified properties.
         * @function create
         * @memberof game.EnvConfig
         * @static
         * @param {game.IEnvConfig=} [properties] Properties to set
         * @returns {game.EnvConfig} EnvConfig instance
         */
        EnvConfig.create = function create(properties) {
            return new EnvConfig(properties);
        };

        /**
         * Encodes the specified EnvConfig message. Does not implicitly {@link game.EnvConfig.verify|verify} messages.
         * @function encode
         * @memberof game.EnvConfig
         * @static
         * @param {game.IEnvConfig} message EnvConfig message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvConfig.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.learningSeats != null && message.learningSeats.length) {
                writer.uint32(/* id 1, wireType 2 =*/10).fork();
                for (var i = 0; i < message.learningSeats.length; ++i)
                    writer.uint32(message.learningSeats[i]);
                writer.ldelim();
            }
            if (message.autoPlayHeuristics != null && Object.hasOwnProperty.call(message, "autoPlayHeuristics"))
                writer.uint32(/* id 2, wireType 0 =*/16).bool(message.autoPlayHeuristics);
            if (message.maxDecisions != null && Object.hasOwnProperty.call(message, "maxDecisions"))
                writer.uint32(/* id 3, wireType 0 =*/24).uint32(message.maxDecisions);
            return writer;
        };

        /**
         * Encodes the specified EnvConfig message, length delimited. Does not implicitly {@link game.EnvConfig.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.EnvConfig
         * @static
         * @param {game.IEnvConfig} message EnvConfig message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvConfig.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes an EnvConfig message from the specified reader or buffer.
         * @function decode
         * @memberof game.EnvConfig
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.EnvConfig} EnvConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvConfig.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.EnvConfig();
            while (reader.pos < end) {
                var tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        if (!(message.learningSeats && message.learningSeats.length))
                            message.learningSeats = [];
                        if ((tag & 7) === 2) {
                            var end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.learningSeats.push(reader.uint32());
                        } else
                            message.learningSeats.push(reader.uint32());
                        break;
                    }
                case 2: {
                        message.autoPlayHeuristics = reader.bool();
                        break;
                    }
                case 3: {
                        message.maxDecisions = reader.uint32();
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
         * Decodes an EnvConfig message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.EnvConfig
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.EnvConfig} EnvConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvConfig.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies an EnvConfig message.
         * @function verify
         * @memberof game.EnvConfig
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        EnvConfig.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.learningSeats != null && message.hasOwnProperty("learningSeats")) {
                if (!Array.isArray(message.learningSeats))
                    return "learningSeats: array expected";
                for (var i = 0; i < message.learningSeats.length; ++i)
                    if (!$util.isInteger(message.learningSeats[i]))
                        return "learningSeats: integer[] expected";
            }
            if (message.autoPlayHeuristics != null && message.hasOwnProperty("autoPlayHeuristics"))
                if (typeof message.autoPlayHeuristics !== "boolean")
                    return "autoPlayHeuristics: boolean expected";
            if (message.maxDecisions != null && message.hasOwnProperty("maxDecisions"))
                if (!$util.isInteger(message.maxDecisions))
                    return "maxDecisions: integer expected";
            return null;
        };

        /**
         * Creates an EnvConfig message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.EnvConfig
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.EnvConfig} EnvConfig
         */
        EnvConfig.fromObject = function fromObject(object) {
            if (object instanceof $root.game.EnvConfig)
                return object;
            var message = new $root.game.EnvConfig();
            if (object.learningSeats) {
                if (!Array.isArray(object.learningSeats))
                    throw TypeError(".game.EnvConfig.learningSeats: array expected");
                message.learningSeats = [];
                for (var i = 0; i < object.learningSeats.length; ++i)
                    message.learningSeats[i] = object.learningSeats[i] >>> 0;
            }
            if (object.autoPlayHeuristics != null)
                message.autoPlayHeuristics = Boolean(object.autoPlayHeuristics);
            if (object.maxDecisions != null)
                message.maxDecisions = object.maxDecisions >>> 0;
            return message;
        };

        /**
         * Creates a plain object from an EnvConfig message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.EnvConfig
         * @static
         * @param {game.EnvConfig} message EnvConfig
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        EnvConfig.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.arrays || options.defaults)
                object.learningSeats = [];
            if (options.defaults) {
                object.autoPlayHeuristics = false;
                object.maxDecisions = 0;
            }
            if (message.learningSeats && message.learningSeats.length) {
                object.learningSeats = [];
                for (var j = 0; j < message.learningSeats.length; ++j)
                    object.learningSeats[j] = message.learningSeats[j];
            }
            if (message.autoPlayHeuristics != null && message.hasOwnProperty("autoPlayHeuristics"))
                object.autoPlayHeuristics = message.autoPlayHeuristics;
            if (message.maxDecisions != null && message.hasOwnProperty("maxDecisions"))
                object.maxDecisions = message.maxDecisions;
            return object;
        };

        /**
         * Converts this EnvConfig to JSON.
         * @function toJSON
         * @memberof game.EnvConfig
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        EnvConfig.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for EnvConfig
         * @function getTypeUrl
         * @memberof game.EnvConfig
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        EnvConfig.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.EnvConfig";
        };

        return EnvConfig;
    })();

    game.SeatObservation = (function() {

        /**
         * Properties of a SeatObservation.
         * @memberof game
         * @interface ISeatObservation
         * @property {number|undefined} [seat] SeatObservation seat
         * @property {Array.<number>|undefined} [planes] SeatObservation planes
         * @property {number|undefined} [planeChannels] SeatObservation planeChannels
         * @property {number|undefined} [planeHeight] SeatObservation planeHeight
         * @property {number|undefined} [planeWidth] SeatObservation planeWidth
         * @property {Array.<number>|undefined} [scalars] SeatObservation scalars
         * @property {Uint8Array|undefined} [actionMask] SeatObservation actionMask
         * @property {number|undefined} [actionSpaceSize] SeatObservation actionSpaceSize
         * @property {number|Long|undefined} [decisionIndex] SeatObservation decisionIndex
         * @property {game.GamePhase|undefined} [phase] SeatObservation phase
         * @property {number|undefined} [activePlayer] SeatObservation activePlayer
         */

        /**
         * Constructs a new SeatObservation.
         * @memberof game
         * @classdesc Represents a SeatObservation.
         * @implements ISeatObservation
         * @constructor
         * @param {game.ISeatObservation=} [properties] Properties to set
         */
        function SeatObservation(properties) {
            this.planes = [];
            this.scalars = [];
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * SeatObservation seat.
         * @member {number} seat
         * @memberof game.SeatObservation
         * @instance
         */
        SeatObservation.prototype.seat = 0;

        /**
         * SeatObservation planes.
         * @member {Array.<number>} planes
         * @memberof game.SeatObservation
         * @instance
         */
        SeatObservation.prototype.planes = $util.emptyArray;

        /**
         * SeatObservation planeChannels.
         * @member {number} planeChannels
         * @memberof game.SeatObservation
         * @instance
         */
        SeatObservation.prototype.planeChannels = 0;

        /**
         * SeatObservation planeHeight.
         * @member {number} planeHeight
         * @memberof game.SeatObservation
         * @instance
         */
        SeatObservation.prototype.planeHeight = 0;

        /**
         * SeatObservation planeWidth.
         * @member {number} planeWidth
         * @memberof game.SeatObservation
         * @instance
         */
        SeatObservation.prototype.planeWidth = 0;

        /**
         * SeatObservation scalars.
         * @member {Array.<number>} scalars
         * @memberof game.SeatObservation
         * @instance
         */
        SeatObservation.prototype.scalars = $util.emptyArray;

        /**
         * SeatObservation actionMask.
         * @member {Uint8Array} actionMask
         * @memberof game.SeatObservation
         * @instance
         */
        SeatObservation.prototype.actionMask = $util.newBuffer([]);

        /**
         * SeatObservation actionSpaceSize.
         * @member {number} actionSpaceSize
         * @memberof game.SeatObservation
         * @instance
         */
        SeatObservation.prototype.actionSpaceSize = 0;

        /**
         * SeatObservation decisionIndex.
         * @member {number|Long} decisionIndex
         * @memberof game.SeatObservation
         * @instance
         */
        SeatObservation.prototype.decisionIndex = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * SeatObservation phase.
         * @member {game.GamePhase} phase
         * @memberof game.SeatObservation
         * @instance
         */
        SeatObservation.prototype.phase = 0;

        /**
         * SeatObservation activePlayer.
         * @member {number} activePlayer
         * @memberof game.SeatObservation
         * @instance
         */
        SeatObservation.prototype.activePlayer = 0;

        /**
         * Creates a new SeatObservation instance using the specified properties.
         * @function create
         * @memberof game.SeatObservation
         * @static
         * @param {game.ISeatObservation=} [properties] Properties to set
         * @returns {game.SeatObservation} SeatObservation instance
         */
        SeatObservation.create = function create(properties) {
            return new SeatObservation(properties);
        };

        /**
         * Encodes the specified SeatObservation message. Does not implicitly {@link game.SeatObservation.verify|verify} messages.
         * @function encode
         * @memberof game.SeatObservation
         * @static
         * @param {game.ISeatObservation} message SeatObservation message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        SeatObservation.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.seat != null && Object.hasOwnProperty.call(message, "seat"))
                writer.uint32(/* id 1, wireType 0 =*/8).uint32(message.seat);
            if (message.planes != null && message.planes.length) {
                writer.uint32(/* id 2, wireType 2 =*/18).fork();
                for (var i = 0; i < message.planes.length; ++i)
                    writer.float(message.planes[i]);
                writer.ldelim();
            }
            if (message.planeChannels != null && Object.hasOwnProperty.call(message, "planeChannels"))
                writer.uint32(/* id 3, wireType 0 =*/24).uint32(message.planeChannels);
            if (message.planeHeight != null && Object.hasOwnProperty.call(message, "planeHeight"))
                writer.uint32(/* id 4, wireType 0 =*/32).uint32(message.planeHeight);
            if (message.planeWidth != null && Object.hasOwnProperty.call(message, "planeWidth"))
                writer.uint32(/* id 5, wireType 0 =*/40).uint32(message.planeWidth);
            if (message.scalars != null && message.scalars.length) {
                writer.uint32(/* id 6, wireType 2 =*/50).fork();
                for (var i = 0; i < message.scalars.length; ++i)
                    writer.float(message.scalars[i]);
                writer.ldelim();
            }
            if (message.actionMask != null && Object.hasOwnProperty.call(message, "actionMask"))
                writer.uint32(/* id 7, wireType 2 =*/58).bytes(message.actionMask);
            if (message.actionSpaceSize != null && Object.hasOwnProperty.call(message, "actionSpaceSize"))
                writer.uint32(/* id 8, wireType 0 =*/64).uint32(message.actionSpaceSize);
            if (message.decisionIndex != null && Object.hasOwnProperty.call(message, "decisionIndex"))
                writer.uint32(/* id 9, wireType 0 =*/72).uint64(message.decisionIndex);
            if (message.phase != null && Object.hasOwnProperty.call(message, "phase"))
                writer.uint32(/* id 10, wireType 0 =*/80).int32(message.phase);
            if (message.activePlayer != null && Object.hasOwnProperty.call(message, "activePlayer"))
                writer.uint32(/* id 11, wireType 0 =*/88).uint32(message.activePlayer);
            return writer;
        };

        /**
         * Encodes the specified SeatObservation message, length delimited. Does not implicitly {@link game.SeatObservation.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.SeatObservation
         * @static
         * @param {game.ISeatObservation} message SeatObservation message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        SeatObservation.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a SeatObservation message from the specified reader or buffer.
         * @function decode
         * @memberof game.SeatObservation
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.SeatObservation} SeatObservation
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        SeatObservation.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.SeatObservation();
            while (reader.pos < end) {
                var tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.seat = reader.uint32();
                        break;
                    }
                case 2: {
                        if (!(message.planes && message.planes.length))
                            message.planes = [];
                        if ((tag & 7) === 2) {
                            var end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.planes.push(reader.float());
                        } else
                            message.planes.push(reader.float());
                        break;
                    }
                case 3: {
                        message.planeChannels = reader.uint32();
                        break;
                    }
                case 4: {
                        message.planeHeight = reader.uint32();
                        break;
                    }
                case 5: {
                        message.planeWidth = reader.uint32();
                        break;
                    }
                case 6: {
                        if (!(message.scalars && message.scalars.length))
                            message.scalars = [];
                        if ((tag & 7) === 2) {
                            var end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.scalars.push(reader.float());
                        } else
                            message.scalars.push(reader.float());
                        break;
                    }
                case 7: {
                        message.actionMask = reader.bytes();
                        break;
                    }
                case 8: {
                        message.actionSpaceSize = reader.uint32();
                        break;
                    }
                case 9: {
                        message.decisionIndex = reader.uint64();
                        break;
                    }
                case 10: {
                        message.phase = reader.int32();
                        break;
                    }
                case 11: {
                        message.activePlayer = reader.uint32();
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
         * Decodes a SeatObservation message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.SeatObservation
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.SeatObservation} SeatObservation
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        SeatObservation.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a SeatObservation message.
         * @function verify
         * @memberof game.SeatObservation
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        SeatObservation.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.seat != null && message.hasOwnProperty("seat"))
                if (!$util.isInteger(message.seat))
                    return "seat: integer expected";
            if (message.planes != null && message.hasOwnProperty("planes")) {
                if (!Array.isArray(message.planes))
                    return "planes: array expected";
                for (var i = 0; i < message.planes.length; ++i)
                    if (typeof message.planes[i] !== "number")
                        return "planes: number[] expected";
            }
            if (message.planeChannels != null && message.hasOwnProperty("planeChannels"))
                if (!$util.isInteger(message.planeChannels))
                    return "planeChannels: integer expected";
            if (message.planeHeight != null && message.hasOwnProperty("planeHeight"))
                if (!$util.isInteger(message.planeHeight))
                    return "planeHeight: integer expected";
            if (message.planeWidth != null && message.hasOwnProperty("planeWidth"))
                if (!$util.isInteger(message.planeWidth))
                    return "planeWidth: integer expected";
            if (message.scalars != null && message.hasOwnProperty("scalars")) {
                if (!Array.isArray(message.scalars))
                    return "scalars: array expected";
                for (var i = 0; i < message.scalars.length; ++i)
                    if (typeof message.scalars[i] !== "number")
                        return "scalars: number[] expected";
            }
            if (message.actionMask != null && message.hasOwnProperty("actionMask"))
                if (!(message.actionMask && typeof message.actionMask.length === "number" || $util.isString(message.actionMask)))
                    return "actionMask: buffer expected";
            if (message.actionSpaceSize != null && message.hasOwnProperty("actionSpaceSize"))
                if (!$util.isInteger(message.actionSpaceSize))
                    return "actionSpaceSize: integer expected";
            if (message.decisionIndex != null && message.hasOwnProperty("decisionIndex"))
                if (!$util.isInteger(message.decisionIndex) && !(message.decisionIndex && $util.isInteger(message.decisionIndex.low) && $util.isInteger(message.decisionIndex.high)))
                    return "decisionIndex: integer|Long expected";
            if (message.phase != null && message.hasOwnProperty("phase"))
                switch (message.phase) {
                default:
                    return "phase: enum value expected";
                case 0:
                case 1:
                case 2:
                case 3:
                case 4:
                case 5:
                    break;
                }
            if (message.activePlayer != null && message.hasOwnProperty("activePlayer"))
                if (!$util.isInteger(message.activePlayer))
                    return "activePlayer: integer expected";
            return null;
        };

        /**
         * Creates a SeatObservation message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.SeatObservation
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.SeatObservation} SeatObservation
         */
        SeatObservation.fromObject = function fromObject(object) {
            if (object instanceof $root.game.SeatObservation)
                return object;
            var message = new $root.game.SeatObservation();
            if (object.seat != null)
                message.seat = object.seat >>> 0;
            if (object.planes) {
                if (!Array.isArray(object.planes))
                    throw TypeError(".game.SeatObservation.planes: array expected");
                message.planes = [];
                for (var i = 0; i < object.planes.length; ++i)
                    message.planes[i] = Number(object.planes[i]);
            }
            if (object.planeChannels != null)
                message.planeChannels = object.planeChannels >>> 0;
            if (object.planeHeight != null)
                message.planeHeight = object.planeHeight >>> 0;
            if (object.planeWidth != null)
                message.planeWidth = object.planeWidth >>> 0;
            if (object.scalars) {
                if (!Array.isArray(object.scalars))
                    throw TypeError(".game.SeatObservation.scalars: array expected");
                message.scalars = [];
                for (var i = 0; i < object.scalars.length; ++i)
                    message.scalars[i] = Number(object.scalars[i]);
            }
            if (object.actionMask != null)
                if (typeof object.actionMask === "string")
                    $util.base64.decode(object.actionMask, message.actionMask = $util.newBuffer($util.base64.length(object.actionMask)), 0);
                else if (object.actionMask.length >= 0)
                    message.actionMask = object.actionMask;
            if (object.actionSpaceSize != null)
                message.actionSpaceSize = object.actionSpaceSize >>> 0;
            if (object.decisionIndex != null)
                if ($util.Long)
                    (message.decisionIndex = $util.Long.fromValue(object.decisionIndex)).unsigned = true;
                else if (typeof object.decisionIndex === "string")
                    message.decisionIndex = parseInt(object.decisionIndex, 10);
                else if (typeof object.decisionIndex === "number")
                    message.decisionIndex = object.decisionIndex;
                else if (typeof object.decisionIndex === "object")
                    message.decisionIndex = new $util.LongBits(object.decisionIndex.low >>> 0, object.decisionIndex.high >>> 0).toNumber(true);
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
            case "PHASE_MATCH_END":
            case 5:
                message.phase = 5;
                break;
            }
            if (object.activePlayer != null)
                message.activePlayer = object.activePlayer >>> 0;
            return message;
        };

        /**
         * Creates a plain object from a SeatObservation message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.SeatObservation
         * @static
         * @param {game.SeatObservation} message SeatObservation
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        SeatObservation.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.arrays || options.defaults) {
                object.planes = [];
                object.scalars = [];
            }
            if (options.defaults) {
                object.seat = 0;
                object.planeChannels = 0;
                object.planeHeight = 0;
                object.planeWidth = 0;
                if (options.bytes === String)
                    object.actionMask = "";
                else {
                    object.actionMask = [];
                    if (options.bytes !== Array)
                        object.actionMask = $util.newBuffer(object.actionMask);
                }
                object.actionSpaceSize = 0;
                if ($util.Long) {
                    var long = new $util.Long(0, 0, true);
                    object.decisionIndex = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.decisionIndex = options.longs === String ? "0" : 0;
                object.phase = options.enums === String ? "PHASE_INIT" : 0;
                object.activePlayer = 0;
            }
            if (message.seat != null && message.hasOwnProperty("seat"))
                object.seat = message.seat;
            if (message.planes && message.planes.length) {
                object.planes = [];
                for (var j = 0; j < message.planes.length; ++j)
                    object.planes[j] = options.json && !isFinite(message.planes[j]) ? String(message.planes[j]) : message.planes[j];
            }
            if (message.planeChannels != null && message.hasOwnProperty("planeChannels"))
                object.planeChannels = message.planeChannels;
            if (message.planeHeight != null && message.hasOwnProperty("planeHeight"))
                object.planeHeight = message.planeHeight;
            if (message.planeWidth != null && message.hasOwnProperty("planeWidth"))
                object.planeWidth = message.planeWidth;
            if (message.scalars && message.scalars.length) {
                object.scalars = [];
                for (var j = 0; j < message.scalars.length; ++j)
                    object.scalars[j] = options.json && !isFinite(message.scalars[j]) ? String(message.scalars[j]) : message.scalars[j];
            }
            if (message.actionMask != null && message.hasOwnProperty("actionMask"))
                object.actionMask = options.bytes === String ? $util.base64.encode(message.actionMask, 0, message.actionMask.length) : options.bytes === Array ? Array.prototype.slice.call(message.actionMask) : message.actionMask;
            if (message.actionSpaceSize != null && message.hasOwnProperty("actionSpaceSize"))
                object.actionSpaceSize = message.actionSpaceSize;
            if (message.decisionIndex != null && message.hasOwnProperty("decisionIndex"))
                if (typeof message.decisionIndex === "number")
                    object.decisionIndex = options.longs === String ? String(message.decisionIndex) : message.decisionIndex;
                else
                    object.decisionIndex = options.longs === String ? $util.Long.prototype.toString.call(message.decisionIndex) : options.longs === Number ? new $util.LongBits(message.decisionIndex.low >>> 0, message.decisionIndex.high >>> 0).toNumber(true) : message.decisionIndex;
            if (message.phase != null && message.hasOwnProperty("phase"))
                object.phase = options.enums === String ? $root.game.GamePhase[message.phase] === undefined ? message.phase : $root.game.GamePhase[message.phase] : message.phase;
            if (message.activePlayer != null && message.hasOwnProperty("activePlayer"))
                object.activePlayer = message.activePlayer;
            return object;
        };

        /**
         * Converts this SeatObservation to JSON.
         * @function toJSON
         * @memberof game.SeatObservation
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        SeatObservation.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for SeatObservation
         * @function getTypeUrl
         * @memberof game.SeatObservation
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        SeatObservation.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.SeatObservation";
        };

        return SeatObservation;
    })();

    game.EnvResetRequest = (function() {

        /**
         * Properties of an EnvResetRequest.
         * @memberof game
         * @interface IEnvResetRequest
         * @property {number|Long|undefined} [seed] EnvResetRequest seed
         * @property {game.IEnvConfig|undefined} [config] EnvResetRequest config
         */

        /**
         * Constructs a new EnvResetRequest.
         * @memberof game
         * @classdesc Represents an EnvResetRequest.
         * @implements IEnvResetRequest
         * @constructor
         * @param {game.IEnvResetRequest=} [properties] Properties to set
         */
        function EnvResetRequest(properties) {
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * EnvResetRequest seed.
         * @member {number|Long} seed
         * @memberof game.EnvResetRequest
         * @instance
         */
        EnvResetRequest.prototype.seed = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * EnvResetRequest config.
         * @member {game.EnvConfig} config
         * @memberof game.EnvResetRequest
         * @instance
         */
        EnvResetRequest.prototype.config = null;

        /**
         * Creates a new EnvResetRequest instance using the specified properties.
         * @function create
         * @memberof game.EnvResetRequest
         * @static
         * @param {game.IEnvResetRequest=} [properties] Properties to set
         * @returns {game.EnvResetRequest} EnvResetRequest instance
         */
        EnvResetRequest.create = function create(properties) {
            return new EnvResetRequest(properties);
        };

        /**
         * Encodes the specified EnvResetRequest message. Does not implicitly {@link game.EnvResetRequest.verify|verify} messages.
         * @function encode
         * @memberof game.EnvResetRequest
         * @static
         * @param {game.IEnvResetRequest} message EnvResetRequest message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvResetRequest.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.seed != null && Object.hasOwnProperty.call(message, "seed"))
                writer.uint32(/* id 1, wireType 0 =*/8).uint64(message.seed);
            if (message.config != null && Object.hasOwnProperty.call(message, "config"))
                $root.game.EnvConfig.encode(message.config, writer.uint32(/* id 2, wireType 2 =*/18).fork()).ldelim();
            return writer;
        };

        /**
         * Encodes the specified EnvResetRequest message, length delimited. Does not implicitly {@link game.EnvResetRequest.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.EnvResetRequest
         * @static
         * @param {game.IEnvResetRequest} message EnvResetRequest message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvResetRequest.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes an EnvResetRequest message from the specified reader or buffer.
         * @function decode
         * @memberof game.EnvResetRequest
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.EnvResetRequest} EnvResetRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvResetRequest.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.EnvResetRequest();
            while (reader.pos < end) {
                var tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.seed = reader.uint64();
                        break;
                    }
                case 2: {
                        message.config = $root.game.EnvConfig.decode(reader, reader.uint32());
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
         * Decodes an EnvResetRequest message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.EnvResetRequest
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.EnvResetRequest} EnvResetRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvResetRequest.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies an EnvResetRequest message.
         * @function verify
         * @memberof game.EnvResetRequest
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        EnvResetRequest.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.seed != null && message.hasOwnProperty("seed"))
                if (!$util.isInteger(message.seed) && !(message.seed && $util.isInteger(message.seed.low) && $util.isInteger(message.seed.high)))
                    return "seed: integer|Long expected";
            if (message.config != null && message.hasOwnProperty("config")) {
                var error = $root.game.EnvConfig.verify(message.config);
                if (error)
                    return "config." + error;
            }
            return null;
        };

        /**
         * Creates an EnvResetRequest message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.EnvResetRequest
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.EnvResetRequest} EnvResetRequest
         */
        EnvResetRequest.fromObject = function fromObject(object) {
            if (object instanceof $root.game.EnvResetRequest)
                return object;
            var message = new $root.game.EnvResetRequest();
            if (object.seed != null)
                if ($util.Long)
                    (message.seed = $util.Long.fromValue(object.seed)).unsigned = true;
                else if (typeof object.seed === "string")
                    message.seed = parseInt(object.seed, 10);
                else if (typeof object.seed === "number")
                    message.seed = object.seed;
                else if (typeof object.seed === "object")
                    message.seed = new $util.LongBits(object.seed.low >>> 0, object.seed.high >>> 0).toNumber(true);
            if (object.config != null) {
                if (typeof object.config !== "object")
                    throw TypeError(".game.EnvResetRequest.config: object expected");
                message.config = $root.game.EnvConfig.fromObject(object.config);
            }
            return message;
        };

        /**
         * Creates a plain object from an EnvResetRequest message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.EnvResetRequest
         * @static
         * @param {game.EnvResetRequest} message EnvResetRequest
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        EnvResetRequest.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.defaults) {
                if ($util.Long) {
                    var long = new $util.Long(0, 0, true);
                    object.seed = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.seed = options.longs === String ? "0" : 0;
                object.config = null;
            }
            if (message.seed != null && message.hasOwnProperty("seed"))
                if (typeof message.seed === "number")
                    object.seed = options.longs === String ? String(message.seed) : message.seed;
                else
                    object.seed = options.longs === String ? $util.Long.prototype.toString.call(message.seed) : options.longs === Number ? new $util.LongBits(message.seed.low >>> 0, message.seed.high >>> 0).toNumber(true) : message.seed;
            if (message.config != null && message.hasOwnProperty("config"))
                object.config = $root.game.EnvConfig.toObject(message.config, options);
            return object;
        };

        /**
         * Converts this EnvResetRequest to JSON.
         * @function toJSON
         * @memberof game.EnvResetRequest
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        EnvResetRequest.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for EnvResetRequest
         * @function getTypeUrl
         * @memberof game.EnvResetRequest
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        EnvResetRequest.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.EnvResetRequest";
        };

        return EnvResetRequest;
    })();

    game.EnvResetResponse = (function() {

        /**
         * Properties of an EnvResetResponse.
         * @memberof game
         * @interface IEnvResetResponse
         * @property {game.ISeatObservation|undefined} [observation] EnvResetResponse observation
         * @property {Array.<number>|undefined} [rewards] EnvResetResponse rewards
         * @property {boolean|undefined} [terminated] EnvResetResponse terminated
         * @property {boolean|undefined} [truncated] EnvResetResponse truncated
         * @property {game.IRoundOutcome|undefined} [roundOutcome] EnvResetResponse roundOutcome
         */

        /**
         * Constructs a new EnvResetResponse.
         * @memberof game
         * @classdesc Represents an EnvResetResponse.
         * @implements IEnvResetResponse
         * @constructor
         * @param {game.IEnvResetResponse=} [properties] Properties to set
         */
        function EnvResetResponse(properties) {
            this.rewards = [];
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * EnvResetResponse observation.
         * @member {game.SeatObservation} observation
         * @memberof game.EnvResetResponse
         * @instance
         */
        EnvResetResponse.prototype.observation = null;

        /**
         * EnvResetResponse rewards.
         * @member {Array.<number>} rewards
         * @memberof game.EnvResetResponse
         * @instance
         */
        EnvResetResponse.prototype.rewards = $util.emptyArray;

        /**
         * EnvResetResponse terminated.
         * @member {boolean} terminated
         * @memberof game.EnvResetResponse
         * @instance
         */
        EnvResetResponse.prototype.terminated = false;

        /**
         * EnvResetResponse truncated.
         * @member {boolean} truncated
         * @memberof game.EnvResetResponse
         * @instance
         */
        EnvResetResponse.prototype.truncated = false;

        /**
         * EnvResetResponse roundOutcome.
         * @member {game.RoundOutcome} roundOutcome
         * @memberof game.EnvResetResponse
         * @instance
         */
        EnvResetResponse.prototype.roundOutcome = null;

        /**
         * Creates a new EnvResetResponse instance using the specified properties.
         * @function create
         * @memberof game.EnvResetResponse
         * @static
         * @param {game.IEnvResetResponse=} [properties] Properties to set
         * @returns {game.EnvResetResponse} EnvResetResponse instance
         */
        EnvResetResponse.create = function create(properties) {
            return new EnvResetResponse(properties);
        };

        /**
         * Encodes the specified EnvResetResponse message. Does not implicitly {@link game.EnvResetResponse.verify|verify} messages.
         * @function encode
         * @memberof game.EnvResetResponse
         * @static
         * @param {game.IEnvResetResponse} message EnvResetResponse message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvResetResponse.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.observation != null && Object.hasOwnProperty.call(message, "observation"))
                $root.game.SeatObservation.encode(message.observation, writer.uint32(/* id 1, wireType 2 =*/10).fork()).ldelim();
            if (message.rewards != null && message.rewards.length) {
                writer.uint32(/* id 2, wireType 2 =*/18).fork();
                for (var i = 0; i < message.rewards.length; ++i)
                    writer.float(message.rewards[i]);
                writer.ldelim();
            }
            if (message.terminated != null && Object.hasOwnProperty.call(message, "terminated"))
                writer.uint32(/* id 3, wireType 0 =*/24).bool(message.terminated);
            if (message.truncated != null && Object.hasOwnProperty.call(message, "truncated"))
                writer.uint32(/* id 4, wireType 0 =*/32).bool(message.truncated);
            if (message.roundOutcome != null && Object.hasOwnProperty.call(message, "roundOutcome"))
                $root.game.RoundOutcome.encode(message.roundOutcome, writer.uint32(/* id 5, wireType 2 =*/42).fork()).ldelim();
            return writer;
        };

        /**
         * Encodes the specified EnvResetResponse message, length delimited. Does not implicitly {@link game.EnvResetResponse.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.EnvResetResponse
         * @static
         * @param {game.IEnvResetResponse} message EnvResetResponse message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvResetResponse.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes an EnvResetResponse message from the specified reader or buffer.
         * @function decode
         * @memberof game.EnvResetResponse
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.EnvResetResponse} EnvResetResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvResetResponse.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.EnvResetResponse();
            while (reader.pos < end) {
                var tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.observation = $root.game.SeatObservation.decode(reader, reader.uint32());
                        break;
                    }
                case 2: {
                        if (!(message.rewards && message.rewards.length))
                            message.rewards = [];
                        if ((tag & 7) === 2) {
                            var end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.rewards.push(reader.float());
                        } else
                            message.rewards.push(reader.float());
                        break;
                    }
                case 3: {
                        message.terminated = reader.bool();
                        break;
                    }
                case 4: {
                        message.truncated = reader.bool();
                        break;
                    }
                case 5: {
                        message.roundOutcome = $root.game.RoundOutcome.decode(reader, reader.uint32());
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
         * Decodes an EnvResetResponse message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.EnvResetResponse
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.EnvResetResponse} EnvResetResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvResetResponse.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies an EnvResetResponse message.
         * @function verify
         * @memberof game.EnvResetResponse
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        EnvResetResponse.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.observation != null && message.hasOwnProperty("observation")) {
                var error = $root.game.SeatObservation.verify(message.observation);
                if (error)
                    return "observation." + error;
            }
            if (message.rewards != null && message.hasOwnProperty("rewards")) {
                if (!Array.isArray(message.rewards))
                    return "rewards: array expected";
                for (var i = 0; i < message.rewards.length; ++i)
                    if (typeof message.rewards[i] !== "number")
                        return "rewards: number[] expected";
            }
            if (message.terminated != null && message.hasOwnProperty("terminated"))
                if (typeof message.terminated !== "boolean")
                    return "terminated: boolean expected";
            if (message.truncated != null && message.hasOwnProperty("truncated"))
                if (typeof message.truncated !== "boolean")
                    return "truncated: boolean expected";
            if (message.roundOutcome != null && message.hasOwnProperty("roundOutcome")) {
                var error = $root.game.RoundOutcome.verify(message.roundOutcome);
                if (error)
                    return "roundOutcome." + error;
            }
            return null;
        };

        /**
         * Creates an EnvResetResponse message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.EnvResetResponse
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.EnvResetResponse} EnvResetResponse
         */
        EnvResetResponse.fromObject = function fromObject(object) {
            if (object instanceof $root.game.EnvResetResponse)
                return object;
            var message = new $root.game.EnvResetResponse();
            if (object.observation != null) {
                if (typeof object.observation !== "object")
                    throw TypeError(".game.EnvResetResponse.observation: object expected");
                message.observation = $root.game.SeatObservation.fromObject(object.observation);
            }
            if (object.rewards) {
                if (!Array.isArray(object.rewards))
                    throw TypeError(".game.EnvResetResponse.rewards: array expected");
                message.rewards = [];
                for (var i = 0; i < object.rewards.length; ++i)
                    message.rewards[i] = Number(object.rewards[i]);
            }
            if (object.terminated != null)
                message.terminated = Boolean(object.terminated);
            if (object.truncated != null)
                message.truncated = Boolean(object.truncated);
            if (object.roundOutcome != null) {
                if (typeof object.roundOutcome !== "object")
                    throw TypeError(".game.EnvResetResponse.roundOutcome: object expected");
                message.roundOutcome = $root.game.RoundOutcome.fromObject(object.roundOutcome);
            }
            return message;
        };

        /**
         * Creates a plain object from an EnvResetResponse message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.EnvResetResponse
         * @static
         * @param {game.EnvResetResponse} message EnvResetResponse
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        EnvResetResponse.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.arrays || options.defaults)
                object.rewards = [];
            if (options.defaults) {
                object.observation = null;
                object.terminated = false;
                object.truncated = false;
                object.roundOutcome = null;
            }
            if (message.observation != null && message.hasOwnProperty("observation"))
                object.observation = $root.game.SeatObservation.toObject(message.observation, options);
            if (message.rewards && message.rewards.length) {
                object.rewards = [];
                for (var j = 0; j < message.rewards.length; ++j)
                    object.rewards[j] = options.json && !isFinite(message.rewards[j]) ? String(message.rewards[j]) : message.rewards[j];
            }
            if (message.terminated != null && message.hasOwnProperty("terminated"))
                object.terminated = message.terminated;
            if (message.truncated != null && message.hasOwnProperty("truncated"))
                object.truncated = message.truncated;
            if (message.roundOutcome != null && message.hasOwnProperty("roundOutcome"))
                object.roundOutcome = $root.game.RoundOutcome.toObject(message.roundOutcome, options);
            return object;
        };

        /**
         * Converts this EnvResetResponse to JSON.
         * @function toJSON
         * @memberof game.EnvResetResponse
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        EnvResetResponse.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for EnvResetResponse
         * @function getTypeUrl
         * @memberof game.EnvResetResponse
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        EnvResetResponse.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.EnvResetResponse";
        };

        return EnvResetResponse;
    })();

    game.EnvStepRequest = (function() {

        /**
         * Properties of an EnvStepRequest.
         * @memberof game
         * @interface IEnvStepRequest
         * @property {number|undefined} [actionId] EnvStepRequest actionId
         */

        /**
         * Constructs a new EnvStepRequest.
         * @memberof game
         * @classdesc Represents an EnvStepRequest.
         * @implements IEnvStepRequest
         * @constructor
         * @param {game.IEnvStepRequest=} [properties] Properties to set
         */
        function EnvStepRequest(properties) {
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * EnvStepRequest actionId.
         * @member {number} actionId
         * @memberof game.EnvStepRequest
         * @instance
         */
        EnvStepRequest.prototype.actionId = 0;

        /**
         * Creates a new EnvStepRequest instance using the specified properties.
         * @function create
         * @memberof game.EnvStepRequest
         * @static
         * @param {game.IEnvStepRequest=} [properties] Properties to set
         * @returns {game.EnvStepRequest} EnvStepRequest instance
         */
        EnvStepRequest.create = function create(properties) {
            return new EnvStepRequest(properties);
        };

        /**
         * Encodes the specified EnvStepRequest message. Does not implicitly {@link game.EnvStepRequest.verify|verify} messages.
         * @function encode
         * @memberof game.EnvStepRequest
         * @static
         * @param {game.IEnvStepRequest} message EnvStepRequest message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvStepRequest.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.actionId != null && Object.hasOwnProperty.call(message, "actionId"))
                writer.uint32(/* id 1, wireType 0 =*/8).uint32(message.actionId);
            return writer;
        };

        /**
         * Encodes the specified EnvStepRequest message, length delimited. Does not implicitly {@link game.EnvStepRequest.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.EnvStepRequest
         * @static
         * @param {game.IEnvStepRequest} message EnvStepRequest message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvStepRequest.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes an EnvStepRequest message from the specified reader or buffer.
         * @function decode
         * @memberof game.EnvStepRequest
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.EnvStepRequest} EnvStepRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvStepRequest.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.EnvStepRequest();
            while (reader.pos < end) {
                var tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.actionId = reader.uint32();
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
         * Decodes an EnvStepRequest message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.EnvStepRequest
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.EnvStepRequest} EnvStepRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvStepRequest.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies an EnvStepRequest message.
         * @function verify
         * @memberof game.EnvStepRequest
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        EnvStepRequest.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.actionId != null && message.hasOwnProperty("actionId"))
                if (!$util.isInteger(message.actionId))
                    return "actionId: integer expected";
            return null;
        };

        /**
         * Creates an EnvStepRequest message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.EnvStepRequest
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.EnvStepRequest} EnvStepRequest
         */
        EnvStepRequest.fromObject = function fromObject(object) {
            if (object instanceof $root.game.EnvStepRequest)
                return object;
            var message = new $root.game.EnvStepRequest();
            if (object.actionId != null)
                message.actionId = object.actionId >>> 0;
            return message;
        };

        /**
         * Creates a plain object from an EnvStepRequest message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.EnvStepRequest
         * @static
         * @param {game.EnvStepRequest} message EnvStepRequest
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        EnvStepRequest.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.defaults)
                object.actionId = 0;
            if (message.actionId != null && message.hasOwnProperty("actionId"))
                object.actionId = message.actionId;
            return object;
        };

        /**
         * Converts this EnvStepRequest to JSON.
         * @function toJSON
         * @memberof game.EnvStepRequest
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        EnvStepRequest.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for EnvStepRequest
         * @function getTypeUrl
         * @memberof game.EnvStepRequest
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        EnvStepRequest.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.EnvStepRequest";
        };

        return EnvStepRequest;
    })();

    game.EnvStepResponse = (function() {

        /**
         * Properties of an EnvStepResponse.
         * @memberof game
         * @interface IEnvStepResponse
         * @property {game.ISeatObservation|undefined} [observation] EnvStepResponse observation
         * @property {Array.<number>|undefined} [rewards] EnvStepResponse rewards
         * @property {boolean|undefined} [terminated] EnvStepResponse terminated
         * @property {boolean|undefined} [truncated] EnvStepResponse truncated
         * @property {game.IRoundOutcome|undefined} [roundOutcome] EnvStepResponse roundOutcome
         */

        /**
         * Constructs a new EnvStepResponse.
         * @memberof game
         * @classdesc Represents an EnvStepResponse.
         * @implements IEnvStepResponse
         * @constructor
         * @param {game.IEnvStepResponse=} [properties] Properties to set
         */
        function EnvStepResponse(properties) {
            this.rewards = [];
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * EnvStepResponse observation.
         * @member {game.SeatObservation} observation
         * @memberof game.EnvStepResponse
         * @instance
         */
        EnvStepResponse.prototype.observation = null;

        /**
         * EnvStepResponse rewards.
         * @member {Array.<number>} rewards
         * @memberof game.EnvStepResponse
         * @instance
         */
        EnvStepResponse.prototype.rewards = $util.emptyArray;

        /**
         * EnvStepResponse terminated.
         * @member {boolean} terminated
         * @memberof game.EnvStepResponse
         * @instance
         */
        EnvStepResponse.prototype.terminated = false;

        /**
         * EnvStepResponse truncated.
         * @member {boolean} truncated
         * @memberof game.EnvStepResponse
         * @instance
         */
        EnvStepResponse.prototype.truncated = false;

        /**
         * EnvStepResponse roundOutcome.
         * @member {game.RoundOutcome} roundOutcome
         * @memberof game.EnvStepResponse
         * @instance
         */
        EnvStepResponse.prototype.roundOutcome = null;

        /**
         * Creates a new EnvStepResponse instance using the specified properties.
         * @function create
         * @memberof game.EnvStepResponse
         * @static
         * @param {game.IEnvStepResponse=} [properties] Properties to set
         * @returns {game.EnvStepResponse} EnvStepResponse instance
         */
        EnvStepResponse.create = function create(properties) {
            return new EnvStepResponse(properties);
        };

        /**
         * Encodes the specified EnvStepResponse message. Does not implicitly {@link game.EnvStepResponse.verify|verify} messages.
         * @function encode
         * @memberof game.EnvStepResponse
         * @static
         * @param {game.IEnvStepResponse} message EnvStepResponse message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvStepResponse.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.observation != null && Object.hasOwnProperty.call(message, "observation"))
                $root.game.SeatObservation.encode(message.observation, writer.uint32(/* id 1, wireType 2 =*/10).fork()).ldelim();
            if (message.rewards != null && message.rewards.length) {
                writer.uint32(/* id 2, wireType 2 =*/18).fork();
                for (var i = 0; i < message.rewards.length; ++i)
                    writer.float(message.rewards[i]);
                writer.ldelim();
            }
            if (message.terminated != null && Object.hasOwnProperty.call(message, "terminated"))
                writer.uint32(/* id 3, wireType 0 =*/24).bool(message.terminated);
            if (message.truncated != null && Object.hasOwnProperty.call(message, "truncated"))
                writer.uint32(/* id 4, wireType 0 =*/32).bool(message.truncated);
            if (message.roundOutcome != null && Object.hasOwnProperty.call(message, "roundOutcome"))
                $root.game.RoundOutcome.encode(message.roundOutcome, writer.uint32(/* id 5, wireType 2 =*/42).fork()).ldelim();
            return writer;
        };

        /**
         * Encodes the specified EnvStepResponse message, length delimited. Does not implicitly {@link game.EnvStepResponse.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.EnvStepResponse
         * @static
         * @param {game.IEnvStepResponse} message EnvStepResponse message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvStepResponse.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes an EnvStepResponse message from the specified reader or buffer.
         * @function decode
         * @memberof game.EnvStepResponse
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.EnvStepResponse} EnvStepResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvStepResponse.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.EnvStepResponse();
            while (reader.pos < end) {
                var tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.observation = $root.game.SeatObservation.decode(reader, reader.uint32());
                        break;
                    }
                case 2: {
                        if (!(message.rewards && message.rewards.length))
                            message.rewards = [];
                        if ((tag & 7) === 2) {
                            var end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.rewards.push(reader.float());
                        } else
                            message.rewards.push(reader.float());
                        break;
                    }
                case 3: {
                        message.terminated = reader.bool();
                        break;
                    }
                case 4: {
                        message.truncated = reader.bool();
                        break;
                    }
                case 5: {
                        message.roundOutcome = $root.game.RoundOutcome.decode(reader, reader.uint32());
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
         * Decodes an EnvStepResponse message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.EnvStepResponse
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.EnvStepResponse} EnvStepResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvStepResponse.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies an EnvStepResponse message.
         * @function verify
         * @memberof game.EnvStepResponse
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        EnvStepResponse.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.observation != null && message.hasOwnProperty("observation")) {
                var error = $root.game.SeatObservation.verify(message.observation);
                if (error)
                    return "observation." + error;
            }
            if (message.rewards != null && message.hasOwnProperty("rewards")) {
                if (!Array.isArray(message.rewards))
                    return "rewards: array expected";
                for (var i = 0; i < message.rewards.length; ++i)
                    if (typeof message.rewards[i] !== "number")
                        return "rewards: number[] expected";
            }
            if (message.terminated != null && message.hasOwnProperty("terminated"))
                if (typeof message.terminated !== "boolean")
                    return "terminated: boolean expected";
            if (message.truncated != null && message.hasOwnProperty("truncated"))
                if (typeof message.truncated !== "boolean")
                    return "truncated: boolean expected";
            if (message.roundOutcome != null && message.hasOwnProperty("roundOutcome")) {
                var error = $root.game.RoundOutcome.verify(message.roundOutcome);
                if (error)
                    return "roundOutcome." + error;
            }
            return null;
        };

        /**
         * Creates an EnvStepResponse message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.EnvStepResponse
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.EnvStepResponse} EnvStepResponse
         */
        EnvStepResponse.fromObject = function fromObject(object) {
            if (object instanceof $root.game.EnvStepResponse)
                return object;
            var message = new $root.game.EnvStepResponse();
            if (object.observation != null) {
                if (typeof object.observation !== "object")
                    throw TypeError(".game.EnvStepResponse.observation: object expected");
                message.observation = $root.game.SeatObservation.fromObject(object.observation);
            }
            if (object.rewards) {
                if (!Array.isArray(object.rewards))
                    throw TypeError(".game.EnvStepResponse.rewards: array expected");
                message.rewards = [];
                for (var i = 0; i < object.rewards.length; ++i)
                    message.rewards[i] = Number(object.rewards[i]);
            }
            if (object.terminated != null)
                message.terminated = Boolean(object.terminated);
            if (object.truncated != null)
                message.truncated = Boolean(object.truncated);
            if (object.roundOutcome != null) {
                if (typeof object.roundOutcome !== "object")
                    throw TypeError(".game.EnvStepResponse.roundOutcome: object expected");
                message.roundOutcome = $root.game.RoundOutcome.fromObject(object.roundOutcome);
            }
            return message;
        };

        /**
         * Creates a plain object from an EnvStepResponse message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.EnvStepResponse
         * @static
         * @param {game.EnvStepResponse} message EnvStepResponse
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        EnvStepResponse.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.arrays || options.defaults)
                object.rewards = [];
            if (options.defaults) {
                object.observation = null;
                object.terminated = false;
                object.truncated = false;
                object.roundOutcome = null;
            }
            if (message.observation != null && message.hasOwnProperty("observation"))
                object.observation = $root.game.SeatObservation.toObject(message.observation, options);
            if (message.rewards && message.rewards.length) {
                object.rewards = [];
                for (var j = 0; j < message.rewards.length; ++j)
                    object.rewards[j] = options.json && !isFinite(message.rewards[j]) ? String(message.rewards[j]) : message.rewards[j];
            }
            if (message.terminated != null && message.hasOwnProperty("terminated"))
                object.terminated = message.terminated;
            if (message.truncated != null && message.hasOwnProperty("truncated"))
                object.truncated = message.truncated;
            if (message.roundOutcome != null && message.hasOwnProperty("roundOutcome"))
                object.roundOutcome = $root.game.RoundOutcome.toObject(message.roundOutcome, options);
            return object;
        };

        /**
         * Converts this EnvStepResponse to JSON.
         * @function toJSON
         * @memberof game.EnvStepResponse
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        EnvStepResponse.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for EnvStepResponse
         * @function getTypeUrl
         * @memberof game.EnvStepResponse
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        EnvStepResponse.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.EnvStepResponse";
        };

        return EnvStepResponse;
    })();

    game.TrajectoryRequest = (function() {

        /**
         * Properties of a TrajectoryRequest.
         * @memberof game
         * @interface ITrajectoryRequest
         * @property {number|undefined} [episodes] TrajectoryRequest episodes
         * @property {number|Long|undefined} [startSeed] TrajectoryRequest startSeed
         * @property {game.IEnvConfig|undefined} [config] TrajectoryRequest config
         */

        /**
         * Constructs a new TrajectoryRequest.
         * @memberof game
         * @classdesc Represents a TrajectoryRequest.
         * @implements ITrajectoryRequest
         * @constructor
         * @param {game.ITrajectoryRequest=} [properties] Properties to set
         */
        function TrajectoryRequest(properties) {
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * TrajectoryRequest episodes.
         * @member {number} episodes
         * @memberof game.TrajectoryRequest
         * @instance
         */
        TrajectoryRequest.prototype.episodes = 0;

        /**
         * TrajectoryRequest startSeed.
         * @member {number|Long} startSeed
         * @memberof game.TrajectoryRequest
         * @instance
         */
        TrajectoryRequest.prototype.startSeed = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * TrajectoryRequest config.
         * @member {game.EnvConfig} config
         * @memberof game.TrajectoryRequest
         * @instance
         */
        TrajectoryRequest.prototype.config = null;

        /**
         * Creates a new TrajectoryRequest instance using the specified properties.
         * @function create
         * @memberof game.TrajectoryRequest
         * @static
         * @param {game.ITrajectoryRequest=} [properties] Properties to set
         * @returns {game.TrajectoryRequest} TrajectoryRequest instance
         */
        TrajectoryRequest.create = function create(properties) {
            return new TrajectoryRequest(properties);
        };

        /**
         * Encodes the specified TrajectoryRequest message. Does not implicitly {@link game.TrajectoryRequest.verify|verify} messages.
         * @function encode
         * @memberof game.TrajectoryRequest
         * @static
         * @param {game.ITrajectoryRequest} message TrajectoryRequest message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        TrajectoryRequest.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.episodes != null && Object.hasOwnProperty.call(message, "episodes"))
                writer.uint32(/* id 1, wireType 0 =*/8).uint32(message.episodes);
            if (message.startSeed != null && Object.hasOwnProperty.call(message, "startSeed"))
                writer.uint32(/* id 2, wireType 0 =*/16).uint64(message.startSeed);
            if (message.config != null && Object.hasOwnProperty.call(message, "config"))
                $root.game.EnvConfig.encode(message.config, writer.uint32(/* id 3, wireType 2 =*/26).fork()).ldelim();
            return writer;
        };

        /**
         * Encodes the specified TrajectoryRequest message, length delimited. Does not implicitly {@link game.TrajectoryRequest.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.TrajectoryRequest
         * @static
         * @param {game.ITrajectoryRequest} message TrajectoryRequest message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        TrajectoryRequest.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a TrajectoryRequest message from the specified reader or buffer.
         * @function decode
         * @memberof game.TrajectoryRequest
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.TrajectoryRequest} TrajectoryRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        TrajectoryRequest.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.TrajectoryRequest();
            while (reader.pos < end) {
                var tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.episodes = reader.uint32();
                        break;
                    }
                case 2: {
                        message.startSeed = reader.uint64();
                        break;
                    }
                case 3: {
                        message.config = $root.game.EnvConfig.decode(reader, reader.uint32());
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
         * Decodes a TrajectoryRequest message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.TrajectoryRequest
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.TrajectoryRequest} TrajectoryRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        TrajectoryRequest.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a TrajectoryRequest message.
         * @function verify
         * @memberof game.TrajectoryRequest
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        TrajectoryRequest.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.episodes != null && message.hasOwnProperty("episodes"))
                if (!$util.isInteger(message.episodes))
                    return "episodes: integer expected";
            if (message.startSeed != null && message.hasOwnProperty("startSeed"))
                if (!$util.isInteger(message.startSeed) && !(message.startSeed && $util.isInteger(message.startSeed.low) && $util.isInteger(message.startSeed.high)))
                    return "startSeed: integer|Long expected";
            if (message.config != null && message.hasOwnProperty("config")) {
                var error = $root.game.EnvConfig.verify(message.config);
                if (error)
                    return "config." + error;
            }
            return null;
        };

        /**
         * Creates a TrajectoryRequest message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.TrajectoryRequest
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.TrajectoryRequest} TrajectoryRequest
         */
        TrajectoryRequest.fromObject = function fromObject(object) {
            if (object instanceof $root.game.TrajectoryRequest)
                return object;
            var message = new $root.game.TrajectoryRequest();
            if (object.episodes != null)
                message.episodes = object.episodes >>> 0;
            if (object.startSeed != null)
                if ($util.Long)
                    (message.startSeed = $util.Long.fromValue(object.startSeed)).unsigned = true;
                else if (typeof object.startSeed === "string")
                    message.startSeed = parseInt(object.startSeed, 10);
                else if (typeof object.startSeed === "number")
                    message.startSeed = object.startSeed;
                else if (typeof object.startSeed === "object")
                    message.startSeed = new $util.LongBits(object.startSeed.low >>> 0, object.startSeed.high >>> 0).toNumber(true);
            if (object.config != null) {
                if (typeof object.config !== "object")
                    throw TypeError(".game.TrajectoryRequest.config: object expected");
                message.config = $root.game.EnvConfig.fromObject(object.config);
            }
            return message;
        };

        /**
         * Creates a plain object from a TrajectoryRequest message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.TrajectoryRequest
         * @static
         * @param {game.TrajectoryRequest} message TrajectoryRequest
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        TrajectoryRequest.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.defaults) {
                object.episodes = 0;
                if ($util.Long) {
                    var long = new $util.Long(0, 0, true);
                    object.startSeed = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.startSeed = options.longs === String ? "0" : 0;
                object.config = null;
            }
            if (message.episodes != null && message.hasOwnProperty("episodes"))
                object.episodes = message.episodes;
            if (message.startSeed != null && message.hasOwnProperty("startSeed"))
                if (typeof message.startSeed === "number")
                    object.startSeed = options.longs === String ? String(message.startSeed) : message.startSeed;
                else
                    object.startSeed = options.longs === String ? $util.Long.prototype.toString.call(message.startSeed) : options.longs === Number ? new $util.LongBits(message.startSeed.low >>> 0, message.startSeed.high >>> 0).toNumber(true) : message.startSeed;
            if (message.config != null && message.hasOwnProperty("config"))
                object.config = $root.game.EnvConfig.toObject(message.config, options);
            return object;
        };

        /**
         * Converts this TrajectoryRequest to JSON.
         * @function toJSON
         * @memberof game.TrajectoryRequest
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        TrajectoryRequest.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for TrajectoryRequest
         * @function getTypeUrl
         * @memberof game.TrajectoryRequest
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        TrajectoryRequest.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.TrajectoryRequest";
        };

        return TrajectoryRequest;
    })();

    game.TrajectorySample = (function() {

        /**
         * Properties of a TrajectorySample.
         * @memberof game
         * @interface ITrajectorySample
         * @property {game.ISeatObservation|undefined} [observation] TrajectorySample observation
         * @property {number|undefined} [actionId] TrajectorySample actionId
         * @property {Array.<number>|undefined} [rewards] TrajectorySample rewards
         * @property {game.ISeatObservation|undefined} [nextObservation] TrajectorySample nextObservation
         * @property {boolean|undefined} [terminated] TrajectorySample terminated
         * @property {boolean|undefined} [truncated] TrajectorySample truncated
         * @property {number|undefined} [actingSeat] TrajectorySample actingSeat
         * @property {number|Long|undefined} [episodeIndex] TrajectorySample episodeIndex
         * @property {Array.<number>|undefined} [terminalRewards] TrajectorySample terminalRewards
         * @property {game.IRoundOutcome|undefined} [terminalOutcome] TrajectorySample terminalOutcome
         */

        /**
         * Constructs a new TrajectorySample.
         * @memberof game
         * @classdesc Represents a TrajectorySample.
         * @implements ITrajectorySample
         * @constructor
         * @param {game.ITrajectorySample=} [properties] Properties to set
         */
        function TrajectorySample(properties) {
            this.rewards = [];
            this.terminalRewards = [];
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * TrajectorySample observation.
         * @member {game.SeatObservation} observation
         * @memberof game.TrajectorySample
         * @instance
         */
        TrajectorySample.prototype.observation = null;

        /**
         * TrajectorySample actionId.
         * @member {number} actionId
         * @memberof game.TrajectorySample
         * @instance
         */
        TrajectorySample.prototype.actionId = 0;

        /**
         * TrajectorySample rewards.
         * @member {Array.<number>} rewards
         * @memberof game.TrajectorySample
         * @instance
         */
        TrajectorySample.prototype.rewards = $util.emptyArray;

        /**
         * TrajectorySample nextObservation.
         * @member {game.SeatObservation} nextObservation
         * @memberof game.TrajectorySample
         * @instance
         */
        TrajectorySample.prototype.nextObservation = null;

        /**
         * TrajectorySample terminated.
         * @member {boolean} terminated
         * @memberof game.TrajectorySample
         * @instance
         */
        TrajectorySample.prototype.terminated = false;

        /**
         * TrajectorySample truncated.
         * @member {boolean} truncated
         * @memberof game.TrajectorySample
         * @instance
         */
        TrajectorySample.prototype.truncated = false;

        /**
         * TrajectorySample actingSeat.
         * @member {number} actingSeat
         * @memberof game.TrajectorySample
         * @instance
         */
        TrajectorySample.prototype.actingSeat = 0;

        /**
         * TrajectorySample episodeIndex.
         * @member {number|Long} episodeIndex
         * @memberof game.TrajectorySample
         * @instance
         */
        TrajectorySample.prototype.episodeIndex = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * TrajectorySample terminalRewards.
         * @member {Array.<number>} terminalRewards
         * @memberof game.TrajectorySample
         * @instance
         */
        TrajectorySample.prototype.terminalRewards = $util.emptyArray;

        /**
         * TrajectorySample terminalOutcome.
         * @member {game.RoundOutcome} terminalOutcome
         * @memberof game.TrajectorySample
         * @instance
         */
        TrajectorySample.prototype.terminalOutcome = null;

        /**
         * Creates a new TrajectorySample instance using the specified properties.
         * @function create
         * @memberof game.TrajectorySample
         * @static
         * @param {game.ITrajectorySample=} [properties] Properties to set
         * @returns {game.TrajectorySample} TrajectorySample instance
         */
        TrajectorySample.create = function create(properties) {
            return new TrajectorySample(properties);
        };

        /**
         * Encodes the specified TrajectorySample message. Does not implicitly {@link game.TrajectorySample.verify|verify} messages.
         * @function encode
         * @memberof game.TrajectorySample
         * @static
         * @param {game.ITrajectorySample} message TrajectorySample message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        TrajectorySample.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.observation != null && Object.hasOwnProperty.call(message, "observation"))
                $root.game.SeatObservation.encode(message.observation, writer.uint32(/* id 1, wireType 2 =*/10).fork()).ldelim();
            if (message.actionId != null && Object.hasOwnProperty.call(message, "actionId"))
                writer.uint32(/* id 2, wireType 0 =*/16).uint32(message.actionId);
            if (message.rewards != null && message.rewards.length) {
                writer.uint32(/* id 3, wireType 2 =*/26).fork();
                for (var i = 0; i < message.rewards.length; ++i)
                    writer.float(message.rewards[i]);
                writer.ldelim();
            }
            if (message.nextObservation != null && Object.hasOwnProperty.call(message, "nextObservation"))
                $root.game.SeatObservation.encode(message.nextObservation, writer.uint32(/* id 4, wireType 2 =*/34).fork()).ldelim();
            if (message.terminated != null && Object.hasOwnProperty.call(message, "terminated"))
                writer.uint32(/* id 5, wireType 0 =*/40).bool(message.terminated);
            if (message.truncated != null && Object.hasOwnProperty.call(message, "truncated"))
                writer.uint32(/* id 6, wireType 0 =*/48).bool(message.truncated);
            if (message.actingSeat != null && Object.hasOwnProperty.call(message, "actingSeat"))
                writer.uint32(/* id 7, wireType 0 =*/56).uint32(message.actingSeat);
            if (message.episodeIndex != null && Object.hasOwnProperty.call(message, "episodeIndex"))
                writer.uint32(/* id 8, wireType 0 =*/64).uint64(message.episodeIndex);
            if (message.terminalRewards != null && message.terminalRewards.length) {
                writer.uint32(/* id 9, wireType 2 =*/74).fork();
                for (var i = 0; i < message.terminalRewards.length; ++i)
                    writer.float(message.terminalRewards[i]);
                writer.ldelim();
            }
            if (message.terminalOutcome != null && Object.hasOwnProperty.call(message, "terminalOutcome"))
                $root.game.RoundOutcome.encode(message.terminalOutcome, writer.uint32(/* id 10, wireType 2 =*/82).fork()).ldelim();
            return writer;
        };

        /**
         * Encodes the specified TrajectorySample message, length delimited. Does not implicitly {@link game.TrajectorySample.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.TrajectorySample
         * @static
         * @param {game.ITrajectorySample} message TrajectorySample message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        TrajectorySample.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a TrajectorySample message from the specified reader or buffer.
         * @function decode
         * @memberof game.TrajectorySample
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.TrajectorySample} TrajectorySample
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        TrajectorySample.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.TrajectorySample();
            while (reader.pos < end) {
                var tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.observation = $root.game.SeatObservation.decode(reader, reader.uint32());
                        break;
                    }
                case 2: {
                        message.actionId = reader.uint32();
                        break;
                    }
                case 3: {
                        if (!(message.rewards && message.rewards.length))
                            message.rewards = [];
                        if ((tag & 7) === 2) {
                            var end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.rewards.push(reader.float());
                        } else
                            message.rewards.push(reader.float());
                        break;
                    }
                case 4: {
                        message.nextObservation = $root.game.SeatObservation.decode(reader, reader.uint32());
                        break;
                    }
                case 5: {
                        message.terminated = reader.bool();
                        break;
                    }
                case 6: {
                        message.truncated = reader.bool();
                        break;
                    }
                case 7: {
                        message.actingSeat = reader.uint32();
                        break;
                    }
                case 8: {
                        message.episodeIndex = reader.uint64();
                        break;
                    }
                case 9: {
                        if (!(message.terminalRewards && message.terminalRewards.length))
                            message.terminalRewards = [];
                        if ((tag & 7) === 2) {
                            var end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.terminalRewards.push(reader.float());
                        } else
                            message.terminalRewards.push(reader.float());
                        break;
                    }
                case 10: {
                        message.terminalOutcome = $root.game.RoundOutcome.decode(reader, reader.uint32());
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
         * Decodes a TrajectorySample message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.TrajectorySample
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.TrajectorySample} TrajectorySample
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        TrajectorySample.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a TrajectorySample message.
         * @function verify
         * @memberof game.TrajectorySample
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        TrajectorySample.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.observation != null && message.hasOwnProperty("observation")) {
                var error = $root.game.SeatObservation.verify(message.observation);
                if (error)
                    return "observation." + error;
            }
            if (message.actionId != null && message.hasOwnProperty("actionId"))
                if (!$util.isInteger(message.actionId))
                    return "actionId: integer expected";
            if (message.rewards != null && message.hasOwnProperty("rewards")) {
                if (!Array.isArray(message.rewards))
                    return "rewards: array expected";
                for (var i = 0; i < message.rewards.length; ++i)
                    if (typeof message.rewards[i] !== "number")
                        return "rewards: number[] expected";
            }
            if (message.nextObservation != null && message.hasOwnProperty("nextObservation")) {
                var error = $root.game.SeatObservation.verify(message.nextObservation);
                if (error)
                    return "nextObservation." + error;
            }
            if (message.terminated != null && message.hasOwnProperty("terminated"))
                if (typeof message.terminated !== "boolean")
                    return "terminated: boolean expected";
            if (message.truncated != null && message.hasOwnProperty("truncated"))
                if (typeof message.truncated !== "boolean")
                    return "truncated: boolean expected";
            if (message.actingSeat != null && message.hasOwnProperty("actingSeat"))
                if (!$util.isInteger(message.actingSeat))
                    return "actingSeat: integer expected";
            if (message.episodeIndex != null && message.hasOwnProperty("episodeIndex"))
                if (!$util.isInteger(message.episodeIndex) && !(message.episodeIndex && $util.isInteger(message.episodeIndex.low) && $util.isInteger(message.episodeIndex.high)))
                    return "episodeIndex: integer|Long expected";
            if (message.terminalRewards != null && message.hasOwnProperty("terminalRewards")) {
                if (!Array.isArray(message.terminalRewards))
                    return "terminalRewards: array expected";
                for (var i = 0; i < message.terminalRewards.length; ++i)
                    if (typeof message.terminalRewards[i] !== "number")
                        return "terminalRewards: number[] expected";
            }
            if (message.terminalOutcome != null && message.hasOwnProperty("terminalOutcome")) {
                var error = $root.game.RoundOutcome.verify(message.terminalOutcome);
                if (error)
                    return "terminalOutcome." + error;
            }
            return null;
        };

        /**
         * Creates a TrajectorySample message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.TrajectorySample
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.TrajectorySample} TrajectorySample
         */
        TrajectorySample.fromObject = function fromObject(object) {
            if (object instanceof $root.game.TrajectorySample)
                return object;
            var message = new $root.game.TrajectorySample();
            if (object.observation != null) {
                if (typeof object.observation !== "object")
                    throw TypeError(".game.TrajectorySample.observation: object expected");
                message.observation = $root.game.SeatObservation.fromObject(object.observation);
            }
            if (object.actionId != null)
                message.actionId = object.actionId >>> 0;
            if (object.rewards) {
                if (!Array.isArray(object.rewards))
                    throw TypeError(".game.TrajectorySample.rewards: array expected");
                message.rewards = [];
                for (var i = 0; i < object.rewards.length; ++i)
                    message.rewards[i] = Number(object.rewards[i]);
            }
            if (object.nextObservation != null) {
                if (typeof object.nextObservation !== "object")
                    throw TypeError(".game.TrajectorySample.nextObservation: object expected");
                message.nextObservation = $root.game.SeatObservation.fromObject(object.nextObservation);
            }
            if (object.terminated != null)
                message.terminated = Boolean(object.terminated);
            if (object.truncated != null)
                message.truncated = Boolean(object.truncated);
            if (object.actingSeat != null)
                message.actingSeat = object.actingSeat >>> 0;
            if (object.episodeIndex != null)
                if ($util.Long)
                    (message.episodeIndex = $util.Long.fromValue(object.episodeIndex)).unsigned = true;
                else if (typeof object.episodeIndex === "string")
                    message.episodeIndex = parseInt(object.episodeIndex, 10);
                else if (typeof object.episodeIndex === "number")
                    message.episodeIndex = object.episodeIndex;
                else if (typeof object.episodeIndex === "object")
                    message.episodeIndex = new $util.LongBits(object.episodeIndex.low >>> 0, object.episodeIndex.high >>> 0).toNumber(true);
            if (object.terminalRewards) {
                if (!Array.isArray(object.terminalRewards))
                    throw TypeError(".game.TrajectorySample.terminalRewards: array expected");
                message.terminalRewards = [];
                for (var i = 0; i < object.terminalRewards.length; ++i)
                    message.terminalRewards[i] = Number(object.terminalRewards[i]);
            }
            if (object.terminalOutcome != null) {
                if (typeof object.terminalOutcome !== "object")
                    throw TypeError(".game.TrajectorySample.terminalOutcome: object expected");
                message.terminalOutcome = $root.game.RoundOutcome.fromObject(object.terminalOutcome);
            }
            return message;
        };

        /**
         * Creates a plain object from a TrajectorySample message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.TrajectorySample
         * @static
         * @param {game.TrajectorySample} message TrajectorySample
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        TrajectorySample.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.arrays || options.defaults) {
                object.rewards = [];
                object.terminalRewards = [];
            }
            if (options.defaults) {
                object.observation = null;
                object.actionId = 0;
                object.nextObservation = null;
                object.terminated = false;
                object.truncated = false;
                object.actingSeat = 0;
                if ($util.Long) {
                    var long = new $util.Long(0, 0, true);
                    object.episodeIndex = options.longs === String ? long.toString() : options.longs === Number ? long.toNumber() : long;
                } else
                    object.episodeIndex = options.longs === String ? "0" : 0;
                object.terminalOutcome = null;
            }
            if (message.observation != null && message.hasOwnProperty("observation"))
                object.observation = $root.game.SeatObservation.toObject(message.observation, options);
            if (message.actionId != null && message.hasOwnProperty("actionId"))
                object.actionId = message.actionId;
            if (message.rewards && message.rewards.length) {
                object.rewards = [];
                for (var j = 0; j < message.rewards.length; ++j)
                    object.rewards[j] = options.json && !isFinite(message.rewards[j]) ? String(message.rewards[j]) : message.rewards[j];
            }
            if (message.nextObservation != null && message.hasOwnProperty("nextObservation"))
                object.nextObservation = $root.game.SeatObservation.toObject(message.nextObservation, options);
            if (message.terminated != null && message.hasOwnProperty("terminated"))
                object.terminated = message.terminated;
            if (message.truncated != null && message.hasOwnProperty("truncated"))
                object.truncated = message.truncated;
            if (message.actingSeat != null && message.hasOwnProperty("actingSeat"))
                object.actingSeat = message.actingSeat;
            if (message.episodeIndex != null && message.hasOwnProperty("episodeIndex"))
                if (typeof message.episodeIndex === "number")
                    object.episodeIndex = options.longs === String ? String(message.episodeIndex) : message.episodeIndex;
                else
                    object.episodeIndex = options.longs === String ? $util.Long.prototype.toString.call(message.episodeIndex) : options.longs === Number ? new $util.LongBits(message.episodeIndex.low >>> 0, message.episodeIndex.high >>> 0).toNumber(true) : message.episodeIndex;
            if (message.terminalRewards && message.terminalRewards.length) {
                object.terminalRewards = [];
                for (var j = 0; j < message.terminalRewards.length; ++j)
                    object.terminalRewards[j] = options.json && !isFinite(message.terminalRewards[j]) ? String(message.terminalRewards[j]) : message.terminalRewards[j];
            }
            if (message.terminalOutcome != null && message.hasOwnProperty("terminalOutcome"))
                object.terminalOutcome = $root.game.RoundOutcome.toObject(message.terminalOutcome, options);
            return object;
        };

        /**
         * Converts this TrajectorySample to JSON.
         * @function toJSON
         * @memberof game.TrajectorySample
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        TrajectorySample.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for TrajectorySample
         * @function getTypeUrl
         * @memberof game.TrajectorySample
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        TrajectorySample.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.TrajectorySample";
        };

        return TrajectorySample;
    })();

    game.TrajectoryDataset = (function() {

        /**
         * Properties of a TrajectoryDataset.
         * @memberof game
         * @interface ITrajectoryDataset
         * @property {Array.<game.ITrajectorySample>|undefined} [samples] TrajectoryDataset samples
         */

        /**
         * Constructs a new TrajectoryDataset.
         * @memberof game
         * @classdesc Represents a TrajectoryDataset.
         * @implements ITrajectoryDataset
         * @constructor
         * @param {game.ITrajectoryDataset=} [properties] Properties to set
         */
        function TrajectoryDataset(properties) {
            this.samples = [];
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * TrajectoryDataset samples.
         * @member {Array.<game.TrajectorySample>} samples
         * @memberof game.TrajectoryDataset
         * @instance
         */
        TrajectoryDataset.prototype.samples = $util.emptyArray;

        /**
         * Creates a new TrajectoryDataset instance using the specified properties.
         * @function create
         * @memberof game.TrajectoryDataset
         * @static
         * @param {game.ITrajectoryDataset=} [properties] Properties to set
         * @returns {game.TrajectoryDataset} TrajectoryDataset instance
         */
        TrajectoryDataset.create = function create(properties) {
            return new TrajectoryDataset(properties);
        };

        /**
         * Encodes the specified TrajectoryDataset message. Does not implicitly {@link game.TrajectoryDataset.verify|verify} messages.
         * @function encode
         * @memberof game.TrajectoryDataset
         * @static
         * @param {game.ITrajectoryDataset} message TrajectoryDataset message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        TrajectoryDataset.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.samples != null && message.samples.length)
                for (var i = 0; i < message.samples.length; ++i)
                    $root.game.TrajectorySample.encode(message.samples[i], writer.uint32(/* id 1, wireType 2 =*/10).fork()).ldelim();
            return writer;
        };

        /**
         * Encodes the specified TrajectoryDataset message, length delimited. Does not implicitly {@link game.TrajectoryDataset.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.TrajectoryDataset
         * @static
         * @param {game.ITrajectoryDataset} message TrajectoryDataset message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        TrajectoryDataset.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a TrajectoryDataset message from the specified reader or buffer.
         * @function decode
         * @memberof game.TrajectoryDataset
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.TrajectoryDataset} TrajectoryDataset
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        TrajectoryDataset.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.TrajectoryDataset();
            while (reader.pos < end) {
                var tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        if (!(message.samples && message.samples.length))
                            message.samples = [];
                        message.samples.push($root.game.TrajectorySample.decode(reader, reader.uint32()));
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
         * Decodes a TrajectoryDataset message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.TrajectoryDataset
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.TrajectoryDataset} TrajectoryDataset
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        TrajectoryDataset.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a TrajectoryDataset message.
         * @function verify
         * @memberof game.TrajectoryDataset
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        TrajectoryDataset.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.samples != null && message.hasOwnProperty("samples")) {
                if (!Array.isArray(message.samples))
                    return "samples: array expected";
                for (var i = 0; i < message.samples.length; ++i) {
                    var error = $root.game.TrajectorySample.verify(message.samples[i]);
                    if (error)
                        return "samples." + error;
                }
            }
            return null;
        };

        /**
         * Creates a TrajectoryDataset message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.TrajectoryDataset
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.TrajectoryDataset} TrajectoryDataset
         */
        TrajectoryDataset.fromObject = function fromObject(object) {
            if (object instanceof $root.game.TrajectoryDataset)
                return object;
            var message = new $root.game.TrajectoryDataset();
            if (object.samples) {
                if (!Array.isArray(object.samples))
                    throw TypeError(".game.TrajectoryDataset.samples: array expected");
                message.samples = [];
                for (var i = 0; i < object.samples.length; ++i) {
                    if (typeof object.samples[i] !== "object")
                        throw TypeError(".game.TrajectoryDataset.samples: object expected");
                    message.samples[i] = $root.game.TrajectorySample.fromObject(object.samples[i]);
                }
            }
            return message;
        };

        /**
         * Creates a plain object from a TrajectoryDataset message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.TrajectoryDataset
         * @static
         * @param {game.TrajectoryDataset} message TrajectoryDataset
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        TrajectoryDataset.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.arrays || options.defaults)
                object.samples = [];
            if (message.samples && message.samples.length) {
                object.samples = [];
                for (var j = 0; j < message.samples.length; ++j)
                    object.samples[j] = $root.game.TrajectorySample.toObject(message.samples[j], options);
            }
            return object;
        };

        /**
         * Converts this TrajectoryDataset to JSON.
         * @function toJSON
         * @memberof game.TrajectoryDataset
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        TrajectoryDataset.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for TrajectoryDataset
         * @function getTypeUrl
         * @memberof game.TrajectoryDataset
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        TrajectoryDataset.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.TrajectoryDataset";
        };

        return TrajectoryDataset;
    })();

    /**
     * Difficulty enum.
     * @name game.Difficulty
     * @enum {number}
     * @property {number} DIFFICULTY_UNSPECIFIED=0 DIFFICULTY_UNSPECIFIED value
     * @property {number} DIFFICULTY_HEURISTIC=1 DIFFICULTY_HEURISTIC value
     */
    game.Difficulty = (function() {
        var valuesById = {}, values = Object.create(valuesById);
        values[valuesById[0] = "DIFFICULTY_UNSPECIFIED"] = 0;
        values[valuesById[1] = "DIFFICULTY_HEURISTIC"] = 1;
        return values;
    })();

    game.SeatConfig = (function() {

        /**
         * Properties of a SeatConfig.
         * @memberof game
         * @interface ISeatConfig
         * @property {string|undefined} [kind] SeatConfig kind
         * @property {number|undefined} [userId] SeatConfig userId
         * @property {string|undefined} [username] SeatConfig username
         * @property {game.Difficulty|undefined} [difficulty] SeatConfig difficulty
         */

        /**
         * Constructs a new SeatConfig.
         * @memberof game
         * @classdesc Represents a SeatConfig.
         * @implements ISeatConfig
         * @constructor
         * @param {game.ISeatConfig=} [properties] Properties to set
         */
        function SeatConfig(properties) {
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * SeatConfig kind.
         * @member {string} kind
         * @memberof game.SeatConfig
         * @instance
         */
        SeatConfig.prototype.kind = "";

        /**
         * SeatConfig userId.
         * @member {number} userId
         * @memberof game.SeatConfig
         * @instance
         */
        SeatConfig.prototype.userId = 0;

        /**
         * SeatConfig username.
         * @member {string} username
         * @memberof game.SeatConfig
         * @instance
         */
        SeatConfig.prototype.username = "";

        /**
         * SeatConfig difficulty.
         * @member {game.Difficulty} difficulty
         * @memberof game.SeatConfig
         * @instance
         */
        SeatConfig.prototype.difficulty = 0;

        /**
         * Creates a new SeatConfig instance using the specified properties.
         * @function create
         * @memberof game.SeatConfig
         * @static
         * @param {game.ISeatConfig=} [properties] Properties to set
         * @returns {game.SeatConfig} SeatConfig instance
         */
        SeatConfig.create = function create(properties) {
            return new SeatConfig(properties);
        };

        /**
         * Encodes the specified SeatConfig message. Does not implicitly {@link game.SeatConfig.verify|verify} messages.
         * @function encode
         * @memberof game.SeatConfig
         * @static
         * @param {game.ISeatConfig} message SeatConfig message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        SeatConfig.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.kind != null && Object.hasOwnProperty.call(message, "kind"))
                writer.uint32(/* id 1, wireType 2 =*/10).string(message.kind);
            if (message.userId != null && Object.hasOwnProperty.call(message, "userId"))
                writer.uint32(/* id 2, wireType 0 =*/16).uint32(message.userId);
            if (message.username != null && Object.hasOwnProperty.call(message, "username"))
                writer.uint32(/* id 3, wireType 2 =*/26).string(message.username);
            if (message.difficulty != null && Object.hasOwnProperty.call(message, "difficulty"))
                writer.uint32(/* id 4, wireType 0 =*/32).int32(message.difficulty);
            return writer;
        };

        /**
         * Encodes the specified SeatConfig message, length delimited. Does not implicitly {@link game.SeatConfig.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.SeatConfig
         * @static
         * @param {game.ISeatConfig} message SeatConfig message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        SeatConfig.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a SeatConfig message from the specified reader or buffer.
         * @function decode
         * @memberof game.SeatConfig
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.SeatConfig} SeatConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        SeatConfig.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.SeatConfig();
            while (reader.pos < end) {
                var tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.kind = reader.string();
                        break;
                    }
                case 2: {
                        message.userId = reader.uint32();
                        break;
                    }
                case 3: {
                        message.username = reader.string();
                        break;
                    }
                case 4: {
                        message.difficulty = reader.int32();
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
         * Decodes a SeatConfig message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.SeatConfig
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.SeatConfig} SeatConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        SeatConfig.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a SeatConfig message.
         * @function verify
         * @memberof game.SeatConfig
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        SeatConfig.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.kind != null && message.hasOwnProperty("kind"))
                if (!$util.isString(message.kind))
                    return "kind: string expected";
            if (message.userId != null && message.hasOwnProperty("userId"))
                if (!$util.isInteger(message.userId))
                    return "userId: integer expected";
            if (message.username != null && message.hasOwnProperty("username"))
                if (!$util.isString(message.username))
                    return "username: string expected";
            if (message.difficulty != null && message.hasOwnProperty("difficulty"))
                switch (message.difficulty) {
                default:
                    return "difficulty: enum value expected";
                case 0:
                case 1:
                    break;
                }
            return null;
        };

        /**
         * Creates a SeatConfig message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.SeatConfig
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.SeatConfig} SeatConfig
         */
        SeatConfig.fromObject = function fromObject(object) {
            if (object instanceof $root.game.SeatConfig)
                return object;
            var message = new $root.game.SeatConfig();
            if (object.kind != null)
                message.kind = String(object.kind);
            if (object.userId != null)
                message.userId = object.userId >>> 0;
            if (object.username != null)
                message.username = String(object.username);
            switch (object.difficulty) {
            default:
                if (typeof object.difficulty === "number") {
                    message.difficulty = object.difficulty;
                    break;
                }
                break;
            case "DIFFICULTY_UNSPECIFIED":
            case 0:
                message.difficulty = 0;
                break;
            case "DIFFICULTY_HEURISTIC":
            case 1:
                message.difficulty = 1;
                break;
            }
            return message;
        };

        /**
         * Creates a plain object from a SeatConfig message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.SeatConfig
         * @static
         * @param {game.SeatConfig} message SeatConfig
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        SeatConfig.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.defaults) {
                object.kind = "";
                object.userId = 0;
                object.username = "";
                object.difficulty = options.enums === String ? "DIFFICULTY_UNSPECIFIED" : 0;
            }
            if (message.kind != null && message.hasOwnProperty("kind"))
                object.kind = message.kind;
            if (message.userId != null && message.hasOwnProperty("userId"))
                object.userId = message.userId;
            if (message.username != null && message.hasOwnProperty("username"))
                object.username = message.username;
            if (message.difficulty != null && message.hasOwnProperty("difficulty"))
                object.difficulty = options.enums === String ? $root.game.Difficulty[message.difficulty] === undefined ? message.difficulty : $root.game.Difficulty[message.difficulty] : message.difficulty;
            return object;
        };

        /**
         * Converts this SeatConfig to JSON.
         * @function toJSON
         * @memberof game.SeatConfig
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        SeatConfig.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for SeatConfig
         * @function getTypeUrl
         * @memberof game.SeatConfig
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        SeatConfig.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.SeatConfig";
        };

        return SeatConfig;
    })();

    game.PrivateTableState = (function() {

        /**
         * Properties of a PrivateTableState.
         * @memberof game
         * @interface IPrivateTableState
         * @property {string|undefined} [tableId] PrivateTableState tableId
         * @property {number|undefined} [hostUserId] PrivateTableState hostUserId
         * @property {Array.<game.ISeatConfig>|undefined} [seats] PrivateTableState seats
         * @property {string|undefined} [state] PrivateTableState state
         * @property {string|undefined} [matchId] PrivateTableState matchId
         * @property {game.MatchMode|undefined} [matchMode] PrivateTableState matchMode
         * @property {game.IChongciConfig|undefined} [chongciConfig] PrivateTableState chongciConfig
         */

        /**
         * Constructs a new PrivateTableState.
         * @memberof game
         * @classdesc Represents a PrivateTableState.
         * @implements IPrivateTableState
         * @constructor
         * @param {game.IPrivateTableState=} [properties] Properties to set
         */
        function PrivateTableState(properties) {
            this.seats = [];
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * PrivateTableState tableId.
         * @member {string} tableId
         * @memberof game.PrivateTableState
         * @instance
         */
        PrivateTableState.prototype.tableId = "";

        /**
         * PrivateTableState hostUserId.
         * @member {number} hostUserId
         * @memberof game.PrivateTableState
         * @instance
         */
        PrivateTableState.prototype.hostUserId = 0;

        /**
         * PrivateTableState seats.
         * @member {Array.<game.SeatConfig>} seats
         * @memberof game.PrivateTableState
         * @instance
         */
        PrivateTableState.prototype.seats = $util.emptyArray;

        /**
         * PrivateTableState state.
         * @member {string} state
         * @memberof game.PrivateTableState
         * @instance
         */
        PrivateTableState.prototype.state = "";

        /**
         * PrivateTableState matchId.
         * @member {string} matchId
         * @memberof game.PrivateTableState
         * @instance
         */
        PrivateTableState.prototype.matchId = "";

        /**
         * PrivateTableState matchMode.
         * @member {game.MatchMode} matchMode
         * @memberof game.PrivateTableState
         * @instance
         */
        PrivateTableState.prototype.matchMode = 0;

        /**
         * PrivateTableState chongciConfig.
         * @member {game.ChongciConfig} chongciConfig
         * @memberof game.PrivateTableState
         * @instance
         */
        PrivateTableState.prototype.chongciConfig = null;

        /**
         * Creates a new PrivateTableState instance using the specified properties.
         * @function create
         * @memberof game.PrivateTableState
         * @static
         * @param {game.IPrivateTableState=} [properties] Properties to set
         * @returns {game.PrivateTableState} PrivateTableState instance
         */
        PrivateTableState.create = function create(properties) {
            return new PrivateTableState(properties);
        };

        /**
         * Encodes the specified PrivateTableState message. Does not implicitly {@link game.PrivateTableState.verify|verify} messages.
         * @function encode
         * @memberof game.PrivateTableState
         * @static
         * @param {game.IPrivateTableState} message PrivateTableState message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PrivateTableState.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.tableId != null && Object.hasOwnProperty.call(message, "tableId"))
                writer.uint32(/* id 1, wireType 2 =*/10).string(message.tableId);
            if (message.hostUserId != null && Object.hasOwnProperty.call(message, "hostUserId"))
                writer.uint32(/* id 2, wireType 0 =*/16).uint32(message.hostUserId);
            if (message.seats != null && message.seats.length)
                for (var i = 0; i < message.seats.length; ++i)
                    $root.game.SeatConfig.encode(message.seats[i], writer.uint32(/* id 3, wireType 2 =*/26).fork()).ldelim();
            if (message.state != null && Object.hasOwnProperty.call(message, "state"))
                writer.uint32(/* id 4, wireType 2 =*/34).string(message.state);
            if (message.matchId != null && Object.hasOwnProperty.call(message, "matchId"))
                writer.uint32(/* id 5, wireType 2 =*/42).string(message.matchId);
            if (message.matchMode != null && Object.hasOwnProperty.call(message, "matchMode"))
                writer.uint32(/* id 6, wireType 0 =*/48).int32(message.matchMode);
            if (message.chongciConfig != null && Object.hasOwnProperty.call(message, "chongciConfig"))
                $root.game.ChongciConfig.encode(message.chongciConfig, writer.uint32(/* id 7, wireType 2 =*/58).fork()).ldelim();
            return writer;
        };

        /**
         * Encodes the specified PrivateTableState message, length delimited. Does not implicitly {@link game.PrivateTableState.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.PrivateTableState
         * @static
         * @param {game.IPrivateTableState} message PrivateTableState message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PrivateTableState.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a PrivateTableState message from the specified reader or buffer.
         * @function decode
         * @memberof game.PrivateTableState
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.PrivateTableState} PrivateTableState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PrivateTableState.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.PrivateTableState();
            while (reader.pos < end) {
                var tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.tableId = reader.string();
                        break;
                    }
                case 2: {
                        message.hostUserId = reader.uint32();
                        break;
                    }
                case 3: {
                        if (!(message.seats && message.seats.length))
                            message.seats = [];
                        message.seats.push($root.game.SeatConfig.decode(reader, reader.uint32()));
                        break;
                    }
                case 4: {
                        message.state = reader.string();
                        break;
                    }
                case 5: {
                        message.matchId = reader.string();
                        break;
                    }
                case 6: {
                        message.matchMode = reader.int32();
                        break;
                    }
                case 7: {
                        message.chongciConfig = $root.game.ChongciConfig.decode(reader, reader.uint32());
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
         * Decodes a PrivateTableState message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.PrivateTableState
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.PrivateTableState} PrivateTableState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PrivateTableState.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a PrivateTableState message.
         * @function verify
         * @memberof game.PrivateTableState
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        PrivateTableState.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.tableId != null && message.hasOwnProperty("tableId"))
                if (!$util.isString(message.tableId))
                    return "tableId: string expected";
            if (message.hostUserId != null && message.hasOwnProperty("hostUserId"))
                if (!$util.isInteger(message.hostUserId))
                    return "hostUserId: integer expected";
            if (message.seats != null && message.hasOwnProperty("seats")) {
                if (!Array.isArray(message.seats))
                    return "seats: array expected";
                for (var i = 0; i < message.seats.length; ++i) {
                    var error = $root.game.SeatConfig.verify(message.seats[i]);
                    if (error)
                        return "seats." + error;
                }
            }
            if (message.state != null && message.hasOwnProperty("state"))
                if (!$util.isString(message.state))
                    return "state: string expected";
            if (message.matchId != null && message.hasOwnProperty("matchId"))
                if (!$util.isString(message.matchId))
                    return "matchId: string expected";
            if (message.matchMode != null && message.hasOwnProperty("matchMode"))
                switch (message.matchMode) {
                default:
                    return "matchMode: enum value expected";
                case 0:
                case 1:
                case 2:
                    break;
                }
            if (message.chongciConfig != null && message.hasOwnProperty("chongciConfig")) {
                var error = $root.game.ChongciConfig.verify(message.chongciConfig);
                if (error)
                    return "chongciConfig." + error;
            }
            return null;
        };

        /**
         * Creates a PrivateTableState message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.PrivateTableState
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.PrivateTableState} PrivateTableState
         */
        PrivateTableState.fromObject = function fromObject(object) {
            if (object instanceof $root.game.PrivateTableState)
                return object;
            var message = new $root.game.PrivateTableState();
            if (object.tableId != null)
                message.tableId = String(object.tableId);
            if (object.hostUserId != null)
                message.hostUserId = object.hostUserId >>> 0;
            if (object.seats) {
                if (!Array.isArray(object.seats))
                    throw TypeError(".game.PrivateTableState.seats: array expected");
                message.seats = [];
                for (var i = 0; i < object.seats.length; ++i) {
                    if (typeof object.seats[i] !== "object")
                        throw TypeError(".game.PrivateTableState.seats: object expected");
                    message.seats[i] = $root.game.SeatConfig.fromObject(object.seats[i]);
                }
            }
            if (object.state != null)
                message.state = String(object.state);
            if (object.matchId != null)
                message.matchId = String(object.matchId);
            switch (object.matchMode) {
            default:
                if (typeof object.matchMode === "number") {
                    message.matchMode = object.matchMode;
                    break;
                }
                break;
            case "MATCH_MODE_UNSPECIFIED":
            case 0:
                message.matchMode = 0;
                break;
            case "MATCH_MODE_CLASSIC":
            case 1:
                message.matchMode = 1;
                break;
            case "MATCH_MODE_CHONGCI":
            case 2:
                message.matchMode = 2;
                break;
            }
            if (object.chongciConfig != null) {
                if (typeof object.chongciConfig !== "object")
                    throw TypeError(".game.PrivateTableState.chongciConfig: object expected");
                message.chongciConfig = $root.game.ChongciConfig.fromObject(object.chongciConfig);
            }
            return message;
        };

        /**
         * Creates a plain object from a PrivateTableState message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.PrivateTableState
         * @static
         * @param {game.PrivateTableState} message PrivateTableState
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        PrivateTableState.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.arrays || options.defaults)
                object.seats = [];
            if (options.defaults) {
                object.tableId = "";
                object.hostUserId = 0;
                object.state = "";
                object.matchId = "";
                object.matchMode = options.enums === String ? "MATCH_MODE_UNSPECIFIED" : 0;
                object.chongciConfig = null;
            }
            if (message.tableId != null && message.hasOwnProperty("tableId"))
                object.tableId = message.tableId;
            if (message.hostUserId != null && message.hasOwnProperty("hostUserId"))
                object.hostUserId = message.hostUserId;
            if (message.seats && message.seats.length) {
                object.seats = [];
                for (var j = 0; j < message.seats.length; ++j)
                    object.seats[j] = $root.game.SeatConfig.toObject(message.seats[j], options);
            }
            if (message.state != null && message.hasOwnProperty("state"))
                object.state = message.state;
            if (message.matchId != null && message.hasOwnProperty("matchId"))
                object.matchId = message.matchId;
            if (message.matchMode != null && message.hasOwnProperty("matchMode"))
                object.matchMode = options.enums === String ? $root.game.MatchMode[message.matchMode] === undefined ? message.matchMode : $root.game.MatchMode[message.matchMode] : message.matchMode;
            if (message.chongciConfig != null && message.hasOwnProperty("chongciConfig"))
                object.chongciConfig = $root.game.ChongciConfig.toObject(message.chongciConfig, options);
            return object;
        };

        /**
         * Converts this PrivateTableState to JSON.
         * @function toJSON
         * @memberof game.PrivateTableState
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        PrivateTableState.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for PrivateTableState
         * @function getTypeUrl
         * @memberof game.PrivateTableState
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        PrivateTableState.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.PrivateTableState";
        };

        return PrivateTableState;
    })();

    /**
     * MatchMode enum.
     * @name game.MatchMode
     * @enum {number}
     * @property {number} MATCH_MODE_UNSPECIFIED=0 MATCH_MODE_UNSPECIFIED value
     * @property {number} MATCH_MODE_CLASSIC=1 MATCH_MODE_CLASSIC value
     * @property {number} MATCH_MODE_CHONGCI=2 MATCH_MODE_CHONGCI value
     */
    game.MatchMode = (function() {
        var valuesById = {}, values = Object.create(valuesById);
        values[valuesById[0] = "MATCH_MODE_UNSPECIFIED"] = 0;
        values[valuesById[1] = "MATCH_MODE_CLASSIC"] = 1;
        values[valuesById[2] = "MATCH_MODE_CHONGCI"] = 2;
        return values;
    })();

    game.ChongciConfig = (function() {

        /**
         * Properties of a ChongciConfig.
         * @memberof game
         * @interface IChongciConfig
         * @property {number|undefined} [startingScore] ChongciConfig startingScore
         * @property {number|undefined} [bustThreshold] ChongciConfig bustThreshold
         * @property {number|undefined} [maxHands] ChongciConfig maxHands
         */

        /**
         * Constructs a new ChongciConfig.
         * @memberof game
         * @classdesc Represents a ChongciConfig.
         * @implements IChongciConfig
         * @constructor
         * @param {game.IChongciConfig=} [properties] Properties to set
         */
        function ChongciConfig(properties) {
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * ChongciConfig startingScore.
         * @member {number} startingScore
         * @memberof game.ChongciConfig
         * @instance
         */
        ChongciConfig.prototype.startingScore = 0;

        /**
         * ChongciConfig bustThreshold.
         * @member {number} bustThreshold
         * @memberof game.ChongciConfig
         * @instance
         */
        ChongciConfig.prototype.bustThreshold = 0;

        /**
         * ChongciConfig maxHands.
         * @member {number} maxHands
         * @memberof game.ChongciConfig
         * @instance
         */
        ChongciConfig.prototype.maxHands = 0;

        /**
         * Creates a new ChongciConfig instance using the specified properties.
         * @function create
         * @memberof game.ChongciConfig
         * @static
         * @param {game.IChongciConfig=} [properties] Properties to set
         * @returns {game.ChongciConfig} ChongciConfig instance
         */
        ChongciConfig.create = function create(properties) {
            return new ChongciConfig(properties);
        };

        /**
         * Encodes the specified ChongciConfig message. Does not implicitly {@link game.ChongciConfig.verify|verify} messages.
         * @function encode
         * @memberof game.ChongciConfig
         * @static
         * @param {game.IChongciConfig} message ChongciConfig message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        ChongciConfig.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.startingScore != null && Object.hasOwnProperty.call(message, "startingScore"))
                writer.uint32(/* id 1, wireType 0 =*/8).int32(message.startingScore);
            if (message.bustThreshold != null && Object.hasOwnProperty.call(message, "bustThreshold"))
                writer.uint32(/* id 2, wireType 0 =*/16).int32(message.bustThreshold);
            if (message.maxHands != null && Object.hasOwnProperty.call(message, "maxHands"))
                writer.uint32(/* id 3, wireType 0 =*/24).uint32(message.maxHands);
            return writer;
        };

        /**
         * Encodes the specified ChongciConfig message, length delimited. Does not implicitly {@link game.ChongciConfig.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.ChongciConfig
         * @static
         * @param {game.IChongciConfig} message ChongciConfig message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        ChongciConfig.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a ChongciConfig message from the specified reader or buffer.
         * @function decode
         * @memberof game.ChongciConfig
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.ChongciConfig} ChongciConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        ChongciConfig.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.ChongciConfig();
            while (reader.pos < end) {
                var tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.startingScore = reader.int32();
                        break;
                    }
                case 2: {
                        message.bustThreshold = reader.int32();
                        break;
                    }
                case 3: {
                        message.maxHands = reader.uint32();
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
         * Decodes a ChongciConfig message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.ChongciConfig
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.ChongciConfig} ChongciConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        ChongciConfig.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a ChongciConfig message.
         * @function verify
         * @memberof game.ChongciConfig
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        ChongciConfig.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.startingScore != null && message.hasOwnProperty("startingScore"))
                if (!$util.isInteger(message.startingScore))
                    return "startingScore: integer expected";
            if (message.bustThreshold != null && message.hasOwnProperty("bustThreshold"))
                if (!$util.isInteger(message.bustThreshold))
                    return "bustThreshold: integer expected";
            if (message.maxHands != null && message.hasOwnProperty("maxHands"))
                if (!$util.isInteger(message.maxHands))
                    return "maxHands: integer expected";
            return null;
        };

        /**
         * Creates a ChongciConfig message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.ChongciConfig
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.ChongciConfig} ChongciConfig
         */
        ChongciConfig.fromObject = function fromObject(object) {
            if (object instanceof $root.game.ChongciConfig)
                return object;
            var message = new $root.game.ChongciConfig();
            if (object.startingScore != null)
                message.startingScore = object.startingScore | 0;
            if (object.bustThreshold != null)
                message.bustThreshold = object.bustThreshold | 0;
            if (object.maxHands != null)
                message.maxHands = object.maxHands >>> 0;
            return message;
        };

        /**
         * Creates a plain object from a ChongciConfig message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.ChongciConfig
         * @static
         * @param {game.ChongciConfig} message ChongciConfig
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        ChongciConfig.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.defaults) {
                object.startingScore = 0;
                object.bustThreshold = 0;
                object.maxHands = 0;
            }
            if (message.startingScore != null && message.hasOwnProperty("startingScore"))
                object.startingScore = message.startingScore;
            if (message.bustThreshold != null && message.hasOwnProperty("bustThreshold"))
                object.bustThreshold = message.bustThreshold;
            if (message.maxHands != null && message.hasOwnProperty("maxHands"))
                object.maxHands = message.maxHands;
            return object;
        };

        /**
         * Converts this ChongciConfig to JSON.
         * @function toJSON
         * @memberof game.ChongciConfig
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        ChongciConfig.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for ChongciConfig
         * @function getTypeUrl
         * @memberof game.ChongciConfig
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        ChongciConfig.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.ChongciConfig";
        };

        return ChongciConfig;
    })();

    game.PlayerStanding = (function() {

        /**
         * Properties of a PlayerStanding.
         * @memberof game
         * @interface IPlayerStanding
         * @property {number|undefined} [seat] PlayerStanding seat
         * @property {number|undefined} [rank] PlayerStanding rank
         * @property {number|undefined} [finalScore] PlayerStanding finalScore
         * @property {number|undefined} [netChange] PlayerStanding netChange
         */

        /**
         * Constructs a new PlayerStanding.
         * @memberof game
         * @classdesc Represents a PlayerStanding.
         * @implements IPlayerStanding
         * @constructor
         * @param {game.IPlayerStanding=} [properties] Properties to set
         */
        function PlayerStanding(properties) {
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * PlayerStanding seat.
         * @member {number} seat
         * @memberof game.PlayerStanding
         * @instance
         */
        PlayerStanding.prototype.seat = 0;

        /**
         * PlayerStanding rank.
         * @member {number} rank
         * @memberof game.PlayerStanding
         * @instance
         */
        PlayerStanding.prototype.rank = 0;

        /**
         * PlayerStanding finalScore.
         * @member {number} finalScore
         * @memberof game.PlayerStanding
         * @instance
         */
        PlayerStanding.prototype.finalScore = 0;

        /**
         * PlayerStanding netChange.
         * @member {number} netChange
         * @memberof game.PlayerStanding
         * @instance
         */
        PlayerStanding.prototype.netChange = 0;

        /**
         * Creates a new PlayerStanding instance using the specified properties.
         * @function create
         * @memberof game.PlayerStanding
         * @static
         * @param {game.IPlayerStanding=} [properties] Properties to set
         * @returns {game.PlayerStanding} PlayerStanding instance
         */
        PlayerStanding.create = function create(properties) {
            return new PlayerStanding(properties);
        };

        /**
         * Encodes the specified PlayerStanding message. Does not implicitly {@link game.PlayerStanding.verify|verify} messages.
         * @function encode
         * @memberof game.PlayerStanding
         * @static
         * @param {game.IPlayerStanding} message PlayerStanding message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PlayerStanding.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.seat != null && Object.hasOwnProperty.call(message, "seat"))
                writer.uint32(/* id 1, wireType 0 =*/8).uint32(message.seat);
            if (message.rank != null && Object.hasOwnProperty.call(message, "rank"))
                writer.uint32(/* id 2, wireType 0 =*/16).uint32(message.rank);
            if (message.finalScore != null && Object.hasOwnProperty.call(message, "finalScore"))
                writer.uint32(/* id 3, wireType 0 =*/24).int32(message.finalScore);
            if (message.netChange != null && Object.hasOwnProperty.call(message, "netChange"))
                writer.uint32(/* id 4, wireType 0 =*/32).int32(message.netChange);
            return writer;
        };

        /**
         * Encodes the specified PlayerStanding message, length delimited. Does not implicitly {@link game.PlayerStanding.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.PlayerStanding
         * @static
         * @param {game.IPlayerStanding} message PlayerStanding message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PlayerStanding.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a PlayerStanding message from the specified reader or buffer.
         * @function decode
         * @memberof game.PlayerStanding
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.PlayerStanding} PlayerStanding
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PlayerStanding.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.PlayerStanding();
            while (reader.pos < end) {
                var tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.seat = reader.uint32();
                        break;
                    }
                case 2: {
                        message.rank = reader.uint32();
                        break;
                    }
                case 3: {
                        message.finalScore = reader.int32();
                        break;
                    }
                case 4: {
                        message.netChange = reader.int32();
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
         * Decodes a PlayerStanding message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.PlayerStanding
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.PlayerStanding} PlayerStanding
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PlayerStanding.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a PlayerStanding message.
         * @function verify
         * @memberof game.PlayerStanding
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        PlayerStanding.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.seat != null && message.hasOwnProperty("seat"))
                if (!$util.isInteger(message.seat))
                    return "seat: integer expected";
            if (message.rank != null && message.hasOwnProperty("rank"))
                if (!$util.isInteger(message.rank))
                    return "rank: integer expected";
            if (message.finalScore != null && message.hasOwnProperty("finalScore"))
                if (!$util.isInteger(message.finalScore))
                    return "finalScore: integer expected";
            if (message.netChange != null && message.hasOwnProperty("netChange"))
                if (!$util.isInteger(message.netChange))
                    return "netChange: integer expected";
            return null;
        };

        /**
         * Creates a PlayerStanding message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.PlayerStanding
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.PlayerStanding} PlayerStanding
         */
        PlayerStanding.fromObject = function fromObject(object) {
            if (object instanceof $root.game.PlayerStanding)
                return object;
            var message = new $root.game.PlayerStanding();
            if (object.seat != null)
                message.seat = object.seat >>> 0;
            if (object.rank != null)
                message.rank = object.rank >>> 0;
            if (object.finalScore != null)
                message.finalScore = object.finalScore | 0;
            if (object.netChange != null)
                message.netChange = object.netChange | 0;
            return message;
        };

        /**
         * Creates a plain object from a PlayerStanding message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.PlayerStanding
         * @static
         * @param {game.PlayerStanding} message PlayerStanding
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        PlayerStanding.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.defaults) {
                object.seat = 0;
                object.rank = 0;
                object.finalScore = 0;
                object.netChange = 0;
            }
            if (message.seat != null && message.hasOwnProperty("seat"))
                object.seat = message.seat;
            if (message.rank != null && message.hasOwnProperty("rank"))
                object.rank = message.rank;
            if (message.finalScore != null && message.hasOwnProperty("finalScore"))
                object.finalScore = message.finalScore;
            if (message.netChange != null && message.hasOwnProperty("netChange"))
                object.netChange = message.netChange;
            return object;
        };

        /**
         * Converts this PlayerStanding to JSON.
         * @function toJSON
         * @memberof game.PlayerStanding
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        PlayerStanding.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for PlayerStanding
         * @function getTypeUrl
         * @memberof game.PlayerStanding
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        PlayerStanding.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.PlayerStanding";
        };

        return PlayerStanding;
    })();

    game.MatchEndResult = (function() {

        /**
         * Properties of a MatchEndResult.
         * @memberof game
         * @interface IMatchEndResult
         * @property {string|undefined} [reason] MatchEndResult reason
         * @property {number|undefined} [finalHandNum] MatchEndResult finalHandNum
         * @property {Array.<game.IPlayerStanding>|undefined} [standings] MatchEndResult standings
         */

        /**
         * Constructs a new MatchEndResult.
         * @memberof game
         * @classdesc Represents a MatchEndResult.
         * @implements IMatchEndResult
         * @constructor
         * @param {game.IMatchEndResult=} [properties] Properties to set
         */
        function MatchEndResult(properties) {
            this.standings = [];
            if (properties)
                for (var keys = Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null)
                        this[keys[i]] = properties[keys[i]];
        }

        /**
         * MatchEndResult reason.
         * @member {string} reason
         * @memberof game.MatchEndResult
         * @instance
         */
        MatchEndResult.prototype.reason = "";

        /**
         * MatchEndResult finalHandNum.
         * @member {number} finalHandNum
         * @memberof game.MatchEndResult
         * @instance
         */
        MatchEndResult.prototype.finalHandNum = 0;

        /**
         * MatchEndResult standings.
         * @member {Array.<game.PlayerStanding>} standings
         * @memberof game.MatchEndResult
         * @instance
         */
        MatchEndResult.prototype.standings = $util.emptyArray;

        /**
         * Creates a new MatchEndResult instance using the specified properties.
         * @function create
         * @memberof game.MatchEndResult
         * @static
         * @param {game.IMatchEndResult=} [properties] Properties to set
         * @returns {game.MatchEndResult} MatchEndResult instance
         */
        MatchEndResult.create = function create(properties) {
            return new MatchEndResult(properties);
        };

        /**
         * Encodes the specified MatchEndResult message. Does not implicitly {@link game.MatchEndResult.verify|verify} messages.
         * @function encode
         * @memberof game.MatchEndResult
         * @static
         * @param {game.IMatchEndResult} message MatchEndResult message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        MatchEndResult.encode = function encode(message, writer) {
            if (!writer)
                writer = $Writer.create();
            if (message.reason != null && Object.hasOwnProperty.call(message, "reason"))
                writer.uint32(/* id 1, wireType 2 =*/10).string(message.reason);
            if (message.finalHandNum != null && Object.hasOwnProperty.call(message, "finalHandNum"))
                writer.uint32(/* id 2, wireType 0 =*/16).uint32(message.finalHandNum);
            if (message.standings != null && message.standings.length)
                for (var i = 0; i < message.standings.length; ++i)
                    $root.game.PlayerStanding.encode(message.standings[i], writer.uint32(/* id 3, wireType 2 =*/26).fork()).ldelim();
            return writer;
        };

        /**
         * Encodes the specified MatchEndResult message, length delimited. Does not implicitly {@link game.MatchEndResult.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.MatchEndResult
         * @static
         * @param {game.IMatchEndResult} message MatchEndResult message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        MatchEndResult.encodeDelimited = function encodeDelimited(message, writer) {
            return this.encode(message, writer).ldelim();
        };

        /**
         * Decodes a MatchEndResult message from the specified reader or buffer.
         * @function decode
         * @memberof game.MatchEndResult
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.MatchEndResult} MatchEndResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        MatchEndResult.decode = function decode(reader, length, error) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            var end = length === undefined ? reader.len : reader.pos + length, message = new $root.game.MatchEndResult();
            while (reader.pos < end) {
                var tag = reader.uint32();
                if (tag === error)
                    break;
                switch (tag >>> 3) {
                case 1: {
                        message.reason = reader.string();
                        break;
                    }
                case 2: {
                        message.finalHandNum = reader.uint32();
                        break;
                    }
                case 3: {
                        if (!(message.standings && message.standings.length))
                            message.standings = [];
                        message.standings.push($root.game.PlayerStanding.decode(reader, reader.uint32()));
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
         * Decodes a MatchEndResult message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.MatchEndResult
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.MatchEndResult} MatchEndResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        MatchEndResult.decodeDelimited = function decodeDelimited(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a MatchEndResult message.
         * @function verify
         * @memberof game.MatchEndResult
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        MatchEndResult.verify = function verify(message) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (message.reason != null && message.hasOwnProperty("reason"))
                if (!$util.isString(message.reason))
                    return "reason: string expected";
            if (message.finalHandNum != null && message.hasOwnProperty("finalHandNum"))
                if (!$util.isInteger(message.finalHandNum))
                    return "finalHandNum: integer expected";
            if (message.standings != null && message.hasOwnProperty("standings")) {
                if (!Array.isArray(message.standings))
                    return "standings: array expected";
                for (var i = 0; i < message.standings.length; ++i) {
                    var error = $root.game.PlayerStanding.verify(message.standings[i]);
                    if (error)
                        return "standings." + error;
                }
            }
            return null;
        };

        /**
         * Creates a MatchEndResult message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.MatchEndResult
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.MatchEndResult} MatchEndResult
         */
        MatchEndResult.fromObject = function fromObject(object) {
            if (object instanceof $root.game.MatchEndResult)
                return object;
            var message = new $root.game.MatchEndResult();
            if (object.reason != null)
                message.reason = String(object.reason);
            if (object.finalHandNum != null)
                message.finalHandNum = object.finalHandNum >>> 0;
            if (object.standings) {
                if (!Array.isArray(object.standings))
                    throw TypeError(".game.MatchEndResult.standings: array expected");
                message.standings = [];
                for (var i = 0; i < object.standings.length; ++i) {
                    if (typeof object.standings[i] !== "object")
                        throw TypeError(".game.MatchEndResult.standings: object expected");
                    message.standings[i] = $root.game.PlayerStanding.fromObject(object.standings[i]);
                }
            }
            return message;
        };

        /**
         * Creates a plain object from a MatchEndResult message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.MatchEndResult
         * @static
         * @param {game.MatchEndResult} message MatchEndResult
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        MatchEndResult.toObject = function toObject(message, options) {
            if (!options)
                options = {};
            var object = {};
            if (options.arrays || options.defaults)
                object.standings = [];
            if (options.defaults) {
                object.reason = "";
                object.finalHandNum = 0;
            }
            if (message.reason != null && message.hasOwnProperty("reason"))
                object.reason = message.reason;
            if (message.finalHandNum != null && message.hasOwnProperty("finalHandNum"))
                object.finalHandNum = message.finalHandNum;
            if (message.standings && message.standings.length) {
                object.standings = [];
                for (var j = 0; j < message.standings.length; ++j)
                    object.standings[j] = $root.game.PlayerStanding.toObject(message.standings[j], options);
            }
            return object;
        };

        /**
         * Converts this MatchEndResult to JSON.
         * @function toJSON
         * @memberof game.MatchEndResult
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        MatchEndResult.prototype.toJSON = function toJSON() {
            return this.constructor.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the default type url for MatchEndResult
         * @function getTypeUrl
         * @memberof game.MatchEndResult
         * @static
         * @param {string} [typeUrlPrefix] your custom typeUrlPrefix(default "type.googleapis.com")
         * @returns {string} The default type url
         */
        MatchEndResult.getTypeUrl = function getTypeUrl(typeUrlPrefix) {
            if (typeUrlPrefix === undefined) {
                typeUrlPrefix = "type.googleapis.com";
            }
            return typeUrlPrefix + "/game.MatchEndResult";
        };

        return MatchEndResult;
    })();

    return game;
})();

module.exports = $root;
