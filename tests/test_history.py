"""Tests de consolidación del historial de MT5 (_consolidate_deals).

Cubre el bug donde la web mostraba la dirección INVERTIDA (tomaba el último
deal = cierre, cuyo tipo es el opuesto a la posición: un BUY se cierra con un
deal SELL) y perdía el precio de apertura.

Run:  python -m pytest tests/test_history.py -v
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import _consolidate_deals

# Constantes MT5 (DEAL_ENTRY_IN/OUT, DEAL_TYPE_BUY/SELL)
DEAL_ENTRY_IN, DEAL_ENTRY_OUT = 0, 1
DEAL_TYPE_BUY, DEAL_TYPE_SELL = 0, 1


class Deal:
    def __init__(self, ticket, position_id, entry, dtype, time, price,
                 volume=0.1, profit=0.0, commission=0.0, swap=0.0, symbol="EURUSD"):
        self.ticket = ticket
        self.position_id = position_id
        self.entry = entry
        self.type = dtype
        self.time = time
        self.price = price
        self.volume = volume
        self.profit = profit
        self.commission = commission
        self.swap = swap
        self.symbol = symbol


def test_direction_real_pos_closed_buy():
    """BUY abierta a 1.16279 y cerrada con deal SELL a 1.16318: +24.57."""
    deals = [
        Deal(1, 101, DEAL_ENTRY_IN, DEAL_TYPE_BUY, 1000, 1.16279, volume=0.63),
        Deal(2, 101, DEAL_ENTRY_OUT, DEAL_TYPE_SELL, 1001, 1.16318, volume=0.63, profit=24.57),
    ]
    rec = _consolidate_deals(deals)[101]
    assert (rec["entry"].price, rec["exit"].price) == (1.16279, 1.16318)
    assert round(rec["profit"], 2) == 24.57


def test_direction_seen_from_entry_deal():
    """El tipo del historial debe salir del deal de ENTRADA, no del de cierre."""
    deals = [
        Deal(1, 101, DEAL_ENTRY_IN, DEAL_TYPE_SELL, 1000, 1.16318, volume=0.63),
        Deal(2, 101, DEAL_ENTRY_OUT, DEAL_TYPE_BUY, 1001, 1.16279, volume=0.63, profit=24.57),
    ]
    rec = _consolidate_deals(deals)[101]
    assert rec["entry"].type == DEAL_TYPE_SELL


def test_partial_closes_sum_profit():
    """Cierres parciales (2 deals OUT) acumulan profit y conservan la entrada."""
    deals = [
        Deal(1, 102, DEAL_ENTRY_IN, DEAL_TYPE_BUY, 1000, 1.1000, volume=0.20),
        Deal(2, 102, DEAL_ENTRY_OUT, DEAL_TYPE_SELL, 1002, 1.1010, volume=0.10, profit=10.0),
        Deal(3, 102, DEAL_ENTRY_OUT, DEAL_TYPE_SELL, 1003, 1.1020, volume=0.10, profit=20.0),
    ]
    rec = _consolidate_deals(deals)[102]
    assert round(rec["profit"], 2) == 30.0
    assert rec["entry"].price == 1.1000
    assert rec["exit"].price == 1.1020


def test_swap_and_commission_accumulate():
    """Las patas de swap/comisión del mismo position_id suman también."""
    deals = [
        Deal(1, 103, DEAL_ENTRY_IN, DEAL_TYPE_BUY, 1000, 1.1000),
        Deal(2, 103, DEAL_ENTRY_OUT, DEAL_TYPE_SELL, 1001, 1.1010, profit=5.0),
        Deal(3, 103, DEAL_ENTRY_OUT, DEAL_TYPE_SELL, 1002, 1.1010, commission=-0.5),
        Deal(4, 103, DEAL_ENTRY_OUT, DEAL_TYPE_SELL, 1003, 1.1010, swap=-0.3),
    ]
    rec = _consolidate_deals(deals)[103]
    assert round(rec["profit"], 2) == 5.0
    assert round(rec["commission"], 2) == -0.5
    assert round(rec["swap"], 2) == -0.3


def test_position_id_zero_ignored():
    deals = [
        Deal(1, 0, DEAL_ENTRY_IN, DEAL_TYPE_BUY, 1000, 1.1000),
        Deal(2, 104, DEAL_ENTRY_IN, DEAL_TYPE_BUY, 1000, 1.1050),
    ]
    consolidated = _consolidate_deals(deals)
    assert 0 not in consolidated
    assert 104 in consolidated


def test_multiple_positions_isolated():
    deals = [
        Deal(1, 201, DEAL_ENTRY_IN, DEAL_TYPE_BUY, 1000, 1.1000, profit=0),
        Deal(2, 201, DEAL_ENTRY_OUT, DEAL_TYPE_SELL, 1001, 1.1005, profit=5.0),
        Deal(3, 202, DEAL_ENTRY_IN, DEAL_TYPE_SELL, 2000, 1.1200, profit=0),
        Deal(4, 202, DEAL_ENTRY_OUT, DEAL_TYPE_BUY, 2001, 1.1195, profit=5.0),
    ]
    consolidated = _consolidate_deals(deals)
    assert set(consolidated) == {201, 202}
    assert consolidated[202]["entry"].type == DEAL_TYPE_SELL