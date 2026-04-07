"""DSE algorithm implementations."""
from dse.algorithms import bo_gp, mobo, nsga2, random_search

REGISTRY = {
    "bo_gp": bo_gp,
    "nsga2": nsga2,
    "mobo": mobo,
    "random": random_search,
}

__all__ = ["bo_gp", "mobo", "nsga2", "random_search", "REGISTRY"]
