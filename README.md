# Tech--Titans
This repository is about Hackathon ROOT -36 
# Terminal Mafia — ROOT 36 Hackathon

**Terminal Mafia** is a CLI-based social deduction game built in Python for the ROOT 36 Hackathon. Players are divided into two opposing factions—**Hunters** and **Survivors**—navigating alternating Day and Night cycles filled with role abilities, discussion, investigation, and strategic voting.

---

## 🎮 Game Overview

A hidden Shapeshifter lurks among the village. The Survivors must work together using special abilities and daytime discussions to uncover and eliminate the Shapeshifter before the overall casualty count reaches the critical threshold.

* **Total Players:** 5
* **Team 1 (Hunters):** Shapeshifter
* **Team 2 (Survivors):** Villagers (2), Soldier (1), Detective (1)
* **Max Death Limit:** 3 players

---

## 🎭 Roles & Factions

| Role | Faction | Functionality |
| :--- | :--- | :--- |
| **Villager** (x2) | Survivors | Common villagers who participate in daytime discussions and voting. |
| **Soldier** | Survivors | Protects one player of their choice each night from being killed. |
| **Detective** | Survivors | Investigates one player each night to determine if they are the Shapeshifter. |
| **Shapeshifter** | Hunters | Kills one random non-shapeshifter player per night. Can also report dead bodies during daytime discussions to disguise their intent. |

---

## 🌗 Gameplay Mechanics

### 🌃 Night Phase
1. **Soldier Action:** Selects a player to protect for the upcoming night.
2. **Detective Action:** Investigates a player to reveal whether or not they are the Shapeshifter.
3. **Shapeshifter Action:** Secretly targets and kills a random player (if the target was protected by the Soldier, the kill is blocked).

### ⏳ Phase Transition Delay
* A **2-minute (120-second) countdown timer** runs between Day and Night transitions to simulate real-time deliberation and phase shifts.
* *(Developer Mode: Press `Ctrl+C` during the countdown to skip the wait time during testing).*

### ☀️ Day Phase
1. **Body Discovery & Discussion:** Any surviving player (including the Shapeshifter) can report a discovered body to trigger the morning report.
2. **Voting Phase:** Every living player casts a vote guessing who the Shapeshifter is. The player receiving the most votes is eliminated.

---

## 🏆 Win Conditions

* **Survivors Win (Team 2):** The Shapeshifter is correctly identified and voted out during the Day Phase.
* **Hunters Win (Team 1):** A total of **3 players** die across the game without the Shapeshifter being caught.

---

## 🚀 Getting Started

### Prerequisites
* Python 3.7 or higher installed on your system.

### Running the Game

1. Clone the repository:
   ```bash
   git clone [https://github.com/your-username/terminal-mafia.git](https://github.com/your-username/terminal-mafia.git)
   cd terminal-mafia

   Run the application :
   python main.py

   The names of the 5 players:
   1. villager 1.
   2. villager 2.
   3. detective.
   4. soldier.
   5. shapeshifter.

   License
   Developed for the ROOT 36 Hackathon.
