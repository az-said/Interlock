"""Interlock: a commit gate for AI agent effects. See README."""
from .gate import Gate, Naive, IdempotencyOnly, DurableExecution, SimulatedCrash
from .journal import Journal, SqliteJournal, effect_id_for, open_journal
from .leases import Leases
from .easy import Interlock
