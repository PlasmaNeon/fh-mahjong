/*eslint-disable block-scoped-var, id-length, no-control-regex, no-magic-numbers, no-mixed-operators, no-prototype-builtins, no-redeclare, no-shadow, no-var, sort-vars, default-case, jsdoc/require-param*/
import $protobuf from "protobufjs/minimal.js";

// Common aliases
const $Reader = $protobuf.Reader, $Writer = $protobuf.Writer, $util = $protobuf.util;
const $Object = $util.global.Object, $undefined = $util.global.undefined, $Error = $util.global.Error, $TypeError = $util.global.TypeError, $Number = $util.global.Number, $String = $util.global.String, $Array = $util.global.Array, $Boolean = $util.global.Boolean, $parseInt = $util.global.parseInt, $BigInt = $util.global.BigInt, $isFinite = $util.global.isFinite;

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
        const valuesById = $Object.create(null), values = $Object.create(valuesById);
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
         * @typedef {Object} game.Tile.$Properties
         * @property {number} [id] Tile id
         * @property {game.Suit} [suit] Tile suit
         * @property {number} [value] Tile value
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a Tile.
         * @memberof game
         * @interface ITile
         * @augments game.Tile.$Properties
         * @deprecated Use game.Tile.$Properties instead.
         */

        /**
         * Shape of a Tile.
         * @typedef {game.Tile.$Properties} game.Tile.$Shape
         */

        /**
         * Constructs a new Tile.
         * @memberof game
         * @classdesc Represents a Tile.
         * @constructor
         * @param {game.Tile.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const Tile = function (properties) {
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.Tile.$Properties=} [properties] Properties to set
         * @returns {game.Tile} Tile instance
         * @type {{
         *   (properties: game.Tile.$Shape): game.Tile & game.Tile.$Shape;
         *   (properties?: game.Tile.$Properties): game.Tile;
         * }}
         */
        Tile.create = function(properties) {
            return new Tile(properties);
        };

        /**
         * Encodes the specified Tile message. Does not implicitly {@link game.Tile.verify|verify} messages.
         * @function encode
         * @memberof game.Tile
         * @static
         * @param {game.Tile.$Properties} message Tile message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Tile.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.id != null && $Object.hasOwnProperty.call(message, "id") && message.id !== 0)
                writer.uint32(/* id 1, wireType 0 =*/8).uint32(message.id);
            if (message.suit != null && $Object.hasOwnProperty.call(message, "suit") && message.suit !== 0)
                writer.uint32(/* id 2, wireType 0 =*/16).int32(message.suit);
            if (message.value != null && $Object.hasOwnProperty.call(message, "value") && message.value !== 0)
                writer.uint32(/* id 3, wireType 0 =*/24).uint32(message.value);
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified Tile message, length delimited. Does not implicitly {@link game.Tile.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.Tile
         * @static
         * @param {game.Tile.$Properties} message Tile message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Tile.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a Tile message from the specified reader or buffer.
         * @function decode
         * @memberof game.Tile
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.Tile & game.Tile.$Shape} Tile
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Tile.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.Tile(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.id = value;
                        else
                            delete message.id;
                        continue;
                    }
                case 2: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.suit = value;
                        else
                            delete message.suit;
                        continue;
                    }
                case 3: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.value = value;
                        else
                            delete message.value;
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a Tile message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.Tile
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.Tile & game.Tile.$Shape} Tile
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Tile.decodeDelimited = function(reader) {
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
        Tile.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.id != null && $Object.hasOwnProperty.call(message, "id"))
                if (!$util.isInteger(message.id))
                    return "id: integer expected";
            if (message.suit != null && $Object.hasOwnProperty.call(message, "suit"))
                if (typeof message.suit !== "number" || (message.suit | 0) !== message.suit)
                    return "suit: enum value expected";
            if (message.value != null && $Object.hasOwnProperty.call(message, "value"))
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
        Tile.fromObject = function (object, _depth) {
            if (object instanceof $root.game.Tile)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.Tile: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.Tile();
            if (object.id != null)
                if ($Number(object.id) !== 0)
                    message.id = object.id >>> 0;
            if (object.suit !== 0 && (typeof object.suit !== "string" || $root.game.Suit[object.suit] !== 0))
                switch (object.suit) {
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
                default:
                    if (typeof object.suit === "number" && (object.suit | 0) === object.suit)
                        message.suit = object.suit;
                }
            if (object.value != null)
                if ($Number(object.value) !== 0)
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
        Tile.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.defaults) {
                object.id = 0;
                object.suit = options.enums === $String ? "SUIT_UNKNOWN" : 0;
                object.value = 0;
            }
            if (message.id != null && $Object.hasOwnProperty.call(message, "id"))
                object.id = message.id;
            if (message.suit != null && $Object.hasOwnProperty.call(message, "suit"))
                object.suit = options.enums === $String ? $root.game.Suit[message.suit] === $undefined ? message.suit : $root.game.Suit[message.suit] : message.suit;
            if (message.value != null && $Object.hasOwnProperty.call(message, "value"))
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
        Tile.prototype.toJSON = function() {
            return Tile.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for Tile
         * @function getTypeUrl
         * @memberof game.Tile
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        Tile.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.Tile";
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
        const valuesById = $Object.create(null), values = $Object.create(valuesById);
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
         * @typedef {Object} game.PlayerAction.$Properties
         * @property {game.ActionType} [type] PlayerAction type
         * @property {game.Tile.$Properties} [tile] PlayerAction tile
         * @property {Array.<game.Tile.$Properties>} [meldTiles] PlayerAction meldTiles
         * @property {number} [targetPlayer] PlayerAction targetPlayer
         * @property {boolean} [isRobbingKong] PlayerAction isRobbingKong
         * @property {boolean} [isBottomTile] PlayerAction isBottomTile
         * @property {boolean} [isBloomingKong] PlayerAction isBloomingKong
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a PlayerAction.
         * @memberof game
         * @interface IPlayerAction
         * @augments game.PlayerAction.$Properties
         * @deprecated Use game.PlayerAction.$Properties instead.
         */

        /**
         * Shape of a PlayerAction.
         * @typedef {game.PlayerAction.$Properties} game.PlayerAction.$Shape
         */

        /**
         * Constructs a new PlayerAction.
         * @memberof game
         * @classdesc Represents a PlayerAction.
         * @constructor
         * @param {game.PlayerAction.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const PlayerAction = function (properties) {
            this.meldTiles = [];
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.PlayerAction.$Properties=} [properties] Properties to set
         * @returns {game.PlayerAction} PlayerAction instance
         * @type {{
         *   (properties: game.PlayerAction.$Shape): game.PlayerAction & game.PlayerAction.$Shape;
         *   (properties?: game.PlayerAction.$Properties): game.PlayerAction;
         * }}
         */
        PlayerAction.create = function(properties) {
            return new PlayerAction(properties);
        };

        /**
         * Encodes the specified PlayerAction message. Does not implicitly {@link game.PlayerAction.verify|verify} messages.
         * @function encode
         * @memberof game.PlayerAction
         * @static
         * @param {game.PlayerAction.$Properties} message PlayerAction message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PlayerAction.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.type != null && $Object.hasOwnProperty.call(message, "type") && message.type !== 0)
                writer.uint32(/* id 1, wireType 0 =*/8).int32(message.type);
            if (message.tile != null && $Object.hasOwnProperty.call(message, "tile"))
                $root.game.Tile.encode(message.tile, writer.uint32(/* id 2, wireType 2 =*/18).fork(), _depth + 1).ldelim();
            if (message.meldTiles != null && message.meldTiles.length)
                for (let i = 0; i < message.meldTiles.length; ++i)
                    $root.game.Tile.encode(message.meldTiles[i], writer.uint32(/* id 3, wireType 2 =*/26).fork(), _depth + 1).ldelim();
            if (message.targetPlayer != null && $Object.hasOwnProperty.call(message, "targetPlayer") && message.targetPlayer !== 0)
                writer.uint32(/* id 4, wireType 0 =*/32).uint32(message.targetPlayer);
            if (message.isRobbingKong != null && $Object.hasOwnProperty.call(message, "isRobbingKong") && message.isRobbingKong !== false)
                writer.uint32(/* id 5, wireType 0 =*/40).bool(message.isRobbingKong);
            if (message.isBottomTile != null && $Object.hasOwnProperty.call(message, "isBottomTile") && message.isBottomTile !== false)
                writer.uint32(/* id 6, wireType 0 =*/48).bool(message.isBottomTile);
            if (message.isBloomingKong != null && $Object.hasOwnProperty.call(message, "isBloomingKong") && message.isBloomingKong !== false)
                writer.uint32(/* id 7, wireType 0 =*/56).bool(message.isBloomingKong);
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified PlayerAction message, length delimited. Does not implicitly {@link game.PlayerAction.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.PlayerAction
         * @static
         * @param {game.PlayerAction.$Properties} message PlayerAction message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PlayerAction.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a PlayerAction message from the specified reader or buffer.
         * @function decode
         * @memberof game.PlayerAction
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.PlayerAction & game.PlayerAction.$Shape} PlayerAction
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PlayerAction.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.PlayerAction(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.type = value;
                        else
                            delete message.type;
                        continue;
                    }
                case 2: {
                        if (wireType !== 2)
                            break;
                        message.tile = $root.game.Tile.decode(reader, reader.uint32(), $undefined, _depth + 1, message.tile);
                        continue;
                    }
                case 3: {
                        if (wireType !== 2)
                            break;
                        if (!(message.meldTiles && message.meldTiles.length))
                            message.meldTiles = [];
                        message.meldTiles.push($root.game.Tile.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                case 4: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.targetPlayer = value;
                        else
                            delete message.targetPlayer;
                        continue;
                    }
                case 5: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.isRobbingKong = value;
                        else
                            delete message.isRobbingKong;
                        continue;
                    }
                case 6: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.isBottomTile = value;
                        else
                            delete message.isBottomTile;
                        continue;
                    }
                case 7: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.isBloomingKong = value;
                        else
                            delete message.isBloomingKong;
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a PlayerAction message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.PlayerAction
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.PlayerAction & game.PlayerAction.$Shape} PlayerAction
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PlayerAction.decodeDelimited = function(reader) {
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
        PlayerAction.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.type != null && $Object.hasOwnProperty.call(message, "type"))
                if (typeof message.type !== "number" || (message.type | 0) !== message.type)
                    return "type: enum value expected";
            if (message.tile != null && $Object.hasOwnProperty.call(message, "tile")) {
                let error = $root.game.Tile.verify(message.tile, _depth + 1);
                if (error)
                    return "tile." + error;
            }
            if (message.meldTiles != null && $Object.hasOwnProperty.call(message, "meldTiles")) {
                if (!$Array.isArray(message.meldTiles))
                    return "meldTiles: array expected";
                for (let i = 0; i < message.meldTiles.length; ++i) {
                    let error = $root.game.Tile.verify(message.meldTiles[i], _depth + 1);
                    if (error)
                        return "meldTiles." + error;
                }
            }
            if (message.targetPlayer != null && $Object.hasOwnProperty.call(message, "targetPlayer"))
                if (!$util.isInteger(message.targetPlayer))
                    return "targetPlayer: integer expected";
            if (message.isRobbingKong != null && $Object.hasOwnProperty.call(message, "isRobbingKong"))
                if (typeof message.isRobbingKong !== "boolean")
                    return "isRobbingKong: boolean expected";
            if (message.isBottomTile != null && $Object.hasOwnProperty.call(message, "isBottomTile"))
                if (typeof message.isBottomTile !== "boolean")
                    return "isBottomTile: boolean expected";
            if (message.isBloomingKong != null && $Object.hasOwnProperty.call(message, "isBloomingKong"))
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
        PlayerAction.fromObject = function (object, _depth) {
            if (object instanceof $root.game.PlayerAction)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.PlayerAction: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.PlayerAction();
            if (object.type !== 0 && (typeof object.type !== "string" || $root.game.ActionType[object.type] !== 0))
                switch (object.type) {
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
                default:
                    if (typeof object.type === "number" && (object.type | 0) === object.type)
                        message.type = object.type;
                }
            if (object.tile != null) {
                if (!$util.isObject(object.tile))
                    throw $TypeError(".game.PlayerAction.tile: object expected");
                message.tile = $root.game.Tile.fromObject(object.tile, _depth + 1);
            }
            if (object.meldTiles) {
                if (!$Array.isArray(object.meldTiles))
                    throw $TypeError(".game.PlayerAction.meldTiles: array expected");
                message.meldTiles = $Array(object.meldTiles.length);
                for (let i = 0; i < object.meldTiles.length; ++i) {
                    if (!$util.isObject(object.meldTiles[i]))
                        throw $TypeError(".game.PlayerAction.meldTiles: object expected");
                    message.meldTiles[i] = $root.game.Tile.fromObject(object.meldTiles[i], _depth + 1);
                }
            }
            if (object.targetPlayer != null)
                if ($Number(object.targetPlayer) !== 0)
                    message.targetPlayer = object.targetPlayer >>> 0;
            if (object.isRobbingKong != null)
                if (object.isRobbingKong)
                    message.isRobbingKong = $Boolean(object.isRobbingKong);
            if (object.isBottomTile != null)
                if (object.isBottomTile)
                    message.isBottomTile = $Boolean(object.isBottomTile);
            if (object.isBloomingKong != null)
                if (object.isBloomingKong)
                    message.isBloomingKong = $Boolean(object.isBloomingKong);
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
        PlayerAction.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.arrays || options.defaults)
                object.meldTiles = [];
            if (options.defaults) {
                object.type = options.enums === $String ? "ACTION_UNKNOWN" : 0;
                object.tile = null;
                object.targetPlayer = 0;
                object.isRobbingKong = false;
                object.isBottomTile = false;
                object.isBloomingKong = false;
            }
            if (message.type != null && $Object.hasOwnProperty.call(message, "type"))
                object.type = options.enums === $String ? $root.game.ActionType[message.type] === $undefined ? message.type : $root.game.ActionType[message.type] : message.type;
            if (message.tile != null && $Object.hasOwnProperty.call(message, "tile"))
                object.tile = $root.game.Tile.toObject(message.tile, options, _depth + 1);
            if (message.meldTiles && message.meldTiles.length) {
                object.meldTiles = $Array(message.meldTiles.length);
                for (let j = 0; j < message.meldTiles.length; ++j)
                    object.meldTiles[j] = $root.game.Tile.toObject(message.meldTiles[j], options, _depth + 1);
            }
            if (message.targetPlayer != null && $Object.hasOwnProperty.call(message, "targetPlayer"))
                object.targetPlayer = message.targetPlayer;
            if (message.isRobbingKong != null && $Object.hasOwnProperty.call(message, "isRobbingKong"))
                object.isRobbingKong = message.isRobbingKong;
            if (message.isBottomTile != null && $Object.hasOwnProperty.call(message, "isBottomTile"))
                object.isBottomTile = message.isBottomTile;
            if (message.isBloomingKong != null && $Object.hasOwnProperty.call(message, "isBloomingKong"))
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
        PlayerAction.prototype.toJSON = function() {
            return PlayerAction.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for PlayerAction
         * @function getTypeUrl
         * @memberof game.PlayerAction
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        PlayerAction.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.PlayerAction";
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
        const valuesById = $Object.create(null), values = $Object.create(valuesById);
        values[valuesById[0] = "MELD_DIRECTION_UNKNOWN"] = 0;
        values[valuesById[1] = "MELD_DIRECTION_RIGHT"] = 1;
        values[valuesById[2] = "MELD_DIRECTION_ACROSS"] = 2;
        values[valuesById[3] = "MELD_DIRECTION_LEFT"] = 3;
        return values;
    })();

    game.Meld = (function() {

        /**
         * Properties of a Meld.
         * @typedef {Object} game.Meld.$Properties
         * @property {game.ActionType} [type] Meld type
         * @property {Array.<game.Tile.$Properties>} [tiles] Meld tiles
         * @property {game.MeldDirection} [calledDirection] Meld calledDirection
         * @property {number|null} [calledTileId] Meld calledTileId
         * @property {number|null} [addedTileId] Meld addedTileId
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a Meld.
         * @memberof game
         * @interface IMeld
         * @augments game.Meld.$Properties
         * @deprecated Use game.Meld.$Properties instead.
         */

        /**
         * Shape of a Meld.
         * @typedef {game.Meld.$Properties} game.Meld.$Shape
         */

        /**
         * Constructs a new Meld.
         * @memberof game
         * @classdesc Represents a Meld.
         * @constructor
         * @param {game.Meld.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const Meld = function (properties) {
            this.tiles = [];
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @member {number|null} calledTileId
         * @memberof game.Meld
         * @instance
         */
        Meld.prototype.calledTileId = null;

        /**
         * Meld addedTileId.
         * @member {number|null} addedTileId
         * @memberof game.Meld
         * @instance
         */
        Meld.prototype.addedTileId = null;

        // OneOf field names bound to virtual getters and setters
        let $oneOfFields;

        // Virtual OneOf for proto3 optional field
        $Object.defineProperty(Meld.prototype, "_calledTileId", {
            get: $util.oneOfGetter($oneOfFields = ["calledTileId"]),
            set: $util.oneOfSetter($oneOfFields)
        });

        // Virtual OneOf for proto3 optional field
        $Object.defineProperty(Meld.prototype, "_addedTileId", {
            get: $util.oneOfGetter($oneOfFields = ["addedTileId"]),
            set: $util.oneOfSetter($oneOfFields)
        });

        /**
         * Creates a new Meld instance using the specified properties.
         * @function create
         * @memberof game.Meld
         * @static
         * @param {game.Meld.$Properties=} [properties] Properties to set
         * @returns {game.Meld} Meld instance
         * @type {{
         *   (properties: game.Meld.$Shape): game.Meld & game.Meld.$Shape;
         *   (properties?: game.Meld.$Properties): game.Meld;
         * }}
         */
        Meld.create = function(properties) {
            return new Meld(properties);
        };

        /**
         * Encodes the specified Meld message. Does not implicitly {@link game.Meld.verify|verify} messages.
         * @function encode
         * @memberof game.Meld
         * @static
         * @param {game.Meld.$Properties} message Meld message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Meld.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.type != null && $Object.hasOwnProperty.call(message, "type") && message.type !== 0)
                writer.uint32(/* id 1, wireType 0 =*/8).int32(message.type);
            if (message.tiles != null && message.tiles.length)
                for (let i = 0; i < message.tiles.length; ++i)
                    $root.game.Tile.encode(message.tiles[i], writer.uint32(/* id 2, wireType 2 =*/18).fork(), _depth + 1).ldelim();
            if (message.calledDirection != null && $Object.hasOwnProperty.call(message, "calledDirection") && message.calledDirection !== 0)
                writer.uint32(/* id 3, wireType 0 =*/24).int32(message.calledDirection);
            if (message.calledTileId != null && $Object.hasOwnProperty.call(message, "calledTileId"))
                writer.uint32(/* id 4, wireType 0 =*/32).uint32(message.calledTileId);
            if (message.addedTileId != null && $Object.hasOwnProperty.call(message, "addedTileId"))
                writer.uint32(/* id 5, wireType 0 =*/40).uint32(message.addedTileId);
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified Meld message, length delimited. Does not implicitly {@link game.Meld.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.Meld
         * @static
         * @param {game.Meld.$Properties} message Meld message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        Meld.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a Meld message from the specified reader or buffer.
         * @function decode
         * @memberof game.Meld
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.Meld & game.Meld.$Shape} Meld
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Meld.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.Meld(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.type = value;
                        else
                            delete message.type;
                        continue;
                    }
                case 2: {
                        if (wireType !== 2)
                            break;
                        if (!(message.tiles && message.tiles.length))
                            message.tiles = [];
                        message.tiles.push($root.game.Tile.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                case 3: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.calledDirection = value;
                        else
                            delete message.calledDirection;
                        continue;
                    }
                case 4: {
                        if (wireType !== 0)
                            break;
                        message.calledTileId = reader.uint32();
                        message._calledTileId = "calledTileId";
                        continue;
                    }
                case 5: {
                        if (wireType !== 0)
                            break;
                        message.addedTileId = reader.uint32();
                        message._addedTileId = "addedTileId";
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a Meld message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.Meld
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.Meld & game.Meld.$Shape} Meld
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        Meld.decodeDelimited = function(reader) {
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
        Meld.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            let properties = {};
            if (message.type != null && $Object.hasOwnProperty.call(message, "type"))
                if (typeof message.type !== "number" || (message.type | 0) !== message.type)
                    return "type: enum value expected";
            if (message.tiles != null && $Object.hasOwnProperty.call(message, "tiles")) {
                if (!$Array.isArray(message.tiles))
                    return "tiles: array expected";
                for (let i = 0; i < message.tiles.length; ++i) {
                    let error = $root.game.Tile.verify(message.tiles[i], _depth + 1);
                    if (error)
                        return "tiles." + error;
                }
            }
            if (message.calledDirection != null && $Object.hasOwnProperty.call(message, "calledDirection"))
                if (typeof message.calledDirection !== "number" || (message.calledDirection | 0) !== message.calledDirection)
                    return "calledDirection: enum value expected";
            if (message.calledTileId != null && $Object.hasOwnProperty.call(message, "calledTileId")) {
                properties._calledTileId = 1;
                if (!$util.isInteger(message.calledTileId))
                    return "calledTileId: integer expected";
            }
            if (message.addedTileId != null && $Object.hasOwnProperty.call(message, "addedTileId")) {
                properties._addedTileId = 1;
                if (!$util.isInteger(message.addedTileId))
                    return "addedTileId: integer expected";
            }
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
        Meld.fromObject = function (object, _depth) {
            if (object instanceof $root.game.Meld)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.Meld: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.Meld();
            if (object.type !== 0 && (typeof object.type !== "string" || $root.game.ActionType[object.type] !== 0))
                switch (object.type) {
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
                default:
                    if (typeof object.type === "number" && (object.type | 0) === object.type)
                        message.type = object.type;
                }
            if (object.tiles) {
                if (!$Array.isArray(object.tiles))
                    throw $TypeError(".game.Meld.tiles: array expected");
                message.tiles = $Array(object.tiles.length);
                for (let i = 0; i < object.tiles.length; ++i) {
                    if (!$util.isObject(object.tiles[i]))
                        throw $TypeError(".game.Meld.tiles: object expected");
                    message.tiles[i] = $root.game.Tile.fromObject(object.tiles[i], _depth + 1);
                }
            }
            if (object.calledDirection !== 0 && (typeof object.calledDirection !== "string" || $root.game.MeldDirection[object.calledDirection] !== 0))
                switch (object.calledDirection) {
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
                default:
                    if (typeof object.calledDirection === "number" && (object.calledDirection | 0) === object.calledDirection)
                        message.calledDirection = object.calledDirection;
                }
            if (object.calledTileId != null)
                message.calledTileId = object.calledTileId >>> 0;
            if (object.addedTileId != null)
                message.addedTileId = object.addedTileId >>> 0;
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
        Meld.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.arrays || options.defaults)
                object.tiles = [];
            if (options.defaults) {
                object.type = options.enums === $String ? "ACTION_UNKNOWN" : 0;
                object.calledDirection = options.enums === $String ? "MELD_DIRECTION_UNKNOWN" : 0;
            }
            if (message.type != null && $Object.hasOwnProperty.call(message, "type"))
                object.type = options.enums === $String ? $root.game.ActionType[message.type] === $undefined ? message.type : $root.game.ActionType[message.type] : message.type;
            if (message.tiles && message.tiles.length) {
                object.tiles = $Array(message.tiles.length);
                for (let j = 0; j < message.tiles.length; ++j)
                    object.tiles[j] = $root.game.Tile.toObject(message.tiles[j], options, _depth + 1);
            }
            if (message.calledDirection != null && $Object.hasOwnProperty.call(message, "calledDirection"))
                object.calledDirection = options.enums === $String ? $root.game.MeldDirection[message.calledDirection] === $undefined ? message.calledDirection : $root.game.MeldDirection[message.calledDirection] : message.calledDirection;
            if (message.calledTileId != null && $Object.hasOwnProperty.call(message, "calledTileId"))
                object.calledTileId = message.calledTileId;
            if (message.addedTileId != null && $Object.hasOwnProperty.call(message, "addedTileId"))
                object.addedTileId = message.addedTileId;
            return object;
        };

        /**
         * Converts this Meld to JSON.
         * @function toJSON
         * @memberof game.Meld
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        Meld.prototype.toJSON = function() {
            return Meld.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for Meld
         * @function getTypeUrl
         * @memberof game.Meld
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        Meld.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.Meld";
        };

        return Meld;
    })();

    game.PlayerState = (function() {

        /**
         * Properties of a PlayerState.
         * @typedef {Object} game.PlayerState.$Properties
         * @property {number} [seat] PlayerState seat
         * @property {number} [score] PlayerState score
         * @property {Array.<game.Tile.$Properties>} [closedHand] PlayerState closedHand
         * @property {number} [handSize] PlayerState handSize
         * @property {Array.<game.Meld.$Properties>} [openMelds] PlayerState openMelds
         * @property {Array.<game.Tile.$Properties>} [discards] PlayerState discards
         * @property {number} [seatWind] PlayerState seatWind
         * @property {Array.<game.Tile.$Properties>} [flowerMelds] PlayerState flowerMelds
         * @property {boolean} [hasBuddingDirectKong] PlayerState hasBuddingDirectKong
         * @property {boolean} [hasBloomingDirectKong] PlayerState hasBloomingDirectKong
         * @property {boolean} [hasBuddingClosedKong] PlayerState hasBuddingClosedKong
         * @property {boolean} [hasBloomingClosedKong] PlayerState hasBloomingClosedKong
         * @property {boolean} [hasBuddingRiskyKong] PlayerState hasBuddingRiskyKong
         * @property {boolean} [hasBloomingRiskyKong] PlayerState hasBloomingRiskyKong
         * @property {boolean} [hasBloomingFlowerKong] PlayerState hasBloomingFlowerKong
         * @property {Array.<game.PlayerAction.$Properties>} [validActions] PlayerState validActions
         * @property {number|null} [drawnTileId] PlayerState drawnTileId
         * @property {number} [shanten] PlayerState shanten
         * @property {boolean} [lastDiscardFromDrawn] PlayerState lastDiscardFromDrawn
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a PlayerState.
         * @memberof game
         * @interface IPlayerState
         * @augments game.PlayerState.$Properties
         * @deprecated Use game.PlayerState.$Properties instead.
         */

        /**
         * Shape of a PlayerState.
         * @typedef {game.PlayerState.$Properties} game.PlayerState.$Shape
         */

        /**
         * Constructs a new PlayerState.
         * @memberof game
         * @classdesc Represents a PlayerState.
         * @constructor
         * @param {game.PlayerState.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const PlayerState = function (properties) {
            this.closedHand = [];
            this.openMelds = [];
            this.discards = [];
            this.flowerMelds = [];
            this.validActions = [];
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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

        /**
         * PlayerState lastDiscardFromDrawn.
         * @member {boolean} lastDiscardFromDrawn
         * @memberof game.PlayerState
         * @instance
         */
        PlayerState.prototype.lastDiscardFromDrawn = false;

        // OneOf field names bound to virtual getters and setters
        let $oneOfFields;

        // Virtual OneOf for proto3 optional field
        $Object.defineProperty(PlayerState.prototype, "_drawnTileId", {
            get: $util.oneOfGetter($oneOfFields = ["drawnTileId"]),
            set: $util.oneOfSetter($oneOfFields)
        });

        /**
         * Creates a new PlayerState instance using the specified properties.
         * @function create
         * @memberof game.PlayerState
         * @static
         * @param {game.PlayerState.$Properties=} [properties] Properties to set
         * @returns {game.PlayerState} PlayerState instance
         * @type {{
         *   (properties: game.PlayerState.$Shape): game.PlayerState & game.PlayerState.$Shape;
         *   (properties?: game.PlayerState.$Properties): game.PlayerState;
         * }}
         */
        PlayerState.create = function(properties) {
            return new PlayerState(properties);
        };

        /**
         * Encodes the specified PlayerState message. Does not implicitly {@link game.PlayerState.verify|verify} messages.
         * @function encode
         * @memberof game.PlayerState
         * @static
         * @param {game.PlayerState.$Properties} message PlayerState message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PlayerState.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.seat != null && $Object.hasOwnProperty.call(message, "seat") && message.seat !== 0)
                writer.uint32(/* id 1, wireType 0 =*/8).uint32(message.seat);
            if (message.score != null && $Object.hasOwnProperty.call(message, "score") && message.score !== 0)
                writer.uint32(/* id 2, wireType 0 =*/16).int32(message.score);
            if (message.closedHand != null && message.closedHand.length)
                for (let i = 0; i < message.closedHand.length; ++i)
                    $root.game.Tile.encode(message.closedHand[i], writer.uint32(/* id 3, wireType 2 =*/26).fork(), _depth + 1).ldelim();
            if (message.handSize != null && $Object.hasOwnProperty.call(message, "handSize") && message.handSize !== 0)
                writer.uint32(/* id 4, wireType 0 =*/32).uint32(message.handSize);
            if (message.openMelds != null && message.openMelds.length)
                for (let i = 0; i < message.openMelds.length; ++i)
                    $root.game.Meld.encode(message.openMelds[i], writer.uint32(/* id 5, wireType 2 =*/42).fork(), _depth + 1).ldelim();
            if (message.discards != null && message.discards.length)
                for (let i = 0; i < message.discards.length; ++i)
                    $root.game.Tile.encode(message.discards[i], writer.uint32(/* id 6, wireType 2 =*/50).fork(), _depth + 1).ldelim();
            if (message.seatWind != null && $Object.hasOwnProperty.call(message, "seatWind") && message.seatWind !== 0)
                writer.uint32(/* id 7, wireType 0 =*/56).uint32(message.seatWind);
            if (message.flowerMelds != null && message.flowerMelds.length)
                for (let i = 0; i < message.flowerMelds.length; ++i)
                    $root.game.Tile.encode(message.flowerMelds[i], writer.uint32(/* id 8, wireType 2 =*/66).fork(), _depth + 1).ldelim();
            if (message.hasBuddingDirectKong != null && $Object.hasOwnProperty.call(message, "hasBuddingDirectKong") && message.hasBuddingDirectKong !== false)
                writer.uint32(/* id 9, wireType 0 =*/72).bool(message.hasBuddingDirectKong);
            if (message.hasBloomingDirectKong != null && $Object.hasOwnProperty.call(message, "hasBloomingDirectKong") && message.hasBloomingDirectKong !== false)
                writer.uint32(/* id 10, wireType 0 =*/80).bool(message.hasBloomingDirectKong);
            if (message.hasBuddingClosedKong != null && $Object.hasOwnProperty.call(message, "hasBuddingClosedKong") && message.hasBuddingClosedKong !== false)
                writer.uint32(/* id 11, wireType 0 =*/88).bool(message.hasBuddingClosedKong);
            if (message.hasBloomingClosedKong != null && $Object.hasOwnProperty.call(message, "hasBloomingClosedKong") && message.hasBloomingClosedKong !== false)
                writer.uint32(/* id 12, wireType 0 =*/96).bool(message.hasBloomingClosedKong);
            if (message.hasBuddingRiskyKong != null && $Object.hasOwnProperty.call(message, "hasBuddingRiskyKong") && message.hasBuddingRiskyKong !== false)
                writer.uint32(/* id 13, wireType 0 =*/104).bool(message.hasBuddingRiskyKong);
            if (message.hasBloomingRiskyKong != null && $Object.hasOwnProperty.call(message, "hasBloomingRiskyKong") && message.hasBloomingRiskyKong !== false)
                writer.uint32(/* id 14, wireType 0 =*/112).bool(message.hasBloomingRiskyKong);
            if (message.hasBloomingFlowerKong != null && $Object.hasOwnProperty.call(message, "hasBloomingFlowerKong") && message.hasBloomingFlowerKong !== false)
                writer.uint32(/* id 15, wireType 0 =*/120).bool(message.hasBloomingFlowerKong);
            if (message.validActions != null && message.validActions.length)
                for (let i = 0; i < message.validActions.length; ++i)
                    $root.game.PlayerAction.encode(message.validActions[i], writer.uint32(/* id 16, wireType 2 =*/130).fork(), _depth + 1).ldelim();
            if (message.drawnTileId != null && $Object.hasOwnProperty.call(message, "drawnTileId"))
                writer.uint32(/* id 17, wireType 0 =*/136).int32(message.drawnTileId);
            if (message.shanten != null && $Object.hasOwnProperty.call(message, "shanten") && message.shanten !== 0)
                writer.uint32(/* id 18, wireType 0 =*/144).int32(message.shanten);
            if (message.lastDiscardFromDrawn != null && $Object.hasOwnProperty.call(message, "lastDiscardFromDrawn") && message.lastDiscardFromDrawn !== false)
                writer.uint32(/* id 19, wireType 0 =*/152).bool(message.lastDiscardFromDrawn);
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified PlayerState message, length delimited. Does not implicitly {@link game.PlayerState.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.PlayerState
         * @static
         * @param {game.PlayerState.$Properties} message PlayerState message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PlayerState.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a PlayerState message from the specified reader or buffer.
         * @function decode
         * @memberof game.PlayerState
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.PlayerState & game.PlayerState.$Shape} PlayerState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PlayerState.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.PlayerState(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.seat = value;
                        else
                            delete message.seat;
                        continue;
                    }
                case 2: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.score = value;
                        else
                            delete message.score;
                        continue;
                    }
                case 3: {
                        if (wireType !== 2)
                            break;
                        if (!(message.closedHand && message.closedHand.length))
                            message.closedHand = [];
                        message.closedHand.push($root.game.Tile.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                case 4: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.handSize = value;
                        else
                            delete message.handSize;
                        continue;
                    }
                case 5: {
                        if (wireType !== 2)
                            break;
                        if (!(message.openMelds && message.openMelds.length))
                            message.openMelds = [];
                        message.openMelds.push($root.game.Meld.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                case 6: {
                        if (wireType !== 2)
                            break;
                        if (!(message.discards && message.discards.length))
                            message.discards = [];
                        message.discards.push($root.game.Tile.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                case 7: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.seatWind = value;
                        else
                            delete message.seatWind;
                        continue;
                    }
                case 8: {
                        if (wireType !== 2)
                            break;
                        if (!(message.flowerMelds && message.flowerMelds.length))
                            message.flowerMelds = [];
                        message.flowerMelds.push($root.game.Tile.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                case 9: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.hasBuddingDirectKong = value;
                        else
                            delete message.hasBuddingDirectKong;
                        continue;
                    }
                case 10: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.hasBloomingDirectKong = value;
                        else
                            delete message.hasBloomingDirectKong;
                        continue;
                    }
                case 11: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.hasBuddingClosedKong = value;
                        else
                            delete message.hasBuddingClosedKong;
                        continue;
                    }
                case 12: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.hasBloomingClosedKong = value;
                        else
                            delete message.hasBloomingClosedKong;
                        continue;
                    }
                case 13: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.hasBuddingRiskyKong = value;
                        else
                            delete message.hasBuddingRiskyKong;
                        continue;
                    }
                case 14: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.hasBloomingRiskyKong = value;
                        else
                            delete message.hasBloomingRiskyKong;
                        continue;
                    }
                case 15: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.hasBloomingFlowerKong = value;
                        else
                            delete message.hasBloomingFlowerKong;
                        continue;
                    }
                case 16: {
                        if (wireType !== 2)
                            break;
                        if (!(message.validActions && message.validActions.length))
                            message.validActions = [];
                        message.validActions.push($root.game.PlayerAction.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                case 17: {
                        if (wireType !== 0)
                            break;
                        message.drawnTileId = reader.int32();
                        message._drawnTileId = "drawnTileId";
                        continue;
                    }
                case 18: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.shanten = value;
                        else
                            delete message.shanten;
                        continue;
                    }
                case 19: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.lastDiscardFromDrawn = value;
                        else
                            delete message.lastDiscardFromDrawn;
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a PlayerState message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.PlayerState
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.PlayerState & game.PlayerState.$Shape} PlayerState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PlayerState.decodeDelimited = function(reader) {
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
        PlayerState.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            let properties = {};
            if (message.seat != null && $Object.hasOwnProperty.call(message, "seat"))
                if (!$util.isInteger(message.seat))
                    return "seat: integer expected";
            if (message.score != null && $Object.hasOwnProperty.call(message, "score"))
                if (!$util.isInteger(message.score))
                    return "score: integer expected";
            if (message.closedHand != null && $Object.hasOwnProperty.call(message, "closedHand")) {
                if (!$Array.isArray(message.closedHand))
                    return "closedHand: array expected";
                for (let i = 0; i < message.closedHand.length; ++i) {
                    let error = $root.game.Tile.verify(message.closedHand[i], _depth + 1);
                    if (error)
                        return "closedHand." + error;
                }
            }
            if (message.handSize != null && $Object.hasOwnProperty.call(message, "handSize"))
                if (!$util.isInteger(message.handSize))
                    return "handSize: integer expected";
            if (message.openMelds != null && $Object.hasOwnProperty.call(message, "openMelds")) {
                if (!$Array.isArray(message.openMelds))
                    return "openMelds: array expected";
                for (let i = 0; i < message.openMelds.length; ++i) {
                    let error = $root.game.Meld.verify(message.openMelds[i], _depth + 1);
                    if (error)
                        return "openMelds." + error;
                }
            }
            if (message.discards != null && $Object.hasOwnProperty.call(message, "discards")) {
                if (!$Array.isArray(message.discards))
                    return "discards: array expected";
                for (let i = 0; i < message.discards.length; ++i) {
                    let error = $root.game.Tile.verify(message.discards[i], _depth + 1);
                    if (error)
                        return "discards." + error;
                }
            }
            if (message.seatWind != null && $Object.hasOwnProperty.call(message, "seatWind"))
                if (!$util.isInteger(message.seatWind))
                    return "seatWind: integer expected";
            if (message.flowerMelds != null && $Object.hasOwnProperty.call(message, "flowerMelds")) {
                if (!$Array.isArray(message.flowerMelds))
                    return "flowerMelds: array expected";
                for (let i = 0; i < message.flowerMelds.length; ++i) {
                    let error = $root.game.Tile.verify(message.flowerMelds[i], _depth + 1);
                    if (error)
                        return "flowerMelds." + error;
                }
            }
            if (message.hasBuddingDirectKong != null && $Object.hasOwnProperty.call(message, "hasBuddingDirectKong"))
                if (typeof message.hasBuddingDirectKong !== "boolean")
                    return "hasBuddingDirectKong: boolean expected";
            if (message.hasBloomingDirectKong != null && $Object.hasOwnProperty.call(message, "hasBloomingDirectKong"))
                if (typeof message.hasBloomingDirectKong !== "boolean")
                    return "hasBloomingDirectKong: boolean expected";
            if (message.hasBuddingClosedKong != null && $Object.hasOwnProperty.call(message, "hasBuddingClosedKong"))
                if (typeof message.hasBuddingClosedKong !== "boolean")
                    return "hasBuddingClosedKong: boolean expected";
            if (message.hasBloomingClosedKong != null && $Object.hasOwnProperty.call(message, "hasBloomingClosedKong"))
                if (typeof message.hasBloomingClosedKong !== "boolean")
                    return "hasBloomingClosedKong: boolean expected";
            if (message.hasBuddingRiskyKong != null && $Object.hasOwnProperty.call(message, "hasBuddingRiskyKong"))
                if (typeof message.hasBuddingRiskyKong !== "boolean")
                    return "hasBuddingRiskyKong: boolean expected";
            if (message.hasBloomingRiskyKong != null && $Object.hasOwnProperty.call(message, "hasBloomingRiskyKong"))
                if (typeof message.hasBloomingRiskyKong !== "boolean")
                    return "hasBloomingRiskyKong: boolean expected";
            if (message.hasBloomingFlowerKong != null && $Object.hasOwnProperty.call(message, "hasBloomingFlowerKong"))
                if (typeof message.hasBloomingFlowerKong !== "boolean")
                    return "hasBloomingFlowerKong: boolean expected";
            if (message.validActions != null && $Object.hasOwnProperty.call(message, "validActions")) {
                if (!$Array.isArray(message.validActions))
                    return "validActions: array expected";
                for (let i = 0; i < message.validActions.length; ++i) {
                    let error = $root.game.PlayerAction.verify(message.validActions[i], _depth + 1);
                    if (error)
                        return "validActions." + error;
                }
            }
            if (message.drawnTileId != null && $Object.hasOwnProperty.call(message, "drawnTileId")) {
                properties._drawnTileId = 1;
                if (!$util.isInteger(message.drawnTileId))
                    return "drawnTileId: integer expected";
            }
            if (message.shanten != null && $Object.hasOwnProperty.call(message, "shanten"))
                if (!$util.isInteger(message.shanten))
                    return "shanten: integer expected";
            if (message.lastDiscardFromDrawn != null && $Object.hasOwnProperty.call(message, "lastDiscardFromDrawn"))
                if (typeof message.lastDiscardFromDrawn !== "boolean")
                    return "lastDiscardFromDrawn: boolean expected";
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
        PlayerState.fromObject = function (object, _depth) {
            if (object instanceof $root.game.PlayerState)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.PlayerState: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.PlayerState();
            if (object.seat != null)
                if ($Number(object.seat) !== 0)
                    message.seat = object.seat >>> 0;
            if (object.score != null)
                if ($Number(object.score) !== 0)
                    message.score = object.score | 0;
            if (object.closedHand) {
                if (!$Array.isArray(object.closedHand))
                    throw $TypeError(".game.PlayerState.closedHand: array expected");
                message.closedHand = $Array(object.closedHand.length);
                for (let i = 0; i < object.closedHand.length; ++i) {
                    if (!$util.isObject(object.closedHand[i]))
                        throw $TypeError(".game.PlayerState.closedHand: object expected");
                    message.closedHand[i] = $root.game.Tile.fromObject(object.closedHand[i], _depth + 1);
                }
            }
            if (object.handSize != null)
                if ($Number(object.handSize) !== 0)
                    message.handSize = object.handSize >>> 0;
            if (object.openMelds) {
                if (!$Array.isArray(object.openMelds))
                    throw $TypeError(".game.PlayerState.openMelds: array expected");
                message.openMelds = $Array(object.openMelds.length);
                for (let i = 0; i < object.openMelds.length; ++i) {
                    if (!$util.isObject(object.openMelds[i]))
                        throw $TypeError(".game.PlayerState.openMelds: object expected");
                    message.openMelds[i] = $root.game.Meld.fromObject(object.openMelds[i], _depth + 1);
                }
            }
            if (object.discards) {
                if (!$Array.isArray(object.discards))
                    throw $TypeError(".game.PlayerState.discards: array expected");
                message.discards = $Array(object.discards.length);
                for (let i = 0; i < object.discards.length; ++i) {
                    if (!$util.isObject(object.discards[i]))
                        throw $TypeError(".game.PlayerState.discards: object expected");
                    message.discards[i] = $root.game.Tile.fromObject(object.discards[i], _depth + 1);
                }
            }
            if (object.seatWind != null)
                if ($Number(object.seatWind) !== 0)
                    message.seatWind = object.seatWind >>> 0;
            if (object.flowerMelds) {
                if (!$Array.isArray(object.flowerMelds))
                    throw $TypeError(".game.PlayerState.flowerMelds: array expected");
                message.flowerMelds = $Array(object.flowerMelds.length);
                for (let i = 0; i < object.flowerMelds.length; ++i) {
                    if (!$util.isObject(object.flowerMelds[i]))
                        throw $TypeError(".game.PlayerState.flowerMelds: object expected");
                    message.flowerMelds[i] = $root.game.Tile.fromObject(object.flowerMelds[i], _depth + 1);
                }
            }
            if (object.hasBuddingDirectKong != null)
                if (object.hasBuddingDirectKong)
                    message.hasBuddingDirectKong = $Boolean(object.hasBuddingDirectKong);
            if (object.hasBloomingDirectKong != null)
                if (object.hasBloomingDirectKong)
                    message.hasBloomingDirectKong = $Boolean(object.hasBloomingDirectKong);
            if (object.hasBuddingClosedKong != null)
                if (object.hasBuddingClosedKong)
                    message.hasBuddingClosedKong = $Boolean(object.hasBuddingClosedKong);
            if (object.hasBloomingClosedKong != null)
                if (object.hasBloomingClosedKong)
                    message.hasBloomingClosedKong = $Boolean(object.hasBloomingClosedKong);
            if (object.hasBuddingRiskyKong != null)
                if (object.hasBuddingRiskyKong)
                    message.hasBuddingRiskyKong = $Boolean(object.hasBuddingRiskyKong);
            if (object.hasBloomingRiskyKong != null)
                if (object.hasBloomingRiskyKong)
                    message.hasBloomingRiskyKong = $Boolean(object.hasBloomingRiskyKong);
            if (object.hasBloomingFlowerKong != null)
                if (object.hasBloomingFlowerKong)
                    message.hasBloomingFlowerKong = $Boolean(object.hasBloomingFlowerKong);
            if (object.validActions) {
                if (!$Array.isArray(object.validActions))
                    throw $TypeError(".game.PlayerState.validActions: array expected");
                message.validActions = $Array(object.validActions.length);
                for (let i = 0; i < object.validActions.length; ++i) {
                    if (!$util.isObject(object.validActions[i]))
                        throw $TypeError(".game.PlayerState.validActions: object expected");
                    message.validActions[i] = $root.game.PlayerAction.fromObject(object.validActions[i], _depth + 1);
                }
            }
            if (object.drawnTileId != null)
                message.drawnTileId = object.drawnTileId | 0;
            if (object.shanten != null)
                if ($Number(object.shanten) !== 0)
                    message.shanten = object.shanten | 0;
            if (object.lastDiscardFromDrawn != null)
                if (object.lastDiscardFromDrawn)
                    message.lastDiscardFromDrawn = $Boolean(object.lastDiscardFromDrawn);
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
        PlayerState.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
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
                object.shanten = 0;
                object.lastDiscardFromDrawn = false;
            }
            if (message.seat != null && $Object.hasOwnProperty.call(message, "seat"))
                object.seat = message.seat;
            if (message.score != null && $Object.hasOwnProperty.call(message, "score"))
                object.score = message.score;
            if (message.closedHand && message.closedHand.length) {
                object.closedHand = $Array(message.closedHand.length);
                for (let j = 0; j < message.closedHand.length; ++j)
                    object.closedHand[j] = $root.game.Tile.toObject(message.closedHand[j], options, _depth + 1);
            }
            if (message.handSize != null && $Object.hasOwnProperty.call(message, "handSize"))
                object.handSize = message.handSize;
            if (message.openMelds && message.openMelds.length) {
                object.openMelds = $Array(message.openMelds.length);
                for (let j = 0; j < message.openMelds.length; ++j)
                    object.openMelds[j] = $root.game.Meld.toObject(message.openMelds[j], options, _depth + 1);
            }
            if (message.discards && message.discards.length) {
                object.discards = $Array(message.discards.length);
                for (let j = 0; j < message.discards.length; ++j)
                    object.discards[j] = $root.game.Tile.toObject(message.discards[j], options, _depth + 1);
            }
            if (message.seatWind != null && $Object.hasOwnProperty.call(message, "seatWind"))
                object.seatWind = message.seatWind;
            if (message.flowerMelds && message.flowerMelds.length) {
                object.flowerMelds = $Array(message.flowerMelds.length);
                for (let j = 0; j < message.flowerMelds.length; ++j)
                    object.flowerMelds[j] = $root.game.Tile.toObject(message.flowerMelds[j], options, _depth + 1);
            }
            if (message.hasBuddingDirectKong != null && $Object.hasOwnProperty.call(message, "hasBuddingDirectKong"))
                object.hasBuddingDirectKong = message.hasBuddingDirectKong;
            if (message.hasBloomingDirectKong != null && $Object.hasOwnProperty.call(message, "hasBloomingDirectKong"))
                object.hasBloomingDirectKong = message.hasBloomingDirectKong;
            if (message.hasBuddingClosedKong != null && $Object.hasOwnProperty.call(message, "hasBuddingClosedKong"))
                object.hasBuddingClosedKong = message.hasBuddingClosedKong;
            if (message.hasBloomingClosedKong != null && $Object.hasOwnProperty.call(message, "hasBloomingClosedKong"))
                object.hasBloomingClosedKong = message.hasBloomingClosedKong;
            if (message.hasBuddingRiskyKong != null && $Object.hasOwnProperty.call(message, "hasBuddingRiskyKong"))
                object.hasBuddingRiskyKong = message.hasBuddingRiskyKong;
            if (message.hasBloomingRiskyKong != null && $Object.hasOwnProperty.call(message, "hasBloomingRiskyKong"))
                object.hasBloomingRiskyKong = message.hasBloomingRiskyKong;
            if (message.hasBloomingFlowerKong != null && $Object.hasOwnProperty.call(message, "hasBloomingFlowerKong"))
                object.hasBloomingFlowerKong = message.hasBloomingFlowerKong;
            if (message.validActions && message.validActions.length) {
                object.validActions = $Array(message.validActions.length);
                for (let j = 0; j < message.validActions.length; ++j)
                    object.validActions[j] = $root.game.PlayerAction.toObject(message.validActions[j], options, _depth + 1);
            }
            if (message.drawnTileId != null && $Object.hasOwnProperty.call(message, "drawnTileId"))
                object.drawnTileId = message.drawnTileId;
            if (message.shanten != null && $Object.hasOwnProperty.call(message, "shanten"))
                object.shanten = message.shanten;
            if (message.lastDiscardFromDrawn != null && $Object.hasOwnProperty.call(message, "lastDiscardFromDrawn"))
                object.lastDiscardFromDrawn = message.lastDiscardFromDrawn;
            return object;
        };

        /**
         * Converts this PlayerState to JSON.
         * @function toJSON
         * @memberof game.PlayerState
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        PlayerState.prototype.toJSON = function() {
            return PlayerState.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for PlayerState
         * @function getTypeUrl
         * @memberof game.PlayerState
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        PlayerState.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.PlayerState";
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
        const valuesById = $Object.create(null), values = $Object.create(valuesById);
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
         * @typedef {Object} game.GameState.$Properties
         * @property {string} [matchId] GameState matchId
         * @property {game.GamePhase} [phase] GameState phase
         * @property {number} [activePlayer] GameState activePlayer
         * @property {Array.<game.PlayerState.$Properties>} [players] GameState players
         * @property {number} [wallCount] GameState wallCount
         * @property {number} [handNum] GameState handNum
         * @property {game.Tile.$Properties} [activeDiscard] GameState activeDiscard
         * @property {Array.<game.Tile.$Properties>} [wildTiles] GameState wildTiles
         * @property {number} [prevailingWind] GameState prevailingWind
         * @property {string} [wallSeed] GameState wallSeed
         * @property {game.RoundResult.$Properties} [roundResult] GameState roundResult
         * @property {Array.<boolean>} [playerReady] GameState playerReady
         * @property {number} [diceSum] GameState diceSum
         * @property {number} [wangpaiStacks] GameState wangpaiStacks
         * @property {boolean} [isHaitei] GameState isHaitei
         * @property {number} [dice1] GameState dice1
         * @property {number} [dice2] GameState dice2
         * @property {number} [wangpaiTilesLeft] GameState wangpaiTilesLeft
         * @property {game.MatchMode} [matchMode] GameState matchMode
         * @property {game.ChongciConfig.$Properties} [chongciConfig] GameState chongciConfig
         * @property {game.MatchEndResult.$Properties} [matchEndResult] GameState matchEndResult
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a GameState.
         * @memberof game
         * @interface IGameState
         * @augments game.GameState.$Properties
         * @deprecated Use game.GameState.$Properties instead.
         */

        /**
         * Shape of a GameState.
         * @typedef {game.GameState.$Properties} game.GameState.$Shape
         */

        /**
         * Constructs a new GameState.
         * @memberof game
         * @classdesc Represents a GameState.
         * @constructor
         * @param {game.GameState.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const GameState = function (properties) {
            this.players = [];
            this.wildTiles = [];
            this.playerReady = [];
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.GameState.$Properties=} [properties] Properties to set
         * @returns {game.GameState} GameState instance
         * @type {{
         *   (properties: game.GameState.$Shape): game.GameState & game.GameState.$Shape;
         *   (properties?: game.GameState.$Properties): game.GameState;
         * }}
         */
        GameState.create = function(properties) {
            return new GameState(properties);
        };

        /**
         * Encodes the specified GameState message. Does not implicitly {@link game.GameState.verify|verify} messages.
         * @function encode
         * @memberof game.GameState
         * @static
         * @param {game.GameState.$Properties} message GameState message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        GameState.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.matchId != null && $Object.hasOwnProperty.call(message, "matchId") && message.matchId !== "")
                writer.uint32(/* id 1, wireType 2 =*/10).string(message.matchId);
            if (message.phase != null && $Object.hasOwnProperty.call(message, "phase") && message.phase !== 0)
                writer.uint32(/* id 2, wireType 0 =*/16).int32(message.phase);
            if (message.activePlayer != null && $Object.hasOwnProperty.call(message, "activePlayer") && message.activePlayer !== 0)
                writer.uint32(/* id 3, wireType 0 =*/24).uint32(message.activePlayer);
            if (message.players != null && message.players.length)
                for (let i = 0; i < message.players.length; ++i)
                    $root.game.PlayerState.encode(message.players[i], writer.uint32(/* id 4, wireType 2 =*/34).fork(), _depth + 1).ldelim();
            if (message.wallCount != null && $Object.hasOwnProperty.call(message, "wallCount") && message.wallCount !== 0)
                writer.uint32(/* id 5, wireType 0 =*/40).uint32(message.wallCount);
            if (message.handNum != null && $Object.hasOwnProperty.call(message, "handNum") && message.handNum !== 0)
                writer.uint32(/* id 6, wireType 0 =*/48).uint32(message.handNum);
            if (message.activeDiscard != null && $Object.hasOwnProperty.call(message, "activeDiscard"))
                $root.game.Tile.encode(message.activeDiscard, writer.uint32(/* id 7, wireType 2 =*/58).fork(), _depth + 1).ldelim();
            if (message.wildTiles != null && message.wildTiles.length)
                for (let i = 0; i < message.wildTiles.length; ++i)
                    $root.game.Tile.encode(message.wildTiles[i], writer.uint32(/* id 8, wireType 2 =*/66).fork(), _depth + 1).ldelim();
            if (message.prevailingWind != null && $Object.hasOwnProperty.call(message, "prevailingWind") && message.prevailingWind !== 0)
                writer.uint32(/* id 11, wireType 0 =*/88).uint32(message.prevailingWind);
            if (message.wallSeed != null && $Object.hasOwnProperty.call(message, "wallSeed") && message.wallSeed !== "")
                writer.uint32(/* id 12, wireType 2 =*/98).string(message.wallSeed);
            if (message.roundResult != null && $Object.hasOwnProperty.call(message, "roundResult"))
                $root.game.RoundResult.encode(message.roundResult, writer.uint32(/* id 13, wireType 2 =*/106).fork(), _depth + 1).ldelim();
            if (message.playerReady != null && message.playerReady.length) {
                writer.uint32(/* id 14, wireType 2 =*/114).fork();
                for (let i = 0; i < message.playerReady.length; ++i)
                    writer.bool(message.playerReady[i]);
                writer.ldelim();
            }
            if (message.diceSum != null && $Object.hasOwnProperty.call(message, "diceSum") && message.diceSum !== 0)
                writer.uint32(/* id 15, wireType 0 =*/120).uint32(message.diceSum);
            if (message.wangpaiStacks != null && $Object.hasOwnProperty.call(message, "wangpaiStacks") && message.wangpaiStacks !== 0)
                writer.uint32(/* id 16, wireType 0 =*/128).uint32(message.wangpaiStacks);
            if (message.isHaitei != null && $Object.hasOwnProperty.call(message, "isHaitei") && message.isHaitei !== false)
                writer.uint32(/* id 17, wireType 0 =*/136).bool(message.isHaitei);
            if (message.dice1 != null && $Object.hasOwnProperty.call(message, "dice1") && message.dice1 !== 0)
                writer.uint32(/* id 18, wireType 0 =*/144).uint32(message.dice1);
            if (message.dice2 != null && $Object.hasOwnProperty.call(message, "dice2") && message.dice2 !== 0)
                writer.uint32(/* id 19, wireType 0 =*/152).uint32(message.dice2);
            if (message.wangpaiTilesLeft != null && $Object.hasOwnProperty.call(message, "wangpaiTilesLeft") && message.wangpaiTilesLeft !== 0)
                writer.uint32(/* id 20, wireType 0 =*/160).uint32(message.wangpaiTilesLeft);
            if (message.matchMode != null && $Object.hasOwnProperty.call(message, "matchMode") && message.matchMode !== 0)
                writer.uint32(/* id 21, wireType 0 =*/168).int32(message.matchMode);
            if (message.chongciConfig != null && $Object.hasOwnProperty.call(message, "chongciConfig"))
                $root.game.ChongciConfig.encode(message.chongciConfig, writer.uint32(/* id 22, wireType 2 =*/178).fork(), _depth + 1).ldelim();
            if (message.matchEndResult != null && $Object.hasOwnProperty.call(message, "matchEndResult"))
                $root.game.MatchEndResult.encode(message.matchEndResult, writer.uint32(/* id 23, wireType 2 =*/186).fork(), _depth + 1).ldelim();
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified GameState message, length delimited. Does not implicitly {@link game.GameState.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.GameState
         * @static
         * @param {game.GameState.$Properties} message GameState message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        GameState.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a GameState message from the specified reader or buffer.
         * @function decode
         * @memberof game.GameState
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.GameState & game.GameState.$Shape} GameState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        GameState.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.GameState(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 2)
                            break;
                        if ((value = reader.stringVerify()).length)
                            message.matchId = value;
                        else
                            delete message.matchId;
                        continue;
                    }
                case 2: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.phase = value;
                        else
                            delete message.phase;
                        continue;
                    }
                case 3: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.activePlayer = value;
                        else
                            delete message.activePlayer;
                        continue;
                    }
                case 4: {
                        if (wireType !== 2)
                            break;
                        if (!(message.players && message.players.length))
                            message.players = [];
                        message.players.push($root.game.PlayerState.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                case 5: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.wallCount = value;
                        else
                            delete message.wallCount;
                        continue;
                    }
                case 6: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.handNum = value;
                        else
                            delete message.handNum;
                        continue;
                    }
                case 7: {
                        if (wireType !== 2)
                            break;
                        message.activeDiscard = $root.game.Tile.decode(reader, reader.uint32(), $undefined, _depth + 1, message.activeDiscard);
                        continue;
                    }
                case 8: {
                        if (wireType !== 2)
                            break;
                        if (!(message.wildTiles && message.wildTiles.length))
                            message.wildTiles = [];
                        message.wildTiles.push($root.game.Tile.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                case 11: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.prevailingWind = value;
                        else
                            delete message.prevailingWind;
                        continue;
                    }
                case 12: {
                        if (wireType !== 2)
                            break;
                        if ((value = reader.stringVerify()).length)
                            message.wallSeed = value;
                        else
                            delete message.wallSeed;
                        continue;
                    }
                case 13: {
                        if (wireType !== 2)
                            break;
                        message.roundResult = $root.game.RoundResult.decode(reader, reader.uint32(), $undefined, _depth + 1, message.roundResult);
                        continue;
                    }
                case 14: {
                        if (wireType === 2) {
                            if (!(message.playerReady && message.playerReady.length))
                                message.playerReady = [];
                            let end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.playerReady.push(reader.bool());
                            continue;
                        }
                        if (wireType !== 0)
                            break;
                        if (!(message.playerReady && message.playerReady.length))
                            message.playerReady = [];
                        message.playerReady.push(reader.bool());
                        continue;
                    }
                case 15: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.diceSum = value;
                        else
                            delete message.diceSum;
                        continue;
                    }
                case 16: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.wangpaiStacks = value;
                        else
                            delete message.wangpaiStacks;
                        continue;
                    }
                case 17: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.isHaitei = value;
                        else
                            delete message.isHaitei;
                        continue;
                    }
                case 18: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.dice1 = value;
                        else
                            delete message.dice1;
                        continue;
                    }
                case 19: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.dice2 = value;
                        else
                            delete message.dice2;
                        continue;
                    }
                case 20: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.wangpaiTilesLeft = value;
                        else
                            delete message.wangpaiTilesLeft;
                        continue;
                    }
                case 21: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.matchMode = value;
                        else
                            delete message.matchMode;
                        continue;
                    }
                case 22: {
                        if (wireType !== 2)
                            break;
                        message.chongciConfig = $root.game.ChongciConfig.decode(reader, reader.uint32(), $undefined, _depth + 1, message.chongciConfig);
                        continue;
                    }
                case 23: {
                        if (wireType !== 2)
                            break;
                        message.matchEndResult = $root.game.MatchEndResult.decode(reader, reader.uint32(), $undefined, _depth + 1, message.matchEndResult);
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a GameState message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.GameState
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.GameState & game.GameState.$Shape} GameState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        GameState.decodeDelimited = function(reader) {
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
        GameState.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.matchId != null && $Object.hasOwnProperty.call(message, "matchId"))
                if (!$util.isString(message.matchId))
                    return "matchId: string expected";
            if (message.phase != null && $Object.hasOwnProperty.call(message, "phase"))
                if (typeof message.phase !== "number" || (message.phase | 0) !== message.phase)
                    return "phase: enum value expected";
            if (message.activePlayer != null && $Object.hasOwnProperty.call(message, "activePlayer"))
                if (!$util.isInteger(message.activePlayer))
                    return "activePlayer: integer expected";
            if (message.players != null && $Object.hasOwnProperty.call(message, "players")) {
                if (!$Array.isArray(message.players))
                    return "players: array expected";
                for (let i = 0; i < message.players.length; ++i) {
                    let error = $root.game.PlayerState.verify(message.players[i], _depth + 1);
                    if (error)
                        return "players." + error;
                }
            }
            if (message.wallCount != null && $Object.hasOwnProperty.call(message, "wallCount"))
                if (!$util.isInteger(message.wallCount))
                    return "wallCount: integer expected";
            if (message.handNum != null && $Object.hasOwnProperty.call(message, "handNum"))
                if (!$util.isInteger(message.handNum))
                    return "handNum: integer expected";
            if (message.activeDiscard != null && $Object.hasOwnProperty.call(message, "activeDiscard")) {
                let error = $root.game.Tile.verify(message.activeDiscard, _depth + 1);
                if (error)
                    return "activeDiscard." + error;
            }
            if (message.wildTiles != null && $Object.hasOwnProperty.call(message, "wildTiles")) {
                if (!$Array.isArray(message.wildTiles))
                    return "wildTiles: array expected";
                for (let i = 0; i < message.wildTiles.length; ++i) {
                    let error = $root.game.Tile.verify(message.wildTiles[i], _depth + 1);
                    if (error)
                        return "wildTiles." + error;
                }
            }
            if (message.prevailingWind != null && $Object.hasOwnProperty.call(message, "prevailingWind"))
                if (!$util.isInteger(message.prevailingWind))
                    return "prevailingWind: integer expected";
            if (message.wallSeed != null && $Object.hasOwnProperty.call(message, "wallSeed"))
                if (!$util.isString(message.wallSeed))
                    return "wallSeed: string expected";
            if (message.roundResult != null && $Object.hasOwnProperty.call(message, "roundResult")) {
                let error = $root.game.RoundResult.verify(message.roundResult, _depth + 1);
                if (error)
                    return "roundResult." + error;
            }
            if (message.playerReady != null && $Object.hasOwnProperty.call(message, "playerReady")) {
                if (!$Array.isArray(message.playerReady))
                    return "playerReady: array expected";
                for (let i = 0; i < message.playerReady.length; ++i)
                    if (typeof message.playerReady[i] !== "boolean")
                        return "playerReady: boolean[] expected";
            }
            if (message.diceSum != null && $Object.hasOwnProperty.call(message, "diceSum"))
                if (!$util.isInteger(message.diceSum))
                    return "diceSum: integer expected";
            if (message.wangpaiStacks != null && $Object.hasOwnProperty.call(message, "wangpaiStacks"))
                if (!$util.isInteger(message.wangpaiStacks))
                    return "wangpaiStacks: integer expected";
            if (message.isHaitei != null && $Object.hasOwnProperty.call(message, "isHaitei"))
                if (typeof message.isHaitei !== "boolean")
                    return "isHaitei: boolean expected";
            if (message.dice1 != null && $Object.hasOwnProperty.call(message, "dice1"))
                if (!$util.isInteger(message.dice1))
                    return "dice1: integer expected";
            if (message.dice2 != null && $Object.hasOwnProperty.call(message, "dice2"))
                if (!$util.isInteger(message.dice2))
                    return "dice2: integer expected";
            if (message.wangpaiTilesLeft != null && $Object.hasOwnProperty.call(message, "wangpaiTilesLeft"))
                if (!$util.isInteger(message.wangpaiTilesLeft))
                    return "wangpaiTilesLeft: integer expected";
            if (message.matchMode != null && $Object.hasOwnProperty.call(message, "matchMode"))
                if (typeof message.matchMode !== "number" || (message.matchMode | 0) !== message.matchMode)
                    return "matchMode: enum value expected";
            if (message.chongciConfig != null && $Object.hasOwnProperty.call(message, "chongciConfig")) {
                let error = $root.game.ChongciConfig.verify(message.chongciConfig, _depth + 1);
                if (error)
                    return "chongciConfig." + error;
            }
            if (message.matchEndResult != null && $Object.hasOwnProperty.call(message, "matchEndResult")) {
                let error = $root.game.MatchEndResult.verify(message.matchEndResult, _depth + 1);
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
        GameState.fromObject = function (object, _depth) {
            if (object instanceof $root.game.GameState)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.GameState: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.GameState();
            if (object.matchId != null)
                if (typeof object.matchId !== "string" || object.matchId.length)
                    message.matchId = $String(object.matchId);
            if (object.phase !== 0 && (typeof object.phase !== "string" || $root.game.GamePhase[object.phase] !== 0))
                switch (object.phase) {
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
                default:
                    if (typeof object.phase === "number" && (object.phase | 0) === object.phase)
                        message.phase = object.phase;
                }
            if (object.activePlayer != null)
                if ($Number(object.activePlayer) !== 0)
                    message.activePlayer = object.activePlayer >>> 0;
            if (object.players) {
                if (!$Array.isArray(object.players))
                    throw $TypeError(".game.GameState.players: array expected");
                message.players = $Array(object.players.length);
                for (let i = 0; i < object.players.length; ++i) {
                    if (!$util.isObject(object.players[i]))
                        throw $TypeError(".game.GameState.players: object expected");
                    message.players[i] = $root.game.PlayerState.fromObject(object.players[i], _depth + 1);
                }
            }
            if (object.wallCount != null)
                if ($Number(object.wallCount) !== 0)
                    message.wallCount = object.wallCount >>> 0;
            if (object.handNum != null)
                if ($Number(object.handNum) !== 0)
                    message.handNum = object.handNum >>> 0;
            if (object.activeDiscard != null) {
                if (!$util.isObject(object.activeDiscard))
                    throw $TypeError(".game.GameState.activeDiscard: object expected");
                message.activeDiscard = $root.game.Tile.fromObject(object.activeDiscard, _depth + 1);
            }
            if (object.wildTiles) {
                if (!$Array.isArray(object.wildTiles))
                    throw $TypeError(".game.GameState.wildTiles: array expected");
                message.wildTiles = $Array(object.wildTiles.length);
                for (let i = 0; i < object.wildTiles.length; ++i) {
                    if (!$util.isObject(object.wildTiles[i]))
                        throw $TypeError(".game.GameState.wildTiles: object expected");
                    message.wildTiles[i] = $root.game.Tile.fromObject(object.wildTiles[i], _depth + 1);
                }
            }
            if (object.prevailingWind != null)
                if ($Number(object.prevailingWind) !== 0)
                    message.prevailingWind = object.prevailingWind >>> 0;
            if (object.wallSeed != null)
                if (typeof object.wallSeed !== "string" || object.wallSeed.length)
                    message.wallSeed = $String(object.wallSeed);
            if (object.roundResult != null) {
                if (!$util.isObject(object.roundResult))
                    throw $TypeError(".game.GameState.roundResult: object expected");
                message.roundResult = $root.game.RoundResult.fromObject(object.roundResult, _depth + 1);
            }
            if (object.playerReady) {
                if (!$Array.isArray(object.playerReady))
                    throw $TypeError(".game.GameState.playerReady: array expected");
                message.playerReady = $Array(object.playerReady.length);
                for (let i = 0; i < object.playerReady.length; ++i)
                    message.playerReady[i] = $Boolean(object.playerReady[i]);
            }
            if (object.diceSum != null)
                if ($Number(object.diceSum) !== 0)
                    message.diceSum = object.diceSum >>> 0;
            if (object.wangpaiStacks != null)
                if ($Number(object.wangpaiStacks) !== 0)
                    message.wangpaiStacks = object.wangpaiStacks >>> 0;
            if (object.isHaitei != null)
                if (object.isHaitei)
                    message.isHaitei = $Boolean(object.isHaitei);
            if (object.dice1 != null)
                if ($Number(object.dice1) !== 0)
                    message.dice1 = object.dice1 >>> 0;
            if (object.dice2 != null)
                if ($Number(object.dice2) !== 0)
                    message.dice2 = object.dice2 >>> 0;
            if (object.wangpaiTilesLeft != null)
                if ($Number(object.wangpaiTilesLeft) !== 0)
                    message.wangpaiTilesLeft = object.wangpaiTilesLeft >>> 0;
            if (object.matchMode !== 0 && (typeof object.matchMode !== "string" || $root.game.MatchMode[object.matchMode] !== 0))
                switch (object.matchMode) {
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
                default:
                    if (typeof object.matchMode === "number" && (object.matchMode | 0) === object.matchMode)
                        message.matchMode = object.matchMode;
                }
            if (object.chongciConfig != null) {
                if (!$util.isObject(object.chongciConfig))
                    throw $TypeError(".game.GameState.chongciConfig: object expected");
                message.chongciConfig = $root.game.ChongciConfig.fromObject(object.chongciConfig, _depth + 1);
            }
            if (object.matchEndResult != null) {
                if (!$util.isObject(object.matchEndResult))
                    throw $TypeError(".game.GameState.matchEndResult: object expected");
                message.matchEndResult = $root.game.MatchEndResult.fromObject(object.matchEndResult, _depth + 1);
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
        GameState.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.arrays || options.defaults) {
                object.players = [];
                object.wildTiles = [];
                object.playerReady = [];
            }
            if (options.defaults) {
                object.matchId = "";
                object.phase = options.enums === $String ? "PHASE_INIT" : 0;
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
                object.matchMode = options.enums === $String ? "MATCH_MODE_UNSPECIFIED" : 0;
                object.chongciConfig = null;
                object.matchEndResult = null;
            }
            if (message.matchId != null && $Object.hasOwnProperty.call(message, "matchId"))
                object.matchId = message.matchId;
            if (message.phase != null && $Object.hasOwnProperty.call(message, "phase"))
                object.phase = options.enums === $String ? $root.game.GamePhase[message.phase] === $undefined ? message.phase : $root.game.GamePhase[message.phase] : message.phase;
            if (message.activePlayer != null && $Object.hasOwnProperty.call(message, "activePlayer"))
                object.activePlayer = message.activePlayer;
            if (message.players && message.players.length) {
                object.players = $Array(message.players.length);
                for (let j = 0; j < message.players.length; ++j)
                    object.players[j] = $root.game.PlayerState.toObject(message.players[j], options, _depth + 1);
            }
            if (message.wallCount != null && $Object.hasOwnProperty.call(message, "wallCount"))
                object.wallCount = message.wallCount;
            if (message.handNum != null && $Object.hasOwnProperty.call(message, "handNum"))
                object.handNum = message.handNum;
            if (message.activeDiscard != null && $Object.hasOwnProperty.call(message, "activeDiscard"))
                object.activeDiscard = $root.game.Tile.toObject(message.activeDiscard, options, _depth + 1);
            if (message.wildTiles && message.wildTiles.length) {
                object.wildTiles = $Array(message.wildTiles.length);
                for (let j = 0; j < message.wildTiles.length; ++j)
                    object.wildTiles[j] = $root.game.Tile.toObject(message.wildTiles[j], options, _depth + 1);
            }
            if (message.prevailingWind != null && $Object.hasOwnProperty.call(message, "prevailingWind"))
                object.prevailingWind = message.prevailingWind;
            if (message.wallSeed != null && $Object.hasOwnProperty.call(message, "wallSeed"))
                object.wallSeed = message.wallSeed;
            if (message.roundResult != null && $Object.hasOwnProperty.call(message, "roundResult"))
                object.roundResult = $root.game.RoundResult.toObject(message.roundResult, options, _depth + 1);
            if (message.playerReady && message.playerReady.length) {
                object.playerReady = $Array(message.playerReady.length);
                for (let j = 0; j < message.playerReady.length; ++j)
                    object.playerReady[j] = message.playerReady[j];
            }
            if (message.diceSum != null && $Object.hasOwnProperty.call(message, "diceSum"))
                object.diceSum = message.diceSum;
            if (message.wangpaiStacks != null && $Object.hasOwnProperty.call(message, "wangpaiStacks"))
                object.wangpaiStacks = message.wangpaiStacks;
            if (message.isHaitei != null && $Object.hasOwnProperty.call(message, "isHaitei"))
                object.isHaitei = message.isHaitei;
            if (message.dice1 != null && $Object.hasOwnProperty.call(message, "dice1"))
                object.dice1 = message.dice1;
            if (message.dice2 != null && $Object.hasOwnProperty.call(message, "dice2"))
                object.dice2 = message.dice2;
            if (message.wangpaiTilesLeft != null && $Object.hasOwnProperty.call(message, "wangpaiTilesLeft"))
                object.wangpaiTilesLeft = message.wangpaiTilesLeft;
            if (message.matchMode != null && $Object.hasOwnProperty.call(message, "matchMode"))
                object.matchMode = options.enums === $String ? $root.game.MatchMode[message.matchMode] === $undefined ? message.matchMode : $root.game.MatchMode[message.matchMode] : message.matchMode;
            if (message.chongciConfig != null && $Object.hasOwnProperty.call(message, "chongciConfig"))
                object.chongciConfig = $root.game.ChongciConfig.toObject(message.chongciConfig, options, _depth + 1);
            if (message.matchEndResult != null && $Object.hasOwnProperty.call(message, "matchEndResult"))
                object.matchEndResult = $root.game.MatchEndResult.toObject(message.matchEndResult, options, _depth + 1);
            return object;
        };

        /**
         * Converts this GameState to JSON.
         * @function toJSON
         * @memberof game.GameState
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        GameState.prototype.toJSON = function() {
            return GameState.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for GameState
         * @function getTypeUrl
         * @memberof game.GameState
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        GameState.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.GameState";
        };

        return GameState;
    })();

    game.ScoreEntry = (function() {

        /**
         * Properties of a ScoreEntry.
         * @typedef {Object} game.ScoreEntry.$Properties
         * @property {string} [patternName] ScoreEntry patternName
         * @property {number} [points] ScoreEntry points
         * @property {string} [patternId] ScoreEntry patternId
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a ScoreEntry.
         * @memberof game
         * @interface IScoreEntry
         * @augments game.ScoreEntry.$Properties
         * @deprecated Use game.ScoreEntry.$Properties instead.
         */

        /**
         * Shape of a ScoreEntry.
         * @typedef {game.ScoreEntry.$Properties} game.ScoreEntry.$Shape
         */

        /**
         * Constructs a new ScoreEntry.
         * @memberof game
         * @classdesc Represents a ScoreEntry.
         * @constructor
         * @param {game.ScoreEntry.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const ScoreEntry = function (properties) {
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * ScoreEntry patternId.
         * @member {string} patternId
         * @memberof game.ScoreEntry
         * @instance
         */
        ScoreEntry.prototype.patternId = "";

        /**
         * Creates a new ScoreEntry instance using the specified properties.
         * @function create
         * @memberof game.ScoreEntry
         * @static
         * @param {game.ScoreEntry.$Properties=} [properties] Properties to set
         * @returns {game.ScoreEntry} ScoreEntry instance
         * @type {{
         *   (properties: game.ScoreEntry.$Shape): game.ScoreEntry & game.ScoreEntry.$Shape;
         *   (properties?: game.ScoreEntry.$Properties): game.ScoreEntry;
         * }}
         */
        ScoreEntry.create = function(properties) {
            return new ScoreEntry(properties);
        };

        /**
         * Encodes the specified ScoreEntry message. Does not implicitly {@link game.ScoreEntry.verify|verify} messages.
         * @function encode
         * @memberof game.ScoreEntry
         * @static
         * @param {game.ScoreEntry.$Properties} message ScoreEntry message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        ScoreEntry.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.patternName != null && $Object.hasOwnProperty.call(message, "patternName") && message.patternName !== "")
                writer.uint32(/* id 1, wireType 2 =*/10).string(message.patternName);
            if (message.points != null && $Object.hasOwnProperty.call(message, "points") && message.points !== 0)
                writer.uint32(/* id 2, wireType 0 =*/16).int32(message.points);
            if (message.patternId != null && $Object.hasOwnProperty.call(message, "patternId") && message.patternId !== "")
                writer.uint32(/* id 3, wireType 2 =*/26).string(message.patternId);
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified ScoreEntry message, length delimited. Does not implicitly {@link game.ScoreEntry.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.ScoreEntry
         * @static
         * @param {game.ScoreEntry.$Properties} message ScoreEntry message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        ScoreEntry.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a ScoreEntry message from the specified reader or buffer.
         * @function decode
         * @memberof game.ScoreEntry
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.ScoreEntry & game.ScoreEntry.$Shape} ScoreEntry
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        ScoreEntry.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.ScoreEntry(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 2)
                            break;
                        if ((value = reader.stringVerify()).length)
                            message.patternName = value;
                        else
                            delete message.patternName;
                        continue;
                    }
                case 2: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.points = value;
                        else
                            delete message.points;
                        continue;
                    }
                case 3: {
                        if (wireType !== 2)
                            break;
                        if ((value = reader.stringVerify()).length)
                            message.patternId = value;
                        else
                            delete message.patternId;
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a ScoreEntry message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.ScoreEntry
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.ScoreEntry & game.ScoreEntry.$Shape} ScoreEntry
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        ScoreEntry.decodeDelimited = function(reader) {
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
        ScoreEntry.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.patternName != null && $Object.hasOwnProperty.call(message, "patternName"))
                if (!$util.isString(message.patternName))
                    return "patternName: string expected";
            if (message.points != null && $Object.hasOwnProperty.call(message, "points"))
                if (!$util.isInteger(message.points))
                    return "points: integer expected";
            if (message.patternId != null && $Object.hasOwnProperty.call(message, "patternId"))
                if (!$util.isString(message.patternId))
                    return "patternId: string expected";
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
        ScoreEntry.fromObject = function (object, _depth) {
            if (object instanceof $root.game.ScoreEntry)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.ScoreEntry: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.ScoreEntry();
            if (object.patternName != null)
                if (typeof object.patternName !== "string" || object.patternName.length)
                    message.patternName = $String(object.patternName);
            if (object.points != null)
                if ($Number(object.points) !== 0)
                    message.points = object.points | 0;
            if (object.patternId != null)
                if (typeof object.patternId !== "string" || object.patternId.length)
                    message.patternId = $String(object.patternId);
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
        ScoreEntry.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.defaults) {
                object.patternName = "";
                object.points = 0;
                object.patternId = "";
            }
            if (message.patternName != null && $Object.hasOwnProperty.call(message, "patternName"))
                object.patternName = message.patternName;
            if (message.points != null && $Object.hasOwnProperty.call(message, "points"))
                object.points = message.points;
            if (message.patternId != null && $Object.hasOwnProperty.call(message, "patternId"))
                object.patternId = message.patternId;
            return object;
        };

        /**
         * Converts this ScoreEntry to JSON.
         * @function toJSON
         * @memberof game.ScoreEntry
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        ScoreEntry.prototype.toJSON = function() {
            return ScoreEntry.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for ScoreEntry
         * @function getTypeUrl
         * @memberof game.ScoreEntry
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        ScoreEntry.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.ScoreEntry";
        };

        return ScoreEntry;
    })();

    game.PlayerPayout = (function() {

        /**
         * Properties of a PlayerPayout.
         * @typedef {Object} game.PlayerPayout.$Properties
         * @property {number} [seat] PlayerPayout seat
         * @property {number} [amount] PlayerPayout amount
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a PlayerPayout.
         * @memberof game
         * @interface IPlayerPayout
         * @augments game.PlayerPayout.$Properties
         * @deprecated Use game.PlayerPayout.$Properties instead.
         */

        /**
         * Shape of a PlayerPayout.
         * @typedef {game.PlayerPayout.$Properties} game.PlayerPayout.$Shape
         */

        /**
         * Constructs a new PlayerPayout.
         * @memberof game
         * @classdesc Represents a PlayerPayout.
         * @constructor
         * @param {game.PlayerPayout.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const PlayerPayout = function (properties) {
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.PlayerPayout.$Properties=} [properties] Properties to set
         * @returns {game.PlayerPayout} PlayerPayout instance
         * @type {{
         *   (properties: game.PlayerPayout.$Shape): game.PlayerPayout & game.PlayerPayout.$Shape;
         *   (properties?: game.PlayerPayout.$Properties): game.PlayerPayout;
         * }}
         */
        PlayerPayout.create = function(properties) {
            return new PlayerPayout(properties);
        };

        /**
         * Encodes the specified PlayerPayout message. Does not implicitly {@link game.PlayerPayout.verify|verify} messages.
         * @function encode
         * @memberof game.PlayerPayout
         * @static
         * @param {game.PlayerPayout.$Properties} message PlayerPayout message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PlayerPayout.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.seat != null && $Object.hasOwnProperty.call(message, "seat") && message.seat !== 0)
                writer.uint32(/* id 1, wireType 0 =*/8).uint32(message.seat);
            if (message.amount != null && $Object.hasOwnProperty.call(message, "amount") && message.amount !== 0)
                writer.uint32(/* id 2, wireType 0 =*/16).int32(message.amount);
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified PlayerPayout message, length delimited. Does not implicitly {@link game.PlayerPayout.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.PlayerPayout
         * @static
         * @param {game.PlayerPayout.$Properties} message PlayerPayout message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PlayerPayout.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a PlayerPayout message from the specified reader or buffer.
         * @function decode
         * @memberof game.PlayerPayout
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.PlayerPayout & game.PlayerPayout.$Shape} PlayerPayout
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PlayerPayout.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.PlayerPayout(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.seat = value;
                        else
                            delete message.seat;
                        continue;
                    }
                case 2: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.amount = value;
                        else
                            delete message.amount;
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a PlayerPayout message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.PlayerPayout
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.PlayerPayout & game.PlayerPayout.$Shape} PlayerPayout
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PlayerPayout.decodeDelimited = function(reader) {
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
        PlayerPayout.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.seat != null && $Object.hasOwnProperty.call(message, "seat"))
                if (!$util.isInteger(message.seat))
                    return "seat: integer expected";
            if (message.amount != null && $Object.hasOwnProperty.call(message, "amount"))
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
        PlayerPayout.fromObject = function (object, _depth) {
            if (object instanceof $root.game.PlayerPayout)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.PlayerPayout: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.PlayerPayout();
            if (object.seat != null)
                if ($Number(object.seat) !== 0)
                    message.seat = object.seat >>> 0;
            if (object.amount != null)
                if ($Number(object.amount) !== 0)
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
        PlayerPayout.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.defaults) {
                object.seat = 0;
                object.amount = 0;
            }
            if (message.seat != null && $Object.hasOwnProperty.call(message, "seat"))
                object.seat = message.seat;
            if (message.amount != null && $Object.hasOwnProperty.call(message, "amount"))
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
        PlayerPayout.prototype.toJSON = function() {
            return PlayerPayout.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for PlayerPayout
         * @function getTypeUrl
         * @memberof game.PlayerPayout
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        PlayerPayout.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.PlayerPayout";
        };

        return PlayerPayout;
    })();

    game.RoundResult = (function() {

        /**
         * Properties of a RoundResult.
         * @typedef {Object} game.RoundResult.$Properties
         * @property {number} [winnerSeat] RoundResult winnerSeat
         * @property {game.ActionType} [winType] RoundResult winType
         * @property {number} [discarderSeat] RoundResult discarderSeat
         * @property {Array.<game.Tile.$Properties>} [winningHand] RoundResult winningHand
         * @property {Array.<game.Meld.$Properties>} [winningMelds] RoundResult winningMelds
         * @property {game.Tile.$Properties} [winTile] RoundResult winTile
         * @property {Array.<game.ScoreEntry.$Properties>} [breakdown] RoundResult breakdown
         * @property {number} [totalScore] RoundResult totalScore
         * @property {Array.<game.PlayerPayout.$Properties>} [payouts] RoundResult payouts
         * @property {boolean} [isDraw] RoundResult isDraw
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a RoundResult.
         * @memberof game
         * @interface IRoundResult
         * @augments game.RoundResult.$Properties
         * @deprecated Use game.RoundResult.$Properties instead.
         */

        /**
         * Shape of a RoundResult.
         * @typedef {game.RoundResult.$Properties} game.RoundResult.$Shape
         */

        /**
         * Constructs a new RoundResult.
         * @memberof game
         * @classdesc Represents a RoundResult.
         * @constructor
         * @param {game.RoundResult.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const RoundResult = function (properties) {
            this.winningHand = [];
            this.winningMelds = [];
            this.breakdown = [];
            this.payouts = [];
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.RoundResult.$Properties=} [properties] Properties to set
         * @returns {game.RoundResult} RoundResult instance
         * @type {{
         *   (properties: game.RoundResult.$Shape): game.RoundResult & game.RoundResult.$Shape;
         *   (properties?: game.RoundResult.$Properties): game.RoundResult;
         * }}
         */
        RoundResult.create = function(properties) {
            return new RoundResult(properties);
        };

        /**
         * Encodes the specified RoundResult message. Does not implicitly {@link game.RoundResult.verify|verify} messages.
         * @function encode
         * @memberof game.RoundResult
         * @static
         * @param {game.RoundResult.$Properties} message RoundResult message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        RoundResult.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.winnerSeat != null && $Object.hasOwnProperty.call(message, "winnerSeat") && message.winnerSeat !== 0)
                writer.uint32(/* id 1, wireType 0 =*/8).uint32(message.winnerSeat);
            if (message.winType != null && $Object.hasOwnProperty.call(message, "winType") && message.winType !== 0)
                writer.uint32(/* id 2, wireType 0 =*/16).int32(message.winType);
            if (message.discarderSeat != null && $Object.hasOwnProperty.call(message, "discarderSeat") && message.discarderSeat !== 0)
                writer.uint32(/* id 3, wireType 0 =*/24).uint32(message.discarderSeat);
            if (message.winningHand != null && message.winningHand.length)
                for (let i = 0; i < message.winningHand.length; ++i)
                    $root.game.Tile.encode(message.winningHand[i], writer.uint32(/* id 4, wireType 2 =*/34).fork(), _depth + 1).ldelim();
            if (message.winningMelds != null && message.winningMelds.length)
                for (let i = 0; i < message.winningMelds.length; ++i)
                    $root.game.Meld.encode(message.winningMelds[i], writer.uint32(/* id 5, wireType 2 =*/42).fork(), _depth + 1).ldelim();
            if (message.winTile != null && $Object.hasOwnProperty.call(message, "winTile"))
                $root.game.Tile.encode(message.winTile, writer.uint32(/* id 6, wireType 2 =*/50).fork(), _depth + 1).ldelim();
            if (message.breakdown != null && message.breakdown.length)
                for (let i = 0; i < message.breakdown.length; ++i)
                    $root.game.ScoreEntry.encode(message.breakdown[i], writer.uint32(/* id 7, wireType 2 =*/58).fork(), _depth + 1).ldelim();
            if (message.totalScore != null && $Object.hasOwnProperty.call(message, "totalScore") && message.totalScore !== 0)
                writer.uint32(/* id 8, wireType 0 =*/64).int32(message.totalScore);
            if (message.payouts != null && message.payouts.length)
                for (let i = 0; i < message.payouts.length; ++i)
                    $root.game.PlayerPayout.encode(message.payouts[i], writer.uint32(/* id 9, wireType 2 =*/74).fork(), _depth + 1).ldelim();
            if (message.isDraw != null && $Object.hasOwnProperty.call(message, "isDraw") && message.isDraw !== false)
                writer.uint32(/* id 10, wireType 0 =*/80).bool(message.isDraw);
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified RoundResult message, length delimited. Does not implicitly {@link game.RoundResult.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.RoundResult
         * @static
         * @param {game.RoundResult.$Properties} message RoundResult message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        RoundResult.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a RoundResult message from the specified reader or buffer.
         * @function decode
         * @memberof game.RoundResult
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.RoundResult & game.RoundResult.$Shape} RoundResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        RoundResult.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.RoundResult(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.winnerSeat = value;
                        else
                            delete message.winnerSeat;
                        continue;
                    }
                case 2: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.winType = value;
                        else
                            delete message.winType;
                        continue;
                    }
                case 3: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.discarderSeat = value;
                        else
                            delete message.discarderSeat;
                        continue;
                    }
                case 4: {
                        if (wireType !== 2)
                            break;
                        if (!(message.winningHand && message.winningHand.length))
                            message.winningHand = [];
                        message.winningHand.push($root.game.Tile.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                case 5: {
                        if (wireType !== 2)
                            break;
                        if (!(message.winningMelds && message.winningMelds.length))
                            message.winningMelds = [];
                        message.winningMelds.push($root.game.Meld.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                case 6: {
                        if (wireType !== 2)
                            break;
                        message.winTile = $root.game.Tile.decode(reader, reader.uint32(), $undefined, _depth + 1, message.winTile);
                        continue;
                    }
                case 7: {
                        if (wireType !== 2)
                            break;
                        if (!(message.breakdown && message.breakdown.length))
                            message.breakdown = [];
                        message.breakdown.push($root.game.ScoreEntry.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                case 8: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.totalScore = value;
                        else
                            delete message.totalScore;
                        continue;
                    }
                case 9: {
                        if (wireType !== 2)
                            break;
                        if (!(message.payouts && message.payouts.length))
                            message.payouts = [];
                        message.payouts.push($root.game.PlayerPayout.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                case 10: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.isDraw = value;
                        else
                            delete message.isDraw;
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a RoundResult message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.RoundResult
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.RoundResult & game.RoundResult.$Shape} RoundResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        RoundResult.decodeDelimited = function(reader) {
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
        RoundResult.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.winnerSeat != null && $Object.hasOwnProperty.call(message, "winnerSeat"))
                if (!$util.isInteger(message.winnerSeat))
                    return "winnerSeat: integer expected";
            if (message.winType != null && $Object.hasOwnProperty.call(message, "winType"))
                if (typeof message.winType !== "number" || (message.winType | 0) !== message.winType)
                    return "winType: enum value expected";
            if (message.discarderSeat != null && $Object.hasOwnProperty.call(message, "discarderSeat"))
                if (!$util.isInteger(message.discarderSeat))
                    return "discarderSeat: integer expected";
            if (message.winningHand != null && $Object.hasOwnProperty.call(message, "winningHand")) {
                if (!$Array.isArray(message.winningHand))
                    return "winningHand: array expected";
                for (let i = 0; i < message.winningHand.length; ++i) {
                    let error = $root.game.Tile.verify(message.winningHand[i], _depth + 1);
                    if (error)
                        return "winningHand." + error;
                }
            }
            if (message.winningMelds != null && $Object.hasOwnProperty.call(message, "winningMelds")) {
                if (!$Array.isArray(message.winningMelds))
                    return "winningMelds: array expected";
                for (let i = 0; i < message.winningMelds.length; ++i) {
                    let error = $root.game.Meld.verify(message.winningMelds[i], _depth + 1);
                    if (error)
                        return "winningMelds." + error;
                }
            }
            if (message.winTile != null && $Object.hasOwnProperty.call(message, "winTile")) {
                let error = $root.game.Tile.verify(message.winTile, _depth + 1);
                if (error)
                    return "winTile." + error;
            }
            if (message.breakdown != null && $Object.hasOwnProperty.call(message, "breakdown")) {
                if (!$Array.isArray(message.breakdown))
                    return "breakdown: array expected";
                for (let i = 0; i < message.breakdown.length; ++i) {
                    let error = $root.game.ScoreEntry.verify(message.breakdown[i], _depth + 1);
                    if (error)
                        return "breakdown." + error;
                }
            }
            if (message.totalScore != null && $Object.hasOwnProperty.call(message, "totalScore"))
                if (!$util.isInteger(message.totalScore))
                    return "totalScore: integer expected";
            if (message.payouts != null && $Object.hasOwnProperty.call(message, "payouts")) {
                if (!$Array.isArray(message.payouts))
                    return "payouts: array expected";
                for (let i = 0; i < message.payouts.length; ++i) {
                    let error = $root.game.PlayerPayout.verify(message.payouts[i], _depth + 1);
                    if (error)
                        return "payouts." + error;
                }
            }
            if (message.isDraw != null && $Object.hasOwnProperty.call(message, "isDraw"))
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
        RoundResult.fromObject = function (object, _depth) {
            if (object instanceof $root.game.RoundResult)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.RoundResult: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.RoundResult();
            if (object.winnerSeat != null)
                if ($Number(object.winnerSeat) !== 0)
                    message.winnerSeat = object.winnerSeat >>> 0;
            if (object.winType !== 0 && (typeof object.winType !== "string" || $root.game.ActionType[object.winType] !== 0))
                switch (object.winType) {
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
                default:
                    if (typeof object.winType === "number" && (object.winType | 0) === object.winType)
                        message.winType = object.winType;
                }
            if (object.discarderSeat != null)
                if ($Number(object.discarderSeat) !== 0)
                    message.discarderSeat = object.discarderSeat >>> 0;
            if (object.winningHand) {
                if (!$Array.isArray(object.winningHand))
                    throw $TypeError(".game.RoundResult.winningHand: array expected");
                message.winningHand = $Array(object.winningHand.length);
                for (let i = 0; i < object.winningHand.length; ++i) {
                    if (!$util.isObject(object.winningHand[i]))
                        throw $TypeError(".game.RoundResult.winningHand: object expected");
                    message.winningHand[i] = $root.game.Tile.fromObject(object.winningHand[i], _depth + 1);
                }
            }
            if (object.winningMelds) {
                if (!$Array.isArray(object.winningMelds))
                    throw $TypeError(".game.RoundResult.winningMelds: array expected");
                message.winningMelds = $Array(object.winningMelds.length);
                for (let i = 0; i < object.winningMelds.length; ++i) {
                    if (!$util.isObject(object.winningMelds[i]))
                        throw $TypeError(".game.RoundResult.winningMelds: object expected");
                    message.winningMelds[i] = $root.game.Meld.fromObject(object.winningMelds[i], _depth + 1);
                }
            }
            if (object.winTile != null) {
                if (!$util.isObject(object.winTile))
                    throw $TypeError(".game.RoundResult.winTile: object expected");
                message.winTile = $root.game.Tile.fromObject(object.winTile, _depth + 1);
            }
            if (object.breakdown) {
                if (!$Array.isArray(object.breakdown))
                    throw $TypeError(".game.RoundResult.breakdown: array expected");
                message.breakdown = $Array(object.breakdown.length);
                for (let i = 0; i < object.breakdown.length; ++i) {
                    if (!$util.isObject(object.breakdown[i]))
                        throw $TypeError(".game.RoundResult.breakdown: object expected");
                    message.breakdown[i] = $root.game.ScoreEntry.fromObject(object.breakdown[i], _depth + 1);
                }
            }
            if (object.totalScore != null)
                if ($Number(object.totalScore) !== 0)
                    message.totalScore = object.totalScore | 0;
            if (object.payouts) {
                if (!$Array.isArray(object.payouts))
                    throw $TypeError(".game.RoundResult.payouts: array expected");
                message.payouts = $Array(object.payouts.length);
                for (let i = 0; i < object.payouts.length; ++i) {
                    if (!$util.isObject(object.payouts[i]))
                        throw $TypeError(".game.RoundResult.payouts: object expected");
                    message.payouts[i] = $root.game.PlayerPayout.fromObject(object.payouts[i], _depth + 1);
                }
            }
            if (object.isDraw != null)
                if (object.isDraw)
                    message.isDraw = $Boolean(object.isDraw);
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
        RoundResult.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.arrays || options.defaults) {
                object.winningHand = [];
                object.winningMelds = [];
                object.breakdown = [];
                object.payouts = [];
            }
            if (options.defaults) {
                object.winnerSeat = 0;
                object.winType = options.enums === $String ? "ACTION_UNKNOWN" : 0;
                object.discarderSeat = 0;
                object.winTile = null;
                object.totalScore = 0;
                object.isDraw = false;
            }
            if (message.winnerSeat != null && $Object.hasOwnProperty.call(message, "winnerSeat"))
                object.winnerSeat = message.winnerSeat;
            if (message.winType != null && $Object.hasOwnProperty.call(message, "winType"))
                object.winType = options.enums === $String ? $root.game.ActionType[message.winType] === $undefined ? message.winType : $root.game.ActionType[message.winType] : message.winType;
            if (message.discarderSeat != null && $Object.hasOwnProperty.call(message, "discarderSeat"))
                object.discarderSeat = message.discarderSeat;
            if (message.winningHand && message.winningHand.length) {
                object.winningHand = $Array(message.winningHand.length);
                for (let j = 0; j < message.winningHand.length; ++j)
                    object.winningHand[j] = $root.game.Tile.toObject(message.winningHand[j], options, _depth + 1);
            }
            if (message.winningMelds && message.winningMelds.length) {
                object.winningMelds = $Array(message.winningMelds.length);
                for (let j = 0; j < message.winningMelds.length; ++j)
                    object.winningMelds[j] = $root.game.Meld.toObject(message.winningMelds[j], options, _depth + 1);
            }
            if (message.winTile != null && $Object.hasOwnProperty.call(message, "winTile"))
                object.winTile = $root.game.Tile.toObject(message.winTile, options, _depth + 1);
            if (message.breakdown && message.breakdown.length) {
                object.breakdown = $Array(message.breakdown.length);
                for (let j = 0; j < message.breakdown.length; ++j)
                    object.breakdown[j] = $root.game.ScoreEntry.toObject(message.breakdown[j], options, _depth + 1);
            }
            if (message.totalScore != null && $Object.hasOwnProperty.call(message, "totalScore"))
                object.totalScore = message.totalScore;
            if (message.payouts && message.payouts.length) {
                object.payouts = $Array(message.payouts.length);
                for (let j = 0; j < message.payouts.length; ++j)
                    object.payouts[j] = $root.game.PlayerPayout.toObject(message.payouts[j], options, _depth + 1);
            }
            if (message.isDraw != null && $Object.hasOwnProperty.call(message, "isDraw"))
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
        RoundResult.prototype.toJSON = function() {
            return RoundResult.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for RoundResult
         * @function getTypeUrl
         * @memberof game.RoundResult
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        RoundResult.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.RoundResult";
        };

        return RoundResult;
    })();

    game.RoundOutcome = (function() {

        /**
         * Properties of a RoundOutcome.
         * @typedef {Object} game.RoundOutcome.$Properties
         * @property {boolean} [isDraw] RoundOutcome isDraw
         * @property {number} [winnerSeat] RoundOutcome winnerSeat
         * @property {game.ActionType} [winType] RoundOutcome winType
         * @property {number} [discarderSeat] RoundOutcome discarderSeat
         * @property {number} [totalScore] RoundOutcome totalScore
         * @property {Array.<game.PlayerPayout.$Properties>} [payouts] RoundOutcome payouts
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a RoundOutcome.
         * @memberof game
         * @interface IRoundOutcome
         * @augments game.RoundOutcome.$Properties
         * @deprecated Use game.RoundOutcome.$Properties instead.
         */

        /**
         * Shape of a RoundOutcome.
         * @typedef {game.RoundOutcome.$Properties} game.RoundOutcome.$Shape
         */

        /**
         * Constructs a new RoundOutcome.
         * @memberof game
         * @classdesc Represents a RoundOutcome.
         * @constructor
         * @param {game.RoundOutcome.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const RoundOutcome = function (properties) {
            this.payouts = [];
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.RoundOutcome.$Properties=} [properties] Properties to set
         * @returns {game.RoundOutcome} RoundOutcome instance
         * @type {{
         *   (properties: game.RoundOutcome.$Shape): game.RoundOutcome & game.RoundOutcome.$Shape;
         *   (properties?: game.RoundOutcome.$Properties): game.RoundOutcome;
         * }}
         */
        RoundOutcome.create = function(properties) {
            return new RoundOutcome(properties);
        };

        /**
         * Encodes the specified RoundOutcome message. Does not implicitly {@link game.RoundOutcome.verify|verify} messages.
         * @function encode
         * @memberof game.RoundOutcome
         * @static
         * @param {game.RoundOutcome.$Properties} message RoundOutcome message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        RoundOutcome.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.isDraw != null && $Object.hasOwnProperty.call(message, "isDraw") && message.isDraw !== false)
                writer.uint32(/* id 1, wireType 0 =*/8).bool(message.isDraw);
            if (message.winnerSeat != null && $Object.hasOwnProperty.call(message, "winnerSeat") && message.winnerSeat !== 0)
                writer.uint32(/* id 2, wireType 0 =*/16).uint32(message.winnerSeat);
            if (message.winType != null && $Object.hasOwnProperty.call(message, "winType") && message.winType !== 0)
                writer.uint32(/* id 3, wireType 0 =*/24).int32(message.winType);
            if (message.discarderSeat != null && $Object.hasOwnProperty.call(message, "discarderSeat") && message.discarderSeat !== 0)
                writer.uint32(/* id 4, wireType 0 =*/32).uint32(message.discarderSeat);
            if (message.totalScore != null && $Object.hasOwnProperty.call(message, "totalScore") && message.totalScore !== 0)
                writer.uint32(/* id 5, wireType 0 =*/40).int32(message.totalScore);
            if (message.payouts != null && message.payouts.length)
                for (let i = 0; i < message.payouts.length; ++i)
                    $root.game.PlayerPayout.encode(message.payouts[i], writer.uint32(/* id 6, wireType 2 =*/50).fork(), _depth + 1).ldelim();
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified RoundOutcome message, length delimited. Does not implicitly {@link game.RoundOutcome.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.RoundOutcome
         * @static
         * @param {game.RoundOutcome.$Properties} message RoundOutcome message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        RoundOutcome.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a RoundOutcome message from the specified reader or buffer.
         * @function decode
         * @memberof game.RoundOutcome
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.RoundOutcome & game.RoundOutcome.$Shape} RoundOutcome
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        RoundOutcome.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.RoundOutcome(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.isDraw = value;
                        else
                            delete message.isDraw;
                        continue;
                    }
                case 2: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.winnerSeat = value;
                        else
                            delete message.winnerSeat;
                        continue;
                    }
                case 3: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.winType = value;
                        else
                            delete message.winType;
                        continue;
                    }
                case 4: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.discarderSeat = value;
                        else
                            delete message.discarderSeat;
                        continue;
                    }
                case 5: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.totalScore = value;
                        else
                            delete message.totalScore;
                        continue;
                    }
                case 6: {
                        if (wireType !== 2)
                            break;
                        if (!(message.payouts && message.payouts.length))
                            message.payouts = [];
                        message.payouts.push($root.game.PlayerPayout.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a RoundOutcome message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.RoundOutcome
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.RoundOutcome & game.RoundOutcome.$Shape} RoundOutcome
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        RoundOutcome.decodeDelimited = function(reader) {
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
        RoundOutcome.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.isDraw != null && $Object.hasOwnProperty.call(message, "isDraw"))
                if (typeof message.isDraw !== "boolean")
                    return "isDraw: boolean expected";
            if (message.winnerSeat != null && $Object.hasOwnProperty.call(message, "winnerSeat"))
                if (!$util.isInteger(message.winnerSeat))
                    return "winnerSeat: integer expected";
            if (message.winType != null && $Object.hasOwnProperty.call(message, "winType"))
                if (typeof message.winType !== "number" || (message.winType | 0) !== message.winType)
                    return "winType: enum value expected";
            if (message.discarderSeat != null && $Object.hasOwnProperty.call(message, "discarderSeat"))
                if (!$util.isInteger(message.discarderSeat))
                    return "discarderSeat: integer expected";
            if (message.totalScore != null && $Object.hasOwnProperty.call(message, "totalScore"))
                if (!$util.isInteger(message.totalScore))
                    return "totalScore: integer expected";
            if (message.payouts != null && $Object.hasOwnProperty.call(message, "payouts")) {
                if (!$Array.isArray(message.payouts))
                    return "payouts: array expected";
                for (let i = 0; i < message.payouts.length; ++i) {
                    let error = $root.game.PlayerPayout.verify(message.payouts[i], _depth + 1);
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
        RoundOutcome.fromObject = function (object, _depth) {
            if (object instanceof $root.game.RoundOutcome)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.RoundOutcome: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.RoundOutcome();
            if (object.isDraw != null)
                if (object.isDraw)
                    message.isDraw = $Boolean(object.isDraw);
            if (object.winnerSeat != null)
                if ($Number(object.winnerSeat) !== 0)
                    message.winnerSeat = object.winnerSeat >>> 0;
            if (object.winType !== 0 && (typeof object.winType !== "string" || $root.game.ActionType[object.winType] !== 0))
                switch (object.winType) {
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
                default:
                    if (typeof object.winType === "number" && (object.winType | 0) === object.winType)
                        message.winType = object.winType;
                }
            if (object.discarderSeat != null)
                if ($Number(object.discarderSeat) !== 0)
                    message.discarderSeat = object.discarderSeat >>> 0;
            if (object.totalScore != null)
                if ($Number(object.totalScore) !== 0)
                    message.totalScore = object.totalScore | 0;
            if (object.payouts) {
                if (!$Array.isArray(object.payouts))
                    throw $TypeError(".game.RoundOutcome.payouts: array expected");
                message.payouts = $Array(object.payouts.length);
                for (let i = 0; i < object.payouts.length; ++i) {
                    if (!$util.isObject(object.payouts[i]))
                        throw $TypeError(".game.RoundOutcome.payouts: object expected");
                    message.payouts[i] = $root.game.PlayerPayout.fromObject(object.payouts[i], _depth + 1);
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
        RoundOutcome.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.arrays || options.defaults)
                object.payouts = [];
            if (options.defaults) {
                object.isDraw = false;
                object.winnerSeat = 0;
                object.winType = options.enums === $String ? "ACTION_UNKNOWN" : 0;
                object.discarderSeat = 0;
                object.totalScore = 0;
            }
            if (message.isDraw != null && $Object.hasOwnProperty.call(message, "isDraw"))
                object.isDraw = message.isDraw;
            if (message.winnerSeat != null && $Object.hasOwnProperty.call(message, "winnerSeat"))
                object.winnerSeat = message.winnerSeat;
            if (message.winType != null && $Object.hasOwnProperty.call(message, "winType"))
                object.winType = options.enums === $String ? $root.game.ActionType[message.winType] === $undefined ? message.winType : $root.game.ActionType[message.winType] : message.winType;
            if (message.discarderSeat != null && $Object.hasOwnProperty.call(message, "discarderSeat"))
                object.discarderSeat = message.discarderSeat;
            if (message.totalScore != null && $Object.hasOwnProperty.call(message, "totalScore"))
                object.totalScore = message.totalScore;
            if (message.payouts && message.payouts.length) {
                object.payouts = $Array(message.payouts.length);
                for (let j = 0; j < message.payouts.length; ++j)
                    object.payouts[j] = $root.game.PlayerPayout.toObject(message.payouts[j], options, _depth + 1);
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
        RoundOutcome.prototype.toJSON = function() {
            return RoundOutcome.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for RoundOutcome
         * @function getTypeUrl
         * @memberof game.RoundOutcome
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        RoundOutcome.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.RoundOutcome";
        };

        return RoundOutcome;
    })();

    game.EnvConfig = (function() {

        /**
         * Properties of an EnvConfig.
         * @typedef {Object} game.EnvConfig.$Properties
         * @property {Array.<number>} [learningSeats] EnvConfig learningSeats
         * @property {boolean} [autoPlayHeuristics] EnvConfig autoPlayHeuristics
         * @property {number} [maxDecisions] EnvConfig maxDecisions
         * @property {game.MatchMode} [matchMode] EnvConfig matchMode
         * @property {game.ChongciConfig.$Properties} [chongciConfig] EnvConfig chongciConfig
         * @property {boolean} [oracleObservation] EnvConfig oracleObservation
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of an EnvConfig.
         * @memberof game
         * @interface IEnvConfig
         * @augments game.EnvConfig.$Properties
         * @deprecated Use game.EnvConfig.$Properties instead.
         */

        /**
         * Shape of an EnvConfig.
         * @typedef {game.EnvConfig.$Properties} game.EnvConfig.$Shape
         */

        /**
         * Constructs a new EnvConfig.
         * @memberof game
         * @classdesc Represents an EnvConfig.
         * @constructor
         * @param {game.EnvConfig.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const EnvConfig = function (properties) {
            this.learningSeats = [];
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * EnvConfig matchMode.
         * @member {game.MatchMode} matchMode
         * @memberof game.EnvConfig
         * @instance
         */
        EnvConfig.prototype.matchMode = 0;

        /**
         * EnvConfig chongciConfig.
         * @member {game.ChongciConfig} chongciConfig
         * @memberof game.EnvConfig
         * @instance
         */
        EnvConfig.prototype.chongciConfig = null;

        /**
         * EnvConfig oracleObservation.
         * @member {boolean} oracleObservation
         * @memberof game.EnvConfig
         * @instance
         */
        EnvConfig.prototype.oracleObservation = false;

        /**
         * Creates a new EnvConfig instance using the specified properties.
         * @function create
         * @memberof game.EnvConfig
         * @static
         * @param {game.EnvConfig.$Properties=} [properties] Properties to set
         * @returns {game.EnvConfig} EnvConfig instance
         * @type {{
         *   (properties: game.EnvConfig.$Shape): game.EnvConfig & game.EnvConfig.$Shape;
         *   (properties?: game.EnvConfig.$Properties): game.EnvConfig;
         * }}
         */
        EnvConfig.create = function(properties) {
            return new EnvConfig(properties);
        };

        /**
         * Encodes the specified EnvConfig message. Does not implicitly {@link game.EnvConfig.verify|verify} messages.
         * @function encode
         * @memberof game.EnvConfig
         * @static
         * @param {game.EnvConfig.$Properties} message EnvConfig message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvConfig.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.learningSeats != null && message.learningSeats.length) {
                writer.uint32(/* id 1, wireType 2 =*/10).fork();
                for (let i = 0; i < message.learningSeats.length; ++i)
                    writer.uint32(message.learningSeats[i]);
                writer.ldelim();
            }
            if (message.autoPlayHeuristics != null && $Object.hasOwnProperty.call(message, "autoPlayHeuristics") && message.autoPlayHeuristics !== false)
                writer.uint32(/* id 2, wireType 0 =*/16).bool(message.autoPlayHeuristics);
            if (message.maxDecisions != null && $Object.hasOwnProperty.call(message, "maxDecisions") && message.maxDecisions !== 0)
                writer.uint32(/* id 3, wireType 0 =*/24).uint32(message.maxDecisions);
            if (message.matchMode != null && $Object.hasOwnProperty.call(message, "matchMode") && message.matchMode !== 0)
                writer.uint32(/* id 4, wireType 0 =*/32).int32(message.matchMode);
            if (message.chongciConfig != null && $Object.hasOwnProperty.call(message, "chongciConfig"))
                $root.game.ChongciConfig.encode(message.chongciConfig, writer.uint32(/* id 5, wireType 2 =*/42).fork(), _depth + 1).ldelim();
            if (message.oracleObservation != null && $Object.hasOwnProperty.call(message, "oracleObservation") && message.oracleObservation !== false)
                writer.uint32(/* id 6, wireType 0 =*/48).bool(message.oracleObservation);
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified EnvConfig message, length delimited. Does not implicitly {@link game.EnvConfig.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.EnvConfig
         * @static
         * @param {game.EnvConfig.$Properties} message EnvConfig message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvConfig.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes an EnvConfig message from the specified reader or buffer.
         * @function decode
         * @memberof game.EnvConfig
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.EnvConfig & game.EnvConfig.$Shape} EnvConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvConfig.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.EnvConfig(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType === 2) {
                            if (!(message.learningSeats && message.learningSeats.length))
                                message.learningSeats = [];
                            let end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.learningSeats.push(reader.uint32());
                            continue;
                        }
                        if (wireType !== 0)
                            break;
                        if (!(message.learningSeats && message.learningSeats.length))
                            message.learningSeats = [];
                        message.learningSeats.push(reader.uint32());
                        continue;
                    }
                case 2: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.autoPlayHeuristics = value;
                        else
                            delete message.autoPlayHeuristics;
                        continue;
                    }
                case 3: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.maxDecisions = value;
                        else
                            delete message.maxDecisions;
                        continue;
                    }
                case 4: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.matchMode = value;
                        else
                            delete message.matchMode;
                        continue;
                    }
                case 5: {
                        if (wireType !== 2)
                            break;
                        message.chongciConfig = $root.game.ChongciConfig.decode(reader, reader.uint32(), $undefined, _depth + 1, message.chongciConfig);
                        continue;
                    }
                case 6: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.oracleObservation = value;
                        else
                            delete message.oracleObservation;
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes an EnvConfig message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.EnvConfig
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.EnvConfig & game.EnvConfig.$Shape} EnvConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvConfig.decodeDelimited = function(reader) {
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
        EnvConfig.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.learningSeats != null && $Object.hasOwnProperty.call(message, "learningSeats")) {
                if (!$Array.isArray(message.learningSeats))
                    return "learningSeats: array expected";
                for (let i = 0; i < message.learningSeats.length; ++i)
                    if (!$util.isInteger(message.learningSeats[i]))
                        return "learningSeats: integer[] expected";
            }
            if (message.autoPlayHeuristics != null && $Object.hasOwnProperty.call(message, "autoPlayHeuristics"))
                if (typeof message.autoPlayHeuristics !== "boolean")
                    return "autoPlayHeuristics: boolean expected";
            if (message.maxDecisions != null && $Object.hasOwnProperty.call(message, "maxDecisions"))
                if (!$util.isInteger(message.maxDecisions))
                    return "maxDecisions: integer expected";
            if (message.matchMode != null && $Object.hasOwnProperty.call(message, "matchMode"))
                if (typeof message.matchMode !== "number" || (message.matchMode | 0) !== message.matchMode)
                    return "matchMode: enum value expected";
            if (message.chongciConfig != null && $Object.hasOwnProperty.call(message, "chongciConfig")) {
                let error = $root.game.ChongciConfig.verify(message.chongciConfig, _depth + 1);
                if (error)
                    return "chongciConfig." + error;
            }
            if (message.oracleObservation != null && $Object.hasOwnProperty.call(message, "oracleObservation"))
                if (typeof message.oracleObservation !== "boolean")
                    return "oracleObservation: boolean expected";
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
        EnvConfig.fromObject = function (object, _depth) {
            if (object instanceof $root.game.EnvConfig)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.EnvConfig: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.EnvConfig();
            if (object.learningSeats) {
                if (!$Array.isArray(object.learningSeats))
                    throw $TypeError(".game.EnvConfig.learningSeats: array expected");
                message.learningSeats = $Array(object.learningSeats.length);
                for (let i = 0; i < object.learningSeats.length; ++i)
                    message.learningSeats[i] = object.learningSeats[i] >>> 0;
            }
            if (object.autoPlayHeuristics != null)
                if (object.autoPlayHeuristics)
                    message.autoPlayHeuristics = $Boolean(object.autoPlayHeuristics);
            if (object.maxDecisions != null)
                if ($Number(object.maxDecisions) !== 0)
                    message.maxDecisions = object.maxDecisions >>> 0;
            if (object.matchMode !== 0 && (typeof object.matchMode !== "string" || $root.game.MatchMode[object.matchMode] !== 0))
                switch (object.matchMode) {
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
                default:
                    if (typeof object.matchMode === "number" && (object.matchMode | 0) === object.matchMode)
                        message.matchMode = object.matchMode;
                }
            if (object.chongciConfig != null) {
                if (!$util.isObject(object.chongciConfig))
                    throw $TypeError(".game.EnvConfig.chongciConfig: object expected");
                message.chongciConfig = $root.game.ChongciConfig.fromObject(object.chongciConfig, _depth + 1);
            }
            if (object.oracleObservation != null)
                if (object.oracleObservation)
                    message.oracleObservation = $Boolean(object.oracleObservation);
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
        EnvConfig.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.arrays || options.defaults)
                object.learningSeats = [];
            if (options.defaults) {
                object.autoPlayHeuristics = false;
                object.maxDecisions = 0;
                object.matchMode = options.enums === $String ? "MATCH_MODE_UNSPECIFIED" : 0;
                object.chongciConfig = null;
                object.oracleObservation = false;
            }
            if (message.learningSeats && message.learningSeats.length) {
                object.learningSeats = $Array(message.learningSeats.length);
                for (let j = 0; j < message.learningSeats.length; ++j)
                    object.learningSeats[j] = message.learningSeats[j];
            }
            if (message.autoPlayHeuristics != null && $Object.hasOwnProperty.call(message, "autoPlayHeuristics"))
                object.autoPlayHeuristics = message.autoPlayHeuristics;
            if (message.maxDecisions != null && $Object.hasOwnProperty.call(message, "maxDecisions"))
                object.maxDecisions = message.maxDecisions;
            if (message.matchMode != null && $Object.hasOwnProperty.call(message, "matchMode"))
                object.matchMode = options.enums === $String ? $root.game.MatchMode[message.matchMode] === $undefined ? message.matchMode : $root.game.MatchMode[message.matchMode] : message.matchMode;
            if (message.chongciConfig != null && $Object.hasOwnProperty.call(message, "chongciConfig"))
                object.chongciConfig = $root.game.ChongciConfig.toObject(message.chongciConfig, options, _depth + 1);
            if (message.oracleObservation != null && $Object.hasOwnProperty.call(message, "oracleObservation"))
                object.oracleObservation = message.oracleObservation;
            return object;
        };

        /**
         * Converts this EnvConfig to JSON.
         * @function toJSON
         * @memberof game.EnvConfig
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        EnvConfig.prototype.toJSON = function() {
            return EnvConfig.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for EnvConfig
         * @function getTypeUrl
         * @memberof game.EnvConfig
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        EnvConfig.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.EnvConfig";
        };

        return EnvConfig;
    })();

    game.SeatObservation = (function() {

        /**
         * Properties of a SeatObservation.
         * @typedef {Object} game.SeatObservation.$Properties
         * @property {number} [seat] SeatObservation seat
         * @property {Array.<number>} [planes] SeatObservation planes
         * @property {number} [planeChannels] SeatObservation planeChannels
         * @property {number} [planeHeight] SeatObservation planeHeight
         * @property {number} [planeWidth] SeatObservation planeWidth
         * @property {Array.<number>} [scalars] SeatObservation scalars
         * @property {Uint8Array} [actionMask] SeatObservation actionMask
         * @property {number} [actionSpaceSize] SeatObservation actionSpaceSize
         * @property {number|Long} [decisionIndex] SeatObservation decisionIndex
         * @property {game.GamePhase} [phase] SeatObservation phase
         * @property {number} [activePlayer] SeatObservation activePlayer
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a SeatObservation.
         * @memberof game
         * @interface ISeatObservation
         * @augments game.SeatObservation.$Properties
         * @deprecated Use game.SeatObservation.$Properties instead.
         */

        /**
         * Shape of a SeatObservation.
         * @typedef {game.SeatObservation.$Properties} game.SeatObservation.$Shape
         */

        /**
         * Constructs a new SeatObservation.
         * @memberof game
         * @classdesc Represents a SeatObservation.
         * @constructor
         * @param {game.SeatObservation.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const SeatObservation = function (properties) {
            this.planes = [];
            this.scalars = [];
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.SeatObservation.$Properties=} [properties] Properties to set
         * @returns {game.SeatObservation} SeatObservation instance
         * @type {{
         *   (properties: game.SeatObservation.$Shape): game.SeatObservation & game.SeatObservation.$Shape;
         *   (properties?: game.SeatObservation.$Properties): game.SeatObservation;
         * }}
         */
        SeatObservation.create = function(properties) {
            return new SeatObservation(properties);
        };

        /**
         * Encodes the specified SeatObservation message. Does not implicitly {@link game.SeatObservation.verify|verify} messages.
         * @function encode
         * @memberof game.SeatObservation
         * @static
         * @param {game.SeatObservation.$Properties} message SeatObservation message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        SeatObservation.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.seat != null && $Object.hasOwnProperty.call(message, "seat") && message.seat !== 0)
                writer.uint32(/* id 1, wireType 0 =*/8).uint32(message.seat);
            if (message.planes != null && message.planes.length) {
                writer.uint32(/* id 2, wireType 2 =*/18).fork();
                for (let i = 0; i < message.planes.length; ++i)
                    writer.float(message.planes[i]);
                writer.ldelim();
            }
            if (message.planeChannels != null && $Object.hasOwnProperty.call(message, "planeChannels") && message.planeChannels !== 0)
                writer.uint32(/* id 3, wireType 0 =*/24).uint32(message.planeChannels);
            if (message.planeHeight != null && $Object.hasOwnProperty.call(message, "planeHeight") && message.planeHeight !== 0)
                writer.uint32(/* id 4, wireType 0 =*/32).uint32(message.planeHeight);
            if (message.planeWidth != null && $Object.hasOwnProperty.call(message, "planeWidth") && message.planeWidth !== 0)
                writer.uint32(/* id 5, wireType 0 =*/40).uint32(message.planeWidth);
            if (message.scalars != null && message.scalars.length) {
                writer.uint32(/* id 6, wireType 2 =*/50).fork();
                for (let i = 0; i < message.scalars.length; ++i)
                    writer.float(message.scalars[i]);
                writer.ldelim();
            }
            if (message.actionMask != null && $Object.hasOwnProperty.call(message, "actionMask") && message.actionMask.length)
                writer.uint32(/* id 7, wireType 2 =*/58).bytes(message.actionMask);
            if (message.actionSpaceSize != null && $Object.hasOwnProperty.call(message, "actionSpaceSize") && message.actionSpaceSize !== 0)
                writer.uint32(/* id 8, wireType 0 =*/64).uint32(message.actionSpaceSize);
            if (message.decisionIndex != null && $Object.hasOwnProperty.call(message, "decisionIndex") && (typeof message.decisionIndex === "object" ? message.decisionIndex.low || message.decisionIndex.high : message.decisionIndex !== 0))
                writer.uint32(/* id 9, wireType 0 =*/72).uint64(message.decisionIndex);
            if (message.phase != null && $Object.hasOwnProperty.call(message, "phase") && message.phase !== 0)
                writer.uint32(/* id 10, wireType 0 =*/80).int32(message.phase);
            if (message.activePlayer != null && $Object.hasOwnProperty.call(message, "activePlayer") && message.activePlayer !== 0)
                writer.uint32(/* id 11, wireType 0 =*/88).uint32(message.activePlayer);
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified SeatObservation message, length delimited. Does not implicitly {@link game.SeatObservation.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.SeatObservation
         * @static
         * @param {game.SeatObservation.$Properties} message SeatObservation message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        SeatObservation.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a SeatObservation message from the specified reader or buffer.
         * @function decode
         * @memberof game.SeatObservation
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.SeatObservation & game.SeatObservation.$Shape} SeatObservation
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        SeatObservation.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.SeatObservation(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.seat = value;
                        else
                            delete message.seat;
                        continue;
                    }
                case 2: {
                        if (wireType === 2) {
                            if (!(message.planes && message.planes.length))
                                message.planes = [];
                            let end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.planes.push(reader.float());
                            continue;
                        }
                        if (wireType !== 5)
                            break;
                        if (!(message.planes && message.planes.length))
                            message.planes = [];
                        message.planes.push(reader.float());
                        continue;
                    }
                case 3: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.planeChannels = value;
                        else
                            delete message.planeChannels;
                        continue;
                    }
                case 4: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.planeHeight = value;
                        else
                            delete message.planeHeight;
                        continue;
                    }
                case 5: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.planeWidth = value;
                        else
                            delete message.planeWidth;
                        continue;
                    }
                case 6: {
                        if (wireType === 2) {
                            if (!(message.scalars && message.scalars.length))
                                message.scalars = [];
                            let end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.scalars.push(reader.float());
                            continue;
                        }
                        if (wireType !== 5)
                            break;
                        if (!(message.scalars && message.scalars.length))
                            message.scalars = [];
                        message.scalars.push(reader.float());
                        continue;
                    }
                case 7: {
                        if (wireType !== 2)
                            break;
                        if ((value = reader.bytes()).length)
                            message.actionMask = value;
                        else
                            delete message.actionMask;
                        continue;
                    }
                case 8: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.actionSpaceSize = value;
                        else
                            delete message.actionSpaceSize;
                        continue;
                    }
                case 9: {
                        if (wireType !== 0)
                            break;
                        if (typeof (value = reader.uint64()) === "object" ? value.low || value.high : value !== 0)
                            message.decisionIndex = value;
                        else
                            delete message.decisionIndex;
                        continue;
                    }
                case 10: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.phase = value;
                        else
                            delete message.phase;
                        continue;
                    }
                case 11: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.activePlayer = value;
                        else
                            delete message.activePlayer;
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a SeatObservation message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.SeatObservation
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.SeatObservation & game.SeatObservation.$Shape} SeatObservation
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        SeatObservation.decodeDelimited = function(reader) {
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
        SeatObservation.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.seat != null && $Object.hasOwnProperty.call(message, "seat"))
                if (!$util.isInteger(message.seat))
                    return "seat: integer expected";
            if (message.planes != null && $Object.hasOwnProperty.call(message, "planes")) {
                if (!$Array.isArray(message.planes))
                    return "planes: array expected";
                for (let i = 0; i < message.planes.length; ++i)
                    if (typeof message.planes[i] !== "number")
                        return "planes: number[] expected";
            }
            if (message.planeChannels != null && $Object.hasOwnProperty.call(message, "planeChannels"))
                if (!$util.isInteger(message.planeChannels))
                    return "planeChannels: integer expected";
            if (message.planeHeight != null && $Object.hasOwnProperty.call(message, "planeHeight"))
                if (!$util.isInteger(message.planeHeight))
                    return "planeHeight: integer expected";
            if (message.planeWidth != null && $Object.hasOwnProperty.call(message, "planeWidth"))
                if (!$util.isInteger(message.planeWidth))
                    return "planeWidth: integer expected";
            if (message.scalars != null && $Object.hasOwnProperty.call(message, "scalars")) {
                if (!$Array.isArray(message.scalars))
                    return "scalars: array expected";
                for (let i = 0; i < message.scalars.length; ++i)
                    if (typeof message.scalars[i] !== "number")
                        return "scalars: number[] expected";
            }
            if (message.actionMask != null && $Object.hasOwnProperty.call(message, "actionMask"))
                if (!(message.actionMask && typeof message.actionMask.length === "number" || $util.isString(message.actionMask)))
                    return "actionMask: buffer expected";
            if (message.actionSpaceSize != null && $Object.hasOwnProperty.call(message, "actionSpaceSize"))
                if (!$util.isInteger(message.actionSpaceSize))
                    return "actionSpaceSize: integer expected";
            if (message.decisionIndex != null && $Object.hasOwnProperty.call(message, "decisionIndex"))
                if (!$util.isInteger(message.decisionIndex) && !(message.decisionIndex && $util.isInteger(message.decisionIndex.low) && $util.isInteger(message.decisionIndex.high)))
                    return "decisionIndex: integer|Long expected";
            if (message.phase != null && $Object.hasOwnProperty.call(message, "phase"))
                if (typeof message.phase !== "number" || (message.phase | 0) !== message.phase)
                    return "phase: enum value expected";
            if (message.activePlayer != null && $Object.hasOwnProperty.call(message, "activePlayer"))
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
        SeatObservation.fromObject = function (object, _depth) {
            if (object instanceof $root.game.SeatObservation)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.SeatObservation: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.SeatObservation();
            if (object.seat != null)
                if ($Number(object.seat) !== 0)
                    message.seat = object.seat >>> 0;
            if (object.planes) {
                if (!$Array.isArray(object.planes))
                    throw $TypeError(".game.SeatObservation.planes: array expected");
                message.planes = $Array(object.planes.length);
                for (let i = 0; i < object.planes.length; ++i)
                    message.planes[i] = $Number(object.planes[i]);
            }
            if (object.planeChannels != null)
                if ($Number(object.planeChannels) !== 0)
                    message.planeChannels = object.planeChannels >>> 0;
            if (object.planeHeight != null)
                if ($Number(object.planeHeight) !== 0)
                    message.planeHeight = object.planeHeight >>> 0;
            if (object.planeWidth != null)
                if ($Number(object.planeWidth) !== 0)
                    message.planeWidth = object.planeWidth >>> 0;
            if (object.scalars) {
                if (!$Array.isArray(object.scalars))
                    throw $TypeError(".game.SeatObservation.scalars: array expected");
                message.scalars = $Array(object.scalars.length);
                for (let i = 0; i < object.scalars.length; ++i)
                    message.scalars[i] = $Number(object.scalars[i]);
            }
            if (object.actionMask != null)
                if (object.actionMask.length)
                    if (typeof object.actionMask === "string")
                        $util.base64.decode(object.actionMask, message.actionMask = $util.newBuffer($util.base64.length(object.actionMask)), 0);
                    else if (object.actionMask.length >= 0)
                        message.actionMask = object.actionMask;
            if (object.actionSpaceSize != null)
                if ($Number(object.actionSpaceSize) !== 0)
                    message.actionSpaceSize = object.actionSpaceSize >>> 0;
            if (object.decisionIndex != null)
                if (typeof object.decisionIndex === "object" ? object.decisionIndex.low || object.decisionIndex.high : $Number(object.decisionIndex) !== 0)
                    if ($util.Long)
                        message.decisionIndex = $util.Long.fromValue(object.decisionIndex, true);
                    else if (typeof object.decisionIndex === "string")
                        message.decisionIndex = $parseInt(object.decisionIndex, 10);
                    else if (typeof object.decisionIndex === "number")
                        message.decisionIndex = object.decisionIndex;
                    else if (typeof object.decisionIndex === "object")
                        message.decisionIndex = new $util.LongBits(object.decisionIndex.low >>> 0, object.decisionIndex.high >>> 0).toNumber(true);
            if (object.phase !== 0 && (typeof object.phase !== "string" || $root.game.GamePhase[object.phase] !== 0))
                switch (object.phase) {
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
                default:
                    if (typeof object.phase === "number" && (object.phase | 0) === object.phase)
                        message.phase = object.phase;
                }
            if (object.activePlayer != null)
                if ($Number(object.activePlayer) !== 0)
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
        SeatObservation.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.arrays || options.defaults) {
                object.planes = [];
                object.scalars = [];
            }
            if (options.defaults) {
                object.seat = 0;
                object.planeChannels = 0;
                object.planeHeight = 0;
                object.planeWidth = 0;
                if (options.bytes === $String)
                    object.actionMask = "";
                else {
                    object.actionMask = [];
                    if (options.bytes !== $Array)
                        object.actionMask = $util.newBuffer(object.actionMask);
                }
                object.actionSpaceSize = 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, true);
                    object.decisionIndex = options.longs === $String ? long.toString() : options.longs === $Number ? long.toNumber() : typeof $BigInt !== "undefined" && options.longs === $BigInt ? long.toBigInt() : long;
                } else
                    object.decisionIndex = options.longs === $String ? "0" : typeof $BigInt !== "undefined" && options.longs === $BigInt ? $BigInt("0") : 0;
                object.phase = options.enums === $String ? "PHASE_INIT" : 0;
                object.activePlayer = 0;
            }
            if (message.seat != null && $Object.hasOwnProperty.call(message, "seat"))
                object.seat = message.seat;
            if (message.planes && message.planes.length) {
                object.planes = $Array(message.planes.length);
                for (let j = 0; j < message.planes.length; ++j)
                    object.planes[j] = options.json && !$isFinite(message.planes[j]) ? $String(message.planes[j]) : message.planes[j];
            }
            if (message.planeChannels != null && $Object.hasOwnProperty.call(message, "planeChannels"))
                object.planeChannels = message.planeChannels;
            if (message.planeHeight != null && $Object.hasOwnProperty.call(message, "planeHeight"))
                object.planeHeight = message.planeHeight;
            if (message.planeWidth != null && $Object.hasOwnProperty.call(message, "planeWidth"))
                object.planeWidth = message.planeWidth;
            if (message.scalars && message.scalars.length) {
                object.scalars = $Array(message.scalars.length);
                for (let j = 0; j < message.scalars.length; ++j)
                    object.scalars[j] = options.json && !$isFinite(message.scalars[j]) ? $String(message.scalars[j]) : message.scalars[j];
            }
            if (message.actionMask != null && $Object.hasOwnProperty.call(message, "actionMask"))
                object.actionMask = options.bytes === $String ? $util.base64.encode(message.actionMask, 0, message.actionMask.length) : options.bytes === $Array ? $Array.prototype.slice.call(message.actionMask) : message.actionMask;
            if (message.actionSpaceSize != null && $Object.hasOwnProperty.call(message, "actionSpaceSize"))
                object.actionSpaceSize = message.actionSpaceSize;
            if (message.decisionIndex != null && $Object.hasOwnProperty.call(message, "decisionIndex"))
                if (typeof $BigInt !== "undefined" && options.longs === $BigInt)
                    object.decisionIndex = typeof message.decisionIndex === "number" ? $BigInt(message.decisionIndex) : $util.Long.fromBits(message.decisionIndex.low >>> 0, message.decisionIndex.high >>> 0, true).toBigInt();
                else if (typeof message.decisionIndex === "number")
                    object.decisionIndex = options.longs === $String ? $String(message.decisionIndex) : message.decisionIndex;
                else
                    object.decisionIndex = options.longs === $String ? $util.Long.prototype.toString.call(message.decisionIndex) : options.longs === $Number ? new $util.LongBits(message.decisionIndex.low >>> 0, message.decisionIndex.high >>> 0).toNumber(true) : message.decisionIndex;
            if (message.phase != null && $Object.hasOwnProperty.call(message, "phase"))
                object.phase = options.enums === $String ? $root.game.GamePhase[message.phase] === $undefined ? message.phase : $root.game.GamePhase[message.phase] : message.phase;
            if (message.activePlayer != null && $Object.hasOwnProperty.call(message, "activePlayer"))
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
        SeatObservation.prototype.toJSON = function() {
            return SeatObservation.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for SeatObservation
         * @function getTypeUrl
         * @memberof game.SeatObservation
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        SeatObservation.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.SeatObservation";
        };

        return SeatObservation;
    })();

    game.EnvResetRequest = (function() {

        /**
         * Properties of an EnvResetRequest.
         * @typedef {Object} game.EnvResetRequest.$Properties
         * @property {number|Long} [seed] EnvResetRequest seed
         * @property {game.EnvConfig.$Properties} [config] EnvResetRequest config
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of an EnvResetRequest.
         * @memberof game
         * @interface IEnvResetRequest
         * @augments game.EnvResetRequest.$Properties
         * @deprecated Use game.EnvResetRequest.$Properties instead.
         */

        /**
         * Shape of an EnvResetRequest.
         * @typedef {game.EnvResetRequest.$Properties} game.EnvResetRequest.$Shape
         */

        /**
         * Constructs a new EnvResetRequest.
         * @memberof game
         * @classdesc Represents an EnvResetRequest.
         * @constructor
         * @param {game.EnvResetRequest.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const EnvResetRequest = function (properties) {
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.EnvResetRequest.$Properties=} [properties] Properties to set
         * @returns {game.EnvResetRequest} EnvResetRequest instance
         * @type {{
         *   (properties: game.EnvResetRequest.$Shape): game.EnvResetRequest & game.EnvResetRequest.$Shape;
         *   (properties?: game.EnvResetRequest.$Properties): game.EnvResetRequest;
         * }}
         */
        EnvResetRequest.create = function(properties) {
            return new EnvResetRequest(properties);
        };

        /**
         * Encodes the specified EnvResetRequest message. Does not implicitly {@link game.EnvResetRequest.verify|verify} messages.
         * @function encode
         * @memberof game.EnvResetRequest
         * @static
         * @param {game.EnvResetRequest.$Properties} message EnvResetRequest message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvResetRequest.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.seed != null && $Object.hasOwnProperty.call(message, "seed") && (typeof message.seed === "object" ? message.seed.low || message.seed.high : message.seed !== 0))
                writer.uint32(/* id 1, wireType 0 =*/8).uint64(message.seed);
            if (message.config != null && $Object.hasOwnProperty.call(message, "config"))
                $root.game.EnvConfig.encode(message.config, writer.uint32(/* id 2, wireType 2 =*/18).fork(), _depth + 1).ldelim();
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified EnvResetRequest message, length delimited. Does not implicitly {@link game.EnvResetRequest.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.EnvResetRequest
         * @static
         * @param {game.EnvResetRequest.$Properties} message EnvResetRequest message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvResetRequest.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes an EnvResetRequest message from the specified reader or buffer.
         * @function decode
         * @memberof game.EnvResetRequest
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.EnvResetRequest & game.EnvResetRequest.$Shape} EnvResetRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvResetRequest.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.EnvResetRequest(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 0)
                            break;
                        if (typeof (value = reader.uint64()) === "object" ? value.low || value.high : value !== 0)
                            message.seed = value;
                        else
                            delete message.seed;
                        continue;
                    }
                case 2: {
                        if (wireType !== 2)
                            break;
                        message.config = $root.game.EnvConfig.decode(reader, reader.uint32(), $undefined, _depth + 1, message.config);
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes an EnvResetRequest message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.EnvResetRequest
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.EnvResetRequest & game.EnvResetRequest.$Shape} EnvResetRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvResetRequest.decodeDelimited = function(reader) {
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
        EnvResetRequest.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.seed != null && $Object.hasOwnProperty.call(message, "seed"))
                if (!$util.isInteger(message.seed) && !(message.seed && $util.isInteger(message.seed.low) && $util.isInteger(message.seed.high)))
                    return "seed: integer|Long expected";
            if (message.config != null && $Object.hasOwnProperty.call(message, "config")) {
                let error = $root.game.EnvConfig.verify(message.config, _depth + 1);
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
        EnvResetRequest.fromObject = function (object, _depth) {
            if (object instanceof $root.game.EnvResetRequest)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.EnvResetRequest: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.EnvResetRequest();
            if (object.seed != null)
                if (typeof object.seed === "object" ? object.seed.low || object.seed.high : $Number(object.seed) !== 0)
                    if ($util.Long)
                        message.seed = $util.Long.fromValue(object.seed, true);
                    else if (typeof object.seed === "string")
                        message.seed = $parseInt(object.seed, 10);
                    else if (typeof object.seed === "number")
                        message.seed = object.seed;
                    else if (typeof object.seed === "object")
                        message.seed = new $util.LongBits(object.seed.low >>> 0, object.seed.high >>> 0).toNumber(true);
            if (object.config != null) {
                if (!$util.isObject(object.config))
                    throw $TypeError(".game.EnvResetRequest.config: object expected");
                message.config = $root.game.EnvConfig.fromObject(object.config, _depth + 1);
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
        EnvResetRequest.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.defaults) {
                if ($util.Long) {
                    let long = new $util.Long(0, 0, true);
                    object.seed = options.longs === $String ? long.toString() : options.longs === $Number ? long.toNumber() : typeof $BigInt !== "undefined" && options.longs === $BigInt ? long.toBigInt() : long;
                } else
                    object.seed = options.longs === $String ? "0" : typeof $BigInt !== "undefined" && options.longs === $BigInt ? $BigInt("0") : 0;
                object.config = null;
            }
            if (message.seed != null && $Object.hasOwnProperty.call(message, "seed"))
                if (typeof $BigInt !== "undefined" && options.longs === $BigInt)
                    object.seed = typeof message.seed === "number" ? $BigInt(message.seed) : $util.Long.fromBits(message.seed.low >>> 0, message.seed.high >>> 0, true).toBigInt();
                else if (typeof message.seed === "number")
                    object.seed = options.longs === $String ? $String(message.seed) : message.seed;
                else
                    object.seed = options.longs === $String ? $util.Long.prototype.toString.call(message.seed) : options.longs === $Number ? new $util.LongBits(message.seed.low >>> 0, message.seed.high >>> 0).toNumber(true) : message.seed;
            if (message.config != null && $Object.hasOwnProperty.call(message, "config"))
                object.config = $root.game.EnvConfig.toObject(message.config, options, _depth + 1);
            return object;
        };

        /**
         * Converts this EnvResetRequest to JSON.
         * @function toJSON
         * @memberof game.EnvResetRequest
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        EnvResetRequest.prototype.toJSON = function() {
            return EnvResetRequest.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for EnvResetRequest
         * @function getTypeUrl
         * @memberof game.EnvResetRequest
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        EnvResetRequest.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.EnvResetRequest";
        };

        return EnvResetRequest;
    })();

    game.EnvResetResponse = (function() {

        /**
         * Properties of an EnvResetResponse.
         * @typedef {Object} game.EnvResetResponse.$Properties
         * @property {game.SeatObservation.$Properties} [observation] EnvResetResponse observation
         * @property {Array.<number>} [rewards] EnvResetResponse rewards
         * @property {boolean} [terminated] EnvResetResponse terminated
         * @property {boolean} [truncated] EnvResetResponse truncated
         * @property {game.RoundOutcome.$Properties} [roundOutcome] EnvResetResponse roundOutcome
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of an EnvResetResponse.
         * @memberof game
         * @interface IEnvResetResponse
         * @augments game.EnvResetResponse.$Properties
         * @deprecated Use game.EnvResetResponse.$Properties instead.
         */

        /**
         * Shape of an EnvResetResponse.
         * @typedef {game.EnvResetResponse.$Properties} game.EnvResetResponse.$Shape
         */

        /**
         * Constructs a new EnvResetResponse.
         * @memberof game
         * @classdesc Represents an EnvResetResponse.
         * @constructor
         * @param {game.EnvResetResponse.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const EnvResetResponse = function (properties) {
            this.rewards = [];
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.EnvResetResponse.$Properties=} [properties] Properties to set
         * @returns {game.EnvResetResponse} EnvResetResponse instance
         * @type {{
         *   (properties: game.EnvResetResponse.$Shape): game.EnvResetResponse & game.EnvResetResponse.$Shape;
         *   (properties?: game.EnvResetResponse.$Properties): game.EnvResetResponse;
         * }}
         */
        EnvResetResponse.create = function(properties) {
            return new EnvResetResponse(properties);
        };

        /**
         * Encodes the specified EnvResetResponse message. Does not implicitly {@link game.EnvResetResponse.verify|verify} messages.
         * @function encode
         * @memberof game.EnvResetResponse
         * @static
         * @param {game.EnvResetResponse.$Properties} message EnvResetResponse message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvResetResponse.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.observation != null && $Object.hasOwnProperty.call(message, "observation"))
                $root.game.SeatObservation.encode(message.observation, writer.uint32(/* id 1, wireType 2 =*/10).fork(), _depth + 1).ldelim();
            if (message.rewards != null && message.rewards.length) {
                writer.uint32(/* id 2, wireType 2 =*/18).fork();
                for (let i = 0; i < message.rewards.length; ++i)
                    writer.float(message.rewards[i]);
                writer.ldelim();
            }
            if (message.terminated != null && $Object.hasOwnProperty.call(message, "terminated") && message.terminated !== false)
                writer.uint32(/* id 3, wireType 0 =*/24).bool(message.terminated);
            if (message.truncated != null && $Object.hasOwnProperty.call(message, "truncated") && message.truncated !== false)
                writer.uint32(/* id 4, wireType 0 =*/32).bool(message.truncated);
            if (message.roundOutcome != null && $Object.hasOwnProperty.call(message, "roundOutcome"))
                $root.game.RoundOutcome.encode(message.roundOutcome, writer.uint32(/* id 5, wireType 2 =*/42).fork(), _depth + 1).ldelim();
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified EnvResetResponse message, length delimited. Does not implicitly {@link game.EnvResetResponse.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.EnvResetResponse
         * @static
         * @param {game.EnvResetResponse.$Properties} message EnvResetResponse message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvResetResponse.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes an EnvResetResponse message from the specified reader or buffer.
         * @function decode
         * @memberof game.EnvResetResponse
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.EnvResetResponse & game.EnvResetResponse.$Shape} EnvResetResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvResetResponse.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.EnvResetResponse(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 2)
                            break;
                        message.observation = $root.game.SeatObservation.decode(reader, reader.uint32(), $undefined, _depth + 1, message.observation);
                        continue;
                    }
                case 2: {
                        if (wireType === 2) {
                            if (!(message.rewards && message.rewards.length))
                                message.rewards = [];
                            let end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.rewards.push(reader.float());
                            continue;
                        }
                        if (wireType !== 5)
                            break;
                        if (!(message.rewards && message.rewards.length))
                            message.rewards = [];
                        message.rewards.push(reader.float());
                        continue;
                    }
                case 3: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.terminated = value;
                        else
                            delete message.terminated;
                        continue;
                    }
                case 4: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.truncated = value;
                        else
                            delete message.truncated;
                        continue;
                    }
                case 5: {
                        if (wireType !== 2)
                            break;
                        message.roundOutcome = $root.game.RoundOutcome.decode(reader, reader.uint32(), $undefined, _depth + 1, message.roundOutcome);
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes an EnvResetResponse message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.EnvResetResponse
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.EnvResetResponse & game.EnvResetResponse.$Shape} EnvResetResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvResetResponse.decodeDelimited = function(reader) {
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
        EnvResetResponse.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.observation != null && $Object.hasOwnProperty.call(message, "observation")) {
                let error = $root.game.SeatObservation.verify(message.observation, _depth + 1);
                if (error)
                    return "observation." + error;
            }
            if (message.rewards != null && $Object.hasOwnProperty.call(message, "rewards")) {
                if (!$Array.isArray(message.rewards))
                    return "rewards: array expected";
                for (let i = 0; i < message.rewards.length; ++i)
                    if (typeof message.rewards[i] !== "number")
                        return "rewards: number[] expected";
            }
            if (message.terminated != null && $Object.hasOwnProperty.call(message, "terminated"))
                if (typeof message.terminated !== "boolean")
                    return "terminated: boolean expected";
            if (message.truncated != null && $Object.hasOwnProperty.call(message, "truncated"))
                if (typeof message.truncated !== "boolean")
                    return "truncated: boolean expected";
            if (message.roundOutcome != null && $Object.hasOwnProperty.call(message, "roundOutcome")) {
                let error = $root.game.RoundOutcome.verify(message.roundOutcome, _depth + 1);
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
        EnvResetResponse.fromObject = function (object, _depth) {
            if (object instanceof $root.game.EnvResetResponse)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.EnvResetResponse: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.EnvResetResponse();
            if (object.observation != null) {
                if (!$util.isObject(object.observation))
                    throw $TypeError(".game.EnvResetResponse.observation: object expected");
                message.observation = $root.game.SeatObservation.fromObject(object.observation, _depth + 1);
            }
            if (object.rewards) {
                if (!$Array.isArray(object.rewards))
                    throw $TypeError(".game.EnvResetResponse.rewards: array expected");
                message.rewards = $Array(object.rewards.length);
                for (let i = 0; i < object.rewards.length; ++i)
                    message.rewards[i] = $Number(object.rewards[i]);
            }
            if (object.terminated != null)
                if (object.terminated)
                    message.terminated = $Boolean(object.terminated);
            if (object.truncated != null)
                if (object.truncated)
                    message.truncated = $Boolean(object.truncated);
            if (object.roundOutcome != null) {
                if (!$util.isObject(object.roundOutcome))
                    throw $TypeError(".game.EnvResetResponse.roundOutcome: object expected");
                message.roundOutcome = $root.game.RoundOutcome.fromObject(object.roundOutcome, _depth + 1);
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
        EnvResetResponse.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.arrays || options.defaults)
                object.rewards = [];
            if (options.defaults) {
                object.observation = null;
                object.terminated = false;
                object.truncated = false;
                object.roundOutcome = null;
            }
            if (message.observation != null && $Object.hasOwnProperty.call(message, "observation"))
                object.observation = $root.game.SeatObservation.toObject(message.observation, options, _depth + 1);
            if (message.rewards && message.rewards.length) {
                object.rewards = $Array(message.rewards.length);
                for (let j = 0; j < message.rewards.length; ++j)
                    object.rewards[j] = options.json && !$isFinite(message.rewards[j]) ? $String(message.rewards[j]) : message.rewards[j];
            }
            if (message.terminated != null && $Object.hasOwnProperty.call(message, "terminated"))
                object.terminated = message.terminated;
            if (message.truncated != null && $Object.hasOwnProperty.call(message, "truncated"))
                object.truncated = message.truncated;
            if (message.roundOutcome != null && $Object.hasOwnProperty.call(message, "roundOutcome"))
                object.roundOutcome = $root.game.RoundOutcome.toObject(message.roundOutcome, options, _depth + 1);
            return object;
        };

        /**
         * Converts this EnvResetResponse to JSON.
         * @function toJSON
         * @memberof game.EnvResetResponse
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        EnvResetResponse.prototype.toJSON = function() {
            return EnvResetResponse.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for EnvResetResponse
         * @function getTypeUrl
         * @memberof game.EnvResetResponse
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        EnvResetResponse.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.EnvResetResponse";
        };

        return EnvResetResponse;
    })();

    game.EnvStepRequest = (function() {

        /**
         * Properties of an EnvStepRequest.
         * @typedef {Object} game.EnvStepRequest.$Properties
         * @property {number} [actionId] EnvStepRequest actionId
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of an EnvStepRequest.
         * @memberof game
         * @interface IEnvStepRequest
         * @augments game.EnvStepRequest.$Properties
         * @deprecated Use game.EnvStepRequest.$Properties instead.
         */

        /**
         * Shape of an EnvStepRequest.
         * @typedef {game.EnvStepRequest.$Properties} game.EnvStepRequest.$Shape
         */

        /**
         * Constructs a new EnvStepRequest.
         * @memberof game
         * @classdesc Represents an EnvStepRequest.
         * @constructor
         * @param {game.EnvStepRequest.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const EnvStepRequest = function (properties) {
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.EnvStepRequest.$Properties=} [properties] Properties to set
         * @returns {game.EnvStepRequest} EnvStepRequest instance
         * @type {{
         *   (properties: game.EnvStepRequest.$Shape): game.EnvStepRequest & game.EnvStepRequest.$Shape;
         *   (properties?: game.EnvStepRequest.$Properties): game.EnvStepRequest;
         * }}
         */
        EnvStepRequest.create = function(properties) {
            return new EnvStepRequest(properties);
        };

        /**
         * Encodes the specified EnvStepRequest message. Does not implicitly {@link game.EnvStepRequest.verify|verify} messages.
         * @function encode
         * @memberof game.EnvStepRequest
         * @static
         * @param {game.EnvStepRequest.$Properties} message EnvStepRequest message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvStepRequest.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.actionId != null && $Object.hasOwnProperty.call(message, "actionId") && message.actionId !== 0)
                writer.uint32(/* id 1, wireType 0 =*/8).uint32(message.actionId);
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified EnvStepRequest message, length delimited. Does not implicitly {@link game.EnvStepRequest.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.EnvStepRequest
         * @static
         * @param {game.EnvStepRequest.$Properties} message EnvStepRequest message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvStepRequest.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes an EnvStepRequest message from the specified reader or buffer.
         * @function decode
         * @memberof game.EnvStepRequest
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.EnvStepRequest & game.EnvStepRequest.$Shape} EnvStepRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvStepRequest.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.EnvStepRequest(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.actionId = value;
                        else
                            delete message.actionId;
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes an EnvStepRequest message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.EnvStepRequest
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.EnvStepRequest & game.EnvStepRequest.$Shape} EnvStepRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvStepRequest.decodeDelimited = function(reader) {
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
        EnvStepRequest.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.actionId != null && $Object.hasOwnProperty.call(message, "actionId"))
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
        EnvStepRequest.fromObject = function (object, _depth) {
            if (object instanceof $root.game.EnvStepRequest)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.EnvStepRequest: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.EnvStepRequest();
            if (object.actionId != null)
                if ($Number(object.actionId) !== 0)
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
        EnvStepRequest.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.defaults)
                object.actionId = 0;
            if (message.actionId != null && $Object.hasOwnProperty.call(message, "actionId"))
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
        EnvStepRequest.prototype.toJSON = function() {
            return EnvStepRequest.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for EnvStepRequest
         * @function getTypeUrl
         * @memberof game.EnvStepRequest
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        EnvStepRequest.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.EnvStepRequest";
        };

        return EnvStepRequest;
    })();

    game.EnvStepResponse = (function() {

        /**
         * Properties of an EnvStepResponse.
         * @typedef {Object} game.EnvStepResponse.$Properties
         * @property {game.SeatObservation.$Properties} [observation] EnvStepResponse observation
         * @property {Array.<number>} [rewards] EnvStepResponse rewards
         * @property {boolean} [terminated] EnvStepResponse terminated
         * @property {boolean} [truncated] EnvStepResponse truncated
         * @property {game.RoundOutcome.$Properties} [roundOutcome] EnvStepResponse roundOutcome
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of an EnvStepResponse.
         * @memberof game
         * @interface IEnvStepResponse
         * @augments game.EnvStepResponse.$Properties
         * @deprecated Use game.EnvStepResponse.$Properties instead.
         */

        /**
         * Shape of an EnvStepResponse.
         * @typedef {game.EnvStepResponse.$Properties} game.EnvStepResponse.$Shape
         */

        /**
         * Constructs a new EnvStepResponse.
         * @memberof game
         * @classdesc Represents an EnvStepResponse.
         * @constructor
         * @param {game.EnvStepResponse.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const EnvStepResponse = function (properties) {
            this.rewards = [];
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.EnvStepResponse.$Properties=} [properties] Properties to set
         * @returns {game.EnvStepResponse} EnvStepResponse instance
         * @type {{
         *   (properties: game.EnvStepResponse.$Shape): game.EnvStepResponse & game.EnvStepResponse.$Shape;
         *   (properties?: game.EnvStepResponse.$Properties): game.EnvStepResponse;
         * }}
         */
        EnvStepResponse.create = function(properties) {
            return new EnvStepResponse(properties);
        };

        /**
         * Encodes the specified EnvStepResponse message. Does not implicitly {@link game.EnvStepResponse.verify|verify} messages.
         * @function encode
         * @memberof game.EnvStepResponse
         * @static
         * @param {game.EnvStepResponse.$Properties} message EnvStepResponse message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvStepResponse.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.observation != null && $Object.hasOwnProperty.call(message, "observation"))
                $root.game.SeatObservation.encode(message.observation, writer.uint32(/* id 1, wireType 2 =*/10).fork(), _depth + 1).ldelim();
            if (message.rewards != null && message.rewards.length) {
                writer.uint32(/* id 2, wireType 2 =*/18).fork();
                for (let i = 0; i < message.rewards.length; ++i)
                    writer.float(message.rewards[i]);
                writer.ldelim();
            }
            if (message.terminated != null && $Object.hasOwnProperty.call(message, "terminated") && message.terminated !== false)
                writer.uint32(/* id 3, wireType 0 =*/24).bool(message.terminated);
            if (message.truncated != null && $Object.hasOwnProperty.call(message, "truncated") && message.truncated !== false)
                writer.uint32(/* id 4, wireType 0 =*/32).bool(message.truncated);
            if (message.roundOutcome != null && $Object.hasOwnProperty.call(message, "roundOutcome"))
                $root.game.RoundOutcome.encode(message.roundOutcome, writer.uint32(/* id 5, wireType 2 =*/42).fork(), _depth + 1).ldelim();
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified EnvStepResponse message, length delimited. Does not implicitly {@link game.EnvStepResponse.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.EnvStepResponse
         * @static
         * @param {game.EnvStepResponse.$Properties} message EnvStepResponse message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        EnvStepResponse.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes an EnvStepResponse message from the specified reader or buffer.
         * @function decode
         * @memberof game.EnvStepResponse
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.EnvStepResponse & game.EnvStepResponse.$Shape} EnvStepResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvStepResponse.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.EnvStepResponse(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 2)
                            break;
                        message.observation = $root.game.SeatObservation.decode(reader, reader.uint32(), $undefined, _depth + 1, message.observation);
                        continue;
                    }
                case 2: {
                        if (wireType === 2) {
                            if (!(message.rewards && message.rewards.length))
                                message.rewards = [];
                            let end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.rewards.push(reader.float());
                            continue;
                        }
                        if (wireType !== 5)
                            break;
                        if (!(message.rewards && message.rewards.length))
                            message.rewards = [];
                        message.rewards.push(reader.float());
                        continue;
                    }
                case 3: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.terminated = value;
                        else
                            delete message.terminated;
                        continue;
                    }
                case 4: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.truncated = value;
                        else
                            delete message.truncated;
                        continue;
                    }
                case 5: {
                        if (wireType !== 2)
                            break;
                        message.roundOutcome = $root.game.RoundOutcome.decode(reader, reader.uint32(), $undefined, _depth + 1, message.roundOutcome);
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes an EnvStepResponse message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.EnvStepResponse
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.EnvStepResponse & game.EnvStepResponse.$Shape} EnvStepResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        EnvStepResponse.decodeDelimited = function(reader) {
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
        EnvStepResponse.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.observation != null && $Object.hasOwnProperty.call(message, "observation")) {
                let error = $root.game.SeatObservation.verify(message.observation, _depth + 1);
                if (error)
                    return "observation." + error;
            }
            if (message.rewards != null && $Object.hasOwnProperty.call(message, "rewards")) {
                if (!$Array.isArray(message.rewards))
                    return "rewards: array expected";
                for (let i = 0; i < message.rewards.length; ++i)
                    if (typeof message.rewards[i] !== "number")
                        return "rewards: number[] expected";
            }
            if (message.terminated != null && $Object.hasOwnProperty.call(message, "terminated"))
                if (typeof message.terminated !== "boolean")
                    return "terminated: boolean expected";
            if (message.truncated != null && $Object.hasOwnProperty.call(message, "truncated"))
                if (typeof message.truncated !== "boolean")
                    return "truncated: boolean expected";
            if (message.roundOutcome != null && $Object.hasOwnProperty.call(message, "roundOutcome")) {
                let error = $root.game.RoundOutcome.verify(message.roundOutcome, _depth + 1);
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
        EnvStepResponse.fromObject = function (object, _depth) {
            if (object instanceof $root.game.EnvStepResponse)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.EnvStepResponse: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.EnvStepResponse();
            if (object.observation != null) {
                if (!$util.isObject(object.observation))
                    throw $TypeError(".game.EnvStepResponse.observation: object expected");
                message.observation = $root.game.SeatObservation.fromObject(object.observation, _depth + 1);
            }
            if (object.rewards) {
                if (!$Array.isArray(object.rewards))
                    throw $TypeError(".game.EnvStepResponse.rewards: array expected");
                message.rewards = $Array(object.rewards.length);
                for (let i = 0; i < object.rewards.length; ++i)
                    message.rewards[i] = $Number(object.rewards[i]);
            }
            if (object.terminated != null)
                if (object.terminated)
                    message.terminated = $Boolean(object.terminated);
            if (object.truncated != null)
                if (object.truncated)
                    message.truncated = $Boolean(object.truncated);
            if (object.roundOutcome != null) {
                if (!$util.isObject(object.roundOutcome))
                    throw $TypeError(".game.EnvStepResponse.roundOutcome: object expected");
                message.roundOutcome = $root.game.RoundOutcome.fromObject(object.roundOutcome, _depth + 1);
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
        EnvStepResponse.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.arrays || options.defaults)
                object.rewards = [];
            if (options.defaults) {
                object.observation = null;
                object.terminated = false;
                object.truncated = false;
                object.roundOutcome = null;
            }
            if (message.observation != null && $Object.hasOwnProperty.call(message, "observation"))
                object.observation = $root.game.SeatObservation.toObject(message.observation, options, _depth + 1);
            if (message.rewards && message.rewards.length) {
                object.rewards = $Array(message.rewards.length);
                for (let j = 0; j < message.rewards.length; ++j)
                    object.rewards[j] = options.json && !$isFinite(message.rewards[j]) ? $String(message.rewards[j]) : message.rewards[j];
            }
            if (message.terminated != null && $Object.hasOwnProperty.call(message, "terminated"))
                object.terminated = message.terminated;
            if (message.truncated != null && $Object.hasOwnProperty.call(message, "truncated"))
                object.truncated = message.truncated;
            if (message.roundOutcome != null && $Object.hasOwnProperty.call(message, "roundOutcome"))
                object.roundOutcome = $root.game.RoundOutcome.toObject(message.roundOutcome, options, _depth + 1);
            return object;
        };

        /**
         * Converts this EnvStepResponse to JSON.
         * @function toJSON
         * @memberof game.EnvStepResponse
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        EnvStepResponse.prototype.toJSON = function() {
            return EnvStepResponse.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for EnvStepResponse
         * @function getTypeUrl
         * @memberof game.EnvStepResponse
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        EnvStepResponse.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.EnvStepResponse";
        };

        return EnvStepResponse;
    })();

    game.BranchEvaluationRequest = (function() {

        /**
         * Properties of a BranchEvaluationRequest.
         * @typedef {Object} game.BranchEvaluationRequest.$Properties
         * @property {Array.<number>} [actionIds] BranchEvaluationRequest actionIds
         * @property {boolean} [stopAtRoundEnd] BranchEvaluationRequest stopAtRoundEnd
         * @property {number} [maxDecisions] BranchEvaluationRequest maxDecisions
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a BranchEvaluationRequest.
         * @memberof game
         * @interface IBranchEvaluationRequest
         * @augments game.BranchEvaluationRequest.$Properties
         * @deprecated Use game.BranchEvaluationRequest.$Properties instead.
         */

        /**
         * Shape of a BranchEvaluationRequest.
         * @typedef {game.BranchEvaluationRequest.$Properties} game.BranchEvaluationRequest.$Shape
         */

        /**
         * Constructs a new BranchEvaluationRequest.
         * @memberof game
         * @classdesc Represents a BranchEvaluationRequest.
         * @constructor
         * @param {game.BranchEvaluationRequest.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const BranchEvaluationRequest = function (properties) {
            this.actionIds = [];
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

        /**
         * BranchEvaluationRequest actionIds.
         * @member {Array.<number>} actionIds
         * @memberof game.BranchEvaluationRequest
         * @instance
         */
        BranchEvaluationRequest.prototype.actionIds = $util.emptyArray;

        /**
         * BranchEvaluationRequest stopAtRoundEnd.
         * @member {boolean} stopAtRoundEnd
         * @memberof game.BranchEvaluationRequest
         * @instance
         */
        BranchEvaluationRequest.prototype.stopAtRoundEnd = false;

        /**
         * BranchEvaluationRequest maxDecisions.
         * @member {number} maxDecisions
         * @memberof game.BranchEvaluationRequest
         * @instance
         */
        BranchEvaluationRequest.prototype.maxDecisions = 0;

        /**
         * Creates a new BranchEvaluationRequest instance using the specified properties.
         * @function create
         * @memberof game.BranchEvaluationRequest
         * @static
         * @param {game.BranchEvaluationRequest.$Properties=} [properties] Properties to set
         * @returns {game.BranchEvaluationRequest} BranchEvaluationRequest instance
         * @type {{
         *   (properties: game.BranchEvaluationRequest.$Shape): game.BranchEvaluationRequest & game.BranchEvaluationRequest.$Shape;
         *   (properties?: game.BranchEvaluationRequest.$Properties): game.BranchEvaluationRequest;
         * }}
         */
        BranchEvaluationRequest.create = function(properties) {
            return new BranchEvaluationRequest(properties);
        };

        /**
         * Encodes the specified BranchEvaluationRequest message. Does not implicitly {@link game.BranchEvaluationRequest.verify|verify} messages.
         * @function encode
         * @memberof game.BranchEvaluationRequest
         * @static
         * @param {game.BranchEvaluationRequest.$Properties} message BranchEvaluationRequest message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        BranchEvaluationRequest.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.actionIds != null && message.actionIds.length) {
                writer.uint32(/* id 1, wireType 2 =*/10).fork();
                for (let i = 0; i < message.actionIds.length; ++i)
                    writer.uint32(message.actionIds[i]);
                writer.ldelim();
            }
            if (message.stopAtRoundEnd != null && $Object.hasOwnProperty.call(message, "stopAtRoundEnd") && message.stopAtRoundEnd !== false)
                writer.uint32(/* id 2, wireType 0 =*/16).bool(message.stopAtRoundEnd);
            if (message.maxDecisions != null && $Object.hasOwnProperty.call(message, "maxDecisions") && message.maxDecisions !== 0)
                writer.uint32(/* id 3, wireType 0 =*/24).uint32(message.maxDecisions);
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified BranchEvaluationRequest message, length delimited. Does not implicitly {@link game.BranchEvaluationRequest.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.BranchEvaluationRequest
         * @static
         * @param {game.BranchEvaluationRequest.$Properties} message BranchEvaluationRequest message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        BranchEvaluationRequest.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a BranchEvaluationRequest message from the specified reader or buffer.
         * @function decode
         * @memberof game.BranchEvaluationRequest
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.BranchEvaluationRequest & game.BranchEvaluationRequest.$Shape} BranchEvaluationRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        BranchEvaluationRequest.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.BranchEvaluationRequest(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType === 2) {
                            if (!(message.actionIds && message.actionIds.length))
                                message.actionIds = [];
                            let end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.actionIds.push(reader.uint32());
                            continue;
                        }
                        if (wireType !== 0)
                            break;
                        if (!(message.actionIds && message.actionIds.length))
                            message.actionIds = [];
                        message.actionIds.push(reader.uint32());
                        continue;
                    }
                case 2: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.stopAtRoundEnd = value;
                        else
                            delete message.stopAtRoundEnd;
                        continue;
                    }
                case 3: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.maxDecisions = value;
                        else
                            delete message.maxDecisions;
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a BranchEvaluationRequest message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.BranchEvaluationRequest
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.BranchEvaluationRequest & game.BranchEvaluationRequest.$Shape} BranchEvaluationRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        BranchEvaluationRequest.decodeDelimited = function(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a BranchEvaluationRequest message.
         * @function verify
         * @memberof game.BranchEvaluationRequest
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        BranchEvaluationRequest.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.actionIds != null && $Object.hasOwnProperty.call(message, "actionIds")) {
                if (!$Array.isArray(message.actionIds))
                    return "actionIds: array expected";
                for (let i = 0; i < message.actionIds.length; ++i)
                    if (!$util.isInteger(message.actionIds[i]))
                        return "actionIds: integer[] expected";
            }
            if (message.stopAtRoundEnd != null && $Object.hasOwnProperty.call(message, "stopAtRoundEnd"))
                if (typeof message.stopAtRoundEnd !== "boolean")
                    return "stopAtRoundEnd: boolean expected";
            if (message.maxDecisions != null && $Object.hasOwnProperty.call(message, "maxDecisions"))
                if (!$util.isInteger(message.maxDecisions))
                    return "maxDecisions: integer expected";
            return null;
        };

        /**
         * Creates a BranchEvaluationRequest message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.BranchEvaluationRequest
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.BranchEvaluationRequest} BranchEvaluationRequest
         */
        BranchEvaluationRequest.fromObject = function (object, _depth) {
            if (object instanceof $root.game.BranchEvaluationRequest)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.BranchEvaluationRequest: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.BranchEvaluationRequest();
            if (object.actionIds) {
                if (!$Array.isArray(object.actionIds))
                    throw $TypeError(".game.BranchEvaluationRequest.actionIds: array expected");
                message.actionIds = $Array(object.actionIds.length);
                for (let i = 0; i < object.actionIds.length; ++i)
                    message.actionIds[i] = object.actionIds[i] >>> 0;
            }
            if (object.stopAtRoundEnd != null)
                if (object.stopAtRoundEnd)
                    message.stopAtRoundEnd = $Boolean(object.stopAtRoundEnd);
            if (object.maxDecisions != null)
                if ($Number(object.maxDecisions) !== 0)
                    message.maxDecisions = object.maxDecisions >>> 0;
            return message;
        };

        /**
         * Creates a plain object from a BranchEvaluationRequest message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.BranchEvaluationRequest
         * @static
         * @param {game.BranchEvaluationRequest} message BranchEvaluationRequest
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        BranchEvaluationRequest.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.arrays || options.defaults)
                object.actionIds = [];
            if (options.defaults) {
                object.stopAtRoundEnd = false;
                object.maxDecisions = 0;
            }
            if (message.actionIds && message.actionIds.length) {
                object.actionIds = $Array(message.actionIds.length);
                for (let j = 0; j < message.actionIds.length; ++j)
                    object.actionIds[j] = message.actionIds[j];
            }
            if (message.stopAtRoundEnd != null && $Object.hasOwnProperty.call(message, "stopAtRoundEnd"))
                object.stopAtRoundEnd = message.stopAtRoundEnd;
            if (message.maxDecisions != null && $Object.hasOwnProperty.call(message, "maxDecisions"))
                object.maxDecisions = message.maxDecisions;
            return object;
        };

        /**
         * Converts this BranchEvaluationRequest to JSON.
         * @function toJSON
         * @memberof game.BranchEvaluationRequest
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        BranchEvaluationRequest.prototype.toJSON = function() {
            return BranchEvaluationRequest.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for BranchEvaluationRequest
         * @function getTypeUrl
         * @memberof game.BranchEvaluationRequest
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        BranchEvaluationRequest.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.BranchEvaluationRequest";
        };

        return BranchEvaluationRequest;
    })();

    game.BranchEvaluationResult = (function() {

        /**
         * Properties of a BranchEvaluationResult.
         * @typedef {Object} game.BranchEvaluationResult.$Properties
         * @property {number} [actionId] BranchEvaluationResult actionId
         * @property {Array.<number>} [rewards] BranchEvaluationResult rewards
         * @property {boolean} [terminated] BranchEvaluationResult terminated
         * @property {boolean} [truncated] BranchEvaluationResult truncated
         * @property {game.RoundOutcome.$Properties} [roundOutcome] BranchEvaluationResult roundOutcome
         * @property {number|Long} [decisions] BranchEvaluationResult decisions
         * @property {string} [error] BranchEvaluationResult error
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a BranchEvaluationResult.
         * @memberof game
         * @interface IBranchEvaluationResult
         * @augments game.BranchEvaluationResult.$Properties
         * @deprecated Use game.BranchEvaluationResult.$Properties instead.
         */

        /**
         * Shape of a BranchEvaluationResult.
         * @typedef {game.BranchEvaluationResult.$Properties} game.BranchEvaluationResult.$Shape
         */

        /**
         * Constructs a new BranchEvaluationResult.
         * @memberof game
         * @classdesc Represents a BranchEvaluationResult.
         * @constructor
         * @param {game.BranchEvaluationResult.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const BranchEvaluationResult = function (properties) {
            this.rewards = [];
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

        /**
         * BranchEvaluationResult actionId.
         * @member {number} actionId
         * @memberof game.BranchEvaluationResult
         * @instance
         */
        BranchEvaluationResult.prototype.actionId = 0;

        /**
         * BranchEvaluationResult rewards.
         * @member {Array.<number>} rewards
         * @memberof game.BranchEvaluationResult
         * @instance
         */
        BranchEvaluationResult.prototype.rewards = $util.emptyArray;

        /**
         * BranchEvaluationResult terminated.
         * @member {boolean} terminated
         * @memberof game.BranchEvaluationResult
         * @instance
         */
        BranchEvaluationResult.prototype.terminated = false;

        /**
         * BranchEvaluationResult truncated.
         * @member {boolean} truncated
         * @memberof game.BranchEvaluationResult
         * @instance
         */
        BranchEvaluationResult.prototype.truncated = false;

        /**
         * BranchEvaluationResult roundOutcome.
         * @member {game.RoundOutcome} roundOutcome
         * @memberof game.BranchEvaluationResult
         * @instance
         */
        BranchEvaluationResult.prototype.roundOutcome = null;

        /**
         * BranchEvaluationResult decisions.
         * @member {number|Long} decisions
         * @memberof game.BranchEvaluationResult
         * @instance
         */
        BranchEvaluationResult.prototype.decisions = $util.Long ? $util.Long.fromBits(0,0,true) : 0;

        /**
         * BranchEvaluationResult error.
         * @member {string} error
         * @memberof game.BranchEvaluationResult
         * @instance
         */
        BranchEvaluationResult.prototype.error = "";

        /**
         * Creates a new BranchEvaluationResult instance using the specified properties.
         * @function create
         * @memberof game.BranchEvaluationResult
         * @static
         * @param {game.BranchEvaluationResult.$Properties=} [properties] Properties to set
         * @returns {game.BranchEvaluationResult} BranchEvaluationResult instance
         * @type {{
         *   (properties: game.BranchEvaluationResult.$Shape): game.BranchEvaluationResult & game.BranchEvaluationResult.$Shape;
         *   (properties?: game.BranchEvaluationResult.$Properties): game.BranchEvaluationResult;
         * }}
         */
        BranchEvaluationResult.create = function(properties) {
            return new BranchEvaluationResult(properties);
        };

        /**
         * Encodes the specified BranchEvaluationResult message. Does not implicitly {@link game.BranchEvaluationResult.verify|verify} messages.
         * @function encode
         * @memberof game.BranchEvaluationResult
         * @static
         * @param {game.BranchEvaluationResult.$Properties} message BranchEvaluationResult message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        BranchEvaluationResult.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.actionId != null && $Object.hasOwnProperty.call(message, "actionId") && message.actionId !== 0)
                writer.uint32(/* id 1, wireType 0 =*/8).uint32(message.actionId);
            if (message.rewards != null && message.rewards.length) {
                writer.uint32(/* id 2, wireType 2 =*/18).fork();
                for (let i = 0; i < message.rewards.length; ++i)
                    writer.float(message.rewards[i]);
                writer.ldelim();
            }
            if (message.terminated != null && $Object.hasOwnProperty.call(message, "terminated") && message.terminated !== false)
                writer.uint32(/* id 3, wireType 0 =*/24).bool(message.terminated);
            if (message.truncated != null && $Object.hasOwnProperty.call(message, "truncated") && message.truncated !== false)
                writer.uint32(/* id 4, wireType 0 =*/32).bool(message.truncated);
            if (message.roundOutcome != null && $Object.hasOwnProperty.call(message, "roundOutcome"))
                $root.game.RoundOutcome.encode(message.roundOutcome, writer.uint32(/* id 5, wireType 2 =*/42).fork(), _depth + 1).ldelim();
            if (message.decisions != null && $Object.hasOwnProperty.call(message, "decisions") && (typeof message.decisions === "object" ? message.decisions.low || message.decisions.high : message.decisions !== 0))
                writer.uint32(/* id 6, wireType 0 =*/48).uint64(message.decisions);
            if (message.error != null && $Object.hasOwnProperty.call(message, "error") && message.error !== "")
                writer.uint32(/* id 7, wireType 2 =*/58).string(message.error);
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified BranchEvaluationResult message, length delimited. Does not implicitly {@link game.BranchEvaluationResult.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.BranchEvaluationResult
         * @static
         * @param {game.BranchEvaluationResult.$Properties} message BranchEvaluationResult message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        BranchEvaluationResult.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a BranchEvaluationResult message from the specified reader or buffer.
         * @function decode
         * @memberof game.BranchEvaluationResult
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.BranchEvaluationResult & game.BranchEvaluationResult.$Shape} BranchEvaluationResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        BranchEvaluationResult.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.BranchEvaluationResult(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.actionId = value;
                        else
                            delete message.actionId;
                        continue;
                    }
                case 2: {
                        if (wireType === 2) {
                            if (!(message.rewards && message.rewards.length))
                                message.rewards = [];
                            let end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.rewards.push(reader.float());
                            continue;
                        }
                        if (wireType !== 5)
                            break;
                        if (!(message.rewards && message.rewards.length))
                            message.rewards = [];
                        message.rewards.push(reader.float());
                        continue;
                    }
                case 3: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.terminated = value;
                        else
                            delete message.terminated;
                        continue;
                    }
                case 4: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.truncated = value;
                        else
                            delete message.truncated;
                        continue;
                    }
                case 5: {
                        if (wireType !== 2)
                            break;
                        message.roundOutcome = $root.game.RoundOutcome.decode(reader, reader.uint32(), $undefined, _depth + 1, message.roundOutcome);
                        continue;
                    }
                case 6: {
                        if (wireType !== 0)
                            break;
                        if (typeof (value = reader.uint64()) === "object" ? value.low || value.high : value !== 0)
                            message.decisions = value;
                        else
                            delete message.decisions;
                        continue;
                    }
                case 7: {
                        if (wireType !== 2)
                            break;
                        if ((value = reader.stringVerify()).length)
                            message.error = value;
                        else
                            delete message.error;
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a BranchEvaluationResult message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.BranchEvaluationResult
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.BranchEvaluationResult & game.BranchEvaluationResult.$Shape} BranchEvaluationResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        BranchEvaluationResult.decodeDelimited = function(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a BranchEvaluationResult message.
         * @function verify
         * @memberof game.BranchEvaluationResult
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        BranchEvaluationResult.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.actionId != null && $Object.hasOwnProperty.call(message, "actionId"))
                if (!$util.isInteger(message.actionId))
                    return "actionId: integer expected";
            if (message.rewards != null && $Object.hasOwnProperty.call(message, "rewards")) {
                if (!$Array.isArray(message.rewards))
                    return "rewards: array expected";
                for (let i = 0; i < message.rewards.length; ++i)
                    if (typeof message.rewards[i] !== "number")
                        return "rewards: number[] expected";
            }
            if (message.terminated != null && $Object.hasOwnProperty.call(message, "terminated"))
                if (typeof message.terminated !== "boolean")
                    return "terminated: boolean expected";
            if (message.truncated != null && $Object.hasOwnProperty.call(message, "truncated"))
                if (typeof message.truncated !== "boolean")
                    return "truncated: boolean expected";
            if (message.roundOutcome != null && $Object.hasOwnProperty.call(message, "roundOutcome")) {
                let error = $root.game.RoundOutcome.verify(message.roundOutcome, _depth + 1);
                if (error)
                    return "roundOutcome." + error;
            }
            if (message.decisions != null && $Object.hasOwnProperty.call(message, "decisions"))
                if (!$util.isInteger(message.decisions) && !(message.decisions && $util.isInteger(message.decisions.low) && $util.isInteger(message.decisions.high)))
                    return "decisions: integer|Long expected";
            if (message.error != null && $Object.hasOwnProperty.call(message, "error"))
                if (!$util.isString(message.error))
                    return "error: string expected";
            return null;
        };

        /**
         * Creates a BranchEvaluationResult message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.BranchEvaluationResult
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.BranchEvaluationResult} BranchEvaluationResult
         */
        BranchEvaluationResult.fromObject = function (object, _depth) {
            if (object instanceof $root.game.BranchEvaluationResult)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.BranchEvaluationResult: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.BranchEvaluationResult();
            if (object.actionId != null)
                if ($Number(object.actionId) !== 0)
                    message.actionId = object.actionId >>> 0;
            if (object.rewards) {
                if (!$Array.isArray(object.rewards))
                    throw $TypeError(".game.BranchEvaluationResult.rewards: array expected");
                message.rewards = $Array(object.rewards.length);
                for (let i = 0; i < object.rewards.length; ++i)
                    message.rewards[i] = $Number(object.rewards[i]);
            }
            if (object.terminated != null)
                if (object.terminated)
                    message.terminated = $Boolean(object.terminated);
            if (object.truncated != null)
                if (object.truncated)
                    message.truncated = $Boolean(object.truncated);
            if (object.roundOutcome != null) {
                if (!$util.isObject(object.roundOutcome))
                    throw $TypeError(".game.BranchEvaluationResult.roundOutcome: object expected");
                message.roundOutcome = $root.game.RoundOutcome.fromObject(object.roundOutcome, _depth + 1);
            }
            if (object.decisions != null)
                if (typeof object.decisions === "object" ? object.decisions.low || object.decisions.high : $Number(object.decisions) !== 0)
                    if ($util.Long)
                        message.decisions = $util.Long.fromValue(object.decisions, true);
                    else if (typeof object.decisions === "string")
                        message.decisions = $parseInt(object.decisions, 10);
                    else if (typeof object.decisions === "number")
                        message.decisions = object.decisions;
                    else if (typeof object.decisions === "object")
                        message.decisions = new $util.LongBits(object.decisions.low >>> 0, object.decisions.high >>> 0).toNumber(true);
            if (object.error != null)
                if (typeof object.error !== "string" || object.error.length)
                    message.error = $String(object.error);
            return message;
        };

        /**
         * Creates a plain object from a BranchEvaluationResult message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.BranchEvaluationResult
         * @static
         * @param {game.BranchEvaluationResult} message BranchEvaluationResult
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        BranchEvaluationResult.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.arrays || options.defaults)
                object.rewards = [];
            if (options.defaults) {
                object.actionId = 0;
                object.terminated = false;
                object.truncated = false;
                object.roundOutcome = null;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, true);
                    object.decisions = options.longs === $String ? long.toString() : options.longs === $Number ? long.toNumber() : typeof $BigInt !== "undefined" && options.longs === $BigInt ? long.toBigInt() : long;
                } else
                    object.decisions = options.longs === $String ? "0" : typeof $BigInt !== "undefined" && options.longs === $BigInt ? $BigInt("0") : 0;
                object.error = "";
            }
            if (message.actionId != null && $Object.hasOwnProperty.call(message, "actionId"))
                object.actionId = message.actionId;
            if (message.rewards && message.rewards.length) {
                object.rewards = $Array(message.rewards.length);
                for (let j = 0; j < message.rewards.length; ++j)
                    object.rewards[j] = options.json && !$isFinite(message.rewards[j]) ? $String(message.rewards[j]) : message.rewards[j];
            }
            if (message.terminated != null && $Object.hasOwnProperty.call(message, "terminated"))
                object.terminated = message.terminated;
            if (message.truncated != null && $Object.hasOwnProperty.call(message, "truncated"))
                object.truncated = message.truncated;
            if (message.roundOutcome != null && $Object.hasOwnProperty.call(message, "roundOutcome"))
                object.roundOutcome = $root.game.RoundOutcome.toObject(message.roundOutcome, options, _depth + 1);
            if (message.decisions != null && $Object.hasOwnProperty.call(message, "decisions"))
                if (typeof $BigInt !== "undefined" && options.longs === $BigInt)
                    object.decisions = typeof message.decisions === "number" ? $BigInt(message.decisions) : $util.Long.fromBits(message.decisions.low >>> 0, message.decisions.high >>> 0, true).toBigInt();
                else if (typeof message.decisions === "number")
                    object.decisions = options.longs === $String ? $String(message.decisions) : message.decisions;
                else
                    object.decisions = options.longs === $String ? $util.Long.prototype.toString.call(message.decisions) : options.longs === $Number ? new $util.LongBits(message.decisions.low >>> 0, message.decisions.high >>> 0).toNumber(true) : message.decisions;
            if (message.error != null && $Object.hasOwnProperty.call(message, "error"))
                object.error = message.error;
            return object;
        };

        /**
         * Converts this BranchEvaluationResult to JSON.
         * @function toJSON
         * @memberof game.BranchEvaluationResult
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        BranchEvaluationResult.prototype.toJSON = function() {
            return BranchEvaluationResult.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for BranchEvaluationResult
         * @function getTypeUrl
         * @memberof game.BranchEvaluationResult
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        BranchEvaluationResult.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.BranchEvaluationResult";
        };

        return BranchEvaluationResult;
    })();

    game.BranchEvaluationResponse = (function() {

        /**
         * Properties of a BranchEvaluationResponse.
         * @typedef {Object} game.BranchEvaluationResponse.$Properties
         * @property {game.SeatObservation.$Properties} [observation] BranchEvaluationResponse observation
         * @property {Array.<game.BranchEvaluationResult.$Properties>} [results] BranchEvaluationResponse results
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a BranchEvaluationResponse.
         * @memberof game
         * @interface IBranchEvaluationResponse
         * @augments game.BranchEvaluationResponse.$Properties
         * @deprecated Use game.BranchEvaluationResponse.$Properties instead.
         */

        /**
         * Shape of a BranchEvaluationResponse.
         * @typedef {game.BranchEvaluationResponse.$Properties} game.BranchEvaluationResponse.$Shape
         */

        /**
         * Constructs a new BranchEvaluationResponse.
         * @memberof game
         * @classdesc Represents a BranchEvaluationResponse.
         * @constructor
         * @param {game.BranchEvaluationResponse.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const BranchEvaluationResponse = function (properties) {
            this.results = [];
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

        /**
         * BranchEvaluationResponse observation.
         * @member {game.SeatObservation} observation
         * @memberof game.BranchEvaluationResponse
         * @instance
         */
        BranchEvaluationResponse.prototype.observation = null;

        /**
         * BranchEvaluationResponse results.
         * @member {Array.<game.BranchEvaluationResult>} results
         * @memberof game.BranchEvaluationResponse
         * @instance
         */
        BranchEvaluationResponse.prototype.results = $util.emptyArray;

        /**
         * Creates a new BranchEvaluationResponse instance using the specified properties.
         * @function create
         * @memberof game.BranchEvaluationResponse
         * @static
         * @param {game.BranchEvaluationResponse.$Properties=} [properties] Properties to set
         * @returns {game.BranchEvaluationResponse} BranchEvaluationResponse instance
         * @type {{
         *   (properties: game.BranchEvaluationResponse.$Shape): game.BranchEvaluationResponse & game.BranchEvaluationResponse.$Shape;
         *   (properties?: game.BranchEvaluationResponse.$Properties): game.BranchEvaluationResponse;
         * }}
         */
        BranchEvaluationResponse.create = function(properties) {
            return new BranchEvaluationResponse(properties);
        };

        /**
         * Encodes the specified BranchEvaluationResponse message. Does not implicitly {@link game.BranchEvaluationResponse.verify|verify} messages.
         * @function encode
         * @memberof game.BranchEvaluationResponse
         * @static
         * @param {game.BranchEvaluationResponse.$Properties} message BranchEvaluationResponse message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        BranchEvaluationResponse.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.observation != null && $Object.hasOwnProperty.call(message, "observation"))
                $root.game.SeatObservation.encode(message.observation, writer.uint32(/* id 1, wireType 2 =*/10).fork(), _depth + 1).ldelim();
            if (message.results != null && message.results.length)
                for (let i = 0; i < message.results.length; ++i)
                    $root.game.BranchEvaluationResult.encode(message.results[i], writer.uint32(/* id 2, wireType 2 =*/18).fork(), _depth + 1).ldelim();
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified BranchEvaluationResponse message, length delimited. Does not implicitly {@link game.BranchEvaluationResponse.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.BranchEvaluationResponse
         * @static
         * @param {game.BranchEvaluationResponse.$Properties} message BranchEvaluationResponse message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        BranchEvaluationResponse.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a BranchEvaluationResponse message from the specified reader or buffer.
         * @function decode
         * @memberof game.BranchEvaluationResponse
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.BranchEvaluationResponse & game.BranchEvaluationResponse.$Shape} BranchEvaluationResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        BranchEvaluationResponse.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.BranchEvaluationResponse(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 2)
                            break;
                        message.observation = $root.game.SeatObservation.decode(reader, reader.uint32(), $undefined, _depth + 1, message.observation);
                        continue;
                    }
                case 2: {
                        if (wireType !== 2)
                            break;
                        if (!(message.results && message.results.length))
                            message.results = [];
                        message.results.push($root.game.BranchEvaluationResult.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a BranchEvaluationResponse message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.BranchEvaluationResponse
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.BranchEvaluationResponse & game.BranchEvaluationResponse.$Shape} BranchEvaluationResponse
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        BranchEvaluationResponse.decodeDelimited = function(reader) {
            if (!(reader instanceof $Reader))
                reader = new $Reader(reader);
            return this.decode(reader, reader.uint32());
        };

        /**
         * Verifies a BranchEvaluationResponse message.
         * @function verify
         * @memberof game.BranchEvaluationResponse
         * @static
         * @param {Object.<string,*>} message Plain object to verify
         * @returns {string|null} `null` if valid, otherwise the reason why it is not
         */
        BranchEvaluationResponse.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.observation != null && $Object.hasOwnProperty.call(message, "observation")) {
                let error = $root.game.SeatObservation.verify(message.observation, _depth + 1);
                if (error)
                    return "observation." + error;
            }
            if (message.results != null && $Object.hasOwnProperty.call(message, "results")) {
                if (!$Array.isArray(message.results))
                    return "results: array expected";
                for (let i = 0; i < message.results.length; ++i) {
                    let error = $root.game.BranchEvaluationResult.verify(message.results[i], _depth + 1);
                    if (error)
                        return "results." + error;
                }
            }
            return null;
        };

        /**
         * Creates a BranchEvaluationResponse message from a plain object. Also converts values to their respective internal types.
         * @function fromObject
         * @memberof game.BranchEvaluationResponse
         * @static
         * @param {Object.<string,*>} object Plain object
         * @returns {game.BranchEvaluationResponse} BranchEvaluationResponse
         */
        BranchEvaluationResponse.fromObject = function (object, _depth) {
            if (object instanceof $root.game.BranchEvaluationResponse)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.BranchEvaluationResponse: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.BranchEvaluationResponse();
            if (object.observation != null) {
                if (!$util.isObject(object.observation))
                    throw $TypeError(".game.BranchEvaluationResponse.observation: object expected");
                message.observation = $root.game.SeatObservation.fromObject(object.observation, _depth + 1);
            }
            if (object.results) {
                if (!$Array.isArray(object.results))
                    throw $TypeError(".game.BranchEvaluationResponse.results: array expected");
                message.results = $Array(object.results.length);
                for (let i = 0; i < object.results.length; ++i) {
                    if (!$util.isObject(object.results[i]))
                        throw $TypeError(".game.BranchEvaluationResponse.results: object expected");
                    message.results[i] = $root.game.BranchEvaluationResult.fromObject(object.results[i], _depth + 1);
                }
            }
            return message;
        };

        /**
         * Creates a plain object from a BranchEvaluationResponse message. Also converts values to other types if specified.
         * @function toObject
         * @memberof game.BranchEvaluationResponse
         * @static
         * @param {game.BranchEvaluationResponse} message BranchEvaluationResponse
         * @param {$protobuf.IConversionOptions} [options] Conversion options
         * @returns {Object.<string,*>} Plain object
         */
        BranchEvaluationResponse.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.arrays || options.defaults)
                object.results = [];
            if (options.defaults)
                object.observation = null;
            if (message.observation != null && $Object.hasOwnProperty.call(message, "observation"))
                object.observation = $root.game.SeatObservation.toObject(message.observation, options, _depth + 1);
            if (message.results && message.results.length) {
                object.results = $Array(message.results.length);
                for (let j = 0; j < message.results.length; ++j)
                    object.results[j] = $root.game.BranchEvaluationResult.toObject(message.results[j], options, _depth + 1);
            }
            return object;
        };

        /**
         * Converts this BranchEvaluationResponse to JSON.
         * @function toJSON
         * @memberof game.BranchEvaluationResponse
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        BranchEvaluationResponse.prototype.toJSON = function() {
            return BranchEvaluationResponse.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for BranchEvaluationResponse
         * @function getTypeUrl
         * @memberof game.BranchEvaluationResponse
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        BranchEvaluationResponse.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.BranchEvaluationResponse";
        };

        return BranchEvaluationResponse;
    })();

    game.TrajectoryRequest = (function() {

        /**
         * Properties of a TrajectoryRequest.
         * @typedef {Object} game.TrajectoryRequest.$Properties
         * @property {number} [episodes] TrajectoryRequest episodes
         * @property {number|Long} [startSeed] TrajectoryRequest startSeed
         * @property {game.EnvConfig.$Properties} [config] TrajectoryRequest config
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a TrajectoryRequest.
         * @memberof game
         * @interface ITrajectoryRequest
         * @augments game.TrajectoryRequest.$Properties
         * @deprecated Use game.TrajectoryRequest.$Properties instead.
         */

        /**
         * Shape of a TrajectoryRequest.
         * @typedef {game.TrajectoryRequest.$Properties} game.TrajectoryRequest.$Shape
         */

        /**
         * Constructs a new TrajectoryRequest.
         * @memberof game
         * @classdesc Represents a TrajectoryRequest.
         * @constructor
         * @param {game.TrajectoryRequest.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const TrajectoryRequest = function (properties) {
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.TrajectoryRequest.$Properties=} [properties] Properties to set
         * @returns {game.TrajectoryRequest} TrajectoryRequest instance
         * @type {{
         *   (properties: game.TrajectoryRequest.$Shape): game.TrajectoryRequest & game.TrajectoryRequest.$Shape;
         *   (properties?: game.TrajectoryRequest.$Properties): game.TrajectoryRequest;
         * }}
         */
        TrajectoryRequest.create = function(properties) {
            return new TrajectoryRequest(properties);
        };

        /**
         * Encodes the specified TrajectoryRequest message. Does not implicitly {@link game.TrajectoryRequest.verify|verify} messages.
         * @function encode
         * @memberof game.TrajectoryRequest
         * @static
         * @param {game.TrajectoryRequest.$Properties} message TrajectoryRequest message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        TrajectoryRequest.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.episodes != null && $Object.hasOwnProperty.call(message, "episodes") && message.episodes !== 0)
                writer.uint32(/* id 1, wireType 0 =*/8).uint32(message.episodes);
            if (message.startSeed != null && $Object.hasOwnProperty.call(message, "startSeed") && (typeof message.startSeed === "object" ? message.startSeed.low || message.startSeed.high : message.startSeed !== 0))
                writer.uint32(/* id 2, wireType 0 =*/16).uint64(message.startSeed);
            if (message.config != null && $Object.hasOwnProperty.call(message, "config"))
                $root.game.EnvConfig.encode(message.config, writer.uint32(/* id 3, wireType 2 =*/26).fork(), _depth + 1).ldelim();
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified TrajectoryRequest message, length delimited. Does not implicitly {@link game.TrajectoryRequest.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.TrajectoryRequest
         * @static
         * @param {game.TrajectoryRequest.$Properties} message TrajectoryRequest message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        TrajectoryRequest.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a TrajectoryRequest message from the specified reader or buffer.
         * @function decode
         * @memberof game.TrajectoryRequest
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.TrajectoryRequest & game.TrajectoryRequest.$Shape} TrajectoryRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        TrajectoryRequest.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.TrajectoryRequest(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.episodes = value;
                        else
                            delete message.episodes;
                        continue;
                    }
                case 2: {
                        if (wireType !== 0)
                            break;
                        if (typeof (value = reader.uint64()) === "object" ? value.low || value.high : value !== 0)
                            message.startSeed = value;
                        else
                            delete message.startSeed;
                        continue;
                    }
                case 3: {
                        if (wireType !== 2)
                            break;
                        message.config = $root.game.EnvConfig.decode(reader, reader.uint32(), $undefined, _depth + 1, message.config);
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a TrajectoryRequest message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.TrajectoryRequest
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.TrajectoryRequest & game.TrajectoryRequest.$Shape} TrajectoryRequest
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        TrajectoryRequest.decodeDelimited = function(reader) {
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
        TrajectoryRequest.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.episodes != null && $Object.hasOwnProperty.call(message, "episodes"))
                if (!$util.isInteger(message.episodes))
                    return "episodes: integer expected";
            if (message.startSeed != null && $Object.hasOwnProperty.call(message, "startSeed"))
                if (!$util.isInteger(message.startSeed) && !(message.startSeed && $util.isInteger(message.startSeed.low) && $util.isInteger(message.startSeed.high)))
                    return "startSeed: integer|Long expected";
            if (message.config != null && $Object.hasOwnProperty.call(message, "config")) {
                let error = $root.game.EnvConfig.verify(message.config, _depth + 1);
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
        TrajectoryRequest.fromObject = function (object, _depth) {
            if (object instanceof $root.game.TrajectoryRequest)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.TrajectoryRequest: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.TrajectoryRequest();
            if (object.episodes != null)
                if ($Number(object.episodes) !== 0)
                    message.episodes = object.episodes >>> 0;
            if (object.startSeed != null)
                if (typeof object.startSeed === "object" ? object.startSeed.low || object.startSeed.high : $Number(object.startSeed) !== 0)
                    if ($util.Long)
                        message.startSeed = $util.Long.fromValue(object.startSeed, true);
                    else if (typeof object.startSeed === "string")
                        message.startSeed = $parseInt(object.startSeed, 10);
                    else if (typeof object.startSeed === "number")
                        message.startSeed = object.startSeed;
                    else if (typeof object.startSeed === "object")
                        message.startSeed = new $util.LongBits(object.startSeed.low >>> 0, object.startSeed.high >>> 0).toNumber(true);
            if (object.config != null) {
                if (!$util.isObject(object.config))
                    throw $TypeError(".game.TrajectoryRequest.config: object expected");
                message.config = $root.game.EnvConfig.fromObject(object.config, _depth + 1);
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
        TrajectoryRequest.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.defaults) {
                object.episodes = 0;
                if ($util.Long) {
                    let long = new $util.Long(0, 0, true);
                    object.startSeed = options.longs === $String ? long.toString() : options.longs === $Number ? long.toNumber() : typeof $BigInt !== "undefined" && options.longs === $BigInt ? long.toBigInt() : long;
                } else
                    object.startSeed = options.longs === $String ? "0" : typeof $BigInt !== "undefined" && options.longs === $BigInt ? $BigInt("0") : 0;
                object.config = null;
            }
            if (message.episodes != null && $Object.hasOwnProperty.call(message, "episodes"))
                object.episodes = message.episodes;
            if (message.startSeed != null && $Object.hasOwnProperty.call(message, "startSeed"))
                if (typeof $BigInt !== "undefined" && options.longs === $BigInt)
                    object.startSeed = typeof message.startSeed === "number" ? $BigInt(message.startSeed) : $util.Long.fromBits(message.startSeed.low >>> 0, message.startSeed.high >>> 0, true).toBigInt();
                else if (typeof message.startSeed === "number")
                    object.startSeed = options.longs === $String ? $String(message.startSeed) : message.startSeed;
                else
                    object.startSeed = options.longs === $String ? $util.Long.prototype.toString.call(message.startSeed) : options.longs === $Number ? new $util.LongBits(message.startSeed.low >>> 0, message.startSeed.high >>> 0).toNumber(true) : message.startSeed;
            if (message.config != null && $Object.hasOwnProperty.call(message, "config"))
                object.config = $root.game.EnvConfig.toObject(message.config, options, _depth + 1);
            return object;
        };

        /**
         * Converts this TrajectoryRequest to JSON.
         * @function toJSON
         * @memberof game.TrajectoryRequest
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        TrajectoryRequest.prototype.toJSON = function() {
            return TrajectoryRequest.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for TrajectoryRequest
         * @function getTypeUrl
         * @memberof game.TrajectoryRequest
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        TrajectoryRequest.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.TrajectoryRequest";
        };

        return TrajectoryRequest;
    })();

    game.TrajectorySample = (function() {

        /**
         * Properties of a TrajectorySample.
         * @typedef {Object} game.TrajectorySample.$Properties
         * @property {game.SeatObservation.$Properties} [observation] TrajectorySample observation
         * @property {number} [actionId] TrajectorySample actionId
         * @property {Array.<number>} [rewards] TrajectorySample rewards
         * @property {game.SeatObservation.$Properties} [nextObservation] TrajectorySample nextObservation
         * @property {boolean} [terminated] TrajectorySample terminated
         * @property {boolean} [truncated] TrajectorySample truncated
         * @property {number} [actingSeat] TrajectorySample actingSeat
         * @property {number|Long} [episodeIndex] TrajectorySample episodeIndex
         * @property {Array.<number>} [terminalRewards] TrajectorySample terminalRewards
         * @property {game.RoundOutcome.$Properties} [terminalOutcome] TrajectorySample terminalOutcome
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a TrajectorySample.
         * @memberof game
         * @interface ITrajectorySample
         * @augments game.TrajectorySample.$Properties
         * @deprecated Use game.TrajectorySample.$Properties instead.
         */

        /**
         * Shape of a TrajectorySample.
         * @typedef {game.TrajectorySample.$Properties} game.TrajectorySample.$Shape
         */

        /**
         * Constructs a new TrajectorySample.
         * @memberof game
         * @classdesc Represents a TrajectorySample.
         * @constructor
         * @param {game.TrajectorySample.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const TrajectorySample = function (properties) {
            this.rewards = [];
            this.terminalRewards = [];
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.TrajectorySample.$Properties=} [properties] Properties to set
         * @returns {game.TrajectorySample} TrajectorySample instance
         * @type {{
         *   (properties: game.TrajectorySample.$Shape): game.TrajectorySample & game.TrajectorySample.$Shape;
         *   (properties?: game.TrajectorySample.$Properties): game.TrajectorySample;
         * }}
         */
        TrajectorySample.create = function(properties) {
            return new TrajectorySample(properties);
        };

        /**
         * Encodes the specified TrajectorySample message. Does not implicitly {@link game.TrajectorySample.verify|verify} messages.
         * @function encode
         * @memberof game.TrajectorySample
         * @static
         * @param {game.TrajectorySample.$Properties} message TrajectorySample message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        TrajectorySample.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.observation != null && $Object.hasOwnProperty.call(message, "observation"))
                $root.game.SeatObservation.encode(message.observation, writer.uint32(/* id 1, wireType 2 =*/10).fork(), _depth + 1).ldelim();
            if (message.actionId != null && $Object.hasOwnProperty.call(message, "actionId") && message.actionId !== 0)
                writer.uint32(/* id 2, wireType 0 =*/16).uint32(message.actionId);
            if (message.rewards != null && message.rewards.length) {
                writer.uint32(/* id 3, wireType 2 =*/26).fork();
                for (let i = 0; i < message.rewards.length; ++i)
                    writer.float(message.rewards[i]);
                writer.ldelim();
            }
            if (message.nextObservation != null && $Object.hasOwnProperty.call(message, "nextObservation"))
                $root.game.SeatObservation.encode(message.nextObservation, writer.uint32(/* id 4, wireType 2 =*/34).fork(), _depth + 1).ldelim();
            if (message.terminated != null && $Object.hasOwnProperty.call(message, "terminated") && message.terminated !== false)
                writer.uint32(/* id 5, wireType 0 =*/40).bool(message.terminated);
            if (message.truncated != null && $Object.hasOwnProperty.call(message, "truncated") && message.truncated !== false)
                writer.uint32(/* id 6, wireType 0 =*/48).bool(message.truncated);
            if (message.actingSeat != null && $Object.hasOwnProperty.call(message, "actingSeat") && message.actingSeat !== 0)
                writer.uint32(/* id 7, wireType 0 =*/56).uint32(message.actingSeat);
            if (message.episodeIndex != null && $Object.hasOwnProperty.call(message, "episodeIndex") && (typeof message.episodeIndex === "object" ? message.episodeIndex.low || message.episodeIndex.high : message.episodeIndex !== 0))
                writer.uint32(/* id 8, wireType 0 =*/64).uint64(message.episodeIndex);
            if (message.terminalRewards != null && message.terminalRewards.length) {
                writer.uint32(/* id 9, wireType 2 =*/74).fork();
                for (let i = 0; i < message.terminalRewards.length; ++i)
                    writer.float(message.terminalRewards[i]);
                writer.ldelim();
            }
            if (message.terminalOutcome != null && $Object.hasOwnProperty.call(message, "terminalOutcome"))
                $root.game.RoundOutcome.encode(message.terminalOutcome, writer.uint32(/* id 10, wireType 2 =*/82).fork(), _depth + 1).ldelim();
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified TrajectorySample message, length delimited. Does not implicitly {@link game.TrajectorySample.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.TrajectorySample
         * @static
         * @param {game.TrajectorySample.$Properties} message TrajectorySample message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        TrajectorySample.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a TrajectorySample message from the specified reader or buffer.
         * @function decode
         * @memberof game.TrajectorySample
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.TrajectorySample & game.TrajectorySample.$Shape} TrajectorySample
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        TrajectorySample.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.TrajectorySample(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 2)
                            break;
                        message.observation = $root.game.SeatObservation.decode(reader, reader.uint32(), $undefined, _depth + 1, message.observation);
                        continue;
                    }
                case 2: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.actionId = value;
                        else
                            delete message.actionId;
                        continue;
                    }
                case 3: {
                        if (wireType === 2) {
                            if (!(message.rewards && message.rewards.length))
                                message.rewards = [];
                            let end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.rewards.push(reader.float());
                            continue;
                        }
                        if (wireType !== 5)
                            break;
                        if (!(message.rewards && message.rewards.length))
                            message.rewards = [];
                        message.rewards.push(reader.float());
                        continue;
                    }
                case 4: {
                        if (wireType !== 2)
                            break;
                        message.nextObservation = $root.game.SeatObservation.decode(reader, reader.uint32(), $undefined, _depth + 1, message.nextObservation);
                        continue;
                    }
                case 5: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.terminated = value;
                        else
                            delete message.terminated;
                        continue;
                    }
                case 6: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.bool())
                            message.truncated = value;
                        else
                            delete message.truncated;
                        continue;
                    }
                case 7: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.actingSeat = value;
                        else
                            delete message.actingSeat;
                        continue;
                    }
                case 8: {
                        if (wireType !== 0)
                            break;
                        if (typeof (value = reader.uint64()) === "object" ? value.low || value.high : value !== 0)
                            message.episodeIndex = value;
                        else
                            delete message.episodeIndex;
                        continue;
                    }
                case 9: {
                        if (wireType === 2) {
                            if (!(message.terminalRewards && message.terminalRewards.length))
                                message.terminalRewards = [];
                            let end2 = reader.uint32() + reader.pos;
                            while (reader.pos < end2)
                                message.terminalRewards.push(reader.float());
                            continue;
                        }
                        if (wireType !== 5)
                            break;
                        if (!(message.terminalRewards && message.terminalRewards.length))
                            message.terminalRewards = [];
                        message.terminalRewards.push(reader.float());
                        continue;
                    }
                case 10: {
                        if (wireType !== 2)
                            break;
                        message.terminalOutcome = $root.game.RoundOutcome.decode(reader, reader.uint32(), $undefined, _depth + 1, message.terminalOutcome);
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a TrajectorySample message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.TrajectorySample
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.TrajectorySample & game.TrajectorySample.$Shape} TrajectorySample
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        TrajectorySample.decodeDelimited = function(reader) {
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
        TrajectorySample.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.observation != null && $Object.hasOwnProperty.call(message, "observation")) {
                let error = $root.game.SeatObservation.verify(message.observation, _depth + 1);
                if (error)
                    return "observation." + error;
            }
            if (message.actionId != null && $Object.hasOwnProperty.call(message, "actionId"))
                if (!$util.isInteger(message.actionId))
                    return "actionId: integer expected";
            if (message.rewards != null && $Object.hasOwnProperty.call(message, "rewards")) {
                if (!$Array.isArray(message.rewards))
                    return "rewards: array expected";
                for (let i = 0; i < message.rewards.length; ++i)
                    if (typeof message.rewards[i] !== "number")
                        return "rewards: number[] expected";
            }
            if (message.nextObservation != null && $Object.hasOwnProperty.call(message, "nextObservation")) {
                let error = $root.game.SeatObservation.verify(message.nextObservation, _depth + 1);
                if (error)
                    return "nextObservation." + error;
            }
            if (message.terminated != null && $Object.hasOwnProperty.call(message, "terminated"))
                if (typeof message.terminated !== "boolean")
                    return "terminated: boolean expected";
            if (message.truncated != null && $Object.hasOwnProperty.call(message, "truncated"))
                if (typeof message.truncated !== "boolean")
                    return "truncated: boolean expected";
            if (message.actingSeat != null && $Object.hasOwnProperty.call(message, "actingSeat"))
                if (!$util.isInteger(message.actingSeat))
                    return "actingSeat: integer expected";
            if (message.episodeIndex != null && $Object.hasOwnProperty.call(message, "episodeIndex"))
                if (!$util.isInteger(message.episodeIndex) && !(message.episodeIndex && $util.isInteger(message.episodeIndex.low) && $util.isInteger(message.episodeIndex.high)))
                    return "episodeIndex: integer|Long expected";
            if (message.terminalRewards != null && $Object.hasOwnProperty.call(message, "terminalRewards")) {
                if (!$Array.isArray(message.terminalRewards))
                    return "terminalRewards: array expected";
                for (let i = 0; i < message.terminalRewards.length; ++i)
                    if (typeof message.terminalRewards[i] !== "number")
                        return "terminalRewards: number[] expected";
            }
            if (message.terminalOutcome != null && $Object.hasOwnProperty.call(message, "terminalOutcome")) {
                let error = $root.game.RoundOutcome.verify(message.terminalOutcome, _depth + 1);
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
        TrajectorySample.fromObject = function (object, _depth) {
            if (object instanceof $root.game.TrajectorySample)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.TrajectorySample: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.TrajectorySample();
            if (object.observation != null) {
                if (!$util.isObject(object.observation))
                    throw $TypeError(".game.TrajectorySample.observation: object expected");
                message.observation = $root.game.SeatObservation.fromObject(object.observation, _depth + 1);
            }
            if (object.actionId != null)
                if ($Number(object.actionId) !== 0)
                    message.actionId = object.actionId >>> 0;
            if (object.rewards) {
                if (!$Array.isArray(object.rewards))
                    throw $TypeError(".game.TrajectorySample.rewards: array expected");
                message.rewards = $Array(object.rewards.length);
                for (let i = 0; i < object.rewards.length; ++i)
                    message.rewards[i] = $Number(object.rewards[i]);
            }
            if (object.nextObservation != null) {
                if (!$util.isObject(object.nextObservation))
                    throw $TypeError(".game.TrajectorySample.nextObservation: object expected");
                message.nextObservation = $root.game.SeatObservation.fromObject(object.nextObservation, _depth + 1);
            }
            if (object.terminated != null)
                if (object.terminated)
                    message.terminated = $Boolean(object.terminated);
            if (object.truncated != null)
                if (object.truncated)
                    message.truncated = $Boolean(object.truncated);
            if (object.actingSeat != null)
                if ($Number(object.actingSeat) !== 0)
                    message.actingSeat = object.actingSeat >>> 0;
            if (object.episodeIndex != null)
                if (typeof object.episodeIndex === "object" ? object.episodeIndex.low || object.episodeIndex.high : $Number(object.episodeIndex) !== 0)
                    if ($util.Long)
                        message.episodeIndex = $util.Long.fromValue(object.episodeIndex, true);
                    else if (typeof object.episodeIndex === "string")
                        message.episodeIndex = $parseInt(object.episodeIndex, 10);
                    else if (typeof object.episodeIndex === "number")
                        message.episodeIndex = object.episodeIndex;
                    else if (typeof object.episodeIndex === "object")
                        message.episodeIndex = new $util.LongBits(object.episodeIndex.low >>> 0, object.episodeIndex.high >>> 0).toNumber(true);
            if (object.terminalRewards) {
                if (!$Array.isArray(object.terminalRewards))
                    throw $TypeError(".game.TrajectorySample.terminalRewards: array expected");
                message.terminalRewards = $Array(object.terminalRewards.length);
                for (let i = 0; i < object.terminalRewards.length; ++i)
                    message.terminalRewards[i] = $Number(object.terminalRewards[i]);
            }
            if (object.terminalOutcome != null) {
                if (!$util.isObject(object.terminalOutcome))
                    throw $TypeError(".game.TrajectorySample.terminalOutcome: object expected");
                message.terminalOutcome = $root.game.RoundOutcome.fromObject(object.terminalOutcome, _depth + 1);
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
        TrajectorySample.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
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
                    let long = new $util.Long(0, 0, true);
                    object.episodeIndex = options.longs === $String ? long.toString() : options.longs === $Number ? long.toNumber() : typeof $BigInt !== "undefined" && options.longs === $BigInt ? long.toBigInt() : long;
                } else
                    object.episodeIndex = options.longs === $String ? "0" : typeof $BigInt !== "undefined" && options.longs === $BigInt ? $BigInt("0") : 0;
                object.terminalOutcome = null;
            }
            if (message.observation != null && $Object.hasOwnProperty.call(message, "observation"))
                object.observation = $root.game.SeatObservation.toObject(message.observation, options, _depth + 1);
            if (message.actionId != null && $Object.hasOwnProperty.call(message, "actionId"))
                object.actionId = message.actionId;
            if (message.rewards && message.rewards.length) {
                object.rewards = $Array(message.rewards.length);
                for (let j = 0; j < message.rewards.length; ++j)
                    object.rewards[j] = options.json && !$isFinite(message.rewards[j]) ? $String(message.rewards[j]) : message.rewards[j];
            }
            if (message.nextObservation != null && $Object.hasOwnProperty.call(message, "nextObservation"))
                object.nextObservation = $root.game.SeatObservation.toObject(message.nextObservation, options, _depth + 1);
            if (message.terminated != null && $Object.hasOwnProperty.call(message, "terminated"))
                object.terminated = message.terminated;
            if (message.truncated != null && $Object.hasOwnProperty.call(message, "truncated"))
                object.truncated = message.truncated;
            if (message.actingSeat != null && $Object.hasOwnProperty.call(message, "actingSeat"))
                object.actingSeat = message.actingSeat;
            if (message.episodeIndex != null && $Object.hasOwnProperty.call(message, "episodeIndex"))
                if (typeof $BigInt !== "undefined" && options.longs === $BigInt)
                    object.episodeIndex = typeof message.episodeIndex === "number" ? $BigInt(message.episodeIndex) : $util.Long.fromBits(message.episodeIndex.low >>> 0, message.episodeIndex.high >>> 0, true).toBigInt();
                else if (typeof message.episodeIndex === "number")
                    object.episodeIndex = options.longs === $String ? $String(message.episodeIndex) : message.episodeIndex;
                else
                    object.episodeIndex = options.longs === $String ? $util.Long.prototype.toString.call(message.episodeIndex) : options.longs === $Number ? new $util.LongBits(message.episodeIndex.low >>> 0, message.episodeIndex.high >>> 0).toNumber(true) : message.episodeIndex;
            if (message.terminalRewards && message.terminalRewards.length) {
                object.terminalRewards = $Array(message.terminalRewards.length);
                for (let j = 0; j < message.terminalRewards.length; ++j)
                    object.terminalRewards[j] = options.json && !$isFinite(message.terminalRewards[j]) ? $String(message.terminalRewards[j]) : message.terminalRewards[j];
            }
            if (message.terminalOutcome != null && $Object.hasOwnProperty.call(message, "terminalOutcome"))
                object.terminalOutcome = $root.game.RoundOutcome.toObject(message.terminalOutcome, options, _depth + 1);
            return object;
        };

        /**
         * Converts this TrajectorySample to JSON.
         * @function toJSON
         * @memberof game.TrajectorySample
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        TrajectorySample.prototype.toJSON = function() {
            return TrajectorySample.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for TrajectorySample
         * @function getTypeUrl
         * @memberof game.TrajectorySample
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        TrajectorySample.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.TrajectorySample";
        };

        return TrajectorySample;
    })();

    game.TrajectoryDataset = (function() {

        /**
         * Properties of a TrajectoryDataset.
         * @typedef {Object} game.TrajectoryDataset.$Properties
         * @property {Array.<game.TrajectorySample.$Properties>} [samples] TrajectoryDataset samples
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a TrajectoryDataset.
         * @memberof game
         * @interface ITrajectoryDataset
         * @augments game.TrajectoryDataset.$Properties
         * @deprecated Use game.TrajectoryDataset.$Properties instead.
         */

        /**
         * Shape of a TrajectoryDataset.
         * @typedef {game.TrajectoryDataset.$Properties} game.TrajectoryDataset.$Shape
         */

        /**
         * Constructs a new TrajectoryDataset.
         * @memberof game
         * @classdesc Represents a TrajectoryDataset.
         * @constructor
         * @param {game.TrajectoryDataset.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const TrajectoryDataset = function (properties) {
            this.samples = [];
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.TrajectoryDataset.$Properties=} [properties] Properties to set
         * @returns {game.TrajectoryDataset} TrajectoryDataset instance
         * @type {{
         *   (properties: game.TrajectoryDataset.$Shape): game.TrajectoryDataset & game.TrajectoryDataset.$Shape;
         *   (properties?: game.TrajectoryDataset.$Properties): game.TrajectoryDataset;
         * }}
         */
        TrajectoryDataset.create = function(properties) {
            return new TrajectoryDataset(properties);
        };

        /**
         * Encodes the specified TrajectoryDataset message. Does not implicitly {@link game.TrajectoryDataset.verify|verify} messages.
         * @function encode
         * @memberof game.TrajectoryDataset
         * @static
         * @param {game.TrajectoryDataset.$Properties} message TrajectoryDataset message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        TrajectoryDataset.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.samples != null && message.samples.length)
                for (let i = 0; i < message.samples.length; ++i)
                    $root.game.TrajectorySample.encode(message.samples[i], writer.uint32(/* id 1, wireType 2 =*/10).fork(), _depth + 1).ldelim();
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified TrajectoryDataset message, length delimited. Does not implicitly {@link game.TrajectoryDataset.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.TrajectoryDataset
         * @static
         * @param {game.TrajectoryDataset.$Properties} message TrajectoryDataset message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        TrajectoryDataset.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a TrajectoryDataset message from the specified reader or buffer.
         * @function decode
         * @memberof game.TrajectoryDataset
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.TrajectoryDataset & game.TrajectoryDataset.$Shape} TrajectoryDataset
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        TrajectoryDataset.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.TrajectoryDataset();
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 2)
                            break;
                        if (!(message.samples && message.samples.length))
                            message.samples = [];
                        message.samples.push($root.game.TrajectorySample.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a TrajectoryDataset message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.TrajectoryDataset
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.TrajectoryDataset & game.TrajectoryDataset.$Shape} TrajectoryDataset
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        TrajectoryDataset.decodeDelimited = function(reader) {
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
        TrajectoryDataset.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.samples != null && $Object.hasOwnProperty.call(message, "samples")) {
                if (!$Array.isArray(message.samples))
                    return "samples: array expected";
                for (let i = 0; i < message.samples.length; ++i) {
                    let error = $root.game.TrajectorySample.verify(message.samples[i], _depth + 1);
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
        TrajectoryDataset.fromObject = function (object, _depth) {
            if (object instanceof $root.game.TrajectoryDataset)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.TrajectoryDataset: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.TrajectoryDataset();
            if (object.samples) {
                if (!$Array.isArray(object.samples))
                    throw $TypeError(".game.TrajectoryDataset.samples: array expected");
                message.samples = $Array(object.samples.length);
                for (let i = 0; i < object.samples.length; ++i) {
                    if (!$util.isObject(object.samples[i]))
                        throw $TypeError(".game.TrajectoryDataset.samples: object expected");
                    message.samples[i] = $root.game.TrajectorySample.fromObject(object.samples[i], _depth + 1);
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
        TrajectoryDataset.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.arrays || options.defaults)
                object.samples = [];
            if (message.samples && message.samples.length) {
                object.samples = $Array(message.samples.length);
                for (let j = 0; j < message.samples.length; ++j)
                    object.samples[j] = $root.game.TrajectorySample.toObject(message.samples[j], options, _depth + 1);
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
        TrajectoryDataset.prototype.toJSON = function() {
            return TrajectoryDataset.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for TrajectoryDataset
         * @function getTypeUrl
         * @memberof game.TrajectoryDataset
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        TrajectoryDataset.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.TrajectoryDataset";
        };

        return TrajectoryDataset;
    })();

    /**
     * Difficulty enum.
     * @name game.Difficulty
     * @enum {number}
     * @property {number} DIFFICULTY_UNSPECIFIED=0 DIFFICULTY_UNSPECIFIED value
     * @property {number} DIFFICULTY_HEURISTIC=1 DIFFICULTY_HEURISTIC value
     * @property {number} DIFFICULTY_RL=2 DIFFICULTY_RL value
     */
    game.Difficulty = (function() {
        const valuesById = $Object.create(null), values = $Object.create(valuesById);
        values[valuesById[0] = "DIFFICULTY_UNSPECIFIED"] = 0;
        values[valuesById[1] = "DIFFICULTY_HEURISTIC"] = 1;
        values[valuesById[2] = "DIFFICULTY_RL"] = 2;
        return values;
    })();

    game.SeatConfig = (function() {

        /**
         * Properties of a SeatConfig.
         * @typedef {Object} game.SeatConfig.$Properties
         * @property {string} [kind] SeatConfig kind
         * @property {number} [userId] SeatConfig userId
         * @property {string} [username] SeatConfig username
         * @property {game.Difficulty} [difficulty] SeatConfig difficulty
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a SeatConfig.
         * @memberof game
         * @interface ISeatConfig
         * @augments game.SeatConfig.$Properties
         * @deprecated Use game.SeatConfig.$Properties instead.
         */

        /**
         * Shape of a SeatConfig.
         * @typedef {game.SeatConfig.$Properties} game.SeatConfig.$Shape
         */

        /**
         * Constructs a new SeatConfig.
         * @memberof game
         * @classdesc Represents a SeatConfig.
         * @constructor
         * @param {game.SeatConfig.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const SeatConfig = function (properties) {
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.SeatConfig.$Properties=} [properties] Properties to set
         * @returns {game.SeatConfig} SeatConfig instance
         * @type {{
         *   (properties: game.SeatConfig.$Shape): game.SeatConfig & game.SeatConfig.$Shape;
         *   (properties?: game.SeatConfig.$Properties): game.SeatConfig;
         * }}
         */
        SeatConfig.create = function(properties) {
            return new SeatConfig(properties);
        };

        /**
         * Encodes the specified SeatConfig message. Does not implicitly {@link game.SeatConfig.verify|verify} messages.
         * @function encode
         * @memberof game.SeatConfig
         * @static
         * @param {game.SeatConfig.$Properties} message SeatConfig message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        SeatConfig.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.kind != null && $Object.hasOwnProperty.call(message, "kind") && message.kind !== "")
                writer.uint32(/* id 1, wireType 2 =*/10).string(message.kind);
            if (message.userId != null && $Object.hasOwnProperty.call(message, "userId") && message.userId !== 0)
                writer.uint32(/* id 2, wireType 0 =*/16).uint32(message.userId);
            if (message.username != null && $Object.hasOwnProperty.call(message, "username") && message.username !== "")
                writer.uint32(/* id 3, wireType 2 =*/26).string(message.username);
            if (message.difficulty != null && $Object.hasOwnProperty.call(message, "difficulty") && message.difficulty !== 0)
                writer.uint32(/* id 4, wireType 0 =*/32).int32(message.difficulty);
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified SeatConfig message, length delimited. Does not implicitly {@link game.SeatConfig.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.SeatConfig
         * @static
         * @param {game.SeatConfig.$Properties} message SeatConfig message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        SeatConfig.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a SeatConfig message from the specified reader or buffer.
         * @function decode
         * @memberof game.SeatConfig
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.SeatConfig & game.SeatConfig.$Shape} SeatConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        SeatConfig.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.SeatConfig(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 2)
                            break;
                        if ((value = reader.stringVerify()).length)
                            message.kind = value;
                        else
                            delete message.kind;
                        continue;
                    }
                case 2: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.userId = value;
                        else
                            delete message.userId;
                        continue;
                    }
                case 3: {
                        if (wireType !== 2)
                            break;
                        if ((value = reader.stringVerify()).length)
                            message.username = value;
                        else
                            delete message.username;
                        continue;
                    }
                case 4: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.difficulty = value;
                        else
                            delete message.difficulty;
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a SeatConfig message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.SeatConfig
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.SeatConfig & game.SeatConfig.$Shape} SeatConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        SeatConfig.decodeDelimited = function(reader) {
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
        SeatConfig.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.kind != null && $Object.hasOwnProperty.call(message, "kind"))
                if (!$util.isString(message.kind))
                    return "kind: string expected";
            if (message.userId != null && $Object.hasOwnProperty.call(message, "userId"))
                if (!$util.isInteger(message.userId))
                    return "userId: integer expected";
            if (message.username != null && $Object.hasOwnProperty.call(message, "username"))
                if (!$util.isString(message.username))
                    return "username: string expected";
            if (message.difficulty != null && $Object.hasOwnProperty.call(message, "difficulty"))
                if (typeof message.difficulty !== "number" || (message.difficulty | 0) !== message.difficulty)
                    return "difficulty: enum value expected";
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
        SeatConfig.fromObject = function (object, _depth) {
            if (object instanceof $root.game.SeatConfig)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.SeatConfig: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.SeatConfig();
            if (object.kind != null)
                if (typeof object.kind !== "string" || object.kind.length)
                    message.kind = $String(object.kind);
            if (object.userId != null)
                if ($Number(object.userId) !== 0)
                    message.userId = object.userId >>> 0;
            if (object.username != null)
                if (typeof object.username !== "string" || object.username.length)
                    message.username = $String(object.username);
            if (object.difficulty !== 0 && (typeof object.difficulty !== "string" || $root.game.Difficulty[object.difficulty] !== 0))
                switch (object.difficulty) {
                case "DIFFICULTY_UNSPECIFIED":
                case 0:
                    message.difficulty = 0;
                    break;
                case "DIFFICULTY_HEURISTIC":
                case 1:
                    message.difficulty = 1;
                    break;
                case "DIFFICULTY_RL":
                case 2:
                    message.difficulty = 2;
                    break;
                default:
                    if (typeof object.difficulty === "number" && (object.difficulty | 0) === object.difficulty)
                        message.difficulty = object.difficulty;
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
        SeatConfig.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.defaults) {
                object.kind = "";
                object.userId = 0;
                object.username = "";
                object.difficulty = options.enums === $String ? "DIFFICULTY_UNSPECIFIED" : 0;
            }
            if (message.kind != null && $Object.hasOwnProperty.call(message, "kind"))
                object.kind = message.kind;
            if (message.userId != null && $Object.hasOwnProperty.call(message, "userId"))
                object.userId = message.userId;
            if (message.username != null && $Object.hasOwnProperty.call(message, "username"))
                object.username = message.username;
            if (message.difficulty != null && $Object.hasOwnProperty.call(message, "difficulty"))
                object.difficulty = options.enums === $String ? $root.game.Difficulty[message.difficulty] === $undefined ? message.difficulty : $root.game.Difficulty[message.difficulty] : message.difficulty;
            return object;
        };

        /**
         * Converts this SeatConfig to JSON.
         * @function toJSON
         * @memberof game.SeatConfig
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        SeatConfig.prototype.toJSON = function() {
            return SeatConfig.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for SeatConfig
         * @function getTypeUrl
         * @memberof game.SeatConfig
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        SeatConfig.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.SeatConfig";
        };

        return SeatConfig;
    })();

    game.PrivateTableState = (function() {

        /**
         * Properties of a PrivateTableState.
         * @typedef {Object} game.PrivateTableState.$Properties
         * @property {string} [tableId] PrivateTableState tableId
         * @property {number} [hostUserId] PrivateTableState hostUserId
         * @property {Array.<game.SeatConfig.$Properties>} [seats] PrivateTableState seats
         * @property {string} [state] PrivateTableState state
         * @property {string} [matchId] PrivateTableState matchId
         * @property {game.MatchMode} [matchMode] PrivateTableState matchMode
         * @property {game.ChongciConfig.$Properties} [chongciConfig] PrivateTableState chongciConfig
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a PrivateTableState.
         * @memberof game
         * @interface IPrivateTableState
         * @augments game.PrivateTableState.$Properties
         * @deprecated Use game.PrivateTableState.$Properties instead.
         */

        /**
         * Shape of a PrivateTableState.
         * @typedef {game.PrivateTableState.$Properties} game.PrivateTableState.$Shape
         */

        /**
         * Constructs a new PrivateTableState.
         * @memberof game
         * @classdesc Represents a PrivateTableState.
         * @constructor
         * @param {game.PrivateTableState.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const PrivateTableState = function (properties) {
            this.seats = [];
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.PrivateTableState.$Properties=} [properties] Properties to set
         * @returns {game.PrivateTableState} PrivateTableState instance
         * @type {{
         *   (properties: game.PrivateTableState.$Shape): game.PrivateTableState & game.PrivateTableState.$Shape;
         *   (properties?: game.PrivateTableState.$Properties): game.PrivateTableState;
         * }}
         */
        PrivateTableState.create = function(properties) {
            return new PrivateTableState(properties);
        };

        /**
         * Encodes the specified PrivateTableState message. Does not implicitly {@link game.PrivateTableState.verify|verify} messages.
         * @function encode
         * @memberof game.PrivateTableState
         * @static
         * @param {game.PrivateTableState.$Properties} message PrivateTableState message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PrivateTableState.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.tableId != null && $Object.hasOwnProperty.call(message, "tableId") && message.tableId !== "")
                writer.uint32(/* id 1, wireType 2 =*/10).string(message.tableId);
            if (message.hostUserId != null && $Object.hasOwnProperty.call(message, "hostUserId") && message.hostUserId !== 0)
                writer.uint32(/* id 2, wireType 0 =*/16).uint32(message.hostUserId);
            if (message.seats != null && message.seats.length)
                for (let i = 0; i < message.seats.length; ++i)
                    $root.game.SeatConfig.encode(message.seats[i], writer.uint32(/* id 3, wireType 2 =*/26).fork(), _depth + 1).ldelim();
            if (message.state != null && $Object.hasOwnProperty.call(message, "state") && message.state !== "")
                writer.uint32(/* id 4, wireType 2 =*/34).string(message.state);
            if (message.matchId != null && $Object.hasOwnProperty.call(message, "matchId") && message.matchId !== "")
                writer.uint32(/* id 5, wireType 2 =*/42).string(message.matchId);
            if (message.matchMode != null && $Object.hasOwnProperty.call(message, "matchMode") && message.matchMode !== 0)
                writer.uint32(/* id 6, wireType 0 =*/48).int32(message.matchMode);
            if (message.chongciConfig != null && $Object.hasOwnProperty.call(message, "chongciConfig"))
                $root.game.ChongciConfig.encode(message.chongciConfig, writer.uint32(/* id 7, wireType 2 =*/58).fork(), _depth + 1).ldelim();
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified PrivateTableState message, length delimited. Does not implicitly {@link game.PrivateTableState.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.PrivateTableState
         * @static
         * @param {game.PrivateTableState.$Properties} message PrivateTableState message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PrivateTableState.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a PrivateTableState message from the specified reader or buffer.
         * @function decode
         * @memberof game.PrivateTableState
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.PrivateTableState & game.PrivateTableState.$Shape} PrivateTableState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PrivateTableState.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.PrivateTableState(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 2)
                            break;
                        if ((value = reader.stringVerify()).length)
                            message.tableId = value;
                        else
                            delete message.tableId;
                        continue;
                    }
                case 2: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.hostUserId = value;
                        else
                            delete message.hostUserId;
                        continue;
                    }
                case 3: {
                        if (wireType !== 2)
                            break;
                        if (!(message.seats && message.seats.length))
                            message.seats = [];
                        message.seats.push($root.game.SeatConfig.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                case 4: {
                        if (wireType !== 2)
                            break;
                        if ((value = reader.stringVerify()).length)
                            message.state = value;
                        else
                            delete message.state;
                        continue;
                    }
                case 5: {
                        if (wireType !== 2)
                            break;
                        if ((value = reader.stringVerify()).length)
                            message.matchId = value;
                        else
                            delete message.matchId;
                        continue;
                    }
                case 6: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.matchMode = value;
                        else
                            delete message.matchMode;
                        continue;
                    }
                case 7: {
                        if (wireType !== 2)
                            break;
                        message.chongciConfig = $root.game.ChongciConfig.decode(reader, reader.uint32(), $undefined, _depth + 1, message.chongciConfig);
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a PrivateTableState message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.PrivateTableState
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.PrivateTableState & game.PrivateTableState.$Shape} PrivateTableState
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PrivateTableState.decodeDelimited = function(reader) {
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
        PrivateTableState.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.tableId != null && $Object.hasOwnProperty.call(message, "tableId"))
                if (!$util.isString(message.tableId))
                    return "tableId: string expected";
            if (message.hostUserId != null && $Object.hasOwnProperty.call(message, "hostUserId"))
                if (!$util.isInteger(message.hostUserId))
                    return "hostUserId: integer expected";
            if (message.seats != null && $Object.hasOwnProperty.call(message, "seats")) {
                if (!$Array.isArray(message.seats))
                    return "seats: array expected";
                for (let i = 0; i < message.seats.length; ++i) {
                    let error = $root.game.SeatConfig.verify(message.seats[i], _depth + 1);
                    if (error)
                        return "seats." + error;
                }
            }
            if (message.state != null && $Object.hasOwnProperty.call(message, "state"))
                if (!$util.isString(message.state))
                    return "state: string expected";
            if (message.matchId != null && $Object.hasOwnProperty.call(message, "matchId"))
                if (!$util.isString(message.matchId))
                    return "matchId: string expected";
            if (message.matchMode != null && $Object.hasOwnProperty.call(message, "matchMode"))
                if (typeof message.matchMode !== "number" || (message.matchMode | 0) !== message.matchMode)
                    return "matchMode: enum value expected";
            if (message.chongciConfig != null && $Object.hasOwnProperty.call(message, "chongciConfig")) {
                let error = $root.game.ChongciConfig.verify(message.chongciConfig, _depth + 1);
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
        PrivateTableState.fromObject = function (object, _depth) {
            if (object instanceof $root.game.PrivateTableState)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.PrivateTableState: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.PrivateTableState();
            if (object.tableId != null)
                if (typeof object.tableId !== "string" || object.tableId.length)
                    message.tableId = $String(object.tableId);
            if (object.hostUserId != null)
                if ($Number(object.hostUserId) !== 0)
                    message.hostUserId = object.hostUserId >>> 0;
            if (object.seats) {
                if (!$Array.isArray(object.seats))
                    throw $TypeError(".game.PrivateTableState.seats: array expected");
                message.seats = $Array(object.seats.length);
                for (let i = 0; i < object.seats.length; ++i) {
                    if (!$util.isObject(object.seats[i]))
                        throw $TypeError(".game.PrivateTableState.seats: object expected");
                    message.seats[i] = $root.game.SeatConfig.fromObject(object.seats[i], _depth + 1);
                }
            }
            if (object.state != null)
                if (typeof object.state !== "string" || object.state.length)
                    message.state = $String(object.state);
            if (object.matchId != null)
                if (typeof object.matchId !== "string" || object.matchId.length)
                    message.matchId = $String(object.matchId);
            if (object.matchMode !== 0 && (typeof object.matchMode !== "string" || $root.game.MatchMode[object.matchMode] !== 0))
                switch (object.matchMode) {
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
                default:
                    if (typeof object.matchMode === "number" && (object.matchMode | 0) === object.matchMode)
                        message.matchMode = object.matchMode;
                }
            if (object.chongciConfig != null) {
                if (!$util.isObject(object.chongciConfig))
                    throw $TypeError(".game.PrivateTableState.chongciConfig: object expected");
                message.chongciConfig = $root.game.ChongciConfig.fromObject(object.chongciConfig, _depth + 1);
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
        PrivateTableState.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.arrays || options.defaults)
                object.seats = [];
            if (options.defaults) {
                object.tableId = "";
                object.hostUserId = 0;
                object.state = "";
                object.matchId = "";
                object.matchMode = options.enums === $String ? "MATCH_MODE_UNSPECIFIED" : 0;
                object.chongciConfig = null;
            }
            if (message.tableId != null && $Object.hasOwnProperty.call(message, "tableId"))
                object.tableId = message.tableId;
            if (message.hostUserId != null && $Object.hasOwnProperty.call(message, "hostUserId"))
                object.hostUserId = message.hostUserId;
            if (message.seats && message.seats.length) {
                object.seats = $Array(message.seats.length);
                for (let j = 0; j < message.seats.length; ++j)
                    object.seats[j] = $root.game.SeatConfig.toObject(message.seats[j], options, _depth + 1);
            }
            if (message.state != null && $Object.hasOwnProperty.call(message, "state"))
                object.state = message.state;
            if (message.matchId != null && $Object.hasOwnProperty.call(message, "matchId"))
                object.matchId = message.matchId;
            if (message.matchMode != null && $Object.hasOwnProperty.call(message, "matchMode"))
                object.matchMode = options.enums === $String ? $root.game.MatchMode[message.matchMode] === $undefined ? message.matchMode : $root.game.MatchMode[message.matchMode] : message.matchMode;
            if (message.chongciConfig != null && $Object.hasOwnProperty.call(message, "chongciConfig"))
                object.chongciConfig = $root.game.ChongciConfig.toObject(message.chongciConfig, options, _depth + 1);
            return object;
        };

        /**
         * Converts this PrivateTableState to JSON.
         * @function toJSON
         * @memberof game.PrivateTableState
         * @instance
         * @returns {Object.<string,*>} JSON object
         */
        PrivateTableState.prototype.toJSON = function() {
            return PrivateTableState.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for PrivateTableState
         * @function getTypeUrl
         * @memberof game.PrivateTableState
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        PrivateTableState.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.PrivateTableState";
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
        const valuesById = $Object.create(null), values = $Object.create(valuesById);
        values[valuesById[0] = "MATCH_MODE_UNSPECIFIED"] = 0;
        values[valuesById[1] = "MATCH_MODE_CLASSIC"] = 1;
        values[valuesById[2] = "MATCH_MODE_CHONGCI"] = 2;
        return values;
    })();

    game.ChongciConfig = (function() {

        /**
         * Properties of a ChongciConfig.
         * @typedef {Object} game.ChongciConfig.$Properties
         * @property {number} [startingScore] ChongciConfig startingScore
         * @property {number} [bustThreshold] ChongciConfig bustThreshold
         * @property {number} [maxHands] ChongciConfig maxHands
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a ChongciConfig.
         * @memberof game
         * @interface IChongciConfig
         * @augments game.ChongciConfig.$Properties
         * @deprecated Use game.ChongciConfig.$Properties instead.
         */

        /**
         * Shape of a ChongciConfig.
         * @typedef {game.ChongciConfig.$Properties} game.ChongciConfig.$Shape
         */

        /**
         * Constructs a new ChongciConfig.
         * @memberof game
         * @classdesc Represents a ChongciConfig.
         * @constructor
         * @param {game.ChongciConfig.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const ChongciConfig = function (properties) {
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.ChongciConfig.$Properties=} [properties] Properties to set
         * @returns {game.ChongciConfig} ChongciConfig instance
         * @type {{
         *   (properties: game.ChongciConfig.$Shape): game.ChongciConfig & game.ChongciConfig.$Shape;
         *   (properties?: game.ChongciConfig.$Properties): game.ChongciConfig;
         * }}
         */
        ChongciConfig.create = function(properties) {
            return new ChongciConfig(properties);
        };

        /**
         * Encodes the specified ChongciConfig message. Does not implicitly {@link game.ChongciConfig.verify|verify} messages.
         * @function encode
         * @memberof game.ChongciConfig
         * @static
         * @param {game.ChongciConfig.$Properties} message ChongciConfig message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        ChongciConfig.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.startingScore != null && $Object.hasOwnProperty.call(message, "startingScore") && message.startingScore !== 0)
                writer.uint32(/* id 1, wireType 0 =*/8).int32(message.startingScore);
            if (message.bustThreshold != null && $Object.hasOwnProperty.call(message, "bustThreshold") && message.bustThreshold !== 0)
                writer.uint32(/* id 2, wireType 0 =*/16).int32(message.bustThreshold);
            if (message.maxHands != null && $Object.hasOwnProperty.call(message, "maxHands") && message.maxHands !== 0)
                writer.uint32(/* id 3, wireType 0 =*/24).uint32(message.maxHands);
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified ChongciConfig message, length delimited. Does not implicitly {@link game.ChongciConfig.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.ChongciConfig
         * @static
         * @param {game.ChongciConfig.$Properties} message ChongciConfig message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        ChongciConfig.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a ChongciConfig message from the specified reader or buffer.
         * @function decode
         * @memberof game.ChongciConfig
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.ChongciConfig & game.ChongciConfig.$Shape} ChongciConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        ChongciConfig.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.ChongciConfig(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.startingScore = value;
                        else
                            delete message.startingScore;
                        continue;
                    }
                case 2: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.bustThreshold = value;
                        else
                            delete message.bustThreshold;
                        continue;
                    }
                case 3: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.maxHands = value;
                        else
                            delete message.maxHands;
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a ChongciConfig message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.ChongciConfig
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.ChongciConfig & game.ChongciConfig.$Shape} ChongciConfig
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        ChongciConfig.decodeDelimited = function(reader) {
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
        ChongciConfig.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.startingScore != null && $Object.hasOwnProperty.call(message, "startingScore"))
                if (!$util.isInteger(message.startingScore))
                    return "startingScore: integer expected";
            if (message.bustThreshold != null && $Object.hasOwnProperty.call(message, "bustThreshold"))
                if (!$util.isInteger(message.bustThreshold))
                    return "bustThreshold: integer expected";
            if (message.maxHands != null && $Object.hasOwnProperty.call(message, "maxHands"))
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
        ChongciConfig.fromObject = function (object, _depth) {
            if (object instanceof $root.game.ChongciConfig)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.ChongciConfig: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.ChongciConfig();
            if (object.startingScore != null)
                if ($Number(object.startingScore) !== 0)
                    message.startingScore = object.startingScore | 0;
            if (object.bustThreshold != null)
                if ($Number(object.bustThreshold) !== 0)
                    message.bustThreshold = object.bustThreshold | 0;
            if (object.maxHands != null)
                if ($Number(object.maxHands) !== 0)
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
        ChongciConfig.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.defaults) {
                object.startingScore = 0;
                object.bustThreshold = 0;
                object.maxHands = 0;
            }
            if (message.startingScore != null && $Object.hasOwnProperty.call(message, "startingScore"))
                object.startingScore = message.startingScore;
            if (message.bustThreshold != null && $Object.hasOwnProperty.call(message, "bustThreshold"))
                object.bustThreshold = message.bustThreshold;
            if (message.maxHands != null && $Object.hasOwnProperty.call(message, "maxHands"))
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
        ChongciConfig.prototype.toJSON = function() {
            return ChongciConfig.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for ChongciConfig
         * @function getTypeUrl
         * @memberof game.ChongciConfig
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        ChongciConfig.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.ChongciConfig";
        };

        return ChongciConfig;
    })();

    game.PlayerStanding = (function() {

        /**
         * Properties of a PlayerStanding.
         * @typedef {Object} game.PlayerStanding.$Properties
         * @property {number} [seat] PlayerStanding seat
         * @property {number} [rank] PlayerStanding rank
         * @property {number} [finalScore] PlayerStanding finalScore
         * @property {number} [netChange] PlayerStanding netChange
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a PlayerStanding.
         * @memberof game
         * @interface IPlayerStanding
         * @augments game.PlayerStanding.$Properties
         * @deprecated Use game.PlayerStanding.$Properties instead.
         */

        /**
         * Shape of a PlayerStanding.
         * @typedef {game.PlayerStanding.$Properties} game.PlayerStanding.$Shape
         */

        /**
         * Constructs a new PlayerStanding.
         * @memberof game
         * @classdesc Represents a PlayerStanding.
         * @constructor
         * @param {game.PlayerStanding.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const PlayerStanding = function (properties) {
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.PlayerStanding.$Properties=} [properties] Properties to set
         * @returns {game.PlayerStanding} PlayerStanding instance
         * @type {{
         *   (properties: game.PlayerStanding.$Shape): game.PlayerStanding & game.PlayerStanding.$Shape;
         *   (properties?: game.PlayerStanding.$Properties): game.PlayerStanding;
         * }}
         */
        PlayerStanding.create = function(properties) {
            return new PlayerStanding(properties);
        };

        /**
         * Encodes the specified PlayerStanding message. Does not implicitly {@link game.PlayerStanding.verify|verify} messages.
         * @function encode
         * @memberof game.PlayerStanding
         * @static
         * @param {game.PlayerStanding.$Properties} message PlayerStanding message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PlayerStanding.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.seat != null && $Object.hasOwnProperty.call(message, "seat") && message.seat !== 0)
                writer.uint32(/* id 1, wireType 0 =*/8).uint32(message.seat);
            if (message.rank != null && $Object.hasOwnProperty.call(message, "rank") && message.rank !== 0)
                writer.uint32(/* id 2, wireType 0 =*/16).uint32(message.rank);
            if (message.finalScore != null && $Object.hasOwnProperty.call(message, "finalScore") && message.finalScore !== 0)
                writer.uint32(/* id 3, wireType 0 =*/24).int32(message.finalScore);
            if (message.netChange != null && $Object.hasOwnProperty.call(message, "netChange") && message.netChange !== 0)
                writer.uint32(/* id 4, wireType 0 =*/32).int32(message.netChange);
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified PlayerStanding message, length delimited. Does not implicitly {@link game.PlayerStanding.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.PlayerStanding
         * @static
         * @param {game.PlayerStanding.$Properties} message PlayerStanding message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        PlayerStanding.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a PlayerStanding message from the specified reader or buffer.
         * @function decode
         * @memberof game.PlayerStanding
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.PlayerStanding & game.PlayerStanding.$Shape} PlayerStanding
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PlayerStanding.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.PlayerStanding(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.seat = value;
                        else
                            delete message.seat;
                        continue;
                    }
                case 2: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.rank = value;
                        else
                            delete message.rank;
                        continue;
                    }
                case 3: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.finalScore = value;
                        else
                            delete message.finalScore;
                        continue;
                    }
                case 4: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.int32())
                            message.netChange = value;
                        else
                            delete message.netChange;
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a PlayerStanding message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.PlayerStanding
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.PlayerStanding & game.PlayerStanding.$Shape} PlayerStanding
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        PlayerStanding.decodeDelimited = function(reader) {
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
        PlayerStanding.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.seat != null && $Object.hasOwnProperty.call(message, "seat"))
                if (!$util.isInteger(message.seat))
                    return "seat: integer expected";
            if (message.rank != null && $Object.hasOwnProperty.call(message, "rank"))
                if (!$util.isInteger(message.rank))
                    return "rank: integer expected";
            if (message.finalScore != null && $Object.hasOwnProperty.call(message, "finalScore"))
                if (!$util.isInteger(message.finalScore))
                    return "finalScore: integer expected";
            if (message.netChange != null && $Object.hasOwnProperty.call(message, "netChange"))
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
        PlayerStanding.fromObject = function (object, _depth) {
            if (object instanceof $root.game.PlayerStanding)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.PlayerStanding: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.PlayerStanding();
            if (object.seat != null)
                if ($Number(object.seat) !== 0)
                    message.seat = object.seat >>> 0;
            if (object.rank != null)
                if ($Number(object.rank) !== 0)
                    message.rank = object.rank >>> 0;
            if (object.finalScore != null)
                if ($Number(object.finalScore) !== 0)
                    message.finalScore = object.finalScore | 0;
            if (object.netChange != null)
                if ($Number(object.netChange) !== 0)
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
        PlayerStanding.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.defaults) {
                object.seat = 0;
                object.rank = 0;
                object.finalScore = 0;
                object.netChange = 0;
            }
            if (message.seat != null && $Object.hasOwnProperty.call(message, "seat"))
                object.seat = message.seat;
            if (message.rank != null && $Object.hasOwnProperty.call(message, "rank"))
                object.rank = message.rank;
            if (message.finalScore != null && $Object.hasOwnProperty.call(message, "finalScore"))
                object.finalScore = message.finalScore;
            if (message.netChange != null && $Object.hasOwnProperty.call(message, "netChange"))
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
        PlayerStanding.prototype.toJSON = function() {
            return PlayerStanding.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for PlayerStanding
         * @function getTypeUrl
         * @memberof game.PlayerStanding
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        PlayerStanding.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.PlayerStanding";
        };

        return PlayerStanding;
    })();

    game.MatchEndResult = (function() {

        /**
         * Properties of a MatchEndResult.
         * @typedef {Object} game.MatchEndResult.$Properties
         * @property {string} [reason] MatchEndResult reason
         * @property {number} [finalHandNum] MatchEndResult finalHandNum
         * @property {Array.<game.PlayerStanding.$Properties>} [standings] MatchEndResult standings
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */

        /**
         * Properties of a MatchEndResult.
         * @memberof game
         * @interface IMatchEndResult
         * @augments game.MatchEndResult.$Properties
         * @deprecated Use game.MatchEndResult.$Properties instead.
         */

        /**
         * Shape of a MatchEndResult.
         * @typedef {game.MatchEndResult.$Properties} game.MatchEndResult.$Shape
         */

        /**
         * Constructs a new MatchEndResult.
         * @memberof game
         * @classdesc Represents a MatchEndResult.
         * @constructor
         * @param {game.MatchEndResult.$Properties=} [properties] Properties to set
         * @property {Array.<Uint8Array>} [$unknowns] Unknown fields preserved while decoding when enabled
         */
        const MatchEndResult = function (properties) {
            this.standings = [];
            if (properties)
                for (let keys = $Object.keys(properties), i = 0; i < keys.length; ++i)
                    if (properties[keys[i]] != null && keys[i] !== "__proto__")
                        this[keys[i]] = properties[keys[i]];
        };

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
         * @param {game.MatchEndResult.$Properties=} [properties] Properties to set
         * @returns {game.MatchEndResult} MatchEndResult instance
         * @type {{
         *   (properties: game.MatchEndResult.$Shape): game.MatchEndResult & game.MatchEndResult.$Shape;
         *   (properties?: game.MatchEndResult.$Properties): game.MatchEndResult;
         * }}
         */
        MatchEndResult.create = function(properties) {
            return new MatchEndResult(properties);
        };

        /**
         * Encodes the specified MatchEndResult message. Does not implicitly {@link game.MatchEndResult.verify|verify} messages.
         * @function encode
         * @memberof game.MatchEndResult
         * @static
         * @param {game.MatchEndResult.$Properties} message MatchEndResult message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        MatchEndResult.encode = function (message, writer, _depth) {
            if (!writer)
                writer = $Writer.create();
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            if (message.reason != null && $Object.hasOwnProperty.call(message, "reason") && message.reason !== "")
                writer.uint32(/* id 1, wireType 2 =*/10).string(message.reason);
            if (message.finalHandNum != null && $Object.hasOwnProperty.call(message, "finalHandNum") && message.finalHandNum !== 0)
                writer.uint32(/* id 2, wireType 0 =*/16).uint32(message.finalHandNum);
            if (message.standings != null && message.standings.length)
                for (let i = 0; i < message.standings.length; ++i)
                    $root.game.PlayerStanding.encode(message.standings[i], writer.uint32(/* id 3, wireType 2 =*/26).fork(), _depth + 1).ldelim();
            if (message.$unknowns != null && $Object.hasOwnProperty.call(message, "$unknowns"))
                for (let i = 0; i < message.$unknowns.length; ++i)
                    writer.raw(message.$unknowns[i]);
            return writer;
        };

        /**
         * Encodes the specified MatchEndResult message, length delimited. Does not implicitly {@link game.MatchEndResult.verify|verify} messages.
         * @function encodeDelimited
         * @memberof game.MatchEndResult
         * @static
         * @param {game.MatchEndResult.$Properties} message MatchEndResult message or plain object to encode
         * @param {$protobuf.Writer} [writer] Writer to encode to
         * @returns {$protobuf.Writer} Writer
         */
        MatchEndResult.encodeDelimited = function(message, writer) {
            return this.encode(message, writer && writer.len ? writer.fork() : writer).ldelim();
        };

        /**
         * Decodes a MatchEndResult message from the specified reader or buffer.
         * @function decode
         * @memberof game.MatchEndResult
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @param {number} [length] Message length if known beforehand
         * @returns {game.MatchEndResult & game.MatchEndResult.$Shape} MatchEndResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        MatchEndResult.decode = function (reader, length, _end, _depth, _target) {
            if (!(reader instanceof $Reader))
                reader = $Reader.create(reader);
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $Reader.recursionLimit)
                throw $Error("max depth exceeded");
            let end = length === $undefined ? reader.len : reader.pos + length, message = _target || new $root.game.MatchEndResult(), value;
            while (reader.pos < end) {
                let start = reader.pos;
                let tag = reader.tag();
                if (tag === _end) {
                    _end = $undefined;
                    break;
                }
                let wireType = tag & 7;
                switch (tag >>>= 3) {
                case 1: {
                        if (wireType !== 2)
                            break;
                        if ((value = reader.stringVerify()).length)
                            message.reason = value;
                        else
                            delete message.reason;
                        continue;
                    }
                case 2: {
                        if (wireType !== 0)
                            break;
                        if (value = reader.uint32())
                            message.finalHandNum = value;
                        else
                            delete message.finalHandNum;
                        continue;
                    }
                case 3: {
                        if (wireType !== 2)
                            break;
                        if (!(message.standings && message.standings.length))
                            message.standings = [];
                        message.standings.push($root.game.PlayerStanding.decode(reader, reader.uint32(), $undefined, _depth + 1));
                        continue;
                    }
                }
                reader.skipType(wireType, _depth, tag);
                if (!reader.discardUnknown) {
                    $util.makeProp(message, "$unknowns", false);
                    (message.$unknowns || (message.$unknowns = [])).push(reader.raw(start, reader.pos));
                }
            }
            if (_end !== $undefined)
                throw $Error("missing end group");
            return message;
        };

        /**
         * Decodes a MatchEndResult message from the specified reader or buffer, length delimited.
         * @function decodeDelimited
         * @memberof game.MatchEndResult
         * @static
         * @param {$protobuf.Reader|Uint8Array} reader Reader or buffer to decode from
         * @returns {game.MatchEndResult & game.MatchEndResult.$Shape} MatchEndResult
         * @throws {Error} If the payload is not a reader or valid buffer
         * @throws {$protobuf.util.ProtocolError} If required fields are missing
         */
        MatchEndResult.decodeDelimited = function(reader) {
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
        MatchEndResult.verify = function (message, _depth) {
            if (typeof message !== "object" || message === null)
                return "object expected";
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                return "max depth exceeded";
            if (message.reason != null && $Object.hasOwnProperty.call(message, "reason"))
                if (!$util.isString(message.reason))
                    return "reason: string expected";
            if (message.finalHandNum != null && $Object.hasOwnProperty.call(message, "finalHandNum"))
                if (!$util.isInteger(message.finalHandNum))
                    return "finalHandNum: integer expected";
            if (message.standings != null && $Object.hasOwnProperty.call(message, "standings")) {
                if (!$Array.isArray(message.standings))
                    return "standings: array expected";
                for (let i = 0; i < message.standings.length; ++i) {
                    let error = $root.game.PlayerStanding.verify(message.standings[i], _depth + 1);
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
        MatchEndResult.fromObject = function (object, _depth) {
            if (object instanceof $root.game.MatchEndResult)
                return object;
            if (!$util.isObject(object))
                throw $TypeError(".game.MatchEndResult: object expected");
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let message = new $root.game.MatchEndResult();
            if (object.reason != null)
                if (typeof object.reason !== "string" || object.reason.length)
                    message.reason = $String(object.reason);
            if (object.finalHandNum != null)
                if ($Number(object.finalHandNum) !== 0)
                    message.finalHandNum = object.finalHandNum >>> 0;
            if (object.standings) {
                if (!$Array.isArray(object.standings))
                    throw $TypeError(".game.MatchEndResult.standings: array expected");
                message.standings = $Array(object.standings.length);
                for (let i = 0; i < object.standings.length; ++i) {
                    if (!$util.isObject(object.standings[i]))
                        throw $TypeError(".game.MatchEndResult.standings: object expected");
                    message.standings[i] = $root.game.PlayerStanding.fromObject(object.standings[i], _depth + 1);
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
        MatchEndResult.toObject = function (message, options, _depth) {
            if (!options)
                options = {};
            if (_depth === $undefined)
                _depth = 0;
            if (_depth > $util.recursionLimit)
                throw $Error("max depth exceeded");
            let object = {};
            if (options.arrays || options.defaults)
                object.standings = [];
            if (options.defaults) {
                object.reason = "";
                object.finalHandNum = 0;
            }
            if (message.reason != null && $Object.hasOwnProperty.call(message, "reason"))
                object.reason = message.reason;
            if (message.finalHandNum != null && $Object.hasOwnProperty.call(message, "finalHandNum"))
                object.finalHandNum = message.finalHandNum;
            if (message.standings && message.standings.length) {
                object.standings = $Array(message.standings.length);
                for (let j = 0; j < message.standings.length; ++j)
                    object.standings[j] = $root.game.PlayerStanding.toObject(message.standings[j], options, _depth + 1);
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
        MatchEndResult.prototype.toJSON = function() {
            return MatchEndResult.toObject(this, $protobuf.util.toJSONOptions);
        };

        /**
         * Gets the type url for MatchEndResult
         * @function getTypeUrl
         * @memberof game.MatchEndResult
         * @static
         * @param {string} [prefix] Custom type url prefix, defaults to `"type.googleapis.com"`
         * @returns {string} The type url
         */
        MatchEndResult.getTypeUrl = function(prefix) {
            if (prefix === $undefined)
                prefix = "type.googleapis.com";
            return prefix + "/game.MatchEndResult";
        };

        return MatchEndResult;
    })();

    return game;
})();

export {
  $root as default
};
