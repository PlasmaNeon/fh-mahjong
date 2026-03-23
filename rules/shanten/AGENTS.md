# rules/shanten/

> Shanten and discard-analysis helpers for Fenghua mahjong.

## Overview

This package computes closed-hand progress metrics for Fenghua hands. It supports standard hands, seven pairs, and independence, including wild-tile handling. The package is shared by the server shanten API, in-game shanten display, and heuristic bot decision-making.

## Key Files

- **shanten.go** — Core table-based shanten algorithm with wild support.
- **analysis.go** — Higher-level helpers:
  - `Analyze()` / `AnalyzeFromTiles()` — route-by-route shanten breakdown
  - `AnalyzeHand()` — current-hand useful-tile count plus discard-option analysis
  - `FindUsefulTilesFromTiles()` — effective draws for the current hand state
- **tables.go** — Precomputed suit/honor DP tables.
- **shanten_test.go** — Route, wild, edge-case, and benchmark coverage.

## Architecture Notes

- Flowers are excluded from shanten calculations; wild flowers are counted as wilds instead.
- `RouteUnavailable` marks routes that are invalid for the current hand shape (for example seven pairs after opening the hand).
- Discard analysis is keyed by tile type (`suit` + `value`) rather than unique tile ID so API consumers and bots get stable, deterministic options.
