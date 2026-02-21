import io
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from domain.models import GameSession, Role


def create_team_inventory_chart(game: GameSession, team_code: str) -> io.BytesIO:
    """Generates a line chart showing the Bullwhip Effect in inventory levels."""
    plt.figure(figsize=(10, 6))
    team = game.teams[team_code]

    # Get the number of weeks played
    weeks_played = len(next(iter(team.players.values())).history_inventory)
    weeks = range(1, weeks_played + 1)

    colors = {Role.FACTORY: 'red', Role.DISTRIBUTOR: 'orange', Role.WHOLESALER: 'green', Role.RETAILER: 'blue'}

    for role, player in team.players.items():
        if len(player.history_inventory) > 0:
            plt.plot(weeks, player.history_inventory, label=role.value, color=colors[role], marker='o')

    plt.title(f"Bullwhip Effect: Inventory Levels - Team {team_code}")
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


def create_global_cost_bar_chart(game: GameSession) -> io.BytesIO:
    """Generates a bar chart comparing total costs across all teams."""
    plt.figure(figsize=(10, 6))
    teams = list(game.teams.keys())
    costs = [sum(p.total_cost for p in t.players.values()) for t in game.teams.values()]

    plt.bar(teams, costs, color='skyblue')
    plt.title("Final Supply Chain Cost per Team")
    plt.xlabel("Team Code")
    plt.ylabel("Total Cost ($)")

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf


def create_team_detailed_dashboard(game: GameSession, team_code: str) -> io.BytesIO:
    """Generates a 2x2 subplot dashboard showing Orders vs Backlog vs Inventory for each role."""
    team = game.teams[team_code]
    weeks_played = len(next(iter(team.players.values())).history_inventory)
    weeks = range(1, weeks_played + 1)

    fig, axs = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"Detailed Performance Dashboard - Team {team_code}", fontsize=16)

    roles = [Role.FACTORY, Role.DISTRIBUTOR, Role.WHOLESALER, Role.RETAILER]
    axes_flat = axs.flatten()

    for ax, role in zip(axes_flat, roles):
        player = team.players[role]
        if len(player.history_inventory) > 0:
            ax.plot(weeks, player.history_inventory, label='Inventory', color='green', marker='o')
            ax.plot(weeks, player.history_backlog, label='Backlog', color='red', linestyle='--', marker='x')
            ax.plot(weeks, player.history_order, label='Order Placed', color='blue', linestyle=':', marker='s')

        ax.set_title(role.value)
        ax.set_xlabel("Week")
        ax.set_ylabel("Units")
        ax.legend()
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf