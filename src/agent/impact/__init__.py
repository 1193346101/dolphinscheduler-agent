"""Impact analysis module - Analyze downstream dependencies"""

from .analyzer import ImpactAnalyzer
from .topology import ImpactTopologyBuilder

__all__ = ["ImpactAnalyzer", "ImpactTopologyBuilder"]