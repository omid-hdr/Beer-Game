import io
import matplotlib.pyplot as plt
from typing import List
from domain.models import GameSession, Role


def create_global_cost_bar_chart(game: GameSession) -> io.BytesIO:
    """Chart 1: Bar chart of final total costs per team."""
    plt.figure(figsize=(10, 6))
    teams = list(game.teams.keys())
    # Sum the total_cost of all 4 players in each team
    costs = [sum(p.total_cost for p in t.players.values()) for t in game.teams.values()]

    plt.bar(teams, costs, color='skyblue')
    plt.title("Total Supply Chain Cost per Team")
    plt.xlabel("Team Code")
    plt.ylabel("Total Cost ($)")

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf


def create_team_inventory_chart(game: GameSession, team_code: str) -> io.BytesIO:
    """Chart 3: Line chart of inventory levels per role over time for a specific team."""
    plt.figure(figsize=(10, 6))
    team = game.teams[team_code]
    weeks = range(1, len(next(iter(team.players.values())).history_inventory) + 1)

    colors = {Role.FACTORY: 'red', Role.DISTRIBUTOR: 'orange', Role.WHOLESALER: 'green', Role.RETAILER: 'blue'}

    for role, player in team.players.items():
        plt.plot(weeks, player.history_inventory, label=role.value, color=colors[role], marker='o')

    plt.title(f"Inventory Levels Over Time - Team {team_code}")
    plt.xlabel("Week")
    plt.ylabel("Inventory Units")
    plt.legend()
    plt.grid(True)

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf

# (Similar functions would be written for Chart 2: Global Cumulative Line and Chart 4: Team-Specific Cost Line using the same io.BytesIO pattern)