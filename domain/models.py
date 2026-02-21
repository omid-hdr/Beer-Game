from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class Role(str, Enum):
    FACTORY = "Factory"
    DISTRIBUTOR = "Distributor"
    WHOLESALER = "Wholesaler"
    RETAILER = "Retailer"


@dataclass
class GameConfig:
    inventory_cost: float = 1.0
    backlog_cost: float = 2.0
    starting_inventory: int = 12
    starting_pipeline: int = 4 # Default items already in transit
    shipping_delay: int = 2


@dataclass
class PlayerState:
    role: Role
    user_id: Optional[int] = None  # Will be populated in Phase 3
    inventory: int = 0
    backlog: int = 0
    total_cost: float = 0.0

    # Represents items arriving in [1 week, 2 weeks]
    shipment_pipeline: List[int] = field(default_factory=list)

    # Temporary state for the current round
    current_order_placed: Optional[int] = None
    demand_received: int = 0

    history_inventory: List[int] = field(default_factory=list)
    history_cost: List[float] = field(default_factory=list)

    history_order: list = field(default_factory=list)
    history_backlog: list = field(default_factory=list)

    def __post_init__(self):
        # Initialize pipeline with starting items if empty
        if not self.shipment_pipeline:
            self.shipment_pipeline = [0, 0]

    def receive_shipment(self):
        """Pops the first item from the pipeline (arriving this week) and adds to inventory."""
        if self.shipment_pipeline:
            arrived = self.shipment_pipeline.pop(0)
            self.inventory += arrived

    def calculate_cost(self, config: GameConfig) -> float:
        """Calculates cost for the current week and adds to total."""
        weekly_cost = (self.inventory * config.inventory_cost) + (self.backlog * config.backlog_cost)
        self.total_cost += weekly_cost
        return weekly_cost


@dataclass
class TeamState:
    team_code: str
    current_week: int = 1
    players: Dict[Role, PlayerState] = field(default_factory=dict)

    def __post_init__(self):
        # Initialize the 4 roles if not provided
        if not self.players:
            for role in Role:
                self.players[role] = PlayerState(role=role)

    def is_ready_for_next_week(self) -> bool:
        """Checks if all 4 players have placed their orders for the current week."""
        return all(p.current_order_placed is not None for p in self.players.values())

    def advance_week(self, customer_demand: int, config: GameConfig):
        """Executes the simulation steps for a single week. Must only be called if is_ready_for_next_week() is True."""
        if not self.is_ready_for_next_week():
            raise ValueError("Not all players have placed orders yet.")

        # Reference to roles for easy access
        f, d, w, r = (
            self.players[Role.FACTORY],
            self.players[Role.DISTRIBUTOR],
            self.players[Role.WHOLESALER],
            self.players[Role.RETAILER]
        )

        # 1. Receive incoming shipments
        for player in self.players.values():
            player.receive_shipment()

        # 2. Receive orders from downstream (Information flow)
        r.demand_received = customer_demand
        w.demand_received = r.current_order_placed
        d.demand_received = w.current_order_placed
        f.demand_received = d.current_order_placed

        # Factory's own order goes into production (treated as incoming demand from itself)
        factory_production_order = f.current_order_placed

        # 3. Fulfill orders (Material flow downstream)
        self._fulfill_and_ship(f, d)  # Factory ships to Distributor
        self._fulfill_and_ship(d, w)  # Distributor ships to Wholesaler
        self._fulfill_and_ship(w, r)  # Wholesaler ships to Retailer

        # Retailer ships to Final Customer (leaves the system)
        self._fulfill_and_ship(r, None)

        # Factory production enters pipeline (arrives in 2 weeks)
        f.shipment_pipeline.append(factory_production_order)

        # 4. Calculate costs & reset orders for the next week
        for player in self.players.values():
            weekly_cost = player.calculate_cost(config)
            player.history_inventory.append(player.inventory)
            player.history_cost.append(weekly_cost)
            player.history_order.append(player.current_order_placed)
            player.history_backlog.append(player.backlog)
            player.current_order_placed = None  # Reset for next round
            
        self.current_week += 1

    def _fulfill_and_ship(self, sender: PlayerState, receiver: Optional[PlayerState]):
        """Calculates how much can be shipped, updates sender's inventory/backlog, and adds to receiver's pipeline."""
        total_demand = sender.demand_received + sender.backlog

        if sender.inventory >= total_demand:
            shipped = total_demand
            sender.inventory -= total_demand
            sender.backlog = 0
        else:
            shipped = sender.inventory
            sender.backlog = total_demand - sender.inventory
            sender.inventory = 0

        # Add to receiver's pipeline (2 weeks out)
        if receiver:
            receiver.shipment_pipeline.append(shipped)


@dataclass
class GameSession:
    game_id: str
    total_rounds: int
    demand_pattern: List[int]
    teams: Dict[str, TeamState] = field(default_factory=dict)
    config: GameConfig = field(default_factory=GameConfig)

    def get_demand_for_week(self, week: int) -> int:
        """Returns the customer demand for the given week, repeating the last value if necessary."""
        if week < 1:
            raise ValueError("Week must be >= 1")

        index = week - 1
        if index < len(self.demand_pattern):
            return self.demand_pattern[index]
        else:
            return self.demand_pattern[-1]  # Extrapolate the last demand value