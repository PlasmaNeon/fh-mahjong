"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createFileContext = createFileContext;
const ts_proto_descriptors_1 = require("ts-proto-descriptors");
function createFileContext(file) {
    const edition = file.edition !== ts_proto_descriptors_1.Edition.EDITION_UNKNOWN ? file.edition : undefined;
    const isEdition = edition !== undefined;
    const isProto3Syntax = file.syntax === "proto3" || (file.syntax !== "proto2" && isProto3Edition(edition));
    return {
        isProto3Syntax,
        isEdition,
        edition,
    };
}
function isProto3Edition(edition) {
    if (edition === undefined) {
        return false;
    }
    return edition === ts_proto_descriptors_1.Edition.EDITION_PROTO3 || edition === ts_proto_descriptors_1.Edition.EDITION_2023 || edition === ts_proto_descriptors_1.Edition.EDITION_2024;
}
