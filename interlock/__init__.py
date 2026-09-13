"""Interlock: a commit gate for AI agent effects. See README."""
from .gate import Gate, Naive, IdempotencyOnly, DurableExecution, SimulatedCrash
from .journal import Journal, effect_id_for
from .leases import Leases
from .easy import Interlock
