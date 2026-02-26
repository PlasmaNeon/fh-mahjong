# Custom Mahjong Game - User Guide

## Overview
A web-based, cross-platform Mahjong game inspired by platforms like Tenhou and Majsoul. This project focuses on implementing custom hometown rules rather than standard Riichi rules, complete with user accounts, match replays, and advanced AI opponents.

## Core Features
1. **Cross-Platform Web Play**: A responsive web application allowing users to log in, matchmake, and play seamlessly across different devices.
2. **Custom Hometown Rules**: Core game logic tailored specifically to your hometown's unique Mahjong rules (to be defined).
3. **Replay System**: Comprehensive saving of every match played, enabling players to review their games and analyze decisions.
4. **Reinforcement Learning (RL) AI**: Advanced AI agents trained via RL to understand the custom rules, discover optimal strategies, and serve as challenging opponents or analytical tools.

## Architecture Guidelines (To Be Expanded)
- **Frontend**: Web technologies (HTML/JS/CSS or framework) for the game UI.
- **Backend / Game Server**: Manages user authentication, match sessions, broadcasting moves, and validating custom rule logic.
- **Database**: Stores user accounts, match history, and serialized replays.
- **AI Training Pipeline**: A separate module dedicated to simulating games at high speed and training the RL models based on the custom ruleset.

## Next Steps
- [ ] Receive and document the specific custom hometown rules.
- [ ] Finalize the technology stack based on the rules.
- [ ] Draft an implementation plan covering the web application and RL pipeline.
