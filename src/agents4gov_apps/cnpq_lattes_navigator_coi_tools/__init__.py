"""CNPq/Lattes COI tool bundle."""

from .lattes_coi_judge import Tools as CoiJudgeTools
from .lattes_collector import Tools as LattesCollectorTools

__all__ = ["CoiJudgeTools", "LattesCollectorTools"]
