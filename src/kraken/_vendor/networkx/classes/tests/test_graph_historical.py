"""Original NetworkX graph tests"""
from .... import networkx
from .... import networkx as nx

from .historical_tests import HistoricalTests


class TestGraphHistorical(HistoricalTests):
    @classmethod
    def setup_class(cls):
        HistoricalTests.setup_class()
        cls.G = nx.Graph
