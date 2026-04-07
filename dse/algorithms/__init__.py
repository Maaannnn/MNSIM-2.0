"""DSE algorithm implementations."""
from dse.algorithms import bo_gp, mobo, nsga2

REGISTRY = {
    "bo_gp": bo_gp,
    "nsga2": nsga2,
    "mobo": mobo,
}

__all__ = ["bo_gp", "mobo", "nsga2", "REGISTRY"]
