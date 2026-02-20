# resources.py

HELP_TEXT = """
🎮 **Beer Distribution Game - Player Guide**

**The Concept:**
You are part of a 4-stage supply chain:
🏭 **Factory** ➔ 🚚 **Distributor** ➔ 🏢 **Wholesaler** ➔ 🏪 **Retailer**

**Your Goal:**
Minimize total costs for your team. You must fulfill incoming orders while avoiding:
1.  **Overstocking:** Holding inventory costs **$1.0** per unit/week.
2.  **Backlogs:** Failing to fulfill an order costs **$2.0** per unit/week.

**How to Play:**
1.  **The Delay:** When you place an order, it takes **2 weeks** to arrive in your inventory. You must plan ahead!
2.  **Communication:** You cannot talk to teammates. Your *only* communication is the number of units you order.
3.  **The Loop:** * Receive valid orders from the downstream node.
    * Receive shipments from the upstream node.
    * Type a number to place your order for next week.

**Commands:**
/join `<GameID>` - Join a game lobby.
/team `<TeamCode>` - Join a specific team.
/help - Show this message.
"""

START_TEXT = """
👋 **Welcome to the Beer Game Bot!**

This bot runs the classic System Dynamics simulation.
To start, wait for your instructor to give you a **Game ID**.

Then run: `/join <GameID>`
"""

GAME_NOT_FOUND = "❌ **Game not found.**\nPlease check the ID. If the bot was restarted, the game memory has been cleared."

