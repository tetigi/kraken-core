from ..... import networkx as nx
from .....networkx.algorithms import approximation as a


def test_min_maximal_matching():
    # smoke test
    G = nx.Graph()
    assert len(a.min_maximal_matching(G)) == 0
